from pathlib import Path
import json, re
import pypdfium2 as pdfium
from PIL import Image, ImageDraw

root=Path(__file__).resolve().parent
pdf=pdfium.PdfDocument(root/'final.pdf')
out=root/'render'
out.mkdir(exist_ok=True)
for i in range(len(pdf)):
    pdf[i].render(scale=1.3).to_pil().save(out/f'page-{i+1:02d}.png')
for i in range(0,len(pdf),2):
    pages=[Image.open(out/f'page-{j+1:02d}.png') for j in range(i,min(i+2,len(pdf)))]
    sheet=Image.new('RGB',(pages[0].width,sum(p.height+28 for p in pages)), '#dddddd')
    draw=ImageDraw.Draw(sheet)
    y=0
    for j,p in enumerate(pages):
        draw.text((10,y+6),f'Page {i+j+1}',fill='black')
        sheet.paste(p,(0,y+28)); y+=p.height+28
    sheet.save(out/f'sheet-{i//2+1:02d}.png')

data=json.loads((root/'cases.json').read_text(encoding='utf-8'))
ids=[row[0] for m in data for row in m['cases']]
text='\n'.join(p.get_textpage().get_text_range() for p in pdf)
missing=[ident for ident in ids if ident not in text]
assert not missing, missing
outside=[]
for i,p in enumerate(pdf):
    tp=p.get_textpage()
    w,h=p.get_size()
    for j in range(tp.count_chars()):
        char=tp.get_text_range(j,1)
        if not char.strip():continue
        x0,y0,x1,y1=tp.get_charbox(j)
        if x0<30 or y0<25 or x1>w-28 or y1>h-20:
            outside.append((i+1,char,(x0,y0,x1,y1)))
assert not outside,outside[:10]
assert 'John Lloyd' not in text
assert 'admin@gmail' not in text
report={'pages':len(pdf),'cases':len(ids),'all_ids_present':True,'text_within_page_bounds':True,'foreign_author_and_credentials_removed':True}
(root/'verification.json').write_text(json.dumps(report,indent=2))
print(json.dumps(report))
