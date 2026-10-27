"""Fixed geometry/translation renderer tests. Not OCR or acceptance material."""
import io
import numpy as np
import fitz
from PIL import Image, ImageDraw, ImageFont
import pytest

from document.image_reconstructor import (ImageHold, FONT_ROOT, prepare_action, apply_actions,
    decode_mask, source_image, image_digest, occurrence_safety, validate_output, fit_text)


def geometry():
    image = Image.new('RGB', (600, 400), (245, 245, 245))
    draw = ImageDraw.Draw(image)
    font = ImageFont.truetype(str(FONT_ROOT/'NotoSans-Regular.ttf'), 24)
    draw.text((40, 70), 'SOURCE', font=font, fill=(20, 35, 60))
    box = draw.textbbox((40,70), 'SOURCE', font=font)
    return image, [{'text':'SOURCE', 'position':list(box), 'confidence':99}]


def action_for(image, words, text='Bag-ong hubad: maó, ñ, á.'):
    return prepare_action(image, words, text, [0,0,600,400], [35,65,350,120], initial_size=18)


def document(tmp_path, image):
    stream = io.BytesIO(); image.save(stream,'PNG')
    path = tmp_path/'geometry.pdf'
    with fitz.open() as doc:
        p=doc.new_page(width=600,height=400)
        p.insert_image(p.rect,stream=stream.getvalue())
        doc.save(path)
    return path


@pytest.mark.parametrize('target',['English replacement: café, ñ.', 'Cebuano: maó, bag-ong hubad.', 'Filipino: bagong salin, ñ, á.'])
def test_true_pixel_cleanup_and_visible_searchable_target(tmp_path,target):
    image, words = geometry()
    source = document(tmp_path, image)
    action = action_for(image,words,target)
    mask = decode_mask(action)
    with fitz.open(source) as doc:
        xref = doc[0].get_images()[0][0]
        action.update(page=0,xref=xref,region_id='fixed-region')
        apply_actions(doc,[action])
        output=tmp_path/'edited.pdf';doc.save(output,garbage=4,deflate=True)
    validate_output(output,[action])
    with fitz.open(output) as doc:
        pixels = np.array(source_image(doc,doc[0].get_images()[0][0]))
        assert np.array_equal(pixels[~mask],np.array(image)[~mask])
        assert (pixels[mask] == [245,245,245]).all()
        assert 'SOURCE' not in doc[0].get_text()
        assert target in doc[0].get_text()
        assert image_digest(source_image(doc,doc[0].get_images()[0][0])) != image_digest(image)


@pytest.mark.parametrize('background',['gradient','texture','photo'])
def test_nonflat_backgrounds_are_held(background):
    image, words = geometry()
    a = np.array(image)
    if background == 'gradient': a[:50] = np.arange(600)[None,:,None]//5
    else: a[:50] = np.random.default_rng(123).integers(0,255,(50,600,3),dtype=np.uint8)
    with pytest.raises(ImageHold,match='background|Background'):
        action_for(Image.fromarray(a),words)


def test_rules_neighbors_and_low_confidence_are_not_erased():
    image,words=geometry();draw=ImageDraw.Draw(image)
    draw.line((0,90,599,90),fill='black',width=2)
    with pytest.raises(ImageHold,match='rules|protected'):
        action_for(image,words)
    image,words=geometry()
    with pytest.raises(ImageHold,match='neighbor|protected|samples'):
        prepare_action(image,words,'Fixed',[0,0,600,400],[35,65,350,120],exclusions=[words[0]['position']])
    words[0]['confidence']=20
    with pytest.raises(ImageHold,match='confidence'): action_for(image,words)


def test_fit_hold_and_shared_occurrences(tmp_path):
    with pytest.raises(ImageHold,match='fit'):
        fit_text('Long target '*100,[0,0,50,20],'NotoSans-Regular',12)
    image,words=geometry();source=document(tmp_path,image)
    with fitz.open(source) as doc:
        xref=doc[0].get_images()[0][0]
        p=doc.new_page(width=600,height=400);p.insert_image(p.rect,xref=xref)
        with pytest.raises(ImageHold,match='Shared'): occurrence_safety(doc,0,xref)


@pytest.mark.parametrize('kind',['alpha','clip','overlap','rotation'])
def test_unsafe_occurrences_are_held_before_editing(tmp_path,kind):
    image,_=geometry()
    if kind=='alpha':image=image.convert('RGBA');image.putalpha(150)
    source=document(tmp_path,image)
    with fitz.open(source) as doc:
        page=doc[0];xref=page.get_images()[0][0]
        if kind=='clip':
            stream=page.get_contents()[0]
            doc.update_stream(stream,b'q 0 0 100 100 re W n\n'+doc.xref_stream(stream)+b'\nQ')
        elif kind=='rotation':page.set_rotation(90)
        elif kind=='overlap':
            stream=io.BytesIO();Image.new('RGB',(20,20),'red').save(stream,'PNG')
            page.insert_image(fitz.Rect(400,0,500,100),stream=stream.getvalue())
        with pytest.raises(ImageHold):occurrence_safety(doc,0,xref)


def test_single_assembly_keeps_page_geometry(tmp_path):
    from document.reconstructor import write_pdf_preserved
    image,words=geometry();source=document(tmp_path,image)
    action=action_for(image,words)
    with fitz.open(source) as doc:
        action.update(page=0,xref=doc[0].get_images()[0][0],region_id='fixed')
    output=tmp_path/'assembled.pdf'
    report=write_pdf_preserved([],source,str(output),strict=True,image_actions=[action])
    assert report['status']=='passed'
    with fitz.open(output) as doc:
        assert len(doc)==1 and 'maó' in doc[0].get_text()


def test_mixed_assembly_retains_unmodified_asset_native_links_and_vectors(tmp_path):
    from document.extractor import read_pdf
    from document.reconstructor import write_pdf_preserved
    image,words=geometry();stream=io.BytesIO();image.save(stream,'PNG')
    original=tmp_path/'mixed.pdf'
    with fitz.open() as doc:
        page=doc.new_page(width=600,height=600)
        xref=page.insert_image(fitz.Rect(0,0,600,400),stream=stream.getvalue())
        page.insert_text((40,460),'Native caption')
        page.insert_link({'kind':fitz.LINK_URI,'from':fitz.Rect(40,445,140,465),'uri':'https://example.com/'})
        page.draw_line((20,490),(580,490))
        icon=io.BytesIO();Image.new('RGB',(20,20),'red').save(icon,'PNG')
        keep=page.insert_image(fitz.Rect(500,500,520,520),stream=icon.getvalue())
        expected=doc.extract_image(keep)['image'];doc.save(original)
    native=read_pdf(str(original));native[0].update(text='Bag-ong caption',_original_text='Native caption')
    action=action_for(image,words);action.update(page=0,xref=xref,region_id='fixed')
    output=tmp_path/'out.pdf'
    write_pdf_preserved(native,str(original),str(output),strict=True,image_actions=[action])
    with fitz.open(output) as doc:
        assert len(doc)==1 and doc[0].rect == fitz.Rect(0,0,600,600)
        assert 'Bag-ong caption' in ' '.join(doc[0].get_text().split())
        assert any(link.get('uri') == 'https://example.com/' for link in doc[0].get_links())
        assert doc[0].get_drawings()
        keep=next(i['xref'] for i in doc[0].get_image_info(xrefs=True) if i['bbox']==(500.,500.,520.,520.))
        assert doc.extract_image(keep)['image']==expected
