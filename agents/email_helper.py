"""
Email helper — Resend API (HTTPS) + fallback SMTP
Railway bloque SMTP (ports 465/587), donc on utilise Resend par défaut.
"""
import os, smtplib, requests as _req
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders
from pathlib import Path

RESEND_API_KEY = os.getenv("RESEND_API_KEY", "")
RESEND_FROM    = os.getenv("RESEND_FROM", "JobAI <noreply@jobai-pro.com>")


def send_email(to: str, subject: str, body: str,
               reply_to: str = "",
               attachments: list = None) -> tuple:
    """
    Envoie un email via Resend (Railway-compatible) ou SMTP en fallback.
    attachments = [{"path": "/path/to/file.pdf", "name": "CV.pdf"}]
    Retourne (succes: bool, erreur: str)
    """
    if RESEND_API_KEY:
        return _send_resend(to, subject, body, reply_to, attachments)
    # Fallback SMTP (fonctionne en local, bloqué sur Railway)
    gmail = os.getenv("GMAIL_ADDRESS", "")
    pwd   = os.getenv("GMAIL_APP_PASSWORD", "")
    if gmail and pwd:
        return _send_smtp(gmail, pwd, to, subject, body, reply_to, attachments)
    return False, "Aucune méthode email configurée (RESEND_API_KEY ou GMAIL_ADDRESS)"


def _send_resend(to, subject, body, reply_to, attachments):
    payload = {
        "from":    RESEND_FROM,
        "to":      [to],
        "subject": subject,
        "text":    body,
    }
    if reply_to:
        payload["reply_to"] = reply_to
    if attachments:
        encoded = []
        for att in (attachments or []):
            p = Path(att.get("path", ""))
            if p.exists():
                import base64 as _b64
                encoded.append({
                    "filename": att.get("name", p.name),
                    "content":  _b64.b64encode(p.read_bytes()).decode(),
                })
        if encoded:
            payload["attachments"] = encoded
    try:
        r = _req.post(
            "https://api.resend.com/emails",
            headers={"Authorization": f"Bearer {RESEND_API_KEY}",
                     "Content-Type": "application/json"},
            json=payload,
            timeout=15
        )
        if r.status_code in (200, 201):
            return True, ""
        return False, f"Resend {r.status_code}: {r.text[:120]}"
    except Exception as e:
        return False, str(e)[:100]


def _send_smtp(gmail, pwd, to, subject, body, reply_to, attachments):
    try:
        msg = MIMEMultipart()
        msg["From"]    = gmail
        msg["To"]      = to
        msg["Subject"] = subject
        if reply_to:
            msg["Reply-To"] = reply_to
        msg.attach(MIMEText(body, "plain", "utf-8"))
        for att in (attachments or []):
            p = Path(att.get("path", ""))
            if p.exists():
                with open(p, "rb") as f:
                    part = MIMEBase("application", "octet-stream")
                    part.set_payload(f.read())
                encoders.encode_base64(part)
                part.add_header("Content-Disposition",
                                f'attachment; filename="{att.get("name", p.name)}"')
                msg.attach(part)
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as srv:
            srv.login(gmail, pwd)
            srv.sendmail(gmail, to, msg.as_string())
        return True, ""
    except Exception as e:
        return False, str(e)[:100]
