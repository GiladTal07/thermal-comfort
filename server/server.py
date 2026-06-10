#!/usr/bin/env python3
"""
Phase 2 entry point. Replaces llm.py as the systemd service target.
Runs the Flask HTTP server on port 80 and handles capture via POST /trigger.
"""
import sys
import os
import threading
import csv
import io
from pathlib import Path
from flask import Flask, jsonify, request, send_file, Response, render_template_string

_project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(_project_root, 'src'))

from readings import capture_data
from llm import run as run_analysis
from pmv_calculator import DEFAULT_MET, DEFAULT_CLO

FIRMWARE_VERSION = '1.0.0'

app = Flask(__name__)

# ── Shared state ───────────────────────────────────────────────────────────────
_lock = threading.Lock()
_status = 'idle'    # idle | capturing | ready | error
_error_msg = None
_met = DEFAULT_MET
_clo = DEFAULT_CLO


def _set_status(status, error_msg=None):
    global _status, _error_msg
    with _lock:
        _status = status
        _error_msg = error_msg


def _capture_worker():
    _set_status('capturing')
    try:
        with _lock:
            met, clo = _met, _clo
        run_dir = capture_data(met=met, clo=clo)
        run_analysis(run_dir)
        _set_status('ready')
    except Exception as e:
        _set_status('error', str(e))


# ── File-system helpers ────────────────────────────────────────────────────────

_LABELS = ['timestamp', 'air_temp', 'humidity', 'mrt', 'air_speed',
           'pmv', 'ppd', 'tsv', 'notes']


def _parse_run_dir(run_dir: Path) -> dict | None:
    readings_file = run_dir / 'readings.txt'
    if not readings_file.exists():
        return None
    parts = [p.strip() for p in readings_file.read_text().strip().split('|')]
    row = dict(zip(_LABELS, parts))
    jpg = list(run_dir.glob('*.jpg'))
    png = [p for p in run_dir.glob('*.png') if not p.name.endswith('_thermal.json')]
    raw = list(run_dir.glob('*_thermal.json'))
    row['photo_path'] = str(jpg[0]) if jpg else None
    row['thermal_path'] = str(png[0]) if png else None
    row['thermal_raw_path'] = str(raw[0]) if raw else None
    return row


def _get_run_dirs() -> list[Path]:
    data_dir = Path(_project_root) / 'data'
    if not data_dir.exists():
        return []
    return sorted([d for d in data_dir.iterdir() if d.is_dir()], reverse=True)


def _get_latest() -> dict | None:
    for d in _get_run_dirs():
        row = _parse_run_dir(d)
        if row:
            return row
    return None


def _get_all() -> list[dict]:
    return [r for d in _get_run_dirs() if (r := _parse_run_dir(d))]


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
        return jsonify({'error': 'no readings yet'}), 404
    return jsonify(row)


@app.get('/reading/latest/photo')
def get_latest_photo():
    row = _get_latest()
    if not row or not row.get('photo_path'):
        return jsonify({'error': 'no photo available'}), 404
    path = Path(row['photo_path'])
    if not path.exists():
        return jsonify({'error': 'photo file not found'}), 404
    return send_file(path, mimetype='image/jpeg', conditional=True)


@app.get('/reading/latest/thermal')
def get_latest_thermal():
    row = _get_latest()
    if not row or not row.get('thermal_raw_path'):
        return jsonify({'error': 'no thermal data available'}), 404
    path = Path(row['thermal_raw_path'])
    if not path.exists():
        return jsonify({'error': 'thermal file not found'}), 404
    return send_file(path, mimetype='application/json')


@app.get('/readings')
def get_readings():
    rows = _get_all()
    for r in rows:
        r.pop('photo_path', None)
        r.pop('thermal_path', None)
        r.pop('thermal_raw_path', None)
    return jsonify(rows)


@app.post('/trigger')
def post_trigger():
    with _lock:
        if _status == 'capturing':
            return jsonify({'error': 'capture already in progress'}), 409
    threading.Thread(target=_capture_worker, daemon=True).start()
    return jsonify({'status': 'capturing'}), 202


@app.post('/config')
def post_config():
    global _met, _clo
    data = request.get_json(force=True, silent=True) or {}
    with _lock:
        if 'met' in data:
            _met = float(data['met'])
        if 'clo' in data:
            _clo = float(data['clo'])
        return jsonify({'met': _met, 'clo': _clo})


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
    import subprocess
    conf = Path('/etc/hostapd/hostapd.conf')
    lines = conf.read_text().splitlines()
    conf.write_text('\n'.join(
        f'wpa_passphrase={password}' if l.startswith('wpa_passphrase=') else l
        for l in lines
    ) + '\n')
    subprocess.run(['sudo', 'systemctl', 'restart', 'hostapd'], check=True)


# ── Dashboard ──────────────────────────────────────────────────────────────────

@app.get('/')
def dashboard():
    rows = _get_all()
    with _lock:
        current_status = _status
    return render_template_string(
        _DASHBOARD_HTML,
        status=current_status,
        latest=rows[0] if rows else None,
        rows=rows,
        firmware=FIRMWARE_VERSION,
    )


