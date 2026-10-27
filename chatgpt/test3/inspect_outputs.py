"""Offline structural checks and source/output page comparisons; no AI calls."""
import json
import re
from pathlib import Path
from collections import Counter
import fitz
from PIL import Image, ImageDraw

HERE = Path(__file__).resolve().parent
EVIDENCE = HERE / 'evidence'
QA = EVIDENCE / 'visual-qa'
QA.mkdir(exist_ok=True)
results = json.loads((EVIDENCE / 'results.json').read_text(encoding='utf-8')) if (EVIDENCE / 'results.json').exists() else []
checks = []
for source in sorted(HERE.glob('[0-9][0-9]_*.pdf')):
    index = int(source.name[:2])
    result = next((r for r in results if r['id'] == index), {})
    output = HERE / result['output'] if 'output' in result else None
    src = fitz.open(source)
    dst = fitz.open(output) if output else None
    if dst:
        payload = json.loads((EVIDENCE / f'{index:02d}_response.json').read_text(encoding='utf-8'))
        blocks = payload.get('blocks', [])
        unchanged = [b['block_index'] for b in blocks if not b.get('passthrough') and b.get('source_text', '').strip() == b.get('current_text', '').strip() and len(b.get('source_text', '').split()) >= 5]
        retained = [{'block': b['block_index'], 'type': b.get('block_type'), 'source': b.get('source_text')} for b in blocks if b.get('passthrough') and len(b.get('source_text', '').split()) >= 5]
        blank = [b['block_index'] for b in blocks if b.get('source_text', '').strip() and not b.get('current_text', '').strip()]
        src_text = ' '.join(p.get_text() for p in src)
        dst_text = ' '.join(p.get_text() for p in dst)
        urls = set(re.findall(r'(?:https?://|www\.)[^\s)]+|[A-Za-z0-9][A-Za-z0-9.-]*\.(?:gov|org|com|ph)(?:/[^\s)]+)?', src_text))
        missing_urls = sorted(u for u in urls if u not in dst_text)
        pages = []
        for p, page in enumerate(dst):
            text_page_rect = fitz.Rect(0, 0, page.cropbox.width, page.cropbox.height)
            spans = [s for block in page.get_text('dict')['blocks'] if 'lines' in block for line in block['lines'] for s in line['spans'] if s['text'].strip()]
            pages.append({'page': p+1, 'characters': len(page.get_text()), 'dimensions': list(page.rect),
                          'small_font_spans_under_6pt': sum(s['size'] < 6 for s in spans),
                          'minimum_font_pt': round(min((s['size'] for s in spans), default=0), 2),
                          'page_rotation': page.rotation,
                          'outside_unrotated_crop_spans': sum(not text_page_rect.contains(fitz.Rect(s['bbox'])) for s in spans)})
        checks.append({'id': index, 'sidecar_blocks': len(blocks), 'blank_block_ids': blank,
                       'retained_long_passthrough_blocks': retained, 'missing_literal_urls_including_www': missing_urls,
                       'unchanged_long_block_ids': unchanged, 'pages': pages,
                       'source_dimensions': [list(p.rect) for p in src],
                       'ai_review_scores': dict(Counter(str(b.get('quality_score')) for b in blocks)),
                       'ai_review_issues': [{'block': b['block_index'], 'issues': b['quality_issues']} for b in blocks if b.get('quality_issues')]})
    # Two source/output page pairs per contact sheet, all pages covered.
    for first in range(0, max(len(src), len(dst) if dst else 0), 2):
        canvas = Image.new('RGB', (1200, 1700), 'white')
        draw = ImageDraw.Draw(canvas)
        for row, p in enumerate(range(first, min(first+2, max(len(src), len(dst) if dst else 0)))):
            for col, doc in enumerate((src, dst)):
                draw.text((col*600+10, row*850+5), f'{index:02d} {"SOURCE" if col == 0 else "OUTPUT"} PAGE {p+1}', fill='black')
                if doc is not None and p < len(doc):
                    pix = doc[p].get_pixmap(matrix=fitz.Matrix(1.2, 1.2), alpha=False)
                    image = Image.frombytes('RGB', (pix.width, pix.height), pix.samples)
                    image.thumbnail((580, 810))
                    canvas.paste(image, (col*600+10, row*850+30))
        canvas.save(QA / f'{index:02d}_pages_{first+1}-{first+2}.png')
    src.close()
    if dst: dst.close()
(EVIDENCE / 'qa.json').write_text(json.dumps(checks, ensure_ascii=False, indent=2), encoding='utf-8')
print('Checked outputs:', ', '.join(str(c['id']) for c in checks))
