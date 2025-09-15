#!/bin/bash
# YggSec-Home Installation Script for DietPi
# Compatible with ARM SBCs and x86_64 VMware

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
INSTALL_DIR="/opt/yggsec-home"
SERVICE_USER="root"
WEB_PORT="5000"
GITHUB_REPO="https://github.com/romarroca/yggsec-home.git"

# Functions
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

check_dietpi() {
    if [[ ! -f /boot/dietpi/.version ]]; then
        log_warning "DietPi not detected. This script is optimized for DietPi but may work on Debian-based systems."
        read -p "Continue anyway? (y/N): " -n 1 -r
        echo
        if [[ ! $REPLY =~ ^[Yy]$ ]]; then
            exit 1
        fi
    else
        DIETPI_VERSION=$(cat /boot/dietpi/.version)
        log_info "DietPi version $DIETPI_VERSION detected"
    fi
}

detect_architecture() {
    ARCH=$(uname -m)
    case $ARCH in
        x86_64)
            log_info "Detected architecture: x86_64 (VMware/PC)"
            ;;
        aarch64|arm64)
            log_info "Detected architecture: ARM64"
            ;;
        armv7l)
            log_info "Detected architecture: ARM32v7"
            ;;
        armv6l)
            log_info "Detected architecture: ARM32v6"
            ;;
        *)
            log_warning "Unknown architecture: $ARCH"
            ;;
    esac
}

install_dependencies() {
    log_info "Installing system dependencies..."

    # Update package list
    apt update

    # Install Python and essential packages
    apt install -y \
        python3 \
        python3-pip \
        python3-venv \
        git \
        curl \
        wget \
        nano \
        htop \
        iptables \
        iptables-persistent \
        wireguard-tools

    log_success "Dependencies installed"
}

create_user_and_directories() {
    log_info "Creating directories and setting permissions..."

    # Create installation directory
    mkdir -p "$INSTALL_DIR"
    mkdir -p "$INSTALL_DIR"/{logs,uploads,scripts,systemd}

    # Set ownership
    chown -R $SERVICE_USER:$SERVICE_USER "$INSTALL_DIR"

    log_success "Directories created"
}

clone_repository() {
    log_info "Cloning YggSec-Home repository..."

    if [[ -d "$INSTALL_DIR/.git" ]]; then
        log_info "Repository already exists, updating..."
        cd "$INSTALL_DIR"
        git pull
    else
        git clone "$GITHUB_REPO" "$INSTALL_DIR"
    fi

    cd "$INSTALL_DIR"
    chown -R $SERVICE_USER:$SERVICE_USER "$INSTALL_DIR"

    log_success "Repository cloned/updated"
}

setup_python_environment() {
    log_info "Setting up Python virtual environment..."

    cd "$INSTALL_DIR"

    # Create virtual environment
    python3 -m venv venv

    # Install Python dependencies
    ./venv/bin/pip install --upgrade pip
    ./venv/bin/pip install -r requirements.txt

    log_success "Python environment configured"
}

install_adguard_home() {
    log_info "Installing AdGuard Home..."

    read -p "Install AdGuard Home? (y/N): " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        # Download and install AdGuard Home
        curl -s -S -L https://raw.githubusercontent.com/AdguardTeam/AdGuardHome/master/scripts/install.sh | sh -s -- -v

        # Enable service
        systemctl enable AdGuardHome

        log_success "AdGuard Home installed"
        log_info "Access AdGuard setup at http://$(hostname -I | awk '{print $1}'):3000"
    else
        log_info "Skipping AdGuard Home installation"
    fi
}

