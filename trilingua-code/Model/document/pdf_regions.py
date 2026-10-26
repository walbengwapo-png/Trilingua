"""Conservative region inventory. An unverified raster is never declared text-free."""
from collections import Counter
import hashlib
import json

import fitz

MAX_PAGES = 50
MAX_PIXELS = 40_000_000
SIGNALS_VERSION = 1  # Uncalibrated signals classify uncertainty as held.


def sha256(path):
    with open(path, 'rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def overlap(a, b):
    a, b = fitz.Rect(a), fitz.Rect(b)
    return (a & b).get_area() / max(1e-9, min(a.get_area(), b.get_area()))


def local_matches(native, recognized):
    """Many-to-many local ownership; repeated words in other boxes remain separate."""
    matches = []
    for i, left in enumerate(native):
        for j, right in enumerate(recognized):
            if left.get('page', 0) != right.get('page', 0):
                continue
            common = overlap(left['position'], right['position'])
            a, b = set(left['text'].casefold().split()), set(right['text'].casefold().split())
            agreement = len(a & b) / max(1, min(len(a), len(b)))
            if common >= .8 and agreement >= .8:
                matches.append({'native': i, 'ocr': j, 'overlap': common,
                                'agreement': agreement, 'visible': left.get('visible', False)})
    return matches


def _visible(page, block, images):
    box = fitz.Rect(block['position'])
    traces = [t for t in page.get_texttrace() if overlap(box, t['bbox']) >= .5]
    if not traces or any(t['type'] == 3 or t.get('opacity', 1) < .95 for t in traces):
        return False
    # Later opaque artwork can cover nominally native text.
    for t in traces:
        for seq, (kind, bounds) in enumerate(page.get_bboxlog()):
            if seq > t['seqno'] and kind in {'fill-image', 'fill-path'} and overlap(t['bbox'], bounds) > .9:
                return False
    text = block.get('text', '')
    return bool(text.strip()) and sum(c == '\ufffd' or 0xe000 <= ord(c) <= 0xf8ff for c in text) / len(text) < .05


def inventory_pdf(path, native_blocks, language, column_mode='auto', source_identity=None):
    from document.ocr_extractor import OCRUnavailable, require_ready
    from document.pdf_source import _check_pdf_limits
    _check_pdf_limits(path)
    identity = source_identity or sha256(path)
    regions, pages, blocks, warnings = [], [], [], []
    with fitz.open(path) as doc:
        if len(doc) > MAX_PAGES:
            raise ValueError('Hybrid PDF limit is 50 pages')
        from document.pixel_budget import image_inventory, BUDGET_REASON, limit
        all_images = image_inventory(doc)
        retry_budget = {'remaining': max(0, limit()-doc._hybrid_pixels_used)}
        uses = Counter(i['xref'] for page_images in all_images for i in page_images)
        for number, page in enumerate(doc):
            if page.rect.get_area() * (300 / 72) ** 2 > MAX_PIXELS:
                raise ValueError('Page exceeds the 40 megapixel raster limit')
            images = all_images[number]
            def region(kind, box, **extra):
                token = json.dumps([number, kind, list(box), len(regions)], separators=(',', ':'))
                entry = {'region_id': hashlib.sha256((identity + token).encode()).hexdigest()[:24],
                         'page': number, 'source_kind': kind, 'bbox': list(box),
                         'status': 'held', 'reason': 'unverified', **extra}
                regions.append(entry)
                return entry
            for block in (b for b in native_blocks if b.get('page', 0) == number):
                visible = _visible(page, block, images)
                entry = region('native' if visible else 'hidden_ocr', block['position'])
                if visible:
                    entry.update(status='passthrough' if block.get('passthrough') else 'pending', reason=None,
                                 block_index=len(blocks))
                    block = dict(block, region_id=entry['region_id'], visible=True)
                    blocks.append(block)
                else:
                    entry['reason'] = 'hidden_or_occluded_native'
            for index, image in enumerate(images):
                box = fitz.Rect(image['bbox'])
                # Preview is evidence about pixels, never an OCR acceptance shortcut.
                pix = None if image.get('budget_hold') else page.get_pixmap(clip=box & page.rect, matrix=fitz.Matrix(1, 1), alpha=False)
                samples = pix.samples if pix else b''
                variation = max(samples) - min(samples) if samples else 0
                entry = region('raster', box, occurrence_id=f'{number}:{index}', xref=image['xref'],
                               transform=list(image['transform']), capture_scope=['scan', 'photo', 'screenshot'],
                               signals={'version': SIGNALS_VERSION, 'calibrated': False,
                                        'preview_range': variation}, occurrence_count=uses[image['xref']])
                if image.get('budget_hold'):
                    entry.update(reason=BUDGET_REASON)
                    continue
                try:
                    for category in entry['capture_scope']:
                        require_ready(language, category)
                except OCRUnavailable as exc:
                    entry.update(reason='ocr_acceptance_hold', detail=str(exc))
                else:
                    from document.image_reconstructor import (ImageHold, occurrence_safety, source_image,
                                                               estimate_style)
                    from document.ocr_extractor import recognize_image
                    image_block_start, image_region_start = len(blocks), len(regions)
                    try:
                        occurrence_safety(doc, number, image['xref'])
                        source = source_image(doc, image['xref'])
                        found = recognize_image(source, require_ready(language, 'scan'), number, source.size,
                                                retry_budget=retry_budget)
                        entry.update(status='container', reason=None)
                        for recognized in found:
                            words = recognized['ocr']['words']
                            style = estimate_style(source, words, box.width/source.width)
                            raw = recognized['position']
                            sx, sy = box.width/source.width, box.height/source.height
                            target = fitz.Rect(box.x0+raw[0]*sx-1, box.y0+raw[1]*sy-1,
                                               box.x0+raw[2]*sx+1, box.y0+raw[3]*sy+style['initial_size']*.5) & box
                            neighbors = [fitz.Rect(other['position']) for other in found if other is not recognized]
                            pixel_target = fitz.Rect((target.x0-box.x0)/sx, (target.y0-box.y0)/sy,
                                                      (target.x1-box.x0)/sx, (target.y1-box.y0)/sy)
                            child = region('raster_text', target, parent_region_id=entry['region_id'])
                            if (recognized['ocr']['confidence'] < 80 or any(w['confidence'] < 80 for w in words)
                                    or any(pixel_target.intersects(n) for n in neighbors)):
                                child['reason'] = 'low_confidence_or_neighbor_overlap'
                                continue
                            recognized.update(position=list(target), region_id=child['region_id'], ocr_reflow=False,
                                              image_region={'xref':image['xref'], 'image_bbox':list(box),
                                                            'estimated_style':style})
                            matches = local_matches([b for b in blocks if b['page'] == number], [recognized])
                            if matches:
                                child.update(reason='ambiguous_native_ocr_overlap', dedup_matches=matches)
                                continue
                            child.update(status='pending', reason=None, block_index=len(blocks))
                            blocks.append(recognized)
                    except (ImageHold, OCRUnavailable, ImportError, OSError) as exc:
                        del blocks[image_block_start:]
                        del regions[image_region_start:]
                        entry.update(status='held', reason='image_safety_hold', detail=str(exc))
                if uses[image['xref']] != 1:
                    entry['safety_hold'] = 'shared_or_unresolved_image'
            drawings = page.get_drawings()
            if drawings:
                for bounds in page.cluster_drawings(drawings=drawings):
                    if not any(overlap(bounds, r['bbox']) > .8 for r in regions if r['page'] == number):
                        region('outlined_or_artwork', bounds, reason='outlined_text_excluded')
            if page.get_text().strip() and not any(r['page'] == number and r['source_kind'] in {'native', 'hidden_ocr'} for r in regions):
                region('unknown', page.rect, reason='filtered_or_unextracted_native')
            kinds = {r['source_kind'] for r in regions if r['page'] == number}
            pages.append({'page': number, 'classification': 'mixed' if len(kinds) > 1 else next(iter(kinds), 'blank'),
                          'mediabox': list(page.mediabox), 'cropbox': list(page.cropbox),
                          'rotation': page.rotation, 'rotation_matrix': list(page.rotation_matrix)})
    for r in regions:
        if r['status'] == 'held':
            warnings.append(f"Page {r['page'] + 1}: original region retained ({r['reason']}).")
    return blocks, {'pages': pages, 'regions': regions, 'warnings': warnings,
                    'original_sha256': identity, 'signals_version': SIGNALS_VERSION}


def completed_status(block):
    unchanged = bool(block.get('source_text')) and block.get('text') == block['source_text']
    return 'passthrough' if block.get('passthrough') or unchanged else 'translated'


def content_summary(regions):
    counts = Counter(r['status'] for r in regions)
    held, translated = counts['held'], counts['translated']
    status = ('partial' if translated else 'untranslated') if held else 'complete'
    return {'status': status, 'translated': translated, 'held': held,
            'passthrough': counts['passthrough'], 'source_coverage': 'unknown' if held else 'inventoried',
            'held_region_ids': [r['region_id'] for r in regions if r['status'] == 'held']}
