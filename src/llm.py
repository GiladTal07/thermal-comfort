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
4. Only include a parameter in Recommendations if it requires an occupant action. If a \
parameter is fully within its ISO 7730 acceptable range and presents no comfort concern, do \
not create a Recommendations entry for it — note its acceptable status once in Comfort \
Assessment or Findings instead, and do not repeat a "no action needed" line for it in \
Recommendations. If, after applying this rule, no parameter requires any action, the \
Recommendations section contains only the PPD closing sentence (described in Section Guidance) \
— do not add any other content.
5. Only reference what is directly observable in the provided inputs — sensor readings, camera \
photo, and thermal heatmap. Do not invent or assume features not visible in the photo or \
reflected in the data (e.g. do not mention a window, blind, heat source, or occupant if none \
is visible). Do not write hypothetical or future-tense recommendations ("if you later find…", \
"should conditions change…"). Every statement must be grounded in the data as it stands now. \
Exception: if a recommendation would work against the occupant's current overall thermal \
sensation (for example, recommending blinds/shades to reduce solar gain while the current \
PMV/TSV is on the cool side), explicitly name this trade-off and frame the recommendation as \
conditional, suggesting the occupant re-check comfort at a different time of day rather than \
presenting it as an unconditional action.
6. Never phrase the TSV (Thermal Sensation Vote) as if an occupant gave real-time subjective \
feedback. The TSV is a model-predicted sensation category derived from the calculated PMV, not \
a self-report. Always describe it as a prediction (e.g., "the model predicts occupants would \
experience a 'slightly cool' sensation, based on a PMV of -0.56") — never write "the occupant \
reports feeling…" or similar language implying an actual human response was collected.

OUTPUT FORMAT — use exactly these markdown sections in this order, with no extra sections:

## Summary
## Room Description
## Comfort Assessment
## Findings
## Recommendations
## Appendix A — Sensor Data

SECTION GUIDANCE:
- **Summary**: 2-3 sentences. Overall comfort verdict, the PMV and PPD figures, the predicted \
sensation, and one priority action if any action is needed.
- **Room Description**: Describe the space based on the camera photo — room type, furniture \
layout, window presence, blind/shade state (open or closed), visible occupancy, and anything \
visually relevant to thermal comfort.
- **Comfort Assessment**: Interpret PMV, PPD, and TSV in plain language. Explain what the \
numbers mean for the typical occupant (e.g. "PMV of +1.2 indicates mild warmth; approximately \
35 % of occupants would be dissatisfied"). Note whether humidity and air speed fall within \
the ISO 7730 comfort bands. The standard PMV model uses a single metabolic reference and does \
not distinguish gender. Assume an even male/female split in the office. Research shows women \ 
tend to prefer environments roughly 1-2 °C warmer than men due to lower average metabolic rate \
and different thermoregulatory physiology, so the effective comfort zone for female occupants \
sits slightly warmer than the PMV figure suggests. Always note how the measured PMV is likely \
to be experienced differently by male versus female occupants: when the PMV is cool-biased \
(negative), female occupants are more likely to perceive genuine discomfort than male occupants; \
when the PMV is warm-biased (positive), male occupants reach their comfort limit sooner. Never \
invert this. A cool-biased environment is not more comfortable for women. \
- **Findings**: Notable observations from the thermal heatmap and sensor values — radiant \
asymmetry, localised hot or cold zones, humidity outside the 30-70 % comfort range. Flag \
anything outside ISO 7730 limits. Do not attribute findings to building system faults. \
Use the timestamp to factor in time-of-day context: early morning (before 09:00) may reflect \
HVAC warm-up with residual overnight cool; midday to mid-afternoon (12:00-16:00) brings peak \
solar gain, especially on south- and west-facing surfaces; late afternoon and evening may show \
accumulated building heat. If compass heading is provided, use it to infer wall and surface \
orientation only. Never infer the presence of windows, blinds, or glazing from heading alone; \
those may only be mentioned if directly visible in the camera photo. In the northern hemisphere, \
south-facing surfaces receive the most direct sunlight, east-facing receive morning sun, and west-facing \
receive afternoon sun. Combine heading and timestamp to explain radiant asymmetry or elevated \
mean radiant temperature where visible in the heatmap.
- **Recommendations**: Organize this section under two subheadings, in this order:
  - **Environmental**: actions that change conditions in the workspace generally (adjusting \
blinds/shades, positioning a personal fan or heater to affect the immediate area, relocating \
the desk/chair).
  - **Personal**: actions specific to the individual occupant's body (adding/removing a \
clothing layer, drinking a warm or cold beverage, using a desk fan aimed only at themselves).
  Include a parameter under one or both subheadings only if it needs an action; \
otherwise leave it out of this section entirely (its acceptable status was already covered in \
Comfort Assessment/Findings). Always end the Recommendations section — whether or not any \
actions were listed — with one sentence applying the PPD figure: state what percentage of \
occupants the space is predicted to satisfy. If recommendations were made, add that an \
individual who remains uncomfortable may simply be part of the remaining dissatisfied \
percentage, and that this is why the personal actions target the individual rather than the \
room as a whole. If no recommendations were made, omit that second clause.
- **Appendix A — Sensor Data**: All labeled sensor readings as a two-column markdown table \
with headers Parameter | Value. If the input value for PMV, PPD, or TSV begins with \
"Not calculated", copy it verbatim into the table cell wrapped in gray italic HTML: \
`<span style="color:#888888"><em>Not calculated — reason</em></span>`. \
Do not paraphrase, shorten, or reformat it.
"""

def encode_image(path: Path) -> str:
	return base64.standard_b64encode(path.read_bytes()).decode("utf-8")

def cardinal(degrees: float) -> str:
	directions = ["N", "NE", "E", "SE", "S", "SW", "W", "NW"]
	return directions[round(degrees / 45) % 8]

_PMV_REASONS = [
	("temperature too low",         "air temperature below 10 °C (malfunction)"),
	("temperature too high",        "air temperature exceeds 30 °C (malfunction)"),
	("surface temperature too low", "mean radiant temperature below 10 °C (malfunction)"),
	("surface temperature too high","mean radiant temperature exceeds 40 °C (malfunction)"),
	("negative air speed",          "air speed reading is negative"),
	("air speed too high",          "air speed exceeds 1 m/s"),
	("sensor fault",                "sensor fault — one or more readings unavailable"),
]

def _pmv_reason(notes: str) -> str:
	n = notes.lower()
	for fragment, reason in _PMV_REASONS:
		if fragment in n:
			return reason
	return "sensor data outside model range"

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

	notes_raw = parts[9] if len(parts) > 9 else ""
	pmv_missing = len(parts) > 6 and (not parts[6] or parts[6].lower() in ("nan", "none"))
	reason = _pmv_reason(notes_raw) if pmv_missing else None

	lines = []
	for label, value in zip(labels, parts):
		if label in ("PMV", "PPD (%)", "TSV") and reason:
			value = f"Not calculated — {reason}"
		elif not value or value.lower() in ("nan", "none"):
			value = "N/A"
		elif label == "Compass Heading (°, magnetic)":
			try:
				value = f"{value} ({cardinal(float(value))})"
			except ValueError:
				pass
		lines.append(f"{label}: {value}")
	return "\n".join(lines)

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

	output = []

	with anthropic.Anthropic() as client, client.messages.stream(
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
			# print(text, end="", flush=True)
			output.append(text)

	print("LLM output received.")
	send_email("".join(output), jpg_file, png_file)