configure_systemd_services() {
    log_info "Configuring systemd services..."

    cd "$INSTALL_DIR"

    # Generate random secret key
    SECRET_KEY=$(python3 -c "import secrets; print(secrets.token_urlsafe(32))")

    # Update service file with secret key
    sed -i "s/SECRET_KEY=change-this-in-production/SECRET_KEY=$SECRET_KEY/" systemd/yggsec-home.service

    # Install service files
    cp systemd/yggsec-home.service /etc/systemd/system/
    cp systemd/yggsec-home-firewall.service /etc/systemd/system/

    # Make scripts executable
    chmod +x scripts/*.sh

    # Reload systemd
    systemctl daemon-reload

    log_success "Systemd services configured"
}

setup_firewall() {
    log_info "Setting up firewall..."

    read -p "Configure firewall for LAN-only access? (Y/n): " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Nn]$ ]]; then
        systemctl enable yggsec-home-firewall.service
        systemctl start yggsec-home-firewall.service
        log_success "Firewall configured"
    else
        log_warning "Firewall setup skipped - web interface will be accessible from anywhere"
    fi
}

start_services() {
    log_info "Starting YggSec-Home services..."

    # Enable and start main service
    systemctl enable yggsec-home.service
    systemctl start yggsec-home.service

    # Wait a moment for service to start
    sleep 3

    # Check service status
    if systemctl is-active --quiet yggsec-home.service; then
        log_success "YggSec-Home service started successfully"
    else
        log_error "Failed to start YggSec-Home service"
        systemctl status yggsec-home.service
        return 1
    fi
}

configure_hostname() {
    log_info "Configuring hostname for easy access..."

    read -p "Set hostname to 'yggsec-home'? (Y/n): " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Nn]$ ]]; then
        hostnamectl set-hostname yggsec-home
        echo "127.0.1.1    yggsec-home" >> /etc/hosts
        log_success "Hostname set to yggsec-home"
    fi
}

show_completion_message() {
    local IP_ADDRESS=$(hostname -I | awk '{print $1}')

    echo
    log_success "YggSec-Home installation completed!"
    echo
    echo "=================================================="
    echo "  YggSec-Home is now running on your DietPi device"
    echo "=================================================="
    echo
    echo "Web Interface Access:"
    echo "  Local IP:    http://$IP_ADDRESS:$WEB_PORT"
    echo "  Hostname:    http://yggsec-home.local:$WEB_PORT"
    echo
    echo "Service Management:"
    echo "  Status:      sudo systemctl status yggsec-home"
    echo "  Logs:        sudo journalctl -u yggsec-home -f"
    echo "  Restart:     sudo systemctl restart yggsec-home"
    echo
    echo "Configuration Files:"
    echo "  Main config: $INSTALL_DIR/config.py"
    echo "  Logs:        $INSTALL_DIR/logs/"
    echo "  Uploads:     $INSTALL_DIR/uploads/"
    echo
    if systemctl is-enabled --quiet AdGuardHome; then
        echo "AdGuard Home:"
        echo "  Dashboard:   http://$IP_ADDRESS:3000"
        echo
    fi
    echo "Security:"
    echo "  - Web interface accessible from LAN only"
    echo "  - SSH access maintained on port 22"
    echo "  - Change default passwords immediately"
    echo
    echo "Next Steps:"
    echo "  1. Access the web interface using the URL above"
    echo "  2. Configure network settings if needed"
    echo "  3. Set up AdGuard Home (if installed)"
    echo "  4. Upload WireGuard configuration (if needed)"
    echo "  5. Change admin password in Settings"
    echo
    log_info "Installation complete! Enjoy your YggSec-Home setup."
}

# Main installation process
main() {
    echo "=================================================="
    echo "  YggSec-Home Installation Script for DietPi"
    echo "=================================================="
    echo

    check_root
    check_dietpi
    detect_architecture

    echo
    log_info "Starting installation process..."
    echo

    install_dependencies
    create_user_and_directories
    clone_repository
    setup_python_environment
    install_adguard_home
    configure_systemd_services
    setup_firewall
    start_services
    configure_hostname
    show_completion_message
}

# Error handling
trap 'log_error "Installation failed at line $LINENO. Check the output above for details."' ERR

# Run main function
main "$@"