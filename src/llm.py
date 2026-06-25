import base64
import re
import subprocess
import time
import anthropic
from pathlib import Path
from threading import Thread
from gpiozero import Button
from picamera2 import Picamera2
from PIL import Image, ImageTk
from readings import capture_data, DATA_DIR
from mailer import send_email
import tkinter as tk
import evdev
from evdev import InputDevice, ecodes

BUTTON_PIN = 17

SYSTEM_PROMPT = """\
You are a certified thermal comfort specialist (ISO 7730:2005) producing occupant comfort \
assessment reports for office spaces.

STRICT RULES — follow without exception:
1. Do not criticize base building systems (HVAC, ventilation, building design, insulation). \
These are outside the occupant's control. The only exception is a clear malfunction: \
air temperature below 15 °C or above 30 °C, or sensor data that indicates equipment failure.
2. Every recommendation must be an action the individual occupant can take right now in \
the current environment: adjust window blinds or shades, use a personal desk fan, plug in \
a space heater under the desk, wear or remove a layer of clothing, move to a different seat, \
drink a warm or cold beverage, etc. Do not suggest contacting facilities management unless \
a malfunction is present.

OUTPUT FORMAT — use exactly these markdown sections in this order, with no extra sections:

## Summary
## Room Description
## Comfort Assessment
## Findings
## Recommendations
## Appendix A — Sensor Data

SECTION GUIDANCE:
- **Summary**: 2-3 sentences. Overall comfort verdict, the PMV and PPD figures, one priority action.
- **Room Description**: Describe the space based on the camera photo — room type, furniture \
layout, window presence, blind/shade state (open or closed), visible occupancy, and anything \
visually relevant to thermal comfort.
- **Comfort Assessment**: Interpret PMV, PPD, and TSV in plain language. Explain what the numbers \
mean for the typical occupant (e.g. "PMV of +1.2 indicates mild warmth; approximately 35 % of \
occupants would be dissatisfied"). Note whether humidity and air speed fall within the ISO 7730 \
comfort bands.
- **Findings**: Notable observations from the thermal heatmap and sensor values — radiant \
asymmetry, localised hot or cold zones, humidity outside the 30-70 % comfort range. Flag \
anything outside ISO 7730 limits. Do not attribute findings to building system faults. \
If compass heading is provided, use it to infer window and wall orientation: in the northern \
hemisphere, south-facing surfaces receive the most direct sunlight, east-facing receive morning \
sun, and west-facing receive afternoon sun. Use this to explain radiant asymmetry or elevated \
mean radiant temperature where visible in the heatmap.
- **Recommendations**: Bulleted list. Individual occupant actions only. Each bullet should be \
specific, immediately actionable, and tied to a finding above.
- **Appendix A — Sensor Data**: All labeled sensor readings as a two-column markdown table \
with headers Parameter | Value.\
"""

def encode_image(path: Path) -> str:
	return base64.standard_b64encode(path.read_bytes()).decode("utf-8")

def parse_readings(text: str) -> str:
	labels = [
		"Timestamp",
		"Air Temperature (°C)",
		"Humidity (%)",
		"Mean Radiant Temperature (°C)",
		"Air Speed (m/s)",
		"Compass Heading (°, magnetic)",
		"PMV",
		"PPD (%)",
		"TSV",
		"Notes",
	]
	parts = [p.strip() for p in text.strip().split("|")]
	return "\n".join(
		f"{label}: {value}"
		for label, value in zip(labels, parts)
		if value
	)

def run(folder_path: str) -> None:
	folder = Path(folder_path)

	readings_file = folder / "data.txt"
	jpg_file = folder / "image.jpg"
	png_file = folder / "thermal.png"

	if not readings_file.exists():
		raise FileNotFoundError(f"data.txt not found in {folder}")
	if not jpg_file.exists():
		raise FileNotFoundError(f"image.jpg not found in {folder}")
	if not png_file.exists():
		raise FileNotFoundError(f"thermal.png not found in {folder}")

	client = anthropic.Anthropic()
	output = []

	with client.messages.stream(
		model="claude-haiku-4-5",
		max_tokens=4096,
		system=SYSTEM_PROMPT,
		messages=[{
			"role": "user",
			"content": [
				{
					"type": "text",
					"text": "Sensor reading:\n\n" + parse_readings(readings_file.read_text()),
				},
				{
					"type": "text",
					"text": "HQ camera photo of the space:",
				},
				{
					"type": "image",
					"source": {
						"type": "base64",
						"media_type": "image/jpeg",
						"data": encode_image(jpg_file),
					},
				},
				{
					"type": "text",
					"text": "Thermal heatmap (MLX90640, bicubic-upscaled, inferno colormap — brighter = warmer):",
				},
				{
					"type": "image",
					"source": {
						"type": "base64",
						"media_type": "image/png",
						"data": encode_image(png_file),
					},
				},
				{
					"type": "text",
					"text": "Produce a thermal comfort assessment report following the system prompt format and rules.",
				},
			],
		}],
	) as stream:
		for text in stream.text_stream:
			print(text, end="", flush=True)
			output.append(text)

	print()
	send_email("".join(output), jpg_file, png_file)

