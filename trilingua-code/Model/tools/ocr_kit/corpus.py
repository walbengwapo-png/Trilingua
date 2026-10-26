"""Human-supplied intake, reference checks and evaluator-manifest preparation."""
import csv
from datetime import date
import hashlib
import json
from pathlib import Path
from PIL import Image, ImageOps
import fitz
from document.ocr_extractor import PACKS, MAX_PIXELS
from document.pixel_budget import limit
from benchmarks.ocr_feasibility import normalize

SUFFIXES = {'.pdf', '.png', '.jpg', '.jpeg'}
BANNER = 'DIAGNOSTIC, NOT ACCEPTANCE EVIDENCE'


def digest(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def save(path, value):
    path = Path(path);path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False)+'\n', encoding='utf-8')


def pages(path, dpi=300):
    """Diagnostic rasterization only, with the same page/image/job caps."""
    path=Path(path);used=0
    if path.suffix.lower()=='.pdf':
        with fitz.open(path) as doc:
            if len(doc)>50:raise ValueError('50-page limit exceeded')
            for page in doc:
                width,height=int(page.rect.width*dpi/72+.999),int(page.rect.height*dpi/72+.999)
                if width*height>MAX_PIXELS or used+width*height>limit():raise ValueError('Raster pixel budget exceeded')
                if any(r[2]*r[3]>MAX_PIXELS for r in page.get_images(full=True)):raise ValueError('Source image exceeds 40 MP')
                used+=width*height
                pix=page.get_pixmap(matrix=fitz.Matrix(dpi/72,dpi/72),alpha=False)
                if pix.colorspace!=fitz.csRGB:pix=fitz.Pixmap(fitz.csRGB,pix)
                yield page.number,Image.frombytes('RGB',(pix.width,pix.height),pix.samples)
    else:
        with Image.open(path) as source:
            if getattr(source,'n_frames',1)!=1:raise ValueError('Single-frame images required')
            width,height=source.size
            scaled=int(width*dpi/300)*int(height*dpi/300)
            if width*height>MAX_PIXELS or scaled>min(MAX_PIXELS,limit()):raise ValueError('Raster pixel budget exceeded')
            image=ImageOps.exif_transpose(source).convert('RGB')
            if dpi!=300:image=image.resize((int(image.width*dpi/300),int(image.height*dpi/300)))
            yield 0,image


def intake(folder):
    folder=Path(folder).resolve();samples=[];gaps=[];groups={};seen=set()
    with (folder/'info.csv').open(encoding='utf-8-sig',newline='') as stream:
        rows=list(csv.DictReader(stream))
    required={'file','language','capture_class','content_group_id','split','author','rights_note'}
    if not rows or not required<=rows[0].keys():raise ValueError('info.csv requires '+', '.join(sorted(required)))
    for row in rows:
        name=row['file'];source=(folder/name).resolve()
        if not source.is_relative_to(folder) or source.suffix.lower() not in SUFFIXES or not source.is_file():
            gaps.append(f'{name}: missing/unsafe/unsupported file');continue
        if name in seen:raise ValueError('Duplicate intake file')
        seen.add(name)
        split={'held_out':'heldout'}.get(row['split'],row['split'])
        group=row['content_group_id']
        if group in groups and groups[group]!=split:raise ValueError('Content group spans splits')
        groups[group]=split
        reference=source.with_suffix('.txt');regions=source.with_suffix('.regions.json')
        identity=hashlib.sha256(name.encode()).hexdigest()[:16]
        sample=dict(row,id=identity,split=split,pack=PACKS.get(row['language']),
            image_sha256=digest(source),reference=str(reference),regions_file=str(regions),
            reference_sha256=digest(reference) if reference.is_file() else None)
        issues=[]
        try:
            if source.suffix.lower()=='.pdf':
                with fitz.open(source) as doc:
                    if len(doc)>50 or any(p.rect.get_area()*(300/72)**2>MAX_PIXELS for p in doc):
                        issues.append('PDF page/raster limit exceeded')
            else:
                with Image.open(source) as image:
                    expected={'.png':'PNG','.jpg':'JPEG','.jpeg':'JPEG'}[source.suffix.lower()]
                    if image.format!=expected or getattr(image,'n_frames',1)!=1 or min(image.size)<200 or image.width*image.height>MAX_PIXELS:
                        issues.append('image format/resolution/frame limit invalid')
        except (OSError,ValueError,RuntimeError,Image.DecompressionBombError):issues.append('unreadable/oversized image or PDF')
        if row['language'] not in PACKS or row['capture_class'] not in {'scan','photo','screenshot'}:issues.append('unsupported language/capture class')
        if split not in {'calibration','heldout'} or not group:issues.append('split/content group missing')
        if not row['author'].strip() or not row['rights_note'].strip():issues.append('author/rights note missing')
        if not reference.is_file() or not reference.read_text(encoding='utf-8').strip():issues.append('matching nonempty .txt missing')
        if not regions.is_file():issues.append('checked .regions.json geometry missing (layout metrics unavailable)')
        sample['gaps']=issues;samples.append(sample);gaps.extend(f'{name}: {x}' for x in issues)
    listed={str((folder/name).resolve()) for name in seen}
    gaps.extend(f'{p.name}: absent from info.csv' for p in folder.iterdir() if p.suffix.lower() in SUFFIXES and str(p.resolve()) not in listed)
    return {'purpose':'diagnostic','banner':BANNER,'root':str(folder),'info_sha256':digest(folder/'info.csv'),
            'samples':samples,'gaps':gaps}


