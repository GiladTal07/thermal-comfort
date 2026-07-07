# Architecture Design: Capture / Reader Split (Threads)

## Motivation

The current single-process app entangles capture and sending. Internet connectivity can drop
at any point during `trigger()` — between the photo being taken, the archive being written, the
LLM call, and the email send — and each of those moments produces a different failure mode that
needs to be handled separately.

The fix is to make the capture code completely unaware of the network. It writes data to disk
and stops there. A dedicated Reader thread owns all network-dependent work and handles every
connectivity state in one place. This is a single Python process with two threads — no IPC
serialization, no process supervision, no extra interpreter overhead.

---

## Threads

### Main thread (Capture)

Owns everything the user sees and touches. Never calls the LLM or sends email.

- Tkinter UI and all frames
- Camera preview and capture
- Sensor readings
- Writes completed captures to `ARCHIVE_DIR` via `archive_capture()`
- Wi-Fi management UI (network list, password entry)
- When a capture is complete, calls `send_queue.put(folder_path)` and is done — it does not
  check connectivity, does not call `run()`, and does not manage retries
- Polls `status_queue` via `root.after` to update the CAPTURE button label

### Reader (worker thread)

A daemon thread, started once at app launch, that waits around until it has both data and a
connection. Shares the process with the main thread but touches no UI state and no camera state.

- Blocks on `send_queue.get()` with a timeout, so it also wakes periodically to recheck
  connectivity even with no new jobs
- On startup, scans `ARCHIVE_DIR` and queues any folders left over from a previous session or
  an interrupted run
- Polls connectivity (`is_connected()`) independently of the main thread's own Wi-Fi UI
- When a folder is available and the device is online: calls `run(folder)`, deletes the folder
  on success, pushes a status message to `status_queue`
- If the connection drops mid-send, `run()` raises, the folder is left on disk, and the loop
  retries on its next wake
- The loop body is wrapped in `try/except` so one bad job (e.g. malformed archive) can't kill
  the thread — an uncaught exception inside a thread function silently ends that thread, with
  no automatic restart, unlike a crashed process which the main thread can detect and respawn

---

## What Capture no longer does

- Checks `is_connected()` before deciding to send
- Calls `run()`
- Manages `flush_queue` or any retry logic
- Spawns a one-off `send` thread per flush attempt
- Shows "Analysing..." or "Email sent!" from inside its own capture function

The only network-aware code left in the main thread is the Wi-Fi management UI (nmcli calls to
connect to a network). That is purely user-driven and not part of the data pipeline.

---

## Communication

Two `queue.Queue` instances created at startup, shared by reference between the two threads —
no serialization, no pickling, just Python objects passed directly.

```
Capture ──send_queue──▶ Reader
Capture ◀──status_queue── Reader
```

### Job message (Capture → Reader)

```python
str  # absolute path to an archive folder
     # e.g. "/home/pi/data/data_archive/2026-06-30_14-22-01"
```

### Status message (Reader → Capture)

```python
{
    "folder": str,   # archive path that was processed
    "status": str,   # "sending" | "done" | "error"
    "detail": str,   # shown in the UI button label
}
```

Capture polls `status_queue` via `root.after` on the main thread (no extra threads needed for
UI updates) and updates the button label accordingly.

---

## Reader loop

```python
def reader_loop():
    try:
        pending = scan_archive_dir_for_leftovers()
    except Exception as e:
        print(f"Reader: startup scan failed: {e}")
        pending = []

    while True:
        try:
            try:
                folder = send_queue.get(timeout=15)
                pending.append(folder)
            except queue.Empty:
                pass

            if pending and is_connected():
                folder = pending.pop(0)
                status_queue.put({"folder": folder, "status": "sending", "detail": f"Sending {folder.name}..."})
                try:
                    run(str(folder))
                    shutil.rmtree(folder, ignore_errors=True)
                    status_queue.put({"folder": folder, "status": "done", "detail": "Email sent!"})
                except Exception as e:
                    pending.insert(0, folder)
                    status_queue.put({"folder": folder, "status": "error", "detail": str(e)})

        except Exception as e:
            # Catch anything not already handled above (e.g. is_connected() failing,
            # status_queue.put() raising, unexpected state). Log and continue — the
            # outer while True keeps the thread alive regardless.
            print(f"Reader: unexpected error: {e}")

reader_thread = Thread(target=reader_loop, daemon=True)
reader_thread.start()
```

