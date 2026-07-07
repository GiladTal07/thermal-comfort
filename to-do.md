# To-Do

## Multithreaded architecture

- [x] Add `send_queue` and `status_queue` as `queue.Queue` instances at the top of `if __name__ == "__main__":` in `app.py`

- [x] Write `reader_loop()` and start it as a daemon thread at startup
  - On startup, scan `ARCHIVE_DIR` for leftover folders and add them to a local `pending` list
  - Block on `send_queue.get(timeout=15)` — timeout ensures the loop wakes to recheck connectivity even when idle
  - When `is_connected()` and `pending` is non-empty: call `run()`, delete folder on success, push status to `status_queue`; on failure put folder back at front of `pending` and push error status

- [x] Gut `trigger()` / `work()` down to camera and archive only
  - `work()` stops camera, captures, archives, puts path on `send_queue`, restarts camera — no connectivity check, no `run()` call
  - Button locks via `sending[0]` until Reader reports `done` or `error` via `poll_status()`

- [x] Delete `flush_queue()` entirely

- [x] Add `poll_status()` registered via `root.after`
  - Drains `status_queue` every 200ms, updates button label, restarts Reader thread if dead

- [x] Update `poll_connection()` to remove its `flush_queue()` call

- [x] Remove the `archive_capture()` fallback delete — `work()` rewrite eliminated the direct-send fast path entirely
