#!/usr/bin/env python3
from pathlib import Path
from datetime import datetime

ROOT = Path("/volume1/docker/nas-stack")


def backup(path):
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    bak = path.with_suffix(path.suffix + ".sprint16." + ts + ".bak")
    bak.write_text(path.read_text(errors="replace"), errors="replace")
    print("backup:", bak)


def ensure_line_after(text, marker, line):
    if line in text:
        return text

    idx = text.find(marker)
    if idx == -1:
        return text

    end = text.find("\n", idx)
    if end == -1:
        return text + "\n" + line + "\n"

    return text[:end + 1] + line + "\n" + text[end + 1:]


def patch_scanner():
    path = ROOT / "scanner.py"
    if not path.exists():
        print("scanner.py ontbreekt")
        return

    text = path.read_text(errors="replace")
    backup(path)

    text = ensure_line_after(text, "LOCK_TTL", 'HEARTBEAT_KEY = "scanner:heartbeat"')
    text = ensure_line_after(text, 'HEARTBEAT_KEY = "scanner:heartbeat"', 'HEARTBEAT_TTL = 90')
    text = ensure_line_after(text, 'HEARTBEAT_TTL = 90', 'LAST_SCAN_KEY = "scanner:last_scan"')

    if "def send_heartbeat(" not in text:
        marker = "\ndef main("
        fn = '''
def send_heartbeat(status="running"):
    try:
        now = datetime.now(timezone.utc).isoformat()
        r.set(HEARTBEAT_KEY, now, ex=HEARTBEAT_TTL)
        r.set("scanner:heartbeat:status", status, ex=HEARTBEAT_TTL)
    except Exception as e:
        logger.warning("heartbeat failed: %s", e)

'''
        text = text.replace(marker, "\n" + fn + "def main(", 1)

    if 'send_heartbeat("started")' not in text:
        text = text.replace(
            'logger.info("Starting polling scanner',
            'send_heartbeat("started")\n    logger.info("Starting polling scanner',
            1
        )

    if 'send_heartbeat("running")' not in text:
        text = text.replace(
            "refresh_lock()\n",
            "refresh_lock()\n        send_heartbeat(\"running\")\n",
            1
        )

    if 'r.set(LAST_SCAN_KEY' not in text:
        text = text.replace(
            'logger.info("Scan done:',
            'r.set(LAST_SCAN_KEY, datetime.now(timezone.utc).isoformat(), ex=HEARTBEAT_TTL * 4)\n            logger.info("Scan done:',
            1
        )
        text = text.replace(
            'logger.info("Scan complete:',
            'r.set(LAST_SCAN_KEY, datetime.now(timezone.utc).isoformat(), ex=HEARTBEAT_TTL * 4)\n            logger.info("Scan complete:',
            1
        )

    path.write_text(text)
    print("scanner.py patched")


def patch_worker():
    path = ROOT / "metadata_worker.py"
    if not path.exists():
        print("metadata_worker.py ontbreekt")
        return

    text = path.read_text(errors="replace")
    backup(path)

    text = ensure_line_after(text, "LOCK_TTL", 'HEARTBEAT_KEY = "metadata_worker:heartbeat"')
    text = ensure_line_after(text, 'HEARTBEAT_KEY = "metadata_worker:heartbeat"', 'HEARTBEAT_TTL = 90')
    text = ensure_line_after(text, 'HEARTBEAT_TTL = 90', 'LAST_EVENT_KEY = "metadata_worker:last_event"')

    if "def send_heartbeat(" not in text:
        marker = "\ndef main("
        fn = '''
def send_heartbeat(status="running"):
    try:
        now = datetime.now(timezone.utc).isoformat()
        r.set(HEARTBEAT_KEY, now, ex=HEARTBEAT_TTL)
        r.set("metadata_worker:heartbeat:status", status, ex=HEARTBEAT_TTL)
    except Exception as e:
        logger.warning("heartbeat failed: %s", e)

'''
        text = text.replace(marker, "\n" + fn + "def main(", 1)

    if 'send_heartbeat("started")' not in text:
        text = text.replace(
            'logger.info("Worker started")',
            'send_heartbeat("started")\n    logger.info("Worker started")',
            1
        )

    if 'send_heartbeat("running")' not in text:
        text = text.replace(
            "refresh_lock()\n",
            "refresh_lock()\n        send_heartbeat(\"running\")\n",
            1
        )

    if 'r.set(LAST_EVENT_KEY' not in text:
        text = text.replace(
            "process_event(cur, data)",
            "process_event(cur, data)\n                    r.set(LAST_EVENT_KEY, datetime.now(timezone.utc).isoformat(), ex=HEARTBEAT_TTL * 4)",
            1
        )

    path.write_text(text)
    print("metadata_worker.py patched")


def main():
    patch_scanner()
    patch_worker()
    print("Sprint 1.6 patch klaar.")


if __name__ == "__main__":
    main()
