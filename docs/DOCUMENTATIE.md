# NAS Metadata Platform Documentatie

_Automatisch gegenereerd op 2026-07-26 20:18:07_


---

# NAS Metadata Platform Wiki

Deze wiki wordt automatisch gegenereerd door de documentatiegenerator.

## Hoofdstukken

- [Architectuur](wiki/architecture.md)
- [Scanner](wiki/scanner.md)
- [Metadata Worker](wiki/metadata-worker.md)
- [Docker](wiki/docker.md)
- [PostgreSQL](wiki/postgres.md)
- [Redis](wiki/redis.md)
- [Scripts](wiki/scripts.md)
- [Troubleshooting](wiki/troubleshooting.md)
- [Documentatiegenerator](wiki/documentation-generator.md)
- [Bronbestanden](wiki/sources.md)

## Datastroom

```text
/volume1
  |
  v
Polling Scanner
  |
  v
Redis Stream: scan_stream
  |
  v
Metadata Worker
  |
  v
PostgreSQL

Fouten -> scan_stream_dlq
```


---

# Architectuur

De NAS Metadata Stack bestaat uit een polling scanner, Redis Streams, een metadata worker en PostgreSQL.

## Ontwerpkeuzes

- Geen host watcher meer.
- Geen inotify-afhankelijkheid.
- Scanner draait in Docker.
- Redis Streams koppelen scanner en worker los van elkaar.
- Consumer Groups maken gecontroleerde verwerking mogelijk.
- PostgreSQL bewaart de permanente metadata-index.
- Heartbeats en locks voorkomen dubbele processen.
- DLQ voorkomt dat slechte events de worker blokkeren.


---

# CORE Manifest

## Platform

- `name`: `NAS Metadata Platform`
- `version`: `2.2.0`
- `release`: `CORE Governance`

## Modules

### `scanner`

- `enabled`: `True`

### `metadata_worker`

- `enabled`: `True`

## Engines

### `documentation`

- `enabled`: `True`

### `project_intelligence`

- `enabled`: `True`

### `integrity`

- `enabled`: `True`

### `health`

- `enabled`: `True`

## Bron: core/core.yaml

```yaml
platform:
  name: NAS Metadata Platform
  version: 2.2.0
  release: CORE Governance

paths:
  root: /volume1/docker/nas-stack
  scan_root: /volume1

modules:
  scanner:
    enabled: true
  metadata_worker:
    enabled: true

engines:
  documentation:
    enabled: true
  project_intelligence:
    enabled: true
  integrity:
    enabled: true
  health:
    enabled: true
```


---

# RFC's

Aantal RFC's: `1`

## RFC-0001-core-foundation

- Titel: `RFC-0001 - CORE Foundation`
- Status: `Accepted`
- Bestand: `docs\rfc\RFC-0001-core-foundation.md`
- Regels: `27`

```markdown
# RFC-0001 - CORE Foundation

## Status

Accepted

## Goal

Introduce a stable project structure for CORE without breaking the existing scanner and metadata pipeline.

## Scope

- Add core manifest.
- Add database folder structure.
- Add RFC and standards folders.
- Keep existing runtime files in place.

## Non-goals

- Do not move scanner.py yet.
- Do not move metadata_worker.py yet.
- Do not change Docker Compose behavior yet.
- Do not clean legacy database records yet.

## Outcome

CORE 2.1 becomes the foundation for future Dispatcher, Job Engine, Integrity Engine and Documentation Engine work.
```



---

# Database Views

Aantal SQL-viewbestanden: `1`

## `database\views\file_integrity.sql`

- Regels: `19`
- Views:
  - `v_file_integrity`
- Drops:
  - `v_file_integrity`

```sql
-- v_file_integrity
-- CORE Integrity Engine v0.1
-- Diagnose-only view. Verwijdert niets.

DROP VIEW IF EXISTS v_file_integrity;

CREATE VIEW v_file_integrity AS
SELECT
    f.*,
    CASE
        WHEN f.path IS NULL OR f.path = '' THEN 'LEGACY_MISSING_PATH'
        WHEN f.folder_id IS NULL THEN 'INVALID_MISSING_FOLDER'
        WHEN f.hash_path IS NULL OR f.hash_path = '' THEN 'INCOMPLETE_MISSING_HASH_PATH'
        WHEN f.hash_content IS NULL OR f.hash_content = '' THEN 'INCOMPLETE_MISSING_HASH_CONTENT'
        WHEN f.mime_type IS NULL OR f.mime_type = '' THEN 'INCOMPLETE_MISSING_MIME'
        WHEN f.deleted_at IS NOT NULL THEN 'DELETED'
        ELSE 'VALID'
    END AS integrity_status
FROM files f;
```



---

# Scanner

Bronbestand: `scanner.py`

- Regels: `526`
- Functies: `26`
- Classes: `0`
- Imports: `9`

## Imports

- `datetime.datetime`
- `datetime.timezone`
- `logging`
- `os`
- `psycopg2`
- `redis`
- `socket`
- `time`
- `uuid`

## Constanten

- `CONSUMER_NAME` op regel `38`
- `DIRTY_ROOTS_KEY` op regel `34`
- `FULL_SCAN_INTERVAL` op regel `20`
- `FULL_SCAN_REQUEST_KEY` op regel `35`
- `HEARTBEAT_KEY` op regel `27`
- `HEARTBEAT_STATUS_KEY` op regel `28`
- `HEARTBEAT_TTL` op regel `36`
- `IGNORE_CONTAINS` op regel `44`
- `IGNORE_NAMES` op regel `43`
- `IGNORE_PREFIXES` op regel `42`
- `INTERVAL_ROOT_INDEX_KEY` op regel `33`
- `LAST_FULL_SCAN_KEY` op regel `30`
- `LAST_INTERVAL_ROOT_KEY` op regel `32`
- `LAST_INTERVAL_SCAN_KEY` op regel `31`
- `LAST_SCAN_KEY` op regel `29`
- `LOCK_KEY` op regel `24`
- `LOCK_TTL` op regel `25`
- `MISSING_SCAN_THRESHOLD` op regel `21`
- `REDIS_HOST` op regel `15`
- `REDIS_PORT` op regel `16`
- `SCAN_INTERVAL` op regel `19`
- `SCAN_ROOT` op regel `18`
- `SIGNATURE_PREFIX` op regel `39`
- `STATE_SEPARATOR` op regel `40`
- `STREAM_KEY` op regel `23`

## Redis keys / streams

- `scanner:heartbeat`
- `scanner:heartbeat:status`
- `scanner:lock:event`

## Functies

### `get_db()`

- Regel: `64`
- Docstring: _niet aanwezig_

### `session_call(query, params, fetch)`

- Regel: `78`
- Docstring: Run scan bookkeeping without making PostgreSQL a scanner dependency.

### `utc_now()`

- Regel: `90`
- Docstring: _niet aanwezig_

### `should_skip_path(path)`

- Regel: `94`
- Docstring: _niet aanwezig_

### `heartbeat(status)`

- Regel: `106`
- Docstring: _niet aanwezig_

### `acquire_lock()`

- Regel: `114`
- Docstring: _niet aanwezig_

### `refresh_lock()`

- Regel: `133`
- Docstring: _niet aanwezig_

### `release_lock()`

- Regel: `141`
- Docstring: _niet aanwezig_

### `discover_roots()`

- Regel: `149`
- Docstring: _niet aanwezig_

### `file_signature(path, st)`

- Regel: `169`
- Docstring: _niet aanwezig_

### `parse_file_state(raw)`

- Regel: `173`
- Docstring: _niet aanwezig_

### `encode_file_state(signature, scan_id, missing_scans)`

- Regel: `189`
- Docstring: _niet aanwezig_

### `changed(path, signature, scan_id, full_sweep)`

- Regel: `193`
- Docstring: _niet aanwezig_

### `mark_seen(path, scan_id)`

- Regel: `203`
- Docstring: _niet aanwezig_

### `reconcile_missing(scan_id, session_id, root_scope, threshold)`

- Regel: `210`
- Docstring: _niet aanwezig_

### `raise_walk_error(error)`

- Regel: `246`
- Docstring: _niet aanwezig_

### `select_interval_root(roots)`

- Regel: `250`
- Docstring: _niet aanwezig_

### `select_dirty_root(roots)`

- Regel: `262`
- Docstring: _niet aanwezig_

### `clear_dirty_root(root, expected_marker)`

- Regel: `276`
- Docstring: _niet aanwezig_

### `_scan_roots(roots, scan_id, session_id, full_sweep, scan_type, reconcile_scope, missing_threshold)`

- Regel: `286`
- Docstring: _niet aanwezig_

### `run_scan(scan_type, roots)`

- Regel: `394`
- Docstring: _niet aanwezig_

### `scan_once()`

- Regel: `425`
- Docstring: Run a complete reconciliation sweep (backward-compatible entry point).

### `scan_interval_once()`

- Regel: `433`
- Docstring: _niet aanwezig_

### `consume_full_scan_request()`

- Regel: `455`
- Docstring: _niet aanwezig_

### `wait_for_next_scan(seconds)`

- Regel: `464`
- Docstring: Wait interruptibly so a manual full request is picked up promptly.

### `main()`

- Regel: `475`
- Docstring: _niet aanwezig_

## SQL statements

### Statement regel `403`

```sql
SELECT create_scan_session(%s)
```

### Statement regel `380`

```sql
SELECT increment_files_discovered(%s, %s)
```

### Statement regel `381`

```sql
SELECT increment_jobs_enqueued(%s, %s)
```

### Statement regel `382`

```sql
SELECT finish_scan_session(%s)
```

### Statement regel `86`

```sql
Scan session update failed: %s
```

### Statement regel `419`

```sql
UPDATE scan_sessions SET status = 'failed', finished_at = NOW() WHERE id = %s
```

## Broncode

```python
#!/usr/bin/env python3
import os
import time
import socket
import logging
import uuid
from datetime import datetime, timezone

import redis
import psycopg2

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("scanner")

REDIS_HOST = os.getenv("REDIS_HOST", "redis")
REDIS_PORT = int(os.getenv("REDIS_PORT", "6379"))

SCAN_ROOT = os.getenv("SCAN_ROOT", "/volume1")
SCAN_INTERVAL = max(1, int(os.getenv("SCAN_INTERVAL", "600")))
FULL_SCAN_INTERVAL = max(SCAN_INTERVAL, int(os.getenv("FULL_SCAN_INTERVAL", "3600")))
MISSING_SCAN_THRESHOLD = max(1, int(os.getenv("MISSING_SCAN_THRESHOLD", "2")))

STREAM_KEY = os.getenv("STREAM_KEY", "scan_stream")
LOCK_KEY = "scanner:lock:event"
LOCK_TTL = 90

HEARTBEAT_KEY = "scanner:heartbeat"
HEARTBEAT_STATUS_KEY = "scanner:heartbeat:status"
LAST_SCAN_KEY = "scanner:last_scan"
LAST_FULL_SCAN_KEY = "scanner:last_full_scan"
LAST_INTERVAL_SCAN_KEY = "scanner:last_interval_scan"
LAST_INTERVAL_ROOT_KEY = "scanner:last_interval_root"
INTERVAL_ROOT_INDEX_KEY = "scanner:interval:root_index"
DIRTY_ROOTS_KEY = "scanner:dirty_roots"
FULL_SCAN_REQUEST_KEY = "scanner:request:full"
HEARTBEAT_TTL = 120

CONSUMER_NAME = socket.gethostname()
SIGNATURE_PREFIX = "scanner:sig:"
STATE_SEPARATOR = "\n"

IGNORE_PREFIXES = ("@", ".", "#")
IGNORE_NAMES = {"tmp", "lost+found"}
IGNORE_CONTAINS = (
    "/@eaDir/",
    "/#recycle/",
    "/.Trash/",
    "/docker/postgres/",
    "/docker/redis/",
)

r = redis.Redis(
    host=REDIS_HOST,
    port=REDIS_PORT,
    decode_responses=True,
    socket_timeout=30,
    socket_connect_timeout=10,
    retry_on_timeout=True,
)

_db_conn = None


def get_db():
    global _db_conn
    if _db_conn is None or _db_conn.closed:
        _db_conn = psycopg2.connect(
            host=os.getenv("DB_HOST"),
            port=int(os.getenv("DB_PORT", "5432")),
            user=os.getenv("DB_USER"),
            password=os.getenv("DB_PASS"),
            dbname=os.getenv("DB_NAME"),
        )
        _db_conn.autocommit = True
    return _db_conn


def session_call(query, params=(), fetch=False):
    """Run scan bookkeeping without making PostgreSQL a scanner dependency."""
    try:
        with get_db().cursor() as cur:
            cur.execute(query, params)
            row = cur.fetchone() if fetch else None
            return row[0] if row else None
    except Exception as exc:
        logger.warning("Scan session update failed: %s", exc)
        return None


def utc_now():
    return datetime.now(timezone.utc).isoformat()


def should_skip_path(path):
    parts = path.split(os.sep)
    for part in parts:
        if not part:
            continue
        if part in IGNORE_NAMES:
            return True
        if part.startswith(IGNORE_PREFIXES):
            return True
    return any(x in path for x in IGNORE_CONTAINS)


def heartbeat(status="running"):
    try:
        r.set(HEARTBEAT_KEY, utc_now(), ex=HEARTBEAT_TTL)
        r.set(HEARTBEAT_STATUS_KEY, status, ex=HEARTBEAT_TTL)
    except Exception as e:
        logger.warning("Heartbeat failed: %s", e)


def acquire_lock():
    owner = r.get(LOCK_KEY)
    if owner and owner != CONSUMER_NAME:
        owner_hb = r.get(HEARTBEAT_KEY)
        if owner_hb:
            logger.warning("Scanner already running: owner=%s heartbeat=%s", owner, owner_hb)
            return False
        logger.warning("Stale scanner lock found: owner=%s, taking over", owner)
        r.delete(LOCK_KEY)

    ok = r.set(LOCK_KEY, CONSUMER_NAME, nx=True, ex=LOCK_TTL)
    if not ok:
        logger.warning("Scanner lock busy: %s", r.get(LOCK_KEY))
        return False

    logger.info("Scanner lock acquired by %s", CONSUMER_NAME)
    return True


def refresh_lock():
    try:
        if r.get(LOCK_KEY) == CONSUMER_NAME:
            r.expire(LOCK_KEY, LOCK_TTL)
    except Exception as e:
        logger.warning("Lock refresh failed: %s", e)


def release_lock():
    try:
        if r.get(LOCK_KEY) == CONSUMER_NAME:
            r.delete(LOCK_KEY)
    except Exception:
        pass


def discover_roots():
    if not os.path.isdir(SCAN_ROOT):
        logger.error("SCAN_ROOT does not exist: %s", SCAN_ROOT)
        return []

    roots = []
    for name in os.listdir(SCAN_ROOT):
        path = os.path.join(SCAN_ROOT, name)
        if not os.path.isdir(path):
            continue
        if name in IGNORE_NAMES or name.startswith(IGNORE_PREFIXES):
            continue
        if should_skip_path(path):
            continue
        roots.append(path)

    roots.sort()
    return roots


def file_signature(path, st):
    return f"{int(st.st_mtime)}:{st.st_size}:{st.st_ino}"


def parse_file_state(raw):
    if not raw:
        return None, None, 0

    parts = str(raw).split(STATE_SEPARATOR, 2)
    signature = parts[0]
    scan_id = (parts[1] or None) if len(parts) > 1 else None

    try:
        missing_scans = int(parts[2]) if len(parts) > 2 else 0
    except ValueError:
        missing_scans = 0

    return signature, scan_id, missing_scans


def encode_file_state(signature, scan_id, missing_scans=0):
    return STATE_SEPARATOR.join((signature, scan_id or "", str(missing_scans)))


def changed(path, signature, scan_id, full_sweep=True):
    key = SIGNATURE_PREFIX + path
    old_signature, last_full_sweep, missing_sweeps = parse_file_state(r.get(key))
    if full_sweep:
        last_full_sweep = scan_id
        missing_sweeps = 0
    r.set(key, encode_file_state(signature, last_full_sweep, missing_sweeps))
    return old_signature != signature


def mark_seen(path, scan_id):
    key = SIGNATURE_PREFIX + path
    signature, _, _ = parse_file_state(r.get(key))
    if signature is not None:
        r.set(key, encode_file_state(signature, scan_id))


def reconcile_missing(scan_id, session_id=None, root_scope=None, threshold=None):
    checked = 0
    deleted = 0
    threshold = MISSING_SCAN_THRESHOLD if threshold is None else max(1, threshold)
    pattern = SIGNATURE_PREFIX + "*"
    if root_scope:
        pattern = SIGNATURE_PREFIX + root_scope.rstrip("/") + "/" + "*"

    for key in r.scan_iter(match=pattern, count=1000):
        raw = r.get(key)
        signature, last_seen_scan, missing_scans = parse_file_state(raw)

        if signature is None or last_seen_scan == scan_id:
            continue

        checked += 1
        missing_scans += 1

        if missing_scans < threshold:
            r.set(key, encode_file_state(signature, last_seen_scan, missing_scans))
            continue

        path = key[len(SIGNATURE_PREFIX):]
        r.xadd(STREAM_KEY, {
            "event": "DELETE",
            "path": path,
            "source": "polling_scanner",
            "ts": utc_now(),
            "scan_session_id": str(session_id or ""),
        })
        r.delete(key)
        deleted += 1

    return checked, deleted


def raise_walk_error(error):
    raise error


def select_interval_root(roots):
    if not roots:
        return None
    try:
        index = int(r.get(INTERVAL_ROOT_INDEX_KEY) or 0)
    except (TypeError, ValueError):
        index = 0
    root = roots[index % len(roots)]
    r.set(INTERVAL_ROOT_INDEX_KEY, str((index + 1) % len(roots)))
    return root


def select_dirty_root(roots):
    allowed = set(roots)
    dirty = r.hgetall(DIRTY_ROOTS_KEY)
    candidates = [
        (marked_at, root)
        for root, marked_at in dirty.items()
        if root in allowed
    ]
    if not candidates:
        return None, None
    marked_at, root = min(candidates)
    return root, marked_at


def clear_dirty_root(root, expected_marker):
    script = """
    if redis.call('HGET', KEYS[1], ARGV[1]) == ARGV[2] then
        return redis.call('HDEL', KEYS[1], ARGV[1])
    end
    return 0
    """
    return bool(r.eval(script, 1, DIRTY_ROOTS_KEY, root, expected_marker))


def _scan_roots(
    roots,
    scan_id,
    session_id,
    full_sweep,
    scan_type=None,
    reconcile_scope=None,
    missing_threshold=None,
):
    scan_type = scan_type or ("full" if full_sweep else "interval")
    logger.info("Starting %s scan roots=%s", scan_type, ", ".join(roots))

    discovered = 0
    enqueued = 0

    for root_base in roots:
        root_started = time.time()
        root_discovered = 0
        root_enqueued = 0
        heartbeat("scanning")
        refresh_lock()

        for root, dirs, files in os.walk(root_base, onerror=raise_walk_error):
            dirs[:] = [
                d for d in dirs
                if d not in IGNORE_NAMES
                and not d.startswith(IGNORE_PREFIXES)
                and not should_skip_path(os.path.join(root, d))
            ]

            for filename in files:
                path = os.path.join(root, filename)

                if should_skip_path(path):
                    continue

                try:
                    st = os.stat(path)
                except FileNotFoundError:
                    continue
                except PermissionError:
                    if full_sweep:
                        mark_seen(path, scan_id)
                    logger.warning("Permission denied: %s", path)
                    continue
                except Exception as e:
                    if full_sweep:
                        mark_seen(path, scan_id)
                    logger.warning("stat failed: %s err=%s", path, e)
                    continue

                discovered += 1
                root_discovered += 1
                if root_discovered % 1000 == 0:
                    heartbeat("scanning")
                    refresh_lock()
                sig = file_signature(path, st)

                if not changed(path, sig, scan_id, full_sweep=full_sweep):
                    continue

                r.xadd(STREAM_KEY, {
                    "event": "UPSERT",
                    "path": path,
                    "source": "polling_scanner",
                    "mtime": str(int(st.st_mtime)),
                    "size": str(st.st_size),
                    "inode": str(st.st_ino),
                    "ts": utc_now(),
                    "scan_session_id": str(session_id or ""),
                })
                enqueued += 1
                root_enqueued += 1

        logger.info(
            "Root done: type=%s root=%s discovered=%s enqueued=%s elapsed=%.1fs",
            scan_type,
            root_base,
            root_discovered,
            root_enqueued,
            time.time() - root_started,
        )

    if full_sweep:
        missing, deleted = reconcile_missing(
            scan_id,
            session_id=session_id,
            root_scope=reconcile_scope,
            threshold=missing_threshold,
        )
    else:
        missing, deleted = 0, 0

    if session_id:
        session_call("SELECT increment_files_discovered(%s, %s)", (session_id, discovered))
        session_call("SELECT increment_jobs_enqueued(%s, %s)", (session_id, enqueued + deleted))
        session_call("SELECT finish_scan_session(%s)", (session_id,))

    finished_at = utc_now()
    r.set(LAST_SCAN_KEY, finished_at, ex=HEARTBEAT_TTL * 4)
    if scan_type == "full":
        r.set(LAST_FULL_SCAN_KEY, finished_at)
    else:
        r.set(LAST_INTERVAL_SCAN_KEY, finished_at)
        r.set(LAST_INTERVAL_ROOT_KEY, roots[0] if roots else "")
    return discovered, enqueued, missing, deleted


def run_scan(
    scan_type,
    roots,
    *,
    full_sweep=None,
    reconcile_scope=None,
    missing_threshold=None,
):
    scan_id = uuid.uuid4().hex
    session_id = session_call("SELECT create_scan_session(%s)", (scan_type,), fetch=True)
    if full_sweep is None:
        full_sweep = scan_type == "full"
    try:
        return _scan_roots(
            roots,
            scan_id,
            session_id,
            full_sweep=full_sweep,
            scan_type=scan_type,
            reconcile_scope=reconcile_scope,
            missing_threshold=missing_threshold,
        )
    except Exception:
        if session_id:
            session_call(
                "UPDATE scan_sessions SET status = 'failed', finished_at = NOW() WHERE id = %s",
                (session_id,),
            )
        raise


def scan_once():
    """Run a complete reconciliation sweep (backward-compatible entry point)."""
    roots = discover_roots()
    if not roots:
        raise RuntimeError("Full scan aborted: no scan roots discovered")
    return run_scan("full", roots)


def scan_interval_once():
    roots = discover_roots()
    dirty_root, dirty_marker = select_dirty_root(roots)
    root = dirty_root or select_interval_root(roots)
    if dirty_root:
        result = run_scan(
            "interval",
            [dirty_root],
            full_sweep=True,
            reconcile_scope=dirty_root,
            missing_threshold=1,
        )
    else:
        result = run_scan("interval", [root] if root else [])
    if dirty_root:
        if clear_dirty_root(dirty_root, dirty_marker):
            logger.info("Dirty root reconciled: %s", dirty_root)
        else:
            logger.info("Dirty root changed during reconciliation; keeping marker: %s", dirty_root)
    return result


def consume_full_scan_request():
    requested_at = r.get(FULL_SCAN_REQUEST_KEY)
    if not requested_at:
        return False
    r.delete(FULL_SCAN_REQUEST_KEY)
    logger.info("Manual full scan requested at %s", requested_at)
    return True


def wait_for_next_scan(seconds):
    """Wait interruptibly so a manual full request is picked up promptly."""
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if r.get(FULL_SCAN_REQUEST_KEY):
            return
        heartbeat("idle")
        refresh_lock()
        time.sleep(min(1.0, max(0.0, deadline - time.monotonic())))


def main():
    if not acquire_lock():
        return

    heartbeat("started")
    logger.info(
        "Starting polling scanner on %s interval=%ss full_interval=%ss",
        SCAN_ROOT,
        SCAN_INTERVAL,
        FULL_SCAN_INTERVAL,
    )
    next_full_at = 0.0

    try:
        while True:
            refresh_lock()
            heartbeat("running")

            started = time.time()
            try:
                full_sweep = consume_full_scan_request() or time.monotonic() >= next_full_at
                if full_sweep:
                    discovered, enqueued, missing, deleted = scan_once()
                    next_full_at = time.monotonic() + FULL_SCAN_INTERVAL
                    scan_type = "full"
                else:
                    discovered, enqueued, missing, deleted = scan_interval_once()
                    scan_type = "interval"
                elapsed = time.time() - started
                heartbeat("idle")
                logger.info(
                    "Scan done: type=%s discovered=%s enqueued=%s missing=%s deleted=%s elapsed=%.1fs",
                    scan_type,
                    discovered,
                    enqueued,
                    missing,
                    deleted,
                    elapsed,
                )
            except Exception as e:
                heartbeat("error")
                logger.exception("Scan loop failed: %s", e)

            wait_for_next_scan(SCAN_INTERVAL)

    finally:
        heartbeat("stopped")
        release_lock()


if __name__ == "__main__":
    main()
```


