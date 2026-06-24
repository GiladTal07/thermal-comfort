import base64
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
anything outside ISO 7730 limits. Do not attribute findings to building system faults.
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

if __name__ == "__main__":
	_running = False
	_photo = None

	def _make_picam():
		cam = Picamera2()
		cam.configure(cam.create_preview_configuration(
			main={"size": (1024, 768), "format": "RGB888"}
		))
		cam.start()
		return cam

	picam2 = _make_picam()

	root = tk.Tk()
	root.overrideredirect(True)
	root.geometry("1024x768+1920+0")
	root.configure(bg="black")

	preview_label = tk.Label(root, bg="black")
	preview_label.place(x=0, y=0, width=1024, height=768)

	def update_preview():
		global _photo
		if not _running:
			try:
				frame = picam2.capture_array()
				img = Image.fromarray(frame).rotate(180)
				_photo = ImageTk.PhotoImage(img)
				preview_label.config(image=_photo)
			except Exception:
				pass
		root.after(50, update_preview)

	def trigger():
		global _running
		if _running:
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
		root,
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
	update_preview()
	root.mainloop()
	picam2.stop()
