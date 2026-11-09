"""Consulta somente leitura do Microsoft Forms. Não preenche e não envia."""

from __future__ import annotations

from pathlib import Path

from playwright.sync_api import Page


def inspect_forms(page: Page, url: str, screenshot_path: Path, timeout_ms: int) -> dict[str, object]:
    """Abre o formulário público e lê o texto visível.

    Não digita, não marca opções, não clica em enviar e não faz login.
    """
    result: dict[str, object] = {
        "consultado": True,
        "url": url,
        "acessivel": False,
        "preenchido": False,
        "enviado": False,
        "login_exigido": False,
        "titulo": "",
        "url_final": "",
        "trecho": "",
        "motivo": "",
        "screenshot": "",
    }
    try:
        page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
        page.wait_for_timeout(5000)
        # Algumas telas trocam "Loading…" pelo conteúdo sem uma navegação nova.
        try:
            page.wait_for_function(
                """() => {
                    const text = (document.body && document.body.innerText || '').trim();
                    return text.length > 80 && !/^loading…?$/i.test(text);
                }""",
                timeout=15000,
            )
        except Exception:
            pass
        title = page.title()
        final_url = page.url
        text = page.inner_text("body")
        compact = " ".join(text.split())
        lowered = compact.casefold()
        login_markers = (
            "sign in",
            "entrar",
            "faça login",
            "faca login",
            "pick an account",
            "escolha uma conta",
        )
        login_required = any(marker in lowered for marker in login_markers) and (
            "form" not in lowered or "senha" in lowered or "password" in lowered
        )
        still_loading = compact.casefold() in {"loading…", "loading...", "loading"} or len(compact) < 40
        accessible = not login_required and not still_loading and len(compact) > 80
        screenshot_path.parent.mkdir(parents=True, exist_ok=True)
        page.screenshot(path=str(screenshot_path), full_page=True)
        result.update(
            {
                "acessivel": accessible,
                "login_exigido": login_required,
                "titulo": title,
                "url_final": final_url,
                "trecho": compact[:1200],
                "motivo": (
                    "A página pediu autenticação. Nenhum login foi feito."
                    if login_required
                    else "A página permaneceu em carregamento ou sem conteúdo legível."
                    if not accessible
                    else "Conteúdo visível lido sem preencher campos."
                ),
                "screenshot": str(screenshot_path),
            }
        )
    except Exception as exc:
        result["motivo"] = f"Consulta somente leitura falhou: {exc}"
    return result
