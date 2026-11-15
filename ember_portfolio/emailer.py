"""Email notifications for new contact messages, sent through Resend.

Two transports, chosen with the EMAIL_METHOD environment variable:

  api   (default)  HTTPS POST to https://api.resend.com/emails.
                   Works on PythonAnywhere FREE (api.resend.com is allow-listed)
                   and on Render FREE (which blocks SMTP ports).
  smtp             smtp.resend.com on port 465 (SSL) or 587 (STARTTLS).
                   Needs unrestricted outbound access, e.g. a paid host.

Secrets come from environment variables only; nothing is hard-coded.
"""
import json
import logging
import os
import smtplib
import urllib.error
import urllib.request
from email.message import EmailMessage
from html import escape

log = logging.getLogger("portfolio.email")

TIMEOUT_SECONDS = 10


class EmailError(Exception):
    """Raised when a notification could not be delivered. Message is safe to log."""


def _settings() -> dict:
    return {
        "method": os.environ.get("EMAIL_METHOD", "api").strip().lower(),
        "api_key": os.environ.get("RESEND_API_KEY", "").strip(),
        "api_url": os.environ.get("RESEND_API_URL", "https://api.resend.com/emails"),
        "sender": os.environ.get("MAIL_FROM", "").strip(),
        "recipient": os.environ.get("MAIL_TO", "").strip(),
        "smtp_host": os.environ.get("SMTP_HOST", "smtp.resend.com"),
        "smtp_port": int(os.environ.get("SMTP_PORT", "465")),
    }


def email_is_configured() -> bool:
    s = _settings()
    return bool(s["api_key"] and s["sender"] and s["recipient"])


def _clean_header(value: str) -> str:
    """Strip CR/LF so visitor text can never inject extra email headers."""
    return " ".join(value.replace("\r", " ").replace("\n", " ").split())


def build_content(name: str, email: str, message: str, submitted_at: str) -> tuple[str, str, str]:
    """Return (subject, plain_text, html) for the notification."""
    subject = f"Portfolio message from {_clean_header(name)}"
    text = (
        "New message from your portfolio contact form\n\n"
        f"Name: {name}\n"
        f"Email: {email}\n"
        f"Submitted: {submitted_at}\n\n"
        f"Message:\n{message}\n"
    )
    html = (
        "<h2>New message from your portfolio</h2>"
        f"<p><strong>Name:</strong> {escape(name)}<br>"
        f"<strong>Email:</strong> {escape(email)}<br>"
        f"<strong>Submitted:</strong> {escape(submitted_at)}</p>"
        "<p><strong>Message:</strong></p>"
        f"<p style='white-space:pre-wrap'>{escape(message)}</p>"
        "<hr><p style='color:#777;font-size:12px'>Press Reply to answer the visitor directly.</p>"
    )
    return subject, text, html


def _send_via_api(s: dict, subject: str, text: str, html: str, reply_to: str) -> None:
    payload = {
        "from": s["sender"],
        "to": [s["recipient"]],      # always YOUR inbox, never the visitor
        "reply_to": reply_to,        # visitor's address, so Reply goes to them
        "subject": subject,
        "text": text,
        "html": html,
    }
    request = urllib.request.Request(
        s["api_url"],
        data=json.dumps(payload).encode("utf-8"),
        method="POST",
        headers={
            "Authorization": f"Bearer {s['api_key']}",
            "Content-Type": "application/json",
            # Resend sits behind Cloudflare, which rejects Python's default User-Agent.
            "User-Agent": "sri-lochana-portfolio/1.0",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:
            if response.status not in (200, 201, 202):
                raise EmailError(f"Resend API returned HTTP {response.status}")
    except urllib.error.HTTPError as exc:
        # Resend explains the problem in the body (e.g. unverified domain). Keep it short.
        detail = ""
        try:
            detail = json.loads(exc.read().decode("utf-8")).get("message", "")
        except Exception:
            pass
        raise EmailError(f"Resend API error {exc.code}: {detail}"[:250]) from None
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise EmailError(f"Could not reach Resend API: {type(exc).__name__}") from None


def _send_via_smtp(s: dict, subject: str, text: str, html: str, reply_to: str) -> None:
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = s["sender"]
    msg["To"] = s["recipient"]
    msg["Reply-To"] = reply_to
    msg.set_content(text)
    msg.add_alternative(html, subtype="html")
    try:
        if s["smtp_port"] == 465:
            server = smtplib.SMTP_SSL(s["smtp_host"], 465, timeout=TIMEOUT_SECONDS)
        else:
            server = smtplib.SMTP(s["smtp_host"], s["smtp_port"], timeout=TIMEOUT_SECONDS)
            server.starttls()
        with server:
            server.login("resend", s["api_key"])   # username is literally "resend"
            server.send_message(msg)
    except smtplib.SMTPAuthenticationError:
        raise EmailError("SMTP login rejected (check RESEND_API_KEY)") from None
    except smtplib.SMTPException as exc:
        raise EmailError(f"SMTP error: {type(exc).__name__}") from None
    except (TimeoutError, OSError) as exc:
        raise EmailError(f"Could not reach SMTP server: {type(exc).__name__}") from None


def send_notification(name: str, email: str, message: str, submitted_at: str) -> None:
    """Email the site owner. Raises EmailError on any failure."""
    s = _settings()
    if not (s["api_key"] and s["sender"] and s["recipient"]):
        raise EmailError("Email not configured (RESEND_API_KEY, MAIL_FROM, MAIL_TO)")
    subject, text, html = build_content(name, email, message, submitted_at)
    if s["method"] == "smtp":
        _send_via_smtp(s, subject, text, html, email)
    else:
        _send_via_api(s, subject, text, html, email)
    log.info("Notification email sent via %s", s["method"])
