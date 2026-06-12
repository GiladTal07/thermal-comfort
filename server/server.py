#!/usr/bin/env python3
"""
Phase 2 entry point. Replaces llm.py as the systemd service target.
Runs the Flask HTTP server on port 80 and handles capture via POST /trigger.
"""
import sys
import os
import json
import threading
from pathlib import Path
from flask import Flask, jsonify, request, send_file, render_template_string

_project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(_project_root, 'src'))

from readings import capture_data, LATEST_DIR
from llm import run as run_analysis
from pmv_calculator import DEFAULT_MET, DEFAULT_CLO

FIRMWARE_VERSION = '1.0.0'
_CONFIG_PATH = Path(_project_root) / 'data' / 'config.json'

app = Flask(__name__)

# ── Config ─────────────────────────────────────────────────────────────────────

def _load_config() -> dict:
    if _CONFIG_PATH.exists():
        return json.loads(_CONFIG_PATH.read_text())
    return {'met': DEFAULT_MET, 'clo': DEFAULT_CLO}


def _save_config(cfg: dict):
    _CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    _CONFIG_PATH.write_text(json.dumps(cfg, indent=2))


# ── Shared state ───────────────────────────────────────────────────────────────
_lock = threading.Lock()
_status = 'idle'    # idle | capturing | ready | error
_error_msg = None


def _set_status(status, error_msg=None):
    global _status, _error_msg
    with _lock:
        _status = status
        _error_msg = error_msg


def _capture_worker(met, clo):
    _set_status('capturing')
    try:
        run_dir = capture_data(met=met, clo=clo)
        run_analysis(run_dir)
        _set_status('ready')
    except Exception as e:
        _set_status('error', str(e))


# ── Helpers ────────────────────────────────────────────────────────────────────

_LABELS = ['timestamp', 'air_temp', 'humidity', 'mrt', 'air_speed',
           'pmv', 'ppd', 'tsv', 'notes']


def _get_latest() -> dict | None:
    readings_file = Path(LATEST_DIR) / 'readings.txt'
    if not readings_file.exists():
        return None
    parts = [p.strip() for p in readings_file.read_text().strip().split('|')]
    return dict(zip(_LABELS, parts))


# ── API ────────────────────────────────────────────────────────────────────────

@app.get('/status')
def get_status():
    with _lock:
        return jsonify({
            'status': _status,
            'firmware_version': FIRMWARE_VERSION,
            'error': _error_msg,
        })


@app.get('/reading/latest')
def get_reading_latest():
    row = _get_latest()
    if row is None:
        return jsonify({'error': 'no reading yet'}), 404
    return jsonify(row)


@app.get('/reading/latest/photo')
def get_latest_photo():
    jpgs = list(Path(LATEST_DIR).glob('*.jpg'))
    if not jpgs:
        return jsonify({'error': 'no photo available'}), 404
    return send_file(jpgs[0], mimetype='image/jpeg', conditional=True)


@app.get('/reading/latest/thermal')
def get_latest_thermal():
    path = Path(LATEST_DIR) / 'thermal.json'
    if not path.exists():
        return jsonify({'error': 'no thermal data available'}), 404
    return send_file(path, mimetype='application/json')


@app.post('/trigger')
def post_trigger():
    with _lock:
        if _status == 'capturing':
            return jsonify({'error': 'capture already in progress'}), 409
    cfg = _load_config()
    data = request.get_json(force=True, silent=True) or {}
    met = float(data.get('met', cfg['met']))
    clo = float(data.get('clo', cfg['clo']))
    threading.Thread(target=_capture_worker, args=(met, clo), daemon=True).start()
    return jsonify({'status': 'capturing'}), 202


@app.post('/config')
def post_config():
    data = request.get_json(force=True, silent=True) or {}
    cfg = _load_config()
    if 'met' in data:
        cfg['met'] = float(data['met'])
    if 'clo' in data:
        cfg['clo'] = float(data['clo'])
    _save_config(cfg)
    return jsonify(cfg)


