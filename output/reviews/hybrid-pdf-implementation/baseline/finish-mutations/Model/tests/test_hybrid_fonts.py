"""Run unchanged on Windows and Linux; fonts are repository assets on both."""
import json
import unicodedata
import fitz
import pytest
from document.image_reconstructor import FONT_ROOT, font_asset, fit_text

TEXTS=['English words: café, résumé, “quotes”.', 'Cebuano: maó kini, bag-ong hubad, ñ.',
       'Filipino: mga salita, á, é, í, ó, ú, ü, ñ.']


@pytest.mark.parametrize('font_id',json.loads((FONT_ROOT/'manifest.json').read_text(encoding='utf-8'))['fonts'])
@pytest.mark.parametrize('text',TEXTS)
def test_packaged_fonts_embed_and_roundtrip_all_languages(tmp_path,font_id,text):
    path,item=font_asset(font_id)
    font=fitz.Font(fontfile=str(path))
    assert all(font.has_glyph(ord(c)) for c in text if not c.isspace())
    result=fit_text(text,[20,20,500,100],font_id,14)
    assert result['font_size']>=10 and result['font_sha256']==item['sha256']
    output=tmp_path/'font.pdf'
    with fitz.open() as doc:
        p=doc.new_page();p.insert_font(fontname='checked',fontfile=str(path))
        p.insert_text((20,50),text,fontname='checked',fontsize=14);doc.save(output)
    with fitz.open(output) as doc:assert text in doc[0].get_text()


def test_combining_accents_are_normalized_before_fit():
    fitted=fit_text('mao\u0301 kin\u00ed',[0,0,200,50],'NotoSans-Regular',14)
    assert unicodedata.is_normalized('NFC',fitted['text'])


def test_strict_native_punctuation_uses_packaged_fonts_without_host_paths(tmp_path,monkeypatch):
    import os
    from document.extractor import read_pdf
    from document.reconstructor import write_pdf_preserved
    source=tmp_path/'native.pdf';out=tmp_path/'out.pdf'
    with fitz.open() as doc:
        p=doc.new_page();p.insert_text((40,80),'Original sentence');doc.save(source)
    blocks=read_pdf(str(source));blocks[0].update(text='“Maó kini”',_original_text='Original sentence')
    exists=os.path.exists
    monkeypatch.setattr(os.path,'exists',lambda path:False if 'Windows' in str(path) and 'Fonts' in str(path) else exists(path))
    write_pdf_preserved(blocks,str(source),str(out),strict=True)
    with fitz.open(out) as doc:assert '“Maó' in doc[0].get_text()
