import os
import ipaddress
from pathlib import Path

class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'yggsec-dev-key-change-in-production'

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
    ADGUARD_PORT = 3000
    ADGUARD_CONFIG = '/opt/AdGuardHome/AdGuardHome.yaml'

    # Upload restrictions
    MAX_CONTENT_LENGTH = 16 * 1024  # 16KB max for .conf files
    ALLOWED_EXTENSIONS = {'conf'}

    # Security
    BIND_HOST = '0.0.0.0'  # LAN access only via firewall
    BIND_PORT = 5000
    DEBUG = False

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