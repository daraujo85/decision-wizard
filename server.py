#!/usr/bin/env python3
"""Servidor standalone do decision-wizard: login por senha, docs protegidos, respostas via POST.

Sem dependencia externa (so stdlib). Configuracao via env:
  ARTIFACT_PASSWORD_SHA256   hash sha256 da senha (obrigatorio p/ liberar acesso)
  ARTIFACT_SESSION_SECRET    segredo p/ assinar cookie de sessao (default: gerado ao subir)
  PORT                       porta (default 8890)

Nunca grava senha em texto puro em lugar nenhum (HTML/JS/JSON/log) - so o hash.
"""
import hashlib
import html
import hmac
import json
import os
import re
import secrets
import threading
import time
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, quote, urlparse

ROOT = os.path.dirname(os.path.abspath(__file__))
DOCS = os.path.join(ROOT, "docs")
ANSWERS_FILE = os.path.join(ROOT, "answers.json")
QUESTIONS_FILE = os.path.join(ROOT, "questions.json")
QUESTIONS_LOG = os.path.join(ROOT, "questions.log")
FOLLOWUPS_FILE = os.path.join(ROOT, "followups.json")
PRESENCE_FILE = os.path.join(ROOT, "presence.json")
PRESENCE_TTL = 45  # segundos sem heartbeat = saiu da pagina
PRESENCE = {}      # {doc: {ip: {"last": ts, "country": .., "lat": .., "lon": .., "acc": ..}}}
PRESENCE_LOCK = threading.Lock()
FAVICON_SVG = (b'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64">'
               b'<rect width="64" height="64" fill="#201e1d"/><rect width="10" height="64" fill="#ec3013"/>'
               b'<path d="M26 32h10M36 32l10-14M36 32l10 14" stroke="#bab6b6" stroke-width="4" fill="none"/>'
               b'<rect x="18" y="26" width="12" height="12" fill="#f3f2f2"/><circle cx="48" cy="18" r="6" fill="#f3f2f2"/>'
               b'<circle cx="48" cy="46" r="6" fill="#ec3013"/></svg>')
PASSWORD_HASH = os.environ.get("ARTIFACT_PASSWORD_SHA256", "")
SESSION_SECRET = os.environ.get("ARTIFACT_SESSION_SECRET", secrets.token_hex(32)).encode()
SESSION_TTL = 60 * 60 * 12
LOGIN_HTML = """<!doctype html><html lang="pt-br"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>{og}
<link rel="icon" href="/favicon.svg" type="image/svg+xml">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Archivo:wght@400;700;800&display=swap" rel="stylesheet">
<style>
*{{box-sizing:border-box}}
body{{margin:0;min-height:100vh;display:grid;place-items:center;background:#f3f2f2;color:#201e1d;font:15px/1.55 Archivo,system-ui,sans-serif;border-top:6px solid #ec3013}}
main{{width:min(440px,calc(100% - 32px));background:#eae9e9;border:1px solid #bab6b6;padding:32px}}
.kicker{{font-size:12px;letter-spacing:.08em;text-transform:uppercase;color:#605d5d;margin:0 0 8px}}
h1{{font-size:26px;font-weight:800;line-height:1.2;margin:0 0 8px}}
p{{margin:0 0 20px;color:#605d5d}}
label{{display:block;font-weight:700}}
input,button{{display:block;width:100%;font:inherit;margin-top:8px;padding:12px;border-radius:0}}
input{{border:2px solid #bab6b6;background:#f3f2f2;color:inherit}}
input:focus{{outline:none;border-color:#201e1d}}
button{{margin-top:16px;border:2px solid #ec3013;background:#ec3013;color:#fff;font-weight:700;cursor:pointer}}
button:hover{{background:#e15b47;border-color:#e15b47}}
.error{{color:#ec3013;font-weight:700;margin:0 0 12px}}
</style></head><body><main>
<div class="kicker">Decisões para você revisar</div>
<h1>{heading}</h1>
<p>{subtitle}</p>
{error}<form method="post" action="{action}"><label>Senha<input name="password" type="password" autocomplete="current-password" autofocus required></label><button>Entrar</button></form>
</main></body></html>"""


def _load_json(path):
    # ausente, vazio ou corrompido vira {}: excecao aqui derruba a resposta e o tunnel devolve 502
    try:
        with open(path, encoding="utf-8") as file:
            data = json.load(file)
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def load_answers():
    return _load_json(ANSWERS_FILE)


