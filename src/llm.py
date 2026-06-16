import base64
import anthropic
from pathlib import Path
from gpiozero import Button
from signal import pause
from readings import capture_data, DATA_DIR
from mailer import send_email

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
- **Summary**: 2–3 sentences. Overall comfort verdict, the PMV and PPD figures, one priority action.
- **Room Description**: Describe the space based on the camera photo — room type, furniture \
layout, window presence, blind/shade state (open or closed), visible occupancy, and anything \
visually relevant to thermal comfort.
- **Comfort Assessment**: Interpret PMV, PPD, and TSV in plain language. Explain what the numbers \
mean for the typical occupant (e.g. "PMV of +1.2 indicates mild warmth; approximately 35 % of \
occupants would be dissatisfied"). Note whether humidity and air speed fall within the ISO 7730 \
comfort bands.
- **Findings**: Notable observations from the thermal heatmap and sensor values — radiant \
asymmetry, localised hot or cold zones, humidity outside the 30–70 % comfort range. Flag \
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
	def on_press():
		print("Button pressed — starting capture...")
		try:
			capture_data()
			run(DATA_DIR)
		except Exception as e:
			print(f"Error: {e}")

	button = Button(BUTTON_PIN)
	button.when_pressed = on_press
	print("Ready. Waiting for button press on GPIO 17.")
	pause()
