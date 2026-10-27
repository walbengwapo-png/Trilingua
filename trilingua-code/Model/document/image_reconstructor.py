"""Flat-background pixel editing. Pure planning precedes any PDF mutation."""
import base64
import hashlib
import json
import math
from pathlib import Path
import re
import unicodedata
import zlib

import fitz
from PIL import Image

FONT_ROOT = Path(__file__).resolve().parents[1] / 'assets' / 'fonts'
ALGORITHM_VERSION = 3
MAX_PIXELS = 40_000_000
MAX_MASK_BYTES = 16_000_000


class ImageHold(ValueError):
    pass


def font_asset(font_id):
    manifest = json.loads((FONT_ROOT/'manifest.json').read_text(encoding='utf-8'))
    if manifest.get('version') != 1 or font_id not in manifest['fonts']:
        raise ImageHold('Unsupported font manifest or font ID')
    item = manifest['fonts'][font_id]
    path = FONT_ROOT/item['file']
    if path.parent != FONT_ROOT or hashlib.sha256(path.read_bytes()).hexdigest() != item['sha256']:
        raise ImageHold('Font hash mismatch')
    if hashlib.sha256((FONT_ROOT/item['license_file']).read_bytes()).hexdigest() != manifest['license_sha256']:
        raise ImageHold('Font license hash mismatch')
    return path, item


def fit_text(text, bbox, font_id, initial_size, alignment=0):
    text = unicodedata.normalize('NFC', text)
    path, item = font_asset(font_id)
    font = fitz.Font(fontfile=str(path))
    box = fitz.Rect(bbox)
    if not all(math.isfinite(v) for v in box) or box.is_empty or not math.isfinite(float(initial_size)):
        raise ImageHold('Invalid text fit geometry')
    if not text.strip() or len(text) > 100_000 or alignment not in (0, 1, 2):
        raise ImageHold('Invalid target text/alignment')
    if any(not font.has_glyph(ord(c)) for c in text if not c.isspace()):
        raise ImageHold('Missing target font glyph')
    size = min(float(initial_size), 72)
    minimum = max(10., size * .8)
    while size >= minimum - .01:
        lines = []
        for paragraph in text.split('\n'):
            line = ''
            for word in paragraph.split():
                if font.text_length(word, fontsize=size) > box.width:
                    break
                candidate = (line + ' ' + word).strip()
                if line and font.text_length(candidate, fontsize=size) > box.width:
                    lines.append(line)
                    line = word
                else:
                    line = candidate
            else:
                lines.append(line)
                continue
            break
        else:
            leading = size * max(1.25, font.ascender - font.descender)
            if leading * len(lines) <= box.height:
                return {'font_id': font_id, 'font_sha256': item['sha256'], 'font_size': size,
                        'lines': lines, 'leading': leading, 'alignment': alignment,
                        'bbox': list(box), 'text': text, 'initial_size': initial_size}
        size = round(size - .5, 2)
    raise ImageHold('Target does not fit at the 10 pt/bounded shrink minimum')


def decode_mask(action):
    width, height = action['image_size']
    if not isinstance(width, int) or not isinstance(height, int) or min(width, height) < 1 or width*height > MAX_PIXELS:
        raise ImageHold('Invalid mask dimensions')
    encoded = action['mask']
    if len(encoded) > MAX_MASK_BYTES * 4//3 + 4:
        raise ImageHold('Compressed mask limit exceeded')
    data = base64.b64decode(encoded, validate=True)
    decoder = zlib.decompressobj()
    raw = decoder.decompress(data, width*height + 1)
    if len(raw) != width*height or not decoder.eof or decoder.unused_data or decoder.unconsumed_tail:
        raise ImageHold('Invalid or unbounded mask payload')
    if hashlib.sha256(raw).hexdigest() != action.get('mask_sha256'):
        raise ImageHold('Mask hash mismatch')
    import numpy as np
    mask = np.frombuffer(raw, dtype=np.uint8).reshape(height, width)
    if not np.isin(mask, [0, 1]).all(): raise ImageHold('Mask is not binary')
    return mask.astype(bool)


def image_digest(image):
    return hashlib.sha256(image.tobytes()).hexdigest()


