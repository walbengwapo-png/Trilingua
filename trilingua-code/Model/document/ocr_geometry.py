"""hOCR word/line geometry, parsed locally without XML entities or networking."""
from html.parser import HTMLParser
import math


def properties(title):
    result = {}
    for part in title.split(';'):
        tokens = part.strip().split()
        if tokens:
            result[tokens[0]] = tokens[1:]
    return result


def numbers(props, name, count=None):
    values = [float(x) for x in props.get(name, [])]
    if (count is not None and len(values) != count) or not all(math.isfinite(x) for x in values):
        raise ValueError('Invalid OCR ' + name)
    return values


class HOCRParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.stack, self.groups = [], {}
        self.paragraph = self.line = self.word = None

    def handle_starttag(self, tag, attrs):
        if tag in {'meta', 'link', 'br', 'img', 'input', 'hr'}:
            return
        self.stack.append((tag, self.paragraph, self.line, self.word))
        attrs = dict(attrs)
        classes = attrs.get('class', '').split()
        props = properties(attrs.get('title', ''))
        if 'ocr_par' in classes:
            self.paragraph = attrs.get('id', str(len(self.groups)))
        if 'ocr_line' in classes or 'ocrx_line' in classes:
            self.line = {'id': attrs.get('id', str(len(self.stack))),
                         'position': numbers(props, 'bbox', 4),
                         'baseline': numbers(props, 'baseline', 2) if 'baseline' in props else None}
            for key in ('x_size', 'x_ascenders', 'x_descenders'):
                value = numbers(props, key, 1) if key in props else [0]
                self.line[key] = value[0]
        if 'ocrx_word' in classes or 'ocr_word' in classes:
            confidence = props.get('x_wconf', ['-1'])[0]
            try:
                confidence = float(confidence)
                if not math.isfinite(confidence):confidence = -1
            except (ValueError, TypeError):confidence = -1
            self.word = {'parts': [], 'position': numbers(props, 'bbox', 4), 'confidence': confidence,
                         'paragraph': self.paragraph or 'page',
                         'line': self.line['id'] if self.line else None,
                         'line_geometry': dict(self.line) if self.line else None}

    def handle_data(self, data):
        if self.word is not None:self.word['parts'].append(data)

    def handle_endtag(self, tag):
        if not self.stack or self.stack[-1][0] != tag:
            return
        _, paragraph, line, word = self.stack.pop()
        if self.word is not None and self.word is not word:
            text = ''.join(self.word.pop('parts')).strip()
            if text:
                self.word['text'] = text
                self.groups.setdefault(self.word['paragraph'], []).append(self.word)
        self.paragraph, self.line, self.word = paragraph, line, word


def parse_hocr(raw, size):
    if len(raw) > 24_000_000:raise ValueError('OCR result exceeds 24 MB limit')
    parser = HOCRParser()
    parser.feed(raw.decode('utf-8') if isinstance(raw, bytes) else raw)
    parser.close()
    for words in parser.groups.values():
        for word in words:
            x0,y0,x1,y1 = word['position']
            if not (0 <= x0 < x1 <= size[0] and 0 <= y0 < y1 <= size[1]):
                raise ValueError('OCR word outside source image')
    return parser.groups


def transform_words(words, sx, sy, tx=0, ty=0):
    def box(rect):
        return [rect[0]*sx+tx, rect[1]*sy+ty, rect[2]*sx+tx, rect[3]*sy+ty]
    result = []
    for word in words:
        item = dict(word, position=box(word['position']))
        geometry = word.get('line_geometry')
        if geometry:
            item['line_geometry'] = dict(geometry, position=box(geometry['position']))
            if geometry.get('baseline') is not None:
                m,b = geometry['baseline']
                item['line_geometry']['baseline'] = [m*sy/sx, b*sy]
            for key in ('x_size', 'x_ascenders', 'x_descenders'):
                item['line_geometry'][key] = geometry.get(key, 0)*sy
        result.append(item)
    return result


def validate_baselines(words):
    from statistics import median
    lines = {}
    for word in words:lines.setdefault(word.get('line', 0), []).append(word)
    for line in lines.values():
        tolerance = max(2, median(w['position'][3]-w['position'][1] for w in line)*.3)
        geometry = line[0].get('line_geometry')
        if not geometry:
            if any('line_geometry' in w for w in line):
                raise ValueError('Unverified OCR line baseline')
            # Legacy fixed geometry lacks OCR baselines; retain its conservative hold.
            bottoms = [w['position'][3] for w in line]
            if max(bottoms)-min(bottoms) > tolerance:raise ValueError('Rotated/curved baseline is unsupported')
            continue
        if any(w.get('line_geometry') != geometry for w in line) or geometry.get('baseline') is None:
            raise ValueError('Unverified OCR line baseline')
        x0,y0,x1,y1 = geometry['position']
        m,b = geometry['baseline']
        descenders = geometry.get('x_descenders', 0)
        if not all(math.isfinite(v) for v in (x0,y0,x1,y1,m,b,descenders)) or descenders < 0 or x1 <= x0 or y1 <= y0:
            raise ValueError('Invalid OCR line baseline')
        if abs(m)*(x1-x0) > tolerance:raise ValueError('Rotated/curved baseline is unsupported')
        for word in line:
            box = word['position']
            baseline = y1+b+m*((box[0]+box[2])/2-x0)
            if not -tolerance <= box[3]-baseline <= descenders+tolerance:
                raise ValueError('Rotated/curved baseline is unsupported')