@app.get('/export.csv')
def export_csv():
    rows = _get_all()
    for r in rows:
        r.pop('photo_path', None)
        r.pop('thermal_path', None)
        r.pop('thermal_raw_path', None)
    output = io.StringIO()
    if rows:
        writer = csv.DictWriter(output, fieldnames=rows[0].keys())
        writer.writeheader()
        writer.writerows(rows)
    return Response(
        output.getvalue(),
        mimetype='text/csv',
        headers={'Content-Disposition': 'attachment; filename=readings.csv'},
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
  .container { max-width: 900px; margin: 24px auto; padding: 0 16px; }
  .card { background: #fff; border-radius: 10px; padding: 24px;
          margin-bottom: 20px; box-shadow: 0 1px 4px rgba(0,0,0,0.07); }
  .card h2 { font-size: 10px; font-weight: 700; letter-spacing: 2px;
             text-transform: uppercase; color: #7a8fa6;
             margin-bottom: 16px; padding-bottom: 8px; border-bottom: 2px solid #edf0f4; }
  .grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(130px, 1fr)); gap: 16px; }
  .metric .value { font-size: 26px; font-weight: 700; }
  .metric .unit  { font-size: 13px; color: #7a8fa6; margin-left: 2px; }
  .metric .label { font-size: 11px; color: #9aaaba; margin-top: 4px; }
  .notes { margin-top: 14px; font-size: 12px; color: #7a8fa6; }
  table { width: 100%; border-collapse: collapse; font-size: 13px; }
  th { background: #f4f6f9; color: #7a8fa6; font-size: 10px; font-weight: 700;
       letter-spacing: 1px; text-transform: uppercase;
       padding: 9px 12px; text-align: left; border-bottom: 2px solid #e4e8ee; }
  td { padding: 9px 12px; border-bottom: 1px solid #f0f2f5; }
  tr:last-child td { border-bottom: none; }
  a.export { display: inline-block; margin-top: 14px; font-size: 12px;
             color: #2a3f6f; text-decoration: none; }
  a.export:hover { text-decoration: underline; }
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

  {% if latest %}
  <div class="card">
    <h2>Latest Reading &nbsp;·&nbsp; {{ latest.timestamp }}</h2>
    <div class="grid">
      <div class="metric">
        <div class="value">{{ latest.pmv if latest.pmv is not none else '—' }}</div>
        <div class="label">PMV</div>
      </div>
      <div class="metric">
        <div class="value">{{ latest.ppd if latest.ppd is not none else '—' }}<span class="unit">%</span></div>
        <div class="label">PPD</div>
      </div>
      <div class="metric">
        <div class="value">{{ latest.air_temp if latest.air_temp is not none else '—' }}<span class="unit">°C</span></div>
        <div class="label">Air Temp</div>
      </div>
      <div class="metric">
        <div class="value">{{ latest.humidity if latest.humidity is not none else '—' }}<span class="unit">%</span></div>
        <div class="label">Humidity</div>
      </div>
      <div class="metric">
        <div class="value">{{ latest.mrt if latest.mrt is not none else '—' }}<span class="unit">°C</span></div>
        <div class="label">MRT</div>
      </div>
      <div class="metric">
        <div class="value">{{ latest.air_speed if latest.air_speed is not none else '—' }}<span class="unit">m/s</span></div>
        <div class="label">Air Speed</div>
      </div>
    </div>
    {% if latest.notes and latest.notes != 'No notes.' %}
    <div class="notes">{{ latest.notes }}</div>
    {% endif %}
  </div>
  {% else %}
  <div class="card"><span class="none">No readings yet.</span></div>
  {% endif %}

  <div class="card">
    <h2>Reading History</h2>
    {% if rows %}
    <table>
      <tr>
        <th>Timestamp</th><th>PMV</th><th>PPD %</th>
        <th>Temp °C</th><th>RH %</th><th>MRT °C</th><th>Air m/s</th><th>TSV</th>
      </tr>
      {% for r in rows %}
      <tr>
        <td>{{ r.timestamp }}</td>
        <td>{{ r.pmv       if r.pmv       is not none else '—' }}</td>
        <td>{{ r.ppd       if r.ppd       is not none else '—' }}</td>
        <td>{{ r.air_temp  if r.air_temp  is not none else '—' }}</td>
        <td>{{ r.humidity  if r.humidity  is not none else '—' }}</td>
        <td>{{ r.mrt       if r.mrt       is not none else '—' }}</td>
        <td>{{ r.air_speed if r.air_speed is not none else '—' }}</td>
        <td>{{ r.tsv       if r.tsv              else '—' }}</td>
      </tr>
      {% endfor %}
    </table>
    <a class="export" href="/export.csv">↓ Export as CSV</a>
    {% else %}
    <span class="none">No readings yet.</span>
    {% endif %}
  </div>

</div>
</body>
</html>"""


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 80))
    app.run(host='0.0.0.0', port=port, debug=False)
