"""Async SMTP delivery + templated emails (i18n)."""
from __future__ import annotations

import logging
from email.message import EmailMessage
from pathlib import Path
from typing import Any

import aiosmtplib
from jinja2 import Environment, FileSystemLoader, select_autoescape

from app.config import settings

logger = logging.getLogger(__name__)

_TEMPLATES_DIR = Path(__file__).parent.parent / "data" / "email_templates"
_jinja = Environment(
    loader=FileSystemLoader(str(_TEMPLATES_DIR)),
    autoescape=select_autoescape(["html", "xml"]),
    enable_async=True,
)


def _render(name: str, locale: str, ctx: dict[str, Any]) -> tuple[str, str]:
    """Return (subject, html). Falls back to English if locale template missing."""
    candidates = [f"{name}.{locale}.html", f"{name}.en.html"]
    for candidate in candidates:
        path = _TEMPLATES_DIR / candidate
        if path.exists():
            template = _jinja.get_template(candidate)
            html = template.render(**ctx, public_base_url=settings.public_base_url)
            subject = html.split("<title>", 1)[1].split("</title>", 1)[0].strip()
            return subject, html
    raise FileNotFoundError(f"No template found for {name} (locale={locale})")


async def send_email(
    *,
    to: str,
    template: str,
    locale: str = "en",
    context: dict[str, Any] | None = None,
) -> None:
    subject, html = _render(template, locale, context or {})
    message = EmailMessage()
    message["From"] = f"{settings.smtp_from_name} <{settings.smtp_from_email}>"
    message["To"] = to
    message["Subject"] = subject
    message.set_content("This email contains HTML. Please use an HTML-capable client.")
    message.add_alternative(html, subtype="html")

    if settings.app_env == "test":
        logger.info("[test] would send email to=%s subject=%s", to, subject)
        return

    try:
        await aiosmtplib.send(
            message,
            hostname=settings.smtp_host,
            port=settings.smtp_port,
            start_tls=settings.smtp_use_tls,
            username=settings.smtp_username or None,
            password=settings.smtp_password or None,
            timeout=15,
        )
        logger.info("Email sent to=%s subject=%s", to, subject)
    except Exception:
        logger.exception("Failed to send email to=%s subject=%s", to, subject)
        raise
