#!/usr/bin/env python3
"""Gera a imagem de preview (thumb do link no WhatsApp/Slack/Teams) de um wizard.

Uso:
  og_image.py spec.json <workdir> <doc> [--subtitle "texto"]
  og_image.py --selfcheck

Grava <workdir>/docs/<doc>.og.png (1200x630) e <doc>.og.json (titulo e
subtitulo). O server.py so mostra preview pra docs que tem esses arquivos:
sem rodar este script, o link sai sem titulo/imagem (nada vaza antes do login).
Nao ponha dado sensivel no titulo: o preview e publico pra quem tiver o link.

Requer Pillow (pip install pillow). Fonte: Archivo se instalada, senao a
sans-serif do sistema.
"""
import json
import os
import sys

W, H = 1200, 630
BG, SURFACE, TEXT, MUTED, BORDER, ACCENT, ACCENT_SOFT = (
    "#f3f2f2", "#eae9e9", "#201e1d", "#605d5d", "#bab6b6", "#ec3013", "#fbe2dc")

FONT_CANDIDATES = {
    "bold": [("~/Library/Fonts/Archivo-ExtraBold.ttf", 0), ("~/Library/Fonts/Archivo-Bold.ttf", 0),
             ("/System/Library/Fonts/HelveticaNeue.ttc", 1), ("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 0)],
    "regular": [("~/Library/Fonts/Archivo-Regular.ttf", 0), ("/System/Library/Fonts/HelveticaNeue.ttc", 0),
                ("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 0)],
}

def font(kind, size):
    from PIL import ImageFont
    for path, index in FONT_CANDIDATES[kind]:
        path = os.path.expanduser(path)
        if os.path.isfile(path):
            return ImageFont.truetype(path, size, index=index)
    return ImageFont.load_default(size)

def wrap(draw, text, fnt, width, max_lines):
    words, lines, line = text.split(), [], ""
    for word in words:
        test = (line + " " + word).strip()
        if draw.textlength(test, font=fnt) <= width:
            line = test
            continue
        if line:
            lines.append(line)
        line = word
    if line:
        lines.append(line)
    if len(lines) > max_lines:
        lines = lines[:max_lines]
        while draw.textlength(lines[-1] + "…", font=fnt) > width and " " in lines[-1]:
            lines[-1] = lines[-1].rsplit(" ", 1)[0]
        lines[-1] += "…"
    return lines

def summary(spec):
    decisions = [d for s in spec.get("sections", []) for d in s.get("decisions", [])]
    n, topics = len(decisions), len(spec.get("sections", []))
    minutes = max(1, round(n * 1.5))
    sub = f"{n} {'decisão' if n == 1 else 'decisões'} · {topics} {'assunto' if topics == 1 else 'assuntos'} · ~{minutes} min"
    return decisions, sub

def draw_tree(draw, decisions, x0, y0, x1, y1):
    """Arvore estilizada: raiz -> decisoes -> opcoes, nas cores do wizard."""
    shown = decisions[:4]
    root = (x0, (y0 + y1) // 2)
    draw.rectangle([root[0], root[1] - 22, root[0] + 44, root[1] + 22], fill=TEXT)
    slot = (y1 - y0) / max(len(shown), 1)
    for i, dec in enumerate(shown):
        cy = int(y0 + slot * (i + 0.5))
        dx = x0 + 120
        draw.line([root[0] + 44, root[1], dx, cy], fill=MUTED, width=3)
        draw.rectangle([dx, cy - 18, dx + 90, cy + 18], fill=SURFACE, outline=TEXT, width=3)
        draw.text((dx + 45, cy), dec.get("tag", "")[:4], fill=TEXT, font=font("bold", 20), anchor="mm")
        opts = list(dec.get("options", {}))[:3]
        oslot = min(slot / max(len(opts), 1), 40)
        for j, _ in enumerate(opts):
            oy = int(cy + (j - (len(opts) - 1) / 2) * oslot)
            ox = dx + 150
            draw.line([dx + 90, cy, ox, oy], fill=BORDER, width=2)
            highlight = i == 0 and j == len(opts) - 1
            draw.rectangle([ox, oy - 12, x1, oy + 12], fill=ACCENT if highlight else "#f8f4f4",
                           outline=ACCENT if highlight else BORDER, width=2)
            draw.text((ox + 14, oy), chr(65 + j), fill="#ffffff" if highlight else MUTED, font=font("bold", 16), anchor="lm")

def render(spec, subtitle=None):
    from PIL import Image, ImageDraw
    decisions, auto_sub = summary(spec)
    subtitle = subtitle or auto_sub
    img = Image.new("RGB", (W, H), BG)
    draw = ImageDraw.Draw(img)
    draw.rectangle([0, 0, 18, H], fill=ACCENT)                  # faixa de destaque
    draw.rectangle([0, H - 8, W, H], fill=TEXT)                  # borda de baixo, igual ao header do wizard
    pad = 72
    draw.text((pad, 70), "DECISÕES PARA VOCÊ REVISAR", fill=MUTED, font=font("regular", 24))
    title_font = font("bold", 64)
    lines = wrap(draw, spec.get("title", "Revisão"), title_font, 640, 3)
    y = 118
    for line in lines:
        draw.text((pad, y), line, fill=TEXT, font=title_font)
        y += 78
    sub_font = font("regular", 30)
    y += 14
    for line in wrap(draw, subtitle, sub_font, 640, 2):  # mesma largura do titulo: nao invade a arvore
        draw.text((pad, y), line, fill=TEXT, font=sub_font)
        y += 40
    # botao "Responder" no estilo do wizard
    by = H - 150
    label = "Responder agora"
    bw = draw.textlength(label, font=font("bold", 28)) + 100
    draw.rectangle([pad, by, pad + bw, by + 66], fill=ACCENT)
    draw.text((pad + 28, by + 33), label, fill="#ffffff", font=font("bold", 28), anchor="lm")
    ax = pad + bw - 50  # seta desenhada: nem toda fonte tem o glifo "→"
    draw.line([ax, by + 33, ax + 24, by + 33], fill="#ffffff", width=4)
    draw.polygon([(ax + 28, by + 33), (ax + 16, by + 23), (ax + 16, by + 43)], fill="#ffffff")
    draw.text((pad + bw + 24, by + 33), "acesso com senha", fill=MUTED, font=font("regular", 22), anchor="lm")
    if decisions:
        draw_tree(draw, decisions, 790, 90, W - 60, H - 90)
    return img, subtitle

def build(spec, workdir, doc, subtitle=None):
    if not doc or not doc.replace("-", "").isalnum():
        sys.exit("doc invalido: use so letras, numeros e -")
    docs = os.path.join(workdir, "docs")
    os.makedirs(docs, exist_ok=True)
    img, subtitle = render(spec, subtitle)
    png = os.path.join(docs, doc + ".og.png")
    img.save(png + ".tmp", "PNG", optimize=True)
    os.replace(png + ".tmp", png)
    meta = os.path.join(docs, doc + ".og.json")
    with open(meta + ".tmp", "w", encoding="utf-8") as file:
        json.dump({"title": spec.get("title", ""), "subtitle": subtitle}, file, ensure_ascii=False)
    os.replace(meta + ".tmp", meta)
    return png

def selfcheck():
    import tempfile
    from PIL import Image
    spec = {"title": "Lembrete de boleto pelo WhatsApp com um titulo bem comprido pra testar a quebra de linha", "sections": [
        {"key": "S1", "decisions": [{"tag": "D1", "options": {"a": "x", "b": "y", "c": "z"}},
                                    {"tag": "D2", "options": {"a": "x", "b": "y"}}]}]}
    with tempfile.TemporaryDirectory() as tmp:
        png = build(spec, tmp, "demo")
        with Image.open(png) as img:
            assert img.size == (W, H)
        assert os.path.getsize(png) < 300_000, "WhatsApp ignora imagem grande"
        with open(os.path.join(tmp, "docs", "demo.og.json"), encoding="utf-8") as file:
            meta = json.load(file)
        assert meta["subtitle"] == "2 decisões · 1 assunto · ~3 min"
    print("ok")

def main():
    if "--selfcheck" in sys.argv:
        selfcheck()
        return
    args = sys.argv[1:]
    subtitle = None
    if "--subtitle" in args:
        i = args.index("--subtitle")
        subtitle = args[i + 1]
        del args[i:i + 2]
    if len(args) != 3:
        print(__doc__, file=sys.stderr)
        sys.exit(1)
    spec_path, workdir, doc = args
    with open(spec_path, encoding="utf-8") as file:
        spec = json.load(file)
    print("ok: " + build(spec, workdir, doc, subtitle))

if __name__ == "__main__":
    main()
