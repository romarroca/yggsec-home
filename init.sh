#!/bin/bash
# YggSec-Home Development Initialization Script
# Quick setup for development and testing

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

# Configuration
PYTHON_MIN_VERSION="3.8"
DEV_PORT="5000"

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

check_python() {
    log_info "Checking Python installation..."

    if ! command -v python3 &> /dev/null; then
        log_error "Python 3 is not installed. Please install Python 3.8+ first."
        echo "  Ubuntu/Debian: sudo apt install python3 python3-pip python3-venv"
        echo "  macOS: brew install python3"
        echo "  Windows: Download from python.org"
        exit 1
    fi

    PYTHON_VERSION=$(python3 -c 'import sys; print(".".join(map(str, sys.version_info[:2])))')
    log_info "Found Python $PYTHON_VERSION"

    # Simple version check
    if python3 -c "import sys; exit(0 if sys.version_info >= (3, 8) else 1)"; then
        log_success "Python version is compatible"
    else
        log_error "Python $PYTHON_MIN_VERSION+ is required, found $PYTHON_VERSION"
        exit 1
    fi
}

check_git() {
    if ! command -v git &> /dev/null; then
        log_warning "Git is not installed. Some features may not work."
        echo "  Ubuntu/Debian: sudo apt install git"
        echo "  macOS: brew install git"
        echo "  Windows: Download from git-scm.com"
    else
        log_success "Git is available"
    fi
}

setup_virtual_environment() {
    log_info "Setting up Python virtual environment..."

    if [[ -d "venv" ]]; then
        log_warning "Virtual environment already exists, removing..."
        rm -rf venv
    fi

    python3 -m venv venv
    log_success "Virtual environment created"

    # Activate virtual environment
    if [[ "$OSTYPE" == "msys" || "$OSTYPE" == "win32" ]]; then
        source venv/Scripts/activate
    else
        source venv/bin/activate
    fi

    log_info "Virtual environment activated"
}

install_dependencies() {
    log_info "Installing Python dependencies..."

    # Upgrade pip first
    pip install --upgrade pip

    # Install requirements
    pip install -r requirements.txt

    log_success "Dependencies installed"
}

create_directories() {
    log_info "Creating required directories..."

    mkdir -p logs
    mkdir -p uploads

    # Create empty log file
    touch logs/yggsec-home.log

    log_success "Directories created"
}

setup_development_config() {
    log_info "Setting up development configuration..."

    # Create development environment file
    cat > .env.dev << EOF
# YggSec-Home Development Configuration
FLASK_ENV=development
FLASK_DEBUG=true
SECRET_KEY=dev-key-change-in-production-$(date +%s)

# Development settings
BIND_HOST=127.0.0.1
BIND_PORT=$DEV_PORT
DEBUG=true

# Paths (relative to project root)
LOG_DIR=./logs
UPLOAD_DIR=./uploads

# Development database (if needed)
DATABASE_URL=sqlite:///yggsec-home-dev.db
EOF

    log_success "Development configuration created (.env.dev)"
}

check_optional_dependencies() {
    log_info "Checking optional system dependencies..."

    # Check for WireGuard
    if command -v wg &> /dev/null; then
        log_success "WireGuard tools found"
    else
        log_warning "WireGuard tools not found - VPN features will be limited"
        echo "  Ubuntu/Debian: sudo apt install wireguard-tools"
        echo "  macOS: brew install wireguard-tools"
    fi

    # Check for systemctl (Linux systems)
    if command -v systemctl &> /dev/null; then
        log_success "systemctl found - system management available"
    else
        log_warning "systemctl not found - some system features disabled"
    fi

    # Check for network tools
    if command -v ip &> /dev/null; then
        log_success "Network tools (ip) found"
    else
        log_warning "Network configuration tools not found"
        echo "  Ubuntu/Debian: sudo apt install iproute2"
    fi
}

