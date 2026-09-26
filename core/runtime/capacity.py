"""Single host-capacity publisher; consumers never inspect /proc themselves."""
import json
import math
import os
from pathlib import Path
import time

import redis

KEY = 'core:capacity:v1'
MAX_AGE = 20
INTERVAL = 5


class CapacityUnavailable(ValueError):
    pass


def memory_metrics(text):
    values = {line.split(':',1)[0]: int(line.split()[1])*1024 for line in text.splitlines()}
    total = values['MemTotal']
    if total <= 0:
        raise ValueError('invalid_memory')
    estimated = 'MemAvailable' not in values
    cache = max(0, values.get('Buffers',0)+values.get('Cached',0)+values.get('SReclaimable',0)-values.get('Shmem',0))
    available = values['MemFree']+cache if estimated else values['MemAvailable']
    available = min(total,max(0,available))
    return dict(memory_total=total,memory_used=total-available,memory_available=available,memory_estimated=estimated)


def cpu_counters(text):
    fields = text.splitlines()[0].split()
    if fields[0]!='cpu' or len(fields)<5:
        raise ValueError('invalid_cpu_sample')
    # guest/guest_nice are already included in user/nice, so never count twice.
    values=[int(v) for v in fields[1:9]]
    if any(v<0 for v in values):raise ValueError('invalid_cpu_sample')
    total=sum(values)
    idle=values[3]+(values[4] if len(values)>4 else 0)
    return total,total-idle


def cpu_percent(previous,current):
    total=current[0]-previous[0];busy=current[1]-previous[1]
    if total<=0 or not 0<=busy<=total:raise ValueError('invalid_cpu_delta')
    return round(100*busy/total,2)


def client():
    return redis.Redis(host=os.getenv('REDIS_HOST','redis'),decode_responses=True,socket_timeout=2,socket_connect_timeout=2)


def read_snapshot(connection=None, now=None):
    try:
        value=json.loads((connection or client()).get(KEY) or 'null')
        if not isinstance(value,dict) or type(value.get('version')) is not int or value.get('version')!=1:raise ValueError()
        if not isinstance(value.get('memory_estimated'), bool):raise ValueError()
        current=time.time() if now is None else now
        age=current-value['sampled_at']
        if not 0<=age<=MAX_AGE or not 0<=value['cpu_percent']<=100:raise ValueError()
        for field in ('cpu_percent','memory_total','memory_available','memory_used','sampled_at','load_1m'):
            if isinstance(value[field],bool) or not math.isfinite(value[field]):raise ValueError()
        if value['memory_total']<=0 or not 0<=value['memory_available']<=value['memory_total']:raise ValueError()
        if value['memory_used']!=value['memory_total']-value['memory_available']:raise ValueError()
        return value
    except Exception:
        raise CapacityUnavailable('capacity_unavailable') from None


def worker_resources():
    try:
        value=read_snapshot()
        return {'capacity_available':1,'cpu_load_percent':value['cpu_percent'],
                'available_memory_mib':round(value['memory_available']/1024/1024,1),
                'sampled_at':value['sampled_at']}
    except CapacityUnavailable:
        return {'capacity_available':0}


def main():
    root=Path(os.getenv('HOST_PROC','/host/proc'))
    connection=client();previous=None;previous_time=None
    while True:
        try:
            current=cpu_counters((root/'stat').read_text())
            tick=time.monotonic()
            if previous is not None and 0<tick-previous_time<=INTERVAL*3:
                value={**memory_metrics((root/'meminfo').read_text()),'version':1,
                       'cpu_percent':cpu_percent(previous,current),
                       'load_1m':float((root/'loadavg').read_text().split()[0]),'sampled_at':time.time()}
                connection.set(KEY,json.dumps(value),ex=MAX_AGE)
                connection.set('capacity_worker:heartbeat',str(value['sampled_at']),ex=MAX_AGE)
                connection.set('capacity_worker:heartbeat:status','ready',ex=MAX_AGE)
            else:
                connection.delete(KEY)
            previous,previous_time=current,tick
        except Exception:
            previous=previous_time=None
            try:connection.delete(KEY)
            except Exception:pass
        time.sleep(INTERVAL)


if __name__=='__main__':main()
