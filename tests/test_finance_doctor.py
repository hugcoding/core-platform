"""Synthetic configuration only; never use the NAS environment or bank files."""
import argparse
from contextlib import contextmanager
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from core.finance import doctor

CANARY = 'SECRET-CANARY-DO-NOT-PRINT'
GOOD = {'enabled': True, 'secrets': 'OK', 'database': 'OK', 'storage': 'OK'}


class DoctorTests(unittest.TestCase):
    def run_check(self, setting=None, actual=None, *, compose_value=None, probe=None,
                  worker=False, args=(), failure=False, environ=None):
        parser = argparse.ArgumentParser()
        doctor.add_arguments(parser)
        options = parser.parse_args(args)
        calls = []
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            contents = 'OTHER_SECRET=' + CANARY + '\n'
            if setting is not None:
                contents += doctor.FLAG + '=' + setting + '\n'
            (root / '.env').write_text(contents, encoding='utf-8')
            original = (root / '.env').read_bytes()
            expected = doctor.enabled(setting)
            status = dict(GOOD, enabled=expected if actual is None else actual) if probe is None else probe

            def runner(command, **kwargs):
                calls.append(command)
                self.assertTrue(kwargs['capture_output'])
                self.assertEqual(root, kwargs['cwd'])
                self.assertLessEqual(kwargs['timeout'], 20)
                if failure:
                    raise subprocess.TimeoutExpired(command, 20, output=CANARY, stderr=CANARY)
                if kwargs.get('input'):
                    output = json.dumps({'services': {'dashboard': {'environment': {doctor.FLAG: setting if setting is not None else '__CORE_FINANCE_UNSET__'}}}})
                elif '--format' in command:
                    value = compose_value if compose_value is not None else ('true' if expected else 'false')
                    output = json.dumps({'services': {'dashboard': {'environment': {doctor.FLAG: value, 'DB_PASS': CANARY}}}})

                elif 'exec' in command:
                    if 'finance_worker' in command and not worker:
                        return subprocess.CompletedProcess(command, 1, '', CANARY)
                    output = json.dumps(status)
                else:
                    output = 'synthetic-container-id' if worker else ''
                return subprocess.CompletedProcess(command, 0, stdout=output, stderr=CANARY)

            stream = io.StringIO()
            code = doctor.diagnose(options, root, stdout=stream, runner=runner, environ=environ or {})
            self.assertEqual(original, (root / '.env').read_bytes())
            self.assertNotIn(CANARY, stream.getvalue())
            return code, stream.getvalue(), calls

    def test_absent_false_and_true(self):
        for setting, configured, expected in ((None, 'no', 'false'), ('false', 'yes', 'false'), ('true', 'yes', 'true')):
            with self.subTest(setting=setting):
                code, output, _ = self.run_check(setting)
                self.assertEqual(0, code)
                self.assertIn('configured: ' + configured, output)
                self.assertIn('enabled: ' + expected, output)
                self.assertIn('dashboard: OK', output)
                if setting is None:
                    self.assertIn('safe default false is active', output)

    def test_mismatch_in_both_directions_fails(self):
        for setting, actual in [('true', False), ('false', True), (None, True)]:
            code, output, _ = self.run_check(setting, actual)
            self.assertEqual(1, code)
            self.assertIn('MISMATCH; recreate', output)

    def test_compose_cannot_override_local_intent(self):
        for setting, override in [(None, 'true'), ('false', 'true'), ('true', 'false')]:
            code, output, _ = self.run_check(setting, compose_value=override)
            self.assertEqual(1, code)
            self.assertIn('Compose overrides', output)

    def test_invalid_setting_is_not_echoed(self):
        code, output, _ = self.run_check(CANARY)
        self.assertEqual(1, code)
        self.assertIn('must be true or false', output)

    def test_missing_secrets_and_dependencies_clear_without_leaks(self):
        for field in ('secrets', 'database', 'storage'):
            code, output, _ = self.run_check('true', probe=dict(GOOD, **{field: CANARY}))
            self.assertEqual(1, code)
            self.assertIn(field + ': unavailable or invalid', output)

    def test_disabled_install_does_not_require_finance_dependencies(self):
        code, _, _ = self.run_check('false', probe={'enabled': False})
        self.assertEqual(0, code)

    def test_required_worker_cannot_be_silently_skipped(self):
        code, output, _ = self.run_check('true', args=['--worker'])
        self.assertEqual(1, code)
        self.assertIn('finance_worker: unavailable', output)

    def test_compose_error_is_sanitized(self):
        code, output, _ = self.run_check(failure=True)
        self.assertEqual(1, code)
        self.assertIn('Compose configuration unavailable', output)

    def test_bad_container_response_is_sanitized(self):
        code, output, _ = self.run_check('true', probe={'enabled': CANARY})
        self.assertEqual(1, code)
        self.assertIn('dashboard: unavailable', output)

    def test_compose_options_apply_to_every_command_and_worker_checked(self):
        code, output, calls = self.run_check('true', worker=True, args=['-p', 'test', '-f', 'base.yml', '-f', 'override.yml', '--env-file', '.env', '--worker'])
        self.assertEqual(0, code)
        for command in calls:
            self.assertIn('--project-directory', command)
            self.assertIn('--env-file', command)
        for command in calls[1:]:
            self.assertIn('base.yml', command)
            self.assertIn('override.yml', command)
            self.assertIn('test', command)
        self.assertIn('finance_worker secrets: OK', output)
        self.assertTrue(any('exec' in command and 'finance_worker' in command and '--worker' in command for command in calls))

    def test_python_cli_finance_does_not_require_jira_config(self):
        from core.cli import main
        with tempfile.TemporaryDirectory() as directory, patch('core.finance.doctor.diagnose', return_value=0) as check:
            self.assertEqual(0, main(['doctor', '--finance', '--worker'], base_path=directory))
            self.assertTrue(check.call_args.args[0].worker)


