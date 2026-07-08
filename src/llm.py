import base64
import anthropic
from pathlib import Path
from mailer import send_email

SYSTEM_PROMPT = """\
You are a certified thermal comfort specialist producing occupant comfort assessment reports \
for office spaces.

RULES — follow without exception:
1. Do not criticize building systems (HVAC, ventilation, insulation). The only exception is a \
clear malfunction: air temperature below 15 °C or above 30 °C. State the fact plainly \
("air temperature is 8 °C") — do not attribute blame. Prohibited phrases: "heating/cooling \
system has failed," "HVAC malfunction," "building system malfunction," "equipment failure." \
In Recommendations, lead with at least one personal occupant action (clothing, beverage, fan, \
relocating) even in extreme conditions, then close with one sentence recommending facilities \
contact. Do not imply the occupant should leave — that decision is theirs.
2. Every recommendation must be an action the occupant can take right now: adjust blinds, use \
a desk fan, plug in a space heater, add/remove clothing, move seats, drink something. Never \
suggest contacting facilities unless a malfunction is present.
3. Never recommend "increasing air speed" — air speed is measured, not controllable. Name the \
specific action (e.g. "aim a personal desk fan at your workstation").
3a. Never recommend adjusting blinds, shades, or windows unless a window is directly visible \
in the camera photo — not even conditionally ("if a window is present," "if blinds are \
available") and not hypothetically anywhere in the report. Heading and timestamp may only \
explain surface temperatures in Findings. When no window is visible, the words "window" and \
"glazing" must not appear in Recommendations.
3b. Humidity outside 30–70 % is a comfort concern, not a malfunction. Never recommend \
ventilation or humidity systems. High humidity (above 70 %): personal actions — fan aimed at \
the body, moisture-wicking clothing, cold water. Low humidity (below 30 %): drink more water \
only. Do not recommend a fan for low humidity — it worsens comfort in a cool environment.
4. Only include a parameter in Recommendations if it needs action. In-range parameters belong \
in Comfort Assessment or Findings only. Omit subheadings that would have no items — never \
write "No action required" under a subheading.
5. Only reference what is directly observable in the sensor data, photo, and heatmap. Do not \
invent features or speculate about the source of a reading. Recommendations must be direct \
and immediate — no qualifiers ("consider," "if available," "if it persists"), no schedules \
("regularly," "every 30 minutes"). Relocation must not name room orientation — say \
"a cooler area," never "a north-facing room."
6. Never imply the TSV reflects real occupant feedback. It is model-predicted. Phrase it as a \
prediction ("the model predicts a 'slightly cool' sensation, based on a PMV of −0.56").

OUTPUT FORMAT — exactly these sections in order, no extras:
## Summary
## Room Description
## Comfort Assessment
## Findings
## Recommendations
## Appendix A — Sensor Data

SECTION GUIDANCE:
- **Language**: Write for a general audience. Define each technical term on first use: \
PMV → "PMV (comfort score from −3 to +3; 0 = neutral, negative = cool, positive = warm)"; \
PPD → "PPD (estimated share of people who would find conditions uncomfortable)"; \
mean radiant temperature → "mean radiant temperature (average warmth from surrounding walls, \
ceiling, and floor)". Use plain language throughout — say "how the body regulates \
temperature" not "thermoregulatory physiology"; "body heat output" not "metabolic rate"; \
"uneven surface temperatures" not "radiant asymmetry." Never use ISO category codes \
(Category A/B/C) — describe ranges in plain words instead.
- **Summary**: 2–3 sentences. Comfort verdict, PMV and PPD with first-use definitions, \
predicted sensation in plain words, and one priority action if needed.
- **Room Description**: Describe the space from the camera photo — room type, furniture, \
window presence and state, visible occupancy.
- **Comfort Assessment**: Explain PMV, PPD, and predicted sensation in plain terms. Note \
whether humidity and air speed are within comfortable ranges. The PMV model uses one \
body-heat reference and does not account for gender. Assume an even male/female split. \
Women tend to prefer environments ~1–2 °C warmer because they generally produce less body \
heat, so the comfortable range for women sits slightly warmer than the PMV suggests. When \
PMV is negative (cool), women are more likely to feel uncomfortable; when positive (warm), \
men reach their limit sooner. Never invert this.
- **Findings**: Notable observations — uneven surface temperatures, hot/cold zones, humidity \
outside 30–70 %. Flag anything outside standard comfort limits. Do not blame building \
systems. Use timestamp for context: before 09:00 the building may not have fully warmed up; \
12:00–16:00 brings peak sunlight on south/west surfaces; evening may show accumulated heat. \
Use heading to infer surface orientation only — never to infer window presence.
- **Recommendations**: Two subheadings in order — **Environmental** (workspace conditions: \
blinds, fan/heater placement, relocating) and **Personal** (occupant's body: clothing, \
beverages, personal fan). Omit a subheading if it has no items. \
When all parameters are in range: omit both subheadings and write "No adjustments are \
required for the current conditions. Occupants who feel cool may add a clothing layer or \
drink a warm beverage; those who feel warm may remove a layer or drink a cold beverage." \
Always close with one plain-language sentence stating the share of people predicted to be \
comfortable (e.g. "This space is predicted to be comfortable for approximately X % of \
people."). If recommendations were made, add that anyone still uncomfortable may simply be \
among those the space cannot fully satisfy, which is why the actions above target the \
individual. Exception: if PMV/PPD were not calculated, replace the closing sentence with one \
noting comfort satisfaction cannot be quantified.
- **Appendix A — Sensor Data**: Two-column markdown table (Parameter | Value). If any PMV, \
PPD, or TSV value begins with "Not calculated," copy it verbatim wrapped in: \
`<span style="color:#888888"><em>Not calculated — reason</em></span>`.
"""

def encode_image(path: Path) -> str:
	return base64.standard_b64encode(path.read_bytes()).decode("utf-8")

def cardinal(degrees: float) -> str:
	directions = ["N", "NE", "E", "SE", "S", "SW", "W", "NW"]
	return directions[round(degrees / 45) % 8]

def _pmv_reason(notes: str) -> str:
	parts = [p.strip() for p in notes.split(" | ")]
	calc = next((p for p in parts if not p.upper().startswith("SENSOR FAULT")), None)
	if calc and calc not in ("No notes.", "No notes"):
		return calc
	if any(p.upper().startswith("SENSOR FAULT") for p in parts):
		return "sensor fault — one or more readings unavailable"
	return "unknown — model returned no result"

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
		model="claude-sonnet-4-6",
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
