"""Execute CLI with fake Docker/doctor; never build or replace actual services."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]


@unittest.skipUnless(shutil.which('sh'),'POSIX shell required')
class FinanceCLITests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        root=Path(self.temp.name);self.repo=root/'repo with spaces'
        runtime=self.repo/'tools/runtime';runtime.mkdir(parents=True)
        for name in ['core','finance']:shutil.copyfile(ROOT/'tools/runtime'/name,runtime/name)
        self.bin=root/'bin';self.bin.mkdir();self.log=root/'calls.jsonl'
        for name in ['docker','python3']:
            exe=self.bin/name
            exe.write_text('#!'+sys.executable+'''\nimport json,os,sys
from pathlib import Path
args=sys.argv[1:];tool=Path(sys.argv[0]).name
record=dict(tool=tool,args=args,cwd=os.getcwd(),context=os.getenv('CORE_FINANCE_BUILD_CONTEXT'),
            enabled=os.getenv('CORE_FINANCE_ENABLED'),profiles=os.getenv('COMPOSE_PROFILES'))
with open(os.environ['CALL_LOG'],'a') as f:f.write(json.dumps(record)+'\\n')
if tool=='docker' and 'build' in args:sys.exit(int(os.getenv('BUILD_EXIT','0')))
if tool=='docker' and 'up' in args:sys.exit(int(os.getenv('UP_EXIT','0')))
if tool=='python3':sys.exit(int(os.getenv('DOCTOR_EXIT','0')))
''');exe.chmod(0o755)
        self.env={**os.environ,'PATH':str(self.bin)+os.pathsep+os.environ['PATH'],
                  'DOCKER_BIN':str(self.bin/'docker'),'CALL_LOG':str(self.log),
                  'CORE_FINANCE_BUILD_CONTEXT':'wrong-old-path','CORE_FINANCE_ENABLED':'false'}
        probe=subprocess.run(['sh','-c','command -v "$DOCKER_BIN"'],env=self.env,capture_output=True)
        if probe.returncode:self.skipTest('Use an isolated Linux container with executable temporary files')
        (self.repo/'.env').write_text('synthetic-private-canary')

    def run_cli(self,*args,**env):
        return subprocess.run(['sh',str(self.repo/'tools/runtime/core'),'finance',*args],
                              cwd=self.temp.name,env={**self.env,**env},capture_output=True,text=True)

    def calls(self):
        return [json.loads(line) for line in self.log.read_text().splitlines()] if self.log.exists() else []

    def test_deploy_uses_correct_context_compose_and_service_scope(self):
        result=self.run_cli('deploy');self.assertEqual(0,result.returncode,result.stderr)
        calls=self.calls();self.assertEqual(4,len(calls))
        prefix=['compose','-p','nas','--env-file','.env','-f','docker-compose.yml','-f','tools/runtime/finance-compose.override.yml','--profile','finance']
        self.assertEqual(prefix+['build','dashboard','finance_worker'],calls[0]['args'])
        self.assertEqual(prefix+['up','-d','--no-deps','--force-recreate','dashboard','finance_worker'],calls[1]['args'])
        self.assertEqual(prefix+['ps','dashboard','finance_worker'],calls[2]['args'])
        self.assertEqual(['-m','core.finance.doctor','-p','nas','--env-file','.env','-f','docker-compose.yml','-f','tools/runtime/finance-compose.override.yml','--worker','--wait','20'],calls[3]['args'])
        self.assertEqual('finance',calls[3]['profiles'])
        for call in calls:
            self.assertEqual(str(self.repo),call['context']);self.assertEqual(str(self.repo),call['cwd'])
            self.assertEqual('false',call['enabled'])
        self.assertEqual('synthetic-private-canary',(self.repo/'.env').read_text())
        self.assertNotIn('synthetic-private-canary',result.stdout+result.stderr)

    def test_status_is_read_only_and_uses_same_config(self):
        result=self.run_cli('status');self.assertEqual(0,result.returncode,result.stderr)
        calls=self.calls();self.assertEqual(2,len(calls))
        self.assertEqual(['ps','dashboard','finance_worker'],calls[0]['args'][-3:])
        self.assertEqual('python3',calls[1]['tool']);self.assertIn('--worker',calls[1]['args'])
        self.assertNotIn('--wait',calls[1]['args'])

    def test_failed_build_never_recreates_services(self):
        result=self.run_cli('deploy',BUILD_EXIT='7')
        self.assertEqual(7,result.returncode);self.assertEqual(1,len(self.calls()))

    def test_failed_up_never_reports_successful_diagnosis(self):
        result=self.run_cli('deploy',UP_EXIT='9')
        self.assertEqual(9,result.returncode);self.assertEqual(2,len(self.calls()))

    def test_failed_doctor_propagates_failure(self):
        self.assertEqual(11,self.run_cli('deploy',DOCTOR_EXIT='11').returncode)

    def test_unknown_action_or_extra_arguments_do_not_call_docker(self):
        for args in [(),('unknown',),('deploy','--unexpected')]:
            self.assertEqual(2,self.run_cli(*args).returncode)
        self.assertEqual([],self.calls())


if __name__=='__main__':unittest.main()
