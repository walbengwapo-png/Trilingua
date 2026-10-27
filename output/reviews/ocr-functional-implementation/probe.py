from pathlib import Path
import sys,json,hashlib,importlib.util
root=Path(r'C:\dev\Trilingua');sys.path.insert(0,str(root/'trilingua-code/Model'))
from config.environment import load_engine_environment
load_engine_environment(root/'trilingua-code/.env')
import fitz
from document.ocr_extractor import recognize_image,SETTINGS
from document.image_reconstructor import source_image,estimate_style,prepare_action,ImageHold,FONT_ROOT
oldpath=root/'output/reviews/ocr-functional-implementation/baseline/old_image_reconstructor.py'
spec=importlib.util.spec_from_file_location('old_renderer',oldpath);old=importlib.util.module_from_spec(spec);spec.loader.exec_module(old);old.FONT_ROOT=FONT_ROOT
source=Path(r'C:\Users\walbe\Downloads\Lion_and_Mouse_2_pages_10_blocks_2_image_text.pdf')
result={'purpose':'diagnostic_only','acceptance_evidence':False,'provider_calls':0,'settings':SETTINGS,'input_sha256':hashlib.sha256(source.read_bytes()).hexdigest(),'regions':[]}
with fitz.open(source) as doc:
 for page,xref in [(0,14),(1,23)]:
  image=source_image(doc,xref);box=doc[page].get_image_rects(xref)[0]
  for b in recognize_image(image,'eng',page,image.size):
   words=b['ocr']['words'];style=estimate_style(image,words,box.width/image.width);raw=b['position'];sx=box.width/image.width;sy=box.height/image.height
   target=fitz.Rect(box.x0+raw[0]*sx-1,box.y0+raw[1]*sy-1,box.x0+raw[2]*sx+1,box.y0+raw[3]*sy+style['initial_size']*.5)&box
   row={'page':page+1,'xref':xref,'text':b['text'],'retry':b['ocr']['retry'],'minimum_confidence':min(w['confidence'] for w in words),'style':style}
   for name,module in [('old',old),('new',sys.modules['document.image_reconstructor'])]:
    try:
     action=module.prepare_action(image,words,b['text'],box,target,style['font_id'],style['initial_size'])
     row[name]={'status':'planned_source_text_only','fit':action['fit'],'mask_sha256':action['mask_sha256']}
    except Exception as e:row[name]={'status':'held','reason':str(e)}
   result['regions'].append(row)
path=root/'output/reviews/ocr-functional-implementation/diagnostic.json';path.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
for r in result['regions']:print(json.dumps(r,ensure_ascii=True))
