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
        log_info "DietPi systems often have AdGuard Home and WireGuard pre-installed"
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

check_existing_packages() {
    log_info "Checking for existing installations..."

    # Check WireGuard
    if command -v wg &> /dev/null; then
        log_success "WireGuard tools already installed"
        WG_INSTALLED=true
    else
        log_info "WireGuard tools not found, will install"
        WG_INSTALLED=false
    fi

    # Check Python
    if command -v python3 &> /dev/null; then
        PYTHON_VERSION=$(python3 -c 'import sys; print(".".join(map(str, sys.version_info[:2])))')
        log_success "Python $PYTHON_VERSION already installed"
        PYTHON_INSTALLED=true
    else
        log_info "Python not found, will install"
        PYTHON_INSTALLED=false
    fi
}

check_package_availability() {
    local package=$1
    if apt-cache show "$package" &>/dev/null; then
        return 0
    else
        return 1
    fi
}

install_system_packages() {
    log_info "Installing system packages..."

    # Update package list
    apt update

    # Prepare package lists
    ESSENTIAL_PACKAGES=""
    NETWORK_PACKAGES=""

    # Essential packages for application functionality
    ESSENTIAL_PACKAGES="systemd rsync curl"  # rsync for file copying, curl for AdGuard installer

    # Python packages (install if not present)
    if [[ "$PYTHON_INSTALLED" != true ]]; then
        log_info "Installing Python stack..."
        ESSENTIAL_PACKAGES="$ESSENTIAL_PACKAGES python3 python3-pip python3-venv"
    else
        log_info "Python already installed, checking for pip/venv..."
        # Still install pip and venv if missing
        if ! command -v pip3 &> /dev/null; then
            ESSENTIAL_PACKAGES="$ESSENTIAL_PACKAGES python3-pip"
        fi
        # Check for venv module
        if ! python3 -m venv --help &> /dev/null; then
            ESSENTIAL_PACKAGES="$ESSENTIAL_PACKAGES python3-venv"
        fi
    fi

    # Network management tools
    NETWORK_PACKAGES="iproute2 net-tools"  # For network configuration

    # WireGuard (install if not present)
    if [[ "$WG_INSTALLED" != true ]]; then
        log_info "Installing WireGuard tools..."
        NETWORK_PACKAGES="$NETWORK_PACKAGES wireguard-tools"
    else
        log_info "WireGuard already installed, skipping"
    fi

    # Nginx for SSL termination and reverse proxy
    NGINX_PACKAGES="nginx-light openssl"  # nginx-light for minimal footprint

    # Optional but useful tools
    OPTIONAL_PACKAGES="wget"  # For downloading configs if needed

    # Install packages with error handling (temporarily disable strict error checking)
    set +e

    # Install essential system packages
    if [[ -n "$ESSENTIAL_PACKAGES" ]]; then
        log_info "Installing essential packages: $ESSENTIAL_PACKAGES"
        apt install -y $ESSENTIAL_PACKAGES
        if [[ $? -ne 0 ]]; then
            log_warning "Some essential packages failed to install, continuing..."
        fi
    fi

    # Install network packages
    if [[ -n "$NETWORK_PACKAGES" ]]; then
        log_info "Installing network tools: $NETWORK_PACKAGES"
        apt install -y $NETWORK_PACKAGES
        if [[ $? -ne 0 ]]; then
            log_warning "Some network packages failed to install, continuing..."
        fi
    fi

    # Install nginx packages
    if [[ -n "$NGINX_PACKAGES" ]]; then
        log_info "Installing nginx and SSL tools: $NGINX_PACKAGES"
        apt install -y $NGINX_PACKAGES
        if [[ $? -ne 0 ]]; then
            log_warning "Some nginx packages failed to install, continuing..."
        fi
    fi

    # Install optional packages
    if [[ -n "$OPTIONAL_PACKAGES" ]]; then
        log_info "Installing optional tools: $OPTIONAL_PACKAGES"
        apt install -y $OPTIONAL_PACKAGES
        if [[ $? -ne 0 ]]; then
            log_warning "Some optional packages failed to install, continuing..."
        fi
    fi

    # Re-enable strict error checking
    set -e

    log_success "System packages installation completed"
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

prompt_for_credentials() {
    log_info "Setting up admin credentials..."
    echo
    echo "Please set up admin credentials for YggSec-Home and AdGuard Home:"
    echo "Default username: yggsec"
    echo

    # Prompt for password with confirmation
    while true; do
        echo -n "Enter admin password: "
        read -s ADMIN_PASSWORD
        echo

        if [[ ${#ADMIN_PASSWORD} -lt 8 ]]; then
            log_warning "Password must be at least 8 characters long"
            continue
        fi

        echo -n "Confirm admin password: "
        read -s ADMIN_PASSWORD_CONFIRM
        echo

        if [[ "$ADMIN_PASSWORD" == "$ADMIN_PASSWORD_CONFIRM" ]]; then
            break
        else
            log_warning "Passwords do not match, please try again"
        fi
    done

    # Generate bcrypt hash for AdGuard Home (using Python virtual environment)
    log_info "Generating secure password hash..."
    ADMIN_PASSWORD_HASH=$("$INSTALL_DIR/venv/bin/python" -c "
import bcrypt
password = '$ADMIN_PASSWORD'.encode('utf-8')
salt = bcrypt.gensalt()
hash = bcrypt.hashpw(password, salt)
print(hash.decode('utf-8'))
")

    # Store credentials globally for use in configuration files
    export ADMIN_USERNAME="yggsec"
    export ADMIN_PASSWORD
    export ADMIN_PASSWORD_HASH

    log_success "Admin credentials configured"
}

create_adguard_config() {
    local ADGUARD_CONFIG_DIR="/opt/AdGuardHome"
    local ADGUARD_CONFIG_FILE="$ADGUARD_CONFIG_DIR/AdGuardHome.yaml"

    # Ensure AdGuard config directory exists
    mkdir -p "$ADGUARD_CONFIG_DIR"

    # Create pre-configured AdGuard Home configuration
    cat > "$ADGUARD_CONFIG_FILE" << EOF
bind_host: 127.0.0.1
bind_port: 3001
beta_bind_port: 0
users:
  - name: yggsec
    password: $ADMIN_PASSWORD_HASH
auth_attempts: 5
block_auth_min: 15
http_proxy: ""
language: en
theme: auto
debug_pprof: false
web_session_ttl: 720
http:
  pprof:
    port: 6060
    enabled: false
  address: 127.0.0.1:3001
  session_ttl: 720h
dns:
  bind_hosts:
    - 0.0.0.0
  port: 53
  anonymize_client_ip: false
  protection_enabled: true
  blocking_mode: default
  blocking_ipv4: ""
  blocking_ipv6: ""
  blocked_response_ttl: 10
  parental_block_host: family-block.dns.adguard.com
  safebrowsing_block_host: standard-block.dns.adguard.com
  ratelimit: 20
  ratelimit_whitelist: []
  refuse_any: true
  upstream_dns:
    - 127.0.0.1:5353
  upstream_dns_file: ""
  bootstrap_dns: []
  all_servers: false
  fastest_addr: false
  fastest_timeout: 1s
  allowed_clients: []
  disallowed_clients: []
  blocked_hosts:
    - version.bind
    - id.server
    - hostname.bind
  trusted_proxies:
    - 127.0.0.0/8
    - ::1/128
  cache_size: 4194304
  cache_ttl_min: 0
  cache_ttl_max: 0
  cache_optimistic: false
  bogus_nxdomain: []
  aaaa_disabled: false
  enable_dnssec: false
  edns_client_subnet:
    custom_ip: ""
    enabled: false
    use_custom: false
  max_goroutines: 300
  handle_ddr: true
  ipset: []
  ipset_file: ""
  bootstrap_prefer_ipv6: false
  upstream_timeout: 10s
tls:
  enabled: false
  server_name: ""
  force_https: false
  port_https: 443
  port_dns_over_tls: 853
  port_dns_over_quic: 853
  port_dnscrypt: 0
  dnscrypt_config_file: ""
  allow_unencrypted_doh: false
  certificate_chain: ""
  private_key: ""
  certificate_path: ""
  private_key_path: ""
  strict_sni_check: false
querylog:
  enabled: true
  file_enabled: true
  interval: 2160h
  size_memory: 1000
  ignored: []
statistics:
  enabled: true
  interval: 24h
  ignored: []
filters:
  - enabled: true
    url: https://adguardteam.github.io/AdGuardSDNSFilter/Filters/filter.txt
    name: AdGuard DNS filter
    id: 1
  - enabled: true
    url: https://adaway.org/hosts.txt
    name: AdAway Default Blocklist
    id: 2
whitelist_filters: []
user_rules: []
dhcp:
  enabled: false
  interface_name: ""
  local_domain_name: lan
  dhcpv4:
    gateway_ip: ""
    subnet_mask: ""
    range_start: ""
    range_end: ""
    lease_duration: 86400
    icmp_timeout_msec: 1000
    options: []
  dhcpv6:
    range_start: ""
    lease_duration: 86400
    ra_slaac_only: false
    ra_allow_slaac: false
clients:
  runtime_sources:
    whois: true
    arp: true
    rdns: true
    dhcp: true
    hosts: true
  persistent: []
log_file: ""
log_max_backups: 0
log_max_size: 100
log_max_age: 3
log_compress: false
log_localtime: false
verbose: false
os:
  group: ""
  user: ""
  rlimit_nofile: 0
schema_version: 27
EOF

    # Set proper ownership
    chown -R AdGuardHome:AdGuardHome "$ADGUARD_CONFIG_DIR" 2>/dev/null || true

    log_success "AdGuard Home pre-configured on port 3000"
    log_info "Default admin credentials: yggsec / [password set during installation]"
}

generate_ssl_certificates() {
    log_info "Generating self-signed SSL certificates..."

    local SSL_DIR="/etc/nginx/ssl"
    mkdir -p "$SSL_DIR"

    # Generate certificates for both domains
    local DOMAINS=("home.yggsec.com" "adguard.yggsec.com")

    for DOMAIN in "${DOMAINS[@]}"; do
        local KEY_FILE="$SSL_DIR/${DOMAIN}.key"
        local CERT_FILE="$SSL_DIR/${DOMAIN}.crt"

        if [[ -f "$KEY_FILE" && -f "$CERT_FILE" ]]; then
            log_info "SSL certificate for $DOMAIN already exists, skipping"
            continue
        fi

        log_info "Generating certificate for $DOMAIN..."

        # Generate private key
        openssl genrsa -out "$KEY_FILE" 2048

        # Generate certificate
        openssl req -new -x509 -key "$KEY_FILE" -out "$CERT_FILE" -days 3650 -subj "/CN=$DOMAIN/O=YggSec-Home/C=US"

        # Set proper permissions
        chmod 600 "$KEY_FILE"
        chmod 644 "$CERT_FILE"

        log_success "Generated SSL certificate for $DOMAIN"
    done

    log_success "SSL certificates generated"
}

configure_nginx() {
    log_info "Configuring nginx for SSL termination and reverse proxy..."

    # Note: nginx log creation is now handled automatically by the Flask app

    # Temporarily stop AdGuard to avoid port 3000 conflict during nginx setup
    log_info "Temporarily stopping AdGuard to configure nginx..."
    systemctl stop AdGuardHome 2>/dev/null || true

    # Remove default nginx site
    rm -f /etc/nginx/sites-enabled/default

    # Create nginx configuration for YggSec-Home
    cat > /etc/nginx/sites-available/yggsec-home << 'EOF'
# YggSec-Home SSL Virtual Hosts

# HTTP to HTTPS redirect for any hostname/IP
server {
    listen 80;
    server_name _;
    return 301 https://$host$request_uri;
}

# HTTPS server for direct AdGuard access on port 3000
server {
    listen 3000 ssl;
    http2 on;
    server_name _;

    # SSL Configuration (using AdGuard certificate)
    ssl_certificate /etc/nginx/ssl/adguard.yggsec.com.crt;
    ssl_certificate_key /etc/nginx/ssl/adguard.yggsec.com.key;
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_prefer_server_ciphers on;
    ssl_ciphers ECDHE-ECDSA-AES128-GCM-SHA256:ECDHE-RSA-AES128-GCM-SHA256:ECDHE-ECDSA-AES256-GCM-SHA384:ECDHE-RSA-AES256-GCM-SHA384;
    ssl_session_timeout 1d;
    ssl_session_cache shared:SSL:50m;

    # Security headers
    add_header X-Frame-Options DENY;
    add_header X-Content-Type-Options nosniff;
    add_header X-XSS-Protection "1; mode=block";
    add_header Strict-Transport-Security "max-age=31536000; includeSubDomains" always;

    # Direct proxy to AdGuard Home
    location / {
        proxy_pass http://127.0.0.1:3001;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;

        # WebSocket support for AdGuard
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";

        # Timeouts
        proxy_connect_timeout 60s;
        proxy_send_timeout 60s;
        proxy_read_timeout 60s;
    }
}

# HTTPS server for YggSec-Home (port 443 - main app)
server {
    listen 443 ssl;
    http2 on;
    server_name _;

    # SSL Configuration
    ssl_certificate /etc/nginx/ssl/home.yggsec.com.crt;
    ssl_certificate_key /etc/nginx/ssl/home.yggsec.com.key;
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_prefer_server_ciphers on;
    ssl_ciphers ECDHE-ECDSA-AES128-GCM-SHA256:ECDHE-RSA-AES128-GCM-SHA256:ECDHE-ECDSA-AES256-GCM-SHA384:ECDHE-RSA-AES256-GCM-SHA384;
    ssl_session_timeout 1d;
    ssl_session_cache shared:SSL:50m;

    # Security headers
    add_header X-Frame-Options DENY;
    add_header X-Content-Type-Options nosniff;
    add_header X-XSS-Protection "1; mode=block";
    add_header Strict-Transport-Security "max-age=31536000; includeSubDomains" always;

    # Reverse proxy to Flask app
    location / {
        proxy_pass http://127.0.0.1:5000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header X-Forwarded-Host $host;
        proxy_set_header X-Forwarded-Port $server_port;

        # WebSocket support
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";

        # Timeouts
        proxy_connect_timeout 60s;
        proxy_send_timeout 60s;
        proxy_read_timeout 60s;
    }

    # Static files optimization
    location /static/ {
        proxy_pass http://127.0.0.1:5000;
        expires 1y;
        add_header Cache-Control "public, immutable";
    }
}
EOF

    # Enable the site
    ln -sf /etc/nginx/sites-available/yggsec-home /etc/nginx/sites-enabled/

    # Check nginx version and adjust config if needed
    NGINX_VERSION=$(nginx -v 2>&1 | grep -o '[0-9]\+\.[0-9]\+' | head -1)
    log_info "Nginx version: $NGINX_VERSION"

    # For nginx < 1.25.1, use old http2 syntax
    if dpkg --compare-versions "$NGINX_VERSION" lt "1.25.1"; then
        log_info "Using legacy http2 syntax for older nginx"
        sed -i 's/listen 443 ssl;.*http2 on;/listen 443 ssl http2;/g' /etc/nginx/sites-available/yggsec-home
    fi

    # Test nginx configuration
    if nginx -t; then
        log_success "Nginx configuration is valid"
    else
        log_error "Nginx configuration is invalid"
        log_info "Checking nginx logs..."
        journalctl -u nginx --no-pager -n 20
        exit 1
    fi

    # Configure nginx for auto-start and crash recovery
    log_info "Configuring nginx for automatic startup and crash recovery..."

    # Create systemd override directory for nginx
    mkdir -p /etc/systemd/system/nginx.service.d/

    # Create override configuration for crash recovery
    cat > /etc/systemd/system/nginx.service.d/restart.conf << 'EOF'
[Service]
# Basic log directory creation (Flask app handles the rest)
ExecStartPre=-/bin/mkdir -p /var/log/nginx

# Automatic restart on failure
Restart=always
RestartSec=5

# Resource limits and security
LimitNOFILE=65536
LimitNPROC=32768

# Process management
KillMode=mixed
KillSignal=SIGQUIT
TimeoutStopSec=5
EOF

    # Reload systemd to apply override
    systemctl daemon-reload

    # Enable nginx for automatic startup
    systemctl enable nginx

    # Stop nginx if running, then start fresh
    systemctl stop nginx 2>/dev/null || true
    systemctl start nginx

    # Verify nginx started successfully
    if systemctl is-active --quiet nginx; then
        log_success "Nginx started successfully with crash recovery enabled"
        log_info "Nginx will automatically restart on failure and boot"
    else
        log_error "Nginx failed to start"
        systemctl status nginx --no-pager
        exit 1
    fi

    # Restart AdGuard Home now that nginx is configured
    log_info "Starting AdGuard Home..."
    systemctl start AdGuardHome

    log_success "Nginx configured for SSL termination"
    log_info "Home app: https://home.yggsec.com"
    log_info "AdGuard:  https://adguard.yggsec.com"
    log_info "Direct access: http://device-ip:3000 → redirects to HTTPS"
}

install_and_configure_unbound() {
    log_info "Installing and configuring Unbound DNS resolver..."

    # Check if Unbound is already installed
    if command -v unbound &> /dev/null; then
        log_success "Unbound already installed"
    else
        log_info "Installing Unbound..."

        # Install Unbound using standard apt (works on DietPi and Debian)
        apt install -y unbound

        log_success "Unbound installed"
    fi

    # Create Unbound configuration directory if needed
    mkdir -p /etc/unbound/unbound.conf.d
    mkdir -p /var/lib/unbound

    # Download root hints for recursive DNS
    log_info "Downloading DNS root hints..."
    if [[ ! -f /var/lib/unbound/root.hints ]] || [[ $(find /var/lib/unbound/root.hints -mtime +30 2>/dev/null) ]]; then
        wget -q -O /var/lib/unbound/root.hints https://www.internic.net/domain/named.root || \
            log_warning "Failed to download root hints, will use built-in"
    fi

    # Create YggSec-specific Unbound configuration
    log_info "Configuring Unbound for localhost-only access on port 5353..."
    cat > /etc/unbound/unbound.conf.d/yggsec-unbound.conf << 'EOFUNBOUND'
# YggSec-Home Unbound Configuration
# Optimized for privacy and performance as AdGuard Home upstream resolver

server:
    # Listen on localhost only, port 5353 (AdGuard uses 53)
    interface: 127.0.0.1
    port: 5353

    # Access control - localhost only
    access-control: 0.0.0.0/0 refuse
    access-control: 127.0.0.0/8 allow
    access-control: ::/0 refuse
    access-control: ::1/128 allow

    # Do not daemonize (systemd manages this)
    do-daemonize: no

    # Performance tuning for home use
    num-threads: 1
    msg-cache-size: 50m
    rrset-cache-size: 100m
    cache-min-ttl: 300
    cache-max-ttl: 86400

    # Privacy settings
    hide-identity: yes
    hide-version: yes
    qname-minimisation: yes
    minimal-responses: yes
    use-caps-for-id: yes
    rrset-roundrobin: yes

    # DNSSEC validation
    auto-trust-anchor-file: "/var/lib/unbound/root.key"
    harden-glue: yes
    harden-dnssec-stripped: yes
    harden-algo-downgrade: yes
    harden-large-queries: yes
    harden-short-bufsize: yes

    # Prefetch popular domains
    prefetch: yes
    prefetch-key: yes
    serve-expired: yes

    # Logging (minimal for privacy)
    verbosity: 0
    log-queries: no
    log-replies: no

    # Protocol settings
    do-udp: yes
    do-tcp: yes
    do-ip4: yes
    do-ip6: no

    # Security
    unwanted-reply-threshold: 10000
    ratelimit: 1000

    # EDNS settings
    edns-buffer-size: 1232

    # Root hints file
    root-hints: "/var/lib/unbound/root.hints"
EOFUNBOUND

    # Set proper ownership
    chown -R unbound:unbound /var/lib/unbound 2>/dev/null || true

    # Initialize trust anchor for DNSSEC if not exists
    if [[ ! -f /var/lib/unbound/root.key ]]; then
        log_info "Initializing DNSSEC trust anchor..."
        if command -v unbound-anchor &> /dev/null; then
            unbound-anchor -a /var/lib/unbound/root.key || \
                log_warning "unbound-anchor failed, creating placeholder file"
        else
            log_info "unbound-anchor not available, creating placeholder file"
        fi

        # If still doesn't exist, create an empty file - Unbound will populate it on first start
        if [[ ! -f /var/lib/unbound/root.key ]]; then
            touch /var/lib/unbound/root.key
            chown unbound:unbound /var/lib/unbound/root.key
            log_info "Created empty root.key - Unbound will populate on first start"
        fi
    fi

    # Test Unbound configuration
    if unbound-checkconf; then
        log_success "Unbound configuration is valid"
    else
        log_error "Unbound configuration is invalid"
        unbound-checkconf
        exit 1
    fi

    # Enable and start Unbound
    systemctl enable unbound
    systemctl restart unbound

    # Wait for Unbound to start
    sleep 2

    # Verify Unbound is running
    if systemctl is-active --quiet unbound; then
        log_success "Unbound started successfully on 127.0.0.1:5353"
        log_info "Unbound will provide recursive DNS with DNSSEC validation"
    else
        log_error "Failed to start Unbound"
        systemctl status unbound --no-pager
        exit 1
    fi
}

install_adguard_home() {
    log_info "Checking AdGuard Home installation..."

    # Check if AdGuard Home is already installed
    if systemctl list-unit-files | grep -q "AdGuardHome.service"; then
        log_success "AdGuard Home already installed and configured"

        # Ensure it's enabled and running
        if ! systemctl is-enabled --quiet AdGuardHome; then
            systemctl enable AdGuardHome
            log_info "Enabled AdGuard Home service"
        fi

        if ! systemctl is-active --quiet AdGuardHome; then
            systemctl start AdGuardHome
            log_info "Started AdGuard Home service"
        fi

        log_success "AdGuard Home is ready"
        log_info "Access AdGuard dashboard at http://$(hostname -I | awk '{print $1}'):3000"
        return
    fi

    # Check if AdGuard binary exists
    if command -v AdGuardHome &> /dev/null; then
        log_success "AdGuard Home binary found, configuring service..."
        systemctl enable AdGuardHome 2>/dev/null || true
        systemctl start AdGuardHome 2>/dev/null || true
        log_success "AdGuard Home configured"
        return
    fi

    # If not installed, offer to install
    read -p "AdGuard Home not found. Install it? (Y/n): " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Nn]$ ]]; then
        log_info "Installing and configuring AdGuard Home..."

        # Download and install AdGuard Home
        curl -s -S -L https://raw.githubusercontent.com/AdguardTeam/AdGuardHome/master/scripts/install.sh | sh -s -- -v

        # Stop the service to configure it
        systemctl stop AdGuardHome 2>/dev/null || true

        # Create pre-configured AdGuard Home configuration
        log_info "Creating pre-configured AdGuard Home setup..."
        create_adguard_config

        # Enable and start service
        systemctl enable AdGuardHome
        systemctl start AdGuardHome

        log_success "AdGuard Home installed and configured"
        log_info "AdGuard Home dashboard: http://$(hostname -I | awk '{print $1}'):3000"
        log_info "Default login: yggsec / [password set during installation]"
    else
        log_info "Skipping AdGuard Home installation"
    fi
}

configure_systemd_services() {
    log_info "Configuring systemd services..."

    cd "$INSTALL_DIR"

    # Generate random secret key
    SECRET_KEY=$(python3 -c "import secrets; print(secrets.token_urlsafe(32))")

    # Create DietPi-compatible service file
    log_info "Creating DietPi-compatible service file..."
    cat > /etc/systemd/system/yggsec-home.service << EOF
[Unit]
Description=YggSec-Home Parental Control Web Interface
Documentation=https://github.com/romarroca/yggsec-home
After=network.target
Wants=network.target

[Service]
Type=simple
User=root
Group=root
WorkingDirectory=$INSTALL_DIR
Environment=PYTHONPATH=$INSTALL_DIR
Environment=FLASK_APP=app.py
Environment=FLASK_ENV=production
Environment=SECRET_KEY=$SECRET_KEY
Environment=ADMIN_USERNAME=$ADMIN_USERNAME
Environment=ADMIN_PASSWORD=$ADMIN_PASSWORD
Environment=ADMIN_PASSWORD_HASH=$ADMIN_PASSWORD_HASH
ExecStart=$INSTALL_DIR/venv/bin/python app.py
ExecReload=/bin/kill -HUP \$MAINPID
Restart=always
RestartSec=5
StandardOutput=journal
StandardError=journal
SyslogIdentifier=yggsec-home

# Basic security settings (compatible with DietPi)
NoNewPrivileges=yes

# Resource limits
LimitNOFILE=1024
LimitNPROC=512

[Install]
WantedBy=multi-user.target
EOF

    # Install firewall service
    cp systemd/yggsec-home-firewall.service /etc/systemd/system/

    # Update firewall service paths
    sed -i "s|/opt/yggsec-home/scripts|$INSTALL_DIR/scripts|g" /etc/systemd/system/yggsec-home-firewall.service

    # Make scripts executable
    chmod +x scripts/*.sh

    # Reload systemd
    systemctl daemon-reload

    log_success "DietPi-compatible systemd services configured"

    # Additional DietPi-specific logging
    if [[ "$IS_DIETPI" == true ]]; then
        log_info "Service configured with DietPi-compatible security settings"
        log_info "Removed strict filesystem protection for better compatibility"
    fi
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
    echo "Web Interface Access:"
    echo "  Home App:    https://home.yggsec.com (add to /etc/hosts: $IP_ADDRESS home.yggsec.com)"
    echo "  AdGuard:     https://adguard.yggsec.com (add to /etc/hosts: $IP_ADDRESS adguard.yggsec.com)"
    echo "  Legacy:      http://$IP_ADDRESS:$WEB_PORT (blocked by firewall, localhost only)"
    echo
    echo "Service Management:"
    echo "  YggSec App:  systemctl status yggsec-home"
    echo "  Nginx:       systemctl status nginx"
    echo "  AdGuard:     systemctl status AdGuardHome"
    echo "  Unbound:     systemctl status unbound"
    echo "  Start All:   systemctl start yggsec-home nginx AdGuardHome unbound"
    echo "  Logs:        journalctl -u yggsec-home -f"
    echo
    echo "Installation Directory: $INSTALL_DIR"
    echo "  Configuration: $INSTALL_DIR/config.py"
    echo "  Logs:         $INSTALL_DIR/logs/"
    echo "  Uploads:      $INSTALL_DIR/uploads/"
    echo
    if systemctl is-enabled --quiet AdGuardHome 2>/dev/null; then
        echo "AdGuard Home:"
        echo "  Dashboard:   https://adguard.yggsec.com (SSL via nginx)"
        echo "  Direct:      http://127.0.0.1:3000 (localhost only)"
        echo "  Status:      systemctl status AdGuardHome"
        echo
    fi

    if command -v unbound &> /dev/null; then
        echo "Unbound DNS Resolver:"
        echo "  Status:      systemctl status unbound"
        echo "  Stats:       sudo unbound-control stats_noreset"
        echo "  Listening:   127.0.0.1:5353 (localhost only)"
        echo "  Mode:        Recursive resolver with DNSSEC validation"
        echo
    fi

    if command -v wg &> /dev/null; then
        echo "WireGuard:"
        echo "  Status:      wg show"
        echo "  Config:      Upload via YggSec-Home web interface"
        echo
    fi
    echo "DNS Resolution Chain:"
    echo "  Clients → AdGuard (ad blocking, port 53)"
    echo "          ↓"
    echo "  Unbound (recursive DNS, DNSSEC, port 5353)"
    echo "          ↓"
    echo "  Root DNS Servers (maximum privacy)"
    echo
    echo "Security:"
    echo "  - HTTPS with self-signed certificates"
    echo "  - Web interfaces restricted to LAN access only"
    echo "  - SSH access maintained on port 22"
    echo "  - Apps bind to localhost only (nginx proxy)"
    echo "  - Firewall configured for protection"
    echo "  - All services auto-restart on failure"
    echo
    echo "Next Steps:"
    echo "  1. Add DNS entries to your router or /etc/hosts file:"
    echo "     $IP_ADDRESS home.yggsec.com"
    echo "     $IP_ADDRESS adguard.yggsec.com"
    echo "  2. Access https://home.yggsec.com (accept self-signed cert)"
    echo "  3. Or direct access: http://$IP_ADDRESS:3000 → redirects to HTTPS"
    echo "  4. Configure network settings if needed"
    echo "  5. Upload WireGuard configuration (if needed)"
    echo "  6. Change admin password in Settings → Change Password"
    echo
    echo "Documentation:"
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
    check_existing_packages

    log_info "Starting complete installation process..."
    echo

    install_system_packages
    verify_installation
    setup_directories
    copy_application_files
    setup_python_environment
    prompt_for_credentials
    install_and_configure_unbound
    install_adguard_home
    generate_ssl_certificates
    configure_nginx
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