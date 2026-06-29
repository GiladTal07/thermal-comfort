import base64
import anthropic
from pathlib import Path
from mailer import send_email

SYSTEM_PROMPT = """\
You are a certified thermal comfort specialist (ISO 7730:2005) producing occupant comfort \
assessment reports for office spaces.

STRICT RULES — follow without exception:
1. Do not criticize base building systems (HVAC, ventilation, building design, insulation). \
These are outside the occupant's control. The only exception is a clear malfunction: \
air temperature below 15 °C or above 30 °C, or sensor data that indicates equipment failure.
2. Every recommendation must be an action the individual occupant can take right now: \
adjust window blinds or shades, use a personal desk fan, plug in a space heater under the \
desk, wear or remove a layer of clothing, move to a different seat, drink a warm or cold \
beverage, etc. Do not suggest contacting facilities management unless a malfunction is present.
3. Never recommend changing air speed as if it were a directly controllable parameter. \
Air speed is a measured ambient value, not a dial the occupant can turn. If increased air \
movement would benefit comfort, the recommendation must name a specific occupant action \
(e.g. "aim a personal desk fan at your workstation"). Never write "increase air speed" or similar.
4. The Recommendations section must address every comfort parameter individually. For each \
parameter, either give a specific occupant action or explicitly state the value is acceptable. \
Do not pad with generic wellness advice.

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
comfort bands. The standard PMV model uses a single metabolic reference and does not distinguish \
gender. Assume an even male/female split in the office. Research shows women tend to prefer \
environments roughly 1-2 °C warmer than men due to lower average metabolic rate and different \
thermoregulatory physiology, so the effective comfort zone for female occupants sits slightly \
warmer than the PMV figure suggests. Always note how the measured PMV is likely to be \
experienced differently by male versus female occupants.
- **Findings**: Notable observations from the thermal heatmap and sensor values — radiant \
asymmetry, localised hot or cold zones, humidity outside the 30-70 % comfort range. Flag \
anything outside ISO 7730 limits. Do not attribute findings to building system faults. \
Use the timestamp to factor in time-of-day context: early morning (before 09:00) may reflect \
HVAC warm-up with residual overnight cool; midday to mid-afternoon (12:00–16:00) brings peak \
solar gain, especially on south- and west-facing surfaces; late afternoon and evening may show \
accumulated building heat. If compass heading is provided, use it to infer window and wall \
orientation: in the northern hemisphere, south-facing surfaces receive the most direct sunlight, \
east-facing receive morning sun, and west-facing receive afternoon sun. Combine heading and \
timestamp to explain radiant asymmetry or elevated mean radiant temperature where visible in \
the heatmap.
- **Recommendations**: A structured list with one entry per comfort parameter in this order: \
Air Temperature, Humidity, Mean Radiant Temperature, Air Speed, PMV/PPD. For each parameter, \
either give a specific, immediately actionable occupant recommendation tied to a finding above, \
or state that the value is within the acceptable range and no action is needed. Every parameter \
must appear — none may be omitted.
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
