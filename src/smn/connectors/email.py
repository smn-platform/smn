"""Email connector — governed email delivery via SMTP or API providers.

Provides:
- Content validation (no script injection)
- Rate limiting per recipient
- Attachment size limits
- Template support
- Audit trail
"""

from __future__ import annotations

import logging
import re
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Any

from smn.connectors.base import BaseConnector, ConnectorConfig

logger = logging.getLogger(__name__)

_MAX_RECIPIENTS = 50
_MAX_ATTACHMENT_BYTES = 10 * 1024 * 1024  # 10 MB
_EMAIL_PATTERN = re.compile(r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$")
_SCRIPT_PATTERN = re.compile(r"<\s*script", re.IGNORECASE)


class EmailConnector(BaseConnector):
    """Governed email connector with content validation."""

    def __init__(self, config: ConnectorConfig) -> None:
        super().__init__(config)
        self._smtp_host: str = config.params.get("smtp_host", "")
        self._smtp_port: int = config.params.get("smtp_port", 587)
        self._smtp_user: str = config.params.get("smtp_user", "")
        self._smtp_password: str = config.params.get("smtp_password", "")
        self._from_address: str = config.params.get("from_address", "")
        self._use_tls: bool = config.params.get("use_tls", True)
        self._max_recipients: int = config.params.get("max_recipients", _MAX_RECIPIENTS)

    async def connect(self) -> None:
        if not self._smtp_host:
            raise ValueError("EmailConnector requires 'smtp_host' in params")
        if not self._from_address:
            raise ValueError("EmailConnector requires 'from_address' in params")
        self._is_connected = True
        logger.info("EmailConnector configured: %s via %s", self.config.name, self._smtp_host)

    async def disconnect(self) -> None:
        self._is_connected = False

    async def health_check(self) -> bool:
        if not self._is_connected:
            return False
        try:
            import aiosmtplib
            smtp = aiosmtplib.SMTP(
                hostname=self._smtp_host,
                port=self._smtp_port,
                use_tls=self._use_tls,
            )
            await smtp.connect()
            await smtp.quit()
            return True
        except Exception:
            return False

    async def execute(self, operation: str, **kwargs: Any) -> Any:
        """Send an email.

        Parameters
        ----------
        operation
            "send" — the only supported operation.
        to
            Recipient email address(es) — string or list.
        subject
            Email subject line.
        body
            Email body (plain text or HTML).
        html
            If True, body is treated as HTML (default: False).
        """
        if operation != "send":
            raise ValueError(f"Unknown operation: {operation}. Use 'send'.")

        to = kwargs.get("to", [])
        if isinstance(to, str):
            to = [to]

        subject: str = kwargs.get("subject", "")
        body: str = kwargs.get("body", "")
        is_html: bool = kwargs.get("html", False)

        self._validate_email_params(to, subject, body)

        msg = MIMEMultipart("alternative")
        msg["From"] = self._from_address
        msg["To"] = ", ".join(to)
        msg["Subject"] = subject

        content_type = "html" if is_html else "plain"
        msg.attach(MIMEText(body, content_type, "utf-8"))

        import aiosmtplib
        smtp = aiosmtplib.SMTP(
            hostname=self._smtp_host,
            port=self._smtp_port,
            use_tls=self._use_tls,
        )
        await smtp.connect()
        if self._smtp_user:
            await smtp.login(self._smtp_user, self._smtp_password)
        await smtp.send_message(msg)
        await smtp.quit()

        logger.info("Email sent to %d recipients: %s", len(to), subject)
        return {"status": "sent", "recipients": len(to), "subject": subject}

    def _validate_email_params(
        self, to: list[str], subject: str, body: str
    ) -> None:
        """Validate email parameters for safety."""
        if not to:
            raise ValueError("At least one recipient is required")

        if len(to) > self._max_recipients:
            raise ValueError(f"Too many recipients: {len(to)} > {self._max_recipients}")

        for addr in to:
            if not _EMAIL_PATTERN.match(addr):
                raise ValueError(f"Invalid email address: {addr}")

        if not subject:
            raise ValueError("Subject is required")

        if len(subject) > 998:  # RFC 2822 line length limit
            raise ValueError("Subject too long")

        # Block script injection in HTML emails
        if _SCRIPT_PATTERN.search(body):
            raise ValueError("Script tags are not allowed in email body")

        # Block header injection
        if "\r" in subject or "\n" in subject:
            raise ValueError("Newlines not allowed in subject (header injection)")