class ProbeTests(unittest.TestCase):
    def test_probe_checks_secret_structure_and_read_only_database(self):
        from cryptography.fernet import Fernet
        values = {'data_key': Fernet.generate_key().decode(), 'session_key': Fernet.generate_key().decode(),
                  'identity_key': CANARY, 'access_hash': 'a' * 64}
        cursor = MagicMock()
        conn = MagicMock()
        conn.cursor.return_value.__enter__.return_value = cursor

        @contextmanager
        def connection(worker=False):
            yield conn

        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {doctor.FLAG: 'true'}, clear=True), \
                patch('core.finance.crypto.secret', return_value=values), \
                patch('core.finance.privacy.source_root', return_value=Path(directory)), \
                patch('core.finance.store.connection', connection):
            result = doctor.probe()
            self.assertEqual(GOOD, result)
            self.assertEqual(['SET TRANSACTION READ ONLY', 'SELECT 1 FROM finance.finance_transactions LIMIT 0'],
                             [call.args[0] for call in cursor.execute.call_args_list])
            for field in ('data_key', 'session_key', 'identity_key', 'access_hash'):
                with patch('core.finance.crypto.secret', return_value={**values, field: ''}):
                    self.assertEqual('missing_or_invalid', doctor.probe()['secrets'])
            for value in values.values():
                self.assertNotIn(value, json.dumps(result))

    def test_probe_swallows_sensitive_errors(self):
        with patch.dict(os.environ, {}, clear=True), \
                patch('core.finance.crypto.secret', side_effect=ValueError(CANARY)), \
                patch('core.finance.privacy.source_root', side_effect=OSError(CANARY)), \
                patch('core.finance.store.connection', side_effect=RuntimeError(CANARY)):
            result = doctor.probe()
        self.assertFalse(result['enabled'])
        self.assertNotIn(CANARY, json.dumps(result))
        self.assertEqual('missing_or_invalid', result['secrets'])

    def test_existing_api_remains_disabled_or_owner_locked(self):
        from dashboard.finance import owner, login
        from fastapi import HTTPException
        from cryptography.fernet import Fernet
        request = MagicMock()
        request.cookies = {}
        for setting in (None, 'false', 'true'):
            with patch.dict(os.environ, {} if setting is None else {doctor.FLAG: setting}, clear=True), \
                    patch('dashboard.finance.secret', return_value={'session_key': Fernet.generate_key().decode()}):
                with self.assertRaises(HTTPException) as error:
                    owner(request)
                self.assertEqual(401 if setting == 'true' else 503, error.exception.status_code)
                if setting != 'true':
                    with self.assertRaises(HTTPException) as error:
                        login(request, {'code': CANARY})
                    self.assertEqual(503, error.exception.status_code)


