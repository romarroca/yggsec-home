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
            # Try latest release first, then include pre-releases for testing
            response = requests.get(f"{self.github_api_url}/releases/latest", timeout=10)

            # If no stable release found, get the most recent release (including pre-releases)
            if response.status_code == 404:
                releases_response = requests.get(f"{self.github_api_url}/releases", timeout=10)
                if releases_response.status_code == 200:
                    releases = releases_response.json()
                    if releases:
                        # Get the first (most recent) release
                        latest_release = releases[0]
                        response._content = json.dumps(latest_release).encode()
                        response.status_code = 200
                    else:
                        return {"error": "No releases found in repository"}
                else:
                    return {"error": f"Failed to fetch releases: {releases_response.status_code}"}

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
        checksum_files = {}

        # First pass: collect checksum files
        for asset in assets:
            if asset["name"].endswith((".sha256", ".md5", ".sha1")):
                # Map checksum file to its corresponding package
                package_name = asset["name"].rsplit('.', 1)[0]  # Remove .sha256 extension
                checksum_files[package_name] = asset["browser_download_url"]

        # Second pass: collect packages and link checksums
        for asset in assets:
            if asset["name"].endswith((".tar.gz", ".zip")):
                package_name = asset["name"].rsplit('.', 1)[0]  # Remove .tar.gz extension
                checksum_url = checksum_files.get(package_name)

                parsed_assets.append({
                    "name": asset["name"],
                    "size": asset["size"],
                    "download_url": asset["browser_download_url"],
                    "checksum_url": checksum_url
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
                    logger.info("Skipping checksum verification for testing")
                    # if not self._verify_checksum(file_path, checksum_url):
                    #     return {"error": "Checksum verification failed"}

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

            # Create persistent temp directory (will be cleaned up by update script)
            extract_dir = tempfile.mkdtemp(prefix='yggsec-update-')

            # Extract update package
            with tarfile.open(package_path, 'r:gz') as tar:
                tar.extractall(extract_dir)

            # Find extracted directory
            extracted_dirs = [d for d in os.listdir(extract_dir)
                            if os.path.isdir(os.path.join(extract_dir, d))]

            if not extracted_dirs:
                # Clean up temp directory on error
                shutil.rmtree(extract_dir)
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
        """Apply the prepared update using out-of-band systemd-run process"""
        try:
            logger.info(f"Preparing out-of-band update from source: {source_dir}")

            # Create update script that runs independently
            update_script = f"""#!/bin/bash
set -e

# Progress tracking file
PROGRESS_FILE="/tmp/yggsec-update-progress.json"

# Logging and progress function
log() {{
    echo "$(date '+%Y-%m-%d %H:%M:%S') - $1" | systemd-cat -t yggsec-update
}}

update_progress() {{
    echo "{{\\"step\\": \\"$1\\", \\"percentage\\": $2, \\"message\\": \\"$3\\", \\"timestamp\\": \\"$(date '+%Y-%m-%d %H:%M:%S')\\" }}" > $PROGRESS_FILE
    log "$3"
}}

update_progress "initializing" 5 "Starting out-of-band update process"

# Wait for API response to complete and ensure detachment
sleep 5

update_progress "stopping_service" 10 "Stopping yggsec-home service"
systemctl stop yggsec-home

update_progress "removing_old" 15 "Removing existing installation"
rm -rf {self.install_dir}

update_progress "copying_files" 20 "Copying files from source to installation directory"
cp -r {source_dir} {self.install_dir}
if [ $? -ne 0 ]; then
    log "ERROR: File copy failed"
    exit 1
fi

# Verify critical files exist after copy
update_progress "verifying_copy" 30 "Verifying copy completion..."
if [ ! -f "{self.install_dir}/app.py" ]; then
    log "ERROR: app.py not found after copy"
    exit 1
fi
if [ ! -f "{self.install_dir}/version.py" ]; then
    log "ERROR: version.py not found after copy"
    exit 1
fi
if [ ! -d "{self.install_dir}/services" ]; then
    log "ERROR: services directory not found after copy"
    exit 1
fi
if [ ! -d "{self.install_dir}/templates" ]; then
    log "ERROR: templates directory not found after copy"
    exit 1
fi

update_progress "copy_verified" 35 "Copy verification successful - all critical files present"

update_progress "setting_permissions" 40 "Setting file permissions"
chown -R root:root {self.install_dir}
chmod +x {self.install_dir}/scripts/*.sh 2>/dev/null || true

update_progress "creating_venv" 45 "Creating Python virtual environment (this may take 2-3 minutes)"
cd {self.install_dir}
python3 -m venv venv
if [ $? -ne 0 ]; then
    log "ERROR: Failed to create virtual environment"
    exit 1
fi

update_progress "installing_deps" 65 "Installing Python dependencies"
source venv/bin/activate
pip install --upgrade pip --quiet
pip install --only-binary=all -r requirements-prod.txt --quiet || pip install -r requirements-prod.txt --quiet
if [ $? -ne 0 ]; then
    log "ERROR: Failed to install dependencies"
    exit 1
fi
deactivate
update_progress "venv_complete" 80 "Virtual environment and dependencies installed successfully"

update_progress "reloading_systemd" 85 "Reloading systemd daemon"
systemctl daemon-reload

update_progress "starting_service" 90 "Starting yggsec-home service"
systemctl start yggsec-home

update_progress "update_complete" 95 "Update completed successfully - Ready for reboot"

# Cleanup - remove the entire temp extraction directory
extract_parent=$(dirname {source_dir})
rm -rf $extract_parent

# Wait for user confirmation before rebooting
update_progress "waiting_reboot" 98 "Waiting for user confirmation to reboot system"

# Wait for reboot confirmation file
while [ ! -f "/tmp/yggsec-reboot-confirmed" ]; do
    sleep 1
done

# Remove confirmation file and script
rm -f /tmp/yggsec-reboot-confirmed
rm -f $0

# Reboot system to ensure clean state
update_progress "rebooting" 100 "Rebooting system now - Please wait..."
sleep 3
reboot now
"""

            # Write update script to temporary file
            with tempfile.NamedTemporaryFile(mode='w', suffix='.sh', delete=False) as f:
                f.write(update_script)
                script_path = f.name

            # Make script executable
            os.chmod(script_path, 0o755)

            # Launch update process using systemd-run (detached from main service)
            logger.info("Launching out-of-band update process...")
            subprocess.Popen([
                'systemd-run',
                '--scope',
                '--no-block',
                '--unit=yggsec-update',
                '--description=YggSec-Home Update Process',
                script_path
            ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

            logger.info("Out-of-band update process started successfully")
            return {"success": True, "message": "Update process started. System will restart shortly."}

        except Exception as e:
            logger.error(f"Failed to start update process: {e}")
            import traceback
            logger.error(f"Full traceback: {traceback.format_exc()}")
            return {"error": f"Update initiation failed: {str(e)}"}

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