def _screen_geometry():
	"""Return (geometry_string, width, height) for the target screen.
	Prefers a non-primary screen when two are connected, otherwise uses whichever is available."""
	try:
		out = subprocess.check_output(['xrandr', '--query'], text=True)
		screens = []
		for line in out.splitlines():
			if ' connected ' in line:
				m = re.search(r'(\d+)x(\d+)\+(\d+)\+(\d+)', line)
				if m:
					w, h, x, y = int(m.group(1)), int(m.group(2)), int(m.group(3)), int(m.group(4))
					screens.append((w, h, x, y))
		if not screens:
			raise ValueError("no screens found")
		if len(screens) == 1:
			w, h, x, y = screens[0]
		else:
			# Prefer the screen not at the origin (the secondary monitor)
			secondary = [s for s in screens if s[2] != 0 or s[3] != 0]
			w, h, x, y = secondary[0] if secondary else screens[-1]
		return f"{w}x{h}+{x}+{y}", w, h, x, y
	except Exception:
		return "1024x768+1920+0", 1024, 768, 1920, 0

def connect_to_hotspot(ssid: str, password: str) -> tuple[bool, str]:
	result = subprocess.run(
		['nmcli', 'device', 'wifi', 'connect', ssid, 'password', password],
		capture_output=True, text=True, timeout=30
	)
	if result.returncode == 0:
		return True, f"Connected to {ssid}"
	error = result.stderr.strip() or result.stdout.strip() or "Connection failed"
	return False, error

