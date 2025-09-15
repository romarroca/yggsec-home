// YggSec-Home JavaScript

// CSRF protection helper
function getCSRFHeaders() {
    return {
        'X-CSRFToken': window.csrf_token,
        'Content-Type': 'application/json'
    };
}

// Theme management
function toggleTheme() {
    const html = document.documentElement;
    const themeIcon = document.getElementById('theme-icon');

    if (html.getAttribute('data-bs-theme') === 'light') {
        html.setAttribute('data-bs-theme', 'dark');
        themeIcon.className = 'bi bi-sun-fill';
        localStorage.setItem('theme', 'dark');
    } else {
        html.setAttribute('data-bs-theme', 'light');
        themeIcon.className = 'bi bi-moon-fill';
        localStorage.setItem('theme', 'light');
    }
}

// Initialize theme on page load
document.addEventListener('DOMContentLoaded', function() {
    const savedTheme = localStorage.getItem('theme') || 'light';
    const html = document.documentElement;
    const themeIcon = document.getElementById('theme-icon');

    html.setAttribute('data-bs-theme', savedTheme);
    themeIcon.className = savedTheme === 'dark' ? 'bi bi-sun-fill' : 'bi bi-moon-fill';
});

// Network Management
function showNetworkModal() {
    // Load current network configuration
    fetch('/api/network/status')
        .then(response => response.json())
        .then(data => {
            if (data.success && data.config) {
                const config = data.config;
                document.getElementById('networkMode').value = config.mode || 'dhcp';

                if (config.mode === 'static') {
                    document.getElementById('ipAddress').value = config.ip || '';
                    document.getElementById('netmask').value = config.netmask || '';
                    document.getElementById('gateway').value = config.gateway || '';
                    document.getElementById('dnsServers').value = config.dns ? config.dns.join(', ') : '';
                }

                toggleNetworkFields();
            }
        })
        .catch(error => {
            console.error('Error loading network config:', error);
            showAlert('Failed to load network configuration', 'danger');
        });

    const modal = new bootstrap.Modal(document.getElementById('networkModal'));
    modal.show();
}

function toggleNetworkFields() {
    const mode = document.getElementById('networkMode').value;
    const staticFields = document.getElementById('staticFields');

    if (mode === 'static') {
        staticFields.style.display = 'block';
    } else {
        staticFields.style.display = 'none';
    }
}

// Handle network configuration form submission
document.addEventListener('DOMContentLoaded', function() {
    const networkForm = document.getElementById('networkForm');
    if (networkForm) {
        networkForm.addEventListener('submit', function(e) {
            e.preventDefault();

            const mode = document.getElementById('networkMode').value;
            const data = { mode: mode };

            if (mode === 'static') {
                data.ip_address = document.getElementById('ipAddress').value.trim();
                data.netmask = document.getElementById('netmask').value.trim();
                data.gateway = document.getElementById('gateway').value.trim();
                data.dns_servers = document.getElementById('dnsServers').value
                    .split(',')
                    .map(dns => dns.trim())
                    .filter(dns => dns.length > 0);

                // Basic validation
                if (!data.ip_address || !data.netmask || !data.gateway) {
                    showAlert('Please fill in all required fields', 'danger');
                    return;
                }
            }

            // Show loading state
            const submitBtn = e.target.querySelector('button[type="submit"]');
            const originalText = submitBtn.textContent;
            submitBtn.disabled = true;
            submitBtn.innerHTML = '<span class="spinner-border spinner-border-sm me-2"></span>Applying...';

            fetch('/api/network/configure', {
                method: 'POST',
                headers: getCSRFHeaders(),
                body: JSON.stringify(data)
            })
            .then(response => response.json())
            .then(data => {
                if (data.success) {
                    showAlert(data.message, 'success');
                    bootstrap.Modal.getInstance(document.getElementById('networkModal')).hide();
                } else {
                    showAlert(data.error, 'danger');
                }
            })
            .catch(error => {
                console.error('Error:', error);
                showAlert('Network configuration failed', 'danger');
            })
            .finally(() => {
                submitBtn.disabled = false;
                submitBtn.textContent = originalText;
            });
        });
    }
});

// AdGuard Management
function adguardControl(action) {
    const data = { action: action };

    fetch('/api/adguard/control', {
        method: 'POST',
        headers: getCSRFHeaders(),
        body: JSON.stringify(data)
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            showAlert(data.message, 'success');
        } else {
            showAlert(data.message || 'AdGuard operation failed', 'danger');
        }
    })
    .catch(error => {
        console.error('Error:', error);
        showAlert('AdGuard operation failed', 'danger');
    });
}