create_run_script() {
    log_info "Creating run script..."

    cat > run.sh << 'EOF'
#!/bin/bash
# YggSec-Home Development Runner

# Colors
GREEN='\033[0;32m'
BLUE='\033[0;34m'
NC='\033[0m'

echo -e "${BLUE}Starting YggSec-Home Development Server...${NC}"

# Check if virtual environment exists
if [[ ! -d "venv" ]]; then
    echo "Virtual environment not found. Run ./init.sh first."
    exit 1
fi

# Activate virtual environment
if [[ "$OSTYPE" == "msys" || "$OSTYPE" == "win32" ]]; then
    source venv/Scripts/activate
else
    source venv/bin/activate
fi

# Load development environment
if [[ -f ".env.dev" ]]; then
    export $(cat .env.dev | grep -v '^#' | xargs)
fi

# Set development defaults if not set
export FLASK_ENV=${FLASK_ENV:-development}
export FLASK_DEBUG=${FLASK_DEBUG:-true}
export SECRET_KEY=${SECRET_KEY:-dev-key-please-change}

echo -e "${GREEN}Environment loaded:${NC}"
echo "  FLASK_ENV: $FLASK_ENV"
echo "  DEBUG: $FLASK_DEBUG"
echo "  PORT: ${BIND_PORT:-5000}"
echo ""

echo -e "${BLUE}Access your application at:${NC}"
echo "  http://localhost:${BIND_PORT:-5000}"
echo ""
echo "Press Ctrl+C to stop the server"
echo ""

# Run the application
python app.py
EOF

    chmod +x run.sh
    log_success "Run script created (./run.sh)"
}

show_completion() {
    local IP_ADDRESS=$(hostname -I 2>/dev/null | awk '{print $1}' || echo "localhost")

    echo ""
    echo "=================================================="
    log_success "YggSec-Home Development Setup Complete!"
    echo "=================================================="
    echo ""
    echo "🚀 Quick Start:"
    echo "  ./run.sh                 # Start development server"
    echo ""
    echo "🌐 Access URLs:"
    echo "  http://localhost:$DEV_PORT"
    if [[ "$IP_ADDRESS" != "localhost" ]]; then
        echo "  http://$IP_ADDRESS:$DEV_PORT"
    fi
    echo ""
    echo "📁 Project Structure:"
    echo "  app.py                   # Main application"
    echo "  config.py                # Configuration"
    echo "  services/                # Service modules"
    echo "  templates/               # HTML templates"
    echo "  static/                  # CSS, JS, images"
    echo "  logs/                    # Application logs"
    echo ""
    echo "🛠️ Development Commands:"
    echo "  source venv/bin/activate # Activate virtual env"
    echo "  pip install <package>    # Install new package"
    echo "  pip freeze > requirements.txt # Update requirements"
    echo ""
    echo "⚙️ Configuration:"
    echo "  .env.dev                 # Development settings"
    echo "  Edit this file to customize settings"
    echo ""
    echo "📚 Documentation:"
    echo "  README.md                # Full documentation"
    echo "  API endpoints documented in app.py"
    echo ""

    if command -v systemctl &> /dev/null; then
        echo "🔧 Production Deployment:"
        echo "  sudo ./scripts/install-dietpi.sh  # Full system install"
    fi

    echo ""
    log_info "Ready for development! Run './run.sh' to start the server."
}

# Main execution
main() {
    echo "=================================================="
    echo "  YggSec-Home Development Initialization"
    echo "=================================================="
    echo ""

    # Check if we're in the right directory
    if [[ ! -f "app.py" ]] || [[ ! -f "requirements.txt" ]]; then
        log_error "This script must be run from the YggSec-Home project directory"
        echo "Make sure you're in the directory containing app.py and requirements.txt"
        exit 1
    fi

    log_info "Initializing YggSec-Home development environment..."
    echo ""

    check_python
    check_git
    setup_virtual_environment
    install_dependencies
    create_directories
    setup_development_config
    check_optional_dependencies
    create_run_script
    show_completion
}

# Error handling
trap 'log_error "Initialization failed at line $LINENO. Check the output above."' ERR

# Run main function
main "$@"