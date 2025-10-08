import logging
import smtplib
import socket
from datetime import datetime
from email.message import EmailMessage
from typing import List

from ..config import ReportingConfig
from ..exceptions import ReportingError


def send_failure_report(
    failed_runs: List[int], config: ReportingConfig, stage: str
) -> None:
    logger = logging.getLogger(__name__)
    if not config.send_email_on_error:
        return
    if not failed_runs:
        return

    msg = EmailMessage()
    hostname = socket.gethostname()
    current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    subject = f"Run Record Archiver {stage.capitalize()} Errors on {hostname} at {current_time}"
    body = (
        f"The following runs failed during the {stage} stage:\n\n"
        + "\n".join(map(str, sorted(failed_runs)))
    )

    msg.set_content(body)
    msg["Subject"] = subject
    msg["From"] = config.sender_email
    msg["To"] = config.recipient_email

    try:
        logger.info(
            "Connecting to SMTP server %s:%d to send failure report.",
            config.smtp_host,
            config.smtp_port,
        )
        with smtplib.SMTP(config.smtp_host, config.smtp_port, timeout=10) as server:
            if config.smtp_use_tls:
                server.starttls()
            if config.smtp_user and config.smtp_password:
                server.login(config.smtp_user, config.smtp_password)
            server.send_message(msg)
            logger.info(
                "Failure report email sent successfully to %s.", config.recipient_email
            )
    except (smtplib.SMTPException, socket.gaierror, TimeoutError) as e:
        logger.error("Failed to send failure report email: %s", e)
        raise ReportingError("Failed to send failure report email") from e