---

# Metadata Worker

Bronbestand: `metadata_worker.py`

- Regels: `595`
- Functies: `23`
- Classes: `0`
- Imports: `12`

## Imports

- `datetime.datetime`
- `datetime.timezone`
- `json`
- `logging`
- `magic`
- `os`
- `psycopg2`
- `psycopg2.extras`
- `pyvips`
- `redis`
- `socket`
- `xxhash`

## Constanten

- `CONSUMER_NAME` op regel `34`
- `DLQ_STREAM` op regel `24`
- `FORCE_FULL` op regel `35`
- `GROUP_NAME` op regel `23`
- `HEARTBEAT_KEY` op regel `29`
- `HEARTBEAT_STATUS_KEY` op regel `30`
- `HEARTBEAT_TTL` op regel `32`
- `LAST_EVENT_KEY` op regel `31`
- `LOCK_KEY` op regel `26`
- `LOCK_TTL` op regel `27`
- `REALTIME_STREAM_KEY` op regel `22`
- `REDIS_HOST` op regel `18`
- `REDIS_PORT` op regel `19`
- `STREAM_KEY` op regel `21`

## Redis keys / streams

- `metadata_worker:heartbeat`
- `metadata_worker:heartbeat:status`
- `metadata_worker:lock`
- `scan_stream`
- `scan_stream_dlq`

## Functies

### `utc_now()`

- Regel: `49`
- Docstring: _niet aanwezig_

### `heartbeat(status)`

- Regel: `53`
- Docstring: _niet aanwezig_

### `get_db()`

- Regel: `61`
- Docstring: _niet aanwezig_

### `acquire_lock()`

- Regel: `76`
- Docstring: _niet aanwezig_

### `refresh_lock()`

- Regel: `95`
- Docstring: _niet aanwezig_

### `release_lock()`

- Regel: `103`
- Docstring: _niet aanwezig_

### `ensure_group(stream_key)`

- Regel: `111`
- Docstring: _niet aanwezig_

### `read_next_batch()`

- Regel: `120`
- Docstring: _niet aanwezig_

### `upsert_folder(cur, path)`

- Regel: `138`
- Docstring: _niet aanwezig_

### `hash_first_1024(path)`

- Regel: `162`
- Docstring: _niet aanwezig_

### `get_mime(path)`

- Regel: `170`
- Docstring: _niet aanwezig_

### `get_image_dims(path, mime)`

- Regel: `178`
- Docstring: _niet aanwezig_

### `path_is_missing(path)`

- Regel: `190`
- Docstring: _niet aanwezig_

### `get_file_by_path(cur, path)`

- Regel: `200`
- Docstring: _niet aanwezig_

### `classify_path_mutation(existing_file)`

- Regel: `208`
- Docstring: _niet aanwezig_

### `classify_rename_mutation(old_path, new_path)`

- Regel: `216`
- Docstring: _niet aanwezig_

### `identity_confidence(candidate, filesystem_device, inode, size_bytes, modified_at_fs, content_hash)`

- Regel: `222`
- Docstring: _niet aanwezig_

### `insert_file_event(cur)`

- Regel: `244`
- Docstring: _niet aanwezig_

### `evaluate_identity_match(cur, path, filesystem_device, inode, size_bytes, modified_at_fs, content_hash)`

- Regel: `262`
- Docstring: _niet aanwezig_

### `find_rename_candidate(cur, path, inode, size_bytes, modified_at_fs, content_hash, filesystem_device)`

- Regel: `316`
- Docstring: _niet aanwezig_

### `process_event(cur, data)`

- Regel: `324`
- Docstring: _niet aanwezig_

### `mark_session_job_processed(cur, data)`

- Regel: `527`
- Docstring: _niet aanwezig_

### `main()`

- Regel: `538`
- Docstring: _niet aanwezig_

## SQL statements

### Statement regel `143`

```sql
SELECT id FROM folders WHERE path = %s
```

### Statement regel `151`

```sql
INSERT INTO folders (path, parent_id)
        VALUES (%s, %s)
        ON CONFLICT (path) DO UPDATE SET
            path = EXCLUDED.path
        RETURNING id
```

### Statement regel `202`

```sql
SELECT id, path, deleted_at FROM files WHERE path = %s
```

### Statement regel `249`

```sql
INSERT INTO file_events (
            file_id, candidate_file_id, event_type, old_path, new_path,
            confidence_score, confidence_level, decision, signals, reason,
            scan_session_id, source
        ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb,%s,%s,%s)
```

### Statement regel `263`

```sql
SELECT id, path, filesystem_device, inode, size_bytes, modified_at_fs, hash_content
        FROM files
        WHERE filesystem_device = %s
          AND inode = %s
          AND path <> %s
          AND deleted_at IS NULL
        ORDER BY id
```

### Statement regel `512`

```sql
INSERT INTO metadata (
            file_id, width, height, duration, missing
        )
        VALUES (%s,%s,%s,NULL,false)
        ON CONFLICT (file_id) DO UPDATE SET
            width     = EXCLUDED.width,
            height    = EXCLUDED.height,
            missing   = false
```

### Statement regel `334`

```sql
UPDATE files SET
                deleted_at = NOW(),
                updated_at = NOW(),
                last_mutation_type = 'DELETED'
            WHERE path = %s
            RETURNING id
```

### Statement regel `353`

```sql
UPDATE files SET
                deleted_at = NOW(),
                updated_at = NOW(),
                last_mutation_type = 'DELETED'
            WHERE path = %s
            RETURNING id
```

### Statement regel `418`

```sql
UPDATE files SET
                folder_id          = %s,
                filename           = %s,
                extension          = %s,
                size_bytes         = %s,
                modified_at_fs     = %s,
                filesystem_device  = %s,
                inode              = %s,
                path               = %s,
                source             = %s,
                hash_path          = %s,
                hash_content       = %s,
                mime_type
```

### Statement regel `446`

```sql
INSERT INTO files (
                folder_id, filename, extension, size_bytes,
                modified_at_fs, filesystem_device, inode,
                path, source, hash_path, hash_content,
                mime_type, deleted_at,
                last_mutation_type
            )
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,NULL,%s)
            ON CONFLICT (path) DO UPDATE SET
                folder_id          = EXCLUDED.folder_id,
                filename           = EXCLUDED.filena
```

### Statement regel `508`

```sql
DELETE FROM metadata WHERE file_id = %s
```

### Statement regel `531`

```sql
SELECT increment_jobs_processed(%s)
```

### Statement regel `535`

```sql
Scan session update failed: %s
```

## Broncode

```python
#!/usr/bin/env python3
import os
import json
import socket
import logging
from datetime import datetime, timezone

import redis
import psycopg2
import psycopg2.extras
import magic
import pyvips
import xxhash

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("metadata-worker")

REDIS_HOST = os.getenv("REDIS_HOST", "redis")
REDIS_PORT = int(os.getenv("REDIS_PORT", "6379"))

STREAM_KEY = "scan_stream"
REALTIME_STREAM_KEY = os.getenv("REALTIME_STREAM_KEY", "scan_stream_realtime")
GROUP_NAME = "metadata_group"
DLQ_STREAM = "scan_stream_dlq"

LOCK_KEY = "metadata_worker:lock"
LOCK_TTL = 90

HEARTBEAT_KEY = "metadata_worker:heartbeat"
HEARTBEAT_STATUS_KEY = "metadata_worker:heartbeat:status"
LAST_EVENT_KEY = "metadata_worker:last_event"
HEARTBEAT_TTL = 120

CONSUMER_NAME = socket.gethostname()
FORCE_FULL = os.getenv("FORCE_FULL_METADATA", "false").lower() == "true"

r = redis.Redis(
    host=REDIS_HOST,
    port=REDIS_PORT,
    decode_responses=True,
    socket_timeout=30,
    socket_connect_timeout=10,
    retry_on_timeout=True,
)

_db_conn = None


def utc_now():
    return datetime.now(timezone.utc).isoformat()


def heartbeat(status="running"):
    try:
        r.set(HEARTBEAT_KEY, utc_now(), ex=HEARTBEAT_TTL)
        r.set(HEARTBEAT_STATUS_KEY, status, ex=HEARTBEAT_TTL)
    except Exception as e:
        logger.warning("Heartbeat failed: %s", e)


def get_db():
    global _db_conn
    if _db_conn is None or _db_conn.closed:
        _db_conn = psycopg2.connect(
            host=os.getenv("DB_HOST"),
            port=int(os.getenv("DB_PORT")),
            user=os.getenv("DB_USER"),
            password=os.getenv("DB_PASS"),
            dbname=os.getenv("DB_NAME"),
        )
        _db_conn.autocommit = False
        logger.info("Database connected")
    return _db_conn


def acquire_lock():
    owner = r.get(LOCK_KEY)
    if owner and owner != CONSUMER_NAME:
        owner_hb = r.get(HEARTBEAT_KEY)
        if owner_hb:
            logger.warning("Metadata worker already running: owner=%s heartbeat=%s", owner, owner_hb)
            return False
        logger.warning("Stale metadata worker lock found: owner=%s, taking over", owner)
        r.delete(LOCK_KEY)

    ok = r.set(LOCK_KEY, CONSUMER_NAME, nx=True, ex=LOCK_TTL)
    if not ok:
        logger.warning("Metadata worker lock busy: %s", r.get(LOCK_KEY))
        return False

    logger.info("Metadata worker lock acquired by %s", CONSUMER_NAME)
    return True


def refresh_lock():
    try:
        if r.get(LOCK_KEY) == CONSUMER_NAME:
            r.expire(LOCK_KEY, LOCK_TTL)
    except Exception as e:
        logger.warning("Lock refresh failed: %s", e)


def release_lock():
    try:
        if r.get(LOCK_KEY) == CONSUMER_NAME:
            r.delete(LOCK_KEY)
    except Exception:
        pass


def ensure_group(stream_key=STREAM_KEY):
    try:
        r.xgroup_create(stream_key, GROUP_NAME, id="0", mkstream=True)
        logger.info("Redis consumer group created")
    except redis.exceptions.ResponseError as e:
        if "BUSYGROUP" not in str(e):
            raise


def read_next_batch():
    realtime = r.xreadgroup(
        GROUP_NAME,
        CONSUMER_NAME,
        streams={REALTIME_STREAM_KEY: ">"},
        count=50,
    )
    if realtime:
        return realtime
    return r.xreadgroup(
        GROUP_NAME,
        CONSUMER_NAME,
        streams={STREAM_KEY: ">"},
        count=10,
        block=1000,
    )


def upsert_folder(cur, path):
    path = os.path.normpath(path)
    if not path or path == "/":
        return None

    cur.execute("SELECT id FROM folders WHERE path = %s", (path,))
    row = cur.fetchone()
    if row:
        return row["id"]

    parent = os.path.dirname(path)
    parent_id = None if parent == path else upsert_folder(cur, parent)

    cur.execute("""
        INSERT INTO folders (path, parent_id)
        VALUES (%s, %s)
        ON CONFLICT (path) DO UPDATE SET
            path = EXCLUDED.path
        RETURNING id
    """, (path, parent_id))

    return cur.fetchone()["id"]


def hash_first_1024(path):
    try:
        with open(path, "rb") as f:
            return xxhash.xxh64(f.read(1024)).hexdigest()
    except Exception:
        return None


def get_mime(path):
    try:
        return magic.from_file(path, mime=True)
    except Exception as e:
        logger.warning("MIME failed: %s err=%s", path, e)
        return None


def get_image_dims(path, mime):
    if not mime or not mime.startswith("image/"):
        return None, None

    try:
        img = pyvips.Image.new_from_file(path)
        return img.width, img.height
    except Exception as e:
        logger.warning("Image metadata failed: %s err=%s", path, e)
        return None, None


def path_is_missing(path):
    try:
        os.stat(path)
        return False
    except FileNotFoundError:
        return True
    except OSError:
        return False


def get_file_by_path(cur, path):
    cur.execute(
        "SELECT id, path, deleted_at FROM files WHERE path = %s",
        (path,),
    )
    return cur.fetchone()


def classify_path_mutation(existing_file):
    if not existing_file:
        return "CREATED"
    if existing_file["deleted_at"] is not None:
        return "RESTORED"
    return "MODIFIED"


def classify_rename_mutation(old_path, new_path):
    if os.path.dirname(old_path) == os.path.dirname(new_path):
        return "RENAMED"
    return "MOVED"


def identity_confidence(candidate, filesystem_device, inode, size_bytes, modified_at_fs, content_hash):
    signals = {
        "filesystem_device_match": candidate.get("filesystem_device") == filesystem_device,
        "inode_match": candidate.get("inode") == inode,
        "size_match": candidate.get("size_bytes") == size_bytes,
        "mtime_match": candidate.get("modified_at_fs") == modified_at_fs,
        "content_hash_match": bool(content_hash) and candidate.get("hash_content") == content_hash,
        "old_path_missing": path_is_missing(candidate["path"]),
    }
    weights = {
        "filesystem_device_match": 20,
        "inode_match": 20,
        "size_match": 10,
        "mtime_match": 10,
        "content_hash_match": 30,
        "old_path_missing": 10,
    }
    score = sum(weights[name] for name, matched in signals.items() if matched)
    level = "high" if score >= 90 else "medium" if score >= 65 else "low"
    return score, level, signals


def insert_file_event(cur, *, file_id, event_type, source, old_path=None,
                      new_path=None, candidate_file_id=None, score=None,
                      level=None, decision=None, signals=None, reason=None,
                      scan_session_id=None):
    scan_session_id = scan_session_id or None
    cur.execute("""
        INSERT INTO file_events (
            file_id, candidate_file_id, event_type, old_path, new_path,
            confidence_score, confidence_level, decision, signals, reason,
            scan_session_id, source
        ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb,%s,%s,%s)
    """, (
        file_id, candidate_file_id, event_type, old_path, new_path,
        score, level, decision, json.dumps(signals or {}), reason,
        scan_session_id, source,
    ))


def evaluate_identity_match(cur, path, filesystem_device, inode, size_bytes, modified_at_fs, content_hash):
    cur.execute("""
        SELECT id, path, filesystem_device, inode, size_bytes, modified_at_fs, hash_content
        FROM files
        WHERE filesystem_device = %s
          AND inode = %s
          AND path <> %s
          AND deleted_at IS NULL
        ORDER BY id
    """, (filesystem_device, inode, path))

    rows = cur.fetchall()
    existing_paths = [row for row in rows if not path_is_missing(row["path"])]
    missing_candidates = [row for row in rows if row not in existing_paths]

    if existing_paths:
        return {
            "candidate": existing_paths[0],
            "event_type": "HARDLINK_DETECTED",
            "level": "ambiguous",
            "score": None,
            "signals": {"candidate_count": len(rows), "old_path_missing": False},
            "decision": "created_separate",
            "reason": "same inode is still active at another path",
        }

    if len(missing_candidates) != 1:
        return {
            "candidate": missing_candidates[0] if missing_candidates else None,
            "event_type": "IDENTITY_AMBIGUOUS" if missing_candidates else None,
            "level": "ambiguous" if missing_candidates else None,
            "score": None,
            "signals": {"candidate_count": len(missing_candidates)},
            "decision": "created_separate",
            "reason": "multiple missing candidates" if missing_candidates else "no candidate",
        }

    candidate = missing_candidates[0]
    score, level, signals = identity_confidence(
        candidate, filesystem_device, inode, size_bytes, modified_at_fs, content_hash
    )
    signals["candidate_count"] = 1
    matched = level == "high"
    return {
        "candidate": candidate,
        "event_type": "IDENTITY_MATCHED" if matched else "IDENTITY_REJECTED",
        "level": level,
        "score": score,
        "signals": signals,
        "decision": "auto_linked" if matched else "created_separate",
        "reason": "unique high-confidence match" if matched else "confidence below automatic threshold",
    }


def find_rename_candidate(cur, path, inode, size_bytes, modified_at_fs,
                          content_hash=None, filesystem_device=None):
    result = evaluate_identity_match(
        cur, path, filesystem_device, inode, size_bytes, modified_at_fs, content_hash
    )
    return result["candidate"] if result["decision"] == "auto_linked" else None


def process_event(cur, data):
    event = str(data.get("event", "")).lower()
    path = data.get("path")

    if not path:
        raise ValueError("Empty path")

    path = os.path.normpath(str(path))

    if "delete" in event:
        cur.execute("""
            UPDATE files SET
                deleted_at = NOW(),
                updated_at = NOW(),
                last_mutation_type = 'DELETED'
            WHERE path = %s
            RETURNING id
        """, (path,))
        row = cur.fetchone()
        if row:
            insert_file_event(
                cur, file_id=row["id"], event_type="DELETED",
                source=data.get("source", "polling_scanner"),
                old_path=path, scan_session_id=data.get("scan_session_id"),
            )
        logger.info("Deleted: %s", path)
        return

    if not os.path.exists(path):
        cur.execute("""
            UPDATE files SET
                deleted_at = NOW(),
                updated_at = NOW(),
                last_mutation_type = 'DELETED'
            WHERE path = %s
            RETURNING id
        """, (path,))
        row = cur.fetchone()
        if row:
            insert_file_event(
                cur, file_id=row["id"], event_type="DELETED",
                source=data.get("source", "polling_scanner"),
                old_path=path, reason="path_missing",
                scan_session_id=data.get("scan_session_id"),
            )
        logger.warning("Missing file, marked deleted: %s", path)
        return

    folder_path = os.path.dirname(path)
    folder_id = upsert_folder(cur, folder_path)

    if not folder_id:
        raise RuntimeError(f"No folder_id for {folder_path}")

    filename = os.path.basename(path)
    extension = os.path.splitext(filename)[1].lstrip(".").lower() or None

    stat = os.stat(path)
    size_bytes = stat.st_size
    modified_at_fs = int(stat.st_mtime)
    inode = stat.st_ino
    filesystem_device = stat.st_dev

    hash_path = xxhash.xxh64(path).hexdigest()
    hash_content = hash_first_1024(path)
    mime = get_mime(path)

    values = (
        folder_id,
        filename,
        extension,
        size_bytes,
        modified_at_fs,
        filesystem_device,
        inode,
        path,
        data.get("source", "polling_scanner"),
        hash_path,
        hash_content,
        mime,
    )

    existing_file = get_file_by_path(cur, path)
    rename_candidate = None
    identity_match = None
    if not existing_file:
        identity_match = evaluate_identity_match(
            cur, path, filesystem_device, inode, size_bytes, modified_at_fs, hash_content
        )
        if identity_match["decision"] == "auto_linked":
            rename_candidate = identity_match["candidate"]

    if rename_candidate:
        mutation_type = classify_rename_mutation(rename_candidate["path"], path)
        cur.execute("""
            UPDATE files SET
                folder_id          = %s,
                filename           = %s,
                extension          = %s,
                size_bytes         = %s,
                modified_at_fs     = %s,
                filesystem_device  = %s,
                inode              = %s,
                path               = %s,
                source             = %s,
                hash_path          = %s,
                hash_content       = %s,
                mime_type          = %s,
                last_mutation_type = %s,
                updated_at         = NOW(),
                deleted_at         = NULL
            WHERE id = %s
            RETURNING id
        """, values + (mutation_type, rename_candidate["id"]))
        logger.info(
            "%s: %s -> %s",
            mutation_type.title(),
            rename_candidate["path"],
            path,
        )
    else:
        mutation_type = classify_path_mutation(existing_file)
        cur.execute("""
            INSERT INTO files (
                folder_id, filename, extension, size_bytes,
                modified_at_fs, filesystem_device, inode,
                path, source, hash_path, hash_content,
                mime_type, deleted_at,
                last_mutation_type
            )
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,NULL,%s)
            ON CONFLICT (path) DO UPDATE SET
                folder_id          = EXCLUDED.folder_id,
                filename           = EXCLUDED.filename,
                extension          = EXCLUDED.extension,
                size_bytes         = EXCLUDED.size_bytes,
                modified_at_fs     = EXCLUDED.modified_at_fs,
                filesystem_device  = EXCLUDED.filesystem_device,
                inode              = EXCLUDED.inode,
                source             = EXCLUDED.source,
                hash_path          = EXCLUDED.hash_path,
                hash_content       = EXCLUDED.hash_content,
                mime_type          = EXCLUDED.mime_type,
                last_mutation_type = EXCLUDED.last_mutation_type,
                updated_at         = NOW(),
                deleted_at         = NULL
            RETURNING id
        """, values + (mutation_type,))
    file_id = cur.fetchone()["id"]
    insert_file_event(
        cur,
        file_id=file_id,
        candidate_file_id=rename_candidate["id"] if rename_candidate else None,
        event_type=mutation_type,
        source=data.get("source", "polling_scanner"),
        old_path=rename_candidate["path"] if rename_candidate else None,
        new_path=path,
        decision="auto_linked" if rename_candidate else "state_updated",
        scan_session_id=data.get("scan_session_id"),
    )
    if identity_match and identity_match["event_type"]:
        insert_file_event(
            cur,
            file_id=file_id,
            candidate_file_id=(
                identity_match["candidate"]["id"]
                if identity_match["candidate"] else None
            ),
            event_type=identity_match["event_type"],
            source=data.get("source", "polling_scanner"),
            old_path=(
                identity_match["candidate"]["path"]
                if identity_match["candidate"] else None
            ),
            new_path=path,
            score=identity_match["score"],
            level=identity_match["level"],
            decision=identity_match["decision"],
            signals=identity_match["signals"],
            reason=identity_match["reason"],
            scan_session_id=data.get("scan_session_id"),
        )

    if FORCE_FULL:
        cur.execute("DELETE FROM metadata WHERE file_id = %s", (file_id,))

    width, height = get_image_dims(path, mime)

    cur.execute("""
        INSERT INTO metadata (
            file_id, width, height, duration, missing
        )
        VALUES (%s,%s,%s,NULL,false)
        ON CONFLICT (file_id) DO UPDATE SET
            width     = EXCLUDED.width,
            height    = EXCLUDED.height,
            missing   = false
    """, (file_id, width, height))

    r.set(LAST_EVENT_KEY, utc_now(), ex=HEARTBEAT_TTL * 4)
    logger.info("Processed: %s", path)


def mark_session_job_processed(cur, data):
    session_id = data.get("scan_session_id")
    if session_id:
        try:
            cur.execute("SELECT increment_jobs_processed(%s)", (session_id,))
        except Exception as exc:
            # Session accounting must never turn an otherwise valid legacy
            # metadata event into a DLQ entry.
            logger.warning("Scan session update failed: %s", exc)


def main():
    if not acquire_lock():
        return

    heartbeat("started")
    conn = get_db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    ensure_group(STREAM_KEY)
    ensure_group(REALTIME_STREAM_KEY)
    logger.info("Worker started")

    try:
        while True:
            refresh_lock()
            heartbeat("waiting")

            try:
                resp = read_next_batch()
            except redis.exceptions.ResponseError as e:
                if "NOGROUP" in str(e):
                    logger.warning("NOGROUP detected, recreating group")
                    ensure_group(STREAM_KEY)
                    ensure_group(REALTIME_STREAM_KEY)
                    continue
                raise

            if not resp:
                continue

            heartbeat("processing")

            for source_stream, msgs in resp:
                for msg_id, data in msgs:
                    try:
                        process_event(cur, data)
                        mark_session_job_processed(cur, data)
                        conn.commit()
                    except Exception as e:
                        conn.rollback()
                        logger.error("DLQ msg=%s: %s", msg_id, e, exc_info=True)
                        r.xadd(DLQ_STREAM, {
                            "original_id": msg_id,
                            "original_stream": source_stream,
                            "data": json.dumps(data),
                            "error": str(e),
                            "ts": utc_now(),
                        })
                    finally:
                        r.xack(source_stream, GROUP_NAME, msg_id)

    finally:
        heartbeat("stopped")
        release_lock()


if __name__ == "__main__":
    main()
```


