import subprocess
import logging
import json
import requests
import socket
from pathlib import Path

logger = logging.getLogger(__name__)

class AdGuardManager:
    def __init__(self, port=3000, username=None, password=None):
        self.port = port
        self.service_name = 'AdGuardHome'
        self.config_path = '/opt/AdGuardHome/AdGuardHome.yaml'
        self.username = username
        self.password = password

    def _get_local_ip(self):
        """Get the local IP address of the machine"""
        try:
            # Connect to a remote address to determine local IP
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
                s.connect(('8.8.8.8', 80))
                local_ip = s.getsockname()[0]
            return local_ip
        except Exception:
            # Fallback to localhost if unable to determine IP
            return 'localhost'

    def _get_base_url(self, use_ip=False):
        """Get base URL for AdGuard, optionally using IP instead of localhost"""
        if use_ip:
            ip = self._get_local_ip()
            return f'http://{ip}:{self.port}'
        return f'http://localhost:{self.port}'

    def _get_auth(self):
        """Get authentication tuple for requests if credentials are provided"""
        if self.username and self.password:
            return (self.username, self.password)
        return None

    def get_service_status(self):
        try:
            result = subprocess.run(['systemctl', 'is-active', self.service_name],
                                  capture_output=True, text=True)
            is_active = result.stdout.strip() == 'active'

            result = subprocess.run(['systemctl', 'is-enabled', self.service_name],
                                  capture_output=True, text=True)
            is_enabled = result.stdout.strip() == 'enabled'

            # Check if AdGuard is responding (use localhost for internal check)
            is_responding = False
            localhost_url = self._get_base_url(use_ip=False)
            try:
                response = requests.get(f'{localhost_url}/control/status',
                                      timeout=5)
                is_responding = response.status_code == 200
            except:
                pass

            # Use IP address for dashboard URL (for external access)
            dashboard_url = self._get_base_url(use_ip=True)

            return {
                'active': is_active,
                'enabled': is_enabled,
                'responding': is_responding,
                'dashboard_url': dashboard_url
            }

        except Exception as e:
            logger.error(f"Failed to get AdGuard status: {e}")
            # Fallback URLs
            dashboard_url = self._get_base_url(use_ip=True)
            return {
                'active': False,
                'enabled': False,
                'responding': False,
                'dashboard_url': dashboard_url
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
            localhost_url = self._get_base_url(use_ip=False)
            response = requests.get(f'{localhost_url}/control/stats',
                                  timeout=5)
            if response.status_code == 200:
                return response.json()
            return None
        except Exception as e:
            logger.error(f"Failed to get AdGuard stats: {e}")
            return None

    def get_query_log_config(self):
        try:
            localhost_url = self._get_base_url(use_ip=False)
            response = requests.get(f'{localhost_url}/control/querylog_config',
                                  timeout=5)
            if response.status_code == 200:
                return response.json()
            return None
        except Exception as e:
            logger.error(f"Failed to get query log config: {e}")
            return None

    def get_query_log(self, older_than=None, limit=100):
        try:
            localhost_url = self._get_base_url(use_ip=False)
            params = {}
            if older_than:
                params['older_than'] = older_than
            if limit:
                params['limit'] = limit

            response = requests.get(f'{localhost_url}/control/querylog',
                                  params=params, timeout=10)
            if response.status_code == 200:
                return response.json()
            return None
        except Exception as e:
            logger.error(f"Failed to get query log: {e}")
            return None

    def get_stats_info(self):
        try:
            localhost_url = self._get_base_url(use_ip=False)
            response = requests.get(f'{localhost_url}/control/stats_info',
                                  timeout=5)
            if response.status_code == 200:
                return response.json()
            return None
        except Exception as e:
            logger.error(f"Failed to get stats info: {e}")
            return None

    def get_stats_history(self):
        try:
            localhost_url = self._get_base_url(use_ip=False)
            response = requests.get(f'{localhost_url}/control/stats_history',
                                  timeout=5)
            if response.status_code == 200:
                return response.json()
            return None
        except Exception as e:
            logger.error(f"Failed to get stats history: {e}")
            return None

    def get_top_blocked_domains(self):
        try:
            localhost_url = self._get_base_url(use_ip=False)
            response = requests.get(f'{localhost_url}/control/stats/top_blocked_domains',
                                  timeout=5)
            if response.status_code == 200:
                return response.json()
            return None
        except Exception as e:
            logger.error(f"Failed to get top blocked domains: {e}")
            return None

    def get_top_clients(self):
        try:
            localhost_url = self._get_base_url(use_ip=False)
            response = requests.get(f'{localhost_url}/control/stats/top_clients',
                                  timeout=5)
            if response.status_code == 200:
                return response.json()
            return None
        except Exception as e:
            logger.error(f"Failed to get top clients: {e}")
            return None

    def get_top_queried_domains(self):
        try:
            localhost_url = self._get_base_url(use_ip=False)
            response = requests.get(f'{localhost_url}/control/stats/top_queried_domains',
                                  timeout=5)
            if response.status_code == 200:
                return response.json()
            return None
        except Exception as e:
            logger.error(f"Failed to get top queried domains: {e}")
            return None