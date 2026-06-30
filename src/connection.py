import subprocess

def is_connected() -> bool:
	try:
		result = subprocess.run(
			['nmcli', '-t', '-f', 'CONNECTIVITY', 'general'],
			capture_output=True, text=True, timeout=5
		)
		return result.stdout.strip() == 'full'
	except Exception:
		return False

def connect_saved(ssid: str) -> tuple[bool, str]:
	result = subprocess.run(
		['sudo', 'nmcli', 'connection', 'up', ssid],
		capture_output=True, text=True, timeout=30
	)
	if result.returncode == 0 or is_connected():
		return True, f"Connected to {ssid}"
	error = result.stderr.strip() or result.stdout.strip() or "Connection failed"
	return False, error

def connect_to_hotspot(ssid: str, password: str) -> tuple[bool, str]:
	cmd = ['sudo', 'nmcli', 'device', 'wifi', 'connect', ssid]
	if password:
		cmd += ['password', password]
	result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
	if result.returncode == 0 or is_connected():
		return True, f"Connected to {ssid}"
	error = result.stderr.strip() or result.stdout.strip() or "Connection failed"
	return False, error

def get_known_ssids() -> set:
	try:
		conns = subprocess.run(
			['nmcli', '-t', '-f', 'NAME,TYPE', 'connection', 'show'],
			capture_output=True, text=True, timeout=5
		)
		known = set()
		for line in conns.stdout.splitlines():
			parts = line.split(':')
			if len(parts) >= 2 and '802-11-wireless' in parts[1]:
				known.add(parts[0])
		return known
	except Exception:
		return set()

def scan_nearby_ssids() -> list[str]:
	try:
		result = subprocess.run(
			['nmcli', '-t', '-f', 'SSID,SIGNAL', 'device', 'wifi', 'list'],
			capture_output=True, text=True, timeout=15
		)
		seen = set()
		networks = []
		for line in result.stdout.splitlines():
			parts = line.rsplit(':', 1)
			if len(parts) != 2:
				continue
			ssid = parts[0].strip()
			try:
				signal = int(parts[1].strip())
			except ValueError:
				continue
			if ssid and ssid not in seen and signal >= 30:
				seen.add(ssid)
				networks.append(ssid)
		return networks
	except Exception:
		return []