---

# Docker

## Services

- `redis`
- `scanner`
- `watcher`
- `metadata_worker`
- `redis_data`

## Environment variables

- `DB_HOST`
- `DB_NAME`
- `DB_PASS`
- `DB_PORT`
- `DB_USER`
- `FORCE_FULL_METADATA`
- `FULL_SCAN_INTERVAL`
- `MISSING_SCAN_THRESHOLD`
- `REALTIME_STREAM_KEY`
- `REDIS_HOST`
- `SCAN_INTERVAL`
- `SCAN_ROOT`
- `STREAM_KEY`
- `WATCHER_DEBOUNCE_SECONDS`
- `WATCH_ROOTS`

## docker-compose.yml

```yaml
name: nas
services:
  redis:
    image: redis:7-alpine
    restart: unless-stopped
    command: ["redis-server", "--appendonly", "yes", "--maxmemory-policy", "noeviction"]
    volumes: [redis_data:/data]
    healthcheck: { test: ["CMD", "redis-cli", "ping"], interval: 10s, timeout: 5s, retries: 3 }

  scanner:
    build: { context: ., dockerfile: Dockerfile.scanner }
    restart: unless-stopped
    depends_on: { redis: { condition: service_healthy } }
    volumes: ["/volume1:/volume1:ro"]
    environment:
      - DB_HOST=${DB_HOST}
      - DB_PORT=${DB_PORT}
      - DB_USER=${DB_USER}
      - DB_PASS=${DB_PASS}
      - DB_NAME=${DB_NAME}
      - REDIS_HOST=redis
      - SCAN_ROOT=${SCAN_ROOT:-/volume1}
      - SCAN_INTERVAL=${SCAN_INTERVAL:-600}
      - FULL_SCAN_INTERVAL=${FULL_SCAN_INTERVAL:-3600}
      - MISSING_SCAN_THRESHOLD=${MISSING_SCAN_THRESHOLD:-2}

  watcher:
    build: { context: ., dockerfile: Dockerfile.watcher }
    restart: unless-stopped
    depends_on: { redis: { condition: service_healthy } }
    volumes: ["/volume1:/volume1:ro"]
    environment:
      - REDIS_HOST=redis
      - SCAN_ROOT=${SCAN_ROOT:-/volume1}
      - WATCH_ROOTS=${WATCH_ROOTS:-/volume1/data}
      - STREAM_KEY=${REALTIME_STREAM_KEY:-scan_stream_realtime}
      - WATCHER_DEBOUNCE_SECONDS=${WATCHER_DEBOUNCE_SECONDS:-2}
    healthcheck:
      test: ["CMD", "python3", "-c", "import redis; r=redis.Redis(host='redis', decode_responses=True); assert r.get('watcher:heartbeat')"]
      interval: 30s
      timeout: 5s
      retries: 3

  metadata_worker:
    build: { context: ., dockerfile: Dockerfile.metadata }
    restart: unless-stopped
    depends_on: { redis: { condition: service_healthy } }
    volumes: ["/volume1:/volume1:ro"]
    environment:
      - DB_HOST=${DB_HOST}
      - DB_PORT=${DB_PORT}
      - DB_USER=${DB_USER}
      - DB_PASS=${DB_PASS}
      - DB_NAME=${DB_NAME}
      - REDIS_HOST=redis
      - REALTIME_STREAM_KEY=${REALTIME_STREAM_KEY:-scan_stream_realtime}
      - FORCE_FULL_METADATA=${FORCE_FULL_METADATA:-false}

    healthcheck:
      test: ["CMD", "python3", "-c", "import redis; r=redis.Redis(host='redis', decode_responses=True); r.ping()"]
      interval: 30s
      timeout: 5s
      retries: 3

volumes:
  redis_data:
```

## Dockerfile.base

```dockerfile
FROM debian:bookworm-slim

ENV TZ=Europe/Amsterdam
ENV DEBIAN_FRONTEND=noninteractive

# OS dependencies (inotify + ffprobe zijn hier al inbegrepen)
RUN apt-get update && apt-get install -y \
    curl wget ca-certificates bash tzdata \
    python3 python3-pip \
    libmagic1 libvips42 ffmpeg inotify-tools \
    && rm -rf /var/lib/apt/lists/*

# Python dependencies
RUN pip3 install --break-system-packages redis psycopg2-binary xxhash python-magic pyvips

WORKDIR /app
```

## Dockerfile.scanner

```dockerfile
FROM nas-base:v1
WORKDIR /app
COPY scanner.py .
CMD ["python3", "scanner.py"]
```

## Dockerfile.metadata

```dockerfile
FROM nas-base:v1
WORKDIR /app
COPY metadata_worker.py .
CMD ["python3", "metadata_worker.py"]
```


---

# PostgreSQL

## Tabellen

- `ai_output`
- `embeddings`
- `files`
- `folders`
- `metadata`
- `scan_sessions`

## Unique constraints

- `file_id`
- `path`

## Foreign keys

- `file_id`
- `folder_id`
- `parent_id`

## schema.sql

```sql
--
-- PostgreSQL database dump
--

\restrict KM5I8YsUK7CLbO0daSZ9hUdbrsZeFBT9FWSYUKVNueqkKGoLNR6hGNMoNadS5g0

-- Dumped from database version 16.14 (Debian 16.14-1.pgdg12+1)
-- Dumped by pg_dump version 16.14 (Debian 16.14-1.pgdg12+1)

SET statement_timeout = 0;
SET lock_timeout = 0;
SET idle_in_transaction_session_timeout = 0;
SET client_encoding = 'UTF8';
SET standard_conforming_strings = on;
SELECT pg_catalog.set_config('search_path', '', false);
SET check_function_bodies = false;
SET xmloption = content;
SET client_min_messages = warning;
SET row_security = off;

--
-- Name: vector; Type: EXTENSION; Schema: -; Owner: -
--

CREATE EXTENSION IF NOT EXISTS vector WITH SCHEMA public;


--
-- Name: EXTENSION vector; Type: COMMENT; Schema: -; Owner: 
--

COMMENT ON EXTENSION vector IS 'vector data type and ivfflat and hnsw access methods';


--
-- Name: cleanup_all_execute(); Type: PROCEDURE; Schema: public; Owner: hugo
--

CREATE PROCEDURE public.cleanup_all_execute()
    LANGUAGE plpgsql
    AS $_$
DECLARE
    dir_folders INT := 0;
    dir_files INT := 0;
    dir_meta INT := 0;
    dir_emb INT := 0;
    dir_ai INT := 0;

    file_files INT := 0;
    file_meta INT := 0;
    file_emb INT := 0;
    file_ai INT := 0;

    orphan_metadata INT := 0;
    orphan_embeddings INT := 0;
    orphan_ai INT := 0;
    orphan_files INT := 0;
    orphan_folders INT := 0;
BEGIN
    RAISE NOTICE '=== CLEANUP START ===';

    --------------------------------------------------------------------
    -- 1. SYSTEM FOLDERS (@eaDir, @tmp, @appstore, @*)
    --------------------------------------------------------------------
    WITH excluded_folders AS (
        SELECT id FROM folders
        WHERE path LIKE '%/@eaDir%'
           OR path LIKE '%/@appstore%'
           OR path LIKE '%/@tmp%'
           OR path LIKE '%/@%'
    ),
    files_to_delete AS (
        SELECT id AS file_id FROM files
        WHERE folder_id IN (SELECT id FROM excluded_folders)
    )
    SELECT
        (SELECT COUNT(*) FROM excluded_folders),
        (SELECT COUNT(*) FROM files_to_delete),
        (SELECT COUNT(*) FROM metadata WHERE file_id IN (SELECT file_id FROM files_to_delete)),
        (SELECT COUNT(*) FROM embeddings WHERE file_id IN (SELECT file_id FROM files_to_delete)),
        (SELECT COUNT(*) FROM ai_output WHERE file_id IN (SELECT file_id FROM files_to_delete))
    INTO dir_folders, dir_files, dir_meta, dir_emb, dir_ai;

    RAISE NOTICE 'DIRS → removing % folders, % files, % metadata, % embeddings, % ai_output',
        dir_folders, dir_files, dir_meta, dir_emb, dir_ai;

    -- DELETE using fresh CTE
    WITH files_to_delete AS (
        SELECT id AS file_id FROM files
        WHERE folder_id IN (
            SELECT id FROM folders
            WHERE path LIKE '%/@eaDir%'
               OR path LIKE '%/@appstore%'
               OR path LIKE '%/@tmp%'
               OR path LIKE '%/@%'
        )
    )
    DELETE FROM metadata WHERE file_id IN (SELECT file_id FROM files_to_delete);

    WITH files_to_delete AS (
        SELECT id AS file_id FROM files
        WHERE folder_id IN (
            SELECT id FROM folders
            WHERE path LIKE '%/@eaDir%'
               OR path LIKE '%/@appstore%'
               OR path LIKE '%/@tmp%'
               OR path LIKE '%/@%'
        )
    )
    DELETE FROM embeddings WHERE file_id IN (SELECT file_id FROM files_to_delete);

    WITH files_to_delete AS (
        SELECT id AS file_id FROM files
        WHERE folder_id IN (
            SELECT id FROM folders
            WHERE path LIKE '%/@eaDir%'
               OR path LIKE '%/@appstore%'
               OR path LIKE '%/@tmp%'
               OR path LIKE '%/@%'
        )
    )
    DELETE FROM ai_output WHERE file_id IN (SELECT file_id FROM files_to_delete);

    WITH files_to_delete AS (
        SELECT id AS file_id FROM files
        WHERE folder_id IN (
            SELECT id FROM folders
            WHERE path LIKE '%/@eaDir%'
               OR path LIKE '%/@appstore%'
               OR path LIKE '%/@tmp%'
               OR path LIKE '%/@%'
        )
    )
    DELETE FROM files WHERE id IN (SELECT file_id FROM files_to_delete);

    DELETE FROM folders
    WHERE path LIKE '%/@eaDir%'
       OR path LIKE '%/@appstore%'
       OR path LIKE '%/@tmp%'
       OR path LIKE '%/@%';

    --------------------------------------------------------------------
    -- 2. SYSTEM FILES (~$, ._, .DS_Store, Thumbs.db, *.tmp, *.swp, *.bak)
    --------------------------------------------------------------------
    WITH excluded_files AS (
        SELECT id AS file_id FROM files
        WHERE filename LIKE '~$%'
           OR filename LIKE '._%'
           OR filename = '.DS_Store'
           OR filename = 'Thumbs.db'
           OR filename LIKE '%.tmp'
           OR filename LIKE '%.swp'
           OR filename LIKE '%.bak'
    )
    SELECT
        (SELECT COUNT(*) FROM excluded_files),
        (SELECT COUNT(*) FROM metadata WHERE file_id IN (SELECT file_id FROM excluded_files)),
        (SELECT COUNT(*) FROM embeddings WHERE file_id IN (SELECT file_id FROM excluded_files)),
        (SELECT COUNT(*) FROM ai_output WHERE file_id IN (SELECT file_id FROM excluded_files))
    INTO file_files, file_meta, file_emb, file_ai;

    RAISE NOTICE 'FILES → removing % files, % metadata, % embeddings, % ai_output',
        file_files, file_meta, file_emb, file_ai;

    -- DELETE using fresh CTE
    WITH excluded_files AS (
        SELECT id AS file_id FROM files
        WHERE filename LIKE '~$%'
           OR filename LIKE '._%'
           OR filename = '.DS_Store'
           OR filename = 'Thumbs.db'
           OR filename LIKE '%.tmp'
           OR filename LIKE '%.swp'
           OR filename LIKE '%.bak'
    )
    DELETE FROM metadata WHERE file_id IN (SELECT file_id FROM excluded_files);

    WITH excluded_files AS (
        SELECT id AS file_id FROM files
        WHERE filename LIKE '~$%'
           OR filename LIKE '._%'
           OR filename = '.DS_Store'
           OR filename = 'Thumbs.db'
           OR filename LIKE '%.tmp'
           OR filename LIKE '%.swp'
           OR filename LIKE '%.bak'
    )
    DELETE FROM embeddings WHERE file_id IN (SELECT file_id FROM excluded_files);

    WITH excluded_files AS (
        SELECT id AS file_id FROM files
        WHERE filename LIKE '~$%'
           OR filename LIKE '._%'
           OR filename = '.DS_Store'
           OR filename = 'Thumbs.db'
           OR filename LIKE '%.tmp'
           OR filename LIKE '%.swp'
           OR filename LIKE '%.bak'
    )
    DELETE FROM ai_output WHERE file_id IN (SELECT file_id FROM excluded_files);

    WITH excluded_files AS (
        SELECT id AS file_id FROM files
        WHERE filename LIKE '~$%'
           OR filename LIKE '._%'
           OR filename = '.DS_Store'
           OR filename = 'Thumbs.db'
           OR filename LIKE '%.tmp'
           OR filename LIKE '%.swp'
           OR filename LIKE '%.bak'
    )
    DELETE FROM files WHERE id IN (SELECT file_id FROM excluded_files);

    --------------------------------------------------------------------
    -- 3. ORPHANS (metadata, embeddings, ai_output, files, folders)
    --------------------------------------------------------------------
    SELECT COUNT(*) INTO orphan_metadata
    FROM metadata m LEFT JOIN files f ON f.id = m.file_id
    WHERE f.id IS NULL;

    RAISE NOTICE 'ORPHANS → removing % orphaned metadata', orphan_metadata;

    DELETE FROM metadata m
    WHERE NOT EXISTS (SELECT 1 FROM files f WHERE f.id = m.file_id);

    SELECT COUNT(*) INTO orphan_embeddings
    FROM embeddings e LEFT JOIN files f ON f.id = e.file_id
    WHERE f.id IS NULL;

    RAISE NOTICE 'ORPHANS → removing % orphaned embeddings', orphan_embeddings;

    DELETE FROM embeddings e
    WHERE NOT EXISTS (SELECT 1 FROM files f WHERE f.id = e.file_id);

    SELECT COUNT(*) INTO orphan_ai
    FROM ai_output a LEFT JOIN files f ON f.id = a.file_id
    WHERE f.id IS NULL;

    RAISE NOTICE 'ORPHANS → removing % orphaned ai_output', orphan_ai;

    DELETE FROM ai_output a
    WHERE NOT EXISTS (SELECT 1 FROM files f WHERE f.id = a.file_id);

    SELECT COUNT(*) INTO orphan_files
    FROM files fl LEFT JOIN folders fo ON fo.id = fl.folder_id
    WHERE fo.id IS NULL;

    RAISE NOTICE 'ORPHANS → removing % orphaned files', orphan_files;

    DELETE FROM files fl
    WHERE NOT EXISTS (SELECT 1 FROM folders fo WHERE fo.id = fl.folder_id);

    SELECT COUNT(*) INTO orphan_folders
    FROM folders f LEFT JOIN folders p ON p.id = f.parent_id
    WHERE f.parent_id IS NOT NULL AND p.id IS NULL;

    RAISE NOTICE 'ORPHANS → removing % orphaned folders', orphan_folders;

    DELETE FROM folders f
    WHERE f.parent_id IS NOT NULL
      AND NOT EXISTS (SELECT 1 FROM folders p WHERE p.id = f.parent_id);

    --------------------------------------------------------------------
    RAISE NOTICE '=== CLEANUP COMPLETE ===';
END;
$_$;


ALTER PROCEDURE public.cleanup_all_execute() OWNER TO hugo;

--
-- Name: create_scan_session(text); Type: FUNCTION; Schema: public; Owner: hugo
--

CREATE FUNCTION public.create_scan_session(scan_type text) RETURNS uuid
    LANGUAGE plpgsql
    AS $$
DECLARE
    sid UUID := gen_random_uuid();
BEGIN
    INSERT INTO scan_sessions(id, type)
    VALUES (sid, scan_type);
    RETURN sid;
END;
$$;


ALTER FUNCTION public.create_scan_session(scan_type text) OWNER TO hugo;

--
-- Name: finish_scan_session(uuid); Type: FUNCTION; Schema: public; Owner: hugo
--

CREATE FUNCTION public.finish_scan_session(sid uuid) RETURNS void
    LANGUAGE plpgsql
    AS $$
BEGIN
    UPDATE scan_sessions
    SET finished_at = NOW(),
        status = 'done'
    WHERE id = sid;
END;
$$;


ALTER FUNCTION public.finish_scan_session(sid uuid) OWNER TO hugo;

--
-- Name: increment_files_discovered(uuid, integer); Type: FUNCTION; Schema: public; Owner: hugo
--

CREATE FUNCTION public.increment_files_discovered(sid uuid, cnt integer) RETURNS void
    LANGUAGE plpgsql
    AS $$
BEGIN
    UPDATE scan_sessions
    SET files_discovered = files_discovered + cnt
    WHERE id = sid;
END;
$$;


ALTER FUNCTION public.increment_files_discovered(sid uuid, cnt integer) OWNER TO hugo;

--
-- Name: increment_jobs_enqueued(uuid, integer); Type: FUNCTION; Schema: public; Owner: hugo
--

CREATE FUNCTION public.increment_jobs_enqueued(sid uuid, cnt integer) RETURNS void
    LANGUAGE plpgsql
    AS $$
BEGIN
    UPDATE scan_sessions
    SET jobs_enqueued = jobs_enqueued + cnt
    WHERE id = sid;
END;
$$;


ALTER FUNCTION public.increment_jobs_enqueued(sid uuid, cnt integer) OWNER TO hugo;

--
-- Name: increment_jobs_processed(uuid); Type: FUNCTION; Schema: public; Owner: hugo
--

CREATE FUNCTION public.increment_jobs_processed(sid uuid) RETURNS void
    LANGUAGE plpgsql
    AS $$
BEGIN
    UPDATE scan_sessions
    SET jobs_processed = jobs_processed + 1
    WHERE id = sid;
END;
$$;


ALTER FUNCTION public.increment_jobs_processed(sid uuid) OWNER TO hugo;

--
-- Name: is_scan_complete(uuid); Type: FUNCTION; Schema: public; Owner: hugo
--

CREATE FUNCTION public.is_scan_complete(sid uuid) RETURNS boolean
    LANGUAGE plpgsql
    AS $$
DECLARE done BOOLEAN;
BEGIN
    SELECT (status='done' AND jobs_enqueued>0 AND jobs_processed>=jobs_enqueued)
    INTO done
    FROM scan_sessions WHERE id=sid;
    RETURN COALESCE(done, FALSE);
END;
$$;


ALTER FUNCTION public.is_scan_complete(sid uuid) OWNER TO hugo;

SET default_tablespace = '';

SET default_table_access_method = heap;

--
-- Name: ai_output; Type: TABLE; Schema: public; Owner: hugo
--

CREATE TABLE public.ai_output (
    id integer NOT NULL,
    file_id integer,
    summary text,
    tags text[],
    categories text[],
    embedding public.vector(1536),
    created_at timestamp without time zone DEFAULT now()
);


ALTER TABLE public.ai_output OWNER TO hugo;

--
-- Name: ai_output_id_seq; Type: SEQUENCE; Schema: public; Owner: hugo
--

CREATE SEQUENCE public.ai_output_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.ai_output_id_seq OWNER TO hugo;

--
-- Name: ai_output_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: hugo
--

ALTER SEQUENCE public.ai_output_id_seq OWNED BY public.ai_output.id;


--
-- Name: embeddings; Type: TABLE; Schema: public; Owner: hugo
--

CREATE TABLE public.embeddings (
    id integer NOT NULL,
    file_id integer NOT NULL,
    embedding public.vector(1536),
    created_at timestamp without time zone DEFAULT now()
);


ALTER TABLE public.embeddings OWNER TO hugo;

--
-- Name: embeddings_id_seq; Type: SEQUENCE; Schema: public; Owner: hugo
--

CREATE SEQUENCE public.embeddings_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.embeddings_id_seq OWNER TO hugo;

--
-- Name: embeddings_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: hugo
--

ALTER SEQUENCE public.embeddings_id_seq OWNED BY public.embeddings.id;


--
-- Name: files; Type: TABLE; Schema: public; Owner: hugo
--

CREATE TABLE public.files (
    id integer NOT NULL,
    folder_id integer NOT NULL,
    filename text NOT NULL,
    extension text,
    size_bytes bigint,
    created_at timestamp without time zone DEFAULT now(),
    updated_at timestamp without time zone DEFAULT now(),
    modified_at_fs bigint,
    inode bigint,
    path text,
    mime_type text,
    deleted_at timestamp without time zone,
    hash_content text,
    hash_path text,
    source text,
    last_mutation_type text DEFAULT 'UNKNOWN'::text NOT NULL,
    CONSTRAINT files_last_mutation_type_check CHECK ((last_mutation_type = ANY (ARRAY['UNKNOWN'::text, 'CREATED'::text, 'MODIFIED'::text, 'RENAMED'::text, 'MOVED'::text, 'RESTORED'::text, 'DELETED'::text])))
);


ALTER TABLE public.files OWNER TO hugo;

--
-- Name: files_id_seq; Type: SEQUENCE; Schema: public; Owner: hugo
--

CREATE SEQUENCE public.files_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.files_id_seq OWNER TO hugo;

--
-- Name: files_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: hugo
--

ALTER SEQUENCE public.files_id_seq OWNED BY public.files.id;


--
-- Name: folders; Type: TABLE; Schema: public; Owner: hugo
--

CREATE TABLE public.folders (
    id integer NOT NULL,
    path text NOT NULL,
    parent_id integer,
    created_at timestamp without time zone DEFAULT now()
);


ALTER TABLE public.folders OWNER TO hugo;

--
-- Name: folders_id_seq; Type: SEQUENCE; Schema: public; Owner: hugo
--

CREATE SEQUENCE public.folders_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.folders_id_seq OWNER TO hugo;

--
-- Name: folders_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: hugo
--

ALTER SEQUENCE public.folders_id_seq OWNED BY public.folders.id;


--
-- Name: metadata; Type: TABLE; Schema: public; Owner: hugo
--

CREATE TABLE public.metadata (
    id integer NOT NULL,
    file_id bigint NOT NULL,
    created_at timestamp without time zone DEFAULT now(),
    width integer,
    height integer,
    duration double precision,
    missing boolean DEFAULT false
);


ALTER TABLE public.metadata OWNER TO hugo;

--
-- Name: metadata_id_seq; Type: SEQUENCE; Schema: public; Owner: hugo
--

CREATE SEQUENCE public.metadata_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.metadata_id_seq OWNER TO hugo;

--
-- Name: metadata_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: hugo
--

ALTER SEQUENCE public.metadata_id_seq OWNED BY public.metadata.id;


--
-- Name: scan_sessions; Type: TABLE; Schema: public; Owner: hugo
--

CREATE TABLE public.scan_sessions (
    id uuid NOT NULL,
    type text NOT NULL,
    started_at timestamp without time zone DEFAULT now() NOT NULL,
    finished_at timestamp without time zone,
    status text DEFAULT 'running'::text NOT NULL,
    files_discovered integer DEFAULT 0 NOT NULL,
    jobs_enqueued integer DEFAULT 0 NOT NULL,
    jobs_processed integer DEFAULT 0 NOT NULL,
    CONSTRAINT scan_sessions_status_check CHECK ((status = ANY (ARRAY['running'::text, 'finished'::text, 'failed'::text, 'aborted'::text]))),
    CONSTRAINT scan_sessions_type_check CHECK ((type = ANY (ARRAY['full'::text, 'interval'::text, 'watcher'::text])))
);


ALTER TABLE public.scan_sessions OWNER TO hugo;

--
-- Name: v_files_last_hour; Type: VIEW; Schema: public; Owner: hugo
--

CREATE VIEW public.v_files_last_hour AS
 SELECT count(*) AS files_last_hour
   FROM public.files
  WHERE (updated_at >= ((now() AT TIME ZONE 'UTC'::text) - '01:00:00'::interval));


ALTER VIEW public.v_files_last_hour OWNER TO hugo;

--
-- Name: v_files_over_time_extended; Type: VIEW; Schema: public; Owner: hugo
--

CREATE VIEW public.v_files_over_time_extended AS
 WITH per_day AS (
         SELECT date(files.created_at) AS file_date,
            count(*) AS files_created,
            ((count(*))::numeric / 24.0) AS avg_files_per_hour_that_day
           FROM public.files
          GROUP BY (date(files.created_at))
          ORDER BY (date(files.created_at))
        ), global_stats AS (
         SELECT count(*) AS total_files,
            min(files.created_at) AS first_file,
            max(files.created_at) AS last_file,
            (EXTRACT(epoch FROM (max(files.created_at) - min(files.created_at))) / (3600)::numeric) AS hours_span
           FROM public.files
        )
 SELECT p.file_date,
    p.files_created,
    p.avg_files_per_hour_that_day,
    g.total_files,
    g.first_file,
    g.last_file,
    g.hours_span,
        CASE
            WHEN (g.hours_span < (1)::numeric) THEN NULL::numeric
            ELSE ((g.total_files)::numeric / g.hours_span)
        END AS avg_files_per_hour_global
   FROM (per_day p
     CROSS JOIN global_stats g)
  ORDER BY p.file_date;


ALTER VIEW public.v_files_over_time_extended OWNER TO hugo;

--
-- Name: v_scan_status; Type: VIEW; Schema: public; Owner: hugo
--

CREATE VIEW public.v_scan_status AS
 SELECT id,
    type,
    status,
    started_at,
    finished_at,
    files_discovered,
    jobs_enqueued,
    jobs_processed,
    round((((jobs_processed)::numeric / (NULLIF(jobs_enqueued, 0))::numeric) * (100)::numeric), 2) AS progress_percent
   FROM public.scan_sessions
  ORDER BY started_at DESC;


ALTER VIEW public.v_scan_status OWNER TO hugo;

--
-- Name: v_test_documents; Type: VIEW; Schema: public; Owner: hugo
--

CREATE VIEW public.v_test_documents AS
 SELECT f.id,
    f.folder_id,
    f.filename,
    f.extension,
    f.size_bytes,
    f.created_at,
    f.updated_at,
    f.modified_at_fs,
    f.inode,
    f.hash_path AS xxhash,
    fo.path
   FROM (public.files f
     JOIN public.folders fo ON ((fo.id = f.folder_id)))
  WHERE (fo.path ~~ '/volume1/backup/NITRO/D/data/hugo/Documents%'::text);


ALTER VIEW public.v_test_documents OWNER TO hugo;

--
-- Name: ai_output id; Type: DEFAULT; Schema: public; Owner: hugo
--

ALTER TABLE ONLY public.ai_output ALTER COLUMN id SET DEFAULT nextval('public.ai_output_id_seq'::regclass);


--
-- Name: embeddings id; Type: DEFAULT; Schema: public; Owner: hugo
--

ALTER TABLE ONLY public.embeddings ALTER COLUMN id SET DEFAULT nextval('public.embeddings_id_seq'::regclass);


--
-- Name: files id; Type: DEFAULT; Schema: public; Owner: hugo
--

ALTER TABLE ONLY public.files ALTER COLUMN id SET DEFAULT nextval('public.files_id_seq'::regclass);


--
-- Name: folders id; Type: DEFAULT; Schema: public; Owner: hugo
--

ALTER TABLE ONLY public.folders ALTER COLUMN id SET DEFAULT nextval('public.folders_id_seq'::regclass);


--
-- Name: metadata id; Type: DEFAULT; Schema: public; Owner: hugo
--

ALTER TABLE ONLY public.metadata ALTER COLUMN id SET DEFAULT nextval('public.metadata_id_seq'::regclass);


--
-- Name: ai_output ai_output_pkey; Type: CONSTRAINT; Schema: public; Owner: hugo
--

ALTER TABLE ONLY public.ai_output
    ADD CONSTRAINT ai_output_pkey PRIMARY KEY (id);


--
-- Name: embeddings embeddings_pkey; Type: CONSTRAINT; Schema: public; Owner: hugo
--

ALTER TABLE ONLY public.embeddings
    ADD CONSTRAINT embeddings_pkey PRIMARY KEY (id);


--
-- Name: files files_path_unique; Type: CONSTRAINT; Schema: public; Owner: hugo
--

ALTER TABLE ONLY public.files
    ADD CONSTRAINT files_path_unique UNIQUE (path);


--
-- Name: files files_pkey; Type: CONSTRAINT; Schema: public; Owner: hugo
--

ALTER TABLE ONLY public.files
    ADD CONSTRAINT files_pkey PRIMARY KEY (id);


--
-- Name: folders folders_path_key; Type: CONSTRAINT; Schema: public; Owner: hugo
--

ALTER TABLE ONLY public.folders
    ADD CONSTRAINT folders_path_key UNIQUE (path);


--
-- Name: folders folders_pkey; Type: CONSTRAINT; Schema: public; Owner: hugo
--

ALTER TABLE ONLY public.folders
    ADD CONSTRAINT folders_pkey PRIMARY KEY (id);


--
-- Name: metadata metadata_file_id_unique; Type: CONSTRAINT; Schema: public; Owner: hugo
--

ALTER TABLE ONLY public.metadata
    ADD CONSTRAINT metadata_file_id_unique UNIQUE (file_id);


--
-- Name: metadata metadata_pkey; Type: CONSTRAINT; Schema: public; Owner: hugo
--

ALTER TABLE ONLY public.metadata
    ADD CONSTRAINT metadata_pkey PRIMARY KEY (id);


--
-- Name: scan_sessions scan_sessions_pkey; Type: CONSTRAINT; Schema: public; Owner: hugo
--

ALTER TABLE ONLY public.scan_sessions
    ADD CONSTRAINT scan_sessions_pkey PRIMARY KEY (id);


--
-- Name: idx_files_folder_filename; Type: INDEX; Schema: public; Owner: hugo
--

CREATE INDEX idx_files_folder_filename ON public.files USING btree (folder_id, filename);


--
-- Name: idx_files_inode_mtime; Type: INDEX; Schema: public; Owner: hugo
--

CREATE INDEX idx_files_inode_mtime ON public.files USING btree (inode, modified_at_fs);


--
-- Name: idx_folders_parent_id; Type: INDEX; Schema: public; Owner: hugo
--

CREATE INDEX idx_folders_parent_id ON public.folders USING btree (parent_id);


--
-- Name: idx_metadata_file_id; Type: INDEX; Schema: public; Owner: hugo
--

CREATE INDEX idx_metadata_file_id ON public.metadata USING btree (file_id);


--
-- Name: idx_metadata_width_height; Type: INDEX; Schema: public; Owner: hugo
--

CREATE INDEX idx_metadata_width_height ON public.metadata USING btree (width, height);


--
-- Name: idx_scan_sessions_started_at; Type: INDEX; Schema: public; Owner: hugo
--

CREATE INDEX idx_scan_sessions_started_at ON public.scan_sessions USING btree (started_at DESC);


--
-- Name: ai_output ai_output_file_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: hugo
--

ALTER TABLE ONLY public.ai_output
    ADD CONSTRAINT ai_output_file_id_fkey FOREIGN KEY (file_id) REFERENCES public.files(id) ON DELETE CASCADE;


--
-- Name: embeddings embeddings_file_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: hugo
--

ALTER TABLE ONLY public.embeddings
    ADD CONSTRAINT embeddings_file_id_fkey FOREIGN KEY (file_id) REFERENCES public.files(id) ON DELETE CASCADE;


--
-- Name: files files_folder_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: hugo
--

ALTER TABLE ONLY public.files
    ADD CONSTRAINT files_folder_id_fkey FOREIGN KEY (folder_id) REFERENCES public.folders(id) ON DELETE CASCADE;


--
-- Name: folders folders_parent_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: hugo
--

ALTER TABLE ONLY public.folders
    ADD CONSTRAINT folders_parent_id_fkey FOREIGN KEY (parent_id) REFERENCES public.folders(id) ON DELETE CASCADE;


--
-- Name: metadata metadata_file_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: hugo
--

ALTER TABLE ONLY public.metadata
    ADD CONSTRAINT metadata_file_id_fkey FOREIGN KEY (file_id) REFERENCES public.files(id) ON DELETE CASCADE;


--
-- PostgreSQL database dump complete
--

\unrestrict KM5I8YsUK7CLbO0daSZ9hUdbrsZeFBT9FWSYUKVNueqkKGoLNR6hGNMoNadS5g0
```


