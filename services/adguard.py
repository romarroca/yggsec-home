import subprocess
import logging
import json
import requests
from pathlib import Path

logger = logging.getLogger(__name__)

class AdGuardManager:
    def __init__(self, port=3000):
        self.port = port
        self.service_name = 'AdGuardHome'
        self.config_path = '/opt/AdGuardHome/AdGuardHome.yaml'
        self.base_url = f'http://localhost:{port}'

    def get_service_status(self):
        try:
            result = subprocess.run(['systemctl', 'is-active', self.service_name],
                                  capture_output=True, text=True)
            is_active = result.stdout.strip() == 'active'

            result = subprocess.run(['systemctl', 'is-enabled', self.service_name],
                                  capture_output=True, text=True)
            is_enabled = result.stdout.strip() == 'enabled'

            # Check if AdGuard is responding
            is_responding = False
            try:
                response = requests.get(f'{self.base_url}/control/status',
                                      timeout=5)
                is_responding = response.status_code == 200
            except:
                pass

            return {
                'active': is_active,
                'enabled': is_enabled,
                'responding': is_responding,
                'dashboard_url': f'{self.base_url}'
            }

        except Exception as e:
            logger.error(f"Failed to get AdGuard status: {e}")
            return {
                'active': False,
                'enabled': False,
                'responding': False,
                'dashboard_url': f'{self.base_url}'
            }

    def start_service(self):
        try:
            subprocess.run(['systemctl', 'start', self.service_name], check=True)
            logger.info("AdGuard Home started")
            return True
        except subprocess.CalledProcessError as e:
            logger.error(f"Failed to start AdGuard: {e}")
            return False

    def stop_service(self):
        try:
            subprocess.run(['systemctl', 'stop', self.service_name], check=True)
            logger.info("AdGuard Home stopped")
            return True
        except subprocess.CalledProcessError as e:
            logger.error(f"Failed to stop AdGuard: {e}")
            return False

    def restart_service(self):
        try:
            subprocess.run(['systemctl', 'restart', self.service_name], check=True)
            logger.info("AdGuard Home restarted")
            return True
        except subprocess.CalledProcessError as e:
            logger.error(f"Failed to restart AdGuard: {e}")
            return False

    def enable_service(self):
        try:
            subprocess.run(['systemctl', 'enable', self.service_name], check=True)
            logger.info("AdGuard Home enabled")
            return True
        except subprocess.CalledProcessError as e:
            logger.error(f"Failed to enable AdGuard: {e}")
            return False

    def disable_service(self):
        try:
            subprocess.run(['systemctl', 'disable', self.service_name], check=True)
            logger.info("AdGuard Home disabled")
            return True
        except subprocess.CalledProcessError as e:
            logger.error(f"Failed to disable AdGuard: {e}")
            return False

    def get_stats(self):
        try:
            response = requests.get(f'{self.base_url}/control/stats',
                                  timeout=5)
            if response.status_code == 200:
                return response.json()
            return None
        except Exception as e:
            logger.error(f"Failed to get AdGuard stats: {e}")
            return None

    def get_query_log_config(self):
        try:
            response = requests.get(f'{self.base_url}/control/querylog_config',
                                  timeout=5)
            if response.status_code == 200:
                return response.json()
            return None
        except Exception as e:
            logger.error(f"Failed to get query log config: {e}")
            return None