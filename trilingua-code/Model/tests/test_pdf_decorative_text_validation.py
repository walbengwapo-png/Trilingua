"""Validate mixed-size lettering without inventing missing glyphs."""
import re

import pymupdf as fitz
import pytest

from validators.translation_validator import validate_pdf_output


@pytest.mark.parametrize("missing_letter", [False, True])
def test_decorative_lettering_accepts_content_order_but_requires_all_letters(tmp_path, missing_letter):
    source = tmp_path / "lettering.pdf"
    with fitz.open() as doc:
        page = doc.new_page(width=300, height=200)
        page.insert_text((46, 130), "B", fontsize=30)
        x = 75
        for index, size in enumerate((36, 30, 24, 18)):
            if not (missing_letter and index == 1):
                page.insert_text((x, 138), " Z", fontsize=size)
            x += fitz.get_text_length(" Z", fontsize=size)
        # Region covers the first three diminishing Zs and overlaps the B.
        rect = fitz.Rect(66.01, 91.3, 155.01, 148.764)
        if not missing_letter:
            clip = rect + (-2, -2, 2, 2)
            assert "ZZZ" in re.sub(r"\s", "", page.get_text(clip=clip, sort=False))
            assert "ZZZ" not in re.sub(r"\s", "", page.get_text(clip=clip, sort=True))
        doc.save(source)
    placement = dict(block_index=0, source_page=0, page=0, rect=list(rect),
                     text="Z Z Z", font_size=24, action="passthrough")
    report = validate_pdf_output(source, [placement], 1)
    assert report["status"] == ("failed" if missing_letter else "passed")
    if missing_letter:
        assert any("missing rendered text" in issue for issue in report["issues"])