if __name__ == "__main__":
	_running = False
	_photo = None
	picam2 = None

	_geometry, _sw, _sh, _sx, _sy = _screen_geometry()
	print(f"Target screen: {_geometry}")

	def _make_picam():
		cam = Picamera2()
		cam.configure(cam.create_preview_configuration(
			main={"size": (_sw, _sh), "format": "RGB888"}
		))
		cam.start()
		return cam

	root = tk.Tk()
	root.overrideredirect(True)
	root.geometry(_geometry)
	root.configure(bg="black")

	# ── Camera frame ──────────────────────────────────────────────────────────
	camera_frame = tk.Frame(root, bg="black")
	camera_frame.place(x=0, y=0, width=_sw, height=_sh)

	preview_label = tk.Label(camera_frame, bg="black")
	preview_label.place(x=0, y=0, width=_sw, height=_sh)

	def update_preview():
		global _photo
		if not _running and picam2 is not None:
			try:
				frame = picam2.capture_array()
				img = Image.fromarray(frame).rotate(180)
				_photo = ImageTk.PhotoImage(img)
				preview_label.config(image=_photo)
			except Exception:
				pass
		root.after(50, update_preview)

	def trigger():
		global _running, picam2
		if picam2 is None or _running:
			return
		_running = True
		btn.config(state="disabled", bg="#555", text="Processing...")

		def work():
			global _running, picam2
			try:
				picam2.stop()
				picam2.close()
				time.sleep(0.5)
				capture_data()
				run(DATA_DIR)
				root.after(0, lambda: btn.config(text="Email sent!"))
			except Exception as e:
				print(f"Error: {e}")
				root.after(0, lambda: btn.config(text="Error — check logs"))
			finally:
				picam2 = _make_picam()
				_running = False
				root.after(0, lambda: btn.config(
					state="normal", bg="#2196F3", text="CAPTURE"
				))

		Thread(target=work, daemon=True).start()

	btn = tk.Button(
		camera_frame,
		text="CAPTURE",
		font=("Arial", 28, "bold"),
		bg="#2196F3",
		fg="white",
		activebackground="#1565C0",
		activeforeground="white",
		relief="flat",
		bd=0,
		command=trigger,
	)
	btn.place(relx=0.5, rely=1.0, relwidth=0.6, height=90, anchor="s", y=-15)

	# ── Wi-Fi frame ───────────────────────────────────────────────────────────
	_kbd = [None]

	def _open_keyboard():
		if _kbd[0] is None or _kbd[0].poll() is not None:
			kbd_h = 220
			_kbd[0] = subprocess.Popen([
				'onboard', '--size', f'{_sw}x{kbd_h}',
				'--geometry', f'+{_sx}+{_sy + _sh - kbd_h}',
				'--layout', 'compact',
			])

	def _close_keyboard():
		if _kbd[0] is not None:
			_kbd[0].terminate()
			_kbd[0] = None

	wifi_frame = tk.Frame(root, bg="#1a1a1a")
	wifi_frame.place(x=0, y=0, width=_sw, height=_sh)

	tk.Label(wifi_frame, text="Connect to Wi-Fi", fg="white", bg="#1a1a1a",
		font=("Arial", 32, "bold")).pack(pady=(30, 24))

	tk.Label(wifi_frame, text="Network Name (SSID)", fg="white", bg="#1a1a1a",
		font=("Arial", 20, "bold")).pack(anchor="w", padx=60)
	ssid_var = tk.StringVar()
	ssid_entry = tk.Entry(wifi_frame, textvariable=ssid_var, font=("Arial", 22),
		width=18, bg="white", fg="black", insertbackground="black", relief="flat")
	ssid_entry.pack(pady=(4, 18), ipady=10, padx=60, fill="x")
	ssid_entry.bind("<FocusIn>", lambda e: _open_keyboard())

	tk.Label(wifi_frame, text="Password", fg="white", bg="#1a1a1a",
		font=("Arial", 20, "bold")).pack(anchor="w", padx=60)
	pw_var = tk.StringVar()
	pw_entry = tk.Entry(wifi_frame, textvariable=pw_var, font=("Arial", 22),
		width=18, bg="white", fg="black", insertbackground="black",
		show="*", relief="flat")
	pw_entry.pack(pady=(4, 20), ipady=10, padx=60, fill="x")
	pw_entry.bind("<FocusIn>", lambda e: _open_keyboard())

	wifi_status = tk.Label(wifi_frame, text="", fg="#f44336", bg="#1a1a1a",
		font=("Arial", 18, "bold"))
	wifi_status.pack(pady=(0, 8))

	def _show_camera():
		global picam2
		_close_keyboard()
		picam2 = _make_picam()
		camera_frame.tkraise()
		update_preview()

	def do_connect():
		ssid = ssid_var.get().strip()
		pw = pw_var.get().strip()
		if not ssid:
			wifi_status.config(text="Please enter a network name.", fg="#f44336")
			return
		connect_btn.config(state="disabled", text="Connecting...")
		wifi_status.config(text="")

		def work():
			success, msg = connect_to_hotspot(ssid, pw)
			if success:
				root.after(0, lambda: wifi_status.config(
					text=f"Connected to {ssid}!", fg="#4caf50"))
				root.after(2000, _show_camera)
			else:
				root.after(0, lambda: (
					connect_btn.config(state="normal", text="Connect"),
					wifi_status.config(text=f"Failed: {msg}", fg="#f44336"),
				))

		Thread(target=work, daemon=True).start()

	connect_btn = tk.Button(
		wifi_frame, text="Connect", font=("Arial", 24, "bold"),
		bg="#2196F3", fg="white", activebackground="#1565C0",
		activeforeground="white", relief="flat", bd=0,
		command=do_connect,
	)
	connect_btn.pack(pady=4, ipadx=30, ipady=14)

	wifi_frame.tkraise()

	# ── Touch / physical button listeners ─────────────────────────────────────
	def _find_touch_device():
		for path in evdev.list_devices():
			try:
				dev = InputDevice(path)
				caps = dev.capabilities()
				if ecodes.EV_ABS in caps and ecodes.BTN_TOUCH in caps.get(ecodes.EV_KEY, []):
					return dev
			except Exception:
				pass
		return None

	def _touch_thread():
		dev = None
		while dev is None:
			dev = _find_touch_device()
			if dev is None:
				time.sleep(2)
		print(f"Touch device: {dev.name}")
		for event in dev.read_loop():
			if event.type == ecodes.EV_KEY and event.code == ecodes.BTN_TOUCH and event.value == 1:
				root.after(0, trigger)

	Thread(target=_touch_thread, daemon=True).start()

	physical = Button(BUTTON_PIN)
	physical.when_pressed = lambda: root.after(0, trigger)

	root.bind("<Escape>", lambda e: root.destroy())
	root.mainloop()
	if picam2 is not None:
		picam2.stop()
