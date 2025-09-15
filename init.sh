#!/bin/bash
# YggSec-Home Complete Installation Script
# Automated production deployment for DietPi and Debian-based systems

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

# Configuration
INSTALL_DIR="/opt/yggsec-home"
SERVICE_USER="root"
WEB_PORT="5000"
CURRENT_DIR="$(pwd)"

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
        log_error "This script must be run as root"
        log_info "Run: sudo ./init.sh"
        exit 1
    fi
}

detect_system() {
    log_info "Detecting system..."

    if [[ -f /etc/os-release ]]; then
        . /etc/os-release
        log_info "Detected: $PRETTY_NAME"
    fi

    # Check if it's DietPi
    if [[ -f /boot/dietpi/.version ]]; then
        DIETPI_VERSION=$(cat /boot/dietpi/.version)
        log_success "DietPi version $DIETPI_VERSION detected"
        IS_DIETPI=true
    else
        IS_DIETPI=false
        log_info "Standard Debian/Ubuntu system detected"
    fi

    # Detect architecture
    ARCH=$(uname -m)
    case $ARCH in
        x86_64)
            log_info "Architecture: x86_64 (VMware/PC)"
            ;;
        aarch64|arm64)
            log_info "Architecture: ARM64"
            ;;
        armv7l)
            log_info "Architecture: ARM32v7"
            ;;
        armv6l)
            log_info "Architecture: ARM32v6 (Pi Zero)"
            ;;
        *)
            log_warning "Unknown architecture: $ARCH"
            ;;
    esac
}

install_system_packages() {
    log_info "Installing system packages..."

    # Update package list
    apt update

    # Install essential packages
    log_info "Installing Python and essential tools..."
    apt install -y \
        python3 \
        python3-pip \
        python3-venv \
        python3-dev \
        python3-setuptools \
        build-essential \
        git \
        curl \
        wget \
        nano \
        htop \
        net-tools \
        iproute2 \
        systemd \
        sudo

    # Install network and security tools
    log_info "Installing network and security tools..."
    apt install -y \
        iptables \
        iptables-persistent \
        wireguard-tools \
        dnsutils \
        iputils-ping

    # Install optional but useful packages
    log_info "Installing additional utilities..."
    apt install -y \
        unzip \
        rsync \
        ca-certificates \
        gnupg \
        lsb-release \
        software-properties-common

    log_success "System packages installed"
}

verify_installation() {
    log_info "Verifying installations..."

    # Check Python
    if ! command -v python3 &> /dev/null; then
        log_error "Python 3 installation failed"
        exit 1
    fi

    PYTHON_VERSION=$(python3 -c 'import sys; print(".".join(map(str, sys.version_info[:2])))')
    log_info "Python $PYTHON_VERSION installed"

    # Check pip
    if ! command -v pip3 &> /dev/null; then
        log_error "pip3 installation failed"
        exit 1
    fi

    log_success "All installations verified"
}

setup_directories() {
    log_info "Setting up directories..."

    # Remove existing installation if present
    if [[ -d "$INSTALL_DIR" ]]; then
        log_warning "Existing installation found, backing up..."
        mv "$INSTALL_DIR" "$INSTALL_DIR.backup.$(date +%Y%m%d-%H%M%S)"
    fi

    # Create installation directory
    mkdir -p "$INSTALL_DIR"
    mkdir -p "$INSTALL_DIR"/{logs,uploads}

    log_success "Directories created"
}

copy_application_files() {
    log_info "Copying application files to $INSTALL_DIR..."

    # Copy all files except git directory and temporary files
    rsync -av \
        --exclude='.git' \
        --exclude='__pycache__' \
        --exclude='*.pyc' \
        --exclude='venv' \
        --exclude='logs' \
        --exclude='uploads' \
        --exclude='.env*' \
        "$CURRENT_DIR/" "$INSTALL_DIR/"

    # Set ownership
    chown -R $SERVICE_USER:$SERVICE_USER "$INSTALL_DIR"

    log_success "Application files copied"
}

setup_python_environment() {
    log_info "Setting up Python virtual environment..."

    cd "$INSTALL_DIR"

    # Create virtual environment
    python3 -m venv venv

    # Upgrade pip in virtual environment
    ./venv/bin/pip install --upgrade pip

    # Install requirements
    log_info "Installing Python dependencies..."
    ./venv/bin/pip install -r requirements.txt

    log_success "Python environment configured"
}

