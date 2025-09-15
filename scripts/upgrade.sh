#!/bin/bash
# YggSec-Home Upgrade Script for DietPi

set -e

# Colors for output
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

INSTALL_DIR="/opt/yggsec-home"

log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

log_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

check_root() {
    if [[ $EUID -ne 0 ]]; then
        log_error "This script must be run as root (use sudo)"
        exit 1
    fi
}

backup_config() {
    log_info "Creating backup of current configuration..."

    if [[ -d "$INSTALL_DIR" ]]; then
        cp -r "$INSTALL_DIR/logs" "/tmp/yggsec-home-logs-backup-$(date +%Y%m%d-%H%M%S)" 2>/dev/null || true
        cp -r "$INSTALL_DIR/uploads" "/tmp/yggsec-home-uploads-backup-$(date +%Y%m%d-%H%M%S)" 2>/dev/null || true
        log_success "Configuration backed up to /tmp/"
    fi
}

stop_services() {
    log_info "Stopping YggSec-Home services..."
    systemctl stop yggsec-home.service || true
}

update_code() {
    log_info "Updating YggSec-Home code..."

    cd "$INSTALL_DIR"
    git fetch origin
    git pull origin main

    log_success "Code updated"
}

update_dependencies() {
    log_info "Updating Python dependencies..."

    cd "$INSTALL_DIR"
    ./venv/bin/pip install --upgrade pip
    ./venv/bin/pip install -r requirements.txt --upgrade

    log_success "Dependencies updated"
}

update_services() {
    log_info "Updating systemd services..."

    # Check if service files have changed
    if ! cmp -s "systemd/yggsec-home.service" "/etc/systemd/system/yggsec-home.service"; then
        log_info "Service file updated, installing new version..."

        # Preserve SECRET_KEY if it exists
        SECRET_KEY=$(grep "SECRET_KEY=" /etc/systemd/system/yggsec-home.service | cut -d'=' -f2- | head -n1)

        cp systemd/yggsec-home.service /etc/systemd/system/

        if [[ -n "$SECRET_KEY" && "$SECRET_KEY" != "change-this-in-production" ]]; then
            sed -i "s/SECRET_KEY=change-this-in-production/SECRET_KEY=$SECRET_KEY/" /etc/systemd/system/yggsec-home.service
        fi

        systemctl daemon-reload
        log_success "Service files updated"
    fi
}

start_services() {
    log_info "Starting YggSec-Home services..."

    systemctl start yggsec-home.service

    # Wait for service to start
    sleep 3

    if systemctl is-active --quiet yggsec-home.service; then
        log_success "YggSec-Home service started successfully"
    else
        log_error "Failed to start YggSec-Home service"
        systemctl status yggsec-home.service
        exit 1
    fi
}

show_status() {
    echo
    log_success "YggSec-Home upgrade completed!"
    echo

    # Show version info if available
    cd "$INSTALL_DIR"
    if [[ -f ".git/refs/heads/main" ]]; then
        COMMIT=$(git rev-parse --short HEAD)
        log_info "Updated to commit: $COMMIT"
    fi

    # Show service status
    systemctl status yggsec-home.service --no-pager -l

    echo
    log_info "Access your YggSec-Home interface at:"
    IP_ADDRESS=$(hostname -I | awk '{print $1}')
    echo "  http://$IP_ADDRESS:5000"
    echo "  http://yggsec-home.local:5000"
}

main() {
    echo "=================================================="
    echo "  YggSec-Home Upgrade Script"
    echo "=================================================="
    echo

    check_root

    if [[ ! -d "$INSTALL_DIR" ]]; then
        log_error "YggSec-Home installation not found at $INSTALL_DIR"
        log_info "Please run the installation script first"
        exit 1
    fi

    backup_config
    stop_services
    update_code
    update_dependencies
    update_services
    start_services
    show_status
}

trap 'log_error "Upgrade failed at line $LINENO"' ERR

main "$@"