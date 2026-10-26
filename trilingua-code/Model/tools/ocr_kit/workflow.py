"""Local review preparation and resumable acceptance; never approves human claims."""
import csv
from html import escape
import json
import math
from pathlib import Path
import shutil
import sys
import uuid

from .corpus import (BANNER, SUFFIXES, digest, save, pages, intake, current,
                     reference_sheet, ingest_checks, build_manifest)
from document.ocr_extractor import PACKS, OCRUnavailable, recognize_image, readiness, tesseract_command
from document.pixel_budget import limit
from benchmarks.ocr_feasibility import evaluate
from document.artifact_auth import load_json, sign
from document.report_trust import validate_report, verify_report


def prepare_review(source, output, language):
    source, output = Path(source).resolve(), Path(output).resolve()
    if not source.is_file() or source.suffix.lower() not in SUFFIXES or language not in PACKS:
        raise ValueError('Supported source file and source language required')
    source_pixels = 0
    if source.suffix.lower()=='.pdf':
        import fitz
        with fitz.open(source) as doc:
            if len(doc)>50:raise ValueError('50-page limit exceeded')
            resources, inline, raster = {}, 0, 0
            for page in doc:
                images = {r[0]:r[2]*r[3] for r in page.get_images(full=True)}
                resources.update(images)
                inline += max(0,sum(i['width']*i['height'] for i in page.get_image_info(xrefs=False,hashes=False))-sum(images.values()))
                raster += math.ceil(page.rect.width*300/72)*math.ceil(page.rect.height*300/72)
            source_pixels = sum(resources.values())+inline
            if raster+source_pixels > limit():raise ValueError('Source plus raster pixel budget exceeded')
    output.mkdir(parents=True, exist_ok=False)
    incoming, previews = output/'incoming', output/'previews'
    incoming.mkdir(); previews.mkdir()
    copy = incoming/source.name
    shutil.copyfile(source, copy)
    identity = digest(copy)
    if digest(source) != identity:raise ValueError('Source changed during copy')
    save(output/'workflow.json', {'version':1, 'purpose':'unreviewed-reference-draft',
         'language':language, 'calibration_source_sha256':identity})
    rasters, total = [], 0
    for number, image in pages(copy):
        path = previews/f'page-{number+1}.png'
        image.save(path, 'PNG')
        total += image.width*image.height
        rasters.append((number, path))
    budget, regions, failures, html = {'remaining':max(0,limit()-total-source_pixels)}, [], [], []
    from PIL import Image
    for number, path in rasters:
        with Image.open(path) as image:size=image.size
        try:
            with Image.open(path) as image:
                blocks = recognize_image(image, PACKS[language], number, image.size, retry_budget=budget)
        except (OCRUnavailable, OSError) as exc:
            blocks = []; failures.append({'page':number, 'reason':str(exc)})
        rows, overlays = [], []
        for block in blocks:
            region = {'id':f'p{number+1}-r{len(regions)+1}', 'page':number, 'order':len(regions),
                      'bbox':block['position'], 'text':block['text']}
            regions.append(region)
            rows.append(f'<li><b>{region["id"]}</b>: {escape(block["text"])} '
                        f'<small>bbox {escape(str(region["bbox"]))}</small></li>')
            x0,y0,x1,y1 = region['bbox']
            overlays.append(f'<rect x="{x0}" y="{y0}" width="{x1-x0}" height="{y1-y0}" '
                            f'fill="none" stroke="#d21d58" stroke-width="5"/>'
                            f'<text x="{x0}" y="{max(30,y0-8)}" fill="#a00030" font-size="30">{region["id"]}</text>')
        html.append(f'<h2>Page {number+1}</h2><a href="previews/{path.name}">Open full-resolution page</a>'
                    f'<svg role="img" aria-label="Source page {number+1} with candidate regions" '
                    f'viewBox="0 0 {size[0]} {size[1]}"><image href="previews/{path.name}" '
                    f'width="{size[0]}" height="{size[1]}"/>{"".join(overlays)}</svg><ol>{"".join(rows)}</ol>')
    copy.with_suffix('.txt').write_text('\n'.join(r['text'] for r in regions)+'\n', encoding='utf-8')
    save(copy.with_suffix('.regions.json'), regions)
    with (incoming/'info.csv').open('x', newline='', encoding='utf-8') as stream:
        writer = csv.DictWriter(stream, fieldnames=['file','language','capture_class','content_group_id',
                                                    'split','author','rights_note'])
        writer.writeheader()
        writer.writerow({'file':copy.name, 'language':language, 'content_group_id':identity,
                         'split':'calibration'})
    save(output/'corpus-review.json', {'reviewers':[], 'review_date':'',
         'attestation':'', 'coverage_reviewed':False})
    save(output/'draft-provenance.json', {'purpose':'unreviewed-reference-draft', 'acceptance_eligible':False,
         'generated_by':'local OCR; requires independent correction', 'source_sha256':identity,
         'coordinate_basis':'300 DPI PDF raster or full-resolution EXIF-transposed image',
         'pages':len(rasters), 'regions':len(regions), 'ocr_failures':failures})
    (output/'review.html').write_text('<!doctype html><meta charset="utf-8"><title>OCR review draft</title>'
        '<style>body{font:18px system-ui;max-width:1100px;margin:30px auto;padding:16px}'
        'svg{width:100%;border:1px solid #888}small{display:block}li{margin:14px 0}</style>'
        '<h1>Unreviewed OCR draft</h1><p>No accuracy score or approval is established. '
        'Check every page for missing text, wrong words, box positions and reading order. '
        'You can describe corrections in plain language; the operator can record them in the draft files. '
        'Generated text is not a completed independent review.</p>' + ''.join(html), encoding='utf-8')
    quote = lambda value: "'"+str(value).replace("'", "''")+"'"
    command = (f'Set-Location {quote(Path(__file__).resolve().parents[2])}\n'
               f'& {quote(sys.executable)} -m tools.ocr_kit advance --workspace {quote(output)}')
    (output/'START_HERE.md').write_text(
        '# OCR review packet\n\nThis is an unreviewed draft, not an acceptance report. '
        'It has not enabled OCR in the translation service. You can provide corrections in plain '
        'language and have the operator enter them; you do not need to edit JSON yourself.\n\n'
        '1. Open review.html to compare source pages with the candidate text. '
        'Check for missing text, wrong words, boxes and reading order.\n'
        '2. Correct the matching .txt and .regions.json files in incoming before requesting review. '
        'Keep their complete text consistent.\n'
        '3. Fill the actual capture type, collector and rights basis in incoming/info.csv. '
        'This prepared document stays calibration. Add genuinely unseen documents as separate files/rows; '
        'do not split pages of one book across calibration and held-out.\n'
        '4. Run the command below. It prepares a blank second-review.csv when metadata is complete. '
        'A person other than the collector checks the originals and completes it. '
        'The corpus-review.json file also requires actual coverage review.\n'
        '5. Run the same command again to resume. It reports blockers or evaluates at the unchanged95% gate. '
        'Only a valid passing evaluation plus a private signing key can produce a verified report. '
        'The command never changes live configuration.\n\n'
        f'```powershell\n{command}\n```\n\n'
        'workflow-status.json lists the current step and missing material. '
        'Independent review and source permissions have not been supplied or invented.\n', encoding='utf-8')
    return advance(output)


