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

    _MONO_KEYWORDS = ("courier", "consolas", "mono", "monospace", "andale mono",
                      "source code", "cascadia", "fira code", "jetbrains")
    _SERIF_KEYWORDS = ("times", "georgia", "roman", "garamond", "palatino",
                       "bookman", "caslon", "baskerville", "hoefler", "goudy")
    _SANS_KEYWORDS = ("arial", "helvetica", "sans", "calibri", "segoe", "tahoma",
                      "verdana", "futura", "gill", "century gothic", "trebuchet",
                      "candara", "corbel", "open sans", "lucida", "franklin gothic",
                      "myriad", "noto sans", "roboto", "ubuntu", "dejavu sans")

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

    def resolve_to_pdf_name(
        self,
        font_name: str | None,
        embedded_font_programs: dict[str, bytes],
        *,
        page: int | None = None,
        bbox: list | None = None,
        required_codepoints: set[int] | None = None,
    ) -> tuple[str, bytes | None]:
        """Resolve to a PDF font name that covers *required_codepoints*.

        Returns ``(pdf_fontname, fontbuffer_or_None)``.

        Resolution strategy
        -------------------
        1. If *font_name* is ``None``/empty → ``('helv', None)``.
        2. Try each embedded font program in *embedded_font_programs* that
           belongs to the same category (sans / serif / mono) as *font_name*.
           If one covers all *required_codepoints*, return its name and buffer.
        3. If no embedded font covers the codepoints, try the matching
           Base-14 built-in (helv / tiro / cour) — these are guaranteed
           to support Latin-1 accented characters.
        4. Fall back to the original *font_name* from *embedded_font_programs*
           (no glyph guarantee, matches old behaviour).
        """
        import fitz

        if not font_name:
            return ("helv", None)

        if not required_codepoints:
            pdf_name = self.resolve(font_name, set(embedded_font_programs))
            fb = embedded_font_programs.get(font_name)
            return (pdf_name, fb)

        lower = font_name.lower()
        category = self._classify(lower)

        # Try each embedded font of the same category
        for ef_name, ef_buffer in embedded_font_programs.items():
            if not ef_buffer:
                continue
            ef_lower = ef_name.lower()
            ef_cat = self._classify(ef_lower)
            if ef_cat != category:
                continue
            if self._covers_codepoints(ef_buffer, required_codepoints):
                return (ef_name, ef_buffer)

        # Fall back to Base-14 built-in
        base14_map = {"sans": "helv", "serif": "tiro", "mono": "cour", "other": "helv"}
        fallback = base14_map.get(category, "helv")
        try:
            f = fitz.Font(fallback)
            fnt = fitz.Font(fontbuffer=f.buffer)
            if self._covers_codepoints_check(fnt, required_codepoints):
                return (fallback, None)
        except Exception:
            pass

        # Last resort — return original embedded font unchanged
        fb = embedded_font_programs.get(font_name)
        return (font_name, fb)

    def _classify(self, font_name_lower: str) -> str:
        if any(kw in font_name_lower for kw in self._MONO_KEYWORDS):
            return "mono"
        if any(kw in font_name_lower for kw in self._SERIF_KEYWORDS):
            return "serif"
        if any(kw in font_name_lower for kw in self._SANS_KEYWORDS):
            return "sans"
        return "other"

    @staticmethod
    def _covers_codepoints(fontbuffer: bytes, codepoints: set[int]) -> bool:
        import fitz
        try:
            fnt = fitz.Font(fontbuffer=fontbuffer)
            return FontMapper._covers_codepoints_check(fnt, codepoints)
        except Exception:
            return False

    @staticmethod
    def _covers_codepoints_check(fnt, codepoints: set[int]) -> bool:
        for cp in codepoints:
            try:
                if not fnt.has_glyph(cp):
                    return False
            except Exception:
                return False
        return True


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