---

# Redis

Redis is de event- en statuslaag.

## Belangrijke keys

- `scan_stream`
- `scan_stream_dlq`
- `metadata_group`
- `scanner:lock:event`
- `metadata_worker:lock`
- heartbeat keys

## Checks

```bash
docker exec -it nas-redis-1 redis-cli XLEN scan_stream
docker exec -it nas-redis-1 redis-cli XINFO GROUPS scan_stream
docker exec -it nas-redis-1 redis-cli XINFO CONSUMERS scan_stream metadata_group
docker exec -it nas-redis-1 redis-cli XLEN scan_stream_dlq
```


---

# Scripts

## `tools/runtime/rebuild`

Bouwt scanner en metadata_worker opnieuw.

- Bestaat: `True`
- Regels: `13`
- Gebruikt docker compose: `True`
- Gebruikt Redis: `False`

```bash
#!/bin/bash
set -e
cd /volume1/docker/nas-stack
echo "========== DOCS =========="
./gendocs || echo "Documentation generation failed, continuing build..."
echo "========== BUILD scanner + metadata_worker =========="
docker compose build --no-cache scanner metadata_worker
echo "========== RESTART scanner + metadata_worker =========="
docker compose up -d --force-recreate scanner metadata_worker
echo "========== HEALTH =========="
./health || true
echo "========== LOGS =========="
docker compose logs -f --tail=50 scanner metadata_worker
```

## `tools/runtime/rebuildall`

Bouwt de volledige stack opnieuw.

- Bestaat: `True`
- Regels: `13`
- Gebruikt docker compose: `True`
- Gebruikt Redis: `False`

```bash
#!/bin/bash
set -e
cd /volume1/docker/nas-stack
echo "========== DOCS =========="
./gendocs || echo "Documentation generation failed, continuing build..."
echo "========== BUILD ALL =========="
docker compose build --no-cache
echo "========== RESTART ALL =========="
docker compose up -d --force-recreate --remove-orphans
echo "========== HEALTH =========="
./health || true
echo "========== LOGS =========="
docker compose logs -f --tail=50
```

## `tools/runtime/logs`

Toont live logs.

- CORE command: `core runtime logs`
- Bestaat: `True`
- Regels: `3`
- Gebruikt docker compose: `True`
- Gebruikt Redis: `False`

```bash
#!/bin/bash
cd /volume1/docker/nas-stack
docker compose logs -f --tail=50 scanner metadata_worker
```

## `tools/runtime/status`

Toont status, locks, heartbeats en streaminfo.

- CORE command: `core runtime status`
- Bestaat: `True`
- Regels: `78`
- Gebruikt docker compose: `True`
- Gebruikt Redis: `True`

```bash
#!/bin/bash
cd /volume1/docker/nas-stack

echo "========== CONTAINERS =========="
docker compose ps

echo
echo "========== HEALTH =========="
docker inspect nas-scanner-1 --format 'scanner: {{if .State.Health}}{{.State.Health.Status}}{{else}}no healthcheck{{end}}' 2>/dev/null || true
docker inspect nas-watcher-1 --format 'watcher: {{if .State.Health}}{{.State.Health.Status}}{{else}}no healthcheck{{end}}' 2>/dev/null || true
docker inspect nas-metadata_worker-1 --format 'metadata_worker: {{if .State.Health}}{{.State.Health.Status}}{{else}}no healthcheck{{end}}' 2>/dev/null || true
docker inspect nas-redis-1 --format 'redis: {{if .State.Health}}{{.State.Health.Status}}{{else}}no healthcheck{{end}}' 2>/dev/null || true

echo
echo "========== HEARTBEATS =========="
echo -n "scanner: "
docker exec nas-redis-1 redis-cli GET scanner:heartbeat 2>/dev/null || true
echo -n "watcher: "
docker exec nas-redis-1 redis-cli GET watcher:heartbeat 2>/dev/null || true
echo -n "watcher status: "
docker exec nas-redis-1 redis-cli GET watcher:heartbeat:status 2>/dev/null || true
echo -n "metadata_worker: "
docker exec nas-redis-1 redis-cli GET metadata_worker:heartbeat 2>/dev/null || true

echo
echo "========== LAST ACTIVITY =========="
echo -n "scanner:last_scan = "
docker exec nas-redis-1 redis-cli GET scanner:last_scan 2>/dev/null || true
echo -n "scanner:last_full_scan = "
docker exec nas-redis-1 redis-cli GET scanner:last_full_scan 2>/dev/null || true
echo -n "scanner:last_interval_scan = "
docker exec nas-redis-1 redis-cli GET scanner:last_interval_scan 2>/dev/null || true
echo -n "scanner:last_interval_root = "
docker exec nas-redis-1 redis-cli GET scanner:last_interval_root 2>/dev/null || true
echo -n "metadata_worker:last_event = "
docker exec nas-redis-1 redis-cli GET metadata_worker:last_event 2>/dev/null || true
echo -n "watcher:last_event = "
docker exec nas-redis-1 redis-cli GET watcher:last_event 2>/dev/null || true
echo -n "watcher:startup_recovery_roots = "
docker exec nas-redis-1 redis-cli GET watcher:recovery_roots 2>/dev/null || true

echo
echo "========== DIRTY ROOTS =========="
echo -n "pending = "
docker exec nas-redis-1 redis-cli HLEN scanner:dirty_roots 2>/dev/null || true
docker exec nas-redis-1 redis-cli HGETALL scanner:dirty_roots 2>/dev/null || true

echo
echo "========== SCAN SESSIONS =========="
docker exec nas-postgres-1 sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -P pager=off -c "SELECT id, type, status, started_at, finished_at, files_discovered, jobs_enqueued, jobs_processed FROM public.v_scan_status LIMIT 5"' 2>/dev/null \
  || docker exec postgres sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -P pager=off -c "SELECT id, type, status, started_at, finished_at, files_discovered, jobs_enqueued, jobs_processed FROM public.v_scan_status LIMIT 5"' 2>/dev/null \
  || echo "scan sessions niet beschikbaar"

echo
echo "========== LOCKS =========="
docker exec nas-redis-1 redis-cli KEYS "*lock*" 2>/dev/null || true

echo
echo "========== STREAM =========="
echo -n "polling = "
docker exec nas-redis-1 redis-cli XLEN scan_stream 2>/dev/null || true
echo -n "realtime = "
docker exec nas-redis-1 redis-cli XLEN scan_stream_realtime 2>/dev/null || true

echo
echo "========== POLLING GROUPS =========="
docker exec nas-redis-1 redis-cli XINFO GROUPS scan_stream 2>/dev/null || true
echo
echo "========== REALTIME GROUPS =========="
docker exec nas-redis-1 redis-cli XINFO GROUPS scan_stream_realtime 2>/dev/null || true

echo
echo "========== DLQ =========="
docker exec nas-redis-1 redis-cli XLEN scan_stream_dlq 2>/dev/null || true

echo
echo "========== DOCS =========="
ls -lh docs/DOCUMENTATIE.md 2>/dev/null || echo "docs/DOCUMENTATIE.md ontbreekt"
```

## `tools/runtime/health`

Toont runtime health, Redis en heartbeat status.

- CORE command: `core runtime health`
- Bestaat: `True`
- Regels: `73`
- Gebruikt docker compose: `False`
- Gebruikt Redis: `True`

```bash
#!/bin/bash
cd /volume1/docker/nas-stack
fail=0

echo "========== CONTAINER HEALTH =========="

check_container() {
  name="$1"
  if docker inspect "$name" >/dev/null 2>&1; then
    state=$(docker inspect "$name" --format '{{.State.Status}}')
    health=$(docker inspect "$name" --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}none{{end}}')
    echo "$name: status=$state health=$health"
    [ "$state" = "running" ] || fail=1
    [ "$health" = "unhealthy" ] && fail=1
  else
    echo "$name: missing"
    fail=1
  fi
}

check_container nas-redis-1
check_container nas-scanner-1
check_container nas-watcher-1
check_container nas-metadata_worker-1

echo
echo "========== REDIS =========="
docker exec nas-redis-1 redis-cli ping || fail=1

echo
echo "========== HEARTBEATS =========="
scanner_hb=$(docker exec nas-redis-1 redis-cli GET scanner:heartbeat 2>/dev/null)
watcher_hb=$(docker exec nas-redis-1 redis-cli GET watcher:heartbeat 2>/dev/null)
worker_hb=$(docker exec nas-redis-1 redis-cli GET metadata_worker:heartbeat 2>/dev/null)

echo "scanner: ${scanner_hb:-missing}"
echo "watcher: ${watcher_hb:-missing}"
echo "metadata_worker: ${worker_hb:-missing}"

[ -n "$scanner_hb" ] || fail=1
[ -n "$watcher_hb" ] || fail=1
[ -n "$worker_hb" ] || fail=1

echo
echo "========== LAST ACTIVITY =========="
echo -n "scanner:last_scan = "
docker exec nas-redis-1 redis-cli GET scanner:last_scan 2>/dev/null || true
echo -n "metadata_worker:last_event = "
docker exec nas-redis-1 redis-cli GET metadata_worker:last_event 2>/dev/null || true
echo -n "watcher:last_event = "
docker exec nas-redis-1 redis-cli GET watcher:last_event 2>/dev/null || true
echo -n "dirty roots pending = "
docker exec nas-redis-1 redis-cli HLEN scanner:dirty_roots 2>/dev/null || true

echo
echo "========== STREAM =========="
docker exec nas-redis-1 redis-cli XLEN scan_stream || fail=1
docker exec nas-redis-1 redis-cli XINFO GROUPS scan_stream || true
docker exec nas-redis-1 redis-cli XLEN scan_stream_realtime || fail=1
docker exec nas-redis-1 redis-cli XINFO GROUPS scan_stream_realtime || true

echo
echo "========== DLQ =========="
docker exec nas-redis-1 redis-cli XLEN scan_stream_dlq || true

echo
if [ "$fail" -eq 0 ]; then
  echo "HEALTH OK"
else
  echo "HEALTH WARNING"
fi

exit "$fail"
```

## `tools/runtime/dlq`

Toont DLQ-informatie.

- CORE command: `core runtime dlq`
- Bestaat: `True`
- Regels: `10`
- Gebruikt docker compose: `False`
- Gebruikt Redis: `True`

```bash
#!/bin/sh
set -eu
cd /volume1/docker/nas-stack

echo "========== DLQ LENGTH =========="
docker exec nas-redis-1 redis-cli XLEN scan_stream_dlq

echo
echo "========== LAST 20 DLQ ITEMS =========="
docker exec nas-redis-1 redis-cli XREVRANGE scan_stream_dlq + - COUNT 20
```

## `tools/runtime/cleanlocks`

Verwijdert locks handmatig.

- CORE command: `core runtime cleanlocks`
- Bestaat: `True`
- Regels: `6`
- Gebruikt docker compose: `False`
- Gebruikt Redis: `True`

```bash
#!/bin/bash
cd /volume1/docker/nas-stack
docker exec nas-redis-1 redis-cli DEL scanner:lock:event
docker exec nas-redis-1 redis-cli DEL metadata_worker:lock
docker exec nas-redis-1 redis-cli DEL metadata:lock
echo "Locks cleared."
```

## `tools/runtime/watch`

Live monitor.

- CORE command: `core runtime watch`
- Bestaat: `True`
- Regels: `3`
- Gebruikt docker compose: `True`
- Gebruikt Redis: `True`

```bash
#!/bin/bash
cd /volume1/docker/nas-stack
watch -n 5 'docker compose ps; echo; docker exec nas-redis-1 redis-cli XLEN scan_stream; echo; docker exec nas-redis-1 redis-cli XINFO GROUPS scan_stream; echo; docker exec nas-redis-1 redis-cli XLEN scan_stream_dlq'
```

## `gendocs`

Genereert documentatie.

- CORE command: `core docs generate`
- Bestaat: `True`
- Regels: `5`
- Gebruikt docker compose: `False`
- Gebruikt Redis: `False`

```bash
#!/bin/bash
set -e

cd /volume1/docker/nas-stack
python3 tools/docs/generate_docs.py
```



---

# Troubleshooting

Alle runtime checks lopen via de CORE CLI. Run deze commands op de NAS in `/volume1/docker/nas-stack`, of via de Windows wrapper vanuit de repository.

## Worker is unhealthy

```bash
core runtime health
```

Voor detailinformatie:

```bash
docker inspect nas-metadata_worker-1 --format '{{json .State.Health}}'
```

Controleer of de healthcheck `python3` gebruikt.

## Scanner doet niets

```bash
core runtime logs
core runtime status
```

## Realtime watcher ontbreekt of is unhealthy

```bash
core runtime health
core runtime status
/usr/local/bin/docker compose logs --tail=200 watcher
```

Controleer in `core runtime status` de watcher-heartbeat, `watcher:last_event` en `scanner:dirty_roots`. Een ontbrekende heartbeat betekent dat de watcher niet actief is of Redis niet kan bereiken. Herstel eerst de watcher en laat de dirty-root reconciliation afronden voordat u een opschoning start.

## Container Manager toont een ID-prefix

Controleer de echte Dockernaam:

```bash
docker ps --format '{{.Names}}'
```

Als Docker `nas-scanner-1`, `nas-metadata_worker-1` en `nas-watcher-1` toont, is alleen de Synology-interface uit sync. Sluit Container Manager voordat containers met Compose worden gerecreëerd en open de GUI pas nadat de containers stabiel en gezond zijn.

## Worker zegt dat er al een worker draait

Controleer locks en heartbeats:

```bash
core runtime status
```

## DLQ groeit

```bash
core runtime dlq
```

## Noodoplossing locks

```bash
core runtime cleanlocks
```

## Live monitor

```bash
core runtime watch
```

## Windows wrapper

```powershell
.\tools\windows\core.ps1 runtime status
.\tools\windows\core.ps1 runtime dlq
```


---

# Documentatiegenerator

De documentatiegenerator maakt documentatie op basis van bronbestanden.

## Output

- `docs/DOCUMENTATIE.md`
- `docs/DOCUMENTATIE.docx`
- `docs/wiki/*.md`
- `docs/generated/*.json`

## Self-documentation

De generator analyseert ook zichzelf. Daardoor verschijnt nieuwe generatorcode automatisch in deze documentatie.

## Functies

- `build_analysis()` op regel `42`
- `render_json_outputs(analysis)` op regel `66`
- `render_wiki_pages(analysis)` op regel `78`
- `main()` op regel `110`


---

# Bronbestanden

## `scanner.py`

