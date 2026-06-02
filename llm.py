import sys
import base64
import anthropic
from pathlib import Path
from gpiozero import Button
from readings import capture_data
from mailer import send_email

SYSTEM_PROMPT = (
	"You are an expert in building thermal comfort. You will receive labeled sensor readings "
	"including a timestamp, air temperature (°C), humidity (%), mean radiant temperature (°C), "
	"air speed (m/s), PMV (Predicted Mean Vote, -3 to +3), PPD (Predicted Percentage Dissatisfied, %), "
	"TSV (Thermal Sensation Vote), and additional notes about the data. "
	"You will also receive an HQ photo of the space and a thermal heatmap from an MLX90640 "
	"infrared camera. Provide a thorough thermal comfort analysis."
)

def encode_image(path: Path) -> str:
	return base64.standard_b64encode(path.read_bytes()).decode("utf-8")

def parse_readings(text: str) -> str:
	labels = [
		"Timestamp",
		"Air Temperature (°C)",
		"Humidity (%)",
		"Mean Radiant Temperature (°C)",
		"Air Speed (m/s)"
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
	
	readings_file = folder / "readings.txt"
	jpg_files = list(folder.glob("*.jpg"))
	png_files = list(folder.glob("*.png"))
	
	if not readings_file.exists():
		sys.exit(f"Error: readings.txt not found in {folder}")
	if not jpg_files:
		sys.exit(f"Error: no .jpg file found in {folder}")
	if not png_files:
		sys.exit(f"Error: no .png file found in {folder}")
	
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
						"data": encode_image(jpg_files[0]),
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
						"data": encode_image(png_files[0]),
					},
				},
				{
					"type": "text",
					"text": (
						"Analyze the thermal comfort conditions. Cover: current comfort level "
						"based on the PMV/PPD values, temperature distribution and any hot/cold "
						"spots visible in the heatmap, what the camera photo reveals about the "
						"space, and recommendations to improve comfort."
					),
				},
			],
		}],
	) as stream:
		for text in stream.text_stream:
			print(text, end="", flush=True)
			output.append(text)
	
	print()
	send_email("".join(output))

if __name__ == "__main__":
	if len(sys.argv) == 2:
		run(sys.argv[1])
	elif len(sys.argv) == 1:
		btn = Button(17, pull_up=True, bounce_time=0.1)
		print("Waiting for button press...")
		btn.wait_for_press()
		print("Button pressed - capturing data...")
		folder = capture_data()
		run(folder)
	else:
		print(f"Usage: python {sys.argv[0]} [folder_path]", fle=sys.stderr)
		sys.exit(1)
