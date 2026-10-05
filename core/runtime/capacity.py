"""Single host-capacity publisher; consumers never inspect /proc themselves."""
from collections import deque
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


class CpuAdmission:
    """One publisher owns sample history and hysteresis for every worker profile."""
    def __init__(self, limit, resume, window=6, high=5, resume_seconds=30):
        if not (0 <= resume < limit <= 100 and 1 <= high <= window <= 120 and 0 < resume_seconds <= 3600):
            raise ValueError('invalid_cpu_policy')
        self.limit, self.resume = limit, resume
        self.window, self.high, self.resume_seconds = window, high, resume_seconds
        self.samples = deque(maxlen=window)
        self.paused = False
        self.low_since = self.last = None

    def reset(self):
        self.samples.clear()
        self.low_since = self.last = None

    def update(self, percent, tick):
        if self.last is not None and not 0 < tick-self.last <= INTERVAL*3:
            self.reset()
        self.last = tick
        self.samples.append(percent > self.limit)
        if not self.paused and len(self.samples)==self.window and sum(self.samples)>=self.high:
            self.paused = True
        if self.paused:
            if percent < self.resume:
                if self.low_since is None:
                    self.low_since = tick
                if tick-self.low_since >= self.resume_seconds:
                    self.paused = False
                    self.low_since = None
                    self.samples.clear()
            else:
                self.low_since = None
        return dict(paused=self.paused, pause_percent=self.limit, resume_percent=self.resume,
                    window_samples=self.window, high_samples=self.high,
                    resume_seconds=self.resume_seconds, reason='waiting_for_cpu' if self.paused else None)


def cpu_policies():
    profiles = {'finance':('FINANCE',60), 'ai':('AI',70), 'ocr':('OCR',60), 'execution':('EXECUTION',80)}
    window=int(os.getenv('CORE_CPU_WINDOW_SAMPLES','6'))
    high=int(os.getenv('CORE_CPU_HIGH_SAMPLES','5'))
    seconds=float(os.getenv('CORE_CPU_RESUME_SECONDS','30'))
    result={}
    for name,(prefix,default) in profiles.items():
        limit=float(os.getenv('CORE_'+prefix+'_MAX_CPU_PERCENT',str(default)))
        resume=float(os.getenv('CORE_'+prefix+'_CPU_RESUME_PERCENT',str(max(0,limit-10))))
        result[name]=CpuAdmission(limit,resume,window,high,seconds)
    return result


def cpu_blocked(resources, profile, legacy_limit):
    policies=resources.get('cpu_admission')
    if policies is None:
        # Rolling deployment with the old publisher retains its original safeguard.
        return resources['cpu_load_percent'] > legacy_limit
    return policies[profile]['paused']


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
        if 'cpu_admission' in value:
            policies=value['cpu_admission']
            if not isinstance(policies,dict) or set(policies)!=set(('finance','ai','ocr','execution')):raise ValueError()
            for policy in policies.values():
                if not isinstance(policy,dict) or type(policy.get('paused')) is not bool:raise ValueError()
                if policy.get('reason') != ('waiting_for_cpu' if policy['paused'] else None):raise ValueError()
        return value
    except Exception:
        raise CapacityUnavailable('capacity_unavailable') from None


def worker_resources():
    try:
        value=read_snapshot()
        return {'capacity_available':1,'cpu_load_percent':value['cpu_percent'],
                'available_memory_mib':round(value['memory_available']/1024/1024,1),
                'sampled_at':value['sampled_at'], 'cpu_admission':value.get('cpu_admission')}
    except CapacityUnavailable:
        return {'capacity_available':0}


def main():
    root=Path(os.getenv('HOST_PROC','/host/proc'))
    connection=client();previous=None;previous_time=None;policies=cpu_policies()
    while True:
        try:
            current=cpu_counters((root/'stat').read_text())
            tick=time.monotonic()
            if previous is not None and 0<tick-previous_time<=INTERVAL*3:
                value={**memory_metrics((root/'meminfo').read_text()),'version':1,
                       'cpu_percent':cpu_percent(previous,current),
                       'load_1m':float((root/'loadavg').read_text().split()[0]),'sampled_at':time.time()}
                value['cpu_admission']={name:policy.update(value['cpu_percent'],tick) for name,policy in policies.items()}
                connection.set(KEY,json.dumps(value),ex=MAX_AGE)
                connection.set('capacity_worker:heartbeat',str(value['sampled_at']),ex=MAX_AGE)
                connection.set('capacity_worker:heartbeat:status','ready',ex=MAX_AGE)
            else:
                connection.delete(KEY)
            previous,previous_time=current,tick
        except Exception:
            previous=previous_time=None
            for policy in policies.values():policy.reset()
            try:connection.delete(KEY)
            except Exception:pass
        time.sleep(INTERVAL)


if __name__=='__main__':main()
