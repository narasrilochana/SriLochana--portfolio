"""Sri Lochana's portfolio backend (FastAPI).

Run locally:   uvicorn main:app --reload
Run in prod:   uvicorn main:app --host 0.0.0.0 --port $PORT

Routes
  GET  /              the portfolio page (templates/index.html)
  GET  /health        health check (also /api/health)
  POST /api/contact   contact form: validate -> save to SQLite -> email me
  GET  /api/messages  read saved messages (needs the X-Admin-Token header)
  GET  /docs          automatic interactive API documentation
"""
import logging
import os
import re
import secrets
import threading
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, field_validator

import settings  # noqa: F401  (loads .env before the modules below read it)
import database
import emailer

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("portfolio")

BASE_DIR = Path(__file__).resolve().parent
IST = timezone(timedelta(hours=5, minutes=30))

app = FastAPI(title="Sri Lochana Portfolio API", version="2.0.0")
database.init_db()

# --- CORS: only needed if the HTML is hosted on a different domain than this API.
# Same-origin (the default here) needs no CORS. Set CORS_ORIGINS="https://a.com,https://b.com".
_origins = [o.strip() for o in os.environ.get("CORS_ORIGINS", "").split(",") if o.strip()]
if _origins:
    app.add_middleware(
        CORSMiddleware, allow_origins=_origins, allow_methods=["GET", "POST"], allow_headers=["Content-Type"]
    )


@app.middleware("http")
async def security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["X-Frame-Options"] = "DENY"
    return response


# ---------------------------------------------------------------- validation
EMAIL_RE = re.compile(r"^[A-Za-z0-9._%+\-]+@[A-Za-z0-9\-]+(\.[A-Za-z0-9\-]+)*\.[A-Za-z]{2,}$")


class ContactForm(BaseModel):
    """Pydantic checks every field before our route code runs."""

    name: str
    email: str
    message: str
    website: str = ""  # honeypot: real visitors never see or fill this field

    @field_validator("name")
    @classmethod
    def check_name(cls, v: str) -> str:
        v = " ".join(v.split())
        if not 2 <= len(v) <= 80:
            raise ValueError("Please enter your name (2 to 80 characters).")
        return v

    @field_validator("email")
    @classmethod
    def check_email(cls, v: str) -> str:
        v = v.strip()
        if len(v) > 254 or not EMAIL_RE.match(v):
            raise ValueError("Please enter a valid email address.")
        return v

    @field_validator("message")
    @classmethod
    def check_message(cls, v: str) -> str:
        v = v.strip()
        if not 10 <= len(v) <= 2000:
            raise ValueError("Your message should be between 10 and 2000 characters.")
        return v


# ------------------------------------------------- lightweight spam protection
_lock = threading.Lock()
_recent_by_ip: dict[str, list[float]] = {}
_recent_messages: dict[str, float] = {}
RATE_LIMIT = 5          # submissions ...
RATE_WINDOW = 600       # ... per 10 minutes per visitor
DUPLICATE_WINDOW = 60   # identical message within 60 s is treated as a double click


def _client_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for", "")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def _rate_limited(ip: str) -> bool:
    now = time.time()
    with _lock:
        hits = [t for t in _recent_by_ip.get(ip, []) if now - t < RATE_WINDOW]
        if len(hits) >= RATE_LIMIT:
            _recent_by_ip[ip] = hits
            return True
        hits.append(now)
        _recent_by_ip[ip] = hits
        return False


def _is_duplicate(key: str) -> bool:
    now = time.time()
    with _lock:
        for k in [k for k, t in _recent_messages.items() if now - t > DUPLICATE_WINDOW]:
            del _recent_messages[k]
        if key in _recent_messages:
            return True
        _recent_messages[key] = now
        return False


# ---------------------------------------------------------------- error handlers
@app.exception_handler(RequestValidationError)
async def validation_error_handler(request: Request, exc: RequestValidationError):
    """Turn Pydantic errors into a simple {field: message} JSON the frontend can show."""
    errors: dict[str, str] = {}
    for err in exc.errors():
        field = str(err["loc"][-1]) if err.get("loc") else "form"
        msg = str(err.get("msg", "Invalid value")).removeprefix("Value error, ")
        errors.setdefault(field, msg)
    return JSONResponse(
        status_code=422,
        content={"ok": False, "message": "Please check the highlighted fields.", "errors": errors},
    )


