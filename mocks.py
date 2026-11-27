"""تلگرام و هوش مصنوعیِ شبیه‌سازی‌شده برای تست (فقط کتابخانه‌ی استاندارد)."""
import json, threading, base64
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

TG = {"updates": [], "files": {}, "log": [], "token": "TESTTOKEN"}
LLM = {"log": [], "fail_keys": {"k1": 429}, "bad_keys": set(), "always_429": False}

def llm_answer(text):
    t = text
    base = dict(relevant=True, tags=["نمونه"], reliability="reported", event_date=None, body=t[:300])
    if "ignore previous" in t:
        return dict(base, category="hacked", title="تلاش تزریق", summary="x", confidence=0.99)
    if "سلام و درود" in t:
        return dict(base, relevant=False, category="notice", title="سلام", summary="", confidence=0.9)
    if "مبهم" in t:
        return dict(base, category="notice", title="مطلب مبهم", summary="نامشخص", confidence=0.4)
    if "فاینمن" in t:
        return dict(base, category="method", title="روش فاینمن", summary="توضیح مبحث برای مبتدی", confidence=0.93, reliability="unverified")
    if "ثبت‌نام" in t:
        return dict(base, category="konkur", title="زمان ثبت‌نام کنکور", summary="ثبت‌نام طبق اعلام سنجش", confidence=0.95, reliability="official", event_date="2027-01-10")
    if "جدول امتحانات" in t:
        return dict(base, category="exam", title="جدول امتحانات", summary="از روی تصویر", confidence=0.9)
    return dict(base, category="resource", title="منبع جدید", summary="یک منبع", confidence=0.85)

class H(BaseHTTPRequestHandler):
    def log_message(self, *a): pass
    def _send(self, obj, code=200, raw=None):
        b = raw if raw is not None else json.dumps(obj, ensure_ascii=False).encode()
        self.send_response(code); self.send_header("Content-Type", "application/json"); self.send_header("Content-Length", str(len(b))); self.end_headers(); self.wfile.write(b)
    def body(self):
        n = int(self.headers.get("Content-Length", 0)); return json.loads(self.rfile.read(n) or b"{}")
    def do_GET(self):
        if self.path.startswith("/file/bot"):
            fid = self.path.split("/", 3)[3]
            if fid in TG["files"]: return self._send(None, raw=TG["files"][fid])
            return self._send({}, 404)
        self._send({}, 404)
    def do_POST(self):
        p = self.path; b = self.body()
        if p.startswith("/bot"):
            m = p.split("/", 2)[2]
            if not p.startswith("/bot" + TG["token"]): return self._send({"ok": False, "error_code": 401, "description": "Unauthorized"}, 401)
            if m == "getUpdates":
                off = b.get("offset", 0)
                return self._send({"ok": True, "result": [u for u in TG["updates"] if u["update_id"] >= off][: b.get("limit", 100)]})
            if m == "getFile":
                fid = b["file_id"]
                if fid not in TG["files"]: return self._send({"ok": False, "error_code": 400, "description": "bad file"}, 400)
                return self._send({"ok": True, "result": {"file_id": fid, "file_path": fid}})
            TG["log"].append((m, b)); return self._send({"ok": True, "result": True})
        if p.endswith("/chat/completions"):
            key = self.headers.get("Authorization", "").replace("Bearer ", "")
            msgs = b["messages"]; u = msgs[-1]["content"]
            has_img = isinstance(u, list)
            text = u if isinstance(u, str) else "\n".join(x.get("text", "") for x in u if x.get("type") == "text")
            LLM["log"].append({"key": key, "model": b["model"], "img": has_img, "text": text, "sys": msgs[0]["content"]})
            if LLM["always_429"] or key in LLM["fail_keys"] and LLM["fail_keys"][key]:
                return self._send({"error": {"message": "quota exceeded"}}, LLM["fail_keys"].get(key, 429))
            if key in LLM["bad_keys"]: return self._send({"error": {"message": "API key not valid"}}, 401)
            ans = llm_answer(text)
            return self._send({"choices": [{"message": {"content": "```json\n" + json.dumps(ans, ensure_ascii=False) + "\n```"}}]})
        if p == "/_push":
            TG["updates"].append(b); return self._send({"ok": True})
        self._send({}, 404)

def start(port):
    s = ThreadingHTTPServer(("127.0.0.1", port), H)
    threading.Thread(target=s.serve_forever, daemon=True).start(); return s
