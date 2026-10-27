from pathlib import Path
import sys,os,json,re,hashlib,uuid,codecs
root=Path(r'C:\dev\Trilingua');sys.path.insert(0,str(root/'trilingua-code/Model'))
from document.artifact_auth import generate_key,key_file,production_key,sign,verify
from config.environment import load_engine_environment
private=Path(os.environ['LOCALAPPDATA'])/'TriLingua/ocr/keys'
assert private.is_dir() and not private.resolve().is_relative_to(root.resolve())
evidence=root/'output/reviews/ocr-key-setup-2026-10-27';evidence.mkdir(exist_ok=False)
env=root/'trilingua-code/.env';original=env.read_bytes()
backup=private/('environment-backup-'+uuid.uuid4().hex+'.bin')
with backup.open('xb') as stream:stream.write(original)
assert backup.read_bytes()==original
paths={'OCR_ACCEPTANCE_KEY_FILE':private/'acceptance.json','OCR_PLAN_KEY_FILE':private/'render-plan.json'}
created={}
for name,path in paths.items():
 purpose='acceptance' if name=='OCR_ACCEPTANCE_KEY_FILE' else 'render-plan'
 created[name]=not path.exists()
 if created[name]:generate_key(path,purpose)
 key,secret=key_file(path,purpose);production_key(key)
 assert len(secret)==32
assert key_file(paths['OCR_ACCEPTANCE_KEY_FILE'],'acceptance')[1]!=key_file(paths['OCR_PLAN_KEY_FILE'],'render-plan')[1]
bom=codecs.BOM_UTF8 if original.startswith(codecs.BOM_UTF8) else b''
text=original.decode('utf-8-sig');newline='\r\n' if '\r\n' in text else '\n'
lines=text.splitlines(keepends=True)
pattern=re.compile(r'^\s*(OCR_ACCEPTANCE_KEY_FILE|OCR_PLAN_KEY_FILE)\s*=')
for name,path in paths.items():
 matches=[i for i,line in enumerate(lines) if re.match(r'^\s*'+name+r'\s*=',line)]
 assert len(matches)<=1,'Duplicate key-path entries need inspection'
 replacement=name+'="'+path.as_posix()+'"'+newline
 if matches:
  previous=lines[matches[0]].strip().partition('=')[2].strip().strip('"\'')
  assert not previous or Path(previous).resolve()==path.resolve(),'Existing configured keys must be reused, not rotated'
  lines[matches[0]]=replacement
 else:
  if lines and not lines[-1].endswith(('\r','\n')):lines[-1]+=newline
  lines.append(replacement)
updated=''.join(lines)
without=lambda value:''.join(line for line in value.splitlines(keepends=True) if not pattern.match(line)).rstrip('\r\n')
assert without(text)==without(updated),'Unrelated environment entries must stay byte-for-byte equivalent'
assert env.read_bytes()==original,'Environment changed concurrently; do not overwrite'
new_bytes=bom+updated.encode('utf-8');env.write_bytes(new_bytes)
assert env.read_bytes()==new_bytes
for name in paths:os.environ.pop(name,None)
load_engine_environment(env)
assert all(Path(os.environ[name]).resolve()==path.resolve() for name,path in paths.items())
body={'configuration_probe':'render-plan signing only; not a translation or acceptance report'}
signed=sign(body,paths['OCR_PLAN_KEY_FILE'],'render-plan');verify(signed,paths['OCR_PLAN_KEY_FILE'],'render-plan')
try:verify(dict(signed,configuration_probe='tampered'),paths['OCR_PLAN_KEY_FILE'],'render-plan')
except ValueError:tamper_rejected=True
else:raise AssertionError('Tampered signature was accepted')
from document.ocr_extractor import require_ready,OCRUnavailable
holds={}
for category in ('scan','photo','screenshot'):
 try:require_ready('English',category)
 except OCRUnavailable:holds[category]=True
 else:raise AssertionError('No acceptance scope may be opened by key setup alone')
report={'date':'2026-10-27','key_directory':str(private),'keys':{
 name:{'configured':True,'path':str(path),'created':created[name],'reused':not created[name],
       'purpose':'acceptance' if name=='OCR_ACCEPTANCE_KEY_FILE' else 'render-plan','validated':True}
 for name,path in paths.items()},'environment_original_sha256':hashlib.sha256(original).hexdigest(),
 'environment_current_sha256':hashlib.sha256(new_bytes).hexdigest(),'private_environment_backup_created':True,
 'only_key_path_entries_changed':True,'render_signing_round_trip_passed':True,'tampering_rejected':tamper_rejected,
 'acceptance_report_configured':bool(os.environ.get('OCR_ACCEPTANCE_REPORT')),
 'corpus_manifest_configured':bool(os.environ.get('OCR_CORPUS_MANIFEST')),'english_acceptance_still_held':holds,
 'acceptance_report_issued':False,'service_restarted':False,'provider_calls':0}
(evidence/'setup-result.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
print(json.dumps(report,indent=2))
