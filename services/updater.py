import os
import json
import hashlib
import logging
import requests
import subprocess
import tempfile
from pathlib import Path
from version import VERSION, compare_versions

logger = logging.getLogger(__name__)

class UpdateManager:
    def __init__(self, repo_owner="romarroca", repo_name="yggsec-home"):
        self.repo_owner = repo_owner
        self.repo_name = repo_name
        self.github_api_url = f"https://api.github.com/repos/{repo_owner}/{repo_name}"
        self.current_version = VERSION
        self.install_dir = "/opt/yggsec-home"
        self.backup_dir = "/opt/yggsec-home-backup"

    def check_for_updates(self):
        """Check GitHub for latest release"""
        try:
            logger.info("Checking for updates...")
            response = requests.get(f"{self.github_api_url}/releases/latest", timeout=10)

            if response.status_code != 200:
                return {"error": f"GitHub API error: {response.status_code}"}

            release_data = response.json()
            latest_version = release_data.get("tag_name", "").replace('v', '')

            if not latest_version:
                return {"error": "Could not determine latest version"}

            status = compare_versions(self.current_version, latest_version)

            return {
                "current_version": self.current_version,
                "latest_version": latest_version,
                "status": status,
                "release_notes": release_data.get("body", ""),
                "release_url": release_data.get("html_url", ""),
                "published_at": release_data.get("published_at", ""),
                "assets": self._parse_assets(release_data.get("assets", []))
            }

        except requests.RequestException as e:
            logger.error(f"Network error checking for updates: {e}")
            return {"error": f"Network error: {str(e)}"}
        except Exception as e:
            logger.error(f"Error checking for updates: {e}")
            return {"error": f"Update check failed: {str(e)}"}

    def _parse_assets(self, assets):
        """Parse release assets for update packages"""
        parsed_assets = []
        for asset in assets:
            if asset["name"].endswith((".tar.gz", ".zip")):
                parsed_assets.append({
                    "name": asset["name"],
                    "size": asset["size"],
                    "download_url": asset["browser_download_url"],
                    "checksum_url": None  # Will be populated if checksum file exists
                })
        return parsed_assets

    def download_update(self, download_url, checksum_url=None):
        """Download and verify update package"""
        try:
            logger.info(f"Downloading update from {download_url}")

            # Create temporary directory for download
            with tempfile.TemporaryDirectory() as temp_dir:
                filename = os.path.basename(download_url)
                file_path = os.path.join(temp_dir, filename)

                # Download update package
                response = requests.get(download_url, stream=True, timeout=30)
                response.raise_for_status()

                with open(file_path, 'wb') as f:
                    for chunk in response.iter_content(chunk_size=8192):
                        f.write(chunk)

                # Verify checksum if provided
                if checksum_url:
                    if not self._verify_checksum(file_path, checksum_url):
                        return {"error": "Checksum verification failed"}

                # Extract and prepare update
                return self._prepare_update(file_path)

        except Exception as e:
            logger.error(f"Download failed: {e}")
            return {"error": f"Download failed: {str(e)}"}

    def _verify_checksum(self, file_path, checksum_url):
        """Verify downloaded file checksum"""
        try:
            # Download checksum file
            response = requests.get(checksum_url, timeout=10)
            expected_checksum = response.text.strip().split()[0]

            # Calculate actual checksum
            sha256_hash = hashlib.sha256()
            with open(file_path, "rb") as f:
                for chunk in iter(lambda: f.read(4096), b""):
                    sha256_hash.update(chunk)
            actual_checksum = sha256_hash.hexdigest()

            return actual_checksum == expected_checksum

        except Exception as e:
            logger.error(f"Checksum verification failed: {e}")
            return False

    def _prepare_update(self, package_path):
        """Extract and prepare update package"""
        try:
            import tarfile
            import shutil

            # Create backup of current installation
            if os.path.exists(self.install_dir):
                if os.path.exists(self.backup_dir):
                    shutil.rmtree(self.backup_dir)
                shutil.copytree(self.install_dir, self.backup_dir)
                logger.info(f"Backup created at {self.backup_dir}")

            # Extract update package
            with tempfile.TemporaryDirectory() as extract_dir:
                with tarfile.open(package_path, 'r:gz') as tar:
                    tar.extractall(extract_dir)

                # Find extracted directory
                extracted_dirs = [d for d in os.listdir(extract_dir)
                                if os.path.isdir(os.path.join(extract_dir, d))]

                if not extracted_dirs:
                    return {"error": "Invalid update package structure"}

                source_dir = os.path.join(extract_dir, extracted_dirs[0])

                return {
                    "success": True,
                    "source_dir": source_dir,
                    "backup_created": True
                }

        except Exception as e:
            logger.error(f"Update preparation failed: {e}")
            return {"error": f"Update preparation failed: {str(e)}"}

    def apply_update(self, source_dir):
        """Apply the prepared update"""
        try:
            import shutil

            logger.info("Applying update...")

            # Stop services
            subprocess.run(['systemctl', 'stop', 'yggsec-home'], check=False)

            # Copy new files
            if os.path.exists(self.install_dir):
                shutil.rmtree(self.install_dir)
            shutil.copytree(source_dir, self.install_dir)

            # Set permissions
            subprocess.run(['chown', '-R', 'root:root', self.install_dir], check=False)
            subprocess.run(['chmod', '+x', f'{self.install_dir}/scripts/*.sh'],
                         shell=True, check=False)

            # Update systemd services
            subprocess.run(['systemctl', 'daemon-reload'], check=False)

            # Start services
            subprocess.run(['systemctl', 'start', 'yggsec-home'], check=False)

            logger.info("Update applied successfully")
            return {"success": True, "message": "Update applied successfully"}

        except Exception as e:
            logger.error(f"Update application failed: {e}")
            # Attempt rollback
            return self.rollback_update()

    def rollback_update(self):
        """Rollback to previous version"""
        try:
            import shutil

            logger.info("Rolling back update...")

            if not os.path.exists(self.backup_dir):
                return {"error": "No backup available for rollback"}

            # Stop services
            subprocess.run(['systemctl', 'stop', 'yggsec-home'], check=False)

            # Restore backup
            if os.path.exists(self.install_dir):
                shutil.rmtree(self.install_dir)
            shutil.copytree(self.backup_dir, self.install_dir)

            # Restart services
            subprocess.run(['systemctl', 'start', 'yggsec-home'], check=False)

            logger.info("Rollback completed successfully")
            return {"success": True, "message": "Rollback completed successfully"}

        except Exception as e:
            logger.error(f"Rollback failed: {e}")
            return {"error": f"Rollback failed: {str(e)}"}

    def get_update_status(self):
        """Get current update status"""
        return {
            "current_version": self.current_version,
            "install_dir": self.install_dir,
            "backup_exists": os.path.exists(self.backup_dir),
            "services_running": self._check_services_status()
        }

    def _check_services_status(self):
        """Check if YggSec-Home services are running"""
        try:
            result = subprocess.run(['systemctl', 'is-active', 'yggsec-home'],
                                  capture_output=True, text=True)
            return result.stdout.strip() == 'active'
        except:
            return False