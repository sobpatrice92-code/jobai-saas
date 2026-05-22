"""
Email helper — Brevo API (HTTPS) + fallback SMTP
Railway bloque SMTP (ports 465/587), donc on utilise Brevo par défaut.
"""
import os, base64, smtplib, requests as _req
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders
from pathlib import Path

BREVO_API_KEY   = os.getenv("BREVO_API_KEY", "")
BREVO_FROM_EMAIL= os.getenv("BREVO_FROM_EMAIL", "")
BREVO_FROM_NAME = os.getenv("BREVO_FROM_NAME", "JobAI")


def send_email(to: str, subject: str, body: str,
               reply_to: str = "",
               attachments: list = None) -> tuple:
    """
    Envoie un email via Brevo API (Railway-compatible) ou SMTP en fallback.
    attachments = [{"path": "/path/to/file.pdf", "name": "CV.pdf"}]
    Retourne (succes: bool, erreur: str)
    """
    if BREVO_API_KEY and BREVO_FROM_EMAIL:
        return _send_brevo(to, subject, body, reply_to, attachments)
    # Fallback SMTP (fonctionne en local, bloqué sur Railway)
    gmail = os.getenv("GMAIL_ADDRESS", "")
    pwd   = os.getenv("GMAIL_APP_PASSWORD", "")
    if gmail and pwd:
        return _send_smtp(gmail, pwd, to, subject, body, reply_to, attachments)
    return False, "Aucune méthode email configurée (BREVO_API_KEY ou GMAIL_ADDRESS)"


def _send_brevo(to, subject, body, reply_to, attachments):
    payload = {
        "sender":      {"name": BREVO_FROM_NAME, "email": BREVO_FROM_EMAIL},
        "to":          [{"email": to}],
        "subject":     subject,
        "textContent": body,
    }
    if reply_to:
        payload["replyTo"] = {"email": reply_to}
    atts = []
    for att in (attachments or []):
        p = Path(att.get("path", ""))
        if p.exists():
            atts.append({
                "name":    att.get("name", p.name),
                "content": base64.b64encode(p.read_bytes()).decode(),
            })
    if atts:
        payload["attachment"] = atts
    try:
        r = _req.post(
            "https://api.brevo.com/v3/smtp/email",
            headers={"api-key": BREVO_API_KEY, "Content-Type": "application/json"},
            json=payload,
            timeout=15
        )
        if r.status_code in (200, 201, 202):
            return True, ""
        return False, f"Brevo {r.status_code}: {r.text[:120]}"
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
