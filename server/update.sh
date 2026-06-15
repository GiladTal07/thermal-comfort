set -e

PROJECT_DIR="$(dirname "$(dirname "$(realpath "$0")")")"
GIT_USER="${SUDO_USER:-$USER}"

read -p "Home Wi-Fi SSID: " WIFI_SSID
read -s -p "Home Wi-Fi password: " WIFI_PASSWORD
echo

echo "==> Bringing down AP"
systemctl stop hostapd
nmcli con down thermal-ap 2>/dev/null || true

echo "==> Switching wlan0 to client mode"
nmcli dev set wlan0 managed yes
sleep 2
nmcli dev wifi rescan ifname wlan0 2>/dev/null || true
sleep 3

echo "==> Connecting to $WIFI_SSID"
nmcli -w 30 dev wifi connect "$WIFI_SSID" password "$WIFI_PASSWORD"

echo "==> Pulling latest code"
sudo -u "$GIT_USER" git -C "$PROJECT_DIR" pull

echo "==> Disconnecting"
nmcli con delete "$WIFI_SSID" 2>/dev/null || true

echo "==> Restoring AP"
nmcli con up thermal-ap
systemctl start hostapd

echo ""
echo "Done. AP is back up."
