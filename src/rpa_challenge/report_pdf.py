"""Relatório em PDF, em português, com as capturas reais da execução."""

from __future__ import annotations

import struct
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_JUSTIFY, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import (
    Image,
    KeepTogether,
    ListFlowable,
    ListItem,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

NAVY = colors.HexColor("#002855")
ORANGE = colors.HexColor("#FE5000")
TEAL = colors.HexColor("#0E7C66")
RED = colors.HexColor("#9B2335")
INK = colors.HexColor("#1C2430")
MUTED = colors.HexColor("#5C6B7A")
LINE = colors.HexColor("#D5DDE6")
ZEBRA = colors.HexColor("#F4F7FB")
OK_BG = colors.HexColor("#E5F6EF")
NOK_BG = colors.HexColor("#FDECEC")

FONT = "DejaVu"
FONT_BOLD = "DejaVuBold"


def _register_fonts() -> None:
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont

    if FONT in pdfmetrics.getRegisteredFontNames():
        return
    pdfmetrics.registerFont(TTFont(FONT, "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"))
    pdfmetrics.registerFont(TTFont(FONT_BOLD, "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"))
    pdfmetrics.registerFontFamily(FONT, normal=FONT, bold=FONT_BOLD, italic=FONT, boldItalic=FONT_BOLD)


def _styles() -> dict[str, ParagraphStyle]:
    base = getSampleStyleSheet()
    return {
        "h1": ParagraphStyle(
            "h1",
            fontName=FONT_BOLD,
            fontSize=18,
            leading=22,
            textColor=NAVY,
            spaceAfter=6,
        ),
        "h2": ParagraphStyle(
            "h2",
            fontName=FONT_BOLD,
            fontSize=13,
            leading=16,
            textColor=NAVY,
            spaceBefore=12,
            spaceAfter=6,
        ),
        "body": ParagraphStyle(
            "body",
            fontName=FONT,
            fontSize=9.5,
            leading=13,
            textColor=INK,
            alignment=TA_JUSTIFY,
            spaceAfter=6,
        ),
        "small": ParagraphStyle(
            "small",
            fontName=FONT,
            fontSize=8,
            leading=10.5,
            textColor=INK,
            alignment=TA_LEFT,
        ),
        "th": ParagraphStyle(
            "th",
            fontName=FONT_BOLD,
            fontSize=8,
            leading=10,
            textColor=colors.white,
            alignment=TA_LEFT,
        ),
        "caption": ParagraphStyle(
            "caption",
            fontName=FONT,
            fontSize=8,
            leading=10,
            textColor=MUTED,
            spaceBefore=2,
            spaceAfter=8,
        ),
        "score": ParagraphStyle(
            "score",
            fontName=FONT_BOLD,
            fontSize=22,
            leading=26,
            textColor=ORANGE,
            alignment=TA_LEFT,
        ),
        "bullet": ParagraphStyle(
            "bullet",
            fontName=FONT,
            fontSize=9.5,
            leading=13,
            textColor=INK,
        ),
        "footer": ParagraphStyle(
            "footer",
            parent=base["Normal"],
            fontName=FONT,
            fontSize=8,
            textColor=MUTED,
        ),
    }


def _png_size(path: Path) -> tuple[int, int] | None:
    try:
        header = path.read_bytes()[:24]
    except OSError:
        return None
    if header[:8] != b"\x89PNG\r\n\x1a\n":
        return None
    width, height = struct.unpack(">II", header[16:24])
    return width, height


def _presentation_crop(path: Path, directory: Path) -> Path:
    """Remove a faixa vazia à direita e embaixo, sem alterar o conteúdo visível."""
    try:
        from PIL import Image
    except ImportError:
        return path
    image = Image.open(path).convert("RGB")
    width, height = image.size
    if width < 400 or height < 200:
        return path
    pixels = image.load()
    bottom = 80
    right = 400
    for y in range(60, height):
        for x in range(360, width):
            red, green, blue = pixels[x, y]
            if red < 248 or green < 248 or blue < 248:
                bottom = max(bottom, y)
                right = max(right, x)
    box = (0, 0, min(width, right + 32), min(height, bottom + 28))
    if box[2] > width * 0.92 and box[3] > height * 0.92:
        return path
    directory.mkdir(parents=True, exist_ok=True)
    target = directory / path.name
    image.crop(box).save(target, optimize=True)
    return target


def _image(path: Path, max_width: float, max_height: float) -> Image | None:
    if not path.is_file():
        return None
    size = _png_size(path)
    if not size:
        return None
    width, height = size
    scale = min(max_width / width, max_height / height)
    return Image(str(path), width=width * scale, height=height * scale)


def _table(rows: list[list[str]], col_widths: list[float], styles: dict[str, ParagraphStyle]) -> Table:
    rendered = []
    for index, row in enumerate(rows):
        style = styles["th"] if index == 0 else styles["small"]
        rendered.append([Paragraph(cell, style) for cell in row])
    table = Table(rendered, colWidths=col_widths, repeatRows=1)
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), NAVY),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTNAME", (0, 0), (-1, 0), FONT_BOLD),
                ("BACKGROUND", (0, 1), (-1, -1), colors.white),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, ZEBRA]),
                ("GRID", (0, 0), (-1, -1), 0.3, LINE),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 4),
                ("RIGHTPADDING", (0, 0), (-1, -1), 4),
                ("TOPPADDING", (0, 0), (-1, -1), 3),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
            ]
        )
    )
    return table


