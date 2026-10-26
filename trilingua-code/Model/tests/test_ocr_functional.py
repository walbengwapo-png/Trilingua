"""Generated geometry only; no acquisition/reference acceptance evidence."""
from html import escape
import pytest
from PIL import Image,ImageDraw,ImageFont
from document.ocr_geometry import parse_hocr,transform_words,validate_baselines
from document.image_reconstructor import FONT_ROOT,prepare_action,ImageHold


def hocr(words, baseline='0 -5', box='0 0 1000 300'):
    spans=''.join(f'<span class="ocrx_word" title="bbox {x0} {y0} {x1} {y1}; x_wconf {confidence}">{escape(text)}</span>'
                  for text,confidence,(x0,y0,x1,y1) in words)
    return (f'<html><body><p class="ocr_par" id="p1"><span class="ocr_line" id="l1" '
            f'title="bbox {box}; baseline {baseline}; x_size 50; x_descenders 12; x_ascenders 14">{spans}</span></p></body></html>').encode()


def descender_geometry():
    image=Image.new('RGB',(1200,300),(245,245,245));draw=ImageDraw.Draw(image)
    font=ImageFont.truetype(str(FONT_ROOT/'NotoSerif-Regular.ttf'),48)
    words=[];x=40
    for text in ['see','that','even','a','Mouse','can','help','a','Lion.']:
        draw.text((x,120),text,font=font,fill=(20,35,60),anchor='ls')
        box=list(draw.textbbox((x,120),text,font=font,anchor='ls'))
        words.append({'text':text,'confidence':99,'line':'line1','position':box})
        x+=font.getlength(text+' ')
    bounds=[min(w['position'][0] for w in words),min(w['position'][1] for w in words),
            max(w['position'][2] for w in words),max(w['position'][3] for w in words)]
    geometry={'position':bounds,'baseline':[0,120-bounds[3]],'x_descenders':font.getmetrics()[1],'x_size':48}
    for word in words:word['line_geometry']=geometry
    return image,words


def test_straight_text_with_normal_descenders_is_not_curved():
    image,words=descender_geometry()
    validate_baselines(words)
    action=prepare_action(image,words,'Fixed target',[0,0,1200,300],[35,65,1165,180],initial_size=18)
    assert action['fit']['text']=='Fixed target'


@pytest.mark.parametrize('fault',['slope','curved','missing','nonfinite','no_line'])
def test_real_skew_and_inconsistent_line_geometry_still_hold(fault):
    _,words=descender_geometry()
    if fault=='slope':words[0]['line_geometry']['baseline'][0]=.2
    if fault=='curved':words[-1]['position'][1]+=40;words[-1]['position'][3]+=40
    if fault=='missing':words[0]['line_geometry']['baseline']=None
    if fault=='nonfinite':words[0]['line_geometry']['baseline'][0]=float('nan')
    if fault=='no_line':
        for word in words:word['line_geometry']=None
    with pytest.raises(ValueError):validate_baselines(words)


def test_hocr_entities_confidence_and_inverse_geometry_are_preserved():
    raw=hocr([('maó & ñ "quote"',98.25,[20,40,180,80])],baseline='.01 -10',box='10 30 200 90')
    words=next(iter(parse_hocr(raw,(300,300)).values()))
    assert words[0]['text']=='maó & ñ "quote"' and words[0]['confidence']==98.25
    mapped=transform_words(words,.5,.25,2,3)[0]
    assert mapped['position']==[12,13,92,23]
    assert mapped['line_geometry']['baseline']==[.005,-2.5]
    assert mapped['line_geometry']['x_descenders']==3


@pytest.mark.parametrize('box',['0 0 nan 20','0 0 301 20','0 0 20 0'])
def test_invalid_hocr_boxes_fail_closed(box):
    raw=hocr([('source',99,[1,1,20,20])]).replace(b'bbox 1 1 20 20',('bbox '+box).encode())
    with pytest.raises(ValueError):parse_hocr(raw,(300,300))


@pytest.mark.parametrize('changed',['none','punctuation','case','diacritic','confidence','budget'])
def test_uncertain_retry_requires_exact_text_and_all_confident_words(monkeypatch,changed):
    from document import ocr_extractor as ocr
    original=parse_hocr(hocr([('maó.',61,[40,50,100,90])]),(1000,300))
    variant={'none':'maó.','punctuation':'maó','case':'Maó.','diacritic':'mao.'}.get(changed,'maó.')
    retry=parse_hocr(hocr([(variant,79 if changed=='confidence' else 95,[90,100,170,140])],
                           box='80 80 200 160',baseline='0 -20'),(267,267))
    calls=[]
    def recognize(image,*args):
        calls.append(image.size)
        return original if len(calls)==1 else retry
    monkeypatch.setattr(ocr,'_recognize_pass',recognize)
    budget={'remaining':0 if changed=='budget' else 1_000_000}
    block=ocr.recognize_image(Image.new('RGB',(1000,300),'white'),'eng',page_size=(1000,300),retry_budget=budget)[0]
    assert block['text']=='maó.'
    if changed=='none':
        assert block['ocr']['retry']=='accepted' and not block['ocr']['uncertain_words']
        assert block['ocr']['words'][0]['position']==pytest.approx([37.4157,44.9064,97.3408,74.8689],abs=.01)
        validate_baselines(block['ocr']['words'])
    else:
        assert block['ocr']['retry']!='accepted' and block['ocr']['uncertain_words']
        assert block['ocr']['words'][0]['position']==[40,50,100,90]
    assert len(calls)==(1 if changed=='budget' else 2)
    assert 0 <= budget['remaining'] <= 1_000_000


