# -*- coding: utf-8 -*-
"""
Document layout utilities.

Contains font mapping, style resolution, and background sampling
for document layout preservation during reconstruction.

Contains NO translation logic.
Reused from document_translator_v3.py.
"""


class FontMapper:
    """Centralises PDF font-name resolution.

    Resolution priority (highest → lowest):

    1. ``font_name`` is ``None`` or empty → return ``"helv"`` with warning.
    2. ``font_name.lower()`` matches any entry in *embedded_fonts* lowercased
       → return ``font_name`` as-is.
    3. ``font_name.lower()`` contains a monospace keyword → return ``"cour"``.
    4. ``font_name.lower()`` contains a serif keyword    → return ``"tiro"``.
    5. ``font_name.lower()`` contains a sans-serif keyword → return ``"helv"``.
    6. No match at all → return ``"helv"`` with warning.
    """

    _MONO_KEYWORDS = ("courier", "consolas", "mono")
    _SERIF_KEYWORDS = ("times", "georgia", "roman")
    _SANS_KEYWORDS = ("arial", "helvetica", "sans")

    def resolve(
        self,
        font_name: str | None,
        embedded_fonts: set[str],
        *,
        page: int | None = None,
        bbox: list | None = None,
    ) -> str:
        if not font_name:
            print("⚠️ FontMapper: font_name is None or empty; falling back to 'helv'.")
            return "helv"

        lower = font_name.lower()

        # Priority 2 — embedded font (case-insensitive match)
        if any(lower == ef.lower() for ef in embedded_fonts):
            return font_name

        # Priority 3 — monospace keywords
        if any(kw in lower for kw in self._MONO_KEYWORDS):
            return "cour"

        # Priority 4 — serif keywords
        if any(kw in lower for kw in self._SERIF_KEYWORDS):
            return "tiro"

        # Priority 5 — sans-serif keywords
        if any(kw in lower for kw in self._SANS_KEYWORDS):
            return "helv"

        # Priority 6 — unknown font; warn and fall back
        print(f"⚠️ FontMapper: unknown font '{font_name}'; falling back to 'helv'.")
        return "helv"


class StyleMapper:
    """Resolves a DOCX paragraph style name to a style available in the target document.

    Returns the style name unchanged when it is a non-empty string present in
    *available_styles*, and falls back to ``"Normal"`` in all other cases.
    """

    def resolve(
        self,
        style_name: str | None,
        available_styles: set[str],
    ) -> str:
        if not style_name:
            return "Normal"
        if style_name in available_styles:
            return style_name
        return "Normal"


class BackgroundSampler:
    """Samples the background colour of a PDF text block region.

    Uses the four corner pixels of the bbox to determine whether the
    background is a uniform colour. Returns ``(r, g, b)`` floats in
    ``[0, 1]`` when uniform, or ``None`` when the background is
    non-uniform or the bbox is degenerate.
    """

    @staticmethod
    def sample(page, bbox):
        """Sample background colour at the four corners of *bbox*."""
        x0, y0, x1, y1 = bbox

        if x0 >= x1 or y0 >= y1:
            return None

        pix = page.get_pixmap()

        pw = float(page.rect.x1 - page.rect.x0)
        ph = float(page.rect.y1 - page.rect.y0)
        if pw <= 0 or ph <= 0:
            return None
        px0 = max(0, min(pix.width - 1, int(x0 * pix.width / pw)))
        px1 = max(0, min(pix.width - 1, int(x1 * pix.width / pw)))
        py0 = max(0, min(pix.height - 1, int(y0 * pix.height / ph)))
        py1 = max(0, min(pix.height - 1, int(y1 * pix.height / ph)))

        corners = [
            pix.pixel(px0, py0),
            pix.pixel(px1, py0),
            pix.pixel(px0, py1),
            pix.pixel(px1, py1),
        ]

        first_r, first_g, first_b = corners[0]
        for r, g, b in corners[1:]:
            if r != first_r or g != first_g or b != first_b:
                return None

        return (first_r / 255.0, first_g / 255.0, first_b / 255.0)