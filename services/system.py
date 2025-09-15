import subprocess
import logging
import os
import secrets
import string
import hashlib

logger = logging.getLogger(__name__)

class SystemManager:
    def __init__(self):
        self.admin_user = 'root'  # DietPi default admin user

    def reboot_system(self):
        """Reboot the system"""
        try:
            subprocess.run(['systemctl', 'reboot'], check=True)
            logger.info("System reboot initiated")
            return True, "System reboot initiated"
        except subprocess.CalledProcessError as e:
            error_msg = f"Failed to reboot system: {e}"
            logger.error(error_msg)
            return False, error_msg

    def shutdown_system(self):
        """Shutdown the system"""
        try:
            subprocess.run(['systemctl', 'poweroff'], check=True)
            logger.info("System shutdown initiated")
            return True, "System shutdown initiated"
        except subprocess.CalledProcessError as e:
            error_msg = f"Failed to shutdown system: {e}"
            logger.error(error_msg)
            return False, error_msg

    def get_system_info(self):
        """Get basic system information"""
        try:
            # Get uptime
            uptime_result = subprocess.run(['uptime', '-p'],
                                         capture_output=True, text=True, check=True)
            uptime = uptime_result.stdout.strip()

            # Get load average
            load_result = subprocess.run(['uptime'],
                                       capture_output=True, text=True, check=True)
            load_avg = load_result.stdout.split('load average:')[1].strip()

            # Get memory info
            memory_result = subprocess.run(['free', '-h'],
                                         capture_output=True, text=True, check=True)
            memory_lines = memory_result.stdout.split('\n')
            mem_line = memory_lines[1].split()
            memory = {
                'total': mem_line[1],
                'used': mem_line[2],
                'free': mem_line[3],
                'available': mem_line[6] if len(mem_line) > 6 else mem_line[3]
            }

            # Get disk usage for root partition
            disk_result = subprocess.run(['df', '-h', '/'],
                                       capture_output=True, text=True, check=True)
            disk_lines = disk_result.stdout.split('\n')
            disk_line = disk_lines[1].split()
            disk = {
                'total': disk_line[1],
                'used': disk_line[2],
                'available': disk_line[3],
                'usage_percent': disk_line[4]
            }

            # Get kernel version
            kernel_result = subprocess.run(['uname', '-r'],
                                         capture_output=True, text=True, check=True)
            kernel = kernel_result.stdout.strip()

            # Get architecture
            arch_result = subprocess.run(['uname', '-m'],
                                       capture_output=True, text=True, check=True)
            architecture = arch_result.stdout.strip()

            return {
                'uptime': uptime,
                'load_average': load_avg,
                'memory': memory,
                'disk': disk,
                'kernel': kernel,
                'architecture': architecture
            }

        except Exception as e:
            logger.error(f"Failed to get system info: {e}")
            return None

    def update_system(self):
        """Update the system packages"""
        try:
            # For DietPi, use DietPi-update if available, otherwise use apt
            dietpi_update_path = '/boot/dietpi/dietpi-update'

            if os.path.exists(dietpi_update_path):
                # Use DietPi update system
                result = subprocess.run([dietpi_update_path, '1'],  # 1 = non-interactive
                                      capture_output=True, text=True, timeout=1800)
                if result.returncode == 0:
                    logger.info("DietPi system update completed")
                    return True, "System updated successfully using DietPi-update"
                else:
                    logger.error(f"DietPi update failed: {result.stderr}")
                    return False, f"DietPi update failed: {result.stderr}"
            else:
                # Fall back to standard apt update
                # Update package list
                subprocess.run(['apt', 'update'], check=True, timeout=300)

                # Upgrade packages
                result = subprocess.run(['apt', 'upgrade', '-y'],
                                      capture_output=True, text=True,
                                      check=True, timeout=1800)

                logger.info("System update completed using apt")
                return True, "System updated successfully using apt"

        except subprocess.TimeoutExpired:
            error_msg = "System update timed out"
            logger.error(error_msg)
            return False, error_msg
        except subprocess.CalledProcessError as e:
            error_msg = f"System update failed: {e}"
            logger.error(error_msg)
            return False, error_msg
        except Exception as e:
            error_msg = f"System update error: {e}"
            logger.error(error_msg)
            return False, error_msg

    def change_admin_password(self, new_password):
        """Change the admin user password"""
        try:
            # Validate password strength
            if len(new_password) < 8:
                return False, "Password must be at least 8 characters long"

            if not any(c.isupper() for c in new_password):
                return False, "Password must contain at least one uppercase letter"

            if not any(c.islower() for c in new_password):
                return False, "Password must contain at least one lowercase letter"

            if not any(c.isdigit() for c in new_password):
                return False, "Password must contain at least one digit"

            # Change password using chpasswd (simpler approach, compatible with Python 3.13+)
            chpasswd_input = f"{self.admin_user}:{new_password}"
            result = subprocess.run(['chpasswd'],
                                  input=chpasswd_input,
                                  text=True, check=True)

            logger.info(f"Password changed for user {self.admin_user}")
            return True, "Admin password changed successfully"

        except subprocess.CalledProcessError as e:
            error_msg = f"Failed to change password: {e}"
            logger.error(error_msg)
            return False, error_msg
        except Exception as e:
            error_msg = f"Password change error: {e}"
            logger.error(error_msg)
            return False, error_msg

    def generate_secure_password(self, length=12):
        """Generate a secure random password"""
        alphabet = string.ascii_letters + string.digits + "!@#$%^&*"
        password = ''.join(secrets.choice(alphabet) for _ in range(length))

        # Ensure password meets complexity requirements
        if (any(c.islower() for c in password) and
            any(c.isupper() for c in password) and
            any(c.isdigit() for c in password)):
            return password

        # If generated password doesn't meet requirements, try again
        return self.generate_secure_password(length)

    def get_service_status(self, service_name):
        """Get the status of a systemd service"""
        try:
            result = subprocess.run(['systemctl', 'is-active', service_name],
                                  capture_output=True, text=True)
            is_active = result.stdout.strip() == 'active'

            result = subprocess.run(['systemctl', 'is-enabled', service_name],
                                  capture_output=True, text=True)
            is_enabled = result.stdout.strip() == 'enabled'

            return {
                'active': is_active,
                'enabled': is_enabled,
                'name': service_name
            }

        except Exception as e:
            logger.error(f"Failed to get service status for {service_name}: {e}")
            return {
                'active': False,
                'enabled': False,
                'name': service_name
            }