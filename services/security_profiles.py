#!/usr/bin/env python3

import json
import logging
import requests
import yaml
import subprocess
from pathlib import Path
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

class SecurityProfileManager:
    """
    Manages AdGuard Home security profiles with Light, Balanced, and Maximum modes.
    Each mode enables different sets of blocklists for varying levels of protection.
    """

    def __init__(self, adguard_manager, profiles_file='security_profiles.json'):
        """
        Initialize the Security Profile Manager.

        Args:
            adguard_manager: Instance of AdGuardManager for API communication
            profiles_file: Path to the security profiles JSON configuration
        """
        self.adguard = adguard_manager
        self.profiles_file = Path(profiles_file)
        self.profiles = self._load_profiles()
        self.current_mode = self._get_current_mode()

    def _load_profiles(self) -> Dict:
        """Load security profiles from JSON file."""
        try:
            if self.profiles_file.exists():
                with open(self.profiles_file, 'r') as f:
                    return json.load(f)
            else:
                logger.error(f"Security profiles file not found: {self.profiles_file}")
                return {}
        except Exception as e:
            logger.error(f"Failed to load security profiles: {e}")
            return {}

    def _get_current_mode(self) -> str:
        """
        Determine current security mode by analyzing enabled filters in config file.
        Returns 'balanced' as default if unable to determine.
        """
        try:
            config_path = Path('/opt/AdGuardHome/AdGuardHome.yaml')

            if not config_path.exists():
                logger.warning("AdGuard config file not found, defaulting to balanced")
                return 'balanced'

            with open(config_path, 'r') as f:
                config = yaml.safe_load(f)

            current_filters = config.get('filters', [])
            enabled_urls = {f.get('url') for f in current_filters if f.get('enabled')}

            # Check which mode matches current enabled filters best
            for mode_name in ['maximum', 'balanced', 'light']:  # Check from most restrictive to least
                expected_urls = set(self._get_filter_urls_for_mode(mode_name))
                if enabled_urls >= expected_urls:  # Current filters include all expected
                    return mode_name

            return 'balanced'  # Default fallback

        except Exception as e:
            logger.error(f"Failed to determine current mode: {e}")
            return 'balanced'

    def _get_filter_urls_for_mode(self, mode: str) -> List[str]:
        """
        Get all filter URLs that should be enabled for a given mode.
        Handles inheritance (e.g., 'balanced' inherits from 'light').
        """
        if mode not in self.profiles.get('modes', {}):
            return []

        mode_config = self.profiles['modes'][mode]
        urls = []

        for list_item in mode_config.get('lists', []):
            if 'inherit' in list_item:
                # Recursively get URLs from inherited mode
                inherited_mode = list_item['inherit']
                urls.extend(self._get_filter_urls_for_mode(inherited_mode))
            elif list_item.get('url'):
                urls.append(list_item['url'])

        return urls

    def _get_all_filters_for_mode(self, mode: str) -> List[Dict]:
        """
        Get all filter configurations for a mode, including inherited ones.
        """
        if mode not in self.profiles.get('modes', {}):
            return []

        mode_config = self.profiles['modes'][mode]
        filters = []

        for list_item in mode_config.get('lists', []):
            if 'inherit' in list_item:
                # Recursively get filters from inherited mode
                inherited_mode = list_item['inherit']
                filters.extend(self._get_all_filters_for_mode(inherited_mode))
            elif list_item.get('url') or list_item.get('catalog_hint'):
                filters.append(list_item)

        return filters

    def get_available_modes(self) -> Dict[str, Dict]:
        """Get all available security modes with descriptions."""
        modes = {}
        for mode_name, mode_config in self.profiles.get('modes', {}).items():
            filters = self._get_all_filters_for_mode(mode_name)
            modes[mode_name] = {
                'description': mode_config.get('description', ''),
                'filter_count': len(filters),
                'filters': filters,
                'adult_content': mode_config.get('adult_content', {})
            }
        return modes

    def get_current_mode(self) -> str:
        """Get the currently active security mode."""
        return self.current_mode

    def set_security_mode(self, mode: str) -> Tuple[bool, str]:
        """
        Set the security mode by directly editing AdGuard configuration file.

        Args:
            mode: One of 'light', 'balanced', or 'maximum'

        Returns:
            Tuple of (success: bool, message: str)
        """
        if mode not in self.profiles.get('modes', {}):
            return False, f"Invalid security mode: {mode}"

        try:
            logger.info(f"Setting security mode to: {mode}")

            # Step 1: Update AdGuard config file
            success, message = self._update_adguard_config(mode)
            if not success:
                return False, f"Failed to update AdGuard config: {message}"

            # Step 2: Restart AdGuard service to apply changes
            success, message = self._restart_adguard()
            if not success:
                return False, f"Failed to restart AdGuard: {message}"

            # Update current mode
            self.current_mode = mode

            logger.info(f"Successfully set security mode to: {mode}")
            return True, f"Security mode set to {mode.title()}"

        except Exception as e:
            logger.error(f"Failed to set security mode {mode}: {e}", exc_info=True)
            return False, f"Failed to set security mode: {str(e)}"

    def _update_adguard_config(self, mode: str) -> Tuple[bool, str]:
        """Update AdGuard configuration file with filters for the specified mode."""
        try:
            config_path = Path('/opt/AdGuardHome/AdGuardHome.yaml')

            # Read current config
            with open(config_path, 'r') as f:
                config = yaml.safe_load(f)

            # Get filters for the mode
            target_filters = self._get_all_filters_for_mode(mode)

            # Update filters section
            config['filters'] = []
            for i, filter_config in enumerate(target_filters, 1):
                if filter_config.get('url'):  # Only add filters with URLs
                    config['filters'].append({
                        'enabled': True,
                        'url': filter_config['url'],
                        'name': filter_config['name'],
                        'id': i
                    })

            # Handle adult content for maximum mode
            if mode == 'maximum':
                adult_config = self.profiles['modes'][mode].get('adult_content', {})
                if adult_config.get('enable'):
                    # Enable parental control in AdGuard config
                    if 'dns' not in config:
                        config['dns'] = {}
                    config['dns']['parental_enabled'] = True

            # Write updated config
            with open(config_path, 'w') as f:
                yaml.dump(config, f, default_flow_style=False, sort_keys=False)

            logger.info(f"Updated AdGuard config with {len(config['filters'])} filters for {mode} mode")
            return True, f"Updated AdGuard configuration for {mode} mode"

        except Exception as e:
            logger.error(f"Failed to update AdGuard config: {e}")
            return False, str(e)

    def _restart_adguard(self) -> Tuple[bool, str]:
        """Restart AdGuard Home service to apply configuration changes."""
        try:
            # Restart the service
            result = subprocess.run(['sudo', 'systemctl', 'restart', 'AdGuardHome'],
                                  capture_output=True, text=True, timeout=30)

            if result.returncode == 0:
                logger.info("AdGuard Home restarted successfully")
                return True, "AdGuard Home restarted successfully"
            else:
                error_msg = result.stderr.strip() if result.stderr else "Unknown error"
                logger.error(f"Failed to restart AdGuard Home: {error_msg}")
                return False, f"Failed to restart service: {error_msg}"

        except subprocess.TimeoutExpired:
            logger.error("AdGuard restart timed out")
            return False, "Service restart timed out"
        except Exception as e:
            logger.error(f"Failed to restart AdGuard Home: {e}")
            return False, str(e)


    def get_mode_summary(self, mode: str) -> Optional[Dict]:
        """
        Get a summary of what's enabled in a specific mode.

        Returns:
            Dictionary with mode details, filter counts by category, etc.
        """
        if mode not in self.profiles.get('modes', {}):
            return None

        mode_config = self.profiles['modes'][mode]
        filters = self._get_all_filters_for_mode(mode)

        # Count filters by category
        category_counts = {}
        for filter_config in filters:
            category = filter_config.get('category', 'other')
            category_counts[category] = category_counts.get(category, 0) + 1

        return {
            'name': mode,
            'description': mode_config.get('description', ''),
            'total_filters': len(filters),
            'category_counts': category_counts,
            'adult_content_enabled': mode_config.get('adult_content', {}).get('enable', False),
            'filters': filters
        }