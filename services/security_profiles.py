#!/usr/bin/env python3

import json
import logging
import requests
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
        Determine current security mode by analyzing enabled filters.
        Returns 'balanced' as default if unable to determine.
        """
        try:
            # Get current AdGuard filters
            localhost_url = self.adguard._get_base_url(use_ip=False)
            auth = self.adguard._get_auth()
            logger.info(f"Trying to connect to AdGuard at: {localhost_url}")
            response = requests.get(f'{localhost_url}/control/filtering/status', timeout=5, auth=auth)

            logger.info(f"AdGuard filtering status response: {response.status_code}")
            if response.status_code != 200:
                logger.warning(f"Could not get filtering status: {response.status_code} - {response.text}")
                return 'balanced'

            current_filters = response.json().get('filters', [])
            enabled_urls = {f.get('url') for f in current_filters if f.get('enabled')}

            # Check which mode matches current enabled filters best
            for mode_name in ['light', 'balanced', 'maximum']:
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
        Set the security mode and update AdGuard filters accordingly.

        Args:
            mode: One of 'light', 'balanced', or 'maximum'

        Returns:
            Tuple of (success: bool, message: str)
        """
        if mode not in self.profiles.get('modes', {}):
            return False, f"Invalid security mode: {mode}"

        try:
            logger.info(f"Setting security mode to: {mode}")

            # Step 0: Check if AdGuard is accessible
            if not self._check_adguard_accessibility():
                return False, "AdGuard Home API is not accessible. Please check if AdGuard is running and properly configured."

            # Step 1: Disable all current filters
            success, message = self._disable_all_filters()
            if not success:
                return False, f"Failed to disable current filters: {message}"

            # Step 2: Enable filters for the new mode
            success, message = self._enable_filters_for_mode(mode)
            if not success:
                return False, f"Failed to enable filters for {mode}: {message}"

            # Step 3: Handle adult content filtering for maximum mode
            if mode == 'maximum':
                adult_config = self.profiles['modes'][mode].get('adult_content', {})
                if adult_config.get('enable'):
                    self._enable_adult_content_filtering()

            # Step 4: Reload AdGuard configuration
            self._reload_adguard()

            # Update current mode
            self.current_mode = mode

            logger.info(f"Successfully set security mode to: {mode}")
            return True, f"Security mode set to {mode.title()}"

        except Exception as e:
            logger.error(f"Failed to set security mode {mode}: {e}", exc_info=True)
            return False, f"Failed to set security mode: {str(e)}"

    def _check_adguard_accessibility(self) -> bool:
        """Check if AdGuard Home API is accessible."""
        try:
            localhost_url = self.adguard._get_base_url(use_ip=False)
            logger.info(f"Checking AdGuard accessibility at: {localhost_url}")

            # Try to get basic status - using auth if available
            auth = self.adguard._get_auth()
            response = requests.get(f'{localhost_url}/control/status', timeout=5, auth=auth)
            logger.info(f"AdGuard status check response: {response.status_code}")

            if response.status_code == 200:
                return True
            elif response.status_code == 401:
                logger.warning("AdGuard requires authentication - this may need manual setup")
                return False
            else:
                logger.warning(f"AdGuard returned unexpected status: {response.status_code}")
                return False

        except requests.exceptions.ConnectionError:
            logger.error("Cannot connect to AdGuard Home - service may be down")
            return False
        except Exception as e:
            logger.error(f"Error checking AdGuard accessibility: {e}")
            return False

    def _disable_all_filters(self) -> Tuple[bool, str]:
        """Disable all currently enabled filters."""
        try:
            localhost_url = self.adguard._get_base_url(use_ip=False)
            auth = self.adguard._get_auth()

            # Get current filters
            response = requests.get(f'{localhost_url}/control/filtering/status', timeout=5, auth=auth)
            if response.status_code != 200:
                return False, "Could not get current filter status"

            current_filters = response.json().get('filters', [])

            # Disable each enabled filter
            for filter_item in current_filters:
                if filter_item.get('enabled'):
                    filter_data = {
                        'url': filter_item.get('url', ''),
                        'enabled': False
                    }
                    response = requests.post(
                        f'{localhost_url}/control/filtering/set_url',
                        json=filter_data,
                        timeout=5,
                        auth=auth
                    )
                    if response.status_code != 200:
                        logger.warning(f"Failed to disable filter: {filter_item.get('name', 'Unknown')}")

            return True, "All filters disabled"

        except Exception as e:
            logger.error(f"Failed to disable filters: {e}")
            return False, str(e)

    def _enable_filters_for_mode(self, mode: str) -> Tuple[bool, str]:
        """Enable all filters required for the specified mode."""
        try:
            localhost_url = self.adguard._get_base_url(use_ip=False)
            auth = self.adguard._get_auth()
            filters = self._get_all_filters_for_mode(mode)

            enabled_count = 0
            skipped_count = 0

            for filter_config in filters:
                filter_url = filter_config.get('url')
                filter_name = filter_config.get('name', 'Unknown')

                if not filter_url:
                    # Handle catalog-only filters (requires manual intervention)
                    logger.info(f"Skipping catalog-only filter: {filter_name}")
                    skipped_count += 1
                    continue

                # Add and enable the filter
                filter_data = {
                    'url': filter_url,
                    'enabled': True,
                    'name': filter_name
                }

                response = requests.post(
                    f'{localhost_url}/control/filtering/add_url',
                    json=filter_data,
                    timeout=10,
                    auth=auth
                )

                if response.status_code == 200:
                    enabled_count += 1
                    logger.info(f"Enabled filter: {filter_name}")
                else:
                    logger.warning(f"Failed to enable filter: {filter_name}")

            message = f"Enabled {enabled_count} filters"
            if skipped_count > 0:
                message += f" ({skipped_count} catalog filters require manual setup)"

            return True, message

        except Exception as e:
            logger.error(f"Failed to enable filters for {mode}: {e}")
            return False, str(e)

    def _enable_adult_content_filtering(self) -> None:
        """Enable AdGuard's built-in adult content filtering."""
        try:
            localhost_url = self.adguard._get_base_url(use_ip=False)
            auth = self.adguard._get_auth()

            # Enable parental control
            parental_data = {'enabled': True}
            response = requests.post(
                f'{localhost_url}/control/parental/enable',
                json=parental_data,
                timeout=5,
                auth=auth
            )

            if response.status_code == 200:
                logger.info("Enabled adult content filtering")
            else:
                logger.warning("Failed to enable adult content filtering")

        except Exception as e:
            logger.error(f"Failed to enable adult content filtering: {e}")

    def _reload_adguard(self) -> None:
        """Reload AdGuard Home configuration."""
        try:
            localhost_url = self.adguard._get_base_url(use_ip=False)
            auth = self.adguard._get_auth()
            response = requests.post(f'{localhost_url}/control/filtering/refresh', timeout=10, auth=auth)

            if response.status_code == 200:
                logger.info("AdGuard configuration reloaded")
            else:
                logger.warning("Failed to reload AdGuard configuration")

        except Exception as e:
            logger.error(f"Failed to reload AdGuard: {e}")

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