import unittest
from unittest.mock import patch

from app.services.mail import MailConfigurationError, send_verification_email


class MailTests(unittest.TestCase):
    def test_missing_configuration_fails_closed(self):
        with patch.dict('os.environ', {}, clear=True):
            with self.assertRaises(MailConfigurationError):
                send_verification_email('cat@example.com', 'token')

    def test_sends_verification_link_over_tls(self):
        config = {'SMTP_HOST': 'smtp.example.com', 'SMTP_PORT': '465',
                  'SMTP_USER': 'account', 'SMTP_PASSWORD': 'secret',
                  'SMTP_FROM': 'service@example.com', 'VERIFICATION_BASE_URL': 'https://example.com/verify'}
        with patch.dict('os.environ', config, clear=True), patch('app.services.mail.smtplib.SMTP_SSL') as smtp:
            send_verification_email('cat@example.com', 'a_token')
            client = smtp.return_value.__enter__.return_value
            message = client.send_message.call_args.args[0]
            self.assertEqual(message['To'], 'cat@example.com')
            self.assertIn('https://example.com/verify#token=a_token', message.get_content())
            client.login.assert_called_once_with('account', 'secret')


if __name__ == '__main__':
    unittest.main()
