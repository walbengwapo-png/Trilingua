"""A durable original image may serve as a PDF template without OCR or reflow."""
from contextlib import contextmanager
from pathlib import Path
import tempfile
import os
import fitz
from document.pdf_regions import MAX_PAGES, MAX_PIXELS


def _check_pdf_limits(path):
    with fitz.open(path) as doc:
        if len(doc) > MAX_PAGES:
            raise ValueError('Hybrid PDF limit is 50 pages')
        if any(page.rect.get_area() * (300/72)**2 > MAX_PIXELS for page in doc):
            raise ValueError('Page exceeds 40 MP limit')
        if any(image[2]*image[3] > MAX_PIXELS for page in doc for image in page.get_images(full=True)):
            raise ValueError('Source image exceeds 40 MP limit')


@contextmanager
def original_pdf(path):
    if Path(path).suffix.lower() == '.pdf':
        _check_pdf_limits(path)
        yield str(path)
        return
    from PIL import Image
    expected={'.png':'PNG','.jpg':'JPEG','.jpeg':'JPEG'}.get(Path(path).suffix.lower())
    if expected is None: raise ValueError('Unsupported PDF template format')
    with Image.open(path) as image:
        if image.format != expected or getattr(image,'n_frames',1) != 1:
            raise ValueError('Upload a single PNG/JPEG matching its extension')
        if min(image.size) < 200 or image.width*image.height > MAX_PIXELS:
            raise ValueError('Image resolution must be at least 200 pixels per side and at most 40 MP')
        from document.pixel_budget import limit, BUDGET_REASON
        if image.width*image.height > limit():
            raise ValueError(BUDGET_REASON)
    with tempfile.TemporaryDirectory(prefix='trilingua-pdf-source-', dir=os.environ.get('OCR_JOB_SCRATCH')) as directory:
        output=str(Path(directory)/'source.pdf')
        with fitz.open(path) as source:
            data=source.convert_to_pdf()
        with fitz.open('pdf',data) as doc:doc.save(output)
        _check_pdf_limits(output)
        yield output
