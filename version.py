"""
YggSec-Home Version Management
"""

VERSION = "1.0.0"
BUILD_DATE = "2025-09-19"
RELEASE_CHANNEL = "stable"  # stable, beta, dev

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