def current(saved):
    fresh=intake(saved['root'])
    fingerprint=lambda value:[(s['id'],s['image_sha256'],s['reference_sha256']) for s in value['samples']]
    if fingerprint(saved)!=fingerprint(fresh) or saved.get('info_sha256')!=fresh['info_sha256']:
        raise ValueError('Intake bytes or metadata changed; rerun intake and independent review')
    return fresh


def reference_sheet(saved, output):
    saved=current(saved)
    fields=['id','file','source_sha256','reference_sha256','reviewer','decision','corrected_text',
            'review_date','attestation','rights_verified','representative','real_capture_confirmed']
    with Path(output).open('x',encoding='utf-8',newline='') as stream:
        writer=csv.DictWriter(stream,fieldnames=fields);writer.writeheader()
        for sample in saved['samples']:
            writer.writerow({'id':sample['id'],'file':sample['file'],'source_sha256':sample['image_sha256'],
                             'reference_sha256':sample['reference_sha256']})


def ingest_checks(saved, sheet, output):
    saved=current(saved);source={s['id']:s for s in saved['samples']}
    with Path(sheet).open(encoding='utf-8-sig',newline='') as stream:rows=list(csv.DictReader(stream))
    if len(rows)!=len(source) or {r['id'] for r in rows}!=source.keys():raise ValueError('Reference sheet case coverage/duplicates invalid')
    checked=[];directory=Path(output).resolve().parent/'checked-references';directory.mkdir(parents=True,exist_ok=True)
    for row in rows:
        sample=source[row['id']]
        if row['source_sha256']!=sample['image_sha256'] or row['reference_sha256']!=sample['reference_sha256']:
            raise ValueError('Reference sheet source/reference hash mismatch')
        if not row['reviewer'].strip() or row['reviewer'].strip()==sample['author'].strip():raise ValueError('Independent second reviewer required')
        if row['decision'] not in {'confirmed','corrected'} or not row['attestation'].strip():raise ValueError('Completed reference decision/attestation required')
        if date.fromisoformat(row['review_date'])>date.today():raise ValueError('Future reference review date')
        text=Path(sample['reference']).read_text(encoding='utf-8') if row['decision']=='confirmed' else row['corrected_text']
        if not text.strip():raise ValueError('Nonempty checked/corrected text required')
        reference=directory/(sample['id']+'.txt');reference.write_text(text,encoding='utf-8')
        checked.append({**row,'checked_reference':str(reference),'checked_reference_sha256':digest(reference)})
    result={'purpose':'reference-provenance','banner':BANNER,'checks':checked}
    save(output,result);return result


def checked_page_regions(regions, number, size):
    import math
    found=[r for r in regions if r.get('page',0)==number]
    if not found:raise ValueError('Every page needs complete checked regions')
    for region in found:
        box=region['bbox']
        if (len(box)!=4 or not all(isinstance(v,(int,float)) and math.isfinite(v) for v in box)
                or not 0<=box[0]<box[2]<=size[0] or not 0<=box[1]<box[3]<=size[1]):
            raise ValueError('Checked region geometry outside source raster')
    return found


