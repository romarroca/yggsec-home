#!/bin/bash
# YggSec-Home Firewall Cleanup Script

set -e

echo "Cleaning up YggSec-Home firewall rules..."

# Flush YggSec-Home specific rules
iptables -D INPUT -p tcp --dport 5000 -s 192.168.0.0/16 -j ACCEPT 2>/dev/null || true
iptables -D INPUT -p tcp --dport 5000 -s 10.0.0.0/8 -j ACCEPT 2>/dev/null || true
iptables -D INPUT -p tcp --dport 5000 -s 172.16.0.0/12 -j ACCEPT 2>/dev/null || true

echo "YggSec-Home firewall cleanup complete!"