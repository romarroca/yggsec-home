import subprocess
import re
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

class NetworkManager:
    def __init__(self, interface='eth0'):
        self.interface = interface
        self.dhcpcd_conf = '/etc/dhcpcd.conf'

    def get_current_config(self):
        try:
            # Get current IP configuration
            result = subprocess.run(['ip', 'addr', 'show', self.interface],
                                  capture_output=True, text=True, check=True)

            config = {
                'interface': self.interface,
                'ip': None,
                'gateway': None,
                'dns': [],
                'mode': 'dhcp'
            }

            # Parse IP address
            ip_match = re.search(r'inet (\d+\.\d+\.\d+\.\d+)/(\d+)', result.stdout)
            if ip_match:
                config['ip'] = ip_match.group(1)
                config['netmask'] = ip_match.group(2)

            # Get gateway
            try:
                gw_result = subprocess.run(['ip', 'route', 'show', 'default'],
                                         capture_output=True, text=True, check=True)
                gw_match = re.search(r'default via (\d+\.\d+\.\d+\.\d+)', gw_result.stdout)
                if gw_match:
                    config['gateway'] = gw_match.group(1)
            except subprocess.CalledProcessError:
                pass

            # Get DNS servers
            try:
                with open('/etc/resolv.conf', 'r') as f:
                    for line in f:
                        if line.startswith('nameserver'):
                            dns_ip = line.split()[1]
                            config['dns'].append(dns_ip)
            except FileNotFoundError:
                pass

            # Check if static config exists
            if Path(self.dhcpcd_conf).exists():
                with open(self.dhcpcd_conf, 'r') as f:
                    content = f.read()
                    if f'interface {self.interface}' in content and 'static ip_address' in content:
                        config['mode'] = 'static'

            return config

        except subprocess.CalledProcessError as e:
            logger.error(f"Failed to get network config: {e}")
            return None

    def set_static_config(self, ip_address, netmask, gateway, dns_servers):
        try:
            # Backup existing dhcpcd.conf
            if Path(self.dhcpcd_conf).exists():
                subprocess.run(['cp', self.dhcpcd_conf, f'{self.dhcpcd_conf}.backup'], check=True)

            # Remove existing interface config
            self._remove_interface_config()

            # Add new static configuration
            static_config = f"""
# YggSec-Home static configuration for {self.interface}
interface {self.interface}
static ip_address={ip_address}/{netmask}
static routers={gateway}
static domain_name_servers={' '.join(dns_servers)}
"""

            with open(self.dhcpcd_conf, 'a') as f:
                f.write(static_config)

            # Restart networking
            subprocess.run(['systemctl', 'restart', 'dhcpcd'], check=True)

            logger.info(f"Set static IP: {ip_address}/{netmask}, GW: {gateway}")
            return True

        except Exception as e:
            logger.error(f"Failed to set static config: {e}")
            return False

    def set_dhcp_config(self):
        try:
            # Remove interface-specific static config
            self._remove_interface_config()

            # Restart networking
            subprocess.run(['systemctl', 'restart', 'dhcpcd'], check=True)

            logger.info(f"Set DHCP mode for {self.interface}")
            return True

        except Exception as e:
            logger.error(f"Failed to set DHCP config: {e}")
            return False

    def _remove_interface_config(self):
        """Remove existing configuration for the interface from dhcpcd.conf"""
        if not Path(self.dhcpcd_conf).exists():
            return

        try:
            with open(self.dhcpcd_conf, 'r') as f:
                lines = f.readlines()

            new_lines = []
            skip_section = False

            for line in lines:
                line_stripped = line.strip()

                # Check for start of our interface section
                if line_stripped == f'interface {self.interface}':
                    skip_section = True
                    continue

                # Check for start of another interface section
                elif line_stripped.startswith('interface ') and skip_section:
                    skip_section = False
                    new_lines.append(line)

                # Skip lines in our interface section
                elif skip_section:
                    continue

                # Keep all other lines
                else:
                    new_lines.append(line)

            # Write back the modified configuration
            with open(self.dhcpcd_conf, 'w') as f:
                f.writelines(new_lines)

        except Exception as e:
            logger.error(f"Failed to remove interface config: {e}")
            raise

    def get_interface_status(self):
        try:
            result = subprocess.run(['ip', 'link', 'show', self.interface],
                                  capture_output=True, text=True, check=True)

            return {
                'up': 'UP' in result.stdout,
                'connected': 'LOWER_UP' in result.stdout
            }
        except subprocess.CalledProcessError:
            return {'up': False, 'connected': False}