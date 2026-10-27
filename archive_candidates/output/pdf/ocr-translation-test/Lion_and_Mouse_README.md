# The Lion and the Mouse: mixed-text OCR fixture

Two-page adaptation of Aesop's story in The Aesop for Children (1919), illustrated by Milo Winter. Story wording preserved; layout changed, both dialogue paragraphs rasterized at 216 dpi.

Source: https://www.gutenberg.org/files/19994/19994-h/19994-h.htm
Illustration: https://www.gutenberg.org/files/19994/19994-h/images/i014_th.jpg
Source catalog and rights statement (public domain in the USA): https://www.gutenberg.org/ebooks/19994

10 text blocks total: title, six story/moral paragraphs, attribution, two page numbers. Eight selectable blocks and two image-only dialogue blocks. Two illustration placements are additional images, not text blocks. No hidden OCR overlay is attached to either dialogue image. No alt text stores dialogue in the PDF.

Page 1 image-only dialogue begins: "Spare me!"
Page 2 image-only dialogue begins: "You laughed when I said I would repay you,"

The JSON manifest contains exact expected text, page numbers, bounding boxes and block types for comparison. Block count is the authored paragraph/region count; another layout detector may segment differently. PyMuPDF extraction was also checked to remain below 20 text regions including both raster dialogue blocks.

Verified page count, native text presence, dialogue absence from native extraction and visual page rendering. TriLingua OCR and translation have not been run.
