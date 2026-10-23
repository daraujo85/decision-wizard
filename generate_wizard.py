#!/usr/bin/env python3
"""Gera o HTML do wizard de decisao a partir de um spec JSON.

Uso:
  generate_wizard.py spec.json > docs/meu-doc.html
  cat spec.json | generate_wizard.py > docs/meu-doc.html
  generate_wizard.py --selfcheck

Schema do spec (campos com ? sao opcionais - ausencia esconde a parte
correspondente na UI, sem placeholder forcado):
{
  "title": "...",
  "sections": [{
    "id": "s1", "key": "S1", "title": "...",
    "decisions": [{
      "tag": "D1", "question": "...",
      "context?": "texto abaixo da pergunta",
      "plain?": "explicacao 'em palavras simples' da decisao",
      "tech?": "detalhe tecnico, fica recolhido (so quem quiser abre)",
      "diagram?": "nome do HTML archify em <workdir>/diagrams/ (sem .html)",
      "diagramCaption?": "1 frase dizendo o que olhar no diagrama",
      "options": {"a": "...", "b": "...", "c": "..."},
      "optionPlain?": {"a": "explicacao da opcao A"},
      "optionBadge?": {"a": "ja implementado"}
    }]
  }]
}

A opcao "escrever minha resposta" e implicita, adicionada em runtime pelo
client (answers.js) - nao entra no spec.
"""
import html
import json
import os
import sys

MERMAID_CDN = "https://cdn.jsdelivr.net/npm/mermaid@10.9.1/dist/mermaid.min.js"


# Termos que costumam travar leitor de negocio. Nao bloqueia, so avisa no stderr
# pra quem gerou o spec mover o jargao pro campo "tech" ou traduzir.
# Comparacao sem acento e palavra inteira (evita "pr" casar "pra").
JARGON = (
    "endpoint", "api", "payload", "schema", "migration", "migracao", "deploy",
    "refactor", "refatorar", "cache", "queue", "webhook", "middleware", "backend",
    "frontend", "json", "sql", "query", "worker", "cron", "lambda", "sqs",
    "kafka", "rabbitmq", "redis", "microservico", "microsservico", "rollback",
    "feature flag", "idempotente", "idempotencia", "assincrono", "assincrona",
    "tunnel", "token", "orm", "pr", "branch", "merge", "commit", "job",
)

def _fold(text):
    import unicodedata
    return "".join(c for c in unicodedata.normalize("NFD", text.lower()) if unicodedata.category(c) != "Mn")

def lint(spec, diagrams_dir=None):
    """Retorna avisos de jargao em pergunta/opcoes (campos que todo leitor ve)."""
    import re
    warnings = []
    for sec in spec.get("sections", []):
        for dec in sec.get("decisions", []):
            where = f"{sec.get('key', '?')}-{dec.get('tag', '?')}"
            visible = [("pergunta", dec.get("question", ""))]
            visible += [(f"opcao {k}", v) for k, v in dec.get("options", {}).items()]
            for label, text in visible:
                low = _fold(text)
                hits = [t for t in JARGON if re.search(r"\b" + re.escape(t) + r"\b", low)]
                if hits:
                    warnings.append(f"{where} {label}: termo tecnico ({', '.join(hits)}) -> traduza ou mova pro campo 'tech'")
            if not dec.get("plain"):
                warnings.append(f"{where}: sem 'plain' (explicacao em palavras simples)")
            diagram = dec.get("diagram")
            if diagram:
                if not diagram.replace("-", "").replace("_", "").isalnum():
                    warnings.append(f"{where}: 'diagram' invalido ({diagram}) - use so letras, numeros, - e _ (sem .html)")
                elif diagrams_dir and not os.path.isfile(os.path.join(diagrams_dir, diagram + ".html")):
                    warnings.append(f"{where}: diagrama {diagram}.html nao existe em {diagrams_dir}")
    return warnings