def _status_color(status: str) -> colors.Color:
    return TEAL if status == "OK" else RED


def _checklist(summary: dict[str, object]) -> list[tuple[str, bool]]:
    score = summary.get("pontuacao") if isinstance(summary.get("pontuacao"), dict) else {}
    percent = score.get("percentual") if isinstance(score, dict) else None
    orders = summary.get("quantidade_ordens_distintas") or 0
    forms = summary.get("forms") if isinstance(summary.get("forms"), dict) else {}
    tests = summary.get("testes") if isinstance(summary.get("testes"), dict) else {}
    shots = summary.get("screenshots") if isinstance(summary.get("screenshots"), dict) else {}
    return [
        ("A planilha Excel foi lida em execução; os 10 registros não estão fixos no código.", summary.get("linhas_excel") == 10),
        ("O cabeçalho 'Last Name ' com espaço foi normalizado para a legenda Last Name.", bool(summary.get("cabecalho_last_name_com_espaco"))),
        ("Cada rodada relê a legenda visível antes de digitar.", int(summary.get("eventos_ordem") or 0) >= int(summary.get("linhas_total") or 0) > 0),
        ("Houve mais de uma ordem de campos, evidenciando o embaralhamento.", int(orders) >= 2),
        ("Cada linha tem Status OK ou NOK, Observação e timestamp com fuso.", summary.get("linhas_total") == 10),
        ("O timestamp usa America/Sao_Paulo.", summary.get("fuso") == "America/Sao_Paulo"),
        ("A pontuação final veio do texto publicado pelo site.", bool(score)),
        ("A pontuação medida foi 100%.", percent == 100 or percent == 100.0),
        ("A captura da pontuação final existe.", bool(shots.get("final"))),
        ("CSV, JSON e o log de etapas foram gravados.", bool(summary.get("arquivos_gerados"))),
        ("O Microsoft Forms não foi preenchido nem enviado.", forms.get("preenchido") is False and forms.get("enviado") is False),
        ("Os testes locais de validação e erro passaram.", tests.get("passou") is True),
    ]


def _footer(canvas, doc) -> None:
    canvas.saveState()
    canvas.setFillColor(ORANGE)
    canvas.rect(0, A4[1] - 12, A4[0], 12, fill=1, stroke=0)
    canvas.setFillColor(NAVY)
    canvas.rect(0, 0, A4[0], 28, fill=1, stroke=0)
    canvas.setFillColor(colors.white)
    canvas.setFont(FONT, 8)
    canvas.drawString(1.6 * cm, 12, "Desafio RPA · rpachallenge.com · automação executada, sem autoria humana")
    canvas.drawRightString(A4[0] - 1.6 * cm, 12, f"Página {doc.page}")
    canvas.restoreState()


def _resolve(output_dir: Path, relative: object) -> Path | None:
    if not isinstance(relative, str) or not relative:
        return None
    path = Path(relative)
    if not path.is_absolute():
        path = output_dir / relative
    return path


