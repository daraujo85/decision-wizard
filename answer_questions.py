#!/usr/bin/env python3
"""Lista/responde perguntas feitas via askWidget no wizard (questions.json), sem humano sincrono.

Uso:
  answer_questions.py list <questions.json> [doc]      # so pendentes (answer=null)
  answer_questions.py answer <questions.json> <qid> "resposta"
"""
import json
import os
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


def cmd_list(path, doc=None):
    data = load(path)
    pending = {
        qid: q
        for qid, q in data.items()
        if q.get("answer") is None and (doc is None or q.get("doc") == doc)
    }
    print(json.dumps(pending, ensure_ascii=False, indent=2))


def cmd_answer(path, qid, answer):
    data = load(path)
    if qid not in data:
        print(f"pergunta {qid} nao encontrada", file=sys.stderr)
        sys.exit(1)
    data[qid]["answer"] = answer
    data[qid]["answered_ts"] = time.strftime("%Y-%m-%dT%H:%M:%S")
    save(path, data)
    print("ok")


def main():
    if len(sys.argv) < 3:
        print(__doc__, file=sys.stderr)
        sys.exit(1)
    action, path = sys.argv[1], sys.argv[2]
    if action == "list":
        cmd_list(path, sys.argv[3] if len(sys.argv) > 3 else None)
    elif action == "answer":
        if len(sys.argv) < 5:
            print(__doc__, file=sys.stderr)
            sys.exit(1)
        cmd_answer(path, sys.argv[3], sys.argv[4])
    else:
        print(__doc__, file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