def render(spec):
    title = html.escape(spec["title"], quote=True)
    spec_json = json.dumps(spec, ensure_ascii=False)
    spec_json = spec_json.replace("</", "<\\/")  # nao deixa </script> escapar do bloco inline
    return (
        "<!doctype html>\n"
        '<html lang="pt-br"><head><meta charset="utf-8">\n'
        '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
        f"<title>{title}</title>\n"
        '<link rel="icon" href="/favicon.svg" type="image/svg+xml">\n'
        '<link rel="preconnect" href="https://fonts.googleapis.com">\n'
        '<link href="https://fonts.googleapis.com/css2?family=Archivo:wght@400;700;800&display=swap" rel="stylesheet">\n'
        '<link rel="stylesheet" href="/wizard.css?v=18">\n'
        "</head><body>\n"
        '<div id="wizard-root"></div>\n'
        f"<script>const SPEC = {spec_json};</script>\n"
        f'<script src="{MERMAID_CDN}"></script>\n'
        '<script src="/wizard-core.js?v=18"></script>\n'
        '<script src="/answers.js?v=18"></script>\n'
        "</body></html>\n"
    )


def _assert_render(spec, has_optional):
    out = render(spec)
    assert '<div id="wizard-root">' in out
    assert '"question": "Pergunta?"' in out
    assert "/wizard.css" in out and "/wizard-core.js" in out and "/answers.js" in out
    assert MERMAID_CDN in out
    if has_optional:
        assert "Contexto da decisao" in out
        assert "Explicacao simples" in out
        assert "Explicacao A" in out
        assert "novo" in out
    else:
        assert '"context"' not in out and '"plain"' not in out
    return out


def selfcheck():
    spec_min = {
        "title": "Teste",
        "sections": [{"id": "s1", "key": "S1", "title": "Secao 1", "decisions": [
            {"tag": "D1", "question": "Pergunta?", "options": {"a": "Opcao A", "b": "Opcao B", "c": "Opcao C"}}
        ]}],
    }
    _assert_render(spec_min, has_optional=False)

    spec_full = {
        "title": "Teste completo",
        "sections": [{"id": "s1", "key": "S1", "title": "Secao 1", "decisions": [
            {"tag": "D1", "question": "Pergunta?", "context": "Contexto da decisao",
             "plain": "Explicacao simples", "options": {"a": "Opcao A", "b": "Opcao B", "c": "Opcao C"},
             "optionPlain": {"a": "Explicacao A"}, "optionBadge": {"b": "novo"}}
        ]}],
    }
    _assert_render(spec_full, has_optional=True)

    jargon = {"sections": [{"key": "S1", "decisions": [
        {"tag": "D1", "question": "Qual fila usar no backend?", "options": {"a": "SQS", "b": "Mais rapido pra o projeto do cliente"}},
        {"tag": "D2", "question": "Processar de forma assíncrona?", "plain": "x", "options": {"a": "Sim"}}
    ]}]}
    warns = lint(jargon)
    assert any("backend" in w and "pergunta" in w for w in warns)
    assert any("opcao a" in w and "sqs" in w for w in warns)
    assert not any("opcao b" in w for w in warns)
    assert any("S1-D2" in w and "assincrona" in w for w in warns), "acento nao pode esconder jargao"
    assert any("sem 'plain'" in w for w in warns)
    assert not [w for w in lint(spec_full) if "termo tecnico" in w]

    import tempfile
    with tempfile.TemporaryDirectory() as tmp:
        open(os.path.join(tmp, "fluxo-ok.html"), "w").close()
        dspec = {"sections": [{"key": "S1", "decisions": [
            {"tag": "D1", "question": "Q", "plain": "p", "options": {}, "diagram": "fluxo-ok"},
            {"tag": "D2", "question": "Q", "plain": "p", "options": {}, "diagram": "falta"},
            {"tag": "D3", "question": "Q", "plain": "p", "options": {}, "diagram": "../x.html"},
        ]}]}
        dwarns = lint(dspec, tmp)
        assert not any("S1-D1" in w for w in dwarns)
        assert any("S1-D2" in w and "nao existe" in w for w in dwarns)
        assert any("S1-D3" in w and "invalido" in w for w in dwarns)
    print("ok")


def main():
    if "--selfcheck" in sys.argv:
        selfcheck()
        return
    args = sys.argv[1:]
    diagrams_dir = None
    if "--diagrams-dir" in args:
        i = args.index("--diagrams-dir")
        diagrams_dir = args[i + 1]
        del args[i:i + 2]
    if args:
        with open(args[0], encoding="utf-8") as file:
            spec = json.load(file)
    else:
        spec = json.load(sys.stdin)
    for warning in lint(spec, diagrams_dir):
        print(f"aviso: {warning}", file=sys.stderr)
    sys.stdout.write(render(spec))


if __name__ == "__main__":
    main()
