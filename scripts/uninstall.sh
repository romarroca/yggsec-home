#!/bin/bash
# YggSec-Home Uninstall Script for DietPi

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

confirm_uninstall() {
    echo "=================================================="
    echo "  YggSec-Home Uninstall Script"
    echo "=================================================="
    echo
    log_warning "This will completely remove YggSec-Home from your system"
    echo
    echo "The following will be removed:"
    echo "  - YggSec-Home application files"
    echo "  - Systemd services"
    echo "  - Firewall rules"
    echo "  - Log files and uploads"
    echo
    echo "The following will NOT be removed:"
    echo "  - AdGuard Home (if installed)"
    echo "  - WireGuard system packages"
    echo "  - Python packages"
    echo
    read -p "Are you sure you want to continue? (y/N): " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        log_info "Uninstall cancelled"
        exit 0
    fi
}

stop_and_disable_services() {
    log_info "Stopping and disabling YggSec-Home services..."

    # Stop services
    systemctl stop yggsec-home.service 2>/dev/null || true
    systemctl stop yggsec-home-firewall.service 2>/dev/null || true

    # Disable services
    systemctl disable yggsec-home.service 2>/dev/null || true
    systemctl disable yggsec-home-firewall.service 2>/dev/null || true

    log_success "Services stopped and disabled"
}

remove_systemd_files() {
    log_info "Removing systemd service files..."

    rm -f /etc/systemd/system/yggsec-home.service
    rm -f /etc/systemd/system/yggsec-home-firewall.service

    systemctl daemon-reload

    log_success "Systemd files removed"
}

cleanup_firewall() {
    log_info "Cleaning up firewall rules..."

    # Run cleanup script if it exists
    if [[ -f "$INSTALL_DIR/scripts/cleanup-firewall.sh" ]]; then
        "$INSTALL_DIR/scripts/cleanup-firewall.sh" || true
    fi

    log_success "Firewall rules cleaned up"
}

remove_application_files() {
    log_info "Removing application files..."

    if [[ -d "$INSTALL_DIR" ]]; then
        # Create backup of configuration before removal
        BACKUP_DIR="/tmp/yggsec-home-backup-$(date +%Y%m%d-%H%M%S)"
        mkdir -p "$BACKUP_DIR"

        cp -r "$INSTALL_DIR/logs" "$BACKUP_DIR/" 2>/dev/null || true
        cp -r "$INSTALL_DIR/uploads" "$BACKUP_DIR/" 2>/dev/null || true

        if [[ -d "$BACKUP_DIR/logs" ]] || [[ -d "$BACKUP_DIR/uploads" ]]; then
            log_info "Configuration backed up to: $BACKUP_DIR"
        fi

        # Remove application directory
        rm -rf "$INSTALL_DIR"

        log_success "Application files removed"
    else
        log_warning "Application directory not found"
    fi
}

remove_wireguard_configs() {
    log_info "Checking for WireGuard configurations..."

    read -p "Remove WireGuard configurations? (y/N): " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        # Stop any active WireGuard connections
        wg-quick down wg0 2>/dev/null || true

        # Remove configuration files
        rm -f /etc/wireguard/wg0.conf*

        log_success "WireGuard configurations removed"
    else
        log_info "WireGuard configurations preserved"
    fi
}

cleanup_iptables() {
    log_info "Cleaning up remaining iptables rules..."

    # Remove YggSec-specific rules
    iptables -D INPUT -p tcp --dport 5000 -s 192.168.0.0/16 -j ACCEPT 2>/dev/null || true
    iptables -D INPUT -p tcp --dport 5000 -s 10.0.0.0/8 -j ACCEPT 2>/dev/null || true
    iptables -D INPUT -p tcp --dport 5000 -s 172.16.0.0/12 -j ACCEPT 2>/dev/null || true

    # Save rules if iptables-persistent is installed
    if command -v iptables-save &> /dev/null; then
        iptables-save > /etc/iptables/rules.v4 2>/dev/null || true
    fi

    log_success "Iptables rules cleaned up"
}

show_completion_message() {
    echo
    log_success "YggSec-Home uninstall completed!"
    echo
    echo "What was removed:"
    echo "  ✓ YggSec-Home application"
    echo "  ✓ Systemd services"
    echo "  ✓ Firewall rules"
    echo "  ✓ Log files and uploads"
    echo
    echo "What remains on your system:"
    echo "  - AdGuard Home (if installed)"
    echo "  - WireGuard system packages"
    echo "  - Python packages"
    echo "  - System network configuration"
    echo
    if [[ -d "/tmp/yggsec-home-backup-"* ]]; then
        echo "Configuration backup available in /tmp/"
        ls -la /tmp/yggsec-home-backup-* 2>/dev/null || true
    fi
    echo
    log_info "Uninstall complete. Thank you for using YggSec-Home!"
}

main() {
    check_root
    confirm_uninstall
    stop_and_disable_services
    cleanup_firewall
    remove_systemd_files
    remove_wireguard_configs
    cleanup_iptables
    remove_application_files
    show_completion_message
}

trap 'log_error "Uninstall failed at line $LINENO"' ERR

main "$@"