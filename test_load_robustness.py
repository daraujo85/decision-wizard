#!/usr/bin/env python3
"""Regressao: load_answers/load_questions/load_followups nao podem quebrar
quando os arquivos estao ausentes, vazios ou corrompidos.

Bug original (28/09/2026): o `json.load` direto em arquivo vazio jogava
JSONDecodeError, o BaseHTTPRequestHandler deixava de responder, o tunnel
do cloudflared via EOF, Cloudflare devolvia 502, e o answers.js do wizard
estourava "SyntaxError: Unexpected token '<'" no JSON.parse.

Cobre os 3 cenarios: arquivo ausente, arquivo zero-byte, arquivo com
conteudo nao-JSON. Sem fazer chamadas de rede — importa o server.py
diretamente.
"""
import json
import os
import sys
import tempfile

# skill dir
SKILL_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SKILL_DIR)
import server  # noqa: E402

failures = []


def case(name, before, expected):
    tmpdir = tempfile.mkdtemp()
    if before == "missing":
        pass
    elif before == "empty":
        open(os.path.join(tmpdir, "answers.json"), "w").close()
    elif before == "garbage":
        with open(os.path.join(tmpdir, "answers.json"), "w") as f:
            f.write("not json{{")
    else:
        raise ValueError(before)
    # Redireciona os paths do server pra tmpdir.
    saved = server.ANSWERS_FILE, server.QUESTIONS_FILE, server.FOLLOWUPS_FILE
    server.ANSWERS_FILE = os.path.join(tmpdir, "answers.json")
    server.QUESTIONS_FILE = os.path.join(tmpdir, "questions.json")
    server.FOLLOWUPS_FILE = os.path.join(tmpdir, "followups.json")
    try:
        a = server.load_answers()
        q = server.load_questions()
        f = server.load_followups()
    finally:
        server.ANSWERS_FILE, server.QUESTIONS_FILE, server.FOLLOWUPS_FILE = saved
    for label, got in (("load_answers", a), ("load_questions", q), ("load_followups", f)):
        if got != expected:
            failures.append(f"{name}/{label}: esperado {expected!r}, obtido {got!r}")


for before in ("missing", "empty", "garbage"):
    case(before, before, {})

if failures:
    print("FAIL:")
    for f in failures:
        print(" -", f)
    sys.exit(1)
print("ok")
