import logging
import smtplib
import socket
from datetime import datetime
from email.message import EmailMessage
from typing import List, Optional
from ..config import ReportingConfig
from ..exceptions import ReportingError
try:
    from slack_bolt import App
    SLACK_AVAILABLE = True
except ImportError:
    SLACK_AVAILABLE = False

def _send_slack_notification(failed_runs: List[int], config: ReportingConfig, stage: str) -> None:
    logger = logging.getLogger(__name__)
    if not config.slack.enabled:
        return
    if not SLACK_AVAILABLE:
        logger.warning('Slack notifications enabled but slack-bolt library not available')
        return
    if not failed_runs:
        return
    try:
        app = App(token=config.slack.bot_token)
        hostname = socket.gethostname()
        current_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        run_count = len(failed_runs)
        if run_count <= 10:
            run_list = ', '.join(map(str, sorted(failed_runs)))
        else:
            first_runs = sorted(failed_runs)[:10]
            run_list = ', '.join(map(str, first_runs)) + f', ... ({run_count - 10} more)'
        mentions = ''
        if config.slack.mention_users:
            user_ids = [uid.strip() for uid in config.slack.mention_users.split(',')]
            mentions = ' ' + ' '.join([f'<@{uid}>' for uid in user_ids if uid])
        blocks = [{'type': 'header', 'text': {'type': 'plain_text', 'text': f'⚠️ Run Record Archiver {stage.capitalize()} Failures'}}, {'type': 'section', 'fields': [{'type': 'mrkdwn', 'text': f'*Host:*\n{hostname}'}, {'type': 'mrkdwn', 'text': f'*Time:*\n{current_time}'}, {'type': 'mrkdwn', 'text': f'*Stage:*\n{stage.capitalize()}'}, {'type': 'mrkdwn', 'text': f'*Failed Runs:*\n{run_count}'}]}, {'type': 'section', 'text': {'type': 'mrkdwn', 'text': f'*Run Numbers:*\n{run_list}'}}]
        response = app.client.chat_postMessage(channel=config.slack.channel, text=f'Run Record Archiver {stage.capitalize()} Failures: {run_count} runs failed on {hostname}{mentions}', blocks=blocks)
        if response['ok']:
            logger.info('Slack notification sent successfully to channel %s', config.slack.channel)
        else:
            logger.error('Failed to send Slack notification: %s', response.get('error', 'Unknown error'))
    except Exception as e:
        logger.error('Failed to send Slack notification: %s', e)

def send_failure_report(failed_runs: List[int], config: ReportingConfig, stage: str) -> None:
    logger = logging.getLogger(__name__)
    if not failed_runs:
        return
    _send_slack_notification(failed_runs, config, stage)
    if not config.email.enabled:
        return
    msg = EmailMessage()
    hostname = socket.gethostname()
    current_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    subject = f'Run Record Archiver {stage.capitalize()} Errors on {hostname} at {current_time}'
    body = f'The following runs failed during the {stage} stage:\n\n' + '\n'.join(map(str, sorted(failed_runs)))
    msg.set_content(body)
    msg['Subject'] = subject
    msg['From'] = config.email.sender_email
    msg['To'] = config.email.recipient_email
    try:
        logger.info('Connecting to SMTP server %s:%d to send failure report.', config.email.smtp_host, config.email.smtp_port)
        with smtplib.SMTP(config.email.smtp_host, config.email.smtp_port, timeout=10) as server:
            if config.email.smtp_use_tls:
                server.starttls()
            if config.email.smtp_user and config.email.smtp_password:
                server.login(config.email.smtp_user, config.email.smtp_password)
            server.send_message(msg)
            logger.info('Failure report email sent successfully to %s.', config.email.recipient_email)
    except (smtplib.SMTPException, socket.gaierror, TimeoutError) as e:
        logger.error('Failed to send failure report email: %s', e)
        raise ReportingError('Failed to send failure report email') from e