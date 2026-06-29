import re
import shutil
import subprocess
import time
from pathlib import Path
from threading import Thread
from picamera2 import Picamera2
from PIL import Image, ImageTk
import tkinter as tk
from evdev import InputDevice, ecodes, list_devices

from readings import capture_data, DATA_DIR
from llm import run
from connection import (
	is_connected, connect_saved, connect_to_hotspot,
	save_wifi_creds, get_known_ssids, scan_nearby_ssids,
)

_ARCHIVE_DIR = Path(DATA_DIR).parent / "data_archive"

def _screen_geometry():
	"""Prefers a non-primary screen when two are connected, otherwise uses whichever is available."""
	try:
		out = subprocess.check_output(['xrandr', '--query'], text=True)
		screens = []
		for line in out.splitlines():
			if ' connected ' in line:
				m = re.search(r'(\d+)x(\d+)\+(\d+)\+(\d+)', line)
				if m:
					w, h, x, y = int(m.group(1)), int(m.group(2)), int(m.group(3)), int(m.group(4))
					screens.append((w, h, x, y))
		if not screens:
			raise ValueError("no screens found")
		if len(screens) == 1:
			w, h, x, y = screens[0]
		else:
			secondary = [s for s in screens if s[2] != 0 or s[3] != 0]
			w, h, x, y = secondary[0] if secondary else screens[-1]
		return f"{w}x{h}+{x}+{y}", w, h, x, y
	except Exception:
		return "1024x768+0+0", 1024, 768, 0, 0

def _archive_capture() -> Path:
	ts = time.strftime('%Y-%m-%d_%H-%M-%S')
	dest = _ARCHIVE_DIR / ts
	dest.mkdir(parents=True, exist_ok=True)
	for fname in ('data.txt', 'image.jpg', 'thermal.png'):
		src = Path(DATA_DIR) / fname
		if src.exists():
			shutil.copy2(src, dest / fname)
	return dest

