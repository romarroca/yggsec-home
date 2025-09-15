import subprocess
import re
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

class NetworkManager:
    def __init__(self, interface='eth0'):
        self.interface = interface
        self.interfaces_file = '/etc/network/interfaces'

    def _parse_interfaces_file(self):
        """Parse /etc/network/interfaces to get interface configuration"""
        try:
            if not Path(self.interfaces_file).exists():
                return None

            with open(self.interfaces_file, 'r') as f:
                lines = f.readlines()

            interface_config = None
            in_interface_section = False

            for line in lines:
                line = line.strip()

                # Skip comments and empty lines
                if not line or line.startswith('#'):
                    continue

                # Check for interface declaration
                if line.startswith(f'iface {self.interface}'):
                    in_interface_section = True
                    interface_config = {
                        'mode': 'dhcp' if 'dhcp' in line else 'static',
                        'address': None,
                        'netmask': None,
                        'gateway': None,
                        'dns': []
                    }
                    continue

                # Check for end of interface section
                elif line.startswith('iface ') and in_interface_section:
                    break

                # Parse configuration within interface section
                elif in_interface_section and interface_config:
                    if line.startswith('address '):
                        interface_config['address'] = line.split()[1]
                    elif line.startswith('netmask '):
                        interface_config['netmask'] = line.split()[1]
                    elif line.startswith('gateway '):
                        interface_config['gateway'] = line.split()[1]
                    elif line.startswith('dns-nameservers '):
                        interface_config['dns'] = line.split()[1:]

            return interface_config

        except Exception as e:
            logger.error(f"Failed to parse interfaces file: {e}")
            return None

    def get_current_config(self):
        try:
            # Get current IP configuration from running system
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

            # Get configuration mode from /etc/network/interfaces
            interfaces_config = self._parse_interfaces_file()
            if interfaces_config:
                config['mode'] = interfaces_config['mode']

            return config

        except subprocess.CalledProcessError as e:
            logger.error(f"Failed to get network config: {e}")
            return None

    def set_static_config(self, ip_address, netmask, gateway, dns_servers):
        try:
            return self._set_interfaces_static(ip_address, netmask, gateway, dns_servers)
        except Exception as e:
            logger.error(f"Failed to set static config: {e}")
            return False

    def _set_interfaces_static(self, ip_address, netmask, gateway, dns_servers):
        """Set static configuration using /etc/network/interfaces"""
        try:
            # Backup existing interfaces file
            if Path(self.interfaces_file).exists():
                subprocess.run(['cp', self.interfaces_file, f'{self.interfaces_file}.backup'], check=True)

            # Remove existing interface config
            self._remove_interface_config()

            # Add new static configuration
            static_config = f"""
# YggSec-Home static configuration for {self.interface}
auto {self.interface}
iface {self.interface} inet static
\taddress {ip_address}
\tnetmask {netmask}
\tgateway {gateway}
\tdns-nameservers {' '.join(dns_servers)}
"""

            with open(self.interfaces_file, 'a') as f:
                f.write(static_config)

            # Restart networking
            subprocess.run(['systemctl', 'restart', 'networking'], check=True)

            logger.info(f"Set static IP via interfaces: {ip_address}/{netmask}, GW: {gateway}")
            return True

        except Exception as e:
            logger.error(f"Failed to set interfaces static config: {e}")
            return False


    def set_dhcp_config(self):
        try:
            return self._set_interfaces_dhcp()
        except Exception as e:
            logger.error(f"Failed to set DHCP config: {e}")
            return False

    def _set_interfaces_dhcp(self):
        """Set DHCP configuration using /etc/network/interfaces"""
        try:
            # Backup existing interfaces file
            if Path(self.interfaces_file).exists():
                subprocess.run(['cp', self.interfaces_file, f'{self.interfaces_file}.backup'], check=True)

            # Remove existing interface config
            self._remove_interface_config()

            # Add new DHCP configuration
            dhcp_config = f"""
# YggSec-Home DHCP configuration for {self.interface}
auto {self.interface}
iface {self.interface} inet dhcp
"""

            with open(self.interfaces_file, 'a') as f:
                f.write(dhcp_config)

            # Restart networking
            subprocess.run(['systemctl', 'restart', 'networking'], check=True)

            logger.info(f"Set DHCP mode via interfaces for {self.interface}")
            return True

        except Exception as e:
            logger.error(f"Failed to set interfaces DHCP config: {e}")
            return False


    def _remove_interface_config(self):
        """Remove existing configuration for the interface from /etc/network/interfaces"""
        if not Path(self.interfaces_file).exists():
            return

        try:
            with open(self.interfaces_file, 'r') as f:
                lines = f.readlines()

            new_lines = []
            skip_section = False

            for line in lines:
                line_stripped = line.strip()

                # Check for auto declaration for our interface
                if line_stripped == f'auto {self.interface}':
                    skip_section = True
                    continue

                # Check for iface declaration for our interface
                elif line_stripped.startswith(f'iface {self.interface}'):
                    skip_section = True
                    continue

                # Check for start of another interface section
                elif (line_stripped.startswith('auto ') or line_stripped.startswith('iface ')) and skip_section:
                    if not line_stripped.startswith(f'auto {self.interface}') and not line_stripped.startswith(f'iface {self.interface}'):
                        skip_section = False
                        new_lines.append(line)

                # Skip lines in our interface section (indented or interface-specific)
                elif skip_section and (line.startswith('\t') or line.startswith('    ') or
                                     line_stripped.startswith('address ') or
                                     line_stripped.startswith('netmask ') or
                                     line_stripped.startswith('gateway ') or
                                     line_stripped.startswith('dns-nameservers ')):
                    continue

                # Reset skip_section if we encounter a blank line and we were skipping
                elif skip_section and line_stripped == '':
                    skip_section = False
                    new_lines.append(line)

                # Keep all other lines
                else:
                    new_lines.append(line)

            # Write back the modified configuration
            with open(self.interfaces_file, 'w') as f:
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

    def get_interfaces_config_status(self):
        """Debug method to check network configuration"""
        try:
            debug_info = {
                "interface": self.interface,
                "interfaces_file": self.interfaces_file
            }

            # Check /etc/network/interfaces
            if Path(self.interfaces_file).exists():
                with open(self.interfaces_file, 'r') as f:
                    interfaces_content = f.read()

                debug_info["interfaces"] = {
                    "exists": True,
                    "content": interfaces_content,
                    "has_interface": f'iface {self.interface}' in interfaces_content,
                    "has_static": f'iface {self.interface} inet static' in interfaces_content,
                    "has_dhcp": f'iface {self.interface} inet dhcp' in interfaces_content
                }
            else:
                debug_info["interfaces"] = {"exists": False}

            # Parse current configuration
            parsed_config = self._parse_interfaces_file()
            debug_info["parsed_config"] = parsed_config

            return debug_info

        except Exception as e:
            logger.error(f"Failed to get config status: {e}")
            return {"error": str(e)}