def save_answers(data):
    tmp = ANSWERS_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as file:
        json.dump(data, file, ensure_ascii=False, indent=2)
    os.replace(tmp, ANSWERS_FILE)


def load_questions():
    return _load_json(QUESTIONS_FILE)


def save_questions(data):
    tmp = QUESTIONS_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as file:
        json.dump(data, file, ensure_ascii=False, indent=2)
    os.replace(tmp, QUESTIONS_FILE)


def load_followups():
    return _load_json(FOLLOWUPS_FILE)


def save_followups(data):
    tmp = FOLLOWUPS_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as file:
        json.dump(data, file, ensure_ascii=False, indent=2)
    os.replace(tmp, FOLLOWUPS_FILE)


def save_presence(data):
    tmp = PRESENCE_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as file:
        json.dump(data, file, ensure_ascii=False, indent=2)
    os.replace(tmp, PRESENCE_FILE)


def session_token():
    expires = str(int(time.time()) + SESSION_TTL)
    signature = hmac.new(SESSION_SECRET, expires.encode(), hashlib.sha256).hexdigest()
    return f"{expires}.{signature}"


def valid_session(value):
    if not value or "." not in value:
        return False
    expires, signature = value.split(".", 1)
    if not expires.isdigit() or int(expires) < time.time():
        return False
    expected = hmac.new(SESSION_SECRET, expires.encode(), hashlib.sha256).hexdigest()
    return hmac.compare_digest(signature, expected)


class _Discard:
    """wfile do HEAD depois dos headers: descarta o corpo."""
    def write(self, data):
        return len(data)
    def flush(self):
        pass

