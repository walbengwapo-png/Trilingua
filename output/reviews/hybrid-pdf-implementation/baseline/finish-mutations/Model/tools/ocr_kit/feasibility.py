"""Variant experiments only. Never signs or emits gate-eligible reports."""
import json
from pathlib import Path
import numpy as np
from PIL import Image
from benchmarks.ocr_feasibility import metrics
from benchmarks.ocr_corpus import region_metrics
from document.ocr_extractor import recognize_image, MAX_PIXELS
from document.pixel_budget import limit
from .corpus import BANNER, current, pages


def preprocess(image, dpi, deskew=False, binarize=False):
    import cv2
    matrix=np.array([[dpi/300,0,0],[0,dpi/300,0]],dtype=float)
    gray=np.array(image.convert('L'))
    if deskew:
        points=np.column_stack(np.where(gray<128))[:,::-1].astype(np.float32)
        if len(points)>10:
            angle=cv2.minAreaRect(points)[2]
            if angle>45:angle-=90
            if abs(angle)>15:raise ValueError('Deskew exceeds diagnostic 15 degree range')
            rotation=cv2.getRotationMatrix2D((image.width/2,image.height/2),angle,1)
            gray=cv2.warpAffine(gray,rotation,(image.width,image.height),borderValue=255)
            matrix=(np.vstack((rotation,[0,0,1]))@np.vstack((matrix,[0,0,1])))[:2]
    if binarize:gray=cv2.threshold(gray,0,255,cv2.THRESH_BINARY+cv2.THRESH_OTSU)[1]
    return Image.fromarray(gray),matrix


def transformed(regions, matrix):
    result=[]
    for region in regions:
        x0,y0,x1,y1=region['bbox']
        points=np.array([[x0,y0,1],[x1,y0,1],[x0,y1,1],[x1,y1,1]])@matrix.T
        result.append(dict(region,bbox=[*points.min(axis=0),*points.max(axis=0)]))
    return result


def band(score):
    return '>=95 reachable' if score>=95 else '85-95 try preprocessing' if score>=85 else '<85 engine problem'


def summarize(records):
    words=sum(r['reference_words'] for r in records)
    accuracy=100*max(0,1-sum(r['word_errors'] for r in records)/words) if words else None
    with_geometry=[r for r in records if r.get('expected_regions') is not None]
    expected=sum(r['expected_regions'] for r in with_geometry)
    pairs=sum(r['reading_order_pairs'] for r in with_geometry)
    return {'samples':len(records),'reference_words':words,'word_accuracy_percent':accuracy,
            'region_recall':sum(r['matched_regions'] for r in with_geometry)/expected if expected else None,
            'reading_order_score':sum(r['correct_order_pairs'] for r in with_geometry)/pairs if pairs else None,
            'layout_metrics_samples':len(with_geometry),'verdict':band(accuracy) if accuracy is not None else 'unmeasured'}


def feasibility(saved, dpis=(300,), deskew=False, binarize=False):
    saved=current(saved);results=[]
    for sample in saved['samples']:
        for dpi in dpis:
            row={'id':sample['id'],'language':sample['language'],'capture_class':sample['capture_class'],
                 'split':sample['split'],'dpi':dpi,'deskew':deskew,'binarize':binarize,'status':'unmeasured'}
            try:
                if not sample['pack'] or not sample['reference_sha256']:raise ValueError('Language pack/transcript missing')
                reference=Path(sample['reference']).read_text(encoding='utf-8')
                expected=json.loads(Path(sample['regions_file']).read_text(encoding='utf-8')) if Path(sample['regions_file']).is_file() else None
                texts=[];scores=[];used=0
                for number,image in pages(Path(saved['root'])/sample['file'],dpi):
                    used+=image.width*image.height
                    if used>limit() or image.width*image.height>MAX_PIXELS:raise ValueError('Raster pixel budget exceeded')
                    processed,matrix=preprocess(image,dpi,deskew,binarize)
                    blocks=recognize_image(processed,sample['pack'],number,processed.size)
                    texts.extend(b['text'] for b in blocks)
                    if expected is not None:
                        regions=transformed([r for r in expected if r.get('page',0)==number],matrix)
                        scores.append(region_metrics(regions,blocks))
                row.update(metrics(reference,'\n'.join(texts)),status='measured')
                if expected is not None and scores:
                    row.update(expected_regions=sum(s['expected_regions'] for s in scores),
                        matched_regions=sum(s['matched_regions'] for s in scores),
                        reading_order_pairs=sum(s['reading_order_pairs'] for s in scores),
                        correct_order_pairs=sum((s['reading_order_accuracy'] or 0)*s['reading_order_pairs'] for s in scores))
                else:row['layout_metrics_reason']='Checked geometry unavailable; transcript cannot establish region/order scores'
                row['verdict']=band(row['word_accuracy_percent'])
            except (OSError,ValueError,RuntimeError) as exc:row['reason']=str(exc)
            results.append(row)
    slices={}
    for row in results:
        key=f"{row['language']} / {row['capture_class']} / {row['split']} / {row['dpi']}dpi / deskew={deskew} / binarize={binarize}"
        slices.setdefault(key,[]).append(row)
    return {'purpose':'diagnostic','material':'diagnostic','banner':BANNER,'samples':results,
            'slices':{key:summarize([r for r in group if r['status']=='measured']) for key,group in slices.items()},
            'warning':'Verdict bands are diagnostic suggestions, not OCR acceptance. Missing geometry stays unmeasured.'}