```python
#!/usr/bin/env python3
import os
import time
import socket
import logging
import uuid
from datetime import datetime, timezone

import redis
import psycopg2

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("scanner")

REDIS_HOST = os.getenv("REDIS_HOST", "redis")
REDIS_PORT = int(os.getenv("REDIS_PORT", "6379"))

SCAN_ROOT = os.getenv("SCAN_ROOT", "/volume1")
SCAN_INTERVAL = max(1, int(os.getenv("SCAN_INTERVAL", "600")))
FULL_SCAN_INTERVAL = max(SCAN_INTERVAL, int(os.getenv("FULL_SCAN_INTERVAL", "3600")))
MISSING_SCAN_THRESHOLD = max(1, int(os.getenv("MISSING_SCAN_THRESHOLD", "2")))

STREAM_KEY = os.getenv("STREAM_KEY", "scan_stream")
LOCK_KEY = "scanner:lock:event"
LOCK_TTL = 90

HEARTBEAT_KEY = "scanner:heartbeat"
HEARTBEAT_STATUS_KEY = "scanner:heartbeat:status"
LAST_SCAN_KEY = "scanner:last_scan"
LAST_FULL_SCAN_KEY = "scanner:last_full_scan"
LAST_INTERVAL_SCAN_KEY = "scanner:last_interval_scan"
LAST_INTERVAL_ROOT_KEY = "scanner:last_interval_root"
INTERVAL_ROOT_INDEX_KEY = "scanner:interval:root_index"
DIRTY_ROOTS_KEY = "scanner:dirty_roots"
FULL_SCAN_REQUEST_KEY = "scanner:request:full"
HEARTBEAT_TTL = 120

CONSUMER_NAME = socket.gethostname()
SIGNATURE_PREFIX = "scanner:sig:"
STATE_SEPARATOR = "\n"

IGNORE_PREFIXES = ("@", ".", "#")
IGNORE_NAMES = {"tmp", "lost+found"}
IGNORE_CONTAINS = (
    "/@eaDir/",
    "/#recycle/",
    "/.Trash/",
    "/docker/postgres/",
    "/docker/redis/",
)

r = redis.Redis(
    host=REDIS_HOST,
    port=REDIS_PORT,
    decode_responses=True,
    socket_timeout=30,
    socket_connect_timeout=10,
    retry_on_timeout=True,
)

_db_conn = None


def get_db():
    global _db_conn
    if _db_conn is None or _db_conn.closed:
        _db_conn = psycopg2.connect(
            host=os.getenv("DB_HOST"),
            port=int(os.getenv("DB_PORT", "5432")),
            user=os.getenv("DB_USER"),
            password=os.getenv("DB_PASS"),
            dbname=os.getenv("DB_NAME"),
        )
        _db_conn.autocommit = True
    return _db_conn


def session_call(query, params=(), fetch=False):
    """Run scan bookkeeping without making PostgreSQL a scanner dependency."""
    try:
        with get_db().cursor() as cur:
            cur.execute(query, params)
            row = cur.fetchone() if fetch else None
            return row[0] if row else None
    except Exception as exc:
        logger.warning("Scan session update failed: %s", exc)
        return None


def utc_now():
    return datetime.now(timezone.utc).isoformat()


def should_skip_path(path):
    parts = path.split(os.sep)
    for part in parts:
        if not part:
            continue
        if part in IGNORE_NAMES:
            return True
        if part.startswith(IGNORE_PREFIXES):
            return True
    return any(x in path for x in IGNORE_CONTAINS)


def heartbeat(status="running"):
    try:
        r.set(HEARTBEAT_KEY, utc_now(), ex=HEARTBEAT_TTL)
        r.set(HEARTBEAT_STATUS_KEY, status, ex=HEARTBEAT_TTL)
    except Exception as e:
        logger.warning("Heartbeat failed: %s", e)


def acquire_lock():
    owner = r.get(LOCK_KEY)
    if owner and owner != CONSUMER_NAME:
        owner_hb = r.get(HEARTBEAT_KEY)
        if owner_hb:
            logger.warning("Scanner already running: owner=%s heartbeat=%s", owner, owner_hb)
            return False
        logger.warning("Stale scanner lock found: owner=%s, taking over", owner)
        r.delete(LOCK_KEY)

    ok = r.set(LOCK_KEY, CONSUMER_NAME, nx=True, ex=LOCK_TTL)
    if not ok:
        logger.warning("Scanner lock busy: %s", r.get(LOCK_KEY))
        return False

    logger.info("Scanner lock acquired by %s", CONSUMER_NAME)
    return True


def refresh_lock():
    try:
        if r.get(LOCK_KEY) == CONSUMER_NAME:
            r.expire(LOCK_KEY, LOCK_TTL)
    except Exception as e:
        logger.warning("Lock refresh failed: %s", e)


def release_lock():
    try:
        if r.get(LOCK_KEY) == CONSUMER_NAME:
            r.delete(LOCK_KEY)
    except Exception:
        pass


def discover_roots():
    if not os.path.isdir(SCAN_ROOT):
        logger.error("SCAN_ROOT does not exist: %s", SCAN_ROOT)
        return []

    roots = []
    for name in os.listdir(SCAN_ROOT):
        path = os.path.join(SCAN_ROOT, name)
        if not os.path.isdir(path):
            continue
        if name in IGNORE_NAMES or name.startswith(IGNORE_PREFIXES):
            continue
        if should_skip_path(path):
            continue
        roots.append(path)

    roots.sort()
    return roots


def file_signature(path, st):
    return f"{int(st.st_mtime)}:{st.st_size}:{st.st_ino}"


def parse_file_state(raw):
    if not raw:
        return None, None, 0

    parts = str(raw).split(STATE_SEPARATOR, 2)
    signature = parts[0]
    scan_id = (parts[1] or None) if len(parts) > 1 else None

    try:
        missing_scans = int(parts[2]) if len(parts) > 2 else 0
    except ValueError:
        missing_scans = 0

    return signature, scan_id, missing_scans


def encode_file_state(signature, scan_id, missing_scans=0):
    return STATE_SEPARATOR.join((signature, scan_id or "", str(missing_scans)))


def changed(path, signature, scan_id, full_sweep=True):
    key = SIGNATURE_PREFIX + path
    old_signature, last_full_sweep, missing_sweeps = parse_file_state(r.get(key))
    if full_sweep:
        last_full_sweep = scan_id
        missing_sweeps = 0
    r.set(key, encode_file_state(signature, last_full_sweep, missing_sweeps))
    return old_signature != signature


def mark_seen(path, scan_id):
    key = SIGNATURE_PREFIX + path
    signature, _, _ = parse_file_state(r.get(key))
    if signature is not None:
        r.set(key, encode_file_state(signature, scan_id))


def reconcile_missing(scan_id, session_id=None, root_scope=None, threshold=None):
    checked = 0
    deleted = 0
    threshold = MISSING_SCAN_THRESHOLD if threshold is None else max(1, threshold)
    pattern = SIGNATURE_PREFIX + "*"
    if root_scope:
        pattern = SIGNATURE_PREFIX + root_scope.rstrip("/") + "/" + "*"

    for key in r.scan_iter(match=pattern, count=1000):
        raw = r.get(key)
        signature, last_seen_scan, missing_scans = parse_file_state(raw)

        if signature is None or last_seen_scan == scan_id:
            continue

        checked += 1
        missing_scans += 1

        if missing_scans < threshold:
            r.set(key, encode_file_state(signature, last_seen_scan, missing_scans))
            continue

        path = key[len(SIGNATURE_PREFIX):]
        r.xadd(STREAM_KEY, {
            "event": "DELETE",
            "path": path,
            "source": "polling_scanner",
            "ts": utc_now(),
            "scan_session_id": str(session_id or ""),
        })
        r.delete(key)
        deleted += 1

    return checked, deleted


def raise_walk_error(error):
    raise error


def select_interval_root(roots):
    if not roots:
        return None
    try:
        index = int(r.get(INTERVAL_ROOT_INDEX_KEY) or 0)
    except (TypeError, ValueError):
        index = 0
    root = roots[index % len(roots)]
    r.set(INTERVAL_ROOT_INDEX_KEY, str((index + 1) % len(roots)))
    return root


def select_dirty_root(roots):
    allowed = set(roots)
    dirty = r.hgetall(DIRTY_ROOTS_KEY)
    candidates = [
        (marked_at, root)
        for root, marked_at in dirty.items()
        if root in allowed
    ]
    if not candidates:
        return None, None
    marked_at, root = min(candidates)
    return root, marked_at


def clear_dirty_root(root, expected_marker):
    script = """
    if redis.call('HGET', KEYS[1], ARGV[1]) == ARGV[2] then
        return redis.call('HDEL', KEYS[1], ARGV[1])
    end
    return 0
    """
    return bool(r.eval(script, 1, DIRTY_ROOTS_KEY, root, expected_marker))


def _scan_roots(
    roots,
    scan_id,
    session_id,
    full_sweep,
    scan_type=None,
    reconcile_scope=None,
    missing_threshold=None,
):
    scan_type = scan_type or ("full" if full_sweep else "interval")
    logger.info("Starting %s scan roots=%s", scan_type, ", ".join(roots))

    discovered = 0
    enqueued = 0

    for root_base in roots:
        root_started = time.time()
        root_discovered = 0
        root_enqueued = 0
        heartbeat("scanning")
        refresh_lock()

        for root, dirs, files in os.walk(root_base, onerror=raise_walk_error):
            dirs[:] = [
                d for d in dirs
                if d not in IGNORE_NAMES
                and not d.startswith(IGNORE_PREFIXES)
                and not should_skip_path(os.path.join(root, d))
            ]

            for filename in files:
                path = os.path.join(root, filename)

                if should_skip_path(path):
                    continue

                try:
                    st = os.stat(path)
                except FileNotFoundError:
                    continue
                except PermissionError:
                    if full_sweep:
                        mark_seen(path, scan_id)
                    logger.warning("Permission denied: %s", path)
                    continue
                except Exception as e:
                    if full_sweep:
                        mark_seen(path, scan_id)
                    logger.warning("stat failed: %s err=%s", path, e)
                    continue

                discovered += 1
                root_discovered += 1
                if root_discovered % 1000 == 0:
                    heartbeat("scanning")
                    refresh_lock()
                sig = file_signature(path, st)

                if not changed(path, sig, scan_id, full_sweep=full_sweep):
                    continue

                r.xadd(STREAM_KEY, {
                    "event": "UPSERT",
                    "path": path,
                    "source": "polling_scanner",
                    "mtime": str(int(st.st_mtime)),
                    "size": str(st.st_size),
                    "inode": str(st.st_ino),
                    "ts": utc_now(),
                    "scan_session_id": str(session_id or ""),
                })
                enqueued += 1
                root_enqueued += 1

        logger.info(
            "Root done: type=%s root=%s discovered=%s enqueued=%s elapsed=%.1fs",
            scan_type,
            root_base,
            root_discovered,
            root_enqueued,
            time.time() - root_started,
        )

    if full_sweep:
        missing, deleted = reconcile_missing(
            scan_id,
            session_id=session_id,
            root_scope=reconcile_scope,
            threshold=missing_threshold,
        )
    else:
        missing, deleted = 0, 0

    if session_id:
        session_call("SELECT increment_files_discovered(%s, %s)", (session_id, discovered))
        session_call("SELECT increment_jobs_enqueued(%s, %s)", (session_id, enqueued + deleted))
        session_call("SELECT finish_scan_session(%s)", (session_id,))

    finished_at = utc_now()
    r.set(LAST_SCAN_KEY, finished_at, ex=HEARTBEAT_TTL * 4)
    if scan_type == "full":
        r.set(LAST_FULL_SCAN_KEY, finished_at)
    else:
        r.set(LAST_INTERVAL_SCAN_KEY, finished_at)
        r.set(LAST_INTERVAL_ROOT_KEY, roots[0] if roots else "")
    return discovered, enqueued, missing, deleted


def run_scan(
    scan_type,
    roots,
    *,
    full_sweep=None,
    reconcile_scope=None,
    missing_threshold=None,
):
    scan_id = uuid.uuid4().hex
    session_id = session_call("SELECT create_scan_session(%s)", (scan_type,), fetch=True)
    if full_sweep is None:
        full_sweep = scan_type == "full"
    try:
        return _scan_roots(
            roots,
            scan_id,
            session_id,
            full_sweep=full_sweep,
            scan_type=scan_type,
            reconcile_scope=reconcile_scope,
            missing_threshold=missing_threshold,
        )
    except Exception:
        if session_id:
            session_call(
                "UPDATE scan_sessions SET status = 'failed', finished_at = NOW() WHERE id = %s",
                (session_id,),
            )
        raise


def scan_once():
    """Run a complete reconciliation sweep (backward-compatible entry point)."""
    roots = discover_roots()
    if not roots:
        raise RuntimeError("Full scan aborted: no scan roots discovered")
    return run_scan("full", roots)


def scan_interval_once():
    roots = discover_roots()
    dirty_root, dirty_marker = select_dirty_root(roots)
    root = dirty_root or select_interval_root(roots)
    if dirty_root:
        result = run_scan(
            "interval",
            [dirty_root],
            full_sweep=True,
            reconcile_scope=dirty_root,
            missing_threshold=1,
        )
    else:
        result = run_scan("interval", [root] if root else [])
    if dirty_root:
        if clear_dirty_root(dirty_root, dirty_marker):
            logger.info("Dirty root reconciled: %s", dirty_root)
        else:
            logger.info("Dirty root changed during reconciliation; keeping marker: %s", dirty_root)
    return result


def consume_full_scan_request():
    requested_at = r.get(FULL_SCAN_REQUEST_KEY)
    if not requested_at:
        return False
    r.delete(FULL_SCAN_REQUEST_KEY)
    logger.info("Manual full scan requested at %s", requested_at)
    return True


def wait_for_next_scan(seconds):
    """Wait interruptibly so a manual full request is picked up promptly."""
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if r.get(FULL_SCAN_REQUEST_KEY):
            return
        heartbeat("idle")
        refresh_lock()
        time.sleep(min(1.0, max(0.0, deadline - time.monotonic())))


def main():
    if not acquire_lock():
        return

    heartbeat("started")
    logger.info(
        "Starting polling scanner on %s interval=%ss full_interval=%ss",
        SCAN_ROOT,
        SCAN_INTERVAL,
        FULL_SCAN_INTERVAL,
    )
    next_full_at = 0.0

    try:
        while True:
            refresh_lock()
            heartbeat("running")

            started = time.time()
            try:
                full_sweep = consume_full_scan_request() or time.monotonic() >= next_full_at
                if full_sweep:
                    discovered, enqueued, missing, deleted = scan_once()
                    next_full_at = time.monotonic() + FULL_SCAN_INTERVAL
                    scan_type = "full"
                else:
                    discovered, enqueued, missing, deleted = scan_interval_once()
                    scan_type = "interval"
                elapsed = time.time() - started
                heartbeat("idle")
                logger.info(
                    "Scan done: type=%s discovered=%s enqueued=%s missing=%s deleted=%s elapsed=%.1fs",
                    scan_type,
                    discovered,
                    enqueued,
                    missing,
                    deleted,
                    elapsed,
                )
            except Exception as e:
                heartbeat("error")
                logger.exception("Scan loop failed: %s", e)

            wait_for_next_scan(SCAN_INTERVAL)

    finally:
        heartbeat("stopped")
        release_lock()


if __name__ == "__main__":
    main()
```

## `metadata_worker.py`

```python
#!/usr/bin/env python3
import os
import json
import socket
import logging
from datetime import datetime, timezone

import redis
import psycopg2
import psycopg2.extras
import magic
import pyvips
import xxhash

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("metadata-worker")

REDIS_HOST = os.getenv("REDIS_HOST", "redis")
REDIS_PORT = int(os.getenv("REDIS_PORT", "6379"))

STREAM_KEY = "scan_stream"
REALTIME_STREAM_KEY = os.getenv("REALTIME_STREAM_KEY", "scan_stream_realtime")
GROUP_NAME = "metadata_group"
DLQ_STREAM = "scan_stream_dlq"

LOCK_KEY = "metadata_worker:lock"
LOCK_TTL = 90

HEARTBEAT_KEY = "metadata_worker:heartbeat"
HEARTBEAT_STATUS_KEY = "metadata_worker:heartbeat:status"
LAST_EVENT_KEY = "metadata_worker:last_event"
HEARTBEAT_TTL = 120

CONSUMER_NAME = socket.gethostname()
FORCE_FULL = os.getenv("FORCE_FULL_METADATA", "false").lower() == "true"

r = redis.Redis(
    host=REDIS_HOST,
    port=REDIS_PORT,
    decode_responses=True,
    socket_timeout=30,
    socket_connect_timeout=10,
    retry_on_timeout=True,
)

_db_conn = None


def utc_now():
    return datetime.now(timezone.utc).isoformat()


def heartbeat(status="running"):
    try:
        r.set(HEARTBEAT_KEY, utc_now(), ex=HEARTBEAT_TTL)
        r.set(HEARTBEAT_STATUS_KEY, status, ex=HEARTBEAT_TTL)
    except Exception as e:
        logger.warning("Heartbeat failed: %s", e)


def get_db():
    global _db_conn
    if _db_conn is None or _db_conn.closed:
        _db_conn = psycopg2.connect(
            host=os.getenv("DB_HOST"),
            port=int(os.getenv("DB_PORT")),
            user=os.getenv("DB_USER"),
            password=os.getenv("DB_PASS"),
            dbname=os.getenv("DB_NAME"),
        )
        _db_conn.autocommit = False
        logger.info("Database connected")
    return _db_conn


def acquire_lock():
    owner = r.get(LOCK_KEY)
    if owner and owner != CONSUMER_NAME:
        owner_hb = r.get(HEARTBEAT_KEY)
        if owner_hb:
            logger.warning("Metadata worker already running: owner=%s heartbeat=%s", owner, owner_hb)
            return False
        logger.warning("Stale metadata worker lock found: owner=%s, taking over", owner)
        r.delete(LOCK_KEY)

    ok = r.set(LOCK_KEY, CONSUMER_NAME, nx=True, ex=LOCK_TTL)
    if not ok:
        logger.warning("Metadata worker lock busy: %s", r.get(LOCK_KEY))
        return False

    logger.info("Metadata worker lock acquired by %s", CONSUMER_NAME)
    return True


def refresh_lock():
    try:
        if r.get(LOCK_KEY) == CONSUMER_NAME:
            r.expire(LOCK_KEY, LOCK_TTL)
    except Exception as e:
        logger.warning("Lock refresh failed: %s", e)


def release_lock():
    try:
        if r.get(LOCK_KEY) == CONSUMER_NAME:
            r.delete(LOCK_KEY)
    except Exception:
        pass


def ensure_group(stream_key=STREAM_KEY):
    try:
        r.xgroup_create(stream_key, GROUP_NAME, id="0", mkstream=True)
        logger.info("Redis consumer group created")
    except redis.exceptions.ResponseError as e:
        if "BUSYGROUP" not in str(e):
            raise


def read_next_batch():
    realtime = r.xreadgroup(
        GROUP_NAME,
        CONSUMER_NAME,
        streams={REALTIME_STREAM_KEY: ">"},
        count=50,
    )
    if realtime:
        return realtime
    return r.xreadgroup(
        GROUP_NAME,
        CONSUMER_NAME,
        streams={STREAM_KEY: ">"},
        count=10,
        block=1000,
    )


def upsert_folder(cur, path):
    path = os.path.normpath(path)
    if not path or path == "/":
        return None

    cur.execute("SELECT id FROM folders WHERE path = %s", (path,))
    row = cur.fetchone()
    if row:
        return row["id"]

    parent = os.path.dirname(path)
    parent_id = None if parent == path else upsert_folder(cur, parent)

    cur.execute("""
        INSERT INTO folders (path, parent_id)
        VALUES (%s, %s)
        ON CONFLICT (path) DO UPDATE SET
            path = EXCLUDED.path
        RETURNING id
    """, (path, parent_id))

    return cur.fetchone()["id"]


def hash_first_1024(path):
    try:
        with open(path, "rb") as f:
            return xxhash.xxh64(f.read(1024)).hexdigest()
    except Exception:
        return None


def get_mime(path):
    try:
        return magic.from_file(path, mime=True)
    except Exception as e:
        logger.warning("MIME failed: %s err=%s", path, e)
        return None


def get_image_dims(path, mime):
    if not mime or not mime.startswith("image/"):
        return None, None

    try:
        img = pyvips.Image.new_from_file(path)
        return img.width, img.height
    except Exception as e:
        logger.warning("Image metadata failed: %s err=%s", path, e)
        return None, None


def path_is_missing(path):
    try:
        os.stat(path)
        return False
    except FileNotFoundError:
        return True
    except OSError:
        return False


def get_file_by_path(cur, path):
    cur.execute(
        "SELECT id, path, deleted_at FROM files WHERE path = %s",
        (path,),
    )
    return cur.fetchone()


def classify_path_mutation(existing_file):
    if not existing_file:
        return "CREATED"
    if existing_file["deleted_at"] is not None:
        return "RESTORED"
    return "MODIFIED"


def classify_rename_mutation(old_path, new_path):
    if os.path.dirname(old_path) == os.path.dirname(new_path):
        return "RENAMED"
    return "MOVED"


def identity_confidence(candidate, filesystem_device, inode, size_bytes, modified_at_fs, content_hash):
    signals = {
        "filesystem_device_match": candidate.get("filesystem_device") == filesystem_device,
        "inode_match": candidate.get("inode") == inode,
        "size_match": candidate.get("size_bytes") == size_bytes,
        "mtime_match": candidate.get("modified_at_fs") == modified_at_fs,
        "content_hash_match": bool(content_hash) and candidate.get("hash_content") == content_hash,
        "old_path_missing": path_is_missing(candidate["path"]),
    }
    weights = {
        "filesystem_device_match": 20,
        "inode_match": 20,
        "size_match": 10,
        "mtime_match": 10,
        "content_hash_match": 30,
        "old_path_missing": 10,
    }
    score = sum(weights[name] for name, matched in signals.items() if matched)
    level = "high" if score >= 90 else "medium" if score >= 65 else "low"
    return score, level, signals


def insert_file_event(cur, *, file_id, event_type, source, old_path=None,
                      new_path=None, candidate_file_id=None, score=None,
                      level=None, decision=None, signals=None, reason=None,
                      scan_session_id=None):
    scan_session_id = scan_session_id or None
    cur.execute("""
        INSERT INTO file_events (
            file_id, candidate_file_id, event_type, old_path, new_path,
            confidence_score, confidence_level, decision, signals, reason,
            scan_session_id, source
        ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb,%s,%s,%s)
    """, (
        file_id, candidate_file_id, event_type, old_path, new_path,
        score, level, decision, json.dumps(signals or {}), reason,
        scan_session_id, source,
    ))


def evaluate_identity_match(cur, path, filesystem_device, inode, size_bytes, modified_at_fs, content_hash):
    cur.execute("""
        SELECT id, path, filesystem_device, inode, size_bytes, modified_at_fs, hash_content
        FROM files
        WHERE filesystem_device = %s
          AND inode = %s
          AND path <> %s
          AND deleted_at IS NULL
        ORDER BY id
    """, (filesystem_device, inode, path))

    rows = cur.fetchall()
    existing_paths = [row for row in rows if not path_is_missing(row["path"])]
    missing_candidates = [row for row in rows if row not in existing_paths]

    if existing_paths:
        return {
            "candidate": existing_paths[0],
            "event_type": "HARDLINK_DETECTED",
            "level": "ambiguous",
            "score": None,
            "signals": {"candidate_count": len(rows), "old_path_missing": False},
            "decision": "created_separate",
            "reason": "same inode is still active at another path",
        }

    if len(missing_candidates) != 1:
        return {
            "candidate": missing_candidates[0] if missing_candidates else None,
            "event_type": "IDENTITY_AMBIGUOUS" if missing_candidates else None,
            "level": "ambiguous" if missing_candidates else None,
            "score": None,
            "signals": {"candidate_count": len(missing_candidates)},
            "decision": "created_separate",
            "reason": "multiple missing candidates" if missing_candidates else "no candidate",
        }

    candidate = missing_candidates[0]
    score, level, signals = identity_confidence(
        candidate, filesystem_device, inode, size_bytes, modified_at_fs, content_hash
    )
    signals["candidate_count"] = 1
    matched = level == "high"
    return {
        "candidate": candidate,
        "event_type": "IDENTITY_MATCHED" if matched else "IDENTITY_REJECTED",
        "level": level,
        "score": score,
        "signals": signals,
        "decision": "auto_linked" if matched else "created_separate",
        "reason": "unique high-confidence match" if matched else "confidence below automatic threshold",
    }


def find_rename_candidate(cur, path, inode, size_bytes, modified_at_fs,
                          content_hash=None, filesystem_device=None):
    result = evaluate_identity_match(
        cur, path, filesystem_device, inode, size_bytes, modified_at_fs, content_hash
    )
    return result["candidate"] if result["decision"] == "auto_linked" else None


def process_event(cur, data):
    event = str(data.get("event", "")).lower()
    path = data.get("path")

    if not path:
        raise ValueError("Empty path")

    path = os.path.normpath(str(path))

    if "delete" in event:
        cur.execute("""
            UPDATE files SET
                deleted_at = NOW(),
                updated_at = NOW(),
                last_mutation_type = 'DELETED'
            WHERE path = %s
            RETURNING id
        """, (path,))
        row = cur.fetchone()
        if row:
            insert_file_event(
                cur, file_id=row["id"], event_type="DELETED",
                source=data.get("source", "polling_scanner"),
                old_path=path, scan_session_id=data.get("scan_session_id"),
            )
        logger.info("Deleted: %s", path)
        return

    if not os.path.exists(path):
        cur.execute("""
            UPDATE files SET
                deleted_at = NOW(),
                updated_at = NOW(),
                last_mutation_type = 'DELETED'
            WHERE path = %s
            RETURNING id
        """, (path,))
        row = cur.fetchone()
        if row:
            insert_file_event(
                cur, file_id=row["id"], event_type="DELETED",
                source=data.get("source", "polling_scanner"),
                old_path=path, reason="path_missing",
                scan_session_id=data.get("scan_session_id"),
            )
        logger.warning("Missing file, marked deleted: %s", path)
        return

    folder_path = os.path.dirname(path)
    folder_id = upsert_folder(cur, folder_path)

    if not folder_id:
        raise RuntimeError(f"No folder_id for {folder_path}")

    filename = os.path.basename(path)
    extension = os.path.splitext(filename)[1].lstrip(".").lower() or None

    stat = os.stat(path)
    size_bytes = stat.st_size
    modified_at_fs = int(stat.st_mtime)
    inode = stat.st_ino
    filesystem_device = stat.st_dev

    hash_path = xxhash.xxh64(path).hexdigest()
    hash_content = hash_first_1024(path)
    mime = get_mime(path)

    values = (
        folder_id,
        filename,
        extension,
        size_bytes,
        modified_at_fs,
        filesystem_device,
        inode,
        path,
        data.get("source", "polling_scanner"),
        hash_path,
        hash_content,
        mime,
    )

    existing_file = get_file_by_path(cur, path)
    rename_candidate = None
    identity_match = None
    if not existing_file:
        identity_match = evaluate_identity_match(
            cur, path, filesystem_device, inode, size_bytes, modified_at_fs, hash_content
        )
        if identity_match["decision"] == "auto_linked":
            rename_candidate = identity_match["candidate"]

    if rename_candidate:
        mutation_type = classify_rename_mutation(rename_candidate["path"], path)
        cur.execute("""
            UPDATE files SET
                folder_id          = %s,
                filename           = %s,
                extension          = %s,
                size_bytes         = %s,
                modified_at_fs     = %s,
                filesystem_device  = %s,
                inode              = %s,
                path               = %s,
                source             = %s,
                hash_path          = %s,
                hash_content       = %s,
                mime_type          = %s,
                last_mutation_type = %s,
                updated_at         = NOW(),
                deleted_at         = NULL
            WHERE id = %s
            RETURNING id
        """, values + (mutation_type, rename_candidate["id"]))
        logger.info(
            "%s: %s -> %s",
            mutation_type.title(),
            rename_candidate["path"],
            path,
        )
    else:
        mutation_type = classify_path_mutation(existing_file)
        cur.execute("""
            INSERT INTO files (
                folder_id, filename, extension, size_bytes,
                modified_at_fs, filesystem_device, inode,
                path, source, hash_path, hash_content,
                mime_type, deleted_at,
                last_mutation_type
            )
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,NULL,%s)
            ON CONFLICT (path) DO UPDATE SET
                folder_id          = EXCLUDED.folder_id,
                filename           = EXCLUDED.filename,
                extension          = EXCLUDED.extension,
                size_bytes         = EXCLUDED.size_bytes,
                modified_at_fs     = EXCLUDED.modified_at_fs,
                filesystem_device  = EXCLUDED.filesystem_device,
                inode              = EXCLUDED.inode,
                source             = EXCLUDED.source,
                hash_path          = EXCLUDED.hash_path,
                hash_content       = EXCLUDED.hash_content,
                mime_type          = EXCLUDED.mime_type,
                last_mutation_type = EXCLUDED.last_mutation_type,
                updated_at         = NOW(),
                deleted_at         = NULL
            RETURNING id
        """, values + (mutation_type,))
    file_id = cur.fetchone()["id"]
    insert_file_event(
        cur,
        file_id=file_id,
        candidate_file_id=rename_candidate["id"] if rename_candidate else None,
        event_type=mutation_type,
        source=data.get("source", "polling_scanner"),
        old_path=rename_candidate["path"] if rename_candidate else None,
        new_path=path,
        decision="auto_linked" if rename_candidate else "state_updated",
        scan_session_id=data.get("scan_session_id"),
    )
    if identity_match and identity_match["event_type"]:
        insert_file_event(
            cur,
            file_id=file_id,
            candidate_file_id=(
                identity_match["candidate"]["id"]
                if identity_match["candidate"] else None
            ),
            event_type=identity_match["event_type"],
            source=data.get("source", "polling_scanner"),
            old_path=(
                identity_match["candidate"]["path"]
                if identity_match["candidate"] else None
            ),
            new_path=path,
            score=identity_match["score"],
            level=identity_match["level"],
            decision=identity_match["decision"],
            signals=identity_match["signals"],
            reason=identity_match["reason"],
            scan_session_id=data.get("scan_session_id"),
        )

    if FORCE_FULL:
        cur.execute("DELETE FROM metadata WHERE file_id = %s", (file_id,))

    width, height = get_image_dims(path, mime)

    cur.execute("""
        INSERT INTO metadata (
            file_id, width, height, duration, missing
        )
        VALUES (%s,%s,%s,NULL,false)
        ON CONFLICT (file_id) DO UPDATE SET
            width     = EXCLUDED.width,
            height    = EXCLUDED.height,
            missing   = false
    """, (file_id, width, height))

    r.set(LAST_EVENT_KEY, utc_now(), ex=HEARTBEAT_TTL * 4)
    logger.info("Processed: %s", path)


def mark_session_job_processed(cur, data):
    session_id = data.get("scan_session_id")
    if session_id:
        try:
            cur.execute("SELECT increment_jobs_processed(%s)", (session_id,))
        except Exception as exc:
            # Session accounting must never turn an otherwise valid legacy
            # metadata event into a DLQ entry.
            logger.warning("Scan session update failed: %s", exc)


def main():
    if not acquire_lock():
        return

    heartbeat("started")
    conn = get_db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    ensure_group(STREAM_KEY)
    ensure_group(REALTIME_STREAM_KEY)
    logger.info("Worker started")

    try:
        while True:
            refresh_lock()
            heartbeat("waiting")

            try:
                resp = read_next_batch()
            except redis.exceptions.ResponseError as e:
                if "NOGROUP" in str(e):
                    logger.warning("NOGROUP detected, recreating group")
                    ensure_group(STREAM_KEY)
                    ensure_group(REALTIME_STREAM_KEY)
                    continue
                raise

            if not resp:
                continue

            heartbeat("processing")

            for source_stream, msgs in resp:
                for msg_id, data in msgs:
                    try:
                        process_event(cur, data)
                        mark_session_job_processed(cur, data)
                        conn.commit()
                    except Exception as e:
                        conn.rollback()
                        logger.error("DLQ msg=%s: %s", msg_id, e, exc_info=True)
                        r.xadd(DLQ_STREAM, {
                            "original_id": msg_id,
                            "original_stream": source_stream,
                            "data": json.dumps(data),
                            "error": str(e),
                            "ts": utc_now(),
                        })
                    finally:
                        r.xack(source_stream, GROUP_NAME, msg_id)

    finally:
        heartbeat("stopped")
        release_lock()


if __name__ == "__main__":
    main()
```

