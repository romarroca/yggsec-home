# YggSec-Home: Lightweight Parental Control for DietPi

YggSec-Home is a plug-and-play parental control solution designed for ARM SBCs running DietPi. It provides a simple web interface to manage AdGuard Home, WireGuard VPN, and basic system functions.

## Features

- **Lightweight Web GUI**: <200 MB RAM usage, responsive mobile-friendly interface
- **Network Management**: Configure static IP or DHCP settings
- **AdGuard Home Integration**: Start/stop/restart DNS filtering service with dashboard link
- **WireGuard VPN**: Upload and manage VPN configurations with secure validation
- **System Management**: Reboot, update, and password management
- **Dark/Light Theme**: Consistent with YggSec design language
- **LAN-Only Access**: Secure defaults with firewall protection

## Hardware Requirements

### Supported Platforms
- **ARM SBCs**: NanoPi Zero2, Raspberry Pi Zero2 W, Raspberry Pi 4, etc.
- **Development**: VMware x86_64 with DietPi

### Minimum Specifications
- **RAM**: 512MB (application uses <200MB)
- **Storage**: 4GB SD card/eMMC
- **Network**: Ethernet or WiFi connection

## Quick Start

### 🚀 Development Setup (After Cloning)

```bash
# Clone the repository
git clone https://github.com/romarroca/yggsec-home.git
cd yggsec-home

# One-command setup for development
./init.sh

# Start development server
./run.sh
```

**Access**: `http://localhost:5000`

### 🏠 Production Setup (DietPi)

### 1. DietPi Base Setup

Flash DietPi to your SD card and complete initial setup:

```bash
# First boot - follow DietPi setup wizard
# Enable SSH, set passwords, configure network
```

### 2. Install Dependencies

```bash
# Update system
sudo apt update && sudo apt upgrade -y

# Install Python and dependencies
sudo apt install -y python3 python3-pip python3-venv git

# Install system utilities
sudo apt install -y wireguard-tools iptables-persistent
```

### 3. Install AdGuard Home (Optional)

```bash
# Download and install AdGuard Home
curl -s -S -L https://raw.githubusercontent.com/AdguardTeam/AdGuardHome/master/scripts/install.sh | sh -s -- -v

# Configure AdGuard to start on boot
sudo systemctl enable AdGuardHome
```

### 4. Deploy YggSec-Home

```bash
# Clone repository
sudo git clone https://github.com/romarroca/yggsec-home.git /opt/yggsec-home
cd /opt/yggsec-home

# Create virtual environment
sudo python3 -m venv venv
sudo ./venv/bin/pip install -r requirements.txt

# Set permissions
sudo chown -R root:root /opt/yggsec-home
sudo chmod +x scripts/*.sh

# Create required directories
sudo mkdir -p /opt/yggsec-home/{logs,uploads}
```

### 5. Configure Services

```bash
# Install systemd services
sudo cp systemd/yggsec-home.service /etc/systemd/system/
sudo cp systemd/yggsec-home-firewall.service /etc/systemd/system/

# Set production secret key
sudo nano /etc/systemd/system/yggsec-home.service
# Change: Environment=SECRET_KEY=your-random-secret-key-here

# Enable and start services
sudo systemctl daemon-reload
sudo systemctl enable yggsec-home-firewall.service
sudo systemctl enable yggsec-home.service
sudo systemctl start yggsec-home-firewall.service
sudo systemctl start yggsec-home.service
```

### 6. Access Web Interface

Open your browser and navigate to:
- **Local access**: `http://dietpi-ip-address:5000`
- **mDNS access**: `http://yggsec-home.local:5000` (if mDNS is configured)

## Configuration

### Network Configuration

Configure your DietPi device's network settings through the web interface:

1. Navigate to **Settings → Network**
2. Choose between DHCP (automatic) or Static IP
3. For static IP, provide:
   - IP Address (e.g., 192.168.1.100)
   - Network Mask (e.g., 24)
   - Gateway (e.g., 192.168.1.1)
   - DNS Servers (e.g., 8.8.8.8, 8.8.4.4)

### AdGuard Home Setup

1. Install AdGuard Home (see installation steps above)
2. Access AdGuard dashboard at `http://dietpi-ip:3000`
3. Complete initial AdGuard setup
4. Use YggSec-Home interface to start/stop/restart the service

### WireGuard VPN Configuration

1. Generate or obtain a WireGuard configuration file (.conf)
2. In YggSec-Home, click **Upload VPN Config**
3. Select your .conf file (must be <16KB)
4. Use **Connect/Disconnect** buttons to manage the tunnel

