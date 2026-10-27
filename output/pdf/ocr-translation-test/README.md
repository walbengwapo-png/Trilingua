# OCR and translation test material

Source: NASA / Jet Propulsion Laboratory, Mariner to Mercury, Venus and Mars.
Original PDF: https://mars.nasa.gov/files/mep/Mars-Mission-Mariner-Fact-Sheet.pdf
Usage: https://www.nasa.gov/nasa-brand-center/images-and-media/
NASA permits educational/informational reuse under its media guidelines. Acknowledge NASA/JPL; NASA marks are protected. This is reusable educational material, not an open-source software license.

Both PDFs have three pages. The original is unchanged. The mixed-text test PDF is an adapted fixture, not a naturally mixed original.

Page 1: the left-column second paragraph, beginning "The Mariners were all relatively small robotic explorers" and ending "send useful scientific data for three years.", is a 216-dpi raster image with no text overlay. Surrounding paragraphs remain selectable. Pages 2 and 3 remain selectable text.

Expected image-only text (manual transcription from the visible source):
The Mariners were all relatively small robotic explorers, each launched on an Atlas rocket with either an Agena or Centaur upper-stage booster, and weighing less than half a ton (without onboard rocket propellant). Each of their missions was completed within a few months to a year or two, though one of them outlived its original mission and continued to send useful scientific data for three years.

Checks: three pages; one image on page 1; image paragraph absent from native extraction; surrounding opening paragraph present. extractable-text.txt records extraction without OCR.

A successful test should recover and translate the image paragraph as well as the native text, without duplicating either. OCR/translation through TriLingua has not been run. The original uses legacy font encoding, which produces some replacement characters in text extraction.