## `generate_docs.py`

_Bestand ontbreekt of is leeg._

## `tools/docs/config.py`

```python
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DOCS_DIR = ROOT / "docs"
WIKI_DIR = DOCS_DIR / "wiki"
GENERATED_DIR = DOCS_DIR / "generated"
DIAGRAMS_DIR = DOCS_DIR / "diagrams"

PYTHON_FILES = [
    "scanner.py",
    "metadata_worker.py",
    "generate_docs.py",
    "tools/docs/config.py",
    "tools/docs/analyze_python.py",
    "tools/docs/analyze_project.py",
    "tools/docs/render_markdown.py",
    "tools/docs/render_docx.py",
    "tools/docs/pages.py",
    "tools/docs/generate_docs.py",
]

CONFIG_FILES = [
    "docker-compose.yml",
    "Dockerfile.base",
    "Dockerfile.scanner",
    "Dockerfile.metadata",
    "schema.sql",
]

SCRIPT_FILES = [
    "tools/runtime/rebuild",
    "tools/runtime/rebuildall",
    "tools/runtime/logs",
    "tools/runtime/status",
    "tools/runtime/health",
    "tools/runtime/dlq",
    "tools/runtime/cleanlocks",
    "tools/runtime/watch",
    "gendocs",
]

ALL_SOURCE_FILES = PYTHON_FILES + CONFIG_FILES + SCRIPT_FILES
```

## `tools/docs/analyze_python.py`

```python
import ast
from pathlib import Path
from tools.docs.io_utils import read_text


def _import_name(node):
    if isinstance(node, ast.Import):
        return [alias.name for alias in node.names]
    if isinstance(node, ast.ImportFrom):
        module = node.module or ""
        return [(module + "." + alias.name).strip(".") for alias in node.names]
    return []


def analyze_python_file(root, relative_path):
    path = Path(root) / relative_path
    result = {
        "file": relative_path,
        "exists": path.exists(),
        "line_count": 0,
        "imports": [],
        "constants": [],
        "functions": [],
        "classes": [],
        "redis_keys": [],
        "sql_statements": [],
        "syntax_error": None,
    }

    if not path.exists():
        return result

    text = read_text(path)
    result["line_count"] = len(text.splitlines())

    try:
        tree = ast.parse(text)
    except SyntaxError as exc:
        result["syntax_error"] = str(exc)
        return result

    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            result["imports"].extend(_import_name(node))

        elif isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id.isupper():
                    result["constants"].append({
                        "name": target.id,
                        "line": node.lineno,
                    })

                    if isinstance(node.value, ast.Constant) and isinstance(node.value.value, str):
                        value = node.value.value
                        if "lock" in value.lower() or "stream" in value.lower() or "heartbeat" in value.lower():
                            result["redis_keys"].append(value)

        elif isinstance(node, ast.FunctionDef):
            result["functions"].append({
                "name": node.name,
                "line": node.lineno,
                "args": [arg.arg for arg in node.args.args],
                "docstring": ast.get_docstring(node) or "",
            })

        elif isinstance(node, ast.ClassDef):
            result["classes"].append({
                "name": node.name,
                "line": node.lineno,
                "docstring": ast.get_docstring(node) or "",
            })

        elif isinstance(node, ast.Constant) and isinstance(node.value, str):
            value = node.value.strip()
            upper = value.upper()
            if any(word in upper for word in ["SELECT ", "INSERT ", "UPDATE ", "DELETE ", "ON CONFLICT", "CREATE TABLE"]):
                result["sql_statements"].append({
                    "line": getattr(node, "lineno", None),
                    "snippet": value[:500],
                })

    result["imports"] = sorted(set(result["imports"]))
    result["redis_keys"] = sorted(set(result["redis_keys"]))
    result["constants"] = sorted(result["constants"], key=lambda x: x["name"])
    result["functions"] = sorted(result["functions"], key=lambda x: x["line"])
    result["classes"] = sorted(result["classes"], key=lambda x: x["line"])

    return result


def analyze_python_files(root, files):
    return {filename: analyze_python_file(root, filename) for filename in files}
```

## `tools/docs/analyze_project.py`

```python
import re
from pathlib import Path
from tools.docs.io_utils import read_text


def analyze_compose(root):
    path = Path(root) / "docker-compose.yml"
    text = read_text(path)

    services = []
    in_services = False

    for line in text.splitlines():
        if line.strip() == "services:":
            in_services = True
            continue

        if in_services:
            match = re.match(r"^  ([a-zA-Z0-9_-]+):\s*$", line)
            if match:
                services.append(match.group(1))

    env_vars = sorted(set(re.findall(r"\b[A-Z][A-Z0-9_]+\b", text)))
    env_vars = [e for e in env_vars if e not in {"CMD", "NULL", "TRUE", "FALSE"}]

    return {
        "file": "docker-compose.yml",
        "exists": path.exists(),
        "services": services,
        "environment_variables": env_vars,
        "line_count": len(text.splitlines()),
    }


def analyze_schema(root):
    path = Path(root) / "schema.sql"
    text = read_text(path)

    tables = sorted(set(re.findall(r"CREATE TABLE .*?public\.([a-zA-Z0-9_]+)", text)))
    unique_constraints = re.findall(r"UNIQUE \(([^\)]+)\)", text)
    foreign_keys = re.findall(r"FOREIGN KEY \(([^\)]+)\)", text)

    return {
        "file": "schema.sql",
        "exists": path.exists(),
        "tables": tables,
        "unique_constraints": sorted(set(unique_constraints)),
        "foreign_keys": sorted(set(foreign_keys)),
        "line_count": len(text.splitlines()),
    }


def analyze_scripts(root, scripts):
    result = {}

    for script in scripts:
        path = Path(root) / script
        text = read_text(path)
        result[script] = {
            "exists": path.exists(),
            "line_count": len(text.splitlines()),
            "uses_docker_compose": "docker compose" in text,
            "uses_redis": "redis-cli" in text,
            "content": text,
        }

    return result


def analyze_sources(root, files):
    result = {}
    for file in files:
        path = Path(root) / file
        text = read_text(path)
        result[file] = {
            "exists": path.exists(),
            "line_count": len(text.splitlines()),
        }
    return result
```

## `tools/docs/render_markdown.py`

```python
from pathlib import Path
from datetime import datetime
from tools.docs.io_utils import write_text, read_text


WIKI_LINKS = [
    "architecture.md",
    "core.md",
    "rfc.md",
    "database-views.md",
    "scanner.md",
    "metadata-worker.md",
    "docker.md",
    "postgres.md",
    "redis.md",
    "scripts.md",
    "troubleshooting.md",
    "documentation-generator.md",
    "sources.md",
]


def _fix_links_for_docs_root(content):
    for link in WIKI_LINKS:
        content = content.replace("](" + link + ")", "](wiki/" + link + ")")
    return content


def render_main_document(docs_dir, wiki_dir):
    pages = [
        "index.md",
        "architecture.md",
        "core.md",
        "rfc.md",
        "database-views.md",
        "scanner.md",
        "metadata-worker.md",
        "docker.md",
        "postgres.md",
        "redis.md",
        "scripts.md",
        "troubleshooting.md",
        "documentation-generator.md",
        "sources.md",
    ]

    md = []
    md.append("# NAS Metadata Platform Documentatie\n\n")
    md.append("_Automatisch gegenereerd op " + datetime.now().strftime("%Y-%m-%d %H:%M:%S") + "_\n\n")

    for page in pages:
        path = Path(wiki_dir) / page
        if path.exists():
            md.append("\n---\n\n")
            md.append(_fix_links_for_docs_root(read_text(path)))
            md.append("\n")

    write_text(Path(docs_dir) / "DOCUMENTATIE.md", "".join(md))
```

## `tools/docs/render_docx.py`

```python
try:
    from docx import Document
except Exception:
    Document = None


def render_docx(md_path, docx_path):
    if Document is None:
        return False

    text = md_path.read_text(encoding="utf-8", errors="replace")
    doc = Document()
    in_code = False

    for line in text.splitlines():
        if line.startswith("```"):
            in_code = not in_code
            continue

        if line.startswith("# "):
            doc.add_heading(line[2:].strip(), 1)
        elif line.startswith("## "):
            doc.add_heading(line[3:].strip(), 2)
        elif line.startswith("### "):
            doc.add_heading(line[4:].strip(), 3)
        elif line.startswith("- "):
            doc.add_paragraph(line[2:].strip(), style="List Bullet")
        elif line.strip() == "---":
            doc.add_page_break()
        elif in_code:
            doc.add_paragraph(line)
        else:
            doc.add_paragraph(line)

    docx_path.parent.mkdir(parents=True, exist_ok=True)
    doc.save(docx_path)
    return True
```

## `tools/docs/pages.py`

```python
from tools.docs.io_utils import read_text, code_block


def page_index():
    return """# NAS Metadata Platform Wiki

Deze wiki wordt automatisch gegenereerd door de documentatiegenerator.

## Hoofdstukken

- [Architectuur](wiki/architecture.md)
- [Scanner](wiki/scanner.md)
- [Metadata Worker](wiki/metadata-worker.md)
- [Docker](wiki/docker.md)
- [PostgreSQL](wiki/postgres.md)
- [Redis](wiki/redis.md)
- [Scripts](wiki/scripts.md)
- [Troubleshooting](wiki/troubleshooting.md)
- [Documentatiegenerator](wiki/documentation-generator.md)
- [Bronbestanden](wiki/sources.md)

## Datastroom

```text
/volume1
  |
  v
Polling Scanner
  |
  v
Redis Stream: scan_stream
  |
  v
Metadata Worker
  |
  v
PostgreSQL

Fouten -> scan_stream_dlq
```
"""


def page_architecture():
    return """# Architectuur

De NAS Metadata Stack bestaat uit een polling scanner, Redis Streams, een metadata worker en PostgreSQL.

## Ontwerpkeuzes

- Geen host watcher meer.
- Geen inotify-afhankelijkheid.
- Scanner draait in Docker.
- Redis Streams koppelen scanner en worker los van elkaar.
- Consumer Groups maken gecontroleerde verwerking mogelijk.
- PostgreSQL bewaart de permanente metadata-index.
- Heartbeats en locks voorkomen dubbele processen.
- DLQ voorkomt dat slechte events de worker blokkeren.
"""


def page_python_component(title, analysis, source_text):
    md = []
    md.append("# " + title + "\n\n")
    md.append("Bronbestand: `" + analysis["file"] + "`\n\n")

    if not analysis["exists"]:
        md.append("Bestand ontbreekt.\n")
        return "".join(md)

    md.append(f"- Regels: `{analysis['line_count']}`\n")
    md.append(f"- Functies: `{len(analysis['functions'])}`\n")
    md.append(f"- Classes: `{len(analysis['classes'])}`\n")
    md.append(f"- Imports: `{len(analysis['imports'])}`\n\n")

    if analysis.get("syntax_error"):
        md.append("## Syntaxfout\n\n")
        md.append("`" + analysis["syntax_error"] + "`\n\n")

    md.append("## Imports\n\n")
    for item in analysis["imports"]:
        md.append("- `" + item + "`\n")
    md.append("\n")

    md.append("## Constanten\n\n")
    for item in analysis["constants"]:
        md.append("- `" + item["name"] + "` op regel `" + str(item["line"]) + "`\n")
    md.append("\n")

    md.append("## Redis keys / streams\n\n")
    if analysis["redis_keys"]:
        for key in analysis["redis_keys"]:
            md.append("- `" + key + "`\n")
    else:
        md.append("_Geen Redis-keys automatisch herkend._\n")
    md.append("\n")

    md.append("## Functies\n\n")
    for fn in analysis["functions"]:
        args = ", ".join(fn["args"])
        md.append("### `" + fn["name"] + "(" + args + ")`\n\n")
        md.append("- Regel: `" + str(fn["line"]) + "`\n")
        if fn["docstring"]:
            md.append("- Docstring: " + fn["docstring"] + "\n")
        else:
            md.append("- Docstring: _niet aanwezig_\n")
        md.append("\n")

    md.append("## SQL statements\n\n")
    if analysis["sql_statements"]:
        for stmt in analysis["sql_statements"]:
            md.append("### Statement regel `" + str(stmt["line"]) + "`\n\n")
            md.append(code_block(stmt["snippet"], "sql"))
            md.append("\n")
    else:
        md.append("_Geen SQL-statements automatisch herkend._\n\n")

    md.append("## Broncode\n\n")
    md.append(code_block(source_text, "python"))

    return "".join(md)


def page_docker(compose, root):
    md = ["# Docker\n\n"]

    md.append("## Services\n\n")
    for service in compose["services"]:
        md.append("- `" + service + "`\n")

    md.append("\n## Environment variables\n\n")
    for env in compose["environment_variables"]:
        md.append("- `" + env + "`\n")

    md.append("\n## docker-compose.yml\n\n")
    md.append(code_block(read_text(root / "docker-compose.yml"), "yaml"))

    for dockerfile in ["Dockerfile.base", "Dockerfile.scanner", "Dockerfile.metadata"]:
        md.append("\n## " + dockerfile + "\n\n")
        md.append(code_block(read_text(root / dockerfile), "dockerfile"))

    return "".join(md)


def page_postgres(schema, root):
    md = ["# PostgreSQL\n\n"]

    md.append("## Tabellen\n\n")
    for table in schema["tables"]:
        md.append("- `" + table + "`\n")

    md.append("\n## Unique constraints\n\n")
    for constraint in schema["unique_constraints"]:
        md.append("- `" + constraint + "`\n")

    md.append("\n## Foreign keys\n\n")
    for fk in schema["foreign_keys"]:
        md.append("- `" + fk + "`\n")

    md.append("\n## schema.sql\n\n")
    md.append(code_block(read_text(root / "schema.sql"), "sql"))

    return "".join(md)


def page_redis():
    return """# Redis

Redis is de event- en statuslaag.

## Belangrijke keys

- `scan_stream`
- `scan_stream_dlq`
- `metadata_group`
- `scanner:lock:event`
- `metadata_worker:lock`
- heartbeat keys

## Checks

```bash
docker exec -it nas-redis-1 redis-cli XLEN scan_stream
docker exec -it nas-redis-1 redis-cli XINFO GROUPS scan_stream
docker exec -it nas-redis-1 redis-cli XINFO CONSUMERS scan_stream metadata_group
docker exec -it nas-redis-1 redis-cli XLEN scan_stream_dlq
```
"""


def page_scripts(script_analysis):
    md = ["# Scripts\n\n"]

    descriptions = {
        "rebuild": "Bouwt scanner en metadata_worker opnieuw.",
        "rebuildall": "Bouwt de volledige stack opnieuw.",
        "logs": "Toont live logs.",
        "status": "Toont status, locks, heartbeats en streaminfo.",
        "health": "Toont runtime health, Redis en heartbeat status.",
        "dlq": "Toont DLQ-informatie.",
        "cleanlocks": "Verwijdert locks handmatig.",
        "watch": "Live monitor.",
        "gendocs": "Genereert documentatie.",
    }

    core_commands = {
        "logs": "core runtime logs",
        "status": "core runtime status",
        "health": "core runtime health",
        "dlq": "core runtime dlq",
        "cleanlocks": "core runtime cleanlocks",
        "watch": "core runtime watch",
        "gendocs": "core docs generate",
    }

    for name, info in script_analysis.items():
        script_name = name.split("/")[-1]
        md.append("## `" + name + "`\n\n")
        md.append(descriptions.get(script_name, "Script") + "\n\n")
        if script_name in core_commands:
            md.append("- CORE command: `" + core_commands[script_name] + "`\n")
        md.append("- Bestaat: `" + str(info["exists"]) + "`\n")
        md.append("- Regels: `" + str(info["line_count"]) + "`\n")
        md.append("- Gebruikt docker compose: `" + str(info["uses_docker_compose"]) + "`\n")
        md.append("- Gebruikt Redis: `" + str(info["uses_redis"]) + "`\n\n")
        if info["content"]:
            md.append(code_block(info["content"], "bash"))
        md.append("\n")

    return "".join(md)


def page_troubleshooting():
    return """# Troubleshooting

Alle runtime checks lopen via de CORE CLI. Run deze commands op de NAS in `/volume1/docker/nas-stack`, of via de Windows wrapper vanuit de repository.

## Worker is unhealthy

```bash
core runtime health
```

Voor detailinformatie:

```bash
docker inspect nas-metadata_worker-1 --format '{{json .State.Health}}'
```

Controleer of de healthcheck `python3` gebruikt.

## Scanner doet niets

```bash
core runtime logs
core runtime status
```

## Realtime watcher ontbreekt of is unhealthy

```bash
core runtime health
core runtime status
/usr/local/bin/docker compose logs --tail=200 watcher
```

Controleer in `core runtime status` de watcher-heartbeat, `watcher:last_event` en `scanner:dirty_roots`. Een ontbrekende heartbeat betekent dat de watcher niet actief is of Redis niet kan bereiken. Herstel eerst de watcher en laat de dirty-root reconciliation afronden voordat u een opschoning start.

## Container Manager toont een ID-prefix

Controleer de echte Dockernaam:

```bash
docker ps --format '{{.Names}}'
```

Als Docker `nas-scanner-1`, `nas-metadata_worker-1` en `nas-watcher-1` toont, is alleen de Synology-interface uit sync. Sluit Container Manager voordat containers met Compose worden gerecreëerd en open de GUI pas nadat de containers stabiel en gezond zijn.

## Worker zegt dat er al een worker draait

Controleer locks en heartbeats:

```bash
core runtime status
```

## DLQ groeit

```bash
core runtime dlq
```

## Noodoplossing locks

```bash
core runtime cleanlocks
```

## Live monitor

```bash
core runtime watch
```

## Windows wrapper

```powershell
.\\tools\\windows\\core.ps1 runtime status
.\\tools\\windows\\core.ps1 runtime dlq
```
"""


