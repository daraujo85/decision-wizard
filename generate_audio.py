#!/usr/bin/env python3
"""Gera um audio narrado (TTS via HTTP) por decisao do spec: contexto, pedido
de ajuda, opcoes A/B/C... e cobranca da resposta.

Opcional: so roda pra quem tem a API de TTS configurada. Sem audio o wizard
funciona igual (botao "Ouvir" simplesmente nao aparece).

Uso:
  generate_audio.py spec.json <workdir> [--voice pt-BR-ThalitaNeural] [--force]
  generate_audio.py --selfcheck

Liga por decisao com "audio": true, ou pra todas com "audio": true no topo do
spec ("audio": false numa decisao desliga so ela). Grava os mp3 em
<workdir>/audio/<hash>.mp3 e escreve no proprio spec, em cada decisao:
  "audioFiles": {"question": "<hash>"}
Depois rode o generate_wizard.py normalmente.

mp3 (nao ogg): ogg/opus nao toca em Safari/iPhone antigos. Nome = hash de
voz+texto: texto igual nao gera de novo, texto editado gera arquivo novo.

API: POST $TTS_BASE_URL/tts (form: text, voice, convert_to_ogg=false) que
devolve JSON {"audio_format": "mp3", "audio_base64": "..."}. URL lida do
ambiente ou de $TTS_ENV_FILE (default ~/.config/decision-wizard/tts.env).
"""
import base64
import hashlib
import json
import os
import sys
import urllib.parse
import urllib.request

DEFAULT_VOICE = "pt-BR-ThalitaNeural"
ENV_FILE = os.path.expanduser(os.environ.get("TTS_ENV_FILE", "~/.config/decision-wizard/tts.env"))
MAX_CHARS = 1800  # roteiro inteiro (contexto + todas as opcoes); alem disso passa de ~2 min

def tts_base_url():
    url = os.environ.get("TTS_BASE_URL")
    if url:
        return url.rstrip("/")
    if os.path.isfile(ENV_FILE):
        with open(ENV_FILE, encoding="utf-8") as file:
            for line in file:
                line = line.strip()
                if line.startswith("export "):
                    line = line[len("export "):]
                if line.startswith("TTS_BASE_URL="):
                    return line.split("=", 1)[1].strip().strip("\"'").rstrip("/")
    sys.exit(f"TTS_BASE_URL nao definido (ambiente ou {ENV_FILE})")

def synthesize(base_url, text, voice):
    data = urllib.parse.urlencode({"text": text, "voice": voice, "convert_to_ogg": "false"}).encode()
    # UA proprio: o Cloudflare na frente da API barra o "Python-urllib" padrao (403)
    req = urllib.request.Request(base_url + "/tts", data=data, method="POST",
                                 headers={"User-Agent": "decision-wizard/1.0"})
    with urllib.request.urlopen(req, timeout=120) as resp:
        body = json.load(resp)
    if body.get("audio_format") != "mp3":
        raise RuntimeError(f"formato inesperado: {body.get('audio_format')}")
    return base64.b64decode(body["audio_base64"])

def audio_name(voice, text):
    return hashlib.sha256(f"{voice}\n{text}".encode()).hexdigest()[:20]

def _join(*parts):
    out = []
    for part in parts:
        part = (part or "").strip()
        if part:
            out.append(part if part[-1] in ".?!:" else part + ".")
    return " ".join(out)

def _letters(n):
    letters = [chr(65 + i) for i in range(n)]
    if n <= 1:
        return "".join(letters)
    return ", ".join(letters[:-1]) + " ou " + letters[-1]

def script_for(dec):
    """Roteiro unico da decisao, em linguagem simples (campo 'tech' nunca e falado):
    contexto -> diagrama -> pedido de ajuda -> opcoes A, B, C... -> cobranca da resposta."""
    options = list(dec.get("options", {}).items())
    plains = dec.get("optionPlain") or {}
    badges = dec.get("optionBadge") or {}
    letters = _letters(len(options))
    parts = [dec.get("question"), dec.get("plain")]
    if dec.get("diagram"):
        parts.append("Se quiser ver em que ponto do processo isso entra, clique no diagrama logo abaixo para abrir em tela cheia")
    parts.append(f"Agora preciso da sua ajuda. Preste atenção nas opções e me diga qual é a mais indicada para esse caso: {letters}")
    for i, (key, title) in enumerate(options):
        badge = f", marcada como {badges[key]}" if badges.get(key) else ""
        parts.append(f"Opção {chr(65 + i)}{badge}: {title}")
        parts.append(plains.get(key))
    parts.append(f"Então, qual você escolhe: {letters}? Se nenhuma servir, escreva sua própria resposta no campo Escrever minha resposta")
    return _join(*parts)