def build_manifest(saved, checks, approval, output):
    saved=current(saved)
    if saved['gaps']:raise ValueError('Intake gaps must be resolved before manifest construction')
    if (approval.get('coverage_reviewed') is not True or not approval.get('reviewers')
            or not approval.get('attestation','').strip()):raise ValueError('Owner corpus review/coverage attestation required')
    if date.fromisoformat(approval.get('review_date',''))>date.today():raise ValueError('Future corpus review date')
    reviews={c['id']:c for c in checks['checks']}
    if len(reviews)!=len(checks['checks']) or set(reviews)!={s['id'] for s in saved['samples']}:raise ValueError('Incomplete reference checks')
    output=Path(output).resolve()
    if output.exists():raise FileExistsError('Use a new manifest output directory')
    # Validate every attestation before creating any evaluator material.
    for sample in saved['samples']:
        review=reviews[sample['id']]
        if (review.get('decision') not in {'confirmed','corrected'} or not review.get('attestation','').strip()
                or not review.get('reviewer','').strip() or date.fromisoformat(review.get('review_date',''))>date.today()):
            raise ValueError('Incomplete independent reference check')
        if sample.get('material')=='test_fixture':raise ValueError('Fixtures cannot become real evaluator material')
        if any(review.get(k,'').lower()!='true' for k in ('rights_verified','representative','real_capture_confirmed')):
            raise ValueError('Explicit real capture, rights and representativeness confirmation required')
        if (review['reviewer'] not in approval['reviewers'] or review['reviewer']==sample['author']
                or review['source_sha256']!=sample['image_sha256'] or review['reference_sha256']!=sample['reference_sha256']
                or digest(review['checked_reference'])!=review['checked_reference_sha256']):raise ValueError('Reviewed provenance mismatch')
    output.mkdir(parents=True);cases=[]
    for sample in saved['samples']:
        review=reviews[sample['id']];reference=Path(review['checked_reference']).read_text(encoding='utf-8')
        regions=json.loads(Path(sample['regions_file']).read_text(encoding='utf-8'))
        ordered=sorted(regions,key=lambda r:(r.get('page',0),r['order']))
        if normalize(reference)!=normalize('\n'.join(r['text'] for r in ordered)):raise ValueError('Checked regions must cover the complete checked reference')
        seen_pages=set()
        for number,image in pages(Path(saved['root'])/sample['file']):
            page_regions=checked_page_regions(ordered,number,image.size)
            seen_pages.add(number);identity=sample['id']+'-p'+str(number)
            image_path=output/(identity+'.png');reference_path=output/(identity+'.txt')
            image.save(image_path,'PNG');reference_path.write_text('\n'.join(r['text'] for r in page_regions),encoding='utf-8')
            cases.append({'id':identity,'document_id':sample['id'],'content_group_id':sample['content_group_id'],
                'split':sample['split'],'language':sample['language'],'pack':sample['pack'],'input_category':sample['capture_class'],
                'image':image_path.name,'reference':reference_path.name,'image_sha256':digest(image_path),
                'reference_sha256':digest(reference_path),'reference_reviewer':review['reviewer'],
                'reference_check_status':'verified','reference_review_date':review['review_date'],
                'reference_attestation':review['attestation'],'rights_verified':True,'representative':True,
                'provenance':{'source':sample['file'],'source_sha256':sample['image_sha256'],'acquired_by':sample['author'],
                    'acquisition':'real_'+sample['capture_class'],'rights_note':sample['rights_note']},'regions':page_regions})
        if any(r.get('page',0) not in seen_pages for r in ordered):raise ValueError('Reference region page outside document')
    manifest={'schema_version':2,'material':'real','corpus_review':dict(approval,
        reviewer=', '.join(approval['reviewers']),frozen_at=approval['review_date']),'cases':cases}
    from benchmarks.ocr_corpus import validate
    issues=validate(manifest,output)
    if any(issues.values()):raise ValueError('Evaluator manifest invalid: '+json.dumps(issues))
    save(output/'manifest.json',manifest)
    for name,split in [('calibration','calibration'),('held_out','heldout')]:
        save(output/(name+'.json'),dict(manifest,cases=[c for c in cases if c['split']==split]))
    return manifest