if __name__ == "__main__":
	_running = False
	_photo = None
	picam2 = None

	_geometry, _sw, _sh, _sx, _sy = _screen_geometry()
	print(f"Target screen: {_geometry}")

	def _make_picam():
		cam = Picamera2()
		cam.configure(cam.create_preview_configuration(
			main={"size": (_sw, _sh), "format": "RGB888"}
		))
		cam.start()
		return cam

	root = tk.Tk()
	root.overrideredirect(True)
	root.geometry(_geometry)
	root.configure(bg="black")

	# ── Camera frame ──────────────────────────────────────────────────────────
	camera_frame = tk.Frame(root, bg="black")
	camera_frame.place(x=0, y=0, width=_sw, height=_sh)

	preview_label = tk.Label(camera_frame, bg="black")
	preview_label.place(x=0, y=0, width=_sw, height=_sh)

	def update_preview():
		global _photo
		if not _running and picam2 is not None:
			try:
				frame = picam2.capture_array()
				img = Image.fromarray(frame).rotate(180)
				_photo = ImageTk.PhotoImage(img)
				preview_label.config(image=_photo)
			except Exception:
				pass
		root.after(50, update_preview)

	def trigger():
		global _running, picam2
		if picam2 is None or _running:
			return
		_running = True
		btn.config(state="disabled", bg="#555", text="Processing...")

		def work():
			global _running, picam2
			archive = None
			try:
				root.after(0, lambda: btn.config(text="Taking photo..."))
				picam2.stop()
				picam2.close()
				time.sleep(0.5)
				capture_data()
				archive = _archive_capture()
				root.after(0, lambda: btn.config(text="Analysing..."))
				run(DATA_DIR)
				shutil.rmtree(archive, ignore_errors=True)
				root.after(0, lambda: btn.config(bg="#4caf50", text="Email sent!"))
			except Exception as e:
				print(f"Error: {e}")
				if archive and archive.exists():
					root.after(0, lambda: btn.config(bg="#ff9800", text="Saved — will send when online"))
				else:
					root.after(0, lambda: btn.config(text="Error — check logs"))
			finally:
				picam2 = _make_picam()
				_running = False
				root.after(3000, lambda: btn.config(
					state="normal", bg="#2196F3", text="CAPTURE"
				))

		Thread(target=work, daemon=True).start()

	btn = tk.Button(
		camera_frame,
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

	# ── Network list frame ────────────────────────────────────────────────────
	_kbd_shift = [False]
	_kbd_num = [False]
	_KBD_ALPHA = ['qwertyuiop', 'asdfghjkl', 'zxcvbnm']
	_KBD_NUM   = ['1234567890', '!@#$%&*-_+', '.,:;\'"()/\\']
	_selected_ssid = [None]

	net_list_frame = tk.Frame(root, bg="#1a1a1a")
	net_list_frame.place(x=0, y=0, width=_sw, height=_sh)

	tk.Label(net_list_frame, text="Select a Network", fg="white", bg="#1a1a1a",
		font=("Arial", 20, "bold")).pack(pady=(12, 4))

	scan_status = tk.Label(net_list_frame, text="", fg="#888888", bg="#1a1a1a",
		font=("Arial", 13))
	scan_status.pack()

	net_scroll_frame = tk.Frame(net_list_frame, bg="#1a1a1a")
	net_scroll_frame.pack(fill="both", expand=True, padx=20, pady=4)

	def _flush_queue():
		folders = sorted(p.parent for p in _ARCHIVE_DIR.glob("*/data.txt"))
		if not folders or _running:
			return
		def _send():
			for folder in folders:
				try:
					root.after(0, lambda f=folder: btn.config(
						state="disabled", bg="#ff9800",
						text=f"Sending {f.name}..."
					))
					run(str(folder))
					shutil.rmtree(folder, ignore_errors=True)
				except Exception as e:
					print(f"Queue send failed for {folder.name}: {e}")
					break
			root.after(0, lambda: btn.config(
				state="normal", bg="#2196F3", text="CAPTURE"
			))
		Thread(target=_send, daemon=True).start()

	def _show_camera():
		global picam2
		picam2 = _make_picam()
		camera_frame.tkraise()
		update_preview()
		root.after(3000, _flush_queue)

	def _on_network_tap(ssid, known):
		if known:
			scan_status.config(text=f"Connecting to {ssid}...", fg="#888888")
			def _do():
				success, msg = connect_saved(ssid)
				if success:
					root.after(0, _show_camera)
				else:
					root.after(0, lambda: scan_status.config(text=f"Failed: {msg}", fg="#f44336"))
			Thread(target=_do, daemon=True).start()
		else:
			_selected_ssid[0] = ssid
			ssid_label.config(text=ssid)
			pw_var.set("")
			pw_status.config(text="")
			connect_btn.config(state="normal", text="Connect")
			pwd_frame.tkraise()
			pw_entry.focus_force()

	def _populate_networks(networks, known):
		for w in net_scroll_frame.winfo_children():
			w.destroy()
		if not networks:
			tk.Label(net_scroll_frame, text="No networks found.", fg="#888888",
				bg="#1a1a1a", font=("Arial", 14)).pack(pady=20)
			return
		for ssid in networks:
			is_known = ssid in known
			row = tk.Frame(net_scroll_frame, bg="#2a2a2a", cursor="hand2")
			row.pack(fill="x", pady=3, ipady=8)
			tk.Label(row, text=ssid, fg="white", bg="#2a2a2a",
				font=("Arial", 15, "bold"), anchor="w").pack(side="left", padx=12)
			if is_known:
				tk.Label(row, text="saved", fg="#4caf50", bg="#2a2a2a",
					font=("Arial", 12)).pack(side="right", padx=12)
			row.bind("<Button-1>", lambda e, s=ssid, k=is_known: _on_network_tap(s, k))
			for child in row.winfo_children():
				child.bind("<Button-1>", lambda e, s=ssid, k=is_known: _on_network_tap(s, k))

	def _do_scan():
		root.after(0, lambda: scan_status.config(text="Scanning...", fg="#888888"))
		networks = scan_nearby_ssids()
		known = get_known_ssids()
		networks.sort(key=lambda s: (0 if s in known else 1, s))
		root.after(0, lambda: scan_status.config(text=""))
		root.after(0, lambda: _populate_networks(networks, known))

	tk.Button(net_list_frame, text="↻  Refresh", font=("Arial", 16, "bold"),
		bg="#333", fg="white", activebackground="#555", relief="flat", bd=0,
		command=lambda: Thread(target=_do_scan, daemon=True).start()
	).pack(pady=(0, 6), ipadx=20, ipady=10, padx=20, fill="x")

	# ── Password frame ────────────────────────────────────────────────────────
	pwd_frame = tk.Frame(root, bg="#1a1a1a")
	pwd_frame.place(x=0, y=0, width=_sw, height=_sh)

	tk.Label(pwd_frame, text="Enter Password", fg="white", bg="#1a1a1a",
		font=("Arial", 20, "bold")).pack(pady=(12, 4))

	ssid_label = tk.Label(pwd_frame, text="", fg="#888888", bg="#1a1a1a",
		font=("Arial", 15))
	ssid_label.pack()

	pw_var = tk.StringVar()
	pw_entry = tk.Entry(pwd_frame, textvariable=pw_var, font=("Arial", 16),
		bg="white", fg="black", insertbackground="black", show="*", relief="flat")
	pw_entry.pack(pady=(8, 4), ipady=5, padx=30, fill="x")
	pw_entry.bind("<Button-1>", lambda e: pw_entry.focus_force())

	pw_status = tk.Label(pwd_frame, text="", fg="#f44336", bg="#1a1a1a",
		font=("Arial", 12, "bold"))
	pw_status.pack(pady=(0, 2))

	def do_connect():
		ssid = _selected_ssid[0]
		pw = pw_var.get().strip()
		pw_status.config(text="")
		connect_btn.config(state="disabled", text="Connecting...")
		def work():
			success, msg = connect_to_hotspot(ssid, pw)
			if success:
				save_wifi_creds(ssid, pw)
				root.after(0, _show_camera)
			else:
				root.after(0, lambda: (
					connect_btn.config(state="normal", text="Connect"),
					pw_status.config(text=f"Failed: {msg}", fg="#f44336"),
				))
		Thread(target=work, daemon=True).start()

	btn_row = tk.Frame(pwd_frame, bg="#1a1a1a")
	btn_row.pack(pady=4)

	tk.Button(btn_row, text="← Back", font=("Arial", 18, "bold"),
		bg="#555", fg="white", activebackground="#444", relief="flat", bd=0,
		command=lambda: net_list_frame.tkraise()
	).pack(side="left", ipadx=20, ipady=12, padx=(0, 10))

	connect_btn = tk.Button(btn_row, text="Connect", font=("Arial", 18, "bold"),
		bg="#2196F3", fg="white", activebackground="#1565C0", relief="flat", bd=0,
		command=do_connect,
	)
	connect_btn.pack(side="left", ipadx=24, ipady=12)

	# ── On-screen keyboard (password frame only) ──────────────────────────────
	kbd_frame = tk.Frame(pwd_frame, bg="#222")
	kbd_frame.pack(side="bottom", fill="x")

	def _kpress(ch):
		c = ch.upper() if _kbd_shift[0] else ch
		pw_entry.insert(tk.INSERT, c)
		if _kbd_shift[0]:
			_kbd_shift[0] = False
			_kbuild()

	def _kback():
		pos = pw_entry.index(tk.INSERT)
		if pos > 0:
			pw_entry.delete(pos - 1)

	def _kspace():
		pw_entry.insert(tk.INSERT, ' ')

	def _kbuild():
		for child in kbd_frame.winfo_children():
			child.destroy()
		rows = _KBD_NUM if _kbd_num[0] else _KBD_ALPHA
		kfont = ("Arial", 22, "bold")
		kpad = max(10, _sh // 32)
		for row in rows:
			rf = tk.Frame(kbd_frame, bg="#222")
			rf.pack(fill="x", pady=1, padx=2)
			for ch in row:
				label = ch.upper() if (_kbd_shift[0] and not _kbd_num[0]) else ch
				tk.Button(rf, text=label, font=kfont,
					bg="#3a3a3a", fg="white", activebackground="#555",
					relief="flat", bd=0,
					command=lambda c=ch: _kpress(c)
				).pack(side="left", expand=True, fill="both", padx=1, ipady=kpad)
		bf = tk.Frame(kbd_frame, bg="#222")
		bf.pack(fill="x", pady=1, padx=2)
		tk.Button(bf, text="ABC" if _kbd_num[0] else "?123", font=kfont,
			bg="#555", fg="white", relief="flat", bd=0,
			command=lambda: (_kbd_num.__setitem__(0, not _kbd_num[0]), _kbuild())
		).pack(side="left", fill="both", padx=1, ipady=kpad)
		if not _kbd_num[0]:
			tk.Button(bf, text="⇧", font=kfont,
				bg="#2196F3" if _kbd_shift[0] else "#555", fg="white",
				relief="flat", bd=0,
				command=lambda: (_kbd_shift.__setitem__(0, not _kbd_shift[0]), _kbuild())
			).pack(side="left", fill="both", padx=1, ipady=kpad)
		tk.Button(bf, text="space", font=kfont, bg="#3a3a3a", fg="white",
			relief="flat", bd=0, command=_kspace
		).pack(side="left", expand=True, fill="both", padx=1, ipady=kpad)
		tk.Button(bf, text="⌫", font=kfont, bg="#555", fg="white",
			relief="flat", bd=0, command=_kback
		).pack(side="left", fill="both", padx=1, ipady=kpad)

	_kbuild()

	# ── Startup ───────────────────────────────────────────────────────────────
	if is_connected():
		root.after(0, _show_camera)
	else:
		net_list_frame.tkraise()
		Thread(target=_do_scan, daemon=True).start()

	# ── Touch listener ────────────────────────────────────────────────────────
	def _find_touch_device():
		for path in list_devices():
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

	root.bind("<Escape>", lambda e: root.destroy())
	root.mainloop()
	if picam2 is not None:
		picam2.stop()