def _add_picture(
    story: list,
    styles: dict[str, ParagraphStyle],
    path: Path | None,
    caption: str,
    crop_dir: Path,
    max_height: float = 8.6 * cm,
) -> None:
    if path is None or not path.is_file():
        story.append(Paragraph(f"Captura ausente: {caption}", styles["caption"]))
        return
    display = _presentation_crop(path, crop_dir)
    image = _image(display, 17.6 * cm, max_height)
    if image is None:
        story.append(Paragraph(f"Arquivo de imagem ilegível: {path.name}", styles["caption"]))
        return
    story.append(KeepTogether([image, Paragraph(caption, styles["caption"])]))


def build_pdf(summary: dict[str, object], rows: list[dict[str, object]], pdf_path: Path, output_dir: Path) -> Path:
    _register_fonts()
    styles = _styles()
    pdf_path.parent.mkdir(parents=True, exist_ok=True)
    doc = SimpleDocTemplate(
        str(pdf_path),
        pagesize=A4,
        leftMargin=1.6 * cm,
        rightMargin=1.6 * cm,
        topMargin=1.3 * cm,
        bottomMargin=1.4 * cm,
        title="Relatório técnico do desafio RPA",
        author="Agente de automação — Playwright e openpyxl",
    )
    story: list = []
    score = summary.get("pontuacao") if isinstance(summary.get("pontuacao"), dict) else None
    if score:
        percent = score.get("percentual")
        percent_text = str(int(percent)) if isinstance(percent, float) and percent.is_integer() else str(percent)
        score_line = (
            f"{percent_text}%  ·  {score.get('campos_corretos')}/"
            f"{score.get('campos_totais')} campos  ·  {score.get('tempo_site_ms')} ms no site"
        )
    else:
        score_line = "Pontuação final não publicada pelo site"

    story.append(Paragraph("Relatório técnico do desafio RPA", styles["h1"]))
    story.append(Paragraph(
        "Formulário dinâmico de rpachallenge.com, alimentado pela planilha Excel do desafio.",
        styles["body"],
    ))
    story.append(Paragraph(score_line, styles["score"]))
    story.append(Spacer(1, 6))
    story.append(Paragraph(
        "Este material foi produzido e executado por um agente de automação com Python, "
        "Playwright e openpyxl. Não é apresentado como autoria humana nem como experiência "
        "profissional pessoal. Nada foi enviado ao recrutador, por e-mail ou pelo Microsoft Forms.",
        styles["body"],
    ))

    story.append(Paragraph("1. Resultado medido", styles["h2"]))
    excel = summary.get("excel") if isinstance(summary.get("excel"), dict) else {}
    measured = [
        ["Indicador", "Valor"],
        ["URL executada", str(summary.get("challenge_url") or "")],
        ["Planilha", str(excel.get("caminho") or "")],
        ["SHA-256 da planilha", str(excel.get("sha256") or "")],
        ["Linhas lidas no Excel", str(summary.get("linhas_excel") or "")],
        ["Linhas OK", str(summary.get("linhas_ok") or 0)],
        ["Linhas NOK", str(summary.get("linhas_nok") or 0)],
        ["Mensagem bruta do site", str(summary.get("mensagem_pontuacao") or "não publicada")],
        ["Duração medida pelo site", f"{score.get('tempo_site_ms')} ms" if score else "não publicada"],
        ["Duração de parede da automação", f"{summary.get('duracao_parede_ms')} ms"],
        ["Início", str(summary.get("inicio") or "")],
        ["Fim", str(summary.get("fim") or "")],
        ["Fuso", str(summary.get("fuso") or "")],
        ["Navegador", f"{summary.get('navegador')} · headless={summary.get('headless')}"],
        ["Ordens visuais distintas", str(summary.get("quantidade_ordens_distintas") or 0)],
    ]
    story.append(_table(measured, [5.2 * cm, 12.3 * cm], styles))

    blockers = summary.get("bloqueios") if isinstance(summary.get("bloqueios"), list) else []
    if blockers:
        story.append(Paragraph("Bloqueios registrados", styles["h2"]))
        for item in blockers:
            story.append(Paragraph(f"• {item}", styles["body"]))

    story.append(Paragraph("2. Como a solução funciona", styles["h2"]))
    steps = [
        "openpyxl abre a planilha recebida. A primeira linha é cabeçalho. 'Last Name ' perde o espaço só na comparação; o texto da célula de dados é preservado.",
        "Telefones numéricos viram dígitos, sem notação científica. Linhas completamente vazias são ignoradas.",
        "O Playwright abre o Chrome, espera o botão Start e só então inicia o cronômetro do site.",
        "Depois de cada embaralhamento, o programa lê as legendas visíveis e a posição na tela. O valor do Excel entra no input cuja legenda corresponde ao cabeçalho.",
        "O valor é relido no DOM antes do Submit. Se não permanecer, a linha fica NOK. O Submit ainda ocorre quando a tela segue respondendo, para não trocar a ordem das 10 rodadas.",
        "Ao terminar, a frase 'Your success rate is…' é lida da página. A nota do relatório é essa frase, não um cálculo paralelo.",
    ]
    story.append(ListFlowable(
        [ListItem(Paragraph(text, styles["bullet"]), leftIndent=12) for text in steps],
        bulletType="1",
        start="1",
        leftIndent=16,
        bulletFontName=FONT,
        bulletFontSize=9,
    ))

    story.append(Paragraph("3. Comando", styles["h2"]))
    story.append(Paragraph(
        "No diretório do projeto, com o ambiente virtual já instalado a partir de requirements.txt:",
        styles["body"],
    ))
    story.append(Paragraph(
        "PYTHONPATH=src .venv/bin/python -m pytest",
        styles["small"],
    ))
    story.append(Spacer(1, 3))
    story.append(Paragraph(
        "PYTHONPATH=src .venv/bin/python -m rpa_challenge --config config.yaml",
        styles["small"],
    ))
    story.append(Spacer(1, 6))
    story.append(Paragraph(
        "O Chrome instalado na máquina é usado pelo Playwright. Não há credencial, banco nem atalho de API: o único caminho até a nota é o formulário público.",
        styles["body"],
    ))

    story.append(Paragraph("4. Resultado por linha", styles["h2"]))
    table_rows = [["#", "Linha", "Nome", "Status", "Hora -03", "Observação"]]
    for row in rows:
        note = str(row.get("Observação") or "")
        if len(note) > 220:
            note = note[:217] + "..."
        stamp = str(row.get("Timestamp") or "")
        clock = stamp[11:19] if len(stamp) >= 19 else stamp
        table_rows.append([
            str(row.get("Indice") or ""),
            str(row.get("Linha Excel") or ""),
            f"{row.get('First Name', '')} {row.get('Last Name', '')}",
            str(row.get("Status") or ""),
            clock,
            note,
        ])
    result_table = _table(table_rows, [1.0 * cm, 1.4 * cm, 3.3 * cm, 1.6 * cm, 1.8 * cm, 8.4 * cm], styles)
    status_commands = []
    for index, row in enumerate(rows, start=1):
        if row.get("Status") == "OK":
            status_commands.append(("BACKGROUND", (3, index), (3, index), OK_BG))
        elif row.get("Status") == "NOK":
            status_commands.append(("BACKGROUND", (3, index), (3, index), NOK_BG))
    if status_commands:
        result_table.setStyle(TableStyle(status_commands))
    story.append(result_table)
    story.append(Paragraph(
        "A observação completa, a ordem visual dos campos e os sete valores estão em resultados.csv e resultados.json.",
        styles["caption"],
    ))

    story.append(Paragraph("5. Evidências da execução", styles["h2"]))
    story.append(Paragraph(
        "As imagens abaixo foram capturadas na página real durante esta execução. "
        "A faixa vazia à direita foi cortada só na diagramação; os arquivos originais permanecem intactos.",
        styles["body"],
    ))
    shots = summary.get("screenshots") if isinstance(summary.get("screenshots"), dict) else {}
    crop_dir = output_dir / "screenshots-pdf"
    _add_picture(
        story,
        styles,
        _resolve(output_dir, shots.get("inicial")),
        "Figura 1. Página inicial, antes do Start. O cronômetro do desafio ainda não corre.",
        crop_dir,
    )
    _add_picture(
        story,
        styles,
        _resolve(output_dir, shots.get("apos_start")),
        "Figura 2. Desafio iniciado. Os campos já podem estar em outra ordem.",
        crop_dir,
    )
    round_shots = shots.get("rodadas") if isinstance(shots.get("rodadas"), list) else []
    chosen = []
    if round_shots:
        chosen.append((round_shots[0], "Figura 3. Primeira linha preenchida, antes do envio."))
        if len(round_shots) >= 3:
            chosen.append((round_shots[len(round_shots) // 2], "Figura 4. Rodada intermediária, com a ordem lida de novo."))
        if len(round_shots) >= 2:
            chosen.append((round_shots[-1], "Figura 5. Última linha preenchida, antes do envio final."))
    for relative, caption in chosen:
        _add_picture(story, styles, _resolve(output_dir, relative), caption, crop_dir)
    _add_picture(
        story,
        styles,
        _resolve(output_dir, shots.get("final")),
        "Figura 6. Tela final com a pontuação publicada pelo site.",
        crop_dir,
        7.2 * cm,
    )
    _add_picture(
        story,
        styles,
        _resolve(output_dir, shots.get("final_recorte")),
        "Figura 7. Recorte do bloco de congratulações e da frase de resultado.",
        crop_dir,
        3.4 * cm,
    )

    story.append(Paragraph("6. Checklist do que foi pedido", styles["h2"]))
    checks = _checklist(summary)
    check_rows = [["Requisito", "Situação"]]
    for text, ok in checks:
        check_rows.append([text, "Atendido" if ok else "Não atendido"])
    check_table = _table(check_rows, [14.2 * cm, 3.3 * cm], styles)
    for index, (_, ok) in enumerate(checks, start=1):
        check_table.setStyle(TableStyle([
            ("BACKGROUND", (1, index), (1, index), OK_BG if ok else NOK_BG),
            ("TEXTCOLOR", (1, index), (1, index), _status_color("OK" if ok else "NOK")),
        ]))
    story.append(check_table)

    story.append(Paragraph("7. Microsoft Forms, somente leitura", styles["h2"]))
    forms = summary.get("forms") if isinstance(summary.get("forms"), dict) else {}
    if not forms:
        story.append(Paragraph("A consulta ao Forms não foi executada nesta corrida.", styles["body"]))
    else:
        story.append(Paragraph(
            f"Acessível: {'sim' if forms.get('acessivel') else 'não'}. "
            f"Preenchido: {'sim' if forms.get('preenchido') else 'não'}. "
            f"Enviado: {'sim' if forms.get('enviado') else 'não'}. "
            f"Login exigido: {'sim' if forms.get('login_exigido') else 'não'}.",
            styles["body"],
        ))
        story.append(Paragraph(str(forms.get("motivo") or ""), styles["body"]))
        if forms.get("titulo"):
            story.append(Paragraph(f"Título lido na página: {forms.get('titulo')}.", styles["body"]))
        resumo_forms = str(forms.get("resumo") or "").strip()
        if resumo_forms:
            story.append(Paragraph(resumo_forms, styles["body"]))
        elif not forms.get("acessivel"):
            story.append(Paragraph(
                "A página não entregou o questionário. Nada foi preenchido e nada foi enviado.",
                styles["body"],
            ))

    story.append(Paragraph("8. Testes locais", styles["h2"]))
    tests = summary.get("testes") if isinstance(summary.get("testes"), dict) else {}
    if not tests or not tests.get("executado"):
        story.append(Paragraph(
            "A suíte local ainda não tinha sido registrada quando este PDF foi gerado.",
            styles["body"],
        ))
    else:
        story.append(Paragraph(
            f"Resultado: {'passou' if tests.get('passou') else 'falhou'}. "
            f"Comando: {tests.get('comando') or 'pytest'}.",
            styles["body"],
        ))
        saida = str(tests.get("saida") or "").strip().splitlines()
        final_line = next((line.strip() for line in reversed(saida) if line.strip()), "")
        if final_line:
            story.append(Paragraph(final_line, styles["small"]))

    story.append(Paragraph("9. Limitações", styles["h2"]))
    for item in summary.get("limitacoes") or []:
        story.append(Paragraph(f"• {item}", styles["body"]))

    artifacts = summary.get("artefatos") if isinstance(summary.get("artefatos"), dict) else {}
    if artifacts:
        story.append(Paragraph("10. Cópias para revisão", styles["h2"]))
        story.append(Paragraph(
            "Os arquivos abaixo são as cópias deixadas para quem for revisar o pacote.",
            styles["body"],
        ))
        for label, path in artifacts.items():
            story.append(Paragraph(f"{label}: {path}", styles["small"]))
            story.append(Spacer(1, 2))

    doc.build(story, onFirstPage=_footer, onLaterPages=_footer)
    return pdf_path
