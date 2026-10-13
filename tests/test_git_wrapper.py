"""Execute the shell wrappers with fake Docker, never a real checkout or secrets."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]


@unittest.skipUnless(shutil.which('sh'), 'POSIX shell required')
class GitWrapperTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)/'repo with spaces'
        runtime=self.root/'tools/runtime';runtime.mkdir(parents=True)
        for name in ('core','git-pull','git-run'):
            shutil.copyfile(ROOT/'tools/runtime'/name,runtime/name)
        self.log=self.root/'calls.jsonl'
        docker=Path(self.temp.name)/'fake-docker'
        docker.write_text('''#!/usr/bin/env python3
import json,os,sys
from pathlib import Path
args=sys.argv[1:]
p=Path(os.environ['CALL_LOG'])
previous=p.read_text().splitlines() if p.exists() else []
with p.open('a') as f:f.write(json.dumps(args)+'\\n')
if 'run' not in args:sys.exit(0)
git=args[args.index('maintenance.auto=false')+1:]
if git[0]=='status':print(os.getenv('TRACKED',''))
if git[:2]==['rev-parse','HEAD']:
    heads=sum(json.loads(line)[-2:]==['rev-parse','HEAD'] for line in previous)
    print('old' if heads==0 else 'new')
if git[0]=='fetch':sys.exit(int(os.getenv('FETCH_EXIT','0')))
if git[0]=='diff':print('docs/example.md')
''',encoding='utf-8');docker.chmod(0o755)
        self.env={**os.environ,'DOCKER_BIN':str(docker),'CALL_LOG':str(self.log),
                  'HOME':str(self.root/'private home')}
        probe=subprocess.run(['sh','-c','command -v "$DOCKER_BIN"'],env=self.env,capture_output=True)
        if probe.returncode:
            self.skipTest('Temporary executables unavailable; run in isolated Linux container')
        (self.root/'.env').write_text('synthetic-private-setting')

    def run_core(self,*args,**env):
        return subprocess.run(['sh',str(self.root/'tools/runtime/core'),'git',*args],
                              env={**self.env,**env},capture_output=True,text=True)

    def calls(self):
        return [json.loads(line) for line in self.log.read_text().splitlines()] if self.log.exists() else []

    def test_pull_uses_same_ssh_identity_and_user_mapping_as_other_commands(self):
        result=self.run_core('pull','--skip-docs')
        self.assertEqual(0,result.returncode,result.stderr)
        calls=self.calls()
        self.assertTrue(any(c[-4:]==['fetch','--no-auto-maintenance','origin','main'] for c in calls))
        self.assertTrue(any(c[-3:]==['merge','--ff-only','origin/main'] for c in calls))
        self.assertFalse(any('compose' in c for c in calls))
        for c in calls:
            self.assertIn('/etc/passwd:/etc/passwd:ro',c)
            self.assertIn('/etc/group:/etc/group:ro',c)
            self.assertIn(str(self.root/'private home/.ssh')+':/tmp/corehome/.ssh:ro',c)
            self.assertTrue(any(v.startswith('GIT_SSH_COMMAND=ssh ') for v in c))
        self.assertEqual('synthetic-private-setting',(self.root/'.env').read_text())

    def test_general_commands_keep_argument_boundaries(self):
        for args in [('status','--short'),('diff','--stat'),('commit','-m','message with spaces'),
                     ('push','origin','codex/test'),('branch','--show-current')]:
            result=self.run_core(*args)
            self.assertEqual(0,result.returncode,result.stderr)
            self.assertEqual(list(args),self.calls()[-1][-len(args):])

    def test_dirty_checkout_stops_before_fetch_and_preserves_env(self):
        result=self.run_core('pull','--skip-docs',TRACKED=' M user-file.py')
        self.assertEqual(2,result.returncode)
        self.assertIn('Tracked local changes',result.stdout)
        self.assertEqual(1,len(self.calls()))
        self.assertEqual('synthetic-private-setting',(self.root/'.env').read_text())

    def test_fetch_error_does_not_merge(self):
        result=self.run_core('pull','--skip-docs',FETCH_EXIT='7')
        self.assertEqual(7,result.returncode)
        self.assertFalse(any('merge' in c for c in self.calls()))

    def test_conflicting_options_do_not_invoke_docker(self):
        result=self.run_core('pull','--skip-docs','--rebuild-docs')
        self.assertEqual(2,result.returncode)
        self.assertEqual([],self.calls())


if __name__=='__main__':unittest.main()
