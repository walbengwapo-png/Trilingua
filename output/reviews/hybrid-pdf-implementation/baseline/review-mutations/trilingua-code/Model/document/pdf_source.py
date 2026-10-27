"""A durable original image may serve as a PDF template without OCR or reflow."""
from contextlib import contextmanager
from pathlib import Path
import tempfile
import fitz


@contextmanager
def original_pdf(path):
    if Path(path).suffix.lower() == '.pdf':
        yield str(path)
        return
    from PIL import Image
    expected={'.png':'PNG','.jpg':'JPEG','.jpeg':'JPEG'}.get(Path(path).suffix.lower())
    if expected is None: raise ValueError('Unsupported PDF template format')
    with Image.open(path) as image:
        if image.format != expected or getattr(image,'n_frames',1) != 1:
            raise ValueError('Upload a single PNG/JPEG matching its extension')
        if min(image.size) < 200 or image.width*image.height > 40_000_000:
            raise ValueError('Image resolution must be at least 200 pixels per side and at most 40 MP')
    with tempfile.TemporaryDirectory(prefix='trilingua-pdf-source-') as directory:
        output=str(Path(directory)/'source.pdf')
        with fitz.open(path) as source:
            data=source.convert_to_pdf()
        with fitz.open('pdf',data) as doc:doc.save(output)
        yield output