def wants_audio(spec, dec):
    return dec.get("audio", spec.get("audio", False)) is True

def build(spec, workdir, voice, synth, force=False):
    """Gera os mp3 faltantes e grava audioFiles no spec. Retorna (gerados, reaproveitados)."""
    audio_dir = os.path.join(workdir, "audio")
    os.makedirs(audio_dir, exist_ok=True)
    made = reused = 0

    def ensure(text):
        nonlocal made, reused
        if len(text) > MAX_CHARS:
            print(f"aviso: texto com {len(text)} chars, audio vai ficar longo - encurte 'plain'", file=sys.stderr)
        name = audio_name(voice, text)
        path = os.path.join(audio_dir, name + ".mp3")
        if os.path.isfile(path) and not force:
            reused += 1
            return name
        tmp = path + ".tmp"
        with open(tmp, "wb") as file:
            file.write(synth(text, voice))
        os.replace(tmp, path)
        made += 1
        return name

    for sec in spec.get("sections", []):
        for dec in sec.get("decisions", []):
            if not wants_audio(spec, dec):
                dec.pop("audioFiles", None)
                continue
            dec["audioFiles"] = {"question": ensure(script_for(dec))}
    return made, reused

def selfcheck():
    import tempfile
    calls = []
    fake = lambda text, voice: calls.append(text) or b"ID3fake"
    spec = {"audio": True, "sections": [{"key": "S1", "decisions": [
        {"tag": "D1", "question": "Cliente espera na tela?", "plain": "Hoje espera 20s",
         "options": {"a": "Sim", "b": "Não"}, "optionPlain": {"b": "Avisa depois"}, "tech": "fila sqs"},
        {"tag": "D2", "question": "Outra?", "audio": False, "options": {"a": "X"}},
    ]}]}
    with tempfile.TemporaryDirectory() as tmp:
        made, reused = build(spec, tmp, DEFAULT_VOICE, fake)
        d1, d2 = spec["sections"][0]["decisions"]
        assert made == 1 and reused == 0, "um audio so por decisao"
        assert "audioFiles" not in d2, "audio:false na decisao desliga"
        text = calls[0]
        order = ["Cliente espera na tela?", "Hoje espera 20s.", "preciso da sua ajuda", "A ou B.",
                 "Opção A: Sim.", "Opção B: Não. Avisa depois.", "qual você escolhe: A ou B?", "Escrever minha resposta"]
        pos = [text.find(s) for s in order]
        assert -1 not in pos and pos == sorted(pos), f"roteiro fora de ordem: {text}"
        assert "diagrama" not in text, "sem diagrama, nao cita diagrama"
        assert "sqs" not in text, "campo tech nao e falado"
        name = d1["audioFiles"]["question"]
        assert name.isalnum() and os.path.isfile(os.path.join(tmp, "audio", name + ".mp3"))

        made, reused = build(spec, tmp, DEFAULT_VOICE, fake)
        assert made == 0 and reused == 1, "texto igual reaproveita arquivo"
        d1["question"] = "Mudou?"
        made, _ = build(spec, tmp, DEFAULT_VOICE, fake)
        assert made == 1, "texto editado gera audio novo"

        d1.update(diagram="fluxo", optionBadge={"b": "recomendado"}, options={"a": "Sim", "b": "Não", "c": "Talvez"})
        build(spec, tmp, DEFAULT_VOICE, fake)
        assert "clique no diagrama" in calls[-1]
        assert "A, B ou C" in calls[-1] and "Opção B, marcada como recomendado: Não" in calls[-1]
    print("ok")

def main():
    if "--selfcheck" in sys.argv:
        selfcheck()
        return
    args = sys.argv[1:]
    voice = DEFAULT_VOICE
    force = "--force" in args
    args = [a for a in args if a != "--force"]
    if "--voice" in args:
        i = args.index("--voice")
        voice = args[i + 1]
        del args[i:i + 2]
    if len(args) != 2:
        print(__doc__, file=sys.stderr)
        sys.exit(1)
    spec_path, workdir = args
    with open(spec_path, encoding="utf-8") as file:
        spec = json.load(file)
    base_url = tts_base_url()
    made, reused = build(spec, workdir, voice, lambda text, v: synthesize(base_url, text, v), force)
    tmp = spec_path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as file:
        json.dump(spec, file, ensure_ascii=False, indent=2)
    os.replace(tmp, spec_path)
    print(f"ok: {made} audio(s) gerado(s), {reused} reaproveitado(s) em {os.path.join(workdir, 'audio')}")

if __name__ == "__main__":
    main()
