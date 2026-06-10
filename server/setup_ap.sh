#!/bin/bash
# Configures wlan0 as a permanent Wi-Fi access point.
# Run once as root: sudo bash setup_ap.sh
set -e

IFACE=wlan0
AP_IP=192.168.4.1
DHCP_START=192.168.4.2
DHCP_END=192.168.4.20
DHCP_LEASE=24h
DEFAULT_PASSWORD="comfort1234"   # printed on device label

# Last 4 hex chars of MAC (no colons), uppercased
MAC=$(cat /sys/class/net/$IFACE/address | tr -d ':')
SUFFIX=$(echo "${MAC: -4}" | tr '[:lower:]' '[:upper:]')
SSID="ThermalComfort-$SUFFIX"

echo "==> Installing hostapd and dnsmasq"
apt-get update -qq
apt-get install -y hostapd dnsmasq

echo "==> Stopping services for configuration"
systemctl stop hostapd dnsmasq 2>/dev/null || true
systemctl unmask hostapd

echo "==> Setting static IP on $IFACE"
if ! grep -q "interface $IFACE" /etc/dhcpcd.conf; then
    cat >> /etc/dhcpcd.conf << EOF

interface $IFACE
    static ip_address=$AP_IP/24
    nohook wpa_supplicant
EOF
fi

echo "==> Writing dnsmasq config"
cat > /etc/dnsmasq.conf << EOF
interface=$IFACE
dhcp-range=$DHCP_START,$DHCP_END,$DHCP_LEASE
domain=local
address=/thermal.local/$AP_IP
EOF

echo "==> Writing hostapd config"
cat > /etc/hostapd/hostapd.conf << EOF
interface=$IFACE
driver=nl80211
ssid=$SSID
hw_mode=g
channel=7
wmm_enabled=0
macaddr_acl=0
auth_algs=1
ignore_broadcast_ssid=0
wpa=2
wpa_passphrase=$DEFAULT_PASSWORD
wpa_key_mgmt=WPA-PSK
wpa_pairwise=TKIP
rsn_pairwise=CCMP
EOF

# Point hostapd daemon to its config file
sed -i 's|#DAEMON_CONF=""|DAEMON_CONF="/etc/hostapd/hostapd.conf"|' /etc/default/hostapd

echo "==> Enabling and starting services"
systemctl enable hostapd dnsmasq
systemctl start dnsmasq
systemctl start hostapd

echo ""
echo "Done."
echo "  SSID:      $SSID"
echo "  Password:  $DEFAULT_PASSWORD"
echo "  Device IP: $AP_IP"
echo ""
echo "Print the SSID and password on the device label before shipping."