// WireGuard Management
function showWireguardModal() {
    const modal = new bootstrap.Modal(document.getElementById('wireguardModal'));
    modal.show();
}

function showWireguardEditModal() {
    // Load current configuration
    fetch('/api/wireguard/config')
        .then(response => response.json())
        .then(data => {
            if (data.success) {
                document.getElementById('configContent').value = data.config;
            } else {
                document.getElementById('configContent').value = '';
                showAlert('Failed to load configuration: ' + data.error, 'danger');
            }
        })
        .catch(error => {
            console.error('Error loading config:', error);
            document.getElementById('configContent').value = '';
            showAlert('Failed to load configuration', 'danger');
        });

    const modal = new bootstrap.Modal(document.getElementById('wireguardEditModal'));
    modal.show();
}

function wireguardControl(action) {
    const data = { action: action };

    fetch('/api/wireguard/control', {
        method: 'POST',
        headers: getCSRFHeaders(),
        body: JSON.stringify(data)
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            showAlert(data.message, 'success');
        } else {
            showAlert(data.message || 'WireGuard operation failed', 'danger');
        }
    })
    .catch(error => {
        console.error('Error:', error);
        showAlert('WireGuard operation failed', 'danger');
    });
}

// Handle WireGuard file upload
document.addEventListener('DOMContentLoaded', function() {
    const wireguardForm = document.getElementById('wireguardForm');
    if (wireguardForm) {
        wireguardForm.addEventListener('submit', function(e) {
            e.preventDefault();

            const fileInput = document.getElementById('configFile');
            const file = fileInput.files[0];

            if (!file) {
                showAlert('Please select a configuration file', 'danger');
                return;
            }

            if (!file.name.toLowerCase().endsWith('.conf')) {
                showAlert('Only .conf files are allowed', 'danger');
                return;
            }

            const formData = new FormData();
            formData.append('config_file', file);
            formData.append('csrf_token', window.csrf_token);

            // Show loading state
            const submitBtn = e.target.querySelector('button[type="submit"]');
            const originalText = submitBtn.textContent;
            submitBtn.disabled = true;
            submitBtn.innerHTML = '<span class="spinner-border spinner-border-sm me-2"></span>Uploading...';

            fetch('/api/wireguard/upload', {
                method: 'POST',
                body: formData
            })
            .then(response => response.json())
            .then(data => {
                if (data.success) {
                    showAlert(data.message, 'success');
                    bootstrap.Modal.getInstance(document.getElementById('wireguardModal')).hide();
                    fileInput.value = '';
                } else {
                    showAlert(data.message || 'Upload failed', 'danger');
                }
            })
            .catch(error => {
                console.error('Error:', error);
                showAlert('Upload failed', 'danger');
            })
            .finally(() => {
                submitBtn.disabled = false;
                submitBtn.textContent = originalText;
            });
        });
    }
});

// Handle WireGuard edit form
document.addEventListener('DOMContentLoaded', function() {
    const wireguardEditForm = document.getElementById('wireguardEditForm');
    if (wireguardEditForm) {
        wireguardEditForm.addEventListener('submit', function(e) {
            e.preventDefault();

            const configContent = document.getElementById('configContent').value.trim();

            if (!configContent) {
                showAlert('Configuration content cannot be empty', 'danger');
                return;
            }

            // Show loading state
            const submitBtn = e.target.querySelector('button[type="submit"]');
            const originalText = submitBtn.textContent;
            submitBtn.disabled = true;
            submitBtn.innerHTML = '<span class="spinner-border spinner-border-sm me-2"></span>Saving...';

            fetch('/api/wireguard/save', {
                method: 'POST',
                headers: getCSRFHeaders(),
                body: JSON.stringify({ config: configContent })
            })
            .then(response => response.json())
            .then(data => {
                if (data.success) {
                    showAlert(data.message, 'success');
                    bootstrap.Modal.getInstance(document.getElementById('wireguardEditModal')).hide();
                } else {
                    showAlert(data.message || 'Save failed', 'danger');
                }
            })
            .catch(error => {
                console.error('Error:', error);
                showAlert('Save failed', 'danger');
            })
            .finally(() => {
                submitBtn.disabled = false;
                submitBtn.textContent = originalText;
            });
        });
    }
});

// Password Management
function showPasswordModal() {
    const modal = new bootstrap.Modal(document.getElementById('passwordModal'));
    modal.show();
}

