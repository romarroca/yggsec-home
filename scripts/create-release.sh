#!/bin/bash
# YggSec-Home Release Creation Script

set -e

# Configuration
REPO_DIR="$(pwd)"
BUILD_DIR="/tmp/yggsec-build"
RELEASE_DIR="/tmp/yggsec-release"

# Colors for output
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

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

usage() {
    echo "Usage: $0 <version> [release_type]"
    echo "  version: Version number (e.g., 1.0.1)"
    echo "  release_type: stable|beta|dev (default: stable)"
    echo ""
    echo "Examples:"
    echo "  $0 1.0.1"
    echo "  $0 1.1.0-beta beta"
    exit 1
}

check_requirements() {
    log_info "Checking requirements..."

    # Check if running as root (warn but don't exit)
    if [[ $EUID -ne 0 ]]; then
        log_warning "Not running as root - some operations may require sudo"
    fi

    # Check required tools
    for tool in git tar shasum; do
        if ! command -v $tool &> /dev/null; then
            log_error "Required tool '$tool' not found"
            exit 1
        fi
    done

    # Check if we're in a git repository
    if ! git rev-parse --git-dir > /dev/null 2>&1; then
        log_error "Not in a git repository"
        exit 1
    fi

    log_success "Requirements check passed"
}

update_version() {
    local version=$1
    local release_type=$2
    local build_date=$(date +%Y-%m-%d)

    log_info "Updating version to $version..."

    # Update version.py
    cat > version.py << EOF
"""
YggSec-Home Version Management
"""

VERSION = "$version"
BUILD_DATE = "$build_date"
RELEASE_CHANNEL = "$release_type"  # stable, beta, dev

def get_version_info():
    return {
        "version": VERSION,
        "build_date": BUILD_DATE,
        "release_channel": RELEASE_CHANNEL
    }

def compare_versions(current, latest):
    """Compare version strings (semantic versioning)"""
    def version_tuple(v):
        return tuple(map(int, v.replace('v', '').split('.')))

    current_tuple = version_tuple(current)
    latest_tuple = version_tuple(latest)

    if latest_tuple > current_tuple:
        return "update_available"
    elif latest_tuple == current_tuple:
        return "up_to_date"
    else:
        return "ahead"  # Development version
EOF

    log_success "Version updated to $version"
}

create_release_package() {
    local version=$1

    log_info "Creating release package..."

    # Clean build directories
    rm -rf "$BUILD_DIR" "$RELEASE_DIR"
    mkdir -p "$BUILD_DIR" "$RELEASE_DIR"

    # Copy source files (exclude development files)
    rsync -av \
        --exclude='.git*' \
        --exclude='venv' \
        --exclude='.venv' \
        --exclude='__pycache__' \
        --exclude='*.pyc' \
        --exclude='logs/*' \
        --exclude='uploads/*' \
        --exclude='bandit-report.json' \
        --exclude='.pytest_cache' \
        --exclude='requirements.txt' \
        --include='requirements-prod.txt' \
        . "$BUILD_DIR/yggsec-home-$version/"

    log_info "Ensuring requirements-prod.txt is included..."
    if [ -f "requirements-prod.txt" ]; then
        cp requirements-prod.txt "$BUILD_DIR/yggsec-home-$version/"
        log_success "Production requirements file included"
    else
        log_warning "requirements-prod.txt not found"
    fi

    # Create release archive
    cd "$BUILD_DIR"
    tar -czf "$RELEASE_DIR/yggsec-home-$version.tar.gz" "yggsec-home-$version/"

    # Generate checksums
    cd "$RELEASE_DIR"
    shasum -a 256 "yggsec-home-$version.tar.gz" > "yggsec-home-$version.sha256"

    log_success "Release package created: $RELEASE_DIR/yggsec-home-$version.tar.gz"
    log_info "Checksum file: $RELEASE_DIR/yggsec-home-$version.sha256"
}

create_git_tag() {
    local version=$1

    log_info "Creating git tag v$version..."

    # Commit version changes
    git add version.py
    git commit -m "feat: release version $version"

    # Create tag
    git tag -a "v$version" -m "Release version $version"

    log_success "Git tag v$version created"
}

show_release_info() {
    local version=$1

    echo ""
    log_success "Release $version created successfully!"
    echo ""
    echo "Next steps:"
    echo "1. Push changes and tags:"
    echo "   git push origin main"
    echo "   git push origin v$version"
    echo ""
    echo "2. Create GitHub release:"
    echo "   - Go to https://github.com/romarroca/yggsec-home/releases/new"
    echo "   - Select tag: v$version"
    echo "   - Upload files:"
    echo "     - $RELEASE_DIR/yggsec-home-$version.tar.gz"
    echo "     - $RELEASE_DIR/yggsec-home-$version.sha256"
    echo ""
    echo "3. Test automatic update:"
    echo "   - Deploy to test device"
    echo "   - Check /api/system/update/check"
    echo ""
    echo "Release files location: $RELEASE_DIR"
    ls -la "$RELEASE_DIR"
}

main() {
    local version=$1
    local release_type=${2:-stable}

    if [[ -z "$version" ]]; then
        usage
    fi

    log_info "Creating release $version ($release_type)"

    check_requirements
    update_version "$version" "$release_type"
    create_release_package "$version"
    create_git_tag "$version"
    show_release_info "$version"
}

# Trap errors
trap 'log_error "Release creation failed at line $LINENO"' ERR

main "$@"