#!/usr/bin/env python3
"""Aplica a paleta do wizard (wizard.css) num diagrama HTML gerado pelo archify.

Uso:
  theme_diagram.py <diagrams/arquivo.html> [...]   # edita no lugar; rodar de novo so substitui
  theme_diagram.py --selfcheck

O archify desenha tudo com variaveis CSS (--bg, --text, --backend-stroke...).
Aqui so redefinimos essas variaveis no tema claro, sem tocar no SVG. O wizard
abre o iframe com ?theme=light, entao o tema escuro do archify fica intacto
(so aparece se a pessoa trocar na barra do diagrama em tela cheia).
"""
import re
import sys

MARK_START = "<!-- decision-wizard-theme -->"
MARK_END = "<!-- /decision-wizard-theme -->"

# html[data-theme][data-theme="light"] (0,2,1) ganha de [data-preset=x][data-theme=light] (0,2,0)
THEME_CSS = """
html[data-theme][data-theme="light"] {
  --bg:#f3f2f2; --grid:#eae9e9; --canvas-dot:#dcdada;
  --text:#201e1d; --text-muted:#605d5d; --text-faint:#605d5d; --text-dim:#9b9797;
  --panel:#f8f4f4; --panel-border:#bab6b6; --mask:#f3f2f2;
  --lane-fill:rgba(234,233,233,.55); --lane-stroke:#bab6b6;
  --arrow:#7d7979; --arrow-emphasis:#ec3013;
  --backend-fill:rgba(32,30,29,.06); --backend-stroke:#201e1d;
  --security-fill:#fbe2dc; --security-stroke:#ec3013;
  --external-fill:#f8f4f4; --external-stroke:#605d5d;
  --database-fill:rgba(122,92,62,.12); --database-stroke:#7a5c3e;
  --frontend-fill:rgba(61,90,108,.10); --frontend-stroke:#3d5a6c;
  --cloud-fill:rgba(176,122,30,.12); --cloud-stroke:#9a6a12;
  --messagebus-fill:rgba(225,91,71,.12); --messagebus-stroke:#e15b47;
  --toolbar-bg:rgba(248,244,244,.94); --toolbar-border:#bab6b6; --toolbar-menu-bg:#f8f4f4;
  --toolbar-text:#201e1d; --toolbar-hover:#eae9e9; --guide-accent:#ec3013;
  --lens-color:#ec3013; --reach-color:#ec3013; --reach-fill:rgba(236,48,19,.10);
}
html[data-theme="light"] body, html[data-theme="light"] svg text { font-family: Archivo, system-ui, sans-serif; }
""".strip()

FONT_LINK = '<link href="https://fonts.googleapis.com/css2?family=Archivo:wght@400;700;800&display=swap" rel="stylesheet">'

def apply_theme(html_text):
    block = f"{MARK_START}\n{FONT_LINK}\n<style id=\"decision-wizard-theme\">\n{THEME_CSS}\n</style>\n{MARK_END}\n"
    html_text = re.sub(re.escape(MARK_START) + r".*?" + re.escape(MARK_END) + r"\n?", "", html_text, flags=re.S)
    idx = html_text.find("</head>")
    if idx == -1:
        raise ValueError("HTML sem </head> - nao parece saida do archify")
    return html_text[:idx] + block + html_text[idx:]

def selfcheck():
    src = "<html><head><title>x</title></head><body></body></html>"
    once = apply_theme(src)
    assert once.index(MARK_START) < once.index("</head>"), "tema entra antes de </head>, depois do CSS do archify"
    assert "--backend-stroke:#201e1d" in once
    assert apply_theme(once) == once, "rodar de novo nao duplica"
    try:
        apply_theme("<p>sem head</p>")
        raise AssertionError("deveria falhar sem </head>")
    except ValueError:
        pass
    print("ok")

def main():
    if "--selfcheck" in sys.argv:
        selfcheck()
        return
    if len(sys.argv) < 2:
        print(__doc__, file=sys.stderr)
        sys.exit(1)
    for path in sys.argv[1:]:
        with open(path, encoding="utf-8") as file:
            text = file.read()
        with open(path, "w", encoding="utf-8") as file:
            file.write(apply_theme(text))
        print(f"ok: tema do wizard aplicado em {path}")

if __name__ == "__main__":
    main()
