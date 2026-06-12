#!/bin/bash
# Configures wlan0 as a permanent Wi-Fi AP.
# Uses NetworkManager for static IP + DHCP, and hostapd for WPA2.
# Run once as root: sudo bash server/setup_ap.sh
set -e

IFACE=wlan0
AP_IP=192.168.4.1
DEFAULT_PASSWORD="comfort1234"
CON_NAME="thermal-ap"
HOSTAPD_CONF=/etc/hostapd/hostapd.conf

# Last 4 hex chars of MAC, uppercased
MAC=$(cat /sys/class/net/$IFACE/address | tr -d ':')
SUFFIX=$(echo "${MAC: -4}" | tr '[:lower:]' '[:upper:]')
SSID="ThermalComfort-$SUFFIX"

# ── NetworkManager: static IP + DHCP for clients ───────────────────────────
echo "==> Removing any existing AP connection"
nmcli con delete "$CON_NAME" 2>/dev/null || true

echo "==> Creating NM connection for static IP and DHCP"
nmcli con add \
    type wifi \
    ifname "$IFACE" \
    con-name "$CON_NAME" \
    autoconnect yes \
    ssid "$SSID" \
    802-11-wireless.mode ap \
    802-11-wireless.band bg \
    ipv4.method shared \
    ipv4.addresses "$AP_IP/24"

nmcli con up "$CON_NAME"

# ── hostapd: WPA2 authentication ───────────────────────────────────────────
echo "==> Writing hostapd config"
cat > "$HOSTAPD_CONF" <<EOF
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

echo "==> Enabling hostapd service"
systemctl enable hostapd
systemctl restart hostapd

echo ""
echo "Done."
echo "  SSID:      $SSID"
echo "  Password:  $DEFAULT_PASSWORD"
echo "  Device IP: $AP_IP"
echo ""
echo "The AP will start automatically on every boot."
echo "Print the SSID and password on the device label before shipping."
