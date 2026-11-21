import os
import smtplib
import ssl
from email.message import EmailMessage
from urllib.parse import urlencode, urlsplit, urlunsplit


class MailConfigurationError(Exception):
    pass


def send_verification_email(recipient: str, token: str) -> None:
    names = ('SMTP_HOST', 'SMTP_PORT', 'SMTP_USER', 'SMTP_PASSWORD', 'SMTP_FROM', 'VERIFICATION_BASE_URL')
    values = {name: os.environ.get(name, '') for name in names}
    if not all(values.values()):
        raise MailConfigurationError('SMTP settings and verification URL are required')
    url = urlsplit(values['VERIFICATION_BASE_URL'])
    if url.scheme != 'https' or not url.netloc or url.query or url.fragment:
        raise MailConfigurationError('Verification URL must be HTTPS without query or fragment')
    try:
        port = int(values['SMTP_PORT'])
        if not 1 <= port <= 65535:
            raise ValueError()
    except ValueError as exc:
        raise MailConfigurationError('Invalid SMTP port') from exc
    link = urlunsplit((url.scheme, url.netloc, url.path, '', urlencode({'token': token})))
    message = EmailMessage()
    message['Subject'] = '验证你的绒星邮箱'
    message['From'] = values['SMTP_FROM']
    message['To'] = recipient
    message.set_content('请打开以下链接验证邮箱，链接将在 24 小时后失效：\n\n' + link + '\n')
    with smtplib.SMTP_SSL(values['SMTP_HOST'], port, timeout=10, context=ssl.create_default_context()) as client:
        client.login(values['SMTP_USER'], values['SMTP_PASSWORD'])
        client.send_message(message)
