"""Shared PDF image references must survive native-text replacement."""
import pymupdf as fitz
import pytest

from document.extractor import read_pdf
from document.reconstructor import write_pdf_preserved


@pytest.mark.parametrize("damage_image", [False, True])
def test_shared_image_resource_is_not_mistaken_for_changed_bytes(tmp_path, monkeypatch, damage_image):
    source, output = tmp_path / "shared.pdf", tmp_path / "output.pdf"
    with fitz.open() as doc:
        page = doc.new_page(width=300, height=200)
        page.insert_text((30, 60), "Source heading", fontsize=12)
        pix = fitz.Pixmap(fitz.csRGB, fitz.IRect(0, 0, 20, 20), False)
        pix.clear_with(128)
        page.insert_image(fitz.Rect(30, 100, 60, 130), pixmap=pix)
        stream_xref = page.get_contents()[-1]
        stream = doc.xref_stream(stream_xref)
        doc.update_stream(stream_xref, stream + b"\n" + stream)
        before = [(im["digest"], im["bbox"]) for im in page.get_image_info(hashes=True)]
        doc.save(source)
    if damage_image:
        apply_redactions = fitz.Page.apply_redactions

        def damage_after_redaction(page, *args, **kwargs):
            result = apply_redactions(page, *args, **kwargs)
            image_xref = page.get_images()[0][0]
            page.parent.update_stream(image_xref, bytes(20 * 20 * 3))
            return result

        monkeypatch.setattr(fitz.Page, "apply_redactions", damage_after_redaction)
    blocks = read_pdf(str(source), "single")
    blocks[0].update(text="Hubad", _original_text=blocks[0]["text"])
    if damage_image:
        with pytest.raises(ValueError, match="I1:image-bytes-changed"):
            write_pdf_preserved(blocks, str(source), str(output), strict=True)
        assert not output.exists()
    else:
        report = write_pdf_preserved(blocks, str(source), str(output), strict=True)
        assert report["status"] == "passed"
        with fitz.open(output) as doc:
            assert [(im["digest"], im["bbox"]) for im in doc[0].get_image_info(hashes=True)] == before
            assert "Hubad" in doc[0].get_text() and "Source heading" not in doc[0].get_text()