Example WireGuard client configuration:
```ini
[Interface]
PrivateKey = your-private-key-here
Address = 10.0.0.2/24
DNS = 8.8.8.8

[Peer]
PublicKey = server-public-key-here
Endpoint = your-server.com:51820
AllowedIPs = 0.0.0.0/0
```

## Security Features

### Firewall Protection
- Web interface accessible only from LAN (192.168.x.x, 10.x.x.x, 172.16-31.x.x)
- SSH access maintained on port 22
- WireGuard port 51820 opened for VPN access

### File Upload Security
- WireGuard configs limited to 16KB
- File extension validation (.conf only)
- Configuration content validation (prevents command injection)
- Secure file permissions (600)

### System Security
- Systemd service runs with minimal privileges
- Read-only filesystem protection where possible
- Capability-based access control
- Password complexity requirements

## DietPi-Specific Optimizations

### Memory Usage
- Flask application optimized for <200MB RAM
- Minimal dependencies (no heavy frameworks)
- Efficient CSS/JS (Bootstrap 5.3 + custom styles)

### Storage Efficiency
- Log rotation configured
- Minimal static assets
- Compressed JavaScript/CSS delivery

### System Integration
- Uses DietPi-update when available
- Compatible with DietPi network configuration
- Respects DietPi service management

## API Reference

### Network Management
```bash
# Get network status
curl http://localhost:5000/api/network/status

# Configure static IP
curl -X POST http://localhost:5000/api/network/configure \
  -H "Content-Type: application/json" \
  -d '{"mode":"static","ip_address":"192.168.1.100","netmask":"24","gateway":"192.168.1.1","dns_servers":["8.8.8.8"]}'
```

### AdGuard Control
```bash
# Start AdGuard
curl -X POST http://localhost:5000/api/adguard/control \
  -H "Content-Type: application/json" \
  -d '{"action":"start"}'

# Get AdGuard status
curl http://localhost:5000/api/adguard/status
```

### WireGuard Management
```bash
# Upload config
curl -X POST http://localhost:5000/api/wireguard/upload \
  -F "config_file=@/path/to/config.conf"

# Start tunnel
curl -X POST http://localhost:5000/api/wireguard/control \
  -H "Content-Type: application/json" \
  -d '{"action":"start"}'
```

### System Operations
```bash
# Get system info
curl http://localhost:5000/api/system/info

# Reboot system
curl -X POST http://localhost:5000/api/system/control \
  -H "Content-Type: application/json" \
  -d '{"action":"reboot"}'
```

## Troubleshooting

### Service Issues
```bash
# Check service status
sudo systemctl status yggsec-home

# View logs
sudo journalctl -u yggsec-home -f

# Restart service
sudo systemctl restart yggsec-home
```

### Network Issues
```bash
# Check if service is listening
sudo netstat -tlnp | grep :5000

# Check firewall rules
sudo iptables -L INPUT -n

# Test local access
curl http://localhost:5000
```

### Permission Issues
```bash
# Fix file permissions
sudo chown -R root:root /opt/yggsec-home
sudo chmod 600 /etc/wireguard/*.conf
sudo chmod +x /opt/yggsec-home/scripts/*.sh
```

### Memory Issues
```bash
# Check memory usage
free -h
ps aux | grep python

# Monitor resource usage
htop
```

## Development

### Local Development Setup
```bash
# Clone repository
git clone https://github.com/romarroca/yggsec-home.git
cd yggsec-home

# One-command initialization
./init.sh

# Start development server
./run.sh

# Alternative manual start:
source venv/bin/activate
export FLASK_ENV=development
python app.py
```

### Testing on VMware
1. Install DietPi in VMware VM
2. Configure bridged networking
3. Follow installation steps above
4. Test all functionality before deploying to ARM SBC

## Contributing

1. Fork the repository
2. Create a feature branch
3. Follow coding standards in CLAUDE.md
4. Test on both x86_64 VMware and ARM hardware
5. Submit pull request with security review

## License

This project follows secure coding standards and is designed for educational and personal use. See CLAUDE.md for coding standards and security requirements.

## Support

- **Issues**: Report bugs and feature requests via GitHub Issues
- **Documentation**: Additional documentation in the `/docs` directory
- **Security**: Report security issues privately to maintainers

---

**YggSec-Home v1.0** - Secure, Simple, Lightweight Parental Control for DietPi