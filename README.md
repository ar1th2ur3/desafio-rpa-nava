# Desafio RPA — formulário dinâmico

Automação do desafio público [rpachallenge.com](https://rpachallenge.com/). O programa lê a planilha Excel, preenche o formulário web cujos campos trocam de lugar a cada envio e grava o resultado de cada linha.

Esta solução foi escrita e executada por um agente de automação (Python, Playwright, openpyxl e reportlab). Não é autoria humana e não descreve experiência profissional pessoal. Ela não envia e-mail, não publica o resultado e não preenche o Microsoft Forms do recrutamento.

## O que entra e o que sai

A planilha oficial tem 10 linhas e 7 colunas. O cabeçalho da segunda coluna vem com espaço no fim (`Last Name `). O telefone está gravado como número. Nada disso é copiado para o código: `openpyxl` lê o arquivo indicado em `config.yaml`.

Para cada linha o resultado traz:

- `Status`: `OK` ou `NOK`
- `Observação`: o que foi conferido ou o erro
- `Timestamp`: data e hora com fuso `America/Sao_Paulo`

Também ficam a ordem visual dos campos, o log de etapas e as capturas da execução, inclusive a tela da pontuação publicada pelo site.

## Requisitos

- Python 3.11 ou superior
- Google Chrome, usado pelo Playwright
- Rede até `https://rpachallenge.com/` na hora da execução real

## Instalação

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

O Chrome já instalado na máquina dispensa o download do Chromium. Se esse canal não abrir, o programa tenta o Chromium do Playwright (`python -m playwright install chromium`).

## Testes

```bash
PYTHONPATH=src .venv/bin/python -m pytest
```

A suíte cobre a leitura do Excel (incluindo telefone numérico, cabeçalho com espaço, linha vazia e planilha inválida), o texto de pontuação, o CSV e um formulário local que embaralha os campos. Os testes de erro verificam legenda desconhecida, valor que não permanece no input, linha extra depois do fim do desafio e página inacessível. Esses testes não inventam a nota do site público.

## Execução

```bash
PYTHONPATH=src .venv/bin/python -m rpa_challenge --config config.yaml
```

Para ver o navegador: acrescente `--headed`. Para não consultar o Forms: `--skip-forms`.

A consulta ao Microsoft Forms, quando ligada, só abre a página e lê o texto. Não há digitação, login nem clique em enviar.

## Arquivos gerados

Em `output/execucao/`:

| Arquivo | Conteúdo |
| --- | --- |
| `resultados.csv` | uma linha por registro, com Status, Observação e Timestamp |
| `resultados.json` | o mesmo conteúdo em JSON |
| `passos.jsonl` | log de etapas com o mesmo fuso |
| `resumo.json` | nota lida do site, durações, bloqueios e caminhos das capturas |
| `screenshots/pontuacao-final.png` | tela final real |
| `relatorio-desafio-rpa.pdf` | relatório em português com as capturas |

Para remontar só o PDF, depois de ajustar o resumo:

```bash
PYTHONPATH=src .venv/bin/python -m rpa_challenge --config config.yaml --report-only
```

## Como a nota é obtida

1. A planilha é lida e validada antes de abrir o navegador.
2. O botão Start é clicado uma vez. O cronômetro do site começa nesse clique.
3. Em cada rodada as legendas são lidas de novo. O valor da coluna entra no campo de mesmo nome, independente da posição.
4. O valor é relido no input. Se não conferir, a linha fica `NOK`.
5. O Submit é acionado na página. Depois do décimo envio, o site mostra a frase `Your success rate is …`. Essa frase é a nota do relatório.

Não existe chamada escondida para gravar uma porcentagem. Se o site não mostrar a frase, o resumo deixa a pontuação vazia.

## Limitações

- O site em inglês compara os envios com a lista interna dele. A automação envia o Excel como está.
- O desafio pontua 10 envios. Outra quantidade de linhas fica registrada e não produz o mesmo encerramento.
- As capturas feitas antes de cada envio entram no tempo medido pelo site. A porcentagem é o acerto dos campos.
- Se o Forms pedir login, as perguntas ficam inacessíveis. A página não é preenchida.
- A execução depende do site público e do Chrome local.

## Configuração

`config.yaml` aponta a URL, a planilha, o diretório de saída e o fuso. Não há segredo nem identidade de usuário.
