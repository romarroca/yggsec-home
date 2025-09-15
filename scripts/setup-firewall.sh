#!/bin/bash
# YggSec-Home Firewall Setup Script

set -e

# Configuration
WEB_PORT=5000
SSH_PORT=22
INTERFACE=$(ip route | grep default | awk '{print $5}' | head -n1)

echo "Setting up YggSec-Home firewall rules..."

# Check if iptables is available
if ! command -v iptables &> /dev/null; then
    echo "iptables not found, installing..."
    apt-get update
    apt-get install -y iptables iptables-persistent
fi

# Flush existing rules (be careful!)
iptables -F INPUT
iptables -F FORWARD
iptables -F OUTPUT

# Set default policies
iptables -P INPUT DROP
iptables -P FORWARD ACCEPT
iptables -P OUTPUT ACCEPT

# Allow loopback traffic
iptables -A INPUT -i lo -j ACCEPT

# Allow established and related connections
iptables -A INPUT -m conntrack --ctstate ESTABLISHED,RELATED -j ACCEPT

# Allow SSH (important - don't lock yourself out!)
iptables -A INPUT -p tcp --dport $SSH_PORT -j ACCEPT

# Allow YggSec-Home web interface only from LAN
if [ -n "$INTERFACE" ]; then
    # Get the network range for the interface
    NETWORK=$(ip route | grep $INTERFACE | grep -E '^192\.168\.|^10\.|^172\.(1[6-9]|2[0-9]|3[01])\.' | head -n1 | awk '{print $1}')

    if [ -n "$NETWORK" ]; then
        echo "Allowing YggSec-Home access from LAN network: $NETWORK"
        iptables -A INPUT -p tcp --dport $WEB_PORT -s $NETWORK -j ACCEPT
    else
        echo "Could not determine LAN network, allowing from private ranges"
        iptables -A INPUT -p tcp --dport $WEB_PORT -s 192.168.0.0/16 -j ACCEPT
        iptables -A INPUT -p tcp --dport $WEB_PORT -s 10.0.0.0/8 -j ACCEPT
        iptables -A INPUT -p tcp --dport $WEB_PORT -s 172.16.0.0/12 -j ACCEPT
    fi
else
    echo "Warning: Could not determine network interface"
    iptables -A INPUT -p tcp --dport $WEB_PORT -s 192.168.0.0/16 -j ACCEPT
    iptables -A INPUT -p tcp --dport $WEB_PORT -s 10.0.0.0/8 -j ACCEPT
    iptables -A INPUT -p tcp --dport $WEB_PORT -s 172.16.0.0/12 -j ACCEPT
fi

# Allow ICMP (ping)
iptables -A INPUT -p icmp --icmp-type echo-request -j ACCEPT

# Allow DHCP client
iptables -A INPUT -p udp --sport 67 --dport 68 -j ACCEPT

# Allow DNS queries
iptables -A INPUT -p udp --sport 53 -j ACCEPT
iptables -A INPUT -p tcp --sport 53 -j ACCEPT

# Allow AdGuard Home (if configured)
# iptables -A INPUT -p tcp --dport 3000 -s 192.168.0.0/16 -j ACCEPT
# iptables -A INPUT -p udp --dport 53 -j ACCEPT

# Allow WireGuard
iptables -A INPUT -p udp --dport 51820 -j ACCEPT

# Log dropped packets (optional)
iptables -A INPUT -m limit --limit 5/min -j LOG --log-prefix "iptables denied: " --log-level 7

# Save rules
if command -v iptables-save &> /dev/null; then
    iptables-save > /etc/iptables/rules.v4
    echo "Firewall rules saved to /etc/iptables/rules.v4"
fi

echo "YggSec-Home firewall setup complete!"
echo "Web interface accessible on port $WEB_PORT from LAN only"
echo "SSH accessible on port $SSH_PORT"

# Display current rules
echo ""
echo "Current INPUT rules:"
iptables -L INPUT -n --line-numbers