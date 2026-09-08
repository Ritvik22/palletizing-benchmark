from dataclasses import dataclass
import os
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]


@dataclass
class Settings:
    database: str = str(ROOT / '.competition' / 'portal.sqlite')
    origin: str = 'http://127.0.0.1:8769'
    google_client_id: str = ''
    google_client_secret: str = ''
    smtp_host: str = ''
    smtp_port: int = 587
    smtp_username: str = ''
    smtp_password: str = ''
    mail_from: str = ''
    local_admin_login: bool = False

    def __post_init__(self):
        self.origin = self.origin.rstrip('/')
        parsed = urlparse(self.origin)
        if parsed.username or parsed.password or parsed.path or parsed.query or parsed.fragment:
            raise ValueError('PUBLIC_ORIGIN must be an origin, without a path or credentials.')
        if parsed.scheme != 'https' and not (parsed.scheme == 'http' and parsed.hostname in ('127.0.0.1','localhost','::1')):
            raise ValueError('HTTPS is required outside loopback development.')
        if self.local_admin_login and parsed.hostname not in ('127.0.0.1','localhost','::1'):
            raise ValueError('LOCAL_ADMIN_LOGIN is allowed only with a loopback PUBLIC_ORIGIN.')

    @property
    def secure(self):
        return self.origin.startswith('https:')

    @property
    def google_enabled(self):
        return bool(self.google_client_id and self.google_client_secret)

    @property
    def email_enabled(self):
        return bool(self.smtp_host and self.mail_from and self.smtp_username and self.smtp_password)

    @classmethod
    def from_env(cls):
        return cls(database=os.getenv('COMPETITION_DB',cls.database), origin=os.getenv('PUBLIC_ORIGIN',cls.origin),
                   google_client_id=os.getenv('GOOGLE_CLIENT_ID',''), google_client_secret=os.getenv('GOOGLE_CLIENT_SECRET',''),
                   smtp_host=os.getenv('SMTP_HOST',''), smtp_port=int(os.getenv('SMTP_PORT','587')),
                   smtp_username=os.getenv('SMTP_USERNAME',''), smtp_password=os.getenv('SMTP_PASSWORD',''),
                   mail_from=os.getenv('MAIL_FROM',''),
                   local_admin_login=os.getenv('LOCAL_ADMIN_LOGIN','0')=='1')
