"""Envío de correos de recuperación de contraseña por SMTP.

No se usa un proveedor concreto (Resend, SendGrid...) para no añadir una
dependencia obligatoria: cualquier servicio SMTP sirve (Gmail con contraseña
de aplicación, Mailgun, Amazon SES, Brevo, Resend por SMTP, etc.).
"""

import ipaddress
import logging
import smtplib
import ssl
from email.message import EmailMessage
from urllib.parse import quote, urlparse

from config import config

logger = logging.getLogger("locker.correo")


def enmascarar_email(email: str) -> str:
    """Devuelve el correo con la parte local oculta para los logs."""
    if not email or "@" not in email:
        return "***"
    local, dominio = email.split("@", 1)
    if not local:
        return f"***@{dominio}"
    return f"{local[0]}***@{dominio}"


def _host_local(host: str | None) -> bool:
    """True para localhost, loopback, 0.0.0.0 y dominios .local."""
    if not host:
        return True
    host = host.lower()
    if host in {"localhost", "0.0.0.0"} or host.endswith(".local"):
        return True
    try:
        direccion = ipaddress.ip_address(host)
    except ValueError:
        return False
    return direccion.is_loopback or direccion.is_unspecified


def enlace_recuperacion(destinatario: str, codigo: str) -> str | None:
    """Enlace directo a la app, solo si ``APP_URL`` es una web real.

    En desarrollo ``APP_URL`` apunta a localhost, que no sirve desde el móvil ni
    desde otro dispositivo: en ese caso se envía solo el código.
    """
    base = (config.APP_URL or "").strip()
    try:
        url = urlparse(base)
    except ValueError:
        return None
    if url.scheme not in ("http", "https") or _host_local(url.hostname):
        return None
    return (
        f"{base.rstrip('/')}/recuperar"
        f"?correo={quote(destinatario, safe='')}&codigo={quote(codigo, safe='')}"
    )


def enviar_codigo_recuperacion(destinatario: str, codigo: str) -> bool:
    """Envía el código de recuperación. Devuelve True solo si se entregó al SMTP."""
    if not config.smtp_configurado:
        logger.warning(
            "SMTP no configurado: no se pudo enviar el correo de recuperación a %s. "
            "Define SMTP_HOST y SMTP_FROM (o SMTP_USER) en el .env.",
            enmascarar_email(destinatario),
        )
        return False

    remitente = config.SMTP_FROM or config.SMTP_USER
    minutos = config.RESET_TOKEN_EXPIRE_MINUTES
    enlace = enlace_recuperacion(destinatario, codigo)

    texto = (
        "Hola:\n\n"
        f"Usa este código para restablecer tu contraseña de Locker:\n\n{codigo}\n\n"
        f"El código caduca en {minutos} minutos y solo puede usarse una vez.\n"
    )
    if enlace:
        texto += f"\nTambién puedes abrir: {enlace}\n"
    texto += "\nSi no solicitaste el cambio, ignora este mensaje.\n"

    parrafo_enlace = (
        f'    <p><a href="{enlace}">Abrir la app</a></p>\n' if enlace else ""
    )

    mensaje = EmailMessage()
    mensaje["Subject"] = "Recupera tu contraseña de Locker"
    mensaje["From"] = remitente
    mensaje["To"] = destinatario
    mensaje.set_content(texto)
    mensaje.add_alternative(
        f"""\
<html>
  <body style="font-family: system-ui, sans-serif; color: #1f2937;">
    <h2>Recupera tu contraseña de Locker</h2>
    <p>Usa este código para restablecer tu contraseña:</p>
    <p style="font-size: 24px; font-weight: bold; letter-spacing: 2px;">{codigo}</p>
    <p>Caduca en {minutos} minutos y solo puede usarse una vez.</p>
{parrafo_enlace}    <p style="color: #6b7280;">Si no solicitaste el cambio, ignora este mensaje.</p>
  </body>
</html>""",
        subtype="html",
    )

    contexto = ssl.create_default_context()
    try:
        if config.SMTP_SSL:
            with smtplib.SMTP_SSL(
                config.SMTP_HOST, config.SMTP_PORT, context=contexto, timeout=15
            ) as smtp:
                if config.SMTP_USER:
                    smtp.login(config.SMTP_USER, config.SMTP_PASSWORD or "")
                smtp.send_message(mensaje)
        else:
            with smtplib.SMTP(config.SMTP_HOST, config.SMTP_PORT, timeout=15) as smtp:
                smtp.ehlo()
                if config.SMTP_TLS:
                    smtp.starttls(context=contexto)
                    smtp.ehlo()
                if config.SMTP_USER:
                    smtp.login(config.SMTP_USER, config.SMTP_PASSWORD or "")
                smtp.send_message(mensaje)
    except Exception:
        logger.exception(
            "No se pudo enviar el correo de recuperación a %s",
            enmascarar_email(destinatario),
        )
        return False

    logger.info("Correo de recuperación enviado a %s", enmascarar_email(destinatario))
    return True
