import subprocess
import re
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

class NetworkManager:
    def __init__(self, interface='eth0'):
        self.interface = interface
        self.dhcpcd_conf = '/etc/dhcpcd.conf'
        self.systemd_network_dir = '/etc/systemd/network'
        self.network_manager = self._detect_network_manager()

    def _detect_network_manager(self):
        """Detect which network management system is in use"""
        try:
            # Check for systemd-networkd
            result = subprocess.run(['systemctl', 'is-active', 'systemd-networkd'],
                                  capture_output=True, text=True)
            if result.returncode == 0:
                logger.info("Detected systemd-networkd as network manager")
                return 'systemd-networkd'

            # Check for dhcpcd
            result = subprocess.run(['systemctl', 'is-active', 'dhcpcd'],
                                  capture_output=True, text=True)
            if result.returncode == 0:
                logger.info("Detected dhcpcd as network manager")
                return 'dhcpcd'

            # Check for NetworkManager
            result = subprocess.run(['systemctl', 'is-active', 'NetworkManager'],
                                  capture_output=True, text=True)
            if result.returncode == 0:
                logger.info("Detected NetworkManager as network manager")
                return 'networkmanager'

            # Default fallback to dhcpcd
            logger.warning("No network manager detected, defaulting to dhcpcd")
            return 'dhcpcd'

        except Exception as e:
            logger.error(f"Failed to detect network manager: {e}")
            return 'dhcpcd'

    def _detect_systemd_networkd_mode(self):
        """Detect if systemd-networkd is using static or DHCP configuration"""
        try:
            # Look for .network files in /etc/systemd/network/
            network_files = list(Path(self.systemd_network_dir).glob('*.network'))

            for network_file in network_files:
                try:
                    with open(network_file, 'r') as f:
                        content = f.read()

                    # Check if this file applies to our interface
                    if f'Name={self.interface}' in content or '[Match]' in content:
                        # Check for static address configuration
                        if 'Address=' in content and '[Network]' in content:
                            return 'static'
                        elif 'DHCP=yes' in content or 'DHCP=true' in content:
                            return 'dhcp'

                except Exception as e:
                    logger.warning(f"Failed to read {network_file}: {e}")
                    continue

            # Default to DHCP if no specific configuration found
            return 'dhcp'

        except Exception as e:
            logger.error(f"Failed to detect systemd-networkd mode: {e}")
            return 'dhcp'

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

            # Detect static configuration based on network manager
            if self.network_manager == 'systemd-networkd':
                config['mode'] = self._detect_systemd_networkd_mode()
            else:
                # Check dhcpcd configuration
                if Path(self.dhcpcd_conf).exists():
                    with open(self.dhcpcd_conf, 'r') as f:
                        lines = f.readlines()

                    in_interface_section = False
                    for line in lines:
                        line_stripped = line.strip()

                        # Check for start of our interface section
                        if line_stripped == f'interface {self.interface}':
                            in_interface_section = True
                            continue

                        # Check for start of another interface section
                        elif line_stripped.startswith('interface ') and in_interface_section:
                            in_interface_section = False
                            break

                        # If we're in our interface section and find static ip_address
                        elif in_interface_section and line_stripped.startswith('static ip_address'):
                            config['mode'] = 'static'
                            break

            return config

        except subprocess.CalledProcessError as e:
            logger.error(f"Failed to get network config: {e}")
            return None

    def set_static_config(self, ip_address, netmask, gateway, dns_servers):
        try:
            if self.network_manager == 'systemd-networkd':
                return self._set_systemd_networkd_static(ip_address, netmask, gateway, dns_servers)
            else:
                return self._set_dhcpcd_static(ip_address, netmask, gateway, dns_servers)

        except Exception as e:
            logger.error(f"Failed to set static config: {e}")
            return False

    def _set_dhcpcd_static(self, ip_address, netmask, gateway, dns_servers):
        """Set static configuration using dhcpcd"""
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

            logger.info(f"Set static IP via dhcpcd: {ip_address}/{netmask}, GW: {gateway}")
            return True

        except Exception as e:
            logger.error(f"Failed to set dhcpcd static config: {e}")
            return False

    def _set_systemd_networkd_static(self, ip_address, netmask, gateway, dns_servers):
        """Set static configuration using systemd-networkd"""
        try:
            # Create network configuration file
            network_file = Path(self.systemd_network_dir) / f"10-{self.interface}.network"

            # Ensure directory exists
            Path(self.systemd_network_dir).mkdir(exist_ok=True)

            # Create static configuration
            config_content = f"""[Match]
Name={self.interface}

[Network]
Address={ip_address}/{netmask}
Gateway={gateway}
DNS={' '.join(dns_servers)}
"""

            # Write configuration file
            with open(network_file, 'w') as f:
                f.write(config_content)

            # Set proper permissions
            network_file.chmod(0o644)

            # Restart networking
            subprocess.run(['systemctl', 'restart', 'systemd-networkd'], check=True)

            logger.info(f"Set static IP via systemd-networkd: {ip_address}/{netmask}, GW: {gateway}")
            return True

        except Exception as e:
            logger.error(f"Failed to set systemd-networkd static config: {e}")
            return False

    def set_dhcp_config(self):
        try:
            if self.network_manager == 'systemd-networkd':
                return self._set_systemd_networkd_dhcp()
            else:
                return self._set_dhcpcd_dhcp()

        except Exception as e:
            logger.error(f"Failed to set DHCP config: {e}")
            return False

    def _set_dhcpcd_dhcp(self):
        """Set DHCP configuration using dhcpcd"""
        try:
            # Remove interface-specific static config
            self._remove_interface_config()

            # Restart networking
            subprocess.run(['systemctl', 'restart', 'dhcpcd'], check=True)

            logger.info(f"Set DHCP mode via dhcpcd for {self.interface}")
            return True

        except Exception as e:
            logger.error(f"Failed to set dhcpcd DHCP config: {e}")
            return False

    def _set_systemd_networkd_dhcp(self):
        """Set DHCP configuration using systemd-networkd"""
        try:
            # Create network configuration file
            network_file = Path(self.systemd_network_dir) / f"10-{self.interface}.network"

            # Ensure directory exists
            Path(self.systemd_network_dir).mkdir(exist_ok=True)

            # Create DHCP configuration
            config_content = f"""[Match]
Name={self.interface}

[Network]
DHCP=yes
"""

            # Write configuration file
            with open(network_file, 'w') as f:
                f.write(config_content)

            # Set proper permissions
            network_file.chmod(0o644)

            # Restart networking
            subprocess.run(['systemctl', 'restart', 'systemd-networkd'], check=True)

            logger.info(f"Set DHCP mode via systemd-networkd for {self.interface}")
            return True

        except Exception as e:
            logger.error(f"Failed to set systemd-networkd DHCP config: {e}")
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

    def get_dhcpcd_config_status(self):
        """Debug method to check network configuration"""
        try:
            debug_info = {
                "network_manager": self.network_manager,
                "interface": self.interface
            }

            # Check dhcpcd.conf
            if Path(self.dhcpcd_conf).exists():
                with open(self.dhcpcd_conf, 'r') as f:
                    dhcpcd_content = f.read()

                debug_info["dhcpcd"] = {
                    "exists": True,
                    "content": dhcpcd_content,
                    "has_interface": f'interface {self.interface}' in dhcpcd_content,
                    "has_static_ip": 'static ip_address' in dhcpcd_content
                }
            else:
                debug_info["dhcpcd"] = {"exists": False}

            # Check systemd-networkd files
            if Path(self.systemd_network_dir).exists():
                network_files = list(Path(self.systemd_network_dir).glob('*.network'))
                debug_info["systemd_networkd"] = {
                    "directory_exists": True,
                    "network_files": [str(f) for f in network_files],
                    "files_content": {}
                }

                for network_file in network_files:
                    try:
                        with open(network_file, 'r') as f:
                            debug_info["systemd_networkd"]["files_content"][str(network_file)] = f.read()
                    except Exception as e:
                        debug_info["systemd_networkd"]["files_content"][str(network_file)] = f"Error reading: {e}"
            else:
                debug_info["systemd_networkd"] = {"directory_exists": False}

            return debug_info

        except Exception as e:
            logger.error(f"Failed to get config status: {e}")
            return {"error": str(e)}