#!/bin/bash
# Configures wlan0 as a permanent Wi-Fi AP using NetworkManager (nmcli).
# Required on Raspberry Pi OS Bookworm (Pi 5). Run once as root: sudo bash server/setup_ap.sh
set -e

IFACE=wlan0
AP_IP=192.168.4.1
DEFAULT_PASSWORD="comfort1234"   # printed on device label
CON_NAME="thermal-ap"

# Last 4 hex chars of MAC, uppercased
MAC=$(cat /sys/class/net/$IFACE/address | tr -d ':')
SUFFIX=$(echo "${MAC: -4}" | tr '[:lower:]' '[:upper:]')
SSID="ThermalComfort-$SUFFIX"

echo "==> Removing any existing AP connection"
nmcli con delete "$CON_NAME" 2>/dev/null || true

echo "==> Removing existing Wi-Fi client connections on $IFACE"
nmcli -t -f NAME,TYPE,DEVICE con show | grep ":wifi:$IFACE" | cut -d: -f1 | while read -r con; do
    echo "    Deleting: $con"
    nmcli con delete "$con" 2>/dev/null || true
done

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
    wifi-sec.psk "$DEFAULT_PASSWORD"

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
