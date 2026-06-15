from gpiozero import Button
from signal import pause
from readings import capture_data
from llm import run as run_analysis

BUTTON_PIN = 17

button = Button(BUTTON_PIN)

def on_press():
    print("Button pressed — starting capture...")
    try:
        folder = capture_data()
        run_analysis(folder)
    except Exception as e:
        print(f"Error: {e}")

button.when_pressed = on_press
print("Ready. Waiting for button press on GPIO 17.")
pause()