function generatePassword() {
    fetch('/api/system/generate-password')
        .then(response => response.json())
        .then(data => {
            if (data.success) {
                document.getElementById('newPassword').value = data.password;
                document.getElementById('confirmPassword').value = data.password;
            } else {
                showAlert('Failed to generate password', 'danger');
            }
        })
        .catch(error => {
            console.error('Error:', error);
            showAlert('Failed to generate password', 'danger');
        });
}

// Handle password change form
document.addEventListener('DOMContentLoaded', function() {
    const passwordForm = document.getElementById('passwordForm');
    if (passwordForm) {
        passwordForm.addEventListener('submit', function(e) {
            e.preventDefault();

            const newPassword = document.getElementById('newPassword').value;
            const confirmPassword = document.getElementById('confirmPassword').value;

            if (newPassword !== confirmPassword) {
                showAlert('Passwords do not match', 'danger');
                return;
            }

            if (newPassword.length < 8) {
                showAlert('Password must be at least 8 characters long', 'danger');
                return;
            }

            const data = { new_password: newPassword };

            // Show loading state
            const submitBtn = e.target.querySelector('button[type="submit"]');
            const originalText = submitBtn.textContent;
            submitBtn.disabled = true;
            submitBtn.innerHTML = '<span class="spinner-border spinner-border-sm me-2"></span>Changing...';

            fetch('/api/system/password', {
                method: 'POST',
                headers: getCSRFHeaders(),
                body: JSON.stringify(data)
            })
            .then(response => response.json())
            .then(data => {
                if (data.success) {
                    showAlert(data.message, 'success');
                    bootstrap.Modal.getInstance(document.getElementById('passwordModal')).hide();
                    document.getElementById('newPassword').value = '';
                    document.getElementById('confirmPassword').value = '';
                } else {
                    showAlert(data.message || 'Password change failed', 'danger');
                }
            })
            .catch(error => {
                console.error('Error:', error);
                showAlert('Password change failed', 'danger');
            })
            .finally(() => {
                submitBtn.disabled = false;
                submitBtn.textContent = originalText;
            });
        });
    }
});

// System Management
function systemAction(action) {
    let confirmMessage = '';

    switch(action) {
        case 'reboot':
            confirmMessage = 'Are you sure you want to reboot the system? This will temporarily interrupt all services.';
            break;
        case 'shutdown':
            confirmMessage = 'Are you sure you want to shutdown the system? You will need physical access to turn it back on.';
            break;
        case 'update':
            confirmMessage = 'Are you sure you want to update the system? This may take several minutes.';
            break;
        default:
            return;
    }

    if (!confirm(confirmMessage)) {
        return;
    }

    const data = { action: action };

    fetch('/api/system/control', {
        method: 'POST',
        headers: getCSRFHeaders(),
        body: JSON.stringify(data)
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            showAlert(data.message, 'success');

            if (action === 'reboot' || action === 'shutdown') {
                showAlert('System ' + action + ' initiated. You will lose connection shortly.', 'warning');
            }
        } else {
            showAlert(data.message || 'System operation failed', 'danger');
        }
    })
    .catch(error => {
        console.error('Error:', error);
        showAlert('System operation failed', 'danger');
    });
}

// Utility Functions
function showAlert(message, type = 'info') {
    // Remove existing alerts
    const existingAlerts = document.querySelectorAll('.alert-custom');
    existingAlerts.forEach(alert => alert.remove());

    // Create new alert
    const alertDiv = document.createElement('div');
    alertDiv.className = `alert alert-${type} alert-dismissible fade show alert-custom`;
    alertDiv.innerHTML = `
        ${message}
        <button type="button" class="btn-close" data-bs-dismiss="alert"></button>
    `;

    // Insert at the top of main content
    const main = document.querySelector('main');
    main.insertBefore(alertDiv, main.firstChild);

    // Auto-dismiss after 5 seconds
    setTimeout(() => {
        if (alertDiv.parentNode) {
            bootstrap.Alert.getOrCreateInstance(alertDiv).close();
        }
    }, 5000);
}


// Loading state management
function setLoadingState(element, loading = true) {
    if (loading) {
        element.disabled = true;
        element.classList.add('loading');
        const originalText = element.textContent;
        element.dataset.originalText = originalText;
        element.innerHTML = '<span class="spinner-border spinner-border-sm me-2"></span>' + originalText;
    } else {
        element.disabled = false;
        element.classList.remove('loading');
        element.textContent = element.dataset.originalText || element.textContent;
    }
}

