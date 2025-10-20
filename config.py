import os
import ipaddress
import secrets
from pathlib import Path
from datetime import timedelta

class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY') or secrets.token_urlsafe(32)

    # File paths
    BASE_DIR = Path(__file__).parent
    UPLOAD_DIR = BASE_DIR / 'uploads'
    LOG_DIR = BASE_DIR / 'logs'

    # Network configuration
    NETWORK_INTERFACE = 'eth0'
    DHCPCD_CONF = '/etc/dhcpcd.conf'

    # WireGuard configuration
    WG_CONF_DIR = '/etc/wireguard'
    WG_INTERFACE = 'wg0'

    # AdGuard Home
    ADGUARD_PORT = 3001  # Direct connection to AdGuard (localhost only)
    ADGUARD_CONFIG = '/opt/AdGuardHome/AdGuardHome.yaml'
    ADGUARD_USERNAME = os.environ.get('ADMIN_USERNAME')
    ADGUARD_PASSWORD = os.environ.get('ADMIN_PASSWORD')

    # Upload restrictions
    MAX_CONTENT_LENGTH = 16 * 1024  # 16KB max for .conf files
    ALLOWED_EXTENSIONS = {'conf'}

    # Security
    BIND_HOST = '127.0.0.1'  # Localhost only - nginx handles external access
    BIND_PORT = 5000
    DEBUG = False
    SESSION_TIMEOUT = timedelta(hours=12)  # 12 hour session timeout

    # CSRF protection
    WTF_CSRF_TIME_LIMIT = 3600  # 1 hour CSRF token validity

    @staticmethod
    def init_app(app):
        # Create required directories
        Config.UPLOAD_DIR.mkdir(exist_ok=True)
        Config.LOG_DIR.mkdir(exist_ok=True)

        # Set upload limit
        app.config['MAX_CONTENT_LENGTH'] = Config.MAX_CONTENT_LENGTH

def validate_ip_address(ip_str):
    try:
        ipaddress.ip_address(ip_str)
        return True
    except ValueError:
        return False

def validate_network_mask(mask_str):
    try:
        mask = int(mask_str)
        return 0 <= mask <= 32
    except ValueError:
        return False