def prepare_action(image, words, target, image_bbox, target_bbox, font_id='NotoSans-Regular',
                   initial_size=14, exclusions=(), alignment=0):
    import cv2
    import numpy as np
    if image.mode != 'RGB' or image.width*image.height > MAX_PIXELS:
        raise ImageHold('Only bounded opaque RGB images are supported')
    pixels = np.array(image)
    geometry = np.zeros(pixels.shape[:2], np.uint8)
    for word in words:
        box = word['position']
        x0, y0, x1, y1 = [int(round(v)) for v in box]
        if min(x0, y0) < 0 or x1 > image.width or y1 > image.height or x1 <= x0 or y1 <= y0:
            raise ImageHold('Word geometry outside image')
        if word.get('confidence', 100) < 80:
            raise ImageHold('Low confidence word geometry')
        geometry[max(0,y0-2):min(image.height,y1+2), max(0,x0-2):min(image.width,x1+2)] = 1
    if not geometry.any(): raise ImageHold('No verified word geometry')
    from document.ocr_geometry import validate_baselines
    try:validate_baselines(words)
    except ValueError as exc:raise ImageHold(str(exc)) from exc
    protected = np.zeros_like(geometry)
    for box in exclusions:
        x0, y0, x1, y1 = map(int, box)
        protected[max(0,y0-2):min(image.height,y1+2), max(0,x0-2):min(image.width,x1+2)] = 1
    # Sample many interior/boundary pixels outside the word boxes.
    background_pixels = pixels[(geometry == 0) & (protected == 0)]
    if len(background_pixels) < image.width*image.height*.4:
        raise ImageHold('Insufficient background samples')
    background = np.median(background_pixels, axis=0)
    delta = np.empty(pixels.shape[:2], dtype=np.float32)
    for row in range(0, image.height, 64):
        delta[row:row+64] = np.max(np.abs(np.subtract(pixels[row:row+64], background, dtype=np.float32)), axis=2)
    foreground = (delta > 8).astype(np.uint8)
    horizontal = cv2.morphologyEx(foreground, cv2.MORPH_OPEN, np.ones((1, max(25,image.width//8)), np.uint8))
    # Short image strips otherwise mistake tall letter stems for table rules.
    glyph_height = float(np.median([w['position'][3]-w['position'][1] for w in words]))
    vertical = cv2.morphologyEx(foreground, cv2.MORPH_OPEN,
                               np.ones((max(25,image.height//8,math.ceil(glyph_height*1.5)),1), np.uint8))
    rules = np.zeros_like(geometry)
    for opened in (horizontal, vertical):
        n, labels, stats, _ = cv2.connectedComponentsWithStats(opened, connectivity=8)
        for label, (x,y,width,height,area) in enumerate(stats[1:], 1):
            if min(width,height) <= 3 and max(width,height) >= 25:
                rules[labels == label] = 1
    clean = (geometry == 0) & (protected == 0) & (rules == 0)
    if not clean.any() or np.quantile(delta[clean], .95) > 4:
        raise ImageHold('Non-flat background: texture, gradient or photograph')
    tiles = []
    for rows in np.array_split(np.arange(image.height), 5):
        for cols in np.array_split(np.arange(image.width), 5):
            area = np.ix_(rows, cols)
            values = pixels[area][clean[area]]
            if len(values): tiles.append(np.median(values, axis=0))
    if not tiles or np.max(np.ptp(np.array(tiles), axis=0)) > 2:
        raise ImageHold('Background spatial variation/gradient')
    source_box, target_box = fitz.Rect(image_bbox), fitz.Rect(target_bbox)
    sx,sy=image.width/source_box.width,image.height/source_box.height
    tx0,ty0,tx1,ty1=[int(round(v)) for v in ((target_box.x0-source_box.x0)*sx,
        (target_box.y0-source_box.y0)*sy,(target_box.x1-source_box.x0)*sx,(target_box.y1-source_box.y0)*sy)]
    if rules[max(0,ty0+1):min(image.height,ty1-1),max(0,tx0+1):min(image.width,tx1-1)].any():
        raise ImageHold('Target spans table rules or borders')
    glyphs = foreground & geometry
    if ((glyphs & protected) | (glyphs & rules)).any():
        raise ImageHold('Text intersects rules, borders or protected neighbors')
    count, labels, stats, _ = cv2.connectedComponentsWithStats(glyphs, connectivity=8)
    if count <= 1: raise ImageHold('No source glyphs in geometry')
    for x, y, width, height, area in stats[1:]:
        if width > image.width*.5 or height > image.height*.5:
            raise ImageHold('Stylized or non-glyph component')
    mask = cv2.dilate(glyphs, np.ones((3,3), np.uint8)) & geometry
    if (mask & protected).any(): raise ImageHold('Anti-alias mask touches neighbor')
    if mask.sum() > geometry.sum()*.7: raise ImageHold('Uncertain glyph mask')
    result = pixels.copy()
    fill = np.rint(background).astype(np.uint8)
    result[mask.astype(bool)] = fill
    for row in range(0, image.height, 64):
        residual = np.max(np.abs(np.subtract(result[row:row+64], background, dtype=np.float32)), axis=2) > 8
        if (residual & geometry[row:row+64].astype(bool)).any(): raise ImageHold('Residual source edges after cleanup')
    if not np.array_equal(result[mask == 0], pixels[mask == 0]): raise ImageHold('Outside-mask damage')
    encoded = zlib.compress(mask.tobytes(), 9)
    if len(encoded) > MAX_MASK_BYTES: raise ImageHold('Mask limit exceeded')
    fit = fit_text(target, target_bbox, font_id, initial_size, alignment)
    foreground_color = np.median(pixels[glyphs.astype(bool)], axis=0).round().astype(int).tolist()
    return {'algorithm_version': ALGORITHM_VERSION, 'image_size': list(image.size),
            'source_image_sha256': image_digest(image), 'mask': base64.b64encode(encoded).decode('ascii'),
            'mask_sha256':hashlib.sha256(mask.tobytes()).hexdigest(),
            'word_geometry':[w['position'] for w in words], 'exclusions':list(exclusions),
            'background': fill.tolist(), 'foreground': foreground_color, 'image_bbox': list(image_bbox),
            'fit': fit, 'rotation': 0}


def occurrence_safety(doc, page_number, xref):
    from document.pixel_budget import image_inventory, BUDGET_REASON
    page = doc[page_number]
    all_resources = [image for source_page in doc for image in source_page.get_images(full=True)]
    if any(image[2]*image[3] > MAX_PIXELS for image in all_resources):
        raise ImageHold('Source image exceeds 40 MP limit')
    inventory = image_inventory(doc)
    if xref in doc._hybrid_budget_held:
        raise ImageHold(BUDGET_REASON)
    occurrences = [(number, i) for number,images in enumerate(inventory) for i in images if i['xref'] == xref]
    if len(occurrences) != 1 or occurrences[0][0] != page_number or not xref:
        raise ImageHold('Shared/unresolved image occurrence')
    resources = [image for image in all_resources if image[0] == xref]
    if len(resources) != 1 or doc.get_ocgs() or doc.embfile_count():
        raise ImageHold('Shared resources, optional layers or embedded backups excluded')
    if page.rotation or page.cropbox != page.mediabox or page.get_xobjects():
        raise ImageHold('Rotated/cropped/form image excluded')
    info = occurrences[0][1]
    a,b,c,d,e,f = info['transform']
    if b or c or a <= 0 or d <= 0: raise ImageHold('Non-axis-aligned image')
    if abs(a/info['width']-d/info['height']) > .01*max(a/info['width'],d/info['height']):
        raise ImageHold('Nonuniform image stretch excluded')
    if any(i[0] == xref and i[1] for i in page.get_images(full=True)):
        raise ImageHold('Transparent image')
    source = b'\n'.join(doc.xref_stream(x) for x in page.get_contents())
    if re.search(rb'(?<![A-Za-z])(W\*?|gs)(?![A-Za-z])', source):
        raise ImageHold('Clipping/transparency state is not proven safe')
    box = fitz.Rect(info['bbox'])
    if not page.rect.contains(box): raise ImageHold('Clipped image')
    image_paints = [seq for seq,(kind,bounds) in enumerate(page.get_bboxlog())
                    if kind=='fill-image' and all(abs(a-b)<.001 for a,b in zip(bounds,box))]
    if len(image_paints)!=1:raise ImageHold('Image paint order is ambiguous')
    for other in inventory[page_number]:
        if other['xref'] != xref and (box & fitz.Rect(other['bbox'])).get_area() > 0:
            raise ImageHold('Overlapping image')
    if any((box & fitz.Rect(t['bbox'])).get_area() > 0 for t in page.get_texttrace()):
        raise ImageHold('Native or hidden text overlaps image')
    for drawing in page.get_drawings():
        # An opaque image covers earlier paths; later paths must remain protected.
        sequence = drawing.get('seqno')
        if isinstance(sequence,int) and sequence+(drawing.get('type')=='fs') < image_paints[0]:
            continue
        bounds = fitz.Rect(drawing['rect'])
        if drawing.get('type') in {'s','fs'}:
            half_width = float(drawing.get('width') or 0)/2
            bounds += (-half_width,-half_width,half_width,half_width)
        # A PDF hairline still paints even when its path rectangle has zero area.
        if (box & bounds).get_area() > 0 or (bounds.is_empty and
                box.x0 <= bounds.x1 and bounds.x0 <= box.x1 and box.y0 <= bounds.y1 and bounds.y0 <= box.y1):
            raise ImageHold('Drawing overlaps image')
    return info


def source_image(doc, xref):
    from document.pixel_budget import image_inventory, BUDGET_REASON
    image_inventory(doc)
    if xref in doc._hybrid_budget_held:
        raise ImageHold(BUDGET_REASON)
    width = int(doc.xref_get_key(xref,'Width')[1])
    height = int(doc.xref_get_key(xref,'Height')[1])
    if min(width,height) < 1 or width*height > MAX_PIXELS:
        raise ImageHold('Source image exceeds 40 MP limit')
    pix = fitz.Pixmap(doc, xref)
    if pix.alpha: raise ImageHold('Alpha image')
    if pix.colorspace != fitz.csRGB: pix = fitz.Pixmap(fitz.csRGB, pix)
    return Image.frombytes('RGB', (pix.width, pix.height), pix.samples)


def apply_actions(doc, actions):
    """Update only assets proven to have one occurrence; never global replace_image."""
    import numpy as np
    from document.pixel_budget import check_actions
    check_actions(actions)
    grouped = {}
    for action in actions:
        if action.get('algorithm_version') != ALGORITHM_VERSION: raise ImageHold('Mask version mismatch')
        grouped.setdefault((action['page'], action['xref']), []).append(action)
    prepared = []
    import os, tempfile
    with tempfile.TemporaryDirectory(prefix="clean-images-", dir=os.environ.get("OCR_JOB_SCRATCH")) as staging:
        for (page_number,xref), edits in grouped.items():
            info = occurrence_safety(doc, page_number, xref)
            original = source_image(doc, xref)
            pixels = np.array(original)
            combined = np.zeros(pixels.shape[:2], bool)
            for action in edits:
                if image_digest(original) != action['source_image_sha256'] or list(original.size) != action['image_size']:
                    raise ImageHold('Source image hash/size mismatch')
                if list(info['bbox']) != action['image_bbox']: raise ImageHold('Image transform mismatch')
                mask = decode_mask(action)
                allowed = np.zeros(mask.shape,bool)
                for x0,y0,x1,y1 in action['word_geometry']:
                    x0,y0,x1,y1 = [int(round(v)) for v in (x0,y0,x1,y1)]
                    allowed[max(0,y0-2):min(mask.shape[0],y1+2),max(0,x0-2):min(mask.shape[1],x1+2)] = True
                if (mask & ~allowed).any(): raise ImageHold('Mask outside approved word geometry')
                for x0,y0,x1,y1 in action.get('exclusions',[]):
                    if mask[max(0,int(y0)-2):min(mask.shape[0],int(y1)+2),max(0,int(x0)-2):min(mask.shape[1],int(x1)+2)].any():
                        raise ImageHold('Mask touches protected neighbor')
                if (combined & mask).any(): raise ImageHold('Overlapping edit masks')
                combined |= mask
                pixels[mask] = action['background']
                fit = action['fit']
                if not fitz.Rect(info['bbox']).contains(fitz.Rect(fit['bbox'])):
                    raise ImageHold('Target box outside image')
                if any(other is not action and fitz.Rect(fit['bbox']).intersects(fitz.Rect(other['fit']['bbox'])) for other in edits):
                    raise ImageHold('Overlapping target boxes')
                fresh = fit_text(fit['text'], fit['bbox'], fit['font_id'], fit['initial_size'], fit['alignment'])
                if fresh != fit: raise ImageHold('Font/fit plan mismatch')
            if not np.array_equal(pixels[~combined], np.array(original)[~combined]): raise ImageHold('Outside-mask damage')
            cleaned = Path(staging)/str(len(prepared))
            cleaned.write_bytes(pixels.tobytes())
            prepared.append((page_number,xref,cleaned,edits))
            del pixels, original, combined, mask, allowed
        for page_number,xref,cleaned,edits in prepared:
            raw = cleaned.read_bytes()
            # Uniqueness is established across displayed pages and nested forms are excluded.
            for key, value in {'ColorSpace':'/DeviceRGB','BitsPerComponent':'8','Filter':'null','DecodeParms':'null','Decode':'null'}.items():
                doc.xref_set_key(xref, key, value)
            doc.update_stream(xref, raw, compress=True)
            for action in edits:
                action['cleaned_image_sha256'] = hashlib.sha256(raw).hexdigest()
            del raw
            cleaned.unlink()
            page = doc[page_number]
            for action in edits:
                fit = action['fit']
                path, _ = font_asset(fit['font_id'])
                name = 'hybrid' + hashlib.sha256(fit['font_id'].encode()).hexdigest()[:8]
                page.insert_font(fontname=name, fontfile=str(path))
                font = fitz.Font(fontfile=str(path))
                box = fitz.Rect(fit['bbox'])
                y = box.y0 + font.ascender*fit['font_size']
                for line in fit['lines']:
                    offset = (box.width-font.text_length(line, fontsize=fit['font_size'])) * fit['alignment']/2
                    page.insert_text((box.x0+offset,y), line, fontname=name, fontsize=fit['font_size'],
                                     color=tuple(c/255 for c in action['foreground']))
                    y += fit['leading']


def validate_output(path, actions):
    from document.pixel_budget import image_inventory
    with fitz.open(path) as doc:
        inventory = image_inventory(doc)
        for action in actions:
            images = [i for i in inventory[action['page']] if list(i['bbox']) == action['image_bbox']]
            if len(images) != 1 or image_digest(source_image(doc, images[0]['xref'])) != action['cleaned_image_sha256']:
                raise ImageHold('Saved image pixel validation failed')
            actual = doc[action['page']].get_text(clip=fitz.Rect(action['fit']['bbox']))
            if ''.join(actual.split()) != ''.join(action['fit']['text'].split()):
                raise ImageHold('Saved target text is missing or not searchable')


def estimate_style(image, words, scale):
    """Compare source word shapes against packaged font families/weights."""
    import numpy as np
    from PIL import ImageDraw, ImageFont
    manifest = json.loads((FONT_ROOT/'manifest.json').read_text(encoding='utf-8'))
    scores = []
    samples = [w for w in words if len(w['text']) >= 3][:8]
    if not samples: raise ImageHold('Insufficient glyphs for family/weight estimate')
    bg = np.median(np.array(image.convert('L')))
    for font_id in manifest['fonts']:
        path, item = font_asset(font_id)
        results, sizes = [], []
        for w in samples:
            box = list(map(int, w['position']))
            source = image.crop(box).convert('L')
            array = np.array(source)
            actual = np.abs(array.astype(float)-bg) > 20
            ink = Image.fromarray(actual.astype('uint8')*255).getbbox()
            if not ink:continue
            actual = actual[ink[1]:ink[3],ink[0]:ink[2]]
            font = ImageFont.truetype(str(path), max(10, source.height*2))
            bounds = font.getbbox(w['text'])
            if bounds[2] <= bounds[0] or bounds[3] <= bounds[1]: continue
            sample = Image.new('L', (bounds[2]-bounds[0],bounds[3]-bounds[1]), 0)
            ImageDraw.Draw(sample).text((-bounds[0],-bounds[1]), w['text'], font=font, fill=255)
            sample = sample.crop(sample.getbbox())
            candidate = np.array(sample.resize((actual.shape[1],actual.shape[0]))) > 100
            results.append(2*(candidate & actual).sum()/max(1,candidate.sum()+actual.sum()))
            sizes.append(actual.shape[0] * font.size/sample.height * scale)
        if results: scores.append((sum(results)/len(results),font_id,float(np.median(sizes))))
    scores.sort(reverse=True)
    if not scores or scores[0][0] < .6:
        raise ImageHold('Font family/weight estimate uncertain')
    return {'font_id': scores[0][1], 'initial_size': scores[0][2],
            'method': 'packaged glyph-shape comparison', 'confidence': scores[0][0]}


def plan_images(original, blocks):
    """Translation results become operations only after every destructive check passes."""
    actions, held = [], []
    image_blocks = [b for b in blocks if b.get('image_region')]
    with fitz.open(original) as doc:
        for block in image_blocks:
            region = block['image_region']
            try:
                occurrence_safety(doc, block['page'], region['xref'])
                image = source_image(doc, region['xref'])
                exclusions = [w['position'] for other in image_blocks if other is not block
                              and other['image_region']['xref'] == region['xref']
                              for w in other['ocr']['words']]
                style = region['estimated_style']
                action = prepare_action(image, block['ocr']['words'], block['text'], region['image_bbox'],
                                        block['position'], style['font_id'], style['initial_size'], exclusions)
                action.update(page=block['page'], xref=region['xref'], region_id=block['region_id'])
                if sum(len(a['mask']) for a in actions) + len(action['mask']) > 8_000_000:
                    raise ImageHold('Whole-plan mask budget exceeded')
                actions.append(action)
            except (ImageHold, ImportError, OSError) as exc:
                held.append({'region_id': block['region_id'], 'reason': str(exc)})
    return actions, held