@unittest.skipUnless(shutil.which('git'), 'Git needed for local-env preservation test')
class EnvironmentPreservationTests(unittest.TestCase):
    def test_fast_forward_keeps_ignored_runtime_config(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source, checkout = root / 'source', root / 'checkout'
            source.mkdir()

            def git(path, *args):
                result = subprocess.run(['git', '-c', 'safe.directory=' + str(path), *args], cwd=path,
                                        capture_output=True, text=True, timeout=20)
                self.assertEqual(0, result.returncode, 'synthetic Git command failed')
                return result.stdout

            git(source, 'init', '-b', 'main')
            git(source, 'config', 'user.name', 'Synthetic Test')
            git(source, 'config', 'user.email', 'synthetic@example.invalid')
            (source / '.gitignore').write_text((Path(__file__).resolve().parents[1] / '.gitignore').read_text('utf-8'), encoding='utf-8')
            (source / 'app.txt').write_text('before', encoding='utf-8')
            git(source, 'add', '.')
            git(source, 'commit', '-m', 'synthetic baseline')
            git(root, 'clone', str(source), str(checkout))
            (checkout / '.env').write_text('CORE_FINANCE_ENABLED=true\nDB_PASS=' + CANARY, encoding='utf-8')
            original = (checkout / '.env').read_bytes()
            ignored = git(checkout, 'check-ignore', '.env', '.env.production', 'secret.json', 'access-code.txt')
            self.assertEqual({'.env', '.env.production', 'secret.json', 'access-code.txt'}, set(ignored.splitlines()))
            (source / 'app.txt').write_text('after', encoding='utf-8')
            git(source, 'add', 'app.txt')
            git(source, 'commit', '-m', 'synthetic update')
            git(checkout, 'pull', '--ff-only')
            self.assertEqual(original, (checkout / '.env').read_bytes())
            self.assertEqual('', git(checkout, 'ls-files', '.env'))


@unittest.skipUnless(os.environ.get('CORE_FINANCE_COMPOSE_TEST'), 'Opt-in real Compose configuration test')
class ComposeIntegrationTests(unittest.TestCase):
    def test_deployment_checks_after_recreate_and_propagates_failure(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'tools/runtime').mkdir(parents=True)
            script = root / 'tools/runtime/core'
            source = (Path(__file__).resolve().parents[1] / 'tools/runtime/core').read_text('utf-8')
            # Shell functions cannot fall back to a real Docker executable on a
            # NAS whose temporary directory disallows executing fixture scripts.
            stubs = ('docker() { printf "docker %s\\n" "$*" >> "$TEST_LOG"; }\n'
                     'python3() { printf "python %s\\n" "$*" >> "$TEST_LOG"; return "$TEST_CODE"; }\n')
            script.write_text(stubs + source, encoding='utf-8')
            (root / '.env').write_text('CORE_FINANCE_ENABLED=true\nDB_PASS=' + CANARY, encoding='utf-8')
            before = (root / '.env').read_bytes()
            log = root / 'calls'
            for code in (0, 1):
                log.write_text('', encoding='utf-8')
                env = dict(os.environ, DOCKER_BIN='docker', TEST_CODE=str(code), TEST_LOG=str(log))
                result = subprocess.run(['sh', str(script), 'dashboard', 'deploy'], env=env, capture_output=True, text=True)
                self.assertEqual(code, result.returncode, result.stdout + result.stderr)
                commands = log.read_text('utf-8').splitlines()
                self.assertEqual(commands[:3], ['docker compose build dashboard',
                    'docker compose up -d --force-recreate dashboard', 'python -m core.finance.doctor --wait 20'])
                self.assertEqual(code == 0, 'CORE Pulse:' in result.stdout)
                self.assertEqual(before, (root / '.env').read_bytes())

    def test_real_dotenv_interpolation_and_overrides(self):
        # Runs config only, never builds, starts or connects to any container.
        parser = argparse.ArgumentParser()
        doctor.add_arguments(parser)
        cases = [(None, {}, False, False), ('false', {}, True, False), ('true', {}, True, True),
                 ('"true" # local choice', {}, True, True), ('true', {doctor.FLAG: 'false'}, True, False),
                 ('', {}, False, False)]
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'docker-compose.yml').write_text(
                'services:\n  dashboard:\n    image: scratch\n    environment:\n'
                '      CORE_FINANCE_ENABLED: ${CORE_FINANCE_ENABLED:-false}\n', encoding='utf-8')
            for setting, shell, configured, enabled in cases:
                with self.subTest(setting=setting, shell=shell):
                    envfile = root / 'runtime.env'
                    envfile.write_text('DB_PASS=' + CANARY + '\n' + ('' if setting is None else doctor.FLAG + '=' + setting + '\n'), encoding='utf-8')
                    before = envfile.read_bytes()
                    environ = {key: os.environ[key] for key in ('PATH', 'HOME') if key in os.environ}
                    environ.update(shell)
                    environ['DOCKER_BIN'] = os.environ['CORE_FINANCE_COMPOSE_TEST']

                    def runner(command, **kwargs):
                        if 'exec' in command:
                            return subprocess.CompletedProcess(command, 0, json.dumps(dict(GOOD, enabled=enabled)), '')
                        if 'ps' in command:
                            return subprocess.CompletedProcess(command, 0, '', '')
                        return subprocess.run(command, **kwargs)

                    stream = io.StringIO()
                    code = doctor.diagnose(parser.parse_args(['--env-file', 'runtime.env']), root, stream, runner, environ)
                    self.assertEqual(0, code, stream.getvalue())
                    self.assertIn('configured: ' + ('yes' if configured else 'no'), stream.getvalue())
                    self.assertIn('enabled: ' + str(enabled).lower(), stream.getvalue())
                    self.assertNotIn(CANARY, stream.getvalue())
                    self.assertEqual(before, envfile.read_bytes())
            # A forced override must not silently enable a locally disabled install.
            envfile.write_text('CORE_FINANCE_ENABLED=false\n', encoding='utf-8')
            (root / 'override.yml').write_text('services:\n  dashboard:\n    environment:\n      CORE_FINANCE_ENABLED: "true"\n', encoding='utf-8')
            stream = io.StringIO()
            code = doctor.diagnose(parser.parse_args(['--env-file', 'runtime.env', '-f', 'docker-compose.yml', '-f', 'override.yml']), root, stream, runner, environ)
            self.assertEqual(1, code)
            self.assertIn('Compose overrides', stream.getvalue())


if __name__ == '__main__':
    unittest.main()
