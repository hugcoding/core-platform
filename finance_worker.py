"""CORE Finance single-job worker. Only reason codes leave this process."""
import os
import threading
import time
from datetime import datetime, timezone

import redis
from core.finance.privacy import source_root
from core.finance.store import connection, read_source, import_bytes, ADMISSION_LOCK
from core.finance.camt import ImportErrorCode
from workset_ai_worker import host_resources, stream_lag

STATUS = 'starting'
SINGLE_WORKER_LOCK = 118202611


def gate(conn, client):
    if os.getenv('CORE_MAINTENANCE_MODE','false').lower()=='true': return 'maintenance_mode'
    if not client.ping(): return 'redis_unavailable'
    resources=host_resources()
    if resources['cpu_load_percent']>float(os.getenv('CORE_FINANCE_MAX_CPU_PERCENT','60')): return 'waiting_for_cpu'
    if resources['available_memory_mib']<int(os.getenv('CORE_FINANCE_MIN_AVAILABLE_MIB','2048')): return 'waiting_for_memory'
    if stream_lag(client)>1000: return 'core_pipeline_priority'
    with conn.cursor() as cur:
        cur.execute("SELECT * FROM finance.runtime_pressure()")
        state=cur.fetchone()
        if state['busy']: return 'controlled_execution_priority'
        if state['sessions']>4: return 'postgres_busy'
    return None


def heartbeat(client):
    while True:
        try:
            client.set('finance_ingest_worker:heartbeat',datetime.now(timezone.utc).isoformat(),ex=90)
            client.set('finance_ingest_worker:heartbeat:status',STATUS,ex=90)
        except Exception: pass
        time.sleep(15)


def set_job(job,status,reason=None,error=None):
    with connection(worker=True) as conn, conn.cursor() as cur:
        cur.execute('''UPDATE finance.finance_ingest_jobs SET status=%s,waiting_reason=%s,error_code=%s,
            finished_at=CASE WHEN %s IN ('done','failed') THEN now() ELSE NULL END WHERE id=%s''',
            (status,reason,error,status,job))


def scan(client):
    global STATUS
    with connection(worker=True) as lease, lease.cursor() as cursor:
        cursor.execute('SELECT pg_try_advisory_xact_lock(%s) AS acquired',(SINGLE_WORKER_LOCK,))
        if not cursor.fetchone()['acquired']: return
        # A dead process loses its DB lock. Replay every completed file is safe.
        cursor.execute("SELECT id,attempts FROM finance.finance_ingest_jobs WHERE status IN ('pending','running') ORDER BY requested_at LIMIT 1")
        job=cursor.fetchone()
        if not job: STATUS='idle'; return
        jid=job['id']
        try:
            with connection(worker=True) as conn:
                reason=gate(conn,client)
            if reason:
                STATUS=reason;set_job(jid,'pending',reason);return
            with connection(worker=True) as conn, conn.cursor() as cur:
                cur.execute("UPDATE finance.finance_ingest_jobs SET status='running',waiting_reason=NULL,attempts=attempts+1 WHERE id=%s",(jid,))
            root=source_root()
            if not root.is_dir() or root.is_symlink(): raise ImportErrorCode('source_root_unavailable')
            paths=[]
            for directory,dirs,files in os.walk(root,followlinks=False):
                from pathlib import Path
                dirs[:]=[d for d in dirs if not d.startswith('.') and not (Path(directory)/d).is_symlink()]
                for name in files:
                    if name.lower().endswith('.xml'):
                        from pathlib import Path
                        paths.append(Path(directory)/name)
                    if len(paths)>1000: raise ImportErrorCode('file_count_limit')
            if not paths: raise ImportErrorCode('no_xml_files')
            for path in sorted(paths):
                with connection(worker=True) as conn, conn.cursor() as cur:
                    cur.execute('SELECT pg_try_advisory_xact_lock(%s) AS acquired',(ADMISSION_LOCK,))
                    reason=None if cur.fetchone()['acquired'] else 'controlled_execution_priority'
                    reason=reason or gate(conn,client)
                    if reason:
                        STATUS=reason;set_job(jid,'pending',reason);return
                    STATUS='processing'
                    data=read_source(path)
                    import_bytes(conn,path,data)
                    # Verify same immutable bytes before publishing the DB transaction.
                    if read_source(path)!=data: raise ImportErrorCode('source_changed')
            set_job(jid,'done');STATUS='idle'
        except ImportErrorCode as exc:
            set_job(jid,'failed',error=str(exc));STATUS='attention'
        except Exception:
            attempts=job['attempts']+1
            set_job(jid,'failed' if attempts>=3 else 'pending',reason='retry_wait',error='service_unavailable')
            STATUS='service_unavailable'


def main():
    global STATUS
    client=redis.Redis(host=os.getenv('REDIS_HOST','redis'),decode_responses=True,socket_timeout=3,socket_connect_timeout=3)
    threading.Thread(target=heartbeat,args=(client,),daemon=True).start()
    healthy=0
    while True:
        try:
            with connection(worker=True) as conn: reason=gate(conn,client)
            healthy=healthy+1 if reason is None else 0
            if healthy>=3: scan(client)
            else: STATUS=reason or 'waiting_for_stable_capacity'
        except Exception: healthy=0; STATUS='service_unavailable'
        time.sleep(20)


if __name__=='__main__': main()
