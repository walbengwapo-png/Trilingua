from pathlib import Path
import sys,os,json,time,hashlib,runpy
from urllib.parse import urlsplit
root=Path(r'C:\dev\Trilingua');sys.path.insert(0,str(root/'trilingua-code/Model'))
packet=root/'output/ocr-acceptance/lion-mouse-review-2026-10-26'
evidence=root/'output/reviews/ocr-ai-coordinator-2026-10-26'
paths=list((packet/'incoming').iterdir())+[packet/'workflow.json',packet/'corpus-review.json',root/'trilingua-code/.env']
before={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}
runs=packet/'coordinator-runs';earlier=set(runs.iterdir()) if runs.exists() else set()
import requests
original=requests.sessions.Session.request
calls=[]
def observed(self,method,url,*args,**kwargs):
 parsed=urlsplit(url);start=time.monotonic();row={'method':method,'host':parsed.hostname,'path':parsed.path}
 try:
  response=original(self,method,url,*args,**kwargs);row['http_status']=response.status_code;return response
 except Exception as exc:row['exception_type']=type(exc).__name__;raise
 finally:
  row['elapsed_seconds']=round(time.monotonic()-start,3);calls.append(row)
  (evidence/'observed-provider-requests.json').write_text(json.dumps(calls,indent=2),encoding='utf-8')
requests.sessions.Session.request=observed
started=time.monotonic()
try:
 sys.argv=['tools.ocr_kit','coordinate','--workspace',str(packet)]
 runpy.run_module('tools.ocr_kit',run_name='__main__')
finally:
 requests.sessions.Session.request=original
 changed=[p for p,h in before.items() if hashlib.sha256(Path(p).read_bytes()).hexdigest()!=h]
 created=list(set(runs.iterdir())-earlier) if runs.exists() else []
 status={'entrypoint':'python -m tools.ocr_kit coordinate','elapsed_seconds':round(time.monotonic()-started,3),
   'observed_http_calls':calls,'canonical_files_or_env_changed':changed,'new_runs':[str(p) for p in created]}
 if len(created)==1:
  result=json.loads((created[0]/'coordinator.json').read_text(encoding='utf-8'))
  status.update(status=result['status'],decision=result.get('decision'),response_model=result.get('response_model'),
    proposals=result['proposals'],approval_issued=result['approval_issued'],live_configuration_changed=result['live_configuration_changed'])
 (evidence/'live-run.json').write_text(json.dumps(status,indent=2,ensure_ascii=False),encoding='utf-8')
 print('LIVE RESULT:',json.dumps(status,ensure_ascii=False))
 assert not changed
