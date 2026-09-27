"""Read-only Finance deployment checks. Only allowlisted statuses leave this module.

Host mode needs only the standard library; --probe runs inside the service image.
Never print subprocess output, configuration values or exception messages.
"""
import argparse
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time

FLAG = 'CORE_FINANCE_ENABLED'


def enabled(value):
    # Match the existing API guard exactly (including case handling).
    return str(value).lower() == 'true'


def probe(worker=False):
    result = {'enabled': enabled(os.getenv(FLAG, 'false'))}
    try:
        from cryptography.fernet import Fernet
        from core.finance.crypto import secret
        values = secret()
        for key in ('data_key', 'session_key'):
            Fernet(values[key].encode())
        if not isinstance(values['identity_key'], str) or not values['identity_key']:
            raise ValueError()
        if not re.fullmatch(r'[0-9a-f]{64}', values['access_hash']):
            raise ValueError()
        result['secrets'] = 'OK'
    except Exception:
        result['secrets'] = 'missing_or_invalid'
    try:
        from core.finance.privacy import source_root
        root = source_root()
        result['storage'] = 'OK' if root.is_dir() and os.access(root, os.R_OK | os.X_OK) else 'unavailable'
    except Exception:
        result['storage'] = 'unavailable'
    try:
        from core.finance.store import connection
        with connection(worker=worker) as conn:
            with conn.cursor() as cur:
                cur.execute('SET TRANSACTION READ ONLY')
                # Verify access and the baseline schema, without reading bank rows.
                cur.execute('SELECT 1 FROM finance.finance_transactions LIMIT 0')
        result['database'] = 'OK'
    except Exception:
        result['database'] = 'unavailable_or_schema_missing'
    return result


def add_arguments(parser):
    parser.add_argument('-f', '--file', action='append', default=[], help='Compose files, in deployment order')
    parser.add_argument('--env-file', action='append', default=[], help='Same env file(s) as deployment')
    parser.add_argument('-p', '--project-name')
    parser.add_argument('--worker', action='store_true', help='Require a running finance_worker too')
    parser.add_argument('--wait', type=int, choices=range(0, 61), default=0, metavar='0..60', help='Retry unavailable containers after deployment')


def diagnose(args, root, stdout=sys.stdout, runner=subprocess.run, environ=None):
    environ = os.environ if environ is None else environ
    root = Path(root)
    docker = environ.get('DOCKER_BIN') or shutil.which('docker') or '/usr/local/bin/docker'
    compose = [docker, 'compose', '--project-directory', str(root)]
    for name in args.file:
        compose += ['-f', name]
    for name in args.env_file:
        compose += ['--env-file', name]
    if args.project_name:
        compose += ['-p', args.project_name]

    def call(arguments, prefix=None, source=None):
        try:
            process = runner((prefix or compose) + arguments, cwd=root, env=dict(environ), input=source,
                             capture_output=True, text=True, timeout=20)
            return process.stdout if process.returncode == 0 else None
        except (OSError, UnicodeError, subprocess.SubprocessError):
            return None

    print('Finance', file=stdout)
    # Resolve just this variable through the SAME Compose/.env interpolation.
    # A minimal stdin model works on Synology Compose 2.20 (no --environment).
    # It also distinguishes an absent setting from an explicit false without
    # implementing our own dotenv parser. No container is created.
    local_compose = [docker, 'compose', '--project-directory', str(root), '-p', 'core-finance-doctor', '-f', '-']
    for name in args.env_file:
        local_compose += ['--env-file', name]
    source = ('services:\n  dashboard:\n    image: scratch\n    environment:\n'
              '      CORE_FINANCE_ENABLED: ${CORE_FINANCE_ENABLED-__CORE_FINANCE_UNSET__}\n')
    try:
        local_config = json.loads(call(['config', '--format', 'json'], prefix=local_compose, source=source) or '')
        local_value = local_config['services']['dashboard']['environment'][FLAG]
        explicit = local_value not in ('__CORE_FINANCE_UNSET__', '', None)
        if not explicit:
            local_value = 'false'
        expected = enabled(local_value)
        print('configured: ' + ('yes' if explicit else 'no'), file=stdout)
        config = json.loads(call(['config', '--format', 'json']) or '')
        value = config['services']['dashboard']['environment'].get(FLAG, 'false')
    except (ValueError, TypeError, KeyError, AttributeError):
        print('enabled: unknown\nerror: Compose configuration unavailable; check Docker and local environment configuration', file=stdout)
        return 1
    print('enabled: ' + str(expected).lower(), file=stdout)
    failed = str(local_value).lower() not in ('true', 'false')
    if failed:
        print('error: CORE_FINANCE_ENABLED must be true or false', file=stdout)
    if str(value).lower() not in ('true', 'false') or enabled(value) != expected:
        print('error: Compose overrides CORE_FINANCE_ENABLED; local configuration must remain authoritative', file=stdout)
        failed = True
    if not explicit:
        print('warning: CORE_FINANCE_ENABLED is not configured; safe default false is active', file=stdout)

    def service_probe(service):
        deadline = time.monotonic() + args.wait
        while True:
            command = ['exec', '-T', service, 'python', '-m', 'core.finance.doctor', '--probe']
            if service == 'finance_worker':
                command.append('--worker')
            try:
                result = json.loads(call(command) or '')
                if not isinstance(result, dict) or type(result.get('enabled')) is not bool:
                    raise ValueError()
                return result
            except (ValueError, TypeError):
                if time.monotonic() >= deadline:
                    return None
                time.sleep(2)

    def report(service, result):
        if result is None:
            print(service + ': unavailable; start/rebuild this service, then retry', file=stdout)
            return True
        mismatch = service == 'dashboard' and result['enabled'] != expected
        print(service + ': ' + ('MISMATCH; recreate with the intended local configuration' if mismatch else 'OK'), file=stdout)
        if service == 'dashboard':
            print('dashboard enabled: ' + str(result['enabled']).lower(), file=stdout)
        broken = mismatch
        for field in ('secrets', 'database', 'storage'):
            ok = result.get(field) == 'OK'
            # Never render arbitrary strings from a subprocess, even on failure.
            print(service + ' ' + field + ': ' + ('OK' if ok else 'unavailable or invalid'), file=stdout)
            broken |= expected and not ok
        return broken

    failed |= report('dashboard', service_probe('dashboard'))
    running = call(['ps', '--status', 'running', '-q', 'finance_worker'])
    if args.worker or (running and running.strip()):
        failed |= report('finance_worker', service_probe('finance_worker'))
    else:
        print('finance_worker: not running' if running is not None else 'finance_worker: status unavailable', file=stdout)
        if expected:
            print('warning: imports require finance_worker; validate with --worker after starting it', file=stdout)
    return int(failed)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    add_arguments(parser)
    parser.add_argument('--probe', action='store_true', help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    if args.probe:
        print(json.dumps(probe(worker=args.worker)))
        return 0
    return diagnose(args, Path.cwd())


if __name__ == '__main__':
    raise SystemExit(main())