def test_confident_paragraphs_are_not_retried(monkeypatch):
    from document import ocr_extractor as ocr
    calls=[]
    def recognize(image,*args):
        calls.append(image.size)
        return parse_hocr(hocr([('source',99,[40,50,100,90])]),image.size)
    monkeypatch.setattr(ocr,'_recognize_pass',recognize)
    assert ocr.recognize_image(Image.new('RGB',(1000,300)),'eng')[0]['ocr']['retry']=='not_needed'
    assert len(calls)==1


def test_retry_does_not_extend_ocr_time_allowance(monkeypatch):
    from document import ocr_extractor as ocr
    now=[100.0];calls=[]
    monkeypatch.setattr(ocr.time,'monotonic',lambda:now[0])
    def recognize(image,*args):
        calls.append(image.size);now[0]+=61
        return parse_hocr(hocr([('source',61,[40,50,100,90])]),image.size)
    monkeypatch.setattr(ocr,'_recognize_pass',recognize)
    assert ocr.recognize_image(Image.new('RGB',(1000,300)),'eng')[0]['ocr']['retry']=='time_budget_hold'
    assert len(calls)==1


def test_letter_stems_in_short_strips_are_glyphs_but_long_rules_hold():
    image=Image.new('RGB',(1200,204),'white');draw=ImageDraw.Draw(image)
    font=ImageFont.truetype(str(FONT_ROOT/'NotoSerif-Regular.ttf'),48)
    text='I will help';draw.text((20,85),text,font=font,fill='black',anchor='ls')
    bounds=list(draw.textbbox((20,85),text,font=font,anchor='ls'))
    words=[{'text':text,'position':bounds,'confidence':99,'line':1,
            'line_geometry':{'position':bounds,'baseline':[0,85-bounds[3]],'x_descenders':14}}]
    assert prepare_action(image,words,'Target',[0,0,1200,204],[15,30,600,120])['fit']['text']=='Target'
    draw.line((450,0,450,203),fill='black',width=2)
    with pytest.raises(ImageHold,match='rules|borders'):
        prepare_action(image,words,'Target',[0,0,1200,204],[15,30,600,120])


def test_font_estimate_ignores_ocr_box_padding():
    from document.image_reconstructor import estimate_style
    image,words=descender_geometry()
    padded=[dict(w,position=[w['position'][0]-3,w['position'][1]-3,
                             w['position'][2]+3,w['position'][3]+3]) for w in words]
    for candidate in (words,padded):
        style=estimate_style(image,candidate,1/3)
        assert style['font_id']=='NotoSerif-Regular'
        assert style['initial_size']==pytest.approx(16,abs=1)


@pytest.mark.parametrize('edges,expected',[
    ([(48,561),(48,550),(48,180)],'left'),
    ([(100,500),(150,450),(200,400)],'center'),
    ([(48,560),(70,560),(400,560)],'right'),
    ([(48,560),(48,560),(48,180)],'justify')])
def test_native_alignment_uses_lines_instead_of_union_box(edges,expected):
    from document.extractor import _detect_block_alignment
    lines=[{'x0':a,'text_x1':b} for a,b in edges]
    assert _detect_block_alignment([min(a for a,b in edges),50,max(b for a,b in edges),150],612,792,lines)==expected


def test_unchanged_native_content_is_counted_as_passthrough_and_remains_editable(tmp_path,document_pipeline):
    from document.pdf_regions import sha256
    from document.regenerator import apply_overrides
    source=tmp_path/'unchanged.pdf';source.write_bytes(b'test source identity only')
    sidecar={'blocks':[{'block_index':0,'region_id':'same','text':'Credit: Walben','source_text':'Credit: Walben'},
                       {'block_index':1,'region_id':'changed','text':'Bag-ong teksto','source_text':'Source text'}]}
    extraction={'original_sha256':sha256(source),'regions':[
        {'region_id':'same','status':'pending','page':0},
        {'region_id':'changed','status':'pending','page':0}],'pages':[{'page':0}],'warnings':[]}
    document_pipeline._pdf_sidecar(sidecar,extraction,{},str(source))
    assert sidecar['content_summary']['translated']==1 and sidecar['content_summary']['passthrough']==1
    edited=apply_overrides(sidecar['blocks'],{0:'Edited credit'})[0]
    assert edited['text']=='Edited credit' and not edited.get('passthrough')


def test_regeneration_recounts_identity_content_after_an_edit(tmp_path,document_pipeline):
    import fitz
    from document.extractor import read_pdf
    from document.pdf_regions import sha256
    from document.regenerator import rich_block_entry,reconstruct_from_sidecar
    source=tmp_path/'native.pdf'
    with fitz.open() as doc:
        doc.new_page().insert_text((48,100),'Credit: Walben')
        doc.save(source)
    block=dict(read_pdf(str(source))[0],region_id='same')
    sidecar={'format':'.pdf','blocks':[rich_block_entry(0,block,block['text'])]}
    extraction={'original_sha256':sha256(source),'regions':[
        {'region_id':'same','status':'pending','page':0}], 'pages':[{'page':0}],'warnings':[]}
    document_pipeline._pdf_sidecar(sidecar,extraction,{},str(source))
    assert sidecar['content_summary']['passthrough']==1
    output=tmp_path/'edited.pdf'
    reconstruct_from_sidecar(sidecar,{0:'New credit'},str(source),str(output))
    assert sidecar['content_summary']['translated']==1 and sidecar['content_summary']['passthrough']==0
    with fitz.open(output) as doc:assert 'New credit' in doc[0].get_text()