@app.post('/config/ap-password')
def post_ap_password():
    data = request.get_json(force=True, silent=True) or {}
    password = str(data.get('password', '')).strip()
    if len(password) < 8:
        return jsonify({'error': 'password must be at least 8 characters'}), 400
    try:
        _set_ap_password(password)
        return jsonify({'status': 'ok'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


def _set_ap_password(password: str):
    import subprocess, re
    conf_path = '/etc/hostapd/hostapd.conf'
    with open(conf_path) as f:
        conf = f.read()
    conf = re.sub(r'^wpa_passphrase=.*$', f'wpa_passphrase={password}', conf, flags=re.MULTILINE)
    with open(conf_path, 'w') as f:
        f.write(conf)
    subprocess.run(['systemctl', 'restart', 'hostapd'], check=True)


# ── Dashboard ──────────────────────────────────────────────────────────────────

@app.get('/')
def dashboard():
    row = _get_latest()
    with _lock:
        current_status = _status
    return render_template_string(
        _DASHBOARD_HTML,
        status=current_status,
        row=row,
        firmware=FIRMWARE_VERSION,
    )


_DASHBOARD_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Thermal Comfort Monitor</title>
<style>
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body { font-family: -apple-system, 'Segoe UI', Arial, sans-serif; font-size: 14px;
         background: #f0f2f5; color: #1a1a2e; }
  header { background: linear-gradient(135deg, #1a1a2e, #2a3f6f); color: #fff;
           padding: 20px 28px; }
  header .label { font-size: 10px; letter-spacing: 2px; text-transform: uppercase;
                  color: #8fa8c8; margin-bottom: 4px; }
  header h1 { font-size: 18px; font-weight: 600; }
  header .meta { font-size: 12px; color: #8fa8c8; margin-top: 6px; }
  .badge { display: inline-block; padding: 2px 10px; border-radius: 99px;
           font-size: 10px; font-weight: 700; text-transform: uppercase; letter-spacing: 1px; }
  .badge.idle     { background: #e2e8f0; color: #64748b; }
  .badge.capturing{ background: #fef3c7; color: #92400e; }
  .badge.ready    { background: #d1fae5; color: #065f46; }
  .badge.error    { background: #fee2e2; color: #991b1b; }
  .container { max-width: 760px; margin: 24px auto; padding: 0 16px; }
  .card { background: #fff; border-radius: 10px; padding: 24px;
          margin-bottom: 20px; box-shadow: 0 1px 4px rgba(0,0,0,0.07); }
  .card h2 { font-size: 10px; font-weight: 700; letter-spacing: 2px;
             text-transform: uppercase; color: #7a8fa6;
             margin-bottom: 16px; padding-bottom: 8px; border-bottom: 2px solid #edf0f4; }
  .grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(120px, 1fr)); gap: 16px; }
  .metric .value { font-size: 26px; font-weight: 700; }
  .metric .unit  { font-size: 13px; color: #7a8fa6; margin-left: 2px; }
  .metric .label { font-size: 11px; color: #9aaaba; margin-top: 4px; }
  .notes { margin-top: 14px; font-size: 12px; color: #7a8fa6; }
  .none { color: #9aaaba; font-style: italic; }
</style>
</head>
<body>
<header>
  <div class="label">Thermal Comfort Monitor</div>
  <h1>Device Dashboard</h1>
  <div class="meta">
    Firmware&nbsp;{{ firmware }}&nbsp;&nbsp;·&nbsp;&nbsp;
    Status <span class="badge {{ status }}">{{ status }}</span>
  </div>
</header>
<div class="container">
  {% if row %}
  <div class="card">
    <h2>Latest Reading &nbsp;·&nbsp; {{ row.timestamp }}</h2>
    <div class="grid">
      <div class="metric">
        <div class="value">{{ row.pmv }}</div>
        <div class="label">PMV</div>
      </div>
      <div class="metric">
        <div class="value">{{ row.ppd }}<span class="unit">%</span></div>
        <div class="label">PPD</div>
      </div>
      <div class="metric">
        <div class="value">{{ row.air_temp }}<span class="unit">°C</span></div>
        <div class="label">Air Temp</div>
      </div>
      <div class="metric">
        <div class="value">{{ row.humidity }}<span class="unit">%</span></div>
        <div class="label">Humidity</div>
      </div>
      <div class="metric">
        <div class="value">{{ row.mrt }}<span class="unit">°C</span></div>
        <div class="label">MRT</div>
      </div>
      <div class="metric">
        <div class="value">{{ row.air_speed }}<span class="unit">m/s</span></div>
        <div class="label">Air Speed</div>
      </div>
    </div>
    {% if row.notes and row.notes != 'No notes.' %}
    <div class="notes">{{ row.notes }}</div>
    {% endif %}
  </div>
  {% else %}
  <div class="card"><span class="none">No reading yet.</span></div>
  {% endif %}
</div>
</body>
</html>"""


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 80))
    app.run(host='0.0.0.0', port=port, debug=False)
