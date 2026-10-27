"""Create the four-page SONA speech-content excerpt used for time-boxed testing."""

from pathlib import Path

from pypdf import PdfReader, PdfWriter


ROOT = Path(r"C:\dev\Trilingua\chatgpt\test")
SOURCE = ROOT / "Original Files" / "SONA_2019_English.pdf"
OUTPUT = ROOT / "sona-four-page-excerpt" / "SONA_2019_English__pages-3-to-6.pdf"


def main() -> None:
    reader = PdfReader(str(SOURCE))
    if len(reader.pages) < 6:
        raise RuntimeError(f"Expected at least six pages, found {len(reader.pages)}")
    writer = PdfWriter()
    # Physical pages 1-2 are cover/front matter. Pages 3-6 contain the first
    # four pages of the English SONA speech and form the representative sample.
    for page in reader.pages[2:6]:
        writer.add_page(page)
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    with OUTPUT.open("wb") as stream:
        writer.write(stream)
    print(OUTPUT)


if __name__ == "__main__":
    main()
