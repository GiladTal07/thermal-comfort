#!/bin/bash
# Configures wlan0 as a permanent Wi-Fi AP using NetworkManager.
# Run once as root: sudo bash server/setup_ap.sh
set -e

IFACE=wlan0
AP_IP=192.168.4.1
DEFAULT_PASSWORD="comfort1234"
CON_NAME="thermal-ap"

# Last 4 hex chars of MAC, uppercased
MAC=$(cat /sys/class/net/$IFACE/address | tr -d ':')
SUFFIX=$(echo "${MAC: -4}" | tr '[:lower:]' '[:upper:]')
SSID="ThermalComfort-$SUFFIX"

echo "==> Removing any existing AP connection"
nmcli con delete "$CON_NAME" 2>/dev/null || true

echo "==> Creating AP connection"
nmcli con add \
    type wifi \
    ifname "$IFACE" \
    con-name "$CON_NAME" \
    autoconnect yes \
    ssid "$SSID" \
    802-11-wireless.mode ap \
    802-11-wireless.band bg \
    ipv4.method shared \
    ipv4.addresses "$AP_IP/24" \
    wifi-sec.key-mgmt wpa-psk \
    wifi-sec.psk "$DEFAULT_PASSWORD" \
    802-11-wireless-security.proto rsn \
    802-11-wireless-security.pairwise ccmp \
    802-11-wireless-security.group ccmp \
    802-11-wireless-security.pmf 2

echo "==> Bringing up AP"
nmcli con up "$CON_NAME"

echo ""
echo "Done."
echo "  SSID:      $SSID"
echo "  Password:  $DEFAULT_PASSWORD"
echo "  Device IP: $AP_IP"
echo ""
echo "The AP will start automatically on every boot."
echo "Print the SSID and password on the device label before shipping."
