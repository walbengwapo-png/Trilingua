"""Reserve unique image pixels from metadata before PyMuPDF hashes/decodes."""
import os

DEFAULT_JOB_PIXEL_BUDGET = 120_000_000
BUDGET_REASON = 'aggregate_decoded_pixel_budget_exceeded'


def limit():
    value = int(os.environ.get('OCR_JOB_PIXEL_BUDGET', DEFAULT_JOB_PIXEL_BUDGET))
    if value <= 0:
        raise ValueError('OCR_JOB_PIXEL_BUDGET must be positive')
    return value


def image_inventory(doc):
    cached = getattr(doc, '_hybrid_image_inventory', None)
    if cached is not None:
        return cached
    used, admitted, held, pages = 0, set(), set(), []
    for page in doc:
        resources = {r[0]: r[2]*r[3] for r in page.get_images(full=True)}
        previews = page.get_image_info(xrefs=False, hashes=False)
        inline = max(0, sum(i['width']*i['height'] for i in previews)-sum(resources.values()))
        needed = sum(size for xref,size in resources.items() if xref not in admitted) + inline
        # Hash-based xref resolution decodes every resource on a page. Hold the
        # whole page's images if admitting that decode would exceed the budget.
        over = used + needed > limit() or any(i['width']*i['height'] > 40_000_000 for i in previews)
        if over:
            held.update(resources)
        else:
            used += needed
            admitted.update(resources)
        images = previews if over else page.get_image_info(xrefs=True, hashes=False)
        for image in images:
            if over or image['width']*image['height'] > limit():
                image.update(xref=0, budget_hold=True)
        pages.append(images)
    doc._hybrid_image_inventory = pages
    doc._hybrid_budget_held = held
    doc._hybrid_pixels_used = used
    return pages


def check_actions(actions):
    unique = {}
    for action in actions:
        size = action['image_size'][0]*action['image_size'][1]
        identity = (action['page'], action['xref'])
        if identity in unique and unique[identity] != size:
            raise ValueError('Inconsistent image sizes in plan')
        unique[identity] = size
    if sum(unique.values()) > limit():
        raise ValueError(BUDGET_REASON)
