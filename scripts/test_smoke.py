from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import threading
import unittest


class SmokeTest(unittest.TestCase):
    def setUp(self):
        self.temporary=tempfile.TemporaryDirectory();self.addCleanup(self.temporary.cleanup)
        self.root=Path(self.temporary.name);binary=self.root/'bin';binary.mkdir()
        self.rows={999:'pre-existing'};self.requests=[];self.fail_update=False;self.bad_id=False
        fixture=self
        class API(BaseHTTPRequestHandler):
            def log_message(self,*args):pass
            def do_GET(self):self.endpoint()
            def do_POST(self):self.endpoint()
            def do_PUT(self):self.endpoint()
            def do_DELETE(self):self.endpoint()
            def endpoint(self):
                fixture.requests.append((self.command,self.path))
                suffix=self.path.removeprefix('/api/tests');body=None;code=200
                value=json.loads(self.rfile.read(int(self.headers.get('Content-Length',0))))['value'] if self.command in ['POST','PUT'] else None
                if self.command=='POST':
                    if fixture.bad_id:body={'id':9007199254740992,'value':value};code=201
                    else:
                        id=max(fixture.rows)+1;fixture.rows[id]=value;body={'id':id,'value':value};code=201
                elif not suffix:body=[{'id':id,'value':v} for id,v in fixture.rows.items()]
                else:
                    id=int(suffix[1:])
                    if id not in fixture.rows:code=404;body={'message':'not found'}
                    elif self.command=='PUT' and fixture.fail_update:code=500;body={'message':'fixture failure'}
                    elif self.command=='DELETE':del fixture.rows[id];code=204
                    else:
                        if self.command=='PUT':fixture.rows[id]=value
                        body={'id':id,'value':fixture.rows[id]}
                payload=json.dumps(body).encode() if body is not None else b''
                self.send_response(code);self.send_header('Content-Length',str(len(payload)));self.end_headers();self.wfile.write(payload)
        self.server=ThreadingHTTPServer(('127.0.0.1',0),API)
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start()
        self.addCleanup(self.server.server_close);self.addCleanup(self.server.shutdown)
        curl=binary/'curl';curl.write_text('#!/usr/bin/env bash\nargs=("$@")\nargs[${#args[@]}-1]=http://127.0.0.1:'+str(self.server.server_port)+'${!#}\nargs[${#args[@]}-1]=${args[${#args[@]}-1]//https:\\/\\/fixture.ts.net/}\nexec '+shutil.which('curl')+' "${args[@]}"\n');curl.chmod(0o700)
        kube=binary/'kubectl';kube.write_text('''#!/usr/bin/env bash
printf '%s\\n' "$*" >> "$FIXTURE_ROOT/kube-calls"
if [[ $* == *'config view'* ]]; then cat "$FIXTURE_ROOT/server"; fi
''');kube.chmod(0o700)
        (self.root/'server').write_text('https://prod:6443')
        self.env={'PATH':str(binary)+':'+os.environ['PATH'],'FIXTURE_ROOT':str(self.root),'MORE_NAIVE_ENV':'prod','NAMESPACE':'more-naive-prod','PROXY_HTTPS_HOSTNAME':'fixture.ts.net','KUBE_CONTEXT':'prod','KUBE_SERVER':'https://prod:6443'}
        self.script=Path(__file__).with_name('smoke.sh')

    def invoke(self,*args,**changes):
        return subprocess.run(['bash',str(self.script),*args],env={**self.env,**changes},text=True,capture_output=True)

    def test_default_only_reads(self):
        r=self.invoke();self.assertEqual(r.returncode,0,r.stderr)
        self.assertEqual(self.requests,[('GET','/api/tests')]);self.assertEqual(self.rows,{999:'pre-existing'})

    def test_other_cluster_never_calls_api(self):
        (self.root/'server').write_text('https://other:6443');self.assertNotEqual(self.invoke().returncode,0);self.assertEqual(self.requests,[])

    def test_bad_origin_and_restart_without_optin_do_not_call_commands(self):
        for flags,changes in [([],{'PROXY_HTTPS_HOSTNAME':'http://fixture.ts.net'}),([],{'PROXY_HTTPS_HOSTNAME':'public.example.com'}),([],{'PROXY_HTTPS_HOSTNAME':'user:pass@fixture.ts.net'}),(['--restart-backend'],{}),([],{'MORE_NAIVE_ENV':'dev'})]:
            self.assertNotEqual(self.invoke(*flags,**changes).returncode,0)
        self.assertFalse((self.root/'kube-calls').exists());self.assertEqual(self.requests,[])

    def test_success_cleans_only_owned_rows_and_restarts_opted_in_workloads(self):
        r=self.invoke('--allow-write','--restart-backend','--restart-db');self.assertEqual(r.returncode,0,r.stderr+r.stdout)
        self.assertEqual(self.rows,{999:'pre-existing'})
        self.assertNotIn(('DELETE','/api/tests/999'),self.requests)
        calls=(self.root/'kube-calls').read_text();self.assertIn('rollout restart deployment/backend',calls);self.assertIn('rollout restart statefulset/postgres',calls)

    def test_partial_failure_cleans_only_owned_rows(self):
        self.fail_update=True;r=self.invoke('--allow-write');self.assertNotEqual(r.returncode,0)
        self.assertEqual(self.rows,{999:'pre-existing'});self.assertNotIn(('DELETE','/api/tests/999'),self.requests)

    def test_unsafe_integer_id_is_never_used_for_cleanup(self):
        self.bad_id=True;r=self.invoke('--allow-write');self.assertNotEqual(r.returncode,0)
        self.assertFalse(any(method=='DELETE' for method,path in self.requests));self.assertEqual(self.rows,{999:'pre-existing'})


if __name__=='__main__':unittest.main()
