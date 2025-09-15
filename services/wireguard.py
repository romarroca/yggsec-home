import subprocess
import logging
import re
import os
from pathlib import Path

logger = logging.getLogger(__name__)

class WireGuardManager:
    def __init__(self, interface='wg0', config_dir='/etc/wireguard'):
        self.interface = interface
        self.config_dir = Path(config_dir)
        self.config_file = self.config_dir / f'{interface}.conf'

    def get_connection_status(self):
        try:
            # Check if interface is up
            result = subprocess.run(['wg', 'show', self.interface],
                                  capture_output=True, text=True)

            if result.returncode != 0:
                return {
                    'connected': False,
                    'interface': self.interface,
                    'peers': [],
                    'config_exists': self.config_file.exists()
                }

            # Parse wg show output
            peers = []
            current_peer = None

            for line in result.stdout.split('\n'):
                line = line.strip()
                if line.startswith('peer:'):
                    if current_peer:
                        peers.append(current_peer)
                    current_peer = {
                        'public_key': line.split('peer:')[1].strip(),
                        'endpoint': None,
                        'allowed_ips': [],
                        'latest_handshake': None,
                        'transfer': {'rx': 0, 'tx': 0}
                    }
                elif line.startswith('endpoint:') and current_peer:
                    current_peer['endpoint'] = line.split('endpoint:')[1].strip()
                elif line.startswith('allowed ips:') and current_peer:
                    ips = line.split('allowed ips:')[1].strip()
                    current_peer['allowed_ips'] = [ip.strip() for ip in ips.split(',')]
                elif line.startswith('latest handshake:') and current_peer:
                    current_peer['latest_handshake'] = line.split('latest handshake:')[1].strip()
                elif line.startswith('transfer:') and current_peer:
                    transfer_data = line.split('transfer:')[1].strip()
                    # Parse format like "1.23 KiB received, 2.34 KiB sent"
                    rx_match = re.search(r'([\d.]+)\s*(\w+)\s*received', transfer_data)
                    tx_match = re.search(r'([\d.]+)\s*(\w+)\s*sent', transfer_data)
                    if rx_match:
                        current_peer['transfer']['rx'] = f"{rx_match.group(1)} {rx_match.group(2)}"
                    if tx_match:
                        current_peer['transfer']['tx'] = f"{tx_match.group(1)} {tx_match.group(2)}"

            if current_peer:
                peers.append(current_peer)

            return {
                'connected': True,
                'interface': self.interface,
                'peers': peers,
                'config_exists': self.config_file.exists()
            }

        except Exception as e:
            logger.error(f"Failed to get WireGuard status: {e}")
            return {
                'connected': False,
                'interface': self.interface,
                'peers': [],
                'config_exists': self.config_file.exists()
            }

    def validate_config_content(self, content):
        """Validate WireGuard configuration content"""
        required_sections = ['[Interface]', '[Peer]']
        required_interface_keys = ['PrivateKey']
        required_peer_keys = ['PublicKey']

        # Basic format validation
        for section in required_sections:
            if section not in content:
                return False, f"Missing required section: {section}"

        # Check for dangerous commands
        dangerous_patterns = [
            r'PostUp\s*=.*[;&|]',  # Command injection in PostUp
            r'PreDown\s*=.*[;&|]', # Command injection in PreDown
            r'PostDown\s*=.*[;&|]', # Command injection in PostDown
            r'PreUp\s*=.*[;&|]'    # Command injection in PreUp
        ]

        for pattern in dangerous_patterns:
            if re.search(pattern, content, re.IGNORECASE):
                return False, "Configuration contains potentially dangerous commands"

        # Validate key format (base64)
        private_key_match = re.search(r'PrivateKey\s*=\s*([A-Za-z0-9+/=]+)', content)
        if private_key_match:
            key = private_key_match.group(1)
            if len(key) != 44 or not re.match(r'^[A-Za-z0-9+/]+={0,2}$', key):
                return False, "Invalid PrivateKey format"

        public_key_match = re.search(r'PublicKey\s*=\s*([A-Za-z0-9+/=]+)', content)
        if public_key_match:
            key = public_key_match.group(1)
            if len(key) != 44 or not re.match(r'^[A-Za-z0-9+/]+={0,2}$', key):
                return False, "Invalid PublicKey format"

        return True, "Configuration is valid"

    def get_config_content(self):
        """Get current WireGuard configuration content"""
        try:
            if not self.config_file.exists():
                return None

            with open(self.config_file, 'r') as f:
                return f.read()

        except Exception as e:
            logger.error(f"Failed to read config file: {e}")
            return None

    def upload_config(self, content):
        """Upload and validate WireGuard configuration"""
        try:
            # Validate content
            is_valid, message = self.validate_config_content(content)
            if not is_valid:
                logger.error(f"Invalid WireGuard config: {message}")
                return False, message

            # Ensure config directory exists
            self.config_dir.mkdir(exist_ok=True, mode=0o700)

            # Backup existing config if it exists
            if self.config_file.exists():
                backup_file = self.config_file.with_suffix('.conf.backup')
                self.config_file.rename(backup_file)
                logger.info(f"Backed up existing config to {backup_file}")

            # Write new configuration
            with open(self.config_file, 'w') as f:
                f.write(content)

            # Set secure permissions
            os.chmod(self.config_file, 0o600)

            logger.info(f"WireGuard config uploaded to {self.config_file}")
            return True, "Configuration uploaded successfully"

        except Exception as e:
            logger.error(f"Failed to upload WireGuard config: {e}")
            return False, f"Upload failed: {str(e)}"

    def start_tunnel(self):
        """Start WireGuard tunnel"""
        try:
            if not self.config_file.exists():
                return False, "Configuration file does not exist"

            subprocess.run(['wg-quick', 'up', self.interface], check=True)
            logger.info(f"WireGuard tunnel {self.interface} started")
            return True, "Tunnel started successfully"

        except subprocess.CalledProcessError as e:
            error_msg = f"Failed to start tunnel: {e}"
            logger.error(error_msg)
            return False, error_msg

    def stop_tunnel(self):
        """Stop WireGuard tunnel"""
        try:
            subprocess.run(['wg-quick', 'down', self.interface], check=True)
            logger.info(f"WireGuard tunnel {self.interface} stopped")
            return True, "Tunnel stopped successfully"

        except subprocess.CalledProcessError as e:
            error_msg = f"Failed to stop tunnel: {e}"
            logger.error(error_msg)
            return False, error_msg

    def restart_tunnel(self):
        """Restart WireGuard tunnel"""
        try:
            # Stop first (ignore errors if not running)
            subprocess.run(['wg-quick', 'down', self.interface],
                         capture_output=True)

            # Start
            subprocess.run(['wg-quick', 'up', self.interface], check=True)
            logger.info(f"WireGuard tunnel {self.interface} restarted")
            return True, "Tunnel restarted successfully"

        except subprocess.CalledProcessError as e:
            error_msg = f"Failed to restart tunnel: {e}"
            logger.error(error_msg)
            return False, error_msg

    def delete_config(self):
        """Delete WireGuard configuration"""
        try:
            # Stop tunnel first
            self.stop_tunnel()

            if self.config_file.exists():
                self.config_file.unlink()
                logger.info(f"WireGuard config {self.config_file} deleted")

            return True, "Configuration deleted successfully"

        except Exception as e:
            error_msg = f"Failed to delete config: {e}"
            logger.error(error_msg)
            return False, error_msg