The outer `try/except` wraps the entire loop body so that no unhandled exception can escape the
`while True` and silently kill the thread. The inner `try/except` around `run()` is kept
separate so that a send failure can put the folder back at the front of `pending` before the
outer handler would swallow that context.

The 15-second timeout on the queue wait means the Reader wakes up at least every 15 seconds to
check connectivity even if no new jobs arrive, which handles the reconnect-after-offline case.

## Dead thread detection

A thread that raises outside all `try/except` blocks dies silently — `daemon=True` means it
takes no other thread with it, but there is no automatic restart. The outer guard above makes
this unlikely, but `poll_status()` should also check liveness and restart if needed:

```python
def poll_status():
    global reader_thread
    while not status_queue.empty():
        msg = status_queue.get_nowait()
        # update btn label based on msg["status"] / msg["detail"]

    if not reader_thread.is_alive():
        print("Reader thread died — restarting")
        reader_thread = Thread(target=reader_loop, daemon=True)
        reader_thread.start()

    root.after(200, poll_status)
```

`reader_thread` must be a named variable (not anonymous) so `poll_status` can call
`is_alive()` on it and reassign on restart. Because `poll_status` runs on the main thread via
`root.after`, the reassignment to `reader_thread` is not a race condition.

---

## Key flows

### Capture while online

1. Capture: `archive_capture()` → `send_queue.put(path)` → shows "Saved, sending..."
2. Reader: receives job, `is_connected()` = True → calls `run()` → pushes `{done}` → deletes folder
3. Capture: polls `status_queue` → updates button to "Email sent!"

### Capture while offline

1. Capture: `archive_capture()` → `send_queue.put(path)` → shows "Saved — will send when online"
2. Reader: receives job, `is_connected()` = False → adds to pending list, waits
3. Later: Reader's 15s loop wakes, `is_connected()` = True → sends all pending folders in order

### Internet drops mid-send

1. Reader: `run()` raises partway through → folder stays on disk (not deleted)
2. Reader: puts folder back at front of pending list → retries on next connectivity check
3. Capture UI: receives `{error}` status → shows transient error label or nothing (folder is safe)

### App crash or Pi reboot

1. On next startup, Reader scans `ARCHIVE_DIR` and finds any unsent folders
2. Re-queues them automatically before processing any new jobs

---

## Threads vs. processes

|  | Two threads (this design) | Two processes |
|---|---|---|
| **Communication** | `queue.Queue`, passes Python objects by reference — no serialization | `multiprocessing.Queue` — every message is pickled and unpickled |
| **Memory overhead** | One Python interpreter, shared memory | Two full interpreters, each with its own copy of imports/runtime — meaningful on a Pi |
| **Startup complexity** | `Thread(...).start()` — no ordering concerns | Must create queues before either side starts; both ends need the same queue references |
| **Crash isolation** | An uncaught exception in the worker thread kills only that thread (if unguarded by try/except); a fatal interpreter-level fault (e.g. C-extension segfault) takes down both threads since they share one interpreter | A crash in the Reader process — including a fatal interpreter-level fault — cannot bring down Capture; the OS keeps them fully separate |
| **Recovery** | Main thread has no built-in way to detect a dead worker thread; must be designed in (e.g. a heartbeat) | Main process can call `reader.is_alive()` and respawn cleanly — process death is observable by design |
| **GIL contention** | Both threads share the GIL; CPU-bound work in the Reader (e.g. base64 image encoding) briefly blocks the main thread's bytecode execution, though I/O waits release the GIL | Each process has its own GIL; the Reader's CPU-bound work never contends with Capture's UI loop |
| **Debugging** | One process, one set of logs, a single debugger session sees both threads | Two log streams, two PIDs; correlating a failure across both requires more tooling |
| **Code complexity** | Minimal — a thread, a `queue.Queue`, a `try/except` | Higher — process spawn, queue setup, liveness checks, restart logic |

### Why threads for this app

The actual risk being designed against — Capture's logic accidentally depending on or being
blocked by network state — is solved by **not sharing mutable state across the boundary**, not
by the OS process boundary itself. As long as the Reader thread never touches `picam2`, `running`,
or any camera/UI state, a disconnect at any point inside it cannot corrupt Capture's state,
exactly as a process boundary would guarantee. The scenarios where a process boundary earns its
complexity — protection from a fatal interpreter-level crash, or genuine memory isolation for a
heavy workload like a local LLM — don't apply here: `run()` only calls a remote API and SMTP,
both pure-Python paths with no meaningful crash or memory risk. If that changes (e.g. running a
local model), this design promotes to two processes with the job/status queue API unchanged.