def page_documentation_generator(generator_analysis):
    md = ["# Documentatiegenerator\n\n"]

    md.append("De documentatiegenerator maakt documentatie op basis van bronbestanden.\n\n")

    md.append("## Output\n\n")
    md.append("- `docs/DOCUMENTATIE.md`\n")
    md.append("- `docs/DOCUMENTATIE.docx`\n")
    md.append("- `docs/wiki/*.md`\n")
    md.append("- `docs/generated/*.json`\n\n")

    md.append("## Self-documentation\n\n")
    md.append("De generator analyseert ook zichzelf. Daardoor verschijnt nieuwe generatorcode automatisch in deze documentatie.\n\n")

    md.append("## Functies\n\n")
    for fn in generator_analysis["functions"]:
        args = ", ".join(fn["args"])
        md.append("- `" + fn["name"] + "(" + args + ")` op regel `" + str(fn["line"]) + "`\n")

    return "".join(md)


def page_sources(root, files):
    md = ["# Bronbestanden\n\n"]

    for file in files:
        text = read_text(root / file)
        md.append("## `" + file + "`\n\n")
        if not text:
            md.append("_Bestand ontbreekt of is leeg._\n\n")
            continue

        lang = ""
        if file.endswith(".py"):
            lang = "python"
        elif file.endswith(".yml") or file.endswith(".yaml"):
            lang = "yaml"
        elif file.endswith(".sql"):
            lang = "sql"
        elif "Dockerfile" in file:
            lang = "dockerfile"
        else:
            lang = "bash"

        md.append(code_block(text, lang))
        md.append("\n")

    return "".join(md)
```

## `tools/docs/generate_docs.py`

```python
#!/usr/bin/env python3
import sys
from pathlib import Path

CURRENT = Path(__file__).resolve()
ROOT = CURRENT.parents[2]
sys.path.insert(0, str(ROOT))

from tools.docs.config import (
    ROOT as STACK_ROOT,
    DOCS_DIR,
    WIKI_DIR,
    GENERATED_DIR,
    PYTHON_FILES,
    CONFIG_FILES,
    SCRIPT_FILES,
    ALL_SOURCE_FILES,
)
from tools.docs.analyze_standards import analyze_standards
from tools.docs.io_utils import write_text, write_json, read_text
from tools.docs.analyze_python import analyze_python_files
from tools.docs.analyze_project import analyze_compose, analyze_schema, analyze_scripts, analyze_sources
from tools.docs.analyze_core import analyze_core
from tools.docs.analyze_rfc import analyze_rfc
from tools.docs.analyze_database_views import analyze_database_views
from tools.docs.pages import (
    page_index,
    page_architecture,
    page_python_component,
    page_docker,
    page_postgres,
    page_redis,
    page_scripts,
    page_troubleshooting,
    page_documentation_generator,
    page_sources,
)
from tools.docs.pages_core import page_core, page_rfc, page_database_views, page_standards
from tools.docs.render_markdown import render_main_document
from tools.docs.render_docx import render_docx

def build_analysis():
    python_analysis = analyze_python_files(STACK_ROOT, PYTHON_FILES)
    compose_analysis = analyze_compose(STACK_ROOT)
    schema_analysis = analyze_schema(STACK_ROOT)
    script_analysis = analyze_scripts(STACK_ROOT, SCRIPT_FILES)
    source_analysis = analyze_sources(STACK_ROOT, ALL_SOURCE_FILES)
    core_analysis = analyze_core(STACK_ROOT)
    rfc_analysis = analyze_rfc(STACK_ROOT)
    database_views_analysis = analyze_database_views(STACK_ROOT)
    standards_analysis = analyze_standards(STACK_ROOT)

    return {
        "python": python_analysis,
        "compose": compose_analysis,
        "schema": schema_analysis,
        "scripts": script_analysis,
        "sources": source_analysis,
        "core": core_analysis,
        "rfc": rfc_analysis,
        "database_views": database_views_analysis,
        "standards": standards_analysis,
    }


def render_json_outputs(analysis):
    write_json(GENERATED_DIR / "python_analysis.json", analysis["python"])
    write_json(GENERATED_DIR / "docker_analysis.json", analysis["compose"])
    write_json(GENERATED_DIR / "sql_analysis.json", analysis["schema"])
    write_json(GENERATED_DIR / "scripts_analysis.json", analysis["scripts"])
    write_json(GENERATED_DIR / "project_index.json", analysis["sources"])
    write_json(GENERATED_DIR / "core_analysis.json", analysis["core"])
    write_json(GENERATED_DIR / "rfc_analysis.json", analysis["rfc"])
    write_json(GENERATED_DIR / "database_views_analysis.json", analysis["database_views"])
    write_json(GENERATED_DIR / "standards_analysis.json", analysis["standards"])


def render_wiki_pages(analysis):
    write_text(WIKI_DIR / "index.md", page_index())
    write_text(WIKI_DIR / "architecture.md", page_architecture())
    write_text(WIKI_DIR / "core.md", page_core(analysis["core"]))
    write_text(WIKI_DIR / "rfc.md", page_rfc(analysis["rfc"]))
    write_text(WIKI_DIR / "database-views.md", page_database_views(analysis["database_views"]))
    write_text(WIKI_DIR / "standards.md", page_standards(analysis["standards"]))

    write_text(WIKI_DIR / "scanner.md", page_python_component(
        "Scanner",
        analysis["python"]["scanner.py"],
        read_text(STACK_ROOT / "scanner.py"),
    ))

    write_text(WIKI_DIR / "metadata-worker.md", page_python_component(
        "Metadata Worker",
        analysis["python"]["metadata_worker.py"],
        read_text(STACK_ROOT / "metadata_worker.py"),
    ))

    write_text(WIKI_DIR / "docker.md", page_docker(analysis["compose"], STACK_ROOT))
    write_text(WIKI_DIR / "postgres.md", page_postgres(analysis["schema"], STACK_ROOT))
    write_text(WIKI_DIR / "redis.md", page_redis())
    write_text(WIKI_DIR / "scripts.md", page_scripts(analysis["scripts"]))
    write_text(WIKI_DIR / "troubleshooting.md", page_troubleshooting())

    write_text(WIKI_DIR / "documentation-generator.md", page_documentation_generator(
        analysis["python"]["tools/docs/generate_docs.py"]
    ))

    write_text(WIKI_DIR / "sources.md", page_sources(STACK_ROOT, ALL_SOURCE_FILES))

def main():
    DOCS_DIR.mkdir(exist_ok=True)
    WIKI_DIR.mkdir(exist_ok=True)
    GENERATED_DIR.mkdir(exist_ok=True)

    analysis = build_analysis()

    render_json_outputs(analysis)
    render_wiki_pages(analysis)
    render_main_document(DOCS_DIR, WIKI_DIR)

    docx_done = render_docx(DOCS_DIR / "DOCUMENTATIE.md", DOCS_DIR / "DOCUMENTATIE.docx")

    print("Documentatiegenerator CORE klaar.")
    print("- docs/DOCUMENTATIE.md")

    if docx_done:
        print("- docs/DOCUMENTATIE.docx")
    else:
        print("- DOCX overgeslagen: python-docx ontbreekt")

    print("- docs/wiki/")
    print("- docs/generated/")


if __name__ == "__main__":
    main()
```

## `docker-compose.yml`

```yaml
name: nas
services:
  redis:
    image: redis:7-alpine
    restart: unless-stopped
    command: ["redis-server", "--appendonly", "yes", "--maxmemory-policy", "noeviction"]
    volumes: [redis_data:/data]
    healthcheck: { test: ["CMD", "redis-cli", "ping"], interval: 10s, timeout: 5s, retries: 3 }

  scanner:
    build: { context: ., dockerfile: Dockerfile.scanner }
    restart: unless-stopped
    depends_on: { redis: { condition: service_healthy } }
    volumes: ["/volume1:/volume1:ro"]
    environment:
      - DB_HOST=${DB_HOST}
      - DB_PORT=${DB_PORT}
      - DB_USER=${DB_USER}
      - DB_PASS=${DB_PASS}
      - DB_NAME=${DB_NAME}
      - REDIS_HOST=redis
      - SCAN_ROOT=${SCAN_ROOT:-/volume1}
      - SCAN_INTERVAL=${SCAN_INTERVAL:-600}
      - FULL_SCAN_INTERVAL=${FULL_SCAN_INTERVAL:-3600}
      - MISSING_SCAN_THRESHOLD=${MISSING_SCAN_THRESHOLD:-2}

  watcher:
    build: { context: ., dockerfile: Dockerfile.watcher }
    restart: unless-stopped
    depends_on: { redis: { condition: service_healthy } }
    volumes: ["/volume1:/volume1:ro"]
    environment:
      - REDIS_HOST=redis
      - SCAN_ROOT=${SCAN_ROOT:-/volume1}
      - WATCH_ROOTS=${WATCH_ROOTS:-/volume1/data}
      - STREAM_KEY=${REALTIME_STREAM_KEY:-scan_stream_realtime}
      - WATCHER_DEBOUNCE_SECONDS=${WATCHER_DEBOUNCE_SECONDS:-2}
    healthcheck:
      test: ["CMD", "python3", "-c", "import redis; r=redis.Redis(host='redis', decode_responses=True); assert r.get('watcher:heartbeat')"]
      interval: 30s
      timeout: 5s
      retries: 3

  metadata_worker:
    build: { context: ., dockerfile: Dockerfile.metadata }
    restart: unless-stopped
    depends_on: { redis: { condition: service_healthy } }
    volumes: ["/volume1:/volume1:ro"]
    environment:
      - DB_HOST=${DB_HOST}
      - DB_PORT=${DB_PORT}
      - DB_USER=${DB_USER}
      - DB_PASS=${DB_PASS}
      - DB_NAME=${DB_NAME}
      - REDIS_HOST=redis
      - REALTIME_STREAM_KEY=${REALTIME_STREAM_KEY:-scan_stream_realtime}
      - FORCE_FULL_METADATA=${FORCE_FULL_METADATA:-false}

    healthcheck:
      test: ["CMD", "python3", "-c", "import redis; r=redis.Redis(host='redis', decode_responses=True); r.ping()"]
      interval: 30s
      timeout: 5s
      retries: 3

volumes:
  redis_data:
```

## `Dockerfile.base`

```dockerfile
FROM debian:bookworm-slim

ENV TZ=Europe/Amsterdam
ENV DEBIAN_FRONTEND=noninteractive

