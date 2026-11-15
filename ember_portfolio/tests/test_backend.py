"""Offline tests for database.py and emailer.py (no internet needed).

Run from the ember_portfolio folder:   python tests/test_backend.py
A tiny local server pretends to be api.resend.com so we can inspect the request.
"""
import json
import os
import sqlite3
import sys
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ["DATABASE_PATH"] = os.path.join(tempfile.mkdtemp(), "test.db")

import database  # noqa: E402
import emailer  # noqa: E402

captured = {}
reply_status = {"code": 200}


class FakeResend(BaseHTTPRequestHandler):
    def do_POST(self):
        body = self.rfile.read(int(self.headers["Content-Length"]))
        captured["body"] = json.loads(body)
        captured["auth"] = self.headers.get("Authorization")
        captured["ua"] = self.headers.get("User-Agent")
        self.send_response(reply_status["code"])
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        if reply_status["code"] >= 400:
            self.wfile.write(b'{"message":"The domain is not verified."}')
        else:
            self.wfile.write(b'{"id":"fake-id"}')

    def log_message(self, *args):
        pass


server = HTTPServer(("127.0.0.1", 0), FakeResend)
threading.Thread(target=server.serve_forever, daemon=True).start()
os.environ.update(
    RESEND_API_URL=f"http://127.0.0.1:{server.server_port}/emails",
    RESEND_API_KEY="re_test_key", MAIL_FROM="Portfolio <hello@example.com>", MAIL_TO="owner@example.com",
)

NAME, EMAIL, MSG, WHEN = "Asha <b>Rao</b>", "asha@visitor.com", "Hi!\nLoved your projects.", "15 Nov 2026, 02:00:00 PM IST"

# 1. API transport: recipient, reply-to, content, auth header
emailer.send_notification(NAME, EMAIL, MSG, WHEN)
b = captured["body"]
assert b["to"] == ["owner@example.com"], b["to"]
assert b["reply_to"] == "asha@visitor.com"
assert b["from"] == "Portfolio <hello@example.com>"
for needle in ("Asha", "asha@visitor.com", "Loved your projects.", WHEN):
    assert needle in b["text"], needle
assert "&lt;b&gt;" in b["html"] and "<b>Rao" not in b["html"]  # HTML is escaped
assert captured["auth"] == "Bearer re_test_key" and captured["ua"].startswith("sri-lochana")
print("PASS api: to=owner, reply_to=visitor, name/email/message/time present, HTML escaped")

# 2. API error is reported without leaking the key
reply_status["code"] = 403
try:
    emailer.send_notification(NAME, EMAIL, MSG, WHEN)
    raise SystemExit("expected EmailError")
except emailer.EmailError as exc:
    assert "not verified" in str(exc) and "re_test_key" not in str(exc)
    print("PASS api error handled:", exc)

# 3. Unreachable server
os.environ["RESEND_API_URL"] = "http://127.0.0.1:9/emails"
try:
    emailer.send_notification(NAME, EMAIL, MSG, WHEN)
    raise SystemExit("expected EmailError")
except emailer.EmailError as exc:
    print("PASS unreachable handled:", exc)

# 4. Missing configuration
for k in ("RESEND_API_KEY", "MAIL_TO"):
    os.environ.pop(k)
try:
    emailer.send_notification(NAME, EMAIL, MSG, WHEN)
    raise SystemExit("expected EmailError")
except emailer.EmailError as exc:
    print("PASS missing config handled:", exc)
os.environ.update(RESEND_API_KEY="re_test_key", MAIL_TO="owner@example.com")

# 5. SMTP transport (smtplib faked): login user, reply-to, recipient
sent = {}


class FakeSMTP:
    def __init__(self, host, port, timeout=None):
        sent.update(host=host, port=port, timeout=timeout)
    def __enter__(self): return self
    def __exit__(self, *a): return False
    def login(self, user, pw): sent.update(user=user, pw=pw)
    def starttls(self): sent["tls"] = "starttls"
    def send_message(self, msg): sent["msg"] = msg


emailer.smtplib.SMTP_SSL = FakeSMTP
emailer.smtplib.SMTP = FakeSMTP
os.environ["EMAIL_METHOD"] = "smtp"
emailer.send_notification("Line\r\nBcc: evil@x.com", EMAIL, MSG, WHEN)
m = sent["msg"]
assert (sent["host"], sent["port"], sent["user"]) == ("smtp.resend.com", 465, "resend") and sent["timeout"] == 10
assert m["To"] == "owner@example.com" and m["Reply-To"] == "asha@visitor.com"
assert "\n" not in m["Subject"] and m["Bcc"] is None  # header injection blocked
print("PASS smtp: host/port/user/timeout, To=owner, Reply-To=visitor, header injection blocked")

# 6. Database: new table, save, status update, legacy-table migration
database.init_db()
mid = database.save_message("Asha", EMAIL, "Hello there, nice site", WHEN)
database.set_email_status(mid, "failed", "boom")
row = database.list_messages()[0]
assert row["email_status"] == "failed" and row["email_error"] == "boom"
legacy = os.path.join(tempfile.mkdtemp(), "legacy.db")
c = sqlite3.connect(legacy)
c.execute("CREATE TABLE messages (id INTEGER PRIMARY KEY, name TEXT, email TEXT, message TEXT)")
c.execute("INSERT INTO messages (name,email,message) VALUES ('Old','old@x.com','kept')")
c.commit(); c.close()
database.DB_PATH = legacy
database.init_db()
old = database.list_messages()[0]
assert old["message"] == "kept" and old["email_status"] == "pending"
# SQL injection attempt is stored as plain text
database.save_message("x'); DROP TABLE messages;--", EMAIL, "payload test message", WHEN)
assert len(database.list_messages()) == 2
print("PASS database: save, status update, legacy migration, parameterised SQL")
print("\nALL BACKEND TESTS PASSED")
