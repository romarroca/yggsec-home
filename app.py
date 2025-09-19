#!/usr/bin/env python3

import os
import logging
import bcrypt
from datetime import datetime
from flask import Flask, render_template, request, jsonify, redirect, url_for, flash, session
from werkzeug.utils import secure_filename
from werkzeug.security import check_password_hash, generate_password_hash
from functools import wraps
from pathlib import Path
from flask_wtf.csrf import CSRFProtect
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

from config import Config, validate_ip_address, validate_network_mask
from services.network import NetworkManager
from services.adguard import AdGuardManager
from services.wireguard import WireGuardManager
from services.system import SystemManager
from services.security_profiles import SecurityProfileManager

def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)

    # Initialize configuration
    Config.init_app(app)

    # Ensure nginx log directory and files exist (for system integration)
    try:
        import os
        import subprocess
        nginx_log_dir = "/var/log/nginx"
        if not os.path.exists(nginx_log_dir):
            os.makedirs(nginx_log_dir, mode=0o750, exist_ok=True)

        # Create log files if they don't exist
        error_log = os.path.join(nginx_log_dir, "error.log")
        access_log = os.path.join(nginx_log_dir, "access.log")

        for log_file in [error_log, access_log]:
            if not os.path.exists(log_file):
                open(log_file, 'a').close()

        # Set proper permissions
        try:
            subprocess.run(['chown', '-R', 'www-data:adm', nginx_log_dir],
                         capture_output=True, check=False)
            subprocess.run(['chmod', '750', nginx_log_dir],
                         capture_output=True, check=False)
            subprocess.run(['chmod', '640', error_log, access_log],
                         capture_output=True, check=False)
        except:
            pass  # Ignore permission errors
    except Exception:
        pass  # Don't fail app startup if nginx log setup fails

    # Initialize CSRF protection
    csrf = CSRFProtect(app)

    # Initialize rate limiting
    limiter = Limiter(
        app=app,
        key_func=get_remote_address,
        default_limits=["100 per hour"],
        storage_uri="memory://"
    )

    # Security headers
    @app.after_request
    def security_headers(response):
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['X-Frame-Options'] = 'DENY'
        response.headers['X-XSS-Protection'] = '1; mode=block'
        response.headers['Strict-Transport-Security'] = 'max-age=31536000; includeSubDomains'
        response.headers['Content-Security-Policy'] = (
            "default-src 'self'; "
            "script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
            "style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
            "font-src 'self' https://cdn.jsdelivr.net; "
            "img-src 'self' data:; "
            "connect-src 'self'"
        )
        return response

    # Session timeout
    @app.before_request
    def session_timeout():
        session.permanent = True
        app.permanent_session_lifetime = Config.SESSION_TIMEOUT

    # Setup logging
    log_level = logging.DEBUG if app.config['DEBUG'] else logging.INFO
    logging.basicConfig(
        level=log_level,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler(Config.LOG_DIR / 'yggsec-home.log'),
            logging.StreamHandler()
        ]
    )

    # Initialize service managers
    network_mgr = NetworkManager(Config.NETWORK_INTERFACE)
    adguard_mgr = AdGuardManager(Config.ADGUARD_PORT, Config.ADGUARD_USERNAME, Config.ADGUARD_PASSWORD)
    wireguard_mgr = WireGuardManager(Config.WG_INTERFACE, Config.WG_CONF_DIR)
    system_mgr = SystemManager()
    security_mgr = SecurityProfileManager(adguard_mgr)

    # Initialize update manager
    from services.updater import UpdateManager
    update_mgr = UpdateManager()

    # Initialize background scheduler
    from services.scheduler import BackgroundScheduler
    scheduler = BackgroundScheduler()

    # Add periodic update check (daily at startup, then every 24 hours)
    def check_updates_background():
        """Background update check - logs results but doesn't interrupt user"""
        try:
            result = update_mgr.check_for_updates()
            if result.get('status') == 'update_available':
                app.logger.info(f"Update available: {result.get('current_version')} -> {result.get('latest_version')}")
                # Store update status for UI to display notification
                app.config['UPDATE_AVAILABLE'] = result
            elif result.get('status') == 'up_to_date':
                app.logger.info("System is up to date")
                app.config['UPDATE_AVAILABLE'] = None
            else:
                app.logger.info(f"Update check result: {result.get('status', 'unknown')}")
        except Exception as e:
            app.logger.error(f"Background update check failed: {e}")

    # Schedule daily update checks
    scheduler.add_task(check_updates_background, interval_hours=24, run_immediately=True)
    scheduler.start()

    # Graceful shutdown handler
    import atexit
    atexit.register(lambda: scheduler.stop())

    # Default admin credentials (configured during installation)
    DEFAULT_USERNAME = os.environ.get('ADMIN_USERNAME', 'yggsec')
    DEFAULT_PASSWORD_HASH = os.environ.get('ADMIN_PASSWORD_HASH',
                                          bcrypt.hashpw('yggsec-admin'.encode('utf-8'), bcrypt.gensalt()).decode('utf-8'))

    def login_required(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if 'logged_in' not in session:
                return redirect(url_for('login'))
            return f(*args, **kwargs)
        return decorated_function

    @app.route('/login', methods=['GET', 'POST'])
    @limiter.limit("5 per minute")
    def login():
        """Login page"""
        if request.method == 'POST':
            username = request.form.get('username', '').strip()
            password = request.form.get('password', '')

            # Simple authentication (in production, use proper user management)
            if username == DEFAULT_USERNAME:
                # Check if we have bcrypt hash or werkzeug hash
                if DEFAULT_PASSWORD_HASH.startswith('$2a$') or DEFAULT_PASSWORD_HASH.startswith('$2b$'):
                    # BCrypt hash from installation
                    if bcrypt.checkpw(password.encode('utf-8'), DEFAULT_PASSWORD_HASH.encode('utf-8')):
                        session['logged_in'] = True
                        session['username'] = username
                        flash('Login successful', 'success')
                        return redirect(url_for('dashboard'))
                    else:
                        flash('Invalid username or password', 'error')
                else:
                    # Fallback to werkzeug hash
                    if check_password_hash(DEFAULT_PASSWORD_HASH, password):
                        session['logged_in'] = True
                        session['username'] = username
                        flash('Login successful', 'success')
                        return redirect(url_for('dashboard'))
                    else:
                        flash('Invalid username or password', 'error')
            else:
                flash('Invalid username or password', 'error')

        return render_template('login.html')

    @app.route('/logout')
    def logout():
        """Logout"""
        session.clear()
        flash('You have been logged out', 'info')
        return redirect(url_for('login'))

    @app.route('/')
    @login_required
    def dashboard():
        """Main dashboard - AdGuard statistics"""
        try:
            return render_template('dashboard.html')
        except Exception as e:
            app.logger.error(f"Dashboard error: {e}")
            flash(f"Error loading dashboard: {str(e)}", 'error')
            return render_template('dashboard.html')

    @app.route('/settings')
    @login_required
    def settings():
        """Settings page - system configuration"""
        try:
            # Get status from all services
            network_status = network_mgr.get_current_config()
            adguard_status = adguard_mgr.get_service_status()
            wireguard_status = wireguard_mgr.get_connection_status()
            system_info = system_mgr.get_system_info()

            return render_template('settings.html',
                                 network=network_status,
                                 adguard=adguard_status,
                                 wireguard=wireguard_status,
                                 system=system_info)

        except Exception as e:
            app.logger.error(f"Settings error: {e}")
            flash(f"Error loading settings: {str(e)}", 'error')
            return render_template('settings.html',
                                 network=None, adguard=None,
                                 wireguard=None, system=None)


    # Network Management Routes
    @app.route('/api/network/status')
    @login_required
    def network_status():
        """Get current network configuration"""
        try:
            config = network_mgr.get_current_config()
            interface_status = network_mgr.get_interface_status()

            return jsonify({
                'success': True,
                'config': config,
                'interface': interface_status
            })
        except Exception as e:
            app.logger.error(f"Network status error: {e}")
            return jsonify({'success': False, 'error': str(e)}), 500

    @app.route('/api/network/debug')
    @login_required
    def network_debug():
        """Debug network configuration"""
        try:
            config = network_mgr.get_current_config()
            interface_status = network_mgr.get_interface_status()
            dhcpcd_status = network_mgr.get_dhcpcd_config_status()

            return jsonify({
                'success': True,
                'config': config,
                'interface': interface_status,
                'dhcpcd': dhcpcd_status
            })
        except Exception as e:
            app.logger.error(f"Network debug error: {e}")
            return jsonify({'success': False, 'error': str(e)}), 500

    @app.route('/api/network/configure', methods=['POST'])
    @login_required
    @limiter.limit("10 per minute")
    def configure_network():
        """Configure network settings"""
        try:
            data = request.get_json()
            mode = data.get('mode', 'dhcp')

            if mode == 'dhcp':
                success = network_mgr.set_dhcp_config()
                if success:
                    return jsonify({'success': True, 'message': 'DHCP configuration applied'})
                else:
                    return jsonify({'success': False, 'error': 'Failed to set DHCP configuration'}), 500

            elif mode == 'static':
                ip_address = data.get('ip_address', '').strip()
                netmask = data.get('netmask', '').strip()
                gateway = data.get('gateway', '').strip()
                dns_servers = [dns.strip() for dns in data.get('dns_servers', []) if dns.strip()]

                # Validate inputs
                if not validate_ip_address(ip_address):
                    return jsonify({'success': False, 'error': 'Invalid IP address'}), 400

                if not validate_network_mask(netmask):
                    return jsonify({'success': False, 'error': 'Invalid network mask'}), 400

                if not validate_ip_address(gateway):
                    return jsonify({'success': False, 'error': 'Invalid gateway address'}), 400

                for dns in dns_servers:
                    if not validate_ip_address(dns):
                        return jsonify({'success': False, 'error': f'Invalid DNS server: {dns}'}), 400

                if not dns_servers:
                    dns_servers = ['8.8.8.8', '8.8.4.4']  # Default to Google DNS

                success = network_mgr.set_static_config(ip_address, netmask, gateway, dns_servers)
                if success:
                    return jsonify({'success': True, 'message': 'Static network configuration applied'})
                else:
                    return jsonify({'success': False, 'error': 'Failed to set static configuration'}), 500

            else:
                return jsonify({'success': False, 'error': 'Invalid network mode'}), 400

        except Exception as e:
            app.logger.error(f"Network configuration error: {e}")
            return jsonify({'success': False, 'error': str(e)}), 500

    # AdGuard Home Routes
    @app.route('/api/adguard/status')
    def adguard_status():
        """Get AdGuard Home status"""
        try:
            status = adguard_mgr.get_service_status()
            return jsonify({'success': True, 'status': status})
        except Exception as e:
            app.logger.error(f"AdGuard status error: {e}")
            return jsonify({'success': False, 'error': str(e)}), 500

    @app.route('/api/adguard/control', methods=['POST'])
    @login_required
    @limiter.limit("10 per minute")
    def control_adguard():
        """Control AdGuard Home service"""
        try:
            data = request.get_json()
            action = data.get('action')

            if action == 'start':
                success = adguard_mgr.start_service()
                message = 'AdGuard Home started' if success else 'Failed to start AdGuard Home'
            elif action == 'stop':
                success = adguard_mgr.stop_service()
                message = 'AdGuard Home stopped' if success else 'Failed to stop AdGuard Home'
            elif action == 'restart':
                success = adguard_mgr.restart_service()
                message = 'AdGuard Home restarted' if success else 'Failed to restart AdGuard Home'
            elif action == 'enable':
                success = adguard_mgr.enable_service()
                message = 'AdGuard Home enabled' if success else 'Failed to enable AdGuard Home'
            elif action == 'disable':
                success = adguard_mgr.disable_service()
                message = 'AdGuard Home disabled' if success else 'Failed to disable AdGuard Home'
            else:
                return jsonify({'success': False, 'error': 'Invalid action'}), 400

            return jsonify({'success': success, 'message': message})

        except Exception as e:
            app.logger.error(f"AdGuard control error: {e}")
            return jsonify({'success': False, 'error': str(e)}), 500

    # AdGuard Statistics Routes
    @app.route('/api/adguard/stats')
    def adguard_stats():
        """Get AdGuard statistics"""
        try:
            stats = adguard_mgr.get_stats()
            stats_info = adguard_mgr.get_stats_info()
            return jsonify({
                'success': True,
                'stats': stats,
                'stats_info': stats_info
            })
        except Exception as e:
            app.logger.error(f"AdGuard stats error: {e}")
            return jsonify({'success': False, 'error': str(e)}), 500

    @app.route('/api/adguard/top-domains')
    def adguard_top_domains():
        """Get top queried and blocked domains"""
        try:
            top_queried = adguard_mgr.get_top_queried_domains()
            top_blocked = adguard_mgr.get_top_blocked_domains()
            return jsonify({
                'success': True,
                'top_queried': top_queried,
                'top_blocked': top_blocked
            })
        except Exception as e:
            app.logger.error(f"AdGuard top domains error: {e}")
            return jsonify({'success': False, 'error': str(e)}), 500

    @app.route('/api/adguard/top-clients')
    def adguard_top_clients():
        """Get top clients"""
        try:
            top_clients = adguard_mgr.get_top_clients()
            return jsonify({
                'success': True,
                'top_clients': top_clients
            })
        except Exception as e:
            app.logger.error(f"AdGuard top clients error: {e}")
            return jsonify({'success': False, 'error': str(e)}), 500

    @app.route('/api/adguard/query-log')
    def adguard_query_log():
        """Get recent query log"""
        try:
            limit = request.args.get('limit', 50, type=int)
            older_than = request.args.get('older_than', None)
            query_log = adguard_mgr.get_query_log(older_than=older_than, limit=limit)
            return jsonify({
                'success': True,
                'query_log': query_log
            })
        except Exception as e:
            app.logger.error(f"AdGuard query log error: {e}")
            return jsonify({'success': False, 'error': str(e)}), 500

    # Security Profile Routes
    @app.route('/api/security/modes')
    def get_security_modes():
        """Get all available security modes"""
        try:
            modes = security_mgr.get_available_modes()
            current_mode = security_mgr.get_current_mode()

            return jsonify({
                'success': True,
                'modes': modes,
                'current_mode': current_mode
            })
        except Exception as e:
            app.logger.error(f"Security modes error: {e}")
            return jsonify({'success': False, 'error': str(e)}), 500

    @app.route('/api/security/mode', methods=['POST'])
    @login_required
    @limiter.limit("3 per minute")
    def set_security_mode():
        """Set the security mode"""
        try:
            data = request.get_json()
            mode = data.get('mode')

            if not mode:
                return jsonify({'success': False, 'error': 'Mode is required'}), 400

            if mode not in ['light', 'balanced', 'maximum']:
                return jsonify({'success': False, 'error': 'Invalid mode'}), 400

            success, message = security_mgr.set_security_mode(mode)

            return jsonify({
                'success': success,
                'message': message,
                'current_mode': security_mgr.get_current_mode()
            })

        except Exception as e:
            app.logger.error(f"Set security mode error: {e}")
            return jsonify({'success': False, 'error': str(e)}), 500

    @app.route('/api/security/mode/<mode>/summary')
    def get_mode_summary(mode):
        """Get detailed summary of a security mode"""
        try:
            summary = security_mgr.get_mode_summary(mode)

            if summary is None:
                return jsonify({'success': False, 'error': 'Invalid mode'}), 400

            return jsonify({
                'success': True,
                'summary': summary
            })
        except Exception as e:
            app.logger.error(f"Mode summary error: {e}")
            return jsonify({'success': False, 'error': str(e)}), 500

    # WireGuard Routes
    @app.route('/api/wireguard/status')
    def wireguard_status():
        """Get WireGuard status"""
        try:
            status = wireguard_mgr.get_connection_status()
            return jsonify({'success': True, 'status': status})
        except Exception as e:
            app.logger.error(f"WireGuard status error: {e}")
            return jsonify({'success': False, 'error': str(e)}), 500

    @app.route('/api/wireguard/upload', methods=['POST'])
    @login_required
    @limiter.limit("5 per minute")
    def upload_wireguard_config():
        """Upload WireGuard configuration file"""
        try:
            if 'config_file' not in request.files:
                return jsonify({'success': False, 'error': 'No file uploaded'}), 400

            file = request.files['config_file']
            if file.filename == '':
                return jsonify({'success': False, 'error': 'No file selected'}), 400

            # Validate file extension
            if not file.filename.lower().endswith('.conf'):
                return jsonify({'success': False, 'error': 'Only .conf files are allowed'}), 400

            # Check file size (Flask also has this but let's be explicit)
            file.seek(0, 2)  # Seek to end
            file_size = file.tell()
            file.seek(0)     # Reset to beginning

            if file_size > 10240:  # 10KB limit
                return jsonify({'success': False, 'error': 'File too large (max 10KB)'}), 400

            if file_size == 0:
                return jsonify({'success': False, 'error': 'File is empty'}), 400

            # Read and validate content
            try:
                content = file.read().decode('utf-8')
            except UnicodeDecodeError:
                return jsonify({'success': False, 'error': 'File must be valid UTF-8 text'}), 400

            success, message = wireguard_mgr.upload_config(content)
            return jsonify({'success': success, 'message': message})

        except Exception as e:
            app.logger.error(f"WireGuard upload error: {e}")
            return jsonify({'success': False, 'error': str(e)}), 500

    @app.route('/api/wireguard/config', methods=['GET'])
    @login_required
    def get_wireguard_config():
        """Get current WireGuard configuration"""
        try:
            config_content = wireguard_mgr.get_config_content()
            if config_content is not None:
                return jsonify({'success': True, 'config': config_content})
            else:
                return jsonify({'success': False, 'error': 'No configuration found'}), 404

        except Exception as e:
            app.logger.error(f"WireGuard config get error: {e}")
            return jsonify({'success': False, 'error': str(e)}), 500

    @app.route('/api/wireguard/save', methods=['POST'])
    @login_required
    @limiter.limit("5 per minute")
    def save_wireguard_config():
        """Save edited WireGuard configuration"""
        try:
            data = request.get_json()
            config_content = data.get('config', '').strip()

            if not config_content:
                return jsonify({'success': False, 'error': 'Configuration content is required'}), 400

            success, message = wireguard_mgr.upload_config(config_content)
            return jsonify({'success': success, 'message': message})

        except Exception as e:
            app.logger.error(f"WireGuard config save error: {e}")
            return jsonify({'success': False, 'error': str(e)}), 500

    @app.route('/api/wireguard/control', methods=['POST'])
    @login_required
    @limiter.limit("10 per minute")
    def control_wireguard():
        """Control WireGuard tunnel"""
        try:
            data = request.get_json()
            action = data.get('action')

            if action == 'start':
                success, message = wireguard_mgr.start_tunnel()
            elif action == 'stop':
                success, message = wireguard_mgr.stop_tunnel()
            elif action == 'restart':
                success, message = wireguard_mgr.restart_tunnel()
            elif action == 'delete':
                success, message = wireguard_mgr.delete_config()
            else:
                return jsonify({'success': False, 'error': 'Invalid action'}), 400

            return jsonify({'success': success, 'message': message})

        except Exception as e:
            app.logger.error(f"WireGuard control error: {e}")
            return jsonify({'success': False, 'error': str(e)}), 500

    # System Management Routes
    @app.route('/api/system/info')
    def system_info():
        """Get system information"""
        try:
            info = system_mgr.get_system_info()
            return jsonify({'success': True, 'info': info})
        except Exception as e:
            app.logger.error(f"System info error: {e}")
            return jsonify({'success': False, 'error': str(e)}), 500

    @app.route('/api/system/control', methods=['POST'])
    @login_required
    @limiter.limit("3 per minute")
    def control_system():
        """Control system operations"""
        try:
            data = request.get_json()
            action = data.get('action')

            if action == 'reboot':
                success, message = system_mgr.reboot_system()
            elif action == 'shutdown':
                success, message = system_mgr.shutdown_system()
            elif action == 'update':
                success, message = system_mgr.update_system()
            else:
                return jsonify({'success': False, 'error': 'Invalid action'}), 400

            return jsonify({'success': success, 'message': message})

        except Exception as e:
            app.logger.error(f"System control error: {e}")
            return jsonify({'success': False, 'error': str(e)}), 500

    @app.route('/api/system/password', methods=['POST'])
    @login_required
    @limiter.limit("3 per minute")
    def change_password():
        """Change admin password"""
        try:
            data = request.get_json()
            new_password = data.get('new_password', '').strip()

            if not new_password:
                return jsonify({'success': False, 'error': 'Password cannot be empty'}), 400

            success, message = system_mgr.change_admin_password(new_password)
            return jsonify({'success': success, 'message': message})

        except Exception as e:
            app.logger.error(f"Password change error: {e}")
            return jsonify({'success': False, 'error': str(e)}), 500

    @app.route('/api/system/generate-password')
    def generate_password():
        """Generate a secure password"""
        try:
            password = system_mgr.generate_secure_password()
            return jsonify({'success': True, 'password': password})
        except Exception as e:
            app.logger.error(f"Password generation error: {e}")
            return jsonify({'success': False, 'error': str(e)}), 500

    # Update Management API
    @app.route('/api/system/update/check')
    def check_updates():
        """Check for available updates"""
        try:
            update_info = update_mgr.check_for_updates()
            return jsonify(update_info)
        except Exception as e:
            app.logger.error(f"Update check error: {e}")
            return jsonify({'error': str(e)}), 500

    @app.route('/api/system/update/download', methods=['POST'])
    def download_update():
        """Download update package"""
        try:
            data = request.get_json()
            app.logger.info(f"Download request data: {data}")

            if not data:
                app.logger.error("No JSON data received")
                return jsonify({'error': 'No data provided'}), 400

            download_url = data.get('download_url')
            checksum_url = data.get('checksum_url')

            app.logger.info(f"Download URL: {download_url}")
            app.logger.info(f"Checksum URL: {checksum_url}")

            if not download_url:
                app.logger.error("Download URL is missing")
                return jsonify({'error': 'Download URL required'}), 400

            result = update_mgr.download_update(download_url, checksum_url)
            return jsonify(result)
        except Exception as e:
            app.logger.error(f"Update download error: {e}")
            return jsonify({'error': str(e)}), 500

    @app.route('/api/system/update/apply', methods=['POST'])
    def apply_update():
        """Apply downloaded update"""
        try:
            data = request.get_json()
            source_dir = data.get('source_dir')

            if not source_dir:
                return jsonify({'error': 'Source directory required'}), 400

            result = update_mgr.apply_update(source_dir)
            return jsonify(result)
        except Exception as e:
            app.logger.error(f"Update apply error: {e}")
            return jsonify({'error': str(e)}), 500

    @app.route('/api/system/update/rollback', methods=['POST'])
    def rollback_update():
        """Rollback to previous version"""
        try:
            result = update_mgr.rollback_update()
            return jsonify(result)
        except Exception as e:
            app.logger.error(f"Update rollback error: {e}")
            return jsonify({'error': str(e)}), 500

    @app.route('/api/system/update/status')
    def update_status():
        """Get update status"""
        try:
            status = update_mgr.get_update_status()
            return jsonify(status)
        except Exception as e:
            app.logger.error(f"Update status error: {e}")
            return jsonify({'error': str(e)}), 500

    @app.route('/api/system/update/progress')
    def update_progress():
        """Get current update progress"""
        try:
            import json
            import os
            progress_file = "/tmp/yggsec-update-progress.json"

            if os.path.exists(progress_file):
                with open(progress_file, 'r') as f:
                    progress_data = json.load(f)
                return jsonify({
                    'success': True,
                    'progress': progress_data
                })
            else:
                return jsonify({
                    'success': True,
                    'progress': {
                        'step': 'idle',
                        'percentage': 0,
                        'message': 'No update in progress',
                        'timestamp': ''
                    }
                })
        except Exception as e:
            app.logger.error(f"Update progress error: {e}")
            return jsonify({'error': str(e)}), 500

    @app.route('/api/system/update/confirm-reboot', methods=['POST'])
    def confirm_reboot():
        """Confirm system reboot after update"""
        try:
            # Create confirmation file for update script
            with open('/tmp/yggsec-reboot-confirmed', 'w') as f:
                f.write('confirmed')

            return jsonify({
                'success': True,
                'message': 'Reboot confirmation sent'
            })
        except Exception as e:
            app.logger.error(f"Reboot confirmation error: {e}")
            return jsonify({'error': str(e)}), 500

    @app.route('/api/system/update/upload', methods=['POST'])
    def upload_firmware():
        """Upload local firmware file"""
        try:
            if 'firmware_file' not in request.files:
                return jsonify({'error': 'No firmware file provided'}), 400

            file = request.files['firmware_file']
            if file.filename == '':
                return jsonify({'error': 'No file selected'}), 400

            # Validate file type
            if not (file.filename.endswith('.tar.gz') or file.filename.endswith('.tgz')):
                return jsonify({'error': 'Invalid file type. Only .tar.gz files are supported'}), 400

            # Save uploaded file
            import tempfile
            import os
            with tempfile.NamedTemporaryFile(delete=False, suffix='.tar.gz') as temp_file:
                file.save(temp_file.name)
                temp_file_path = temp_file.name

            # Process uploaded firmware
            result = update_mgr._prepare_update(temp_file_path)

            # Clean up temp file
            os.unlink(temp_file_path)

            return jsonify(result)
        except Exception as e:
            app.logger.error(f"Firmware upload error: {e}")
            return jsonify({'error': str(e)}), 500

    @app.errorhandler(413)
    def too_large(e):
        return jsonify({'success': False, 'error': 'File too large'}), 413

    @app.errorhandler(404)
    def not_found(e):
        return render_template('404.html'), 404

    @app.errorhandler(500)
    def internal_error(e):
        app.logger.error(f"Internal error: {e}")
        return render_template('500.html'), 500

    return app

if __name__ == '__main__':
    app = create_app()
    app.run(
        host=Config.BIND_HOST,
        port=Config.BIND_PORT,
        debug=Config.DEBUG
    )