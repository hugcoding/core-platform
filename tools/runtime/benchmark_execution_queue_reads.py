#!/usr/bin/env python3
"""Read-only NAS-host comparison; never calls approval or executor endpoints.

Run from the repository on a quiet NAS. CPU figures cover the entire Postgres
container (background work is included), not just this request. Uses existing
dashboard container for dependencies. The proposed SQL is inlined, not deployed.
"""
import json
import subprocess
from pathlib import Path

ROOT = Path.cwd() if __file__ == "<stdin>" else Path(__file__).resolve().parents[2]
DOCKER = "/usr/local/bin/docker"


def cpu_seconds():
    return int(subprocess.check_output([
        DOCKER, "exec", "postgres", "cat", "/sys/fs/cgroup/cpuacct/cpuacct.usage"
    ], text=True)) / 1e9


def main():
    migration = (ROOT / "database/migrations/20260902_optimize_exact_duplicate_handoff.sql").read_text()
    handoff = migration.split("v_exact_duplicate_review_handoff AS\n", 1)[1].split(";", 1)[0]
    source = (ROOT / "dashboard/app.py").read_text()
    flat = source.split('flat_files = query_all(conn, """', 1)[1].split('""")', 1)[0]
    candidate_function = "def controlled_execution_candidates" + source.split(
        "def controlled_execution_candidates", 1)[1].split('\n\n@app.get', 1)[0]
    results = []
    for optimized in (False, True):
        code = """
import hashlib,json,time
import dashboard.app as a
if optimized:
    exec(candidate_function, a.__dict__)
connect, query = a.db_connect, a.query_all
def readonly():
    c=connect(); c.set_session(readonly=True)
    c.cursor().execute("SET LOCAL statement_timeout='45s'")
    c.cursor().execute("SET LOCAL jit=off")
    return c
a.db_connect=readonly
def patched(c, sql, *args, **kwargs):
    if optimized and 'FROM public.v_exact_duplicate_review_handoff h' in sql:
        sql=sql.replace('public.v_exact_duplicate_review_handoff h', '('+handoff+') h')
    if optimized and 'COALESCE(location.current_path, f.path) AS source_path' in sql:
        sql=flat
    return query(c,sql,*args,**kwargs)
a.query_all=patched
t=time.monotonic();r=a.controlled_execution_queue_preview()
print(json.dumps({'seconds':round(time.monotonic()-t,3), 'ready':r['ready_count'],
 'blocked':r['blocked_count'], 'digest':hashlib.sha256(json.dumps(r,sort_keys=True,default=str).encode()).hexdigest()}))
"""
        prefix = f"optimized={optimized!r}\nhandoff={handoff!r}\nflat={flat!r}\ncandidate_function={candidate_function!r}\n"
        before = cpu_seconds()
        process = subprocess.run([DOCKER, "exec", "-i", "nas-dashboard-1", "python", "-"],
                                 input=prefix + code, text=True, capture_output=True)
        if process.returncode:
            raise RuntimeError(process.stderr)
        used = cpu_seconds() - before
        result = {**json.loads(process.stdout), "optimized": optimized,
                  "postgres_cpu_seconds": round(used, 3)}
        results.append(result)
        print(json.dumps(result), flush=True)
    equal = results[0]["digest"] == results[1]["digest"]
    print(json.dumps({"results_equal": equal,
        "cpu_reduction_percent": round(100 * (1 - results[1]["postgres_cpu_seconds"] / results[0]["postgres_cpu_seconds"]), 1)}))
    return 0 if equal else 1


if __name__ == "__main__":
    raise SystemExit(main())