def advance(workspace, sign_key=None):
    """Resume existing kit stages, stopping before any missing human evidence."""
    workspace = Path(workspace).resolve()
    config = load_json(workspace/'workflow.json')
    if config.get('version') != 1 or config.get('language') not in PACKS:
        raise ValueError('Unsupported workflow configuration')
    required = [config['language']+' / '+category for category in ('scan','photo','screenshot')]
    fresh = intake(workspace/'incoming')
    missing = {scope:[split for split in ('calibration','heldout') if not any(
        s['language']+' / '+s['capture_class']==scope and s['split']==split for s in fresh['samples'])]
        for scope in required}
    missing = {scope:splits for scope,splits in missing.items() if splits}
    def stop(stage, blockers, **extra):
        result = {'stage':stage, 'acceptance_ready':False, 'banner':BANNER,
                  'live_configuration_changed':False, 'required_scopes':required,
                  'missing_splits':missing, 'blockers':blockers, **extra}
        save(workspace/'workflow-status.json', result)
        return result
    if any(s['image_sha256']==config['calibration_source_sha256'] and s['split']!='calibration'
           for s in fresh['samples']):
        return stop('needs_samples', ['The prepared/tuned source must remain calibration, not held-out.'])
    sheet = workspace/'second-review.csv'
    if fresh['gaps']:
        return stop('needs_source_metadata', fresh['gaps'])
    if not sheet.exists():
        save(workspace/'intake.json', fresh)
        reference_sheet(fresh, sheet)
        return stop('needs_independent_review', ['Complete second-review.csv against the actual originals.'])
    try:
        saved = current(load_json(workspace/'intake.json'))
        checks = ingest_checks(saved, sheet, workspace/'checks.json')
    except (ValueError, OSError, KeyError, TypeError) as exc:
        return stop('needs_independent_review', [str(exc)])
    approval = load_json(workspace/'corpus-review.json')
    if (approval.get('coverage_reviewed') is not True or not approval.get('reviewers')
            or not approval.get('review_date') or not approval.get('attestation','').strip()):
        return stop('needs_corpus_review', ['Complete corpus-review.json with actual review, not generated approval.'])
    if missing:
        return stop('needs_samples', ['Each required capture scope needs separate calibration and held-out documents.'])
    # A fresh run preserves earlier results and never overwrites frozen evidence.
    run = workspace/'runs'/uuid.uuid4().hex
    run.mkdir(parents=True)
    manifest_path = run/'corpus'/'manifest.json'
    try:
        build_manifest(saved, checks, approval, manifest_path.parent)
        report = evaluate(manifest_path, tesseract_command(), 95)
        save(run/'evaluation.json', report)
        if report['outcome'] != 'go':
            return stop('evaluation_hold', ['Evaluation did not pass all required scopes.'], report=str(run/'evaluation.json'))
        validate_report(report, manifest_path)
        if not sign_key:
            return stop('needs_signing_key', ['Supply a private acceptance key via --sign-key-file.'],
                        report=str(run/'evaluation.json'), manifest=str(manifest_path))
        signed = sign(report, sign_key, 'acceptance')
        state = readiness()
        for scope in report['categories']:
            language, category = scope.split(' / ')
            verify_report(signed, sign_key, manifest_path, state, language, category)
        save(run/'signed-report.json', signed)
    except (ValueError, OSError, KeyError, TypeError) as exc:
        return stop('evaluation_hold', [str(exc)], run=str(run))
    return stop('report_verified', [], acceptance_ready=True, report=str(run/'signed-report.json'),
                manifest=str(manifest_path), scope_scores={k:v['word_accuracy_percent'] for k,v in report['categories'].items()})