# OS dependencies (inotify + ffprobe zijn hier al inbegrepen)
RUN apt-get update && apt-get install -y \
    curl wget ca-certificates bash tzdata \
    python3 python3-pip \
    libmagic1 libvips42 ffmpeg inotify-tools \
    && rm -rf /var/lib/apt/lists/*

# Python dependencies
RUN pip3 install --break-system-packages redis psycopg2-binary xxhash python-magic pyvips

WORKDIR /app
```

## `Dockerfile.scanner`

```dockerfile
FROM nas-base:v1
WORKDIR /app
COPY scanner.py .
CMD ["python3", "scanner.py"]
```

## `Dockerfile.metadata`

```dockerfile
FROM nas-base:v1
WORKDIR /app
COPY metadata_worker.py .
CMD ["python3", "metadata_worker.py"]
```

## `schema.sql`

```sql
--
-- PostgreSQL database dump
--

\restrict KM5I8YsUK7CLbO0daSZ9hUdbrsZeFBT9FWSYUKVNueqkKGoLNR6hGNMoNadS5g0

-- Dumped from database version 16.14 (Debian 16.14-1.pgdg12+1)
-- Dumped by pg_dump version 16.14 (Debian 16.14-1.pgdg12+1)

SET statement_timeout = 0;
SET lock_timeout = 0;
SET idle_in_transaction_session_timeout = 0;
SET client_encoding = 'UTF8';
SET standard_conforming_strings = on;
SELECT pg_catalog.set_config('search_path', '', false);
SET check_function_bodies = false;
SET xmloption = content;
SET client_min_messages = warning;
SET row_security = off;

--
-- Name: vector; Type: EXTENSION; Schema: -; Owner: -
--

CREATE EXTENSION IF NOT EXISTS vector WITH SCHEMA public;


--
-- Name: EXTENSION vector; Type: COMMENT; Schema: -; Owner: 
--

COMMENT ON EXTENSION vector IS 'vector data type and ivfflat and hnsw access methods';


--
-- Name: cleanup_all_execute(); Type: PROCEDURE; Schema: public; Owner: hugo
--

CREATE PROCEDURE public.cleanup_all_execute()
    LANGUAGE plpgsql
    AS $_$
DECLARE
    dir_folders INT := 0;
    dir_files INT := 0;
    dir_meta INT := 0;
    dir_emb INT := 0;
    dir_ai INT := 0;

    file_files INT := 0;
    file_meta INT := 0;
    file_emb INT := 0;
    file_ai INT := 0;

    orphan_metadata INT := 0;
    orphan_embeddings INT := 0;
    orphan_ai INT := 0;
    orphan_files INT := 0;
    orphan_folders INT := 0;
BEGIN
    RAISE NOTICE '=== CLEANUP START ===';

    --------------------------------------------------------------------
    -- 1. SYSTEM FOLDERS (@eaDir, @tmp, @appstore, @*)
    --------------------------------------------------------------------
    WITH excluded_folders AS (
        SELECT id FROM folders
        WHERE path LIKE '%/@eaDir%'
           OR path LIKE '%/@appstore%'
           OR path LIKE '%/@tmp%'
           OR path LIKE '%/@%'
    ),
    files_to_delete AS (
        SELECT id AS file_id FROM files
        WHERE folder_id IN (SELECT id FROM excluded_folders)
    )
    SELECT
        (SELECT COUNT(*) FROM excluded_folders),
        (SELECT COUNT(*) FROM files_to_delete),
        (SELECT COUNT(*) FROM metadata WHERE file_id IN (SELECT file_id FROM files_to_delete)),
        (SELECT COUNT(*) FROM embeddings WHERE file_id IN (SELECT file_id FROM files_to_delete)),
        (SELECT COUNT(*) FROM ai_output WHERE file_id IN (SELECT file_id FROM files_to_delete))
    INTO dir_folders, dir_files, dir_meta, dir_emb, dir_ai;

    RAISE NOTICE 'DIRS → removing % folders, % files, % metadata, % embeddings, % ai_output',
        dir_folders, dir_files, dir_meta, dir_emb, dir_ai;

    -- DELETE using fresh CTE
    WITH files_to_delete AS (
        SELECT id AS file_id FROM files
        WHERE folder_id IN (
            SELECT id FROM folders
            WHERE path LIKE '%/@eaDir%'
               OR path LIKE '%/@appstore%'
               OR path LIKE '%/@tmp%'
               OR path LIKE '%/@%'
        )
    )
    DELETE FROM metadata WHERE file_id IN (SELECT file_id FROM files_to_delete);

    WITH files_to_delete AS (
        SELECT id AS file_id FROM files
        WHERE folder_id IN (
            SELECT id FROM folders
            WHERE path LIKE '%/@eaDir%'
               OR path LIKE '%/@appstore%'
               OR path LIKE '%/@tmp%'
               OR path LIKE '%/@%'
        )
    )
    DELETE FROM embeddings WHERE file_id IN (SELECT file_id FROM files_to_delete);

    WITH files_to_delete AS (
        SELECT id AS file_id FROM files
        WHERE folder_id IN (
            SELECT id FROM folders
            WHERE path LIKE '%/@eaDir%'
               OR path LIKE '%/@appstore%'
               OR path LIKE '%/@tmp%'
               OR path LIKE '%/@%'
        )
    )
    DELETE FROM ai_output WHERE file_id IN (SELECT file_id FROM files_to_delete);

    WITH files_to_delete AS (
        SELECT id AS file_id FROM files
        WHERE folder_id IN (
            SELECT id FROM folders
            WHERE path LIKE '%/@eaDir%'
               OR path LIKE '%/@appstore%'
               OR path LIKE '%/@tmp%'
               OR path LIKE '%/@%'
        )
    )
    DELETE FROM files WHERE id IN (SELECT file_id FROM files_to_delete);

    DELETE FROM folders
    WHERE path LIKE '%/@eaDir%'
       OR path LIKE '%/@appstore%'
       OR path LIKE '%/@tmp%'
       OR path LIKE '%/@%';

    --------------------------------------------------------------------
    -- 2. SYSTEM FILES (~$, ._, .DS_Store, Thumbs.db, *.tmp, *.swp, *.bak)
    --------------------------------------------------------------------
    WITH excluded_files AS (
        SELECT id AS file_id FROM files
        WHERE filename LIKE '~$%'
           OR filename LIKE '._%'
           OR filename = '.DS_Store'
           OR filename = 'Thumbs.db'
           OR filename LIKE '%.tmp'
           OR filename LIKE '%.swp'
           OR filename LIKE '%.bak'
    )
    SELECT
        (SELECT COUNT(*) FROM excluded_files),
        (SELECT COUNT(*) FROM metadata WHERE file_id IN (SELECT file_id FROM excluded_files)),
        (SELECT COUNT(*) FROM embeddings WHERE file_id IN (SELECT file_id FROM excluded_files)),
        (SELECT COUNT(*) FROM ai_output WHERE file_id IN (SELECT file_id FROM excluded_files))
    INTO file_files, file_meta, file_emb, file_ai;

    RAISE NOTICE 'FILES → removing % files, % metadata, % embeddings, % ai_output',
        file_files, file_meta, file_emb, file_ai;

    -- DELETE using fresh CTE
    WITH excluded_files AS (
        SELECT id AS file_id FROM files
        WHERE filename LIKE '~$%'
           OR filename LIKE '._%'
           OR filename = '.DS_Store'
           OR filename = 'Thumbs.db'
           OR filename LIKE '%.tmp'
           OR filename LIKE '%.swp'
           OR filename LIKE '%.bak'
    )
    DELETE FROM metadata WHERE file_id IN (SELECT file_id FROM excluded_files);

    WITH excluded_files AS (
        SELECT id AS file_id FROM files
        WHERE filename LIKE '~$%'
           OR filename LIKE '._%'
           OR filename = '.DS_Store'
           OR filename = 'Thumbs.db'
           OR filename LIKE '%.tmp'
           OR filename LIKE '%.swp'
           OR filename LIKE '%.bak'
    )
    DELETE FROM embeddings WHERE file_id IN (SELECT file_id FROM excluded_files);

    WITH excluded_files AS (
        SELECT id AS file_id FROM files
        WHERE filename LIKE '~$%'
           OR filename LIKE '._%'
           OR filename = '.DS_Store'
           OR filename = 'Thumbs.db'
           OR filename LIKE '%.tmp'
           OR filename LIKE '%.swp'
           OR filename LIKE '%.bak'
    )
    DELETE FROM ai_output WHERE file_id IN (SELECT file_id FROM excluded_files);

    WITH excluded_files AS (
        SELECT id AS file_id FROM files
        WHERE filename LIKE '~$%'
           OR filename LIKE '._%'
           OR filename = '.DS_Store'
           OR filename = 'Thumbs.db'
           OR filename LIKE '%.tmp'
           OR filename LIKE '%.swp'
           OR filename LIKE '%.bak'
    )
    DELETE FROM files WHERE id IN (SELECT file_id FROM excluded_files);

    --------------------------------------------------------------------
    -- 3. ORPHANS (metadata, embeddings, ai_output, files, folders)
    --------------------------------------------------------------------
    SELECT COUNT(*) INTO orphan_metadata
    FROM metadata m LEFT JOIN files f ON f.id = m.file_id
    WHERE f.id IS NULL;

    RAISE NOTICE 'ORPHANS → removing % orphaned metadata', orphan_metadata;

    DELETE FROM metadata m
    WHERE NOT EXISTS (SELECT 1 FROM files f WHERE f.id = m.file_id);

    SELECT COUNT(*) INTO orphan_embeddings
    FROM embeddings e LEFT JOIN files f ON f.id = e.file_id
    WHERE f.id IS NULL;

    RAISE NOTICE 'ORPHANS → removing % orphaned embeddings', orphan_embeddings;

    DELETE FROM embeddings e
    WHERE NOT EXISTS (SELECT 1 FROM files f WHERE f.id = e.file_id);

    SELECT COUNT(*) INTO orphan_ai
    FROM ai_output a LEFT JOIN files f ON f.id = a.file_id
    WHERE f.id IS NULL;

    RAISE NOTICE 'ORPHANS → removing % orphaned ai_output', orphan_ai;

    DELETE FROM ai_output a
    WHERE NOT EXISTS (SELECT 1 FROM files f WHERE f.id = a.file_id);

    SELECT COUNT(*) INTO orphan_files
    FROM files fl LEFT JOIN folders fo ON fo.id = fl.folder_id
    WHERE fo.id IS NULL;

    RAISE NOTICE 'ORPHANS → removing % orphaned files', orphan_files;

    DELETE FROM files fl
    WHERE NOT EXISTS (SELECT 1 FROM folders fo WHERE fo.id = fl.folder_id);

    SELECT COUNT(*) INTO orphan_folders
    FROM folders f LEFT JOIN folders p ON p.id = f.parent_id
    WHERE f.parent_id IS NOT NULL AND p.id IS NULL;

    RAISE NOTICE 'ORPHANS → removing % orphaned folders', orphan_folders;

    DELETE FROM folders f
    WHERE f.parent_id IS NOT NULL
      AND NOT EXISTS (SELECT 1 FROM folders p WHERE p.id = f.parent_id);

    --------------------------------------------------------------------
    RAISE NOTICE '=== CLEANUP COMPLETE ===';
END;
$_$;


ALTER PROCEDURE public.cleanup_all_execute() OWNER TO hugo;

--
-- Name: create_scan_session(text); Type: FUNCTION; Schema: public; Owner: hugo
--

CREATE FUNCTION public.create_scan_session(scan_type text) RETURNS uuid
    LANGUAGE plpgsql
    AS $$
DECLARE
    sid UUID := gen_random_uuid();
BEGIN
    INSERT INTO scan_sessions(id, type)
    VALUES (sid, scan_type);
    RETURN sid;
END;
$$;


ALTER FUNCTION public.create_scan_session(scan_type text) OWNER TO hugo;

--
-- Name: finish_scan_session(uuid); Type: FUNCTION; Schema: public; Owner: hugo
--

CREATE FUNCTION public.finish_scan_session(sid uuid) RETURNS void
    LANGUAGE plpgsql
    AS $$
BEGIN
    UPDATE scan_sessions
    SET finished_at = NOW(),
        status = 'done'
    WHERE id = sid;
END;
$$;


ALTER FUNCTION public.finish_scan_session(sid uuid) OWNER TO hugo;

--
-- Name: increment_files_discovered(uuid, integer); Type: FUNCTION; Schema: public; Owner: hugo
--

CREATE FUNCTION public.increment_files_discovered(sid uuid, cnt integer) RETURNS void
    LANGUAGE plpgsql
    AS $$
BEGIN
    UPDATE scan_sessions
    SET files_discovered = files_discovered + cnt
    WHERE id = sid;
END;
$$;


ALTER FUNCTION public.increment_files_discovered(sid uuid, cnt integer) OWNER TO hugo;

--
-- Name: increment_jobs_enqueued(uuid, integer); Type: FUNCTION; Schema: public; Owner: hugo
--

CREATE FUNCTION public.increment_jobs_enqueued(sid uuid, cnt integer) RETURNS void
    LANGUAGE plpgsql
    AS $$
BEGIN
    UPDATE scan_sessions
    SET jobs_enqueued = jobs_enqueued + cnt
    WHERE id = sid;
END;
$$;


ALTER FUNCTION public.increment_jobs_enqueued(sid uuid, cnt integer) OWNER TO hugo;

--
-- Name: increment_jobs_processed(uuid); Type: FUNCTION; Schema: public; Owner: hugo
--

CREATE FUNCTION public.increment_jobs_processed(sid uuid) RETURNS void
    LANGUAGE plpgsql
    AS $$
BEGIN
    UPDATE scan_sessions
    SET jobs_processed = jobs_processed + 1
    WHERE id = sid;
END;
$$;


ALTER FUNCTION public.increment_jobs_processed(sid uuid) OWNER TO hugo;

--
-- Name: is_scan_complete(uuid); Type: FUNCTION; Schema: public; Owner: hugo
--

CREATE FUNCTION public.is_scan_complete(sid uuid) RETURNS boolean
    LANGUAGE plpgsql
    AS $$
DECLARE done BOOLEAN;
BEGIN
    SELECT (status='done' AND jobs_enqueued>0 AND jobs_processed>=jobs_enqueued)
    INTO done
    FROM scan_sessions WHERE id=sid;
    RETURN COALESCE(done, FALSE);
END;
$$;


ALTER FUNCTION public.is_scan_complete(sid uuid) OWNER TO hugo;

SET default_tablespace = '';

SET default_table_access_method = heap;

--
-- Name: ai_output; Type: TABLE; Schema: public; Owner: hugo
--

CREATE TABLE public.ai_output (
    id integer NOT NULL,
    file_id integer,
    summary text,
    tags text[],
    categories text[],
    embedding public.vector(1536),
    created_at timestamp without time zone DEFAULT now()
);


ALTER TABLE public.ai_output OWNER TO hugo;

--
-- Name: ai_output_id_seq; Type: SEQUENCE; Schema: public; Owner: hugo
--

CREATE SEQUENCE public.ai_output_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.ai_output_id_seq OWNER TO hugo;

--
-- Name: ai_output_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: hugo
--

ALTER SEQUENCE public.ai_output_id_seq OWNED BY public.ai_output.id;


--
-- Name: embeddings; Type: TABLE; Schema: public; Owner: hugo
--

CREATE TABLE public.embeddings (
    id integer NOT NULL,
    file_id integer NOT NULL,
    embedding public.vector(1536),
    created_at timestamp without time zone DEFAULT now()
);


ALTER TABLE public.embeddings OWNER TO hugo;

--
-- Name: embeddings_id_seq; Type: SEQUENCE; Schema: public; Owner: hugo
--

CREATE SEQUENCE public.embeddings_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.embeddings_id_seq OWNER TO hugo;

--
-- Name: embeddings_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: hugo
--

ALTER SEQUENCE public.embeddings_id_seq OWNED BY public.embeddings.id;


--
-- Name: files; Type: TABLE; Schema: public; Owner: hugo
--

CREATE TABLE public.files (
    id integer NOT NULL,
    folder_id integer NOT NULL,
    filename text NOT NULL,
    extension text,
    size_bytes bigint,
    created_at timestamp without time zone DEFAULT now(),
    updated_at timestamp without time zone DEFAULT now(),
    modified_at_fs bigint,
    inode bigint,
    path text,
    mime_type text,
    deleted_at timestamp without time zone,
    hash_content text,
    hash_path text,
    source text,
    last_mutation_type text DEFAULT 'UNKNOWN'::text NOT NULL,
    CONSTRAINT files_last_mutation_type_check CHECK ((last_mutation_type = ANY (ARRAY['UNKNOWN'::text, 'CREATED'::text, 'MODIFIED'::text, 'RENAMED'::text, 'MOVED'::text, 'RESTORED'::text, 'DELETED'::text])))
);


ALTER TABLE public.files OWNER TO hugo;

--
-- Name: files_id_seq; Type: SEQUENCE; Schema: public; Owner: hugo
--

CREATE SEQUENCE public.files_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.files_id_seq OWNER TO hugo;

--
-- Name: files_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: hugo
--

ALTER SEQUENCE public.files_id_seq OWNED BY public.files.id;


--
-- Name: folders; Type: TABLE; Schema: public; Owner: hugo
--

CREATE TABLE public.folders (
    id integer NOT NULL,
    path text NOT NULL,
    parent_id integer,
    created_at timestamp without time zone DEFAULT now()
);


ALTER TABLE public.folders OWNER TO hugo;

--
-- Name: folders_id_seq; Type: SEQUENCE; Schema: public; Owner: hugo
--

CREATE SEQUENCE public.folders_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.folders_id_seq OWNER TO hugo;

--
-- Name: folders_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: hugo
--

ALTER SEQUENCE public.folders_id_seq OWNED BY public.folders.id;


--
-- Name: metadata; Type: TABLE; Schema: public; Owner: hugo
--

CREATE TABLE public.metadata (
    id integer NOT NULL,
    file_id bigint NOT NULL,
    created_at timestamp without time zone DEFAULT now(),
    width integer,
    height integer,
    duration double precision,
    missing boolean DEFAULT false
);


ALTER TABLE public.metadata OWNER TO hugo;

--
-- Name: metadata_id_seq; Type: SEQUENCE; Schema: public; Owner: hugo
--

CREATE SEQUENCE public.metadata_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.metadata_id_seq OWNER TO hugo;

--
-- Name: metadata_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: hugo
--

ALTER SEQUENCE public.metadata_id_seq OWNED BY public.metadata.id;


--
-- Name: scan_sessions; Type: TABLE; Schema: public; Owner: hugo
--

CREATE TABLE public.scan_sessions (
    id uuid NOT NULL,
    type text NOT NULL,
    started_at timestamp without time zone DEFAULT now() NOT NULL,
    finished_at timestamp without time zone,
    status text DEFAULT 'running'::text NOT NULL,
    files_discovered integer DEFAULT 0 NOT NULL,
    jobs_enqueued integer DEFAULT 0 NOT NULL,
    jobs_processed integer DEFAULT 0 NOT NULL,
    CONSTRAINT scan_sessions_status_check CHECK ((status = ANY (ARRAY['running'::text, 'finished'::text, 'failed'::text, 'aborted'::text]))),
    CONSTRAINT scan_sessions_type_check CHECK ((type = ANY (ARRAY['full'::text, 'interval'::text, 'watcher'::text])))
);


ALTER TABLE public.scan_sessions OWNER TO hugo;

--
-- Name: v_files_last_hour; Type: VIEW; Schema: public; Owner: hugo
--

CREATE VIEW public.v_files_last_hour AS
 SELECT count(*) AS files_last_hour
   FROM public.files
  WHERE (updated_at >= ((now() AT TIME ZONE 'UTC'::text) - '01:00:00'::interval));


ALTER VIEW public.v_files_last_hour OWNER TO hugo;

--
-- Name: v_files_over_time_extended; Type: VIEW; Schema: public; Owner: hugo
--

CREATE VIEW public.v_files_over_time_extended AS
 WITH per_day AS (
         SELECT date(files.created_at) AS file_date,
            count(*) AS files_created,
            ((count(*))::numeric / 24.0) AS avg_files_per_hour_that_day
           FROM public.files
          GROUP BY (date(files.created_at))
          ORDER BY (date(files.created_at))
        ), global_stats AS (
         SELECT count(*) AS total_files,
            min(files.created_at) AS first_file,
            max(files.created_at) AS last_file,
            (EXTRACT(epoch FROM (max(files.created_at) - min(files.created_at))) / (3600)::numeric) AS hours_span
           FROM public.files
        )
 SELECT p.file_date,
    p.files_created,
    p.avg_files_per_hour_that_day,
    g.total_files,
    g.first_file,
    g.last_file,
    g.hours_span,
        CASE
            WHEN (g.hours_span < (1)::numeric) THEN NULL::numeric
            ELSE ((g.total_files)::numeric / g.hours_span)
        END AS avg_files_per_hour_global
   FROM (per_day p
     CROSS JOIN global_stats g)
  ORDER BY p.file_date;


ALTER VIEW public.v_files_over_time_extended OWNER TO hugo;

--
-- Name: v_scan_status; Type: VIEW; Schema: public; Owner: hugo
--

CREATE VIEW public.v_scan_status AS
 SELECT id,
    type,
    status,
    started_at,
    finished_at,
    files_discovered,
    jobs_enqueued,
    jobs_processed,
    round((((jobs_processed)::numeric / (NULLIF(jobs_enqueued, 0))::numeric) * (100)::numeric), 2) AS progress_percent
   FROM public.scan_sessions
  ORDER BY started_at DESC;


ALTER VIEW public.v_scan_status OWNER TO hugo;

--
-- Name: v_test_documents; Type: VIEW; Schema: public; Owner: hugo
--

CREATE VIEW public.v_test_documents AS
 SELECT f.id,
    f.folder_id,
    f.filename,
    f.extension,
    f.size_bytes,
    f.created_at,
    f.updated_at,
    f.modified_at_fs,
    f.inode,
    f.hash_path AS xxhash,
    fo.path
   FROM (public.files f
     JOIN public.folders fo ON ((fo.id = f.folder_id)))
  WHERE (fo.path ~~ '/volume1/backup/NITRO/D/data/hugo/Documents%'::text);


ALTER VIEW public.v_test_documents OWNER TO hugo;

--
-- Name: ai_output id; Type: DEFAULT; Schema: public; Owner: hugo
--

ALTER TABLE ONLY public.ai_output ALTER COLUMN id SET DEFAULT nextval('public.ai_output_id_seq'::regclass);


--
-- Name: embeddings id; Type: DEFAULT; Schema: public; Owner: hugo
--

ALTER TABLE ONLY public.embeddings ALTER COLUMN id SET DEFAULT nextval('public.embeddings_id_seq'::regclass);


--
-- Name: files id; Type: DEFAULT; Schema: public; Owner: hugo
--

ALTER TABLE ONLY public.files ALTER COLUMN id SET DEFAULT nextval('public.files_id_seq'::regclass);


--
-- Name: folders id; Type: DEFAULT; Schema: public; Owner: hugo
--

ALTER TABLE ONLY public.folders ALTER COLUMN id SET DEFAULT nextval('public.folders_id_seq'::regclass);


--
-- Name: metadata id; Type: DEFAULT; Schema: public; Owner: hugo
--

ALTER TABLE ONLY public.metadata ALTER COLUMN id SET DEFAULT nextval('public.metadata_id_seq'::regclass);


--
-- Name: ai_output ai_output_pkey; Type: CONSTRAINT; Schema: public; Owner: hugo
--

ALTER TABLE ONLY public.ai_output
    ADD CONSTRAINT ai_output_pkey PRIMARY KEY (id);


--
-- Name: embeddings embeddings_pkey; Type: CONSTRAINT; Schema: public; Owner: hugo
--

ALTER TABLE ONLY public.embeddings
    ADD CONSTRAINT embeddings_pkey PRIMARY KEY (id);


--
-- Name: files files_path_unique; Type: CONSTRAINT; Schema: public; Owner: hugo
--

ALTER TABLE ONLY public.files
    ADD CONSTRAINT files_path_unique UNIQUE (path);


--
-- Name: files files_pkey; Type: CONSTRAINT; Schema: public; Owner: hugo
--

ALTER TABLE ONLY public.files
    ADD CONSTRAINT files_pkey PRIMARY KEY (id);


--
-- Name: folders folders_path_key; Type: CONSTRAINT; Schema: public; Owner: hugo
--

ALTER TABLE ONLY public.folders
    ADD CONSTRAINT folders_path_key UNIQUE (path);


--
-- Name: folders folders_pkey; Type: CONSTRAINT; Schema: public; Owner: hugo
--

ALTER TABLE ONLY public.folders
    ADD CONSTRAINT folders_pkey PRIMARY KEY (id);


--
-- Name: metadata metadata_file_id_unique; Type: CONSTRAINT; Schema: public; Owner: hugo
--

ALTER TABLE ONLY public.metadata
    ADD CONSTRAINT metadata_file_id_unique UNIQUE (file_id);


--
-- Name: metadata metadata_pkey; Type: CONSTRAINT; Schema: public; Owner: hugo
--

ALTER TABLE ONLY public.metadata
    ADD CONSTRAINT metadata_pkey PRIMARY KEY (id);


--
-- Name: scan_sessions scan_sessions_pkey; Type: CONSTRAINT; Schema: public; Owner: hugo
--

ALTER TABLE ONLY public.scan_sessions
    ADD CONSTRAINT scan_sessions_pkey PRIMARY KEY (id);


--
-- Name: idx_files_folder_filename; Type: INDEX; Schema: public; Owner: hugo
--

CREATE INDEX idx_files_folder_filename ON public.files USING btree (folder_id, filename);


--
-- Name: idx_files_inode_mtime; Type: INDEX; Schema: public; Owner: hugo
--

CREATE INDEX idx_files_inode_mtime ON public.files USING btree (inode, modified_at_fs);


--
-- Name: idx_folders_parent_id; Type: INDEX; Schema: public; Owner: hugo
--

CREATE INDEX idx_folders_parent_id ON public.folders USING btree (parent_id);


--
-- Name: idx_metadata_file_id; Type: INDEX; Schema: public; Owner: hugo
--

CREATE INDEX idx_metadata_file_id ON public.metadata USING btree (file_id);


--
-- Name: idx_metadata_width_height; Type: INDEX; Schema: public; Owner: hugo
--

CREATE INDEX idx_metadata_width_height ON public.metadata USING btree (width, height);


--
-- Name: idx_scan_sessions_started_at; Type: INDEX; Schema: public; Owner: hugo
--

CREATE INDEX idx_scan_sessions_started_at ON public.scan_sessions USING btree (started_at DESC);


--
-- Name: ai_output ai_output_file_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: hugo
--

ALTER TABLE ONLY public.ai_output
    ADD CONSTRAINT ai_output_file_id_fkey FOREIGN KEY (file_id) REFERENCES public.files(id) ON DELETE CASCADE;


--
-- Name: embeddings embeddings_file_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: hugo
--

ALTER TABLE ONLY public.embeddings
    ADD CONSTRAINT embeddings_file_id_fkey FOREIGN KEY (file_id) REFERENCES public.files(id) ON DELETE CASCADE;


--
-- Name: files files_folder_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: hugo
--

ALTER TABLE ONLY public.files
    ADD CONSTRAINT files_folder_id_fkey FOREIGN KEY (folder_id) REFERENCES public.folders(id) ON DELETE CASCADE;


--
-- Name: folders folders_parent_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: hugo
--

ALTER TABLE ONLY public.folders
    ADD CONSTRAINT folders_parent_id_fkey FOREIGN KEY (parent_id) REFERENCES public.folders(id) ON DELETE CASCADE;


--
-- Name: metadata metadata_file_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: hugo
--

ALTER TABLE ONLY public.metadata
    ADD CONSTRAINT metadata_file_id_fkey FOREIGN KEY (file_id) REFERENCES public.files(id) ON DELETE CASCADE;


--
-- PostgreSQL database dump complete
--

\unrestrict KM5I8YsUK7CLbO0daSZ9hUdbrsZeFBT9FWSYUKVNueqkKGoLNR6hGNMoNadS5g0
```

## `tools/runtime/rebuild`

```bash
#!/bin/bash
set -e
cd /volume1/docker/nas-stack
echo "========== DOCS =========="
./gendocs || echo "Documentation generation failed, continuing build..."
echo "========== BUILD scanner + metadata_worker =========="
docker compose build --no-cache scanner metadata_worker
echo "========== RESTART scanner + metadata_worker =========="
docker compose up -d --force-recreate scanner metadata_worker
echo "========== HEALTH =========="
./health || true
echo "========== LOGS =========="
docker compose logs -f --tail=50 scanner metadata_worker
```

## `tools/runtime/rebuildall`

```bash
#!/bin/bash
set -e
cd /volume1/docker/nas-stack
echo "========== DOCS =========="
./gendocs || echo "Documentation generation failed, continuing build..."
echo "========== BUILD ALL =========="
docker compose build --no-cache
echo "========== RESTART ALL =========="
docker compose up -d --force-recreate --remove-orphans
echo "========== HEALTH =========="
./health || true
echo "========== LOGS =========="
docker compose logs -f --tail=50
```

## `tools/runtime/logs`

```bash
#!/bin/bash
cd /volume1/docker/nas-stack
docker compose logs -f --tail=50 scanner metadata_worker
```

## `tools/runtime/status`

```bash
#!/bin/bash
cd /volume1/docker/nas-stack

echo "========== CONTAINERS =========="
docker compose ps

echo
echo "========== HEALTH =========="
docker inspect nas-scanner-1 --format 'scanner: {{if .State.Health}}{{.State.Health.Status}}{{else}}no healthcheck{{end}}' 2>/dev/null || true
docker inspect nas-watcher-1 --format 'watcher: {{if .State.Health}}{{.State.Health.Status}}{{else}}no healthcheck{{end}}' 2>/dev/null || true
docker inspect nas-metadata_worker-1 --format 'metadata_worker: {{if .State.Health}}{{.State.Health.Status}}{{else}}no healthcheck{{end}}' 2>/dev/null || true
docker inspect nas-redis-1 --format 'redis: {{if .State.Health}}{{.State.Health.Status}}{{else}}no healthcheck{{end}}' 2>/dev/null || true

echo
echo "========== HEARTBEATS =========="
echo -n "scanner: "
docker exec nas-redis-1 redis-cli GET scanner:heartbeat 2>/dev/null || true
echo -n "watcher: "
docker exec nas-redis-1 redis-cli GET watcher:heartbeat 2>/dev/null || true
echo -n "watcher status: "
docker exec nas-redis-1 redis-cli GET watcher:heartbeat:status 2>/dev/null || true
echo -n "metadata_worker: "
docker exec nas-redis-1 redis-cli GET metadata_worker:heartbeat 2>/dev/null || true

echo
echo "========== LAST ACTIVITY =========="
echo -n "scanner:last_scan = "
docker exec nas-redis-1 redis-cli GET scanner:last_scan 2>/dev/null || true
echo -n "scanner:last_full_scan = "
docker exec nas-redis-1 redis-cli GET scanner:last_full_scan 2>/dev/null || true
echo -n "scanner:last_interval_scan = "
docker exec nas-redis-1 redis-cli GET scanner:last_interval_scan 2>/dev/null || true
echo -n "scanner:last_interval_root = "
docker exec nas-redis-1 redis-cli GET scanner:last_interval_root 2>/dev/null || true
echo -n "metadata_worker:last_event = "
docker exec nas-redis-1 redis-cli GET metadata_worker:last_event 2>/dev/null || true
echo -n "watcher:last_event = "
docker exec nas-redis-1 redis-cli GET watcher:last_event 2>/dev/null || true
echo -n "watcher:startup_recovery_roots = "
docker exec nas-redis-1 redis-cli GET watcher:recovery_roots 2>/dev/null || true

echo
echo "========== DIRTY ROOTS =========="
echo -n "pending = "
docker exec nas-redis-1 redis-cli HLEN scanner:dirty_roots 2>/dev/null || true
docker exec nas-redis-1 redis-cli HGETALL scanner:dirty_roots 2>/dev/null || true

echo
echo "========== SCAN SESSIONS =========="
docker exec nas-postgres-1 sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -P pager=off -c "SELECT id, type, status, started_at, finished_at, files_discovered, jobs_enqueued, jobs_processed FROM public.v_scan_status LIMIT 5"' 2>/dev/null \
  || docker exec postgres sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -P pager=off -c "SELECT id, type, status, started_at, finished_at, files_discovered, jobs_enqueued, jobs_processed FROM public.v_scan_status LIMIT 5"' 2>/dev/null \
  || echo "scan sessions niet beschikbaar"

echo
echo "========== LOCKS =========="
docker exec nas-redis-1 redis-cli KEYS "*lock*" 2>/dev/null || true

echo
echo "========== STREAM =========="
echo -n "polling = "
docker exec nas-redis-1 redis-cli XLEN scan_stream 2>/dev/null || true
echo -n "realtime = "
docker exec nas-redis-1 redis-cli XLEN scan_stream_realtime 2>/dev/null || true

echo
echo "========== POLLING GROUPS =========="
docker exec nas-redis-1 redis-cli XINFO GROUPS scan_stream 2>/dev/null || true
echo
echo "========== REALTIME GROUPS =========="
docker exec nas-redis-1 redis-cli XINFO GROUPS scan_stream_realtime 2>/dev/null || true

echo
echo "========== DLQ =========="
docker exec nas-redis-1 redis-cli XLEN scan_stream_dlq 2>/dev/null || true

echo
echo "========== DOCS =========="
ls -lh docs/DOCUMENTATIE.md 2>/dev/null || echo "docs/DOCUMENTATIE.md ontbreekt"
```

## `tools/runtime/health`

```bash
#!/bin/bash
cd /volume1/docker/nas-stack
fail=0

echo "========== CONTAINER HEALTH =========="

check_container() {
  name="$1"
  if docker inspect "$name" >/dev/null 2>&1; then
    state=$(docker inspect "$name" --format '{{.State.Status}}')
    health=$(docker inspect "$name" --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}none{{end}}')
    echo "$name: status=$state health=$health"
    [ "$state" = "running" ] || fail=1
    [ "$health" = "unhealthy" ] && fail=1
  else
    echo "$name: missing"
    fail=1
  fi
}

check_container nas-redis-1
check_container nas-scanner-1
check_container nas-watcher-1
check_container nas-metadata_worker-1

echo
echo "========== REDIS =========="
docker exec nas-redis-1 redis-cli ping || fail=1

echo
echo "========== HEARTBEATS =========="
scanner_hb=$(docker exec nas-redis-1 redis-cli GET scanner:heartbeat 2>/dev/null)
watcher_hb=$(docker exec nas-redis-1 redis-cli GET watcher:heartbeat 2>/dev/null)
worker_hb=$(docker exec nas-redis-1 redis-cli GET metadata_worker:heartbeat 2>/dev/null)

echo "scanner: ${scanner_hb:-missing}"
echo "watcher: ${watcher_hb:-missing}"
echo "metadata_worker: ${worker_hb:-missing}"

[ -n "$scanner_hb" ] || fail=1
[ -n "$watcher_hb" ] || fail=1
[ -n "$worker_hb" ] || fail=1

echo
echo "========== LAST ACTIVITY =========="
echo -n "scanner:last_scan = "
docker exec nas-redis-1 redis-cli GET scanner:last_scan 2>/dev/null || true
echo -n "metadata_worker:last_event = "
docker exec nas-redis-1 redis-cli GET metadata_worker:last_event 2>/dev/null || true
echo -n "watcher:last_event = "
docker exec nas-redis-1 redis-cli GET watcher:last_event 2>/dev/null || true
echo -n "dirty roots pending = "
docker exec nas-redis-1 redis-cli HLEN scanner:dirty_roots 2>/dev/null || true

echo
echo "========== STREAM =========="
docker exec nas-redis-1 redis-cli XLEN scan_stream || fail=1
docker exec nas-redis-1 redis-cli XINFO GROUPS scan_stream || true
docker exec nas-redis-1 redis-cli XLEN scan_stream_realtime || fail=1
docker exec nas-redis-1 redis-cli XINFO GROUPS scan_stream_realtime || true

echo
echo "========== DLQ =========="
docker exec nas-redis-1 redis-cli XLEN scan_stream_dlq || true

echo
if [ "$fail" -eq 0 ]; then
  echo "HEALTH OK"
else
  echo "HEALTH WARNING"
fi

exit "$fail"
```

## `tools/runtime/dlq`

```bash
#!/bin/sh
set -eu
cd /volume1/docker/nas-stack

echo "========== DLQ LENGTH =========="
docker exec nas-redis-1 redis-cli XLEN scan_stream_dlq

echo
echo "========== LAST 20 DLQ ITEMS =========="
docker exec nas-redis-1 redis-cli XREVRANGE scan_stream_dlq + - COUNT 20
```

## `tools/runtime/cleanlocks`

```bash
#!/bin/bash
cd /volume1/docker/nas-stack
docker exec nas-redis-1 redis-cli DEL scanner:lock:event
docker exec nas-redis-1 redis-cli DEL metadata_worker:lock
docker exec nas-redis-1 redis-cli DEL metadata:lock
echo "Locks cleared."
```

## `tools/runtime/watch`

```bash
#!/bin/bash
cd /volume1/docker/nas-stack
watch -n 5 'docker compose ps; echo; docker exec nas-redis-1 redis-cli XLEN scan_stream; echo; docker exec nas-redis-1 redis-cli XINFO GROUPS scan_stream; echo; docker exec nas-redis-1 redis-cli XLEN scan_stream_dlq'
```

## `gendocs`

```bash
#!/bin/bash
set -e

cd /volume1/docker/nas-stack
python3 tools/docs/generate_docs.py
```