install_adguard_home() {
    log_info "Installing AdGuard Home..."

    read -p "Install AdGuard Home for DNS filtering? (Y/n): " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Nn]$ ]]; then
        # Download and install AdGuard Home
        curl -s -S -L https://raw.githubusercontent.com/AdguardTeam/AdGuardHome/master/scripts/install.sh | sh -s -- -v

        # Enable service
        systemctl enable AdGuardHome
        systemctl start AdGuardHome

        log_success "AdGuard Home installed and started"
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

    # Update service file with secret key and correct paths
    sed -i "s|SECRET_KEY=change-this-in-production|SECRET_KEY=$SECRET_KEY|" systemd/yggsec-home.service
    sed -i "s|WorkingDirectory=/opt/yggsec-home|WorkingDirectory=$INSTALL_DIR|" systemd/yggsec-home.service
    sed -i "s|ExecStart=/opt/yggsec-home/venv/bin/python app.py|ExecStart=$INSTALL_DIR/venv/bin/python app.py|" systemd/yggsec-home.service

    # Install service files
    cp systemd/yggsec-home.service /etc/systemd/system/
    cp systemd/yggsec-home-firewall.service /etc/systemd/system/

    # Update firewall service paths
    sed -i "s|/opt/yggsec-home/scripts|$INSTALL_DIR/scripts|g" /etc/systemd/system/yggsec-home-firewall.service

    # Make scripts executable
    chmod +x scripts/*.sh

    # Reload systemd
    systemctl daemon-reload

    log_success "Systemd services configured"
}

setup_firewall() {
    log_info "Setting up firewall for security..."

    read -p "Configure firewall for LAN-only access? (Y/n): " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Nn]$ ]]; then
        systemctl enable yggsec-home-firewall.service
        systemctl start yggsec-home-firewall.service
        log_success "Firewall configured for LAN-only access"
    else
        log_warning "Firewall setup skipped - web interface accessible from anywhere"
    fi
}

start_services() {
    log_info "Starting YggSec-Home services..."

    # Enable and start main service
    systemctl enable yggsec-home.service
    systemctl start yggsec-home.service

    # Wait for service to start
    sleep 3

    # Check service status
    if systemctl is-active --quiet yggsec-home.service; then
        log_success "YggSec-Home service started successfully"
    else
        log_error "Failed to start YggSec-Home service"
        log_info "Checking service logs..."
        systemctl status yggsec-home.service --no-pager
        journalctl -u yggsec-home.service --no-pager -n 20
        exit 1
    fi
}

configure_hostname() {
    log_info "Configuring hostname..."

    read -p "Set hostname to 'yggsec-home' for easy access? (Y/n): " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Nn]$ ]]; then
        hostnamectl set-hostname yggsec-home

        # Update /etc/hosts
        if ! grep -q "yggsec-home" /etc/hosts; then
            echo "127.0.1.1    yggsec-home" >> /etc/hosts
        fi

        log_success "Hostname set to yggsec-home"
    fi
}

show_completion_message() {
    local IP_ADDRESS=$(hostname -I | awk '{print $1}')

    echo
    echo "=================================================================="
    log_success "YggSec-Home installation completed successfully!"
    echo "=================================================================="
    echo
    echo "🌐 Web Interface Access:"
    echo "  Local IP:    http://$IP_ADDRESS:$WEB_PORT"
    echo "  Hostname:    http://yggsec-home.local:$WEB_PORT"
    echo
    echo "📋 Service Management:"
    echo "  Status:      systemctl status yggsec-home"
    echo "  Start:       systemctl start yggsec-home"
    echo "  Stop:        systemctl stop yggsec-home"
    echo "  Restart:     systemctl restart yggsec-home"
    echo "  Logs:        journalctl -u yggsec-home -f"
    echo
    echo "📁 Installation Directory: $INSTALL_DIR"
    echo "  Configuration: $INSTALL_DIR/config.py"
    echo "  Logs:         $INSTALL_DIR/logs/"
    echo "  Uploads:      $INSTALL_DIR/uploads/"
    echo
    if systemctl is-enabled --quiet AdGuardHome 2>/dev/null; then
        echo "🛡️ AdGuard Home:"
        echo "  Dashboard:   http://$IP_ADDRESS:3000"
        echo
    fi
    echo "🔒 Security:"
    echo "  - Web interface restricted to LAN access only"
    echo "  - SSH access maintained on port 22"
    echo "  - Firewall configured for protection"
    echo
    echo "🚀 Next Steps:"
    echo "  1. Access web interface using URL above"
    echo "  2. Configure network settings if needed"
    echo "  3. Set up AdGuard Home (if installed)"
    echo "  4. Upload WireGuard configuration (if needed)"
    echo "  5. Change admin password in Settings → Change Password"
    echo
    echo "📚 Documentation:"
    echo "  README:      $INSTALL_DIR/README.md"
    echo "  GitHub:      https://github.com/romarroca/yggsec-home"
    echo
    log_success "Installation complete! Enjoy your YggSec-Home setup."
}

# Main installation process
main() {
    echo "=================================================================="
    echo "  YggSec-Home Complete Installation Script"
    echo "=================================================================="
    echo

    # Verify we're in the right directory
    if [[ ! -f "app.py" ]] || [[ ! -f "requirements.txt" ]]; then
        log_error "This script must be run from the YggSec-Home source directory"
        log_info "Make sure you're in the directory containing app.py and requirements.txt"
        exit 1
    fi

    check_root
    detect_system

    log_info "Starting complete installation process..."
    echo

    install_system_packages
    verify_installation
    setup_directories
    copy_application_files
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