class Handler(BaseHTTPRequestHandler):
    def _body(self, body, status=200, content_type="text/plain; charset=utf-8"):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _json(self, obj, status=200):
        self._body(json.dumps(obj, ensure_ascii=False).encode(), status, "application/json; charset=utf-8")

    def _authenticated(self):
        cookie = SimpleCookie(self.headers.get("Cookie"))
        session = cookie.get("artifact_session")
        return bool(session and valid_session(session.value))

    def _client_ip(self):
        # atras do cloudflared o socket e sempre 127.0.0.1; o IP real vem no header da Cloudflare
        ip = self.headers.get("CF-Connecting-IP") or (self.headers.get("X-Forwarded-For") or "").split(",")[0]
        return ip.strip()[:64] or self.client_address[0]

    def _presence(self, doc, body):
        """Heartbeat do visitante: marca o IP como ativo e devolve quantos IPs estao na pagina agora."""
        now = time.time()
        entry = {"last": now, "country": (self.headers.get("CF-IPCountry") or "")[:4]}
        geo = body.get("geo")
        if isinstance(geo, dict) and all(isinstance(geo.get(k), (int, float)) for k in ("lat", "lon")):
            entry.update(lat=round(float(geo["lat"]), 4), lon=round(float(geo["lon"]), 4),
                         acc=round(float(geo.get("acc") or 0)))
        with PRESENCE_LOCK:
            visitors = PRESENCE.setdefault(doc, {})
            prev = visitors.get(self._client_ip(), {})
            for key in ("lat", "lon", "acc"):  # coordenada enviada uma vez fica valendo
                if key not in entry and key in prev:
                    entry[key] = prev[key]
            entry["first"] = prev.get("first", now)
            visitors[self._client_ip()] = entry
            for ip in [ip for ip, v in visitors.items() if now - v["last"] > PRESENCE_TTL]:
                del visitors[ip]
            me = self._client_ip()
            # pro mapa: so posicao/pais, nunca o IP (quem tem a senha nao precisa ver IP dos outros)
            people = [{"id": hmac.new(SESSION_SECRET, ip.encode(), hashlib.sha256).hexdigest()[:10], "me": ip == me, "country": v.get("country", ""), "lat": v.get("lat"), "lon": v.get("lon"),
                       "acc": v.get("acc"), "since": int(now - v["first"])} for ip, v in visitors.items()]
            snapshot = {d: {ip: dict(v, last=time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(v["last"])),
                                     first=time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(v["first"])))
                            for ip, v in vs.items()} for d, vs in PRESENCE.items()}
            save_presence(snapshot)
        return people

    def _evidence(self, doc, body=None):
        """Quem respondeu, de onde: IP, pais e ultima coordenada que o navegador mandou (se autorizou)."""
        ip = self._client_ip()
        with PRESENCE_LOCK:
            seen = dict(PRESENCE.get(doc, {}).get(ip, {}))
        ev = {"ip": ip, "country": (self.headers.get("CF-IPCountry") or seen.get("country") or "")[:4],
              "ua": (self.headers.get("User-Agent") or "")[:300]}
        # coordenada do proprio envio vale mais: mesmo IP (wifi da empresa) pode ser varias pessoas
        geo = (body or {}).get("geo")
        if isinstance(geo, dict) and all(isinstance(geo.get(k), (int, float)) for k in ("lat", "lon")):
            ev.update(lat=round(float(geo["lat"]), 4), lon=round(float(geo["lon"]), 4), acc=round(float(geo.get("acc") or 0)))
        elif "lat" in seen:
            ev.update(lat=seen["lat"], lon=seen["lon"], acc=seen.get("acc"), geo_from="presenca")
        return ev

    def _og_meta(self, doc):
        """Titulo/subtitulo/imagem do preview (gerados pelo og_image.py); None se o doc nao tem."""
        if not doc or not doc.replace("-", "").isalnum():
            return None
        try:
            with open(os.path.join(DOCS, doc + ".og.json"), encoding="utf-8") as file:
                meta = json.load(file)
        except (OSError, ValueError):
            return None
        return {"title": str(meta.get("title", "")), "subtitle": str(meta.get("subtitle", "")), "doc": doc}

    def _login(self, error=False, next_path="/"):
        doc = (parse_qs(urlparse(next_path).query).get("doc") or [None])[0]
        meta = self._og_meta(doc)
        og = ""
        if meta:
            # preview do link (WhatsApp/Slack): so titulo/subtitulo/imagem, nada do conteudo das decisoes
            host = self.headers.get("Host", "")
            proto = self.headers.get("X-Forwarded-Proto", "https")
            base = f"{proto}://{host}" if host else ""
            esc = lambda v: html.escape(v, quote=True)
            img = esc(f"{base}/og/{doc}.png")
            og = (f'\n<meta property="og:type" content="website">'
                  f'\n<meta property="og:title" content="{esc(meta["title"])}">'
                  f'\n<meta property="og:description" content="{esc(meta["subtitle"])}">'
                  f'\n<meta property="og:image" content="{img}">'
                  f'\n<meta property="og:image:width" content="1200"><meta property="og:image:height" content="630">'
                  f'\n<meta property="og:image:secure_url" content="{img}"><meta property="og:image:type" content="image/png">'
                  f'\n<meta property="og:site_name" content="Decisões para revisar">'
                  f'\n<meta property="og:url" content="{esc(base + next_path)}">'
                  f'\n<meta name="twitter:card" content="summary_large_image">'
                  f'\n<meta name="description" content="{esc(meta["subtitle"])}">')
        heading = meta["title"] if meta else "Acesso restrito"
        subtitle = (meta["subtitle"] + ". " if meta else "") + "Informe a senha que você recebeu para abrir."
        body = LOGIN_HTML.format(
            title=html.escape(heading), og=og, heading=html.escape(heading), subtitle=html.escape(subtitle),
            error='<p class="error">Senha inválida. Confira e tente de novo.</p>' if error else "",
            action=html.escape("/login?next=" + quote(next_path, safe=""), quote=True),
        )
        self._body(body.encode(), 200, "text/html; charset=utf-8")

    def _safe_next(self, value):
        return value if value.startswith("/") and not value.startswith("//") else "/"

    def _file(self, path, content_type):
        if not os.path.isfile(path):
            self._body(b"not found", 404)
            return
        with open(path, "rb") as file:
            data = file.read()
        # Safari/iPhone so toca <audio> se o servidor responder Range com 206
        rng = re.match(r"bytes=(\d*)-(\d*)$", self.headers.get("Range", "").strip())
        if not rng or not data or rng.group(1) == rng.group(2) == "":
            self._body(data, 200, content_type)
            return
        size = len(data)
        if rng.group(1):
            start = int(rng.group(1))
            end = min(int(rng.group(2)), size - 1) if rng.group(2) else size - 1
        else:
            start, end = max(size - int(rng.group(2)), 0), size - 1
        if start >= size or start > end:
            self.send_response(416)
            self.send_header("Content-Range", f"bytes */{size}")
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
        chunk = data[start:end + 1]
        self.send_response(206)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
        self.send_header("Content-Length", str(len(chunk)))
        self.send_header("Accept-Ranges", "bytes")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(chunk)

    def _require_auth(self, redirect=False):
        if not PASSWORD_HASH:
            self._body(b"access unavailable", 503)
            return False
        if not self._authenticated():
            if redirect:
                self.send_response(303)
                self.send_header("Location", "/login?next=" + quote(self.path, safe=""))
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
            else:
                self._body(b"unauthorized", 401)
            return False
        return True

    def do_GET(self):
        parsed = urlparse(self.path)
        query = parse_qs(parsed.query)
        doc = (query.get("doc") or [None])[0]
        if parsed.path == "/login":
            self._login(next_path=self._safe_next((query.get("next") or ["/"])[0]))
            return
        if parsed.path in ("/favicon.svg", "/favicon.ico"):
            self.send_response(200)
            self.send_header("Content-Type", "image/svg+xml")
            self.send_header("Content-Length", str(len(FAVICON_SVG)))
            self.send_header("Cache-Control", "public, max-age=86400")
            self.end_headers()
            self.wfile.write(FAVICON_SVG)
            return
        if parsed.path.startswith("/og/") and parsed.path.endswith(".png"):
            # imagem do preview e publica (crawler do WhatsApp nao loga); so existe se og_image.py rodou
            name = parsed.path[len("/og/"):-len(".png")]
            if name and name.replace("-", "").isalnum():
                self._file(os.path.join(DOCS, name + ".og.png"), "image/png")
            else:
                self._body(b"not found", 404)
            return
        if parsed.path == "/" and not self._authenticated() and PASSWORD_HASH:
            # 200 direto (sem redirect): crawler de preview le as meta tags na primeira resposta
            self._login(next_path=self._safe_next(self.path))
            return
        if not self._require_auth(redirect=parsed.path == "/"):
            return
        if parsed.path == "/answers.js":
            self._file(os.path.join(ROOT, "answers.js"), "application/javascript; charset=utf-8")
        elif parsed.path == "/wizard.css":
            self._file(os.path.join(ROOT, "wizard.css"), "text/css; charset=utf-8")
        elif parsed.path == "/wizard-core.js":
            self._file(os.path.join(ROOT, "wizard-core.js"), "application/javascript; charset=utf-8")
        elif parsed.path == "/api/answers":
            answers = load_answers().get(doc, {}) if doc else {}
            self._json({k: {f: v for f, v in a.items() if f != "evidence"} for k, a in answers.items()})
        elif parsed.path.startswith("/api/question/"):
            qid = parsed.path[len("/api/question/"):]
            record = load_questions().get(qid)
            self._json({"answer": record.get("answer") if record else None})
        elif parsed.path == "/api/followups":
            data = load_followups()
            out = [dict(rec, id=fid, turns=[{f: v for f, v in t.items() if f != "evidence"} for t in rec.get("turns", [])])
                   for fid, rec in data.items() if doc and rec.get("doc") == doc]
            self._json(out)
        elif parsed.path.startswith("/diagrams/") and parsed.path.endswith(".html"):
            # diagramas archify embutidos nas decisoes; nome restrito evita path traversal
            name = parsed.path[len("/diagrams/"):-len(".html")]
            if name and name.replace("-", "").replace("_", "").isalnum():
                self._file(os.path.join(ROOT, "diagrams", name + ".html"), "text/html; charset=utf-8")
            else:
                self._body(b"not found", 404)
        elif parsed.path.startswith("/audio/") and parsed.path.endswith(".mp3"):
            # audios TTS gerados pelo generate_audio.py; nome = hash alfanumerico
            name = parsed.path[len("/audio/"):-len(".mp3")]
            if name and name.isalnum():
                self._file(os.path.join(ROOT, "audio", name + ".mp3"), "audio/mpeg")
            else:
                self._body(b"not found", 404)
        elif parsed.path == "/" and doc and doc.replace("-", "").isalnum():
            self._file(os.path.join(DOCS, doc + ".html"), "text/html; charset=utf-8")
        elif parsed.path == "/":
            # link sem ?doc= (ou login que voltou pra "/"): abre o unico doc ou lista os disponiveis
            names = sorted(f[:-5] for f in os.listdir(DOCS) if f.endswith(".html")) if os.path.isdir(DOCS) else []
            if len(names) == 1:
                self.send_response(303)
                self.send_header("Location", "/?doc=" + quote(names[0]))
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
            else:
                items = "".join(f'<li><a href="/?doc={quote(n)}">{html.escape(n)}</a></li>' for n in names) or "<li>Nenhum documento publicado.</li>"
                self._body(f'<!doctype html><meta charset="utf-8"><title>Documentos</title><ul>{items}</ul>'.encode(), 200, "text/html; charset=utf-8")
        else:
            self._body(b"not found", 404)

    def do_HEAD(self):
        # WhatsApp/Facebook checam o link com HEAD antes do GET; sem isto o preview nao aparece (501)
        self._head_only = True
        real = self.wfile
        try:
            self.do_GET()
        finally:
            self.wfile = real

    def end_headers(self):
        super().end_headers()
        if getattr(self, "_head_only", False):
            self.wfile = _Discard()  # HEAD: headers (com Content-Length real) saem, corpo nao

    def do_POST(self):
        parsed = urlparse(self.path)
        query = parse_qs(parsed.query)
        doc = (query.get("doc") or [None])[0]
        length = int(self.headers.get("Content-Length", 0))
        raw = self.rfile.read(length)
        if parsed.path == "/login":
            next_path = self._safe_next((query.get("next") or ["/"])[0])
            password = parse_qs(raw.decode()).get("password", [""])[0]
            password_hash = hashlib.sha256(password.encode()).hexdigest()
            if not PASSWORD_HASH or not hmac.compare_digest(password_hash, PASSWORD_HASH):
                self._login(error=True, next_path=next_path)
                return
            self.send_response(303)
            self.send_header("Location", next_path)
            self.send_header("Set-Cookie", f"artifact_session={session_token()}; HttpOnly; Secure; SameSite=Strict; Path=/; Max-Age={SESSION_TTL}")
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            return
        if not self._require_auth():
            return
        if not doc or not doc.replace("-", "").isalnum():
            self._body(b"not found", 404)
            return
        try:
            body = json.loads(raw or b"{}")
        except json.JSONDecodeError:
            self._json({"error": "json invalido"}, 400)
            return
        if parsed.path == "/api/answers":
            decision, choice = body.get("decision"), body.get("choice")
            text = body.get("text")
            # qualquer chave curta alfanumerica: decisao pode ter opcao d, e...
            valid_choice = choice is None or (isinstance(choice, str) and 0 < len(choice) <= 20 and choice.isalnum())
            if not isinstance(decision, str) or not decision or not valid_choice:
                self._json({"error": "decision ou choice invalido"}, 400)
                return
            if choice == "other" and (not isinstance(text, str) or not text.strip()):
                self._json({"error": "text obrigatorio para choice=other"}, 400)
                return
            data = load_answers()
            if choice is None:
                data.get(doc, {}).pop(decision, None)
            else:
                entry = {"choice": choice, "ts": time.strftime("%Y-%m-%dT%H:%M:%S"), "evidence": self._evidence(doc, body)}
                if choice == "other":
                    entry["text"] = text.strip()[:4000]
                data.setdefault(doc, {})[decision] = entry
            save_answers(data)
            self._json({"ok": True})
        elif parsed.path == "/api/presence":
            people = self._presence(doc, body)
            self._json({"online": len(people), "people": people})
        elif parsed.path == "/api/question":
            decision, text = body.get("decision"), body.get("text")
            if not isinstance(decision, str) or not decision or not isinstance(text, str) or not text.strip():
                self._json({"error": "decision ou text invalido"}, 400)
                return
            qid = secrets.token_hex(6)
            questions = load_questions()
            questions[qid] = {"doc": doc, "decision": decision, "text": text.strip()[:2000], "answer": None,
                              "ts": time.strftime("%Y-%m-%dT%H:%M:%S"), "evidence": self._evidence(doc, body)}
            save_questions(questions)
            with open(QUESTIONS_LOG, "a", encoding="utf-8") as file:
                file.write(f"{qid}\t{doc}\t{decision}\t{text.strip()[:2000]}\n")
            self._json({"id": qid})
        elif parsed.path == "/api/followups/reply":
            fid, text = body.get("id"), body.get("text")
            if not isinstance(fid, str) or not fid or not isinstance(text, str) or not text.strip():
                self._json({"error": "id ou text invalido"}, 400)
                return
            data = load_followups()
            record = data.get(fid)
            if not record or record.get("doc") != doc:
                self._json({"error": "followup nao encontrado"}, 404)
                return
            record.setdefault("turns", []).append({
                "role": "user", "text": text.strip()[:4000], "ts": time.strftime("%Y-%m-%dT%H:%M:%S"),
                "evidence": self._evidence(doc, body),
            })
            save_followups(data)
            self._json({"ok": True})
        else:
            self._body(b"not found", 404)

    def log_message(self, fmt, *args):
        pass


if __name__ == "__main__":
    ThreadingHTTPServer(("0.0.0.0", int(os.environ.get("PORT", 8890))), Handler).serve_forever()
