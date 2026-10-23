#!/usr/bin/env python3
"""Agente abre/le duvidas pro USUARIO sobre uma resposta ja dada (followups.json).

Contrario do answer_questions.py: la o usuario pergunta e o agente responde;
aqui o agente (Claude, apos ler o codigo e nao achar o que a resposta livre
descreveu) pergunta e o usuario responde no wizard, na propria decisao.
Suporta varias rodadas: cada followup e uma thread de turnos. O ultimo turno
decide quem esta com a bola - se for do agente, o wizard mostra a badge
"Esperando voce".

Uso:
  agent_followup.py ask <followups.json> <doc> <decision> "pergunta" ["about"]
  agent_followup.py list <followups.json> [doc] [--waiting-user]
  agent_followup.py --selfcheck
"""
import json
import os
import secrets
import sys
import time


def load(path):
    if not os.path.exists(path):
        return {}
    with open(path, encoding="utf-8") as file:
        return json.load(file)


def save(path, data):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as file:
        json.dump(data, file, ensure_ascii=False, indent=2)
    os.replace(tmp, path)


def cmd_ask(path, doc, decision, text, about=""):
    data = load(path)
    fid = secrets.token_hex(6)
    data[fid] = {
        "doc": doc, "decision": decision, "about": about,
        "turns": [{"role": "agent", "text": text, "ts": time.strftime("%Y-%m-%dT%H:%M:%S")}],
    }
    save(path, data)
    print(fid)


def waiting_user(record):
    turns = record.get("turns") or []
    return bool(turns) and turns[-1].get("role") == "agent"


def cmd_list(path, doc=None, waiting_user_only=False):
    data = load(path)
    if doc is not None:
        data = {fid: f for fid, f in data.items() if f.get("doc") == doc}
    if waiting_user_only:
        data = {fid: f for fid, f in data.items() if waiting_user(f)}
    print(json.dumps(data, ensure_ascii=False, indent=2))


def selfcheck():
    import tempfile
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, "followups.json")
        cmd_ask(path, "docA", "s1-D1", "pergunta 1", "Sua resposta em texto livre")
        data = load(path)
        assert len(data) == 1
        fid = next(iter(data))
        assert data[fid]["turns"][0]["role"] == "agent"
        assert data[fid]["about"] == "Sua resposta em texto livre"
        assert waiting_user(data[fid])

        data[fid]["turns"].append({"role": "user", "text": "resposta", "ts": time.strftime("%Y-%m-%dT%H:%M:%S")})
        save(path, data)
        assert not waiting_user(load(path)[fid])

        cmd_ask(path, "docB", "s2-D3", "outra pergunta")
        assert len(load(path)) == 2
    print("ok")


def main():
    if "--selfcheck" in sys.argv:
        selfcheck()
        return
    if len(sys.argv) < 3:
        print(__doc__, file=sys.stderr)
        sys.exit(1)
    action, path = sys.argv[1], sys.argv[2]
    if action == "ask":
        if len(sys.argv) < 6:
            print(__doc__, file=sys.stderr)
            sys.exit(1)
        about = sys.argv[6] if len(sys.argv) > 6 else ""
        cmd_ask(path, sys.argv[3], sys.argv[4], sys.argv[5], about)
    elif action == "list":
        rest = sys.argv[3:]
        waiting_only = "--waiting-user" in rest
        rest = [a for a in rest if a != "--waiting-user"]
        cmd_list(path, rest[0] if rest else None, waiting_only)
    else:
        print(__doc__, file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
