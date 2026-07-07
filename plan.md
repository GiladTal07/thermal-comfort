# High-Level Plan

## Step 1 — Hardware Module Testing

Write and test each sensor driver in isolation. Each module should be runnable standalone (`python module.py`) and print verified output before moving on.

- [ ] **SI7021** — air temperature and relative humidity over I²C
- [ ] **MLX90640** — 32×24 IR array; capture a frame, render heatmap, verify pixel values are physically plausible
- [ ] **PAV3015** — air speed over I²C; validate the conversion formula against a reference anemometer
- [ ] **Pi Camera** — capture a 1920×1080 JPEG via `libcamera-still`, confirm file is written
- [ ] **GPIO button** — confirm GPIO 17 press is detected reliably with debounce
- [ ] **RGB LED** — cycle through states (idle, reading, done, error) and confirm each is visually distinct

---

## Step 2 — LLM Report Generation

With sensor data available, build and test the full analysis pipeline in isolation from hardware.

- [ ] `pmv_calculator.py` — verify PMV/PPD/TSV against known reference cases from ISO 7730 Annex D
- [ ] `parse_readings()` in `llm.py` — confirm all 9 pipe-delimited fields map to the correct labels
- [ ] Claude API call — send a sample `readings.txt`, a test JPEG, and a test PNG; confirm a coherent analysis is returned
- [ ] `mailer.py` — send a test email with HTML formatting and both images embedded; confirm rendering in Gmail and one other client
- [ ] Prompt caching — verify the system prompt is cached across calls (check API response for cache hit)

---

## Step 3 — End-to-End Test

Run the full pipeline on real hardware: button press → sensors → LLM → email.

- [ ] Trigger a reading via button press and confirm all sensor values are captured
- [ ] Confirm `readings.txt`, JPEG, and PNG are written to the correct `data/<timestamp>/` folder
- [ ] Confirm the Claude analysis references the actual sensor values (no label mismatch)
- [ ] Confirm the email arrives with correct HTML formatting, both images visible, and a readable subject line
- [ ] Confirm the service restarts automatically after a simulated crash (`sudo kill <pid>`)
- [ ] Confirm a scheduled reading fires at the configured time

---

## Step 4 — Consumer Product

See [`specs.md`](specs.md), [`prd.md`](prd.md), and [`to-do.md`](to-do.md) for full detail.

High-level milestones:

- [ ] Phase 0 — resolve open decisions (market, cloud vs local, pricing, SBC)
- [ ] Phase 1 — harden existing code (error recovery, retries, SQLite, multi-recipient)
- [ ] Phase 2 — provisioning UI and local web dashboard
- [ ] Phase 3 — scheduled readings and OTA updates
- [ ] Phase 4 — custom PCB and enclosure (design → prototype → validate)
- [ ] Phase 5 — factory calibration and end-of-line test fixture
- [ ] Phase 6 — regulatory certifications (FCC, CE, UL, RoHS)
- [ ] Phase 7 — packaging and launch