@app.exception_handler(HTTPException)
async def http_error_handler(request: Request, exc: HTTPException):
    return JSONResponse(status_code=exc.status_code, content={"ok": False, "message": exc.detail})


@app.exception_handler(Exception)
async def unexpected_error_handler(request: Request, exc: Exception):
    log.exception("Unhandled error on %s", request.url.path)  # details go to the log only
    return JSONResponse(
        status_code=500, content={"ok": False, "message": "Something went wrong on the server. Please try again later."}
    )


# ---------------------------------------------------------------- routes
@app.get("/", include_in_schema=False)
def home():
    return FileResponse(BASE_DIR / "templates" / "index.html")


@app.get("/health")
@app.get("/api/health")
def health():
    try:
        database.ping()
        db_ok = True
    except Exception:
        log.exception("Health check: database error")
        db_ok = False
    return {"status": "ok" if db_ok else "degraded", "database": db_ok, "email_configured": emailer.email_is_configured()}


@app.post("/api/contact")
def contact(form: ContactForm, request: Request):
    # Honeypot: bots fill hidden fields. Pretend success, store nothing.
    if form.website.strip():
        log.info("Honeypot triggered; submission ignored")
        return JSONResponse(status_code=200, content={"ok": True, "saved": False, "emailed": False,
                                                      "message": "Thanks! Your message has been sent."})

    if _rate_limited(_client_ip(request)):
        raise HTTPException(status_code=429, detail="Too many messages in a short time. Please try again in a few minutes.")

    if _is_duplicate(f"{form.email.lower()}|{form.message}"):
        return {"ok": True, "saved": True, "emailed": True, "duplicate": True,
                "message": "Thanks! Your message has already been received."}

    submitted_at = datetime.now(IST).strftime("%d %b %Y, %I:%M:%S %p IST")

    # Step 1: save to SQLite
    message_id = None
    try:
        message_id = database.save_message(form.name, form.email, form.message, submitted_at)
    except Exception:
        log.exception("Could not save contact message")

    # Step 2: email notification to the owner (Reply-To = visitor)
    emailed, email_error = True, None
    try:
        emailer.send_notification(form.name, form.email, form.message, submitted_at)
    except emailer.EmailError as exc:
        emailed, email_error = False, str(exc)
        log.error("Email notification failed: %s", exc)  # never includes keys or message text
    except Exception:
        emailed, email_error = False, "Unexpected email error"
        log.exception("Unexpected email failure")

    if message_id is not None:
        try:
            database.set_email_status(message_id, "sent" if emailed else "failed", email_error)
        except Exception:
            log.exception("Could not update email status")

    saved = message_id is not None
    if saved and emailed:
        return JSONResponse(status_code=201, content={"ok": True, "saved": True, "emailed": True,
                                                      "message": "Thank you! Your message has been sent."})
    if saved:
        return JSONResponse(status_code=202, content={"ok": True, "saved": True, "emailed": False,
                            "message": "Your message was saved, but the email alert could not be sent. "
                                       "It will still be read; you can also reach out by another route."})
    if emailed:
        return JSONResponse(status_code=200, content={"ok": True, "saved": False, "emailed": True,
                            "message": "Your message was emailed to Sri Lochana (it could not be stored in the database)."})
    raise HTTPException(status_code=500, detail="Sorry, your message could not be sent. Please try again later.")


@app.get("/api/messages")
def read_messages(x_admin_token: str = Header(default="")):
    """Owner-only view of saved messages. Disabled unless ADMIN_TOKEN is set."""
    expected = os.environ.get("ADMIN_TOKEN", "")
    if not expected:
        raise HTTPException(status_code=404, detail="Not found")
    if not secrets.compare_digest(x_admin_token, expected):
        raise HTTPException(status_code=401, detail="Invalid admin token")
    return {"ok": True, "messages": database.list_messages()}


app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")
