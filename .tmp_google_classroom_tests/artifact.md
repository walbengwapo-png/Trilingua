# Google Classroom Test Cases Template Contract

## Reference

- Retained reference: `C:\dev\Trilingua\.tmp_google_classroom_tests\Sample_Test Case Template.docx`
- Original supplied file: `C:\Users\walbe\Downloads\Sample_Test Case Template.docx`
- SHA-256: `0CD10758147A28624FFC5628543F2B44F9F373D4CF463A1C952E38CE2D8483B3`
- Reference render: `C:\dev\Trilingua\.tmp_google_classroom_tests\template-reference-render`
- Style evidence: `C:\dev\Trilingua\.tmp_google_classroom_tests\template-style-evidence.json`
- Page count: 2 (page 1 is the editable blank form; page 2 is a 13.00 x 6.50 inch raster example)
- Section count: 1

## Page System

- Page size: 14.00 x 8.50 inches, landscape legal.
- Margins: 0.50 inch on all sides.
- One column; one continuous section; no special first, odd, or even-page header behavior.
- No populated header or footer and no page-number fields.
- Each completed test scenario should use the editable page-1 form pattern and start on a new page.

## Typography and Color

- Document default: Arial, 11 pt, black; default paragraph line spacing 276 twips (approximately 1.15).
- Form labels and column headers: Arial, 10 pt, bold, uppercase, white, single-spaced.
- Label and header fill: dark blue `#0B5394`.
- Body entries: Arial, 9-10 pt, black, single-spaced; preserve readable wrapping.
- Status values use the supplied dropdown control. The initial execution state should be `Not Tested` rather than the example's `Passed`.

## Tables and Components

- Metadata assembly: one borderless 1 x 2 outer layout table with two 6.50-inch columns.
- Left nested metadata table: 6 x 2; grid widths 1.677 and 4.656 inches; slots for Project Name, Module Name, Environment, Created By, Date of Creation, and Date of Review.
- Right nested metadata table: 2 x 2; grid widths 1.573 and 4.760 inches; slots for Test Case ID and Test Scenario.
- Main execution table: 6 x 7, consisting of one header row and five body rows.
- Main table grid widths: 2.219, 1.896, 1.958, 1.740, 1.792, 1.708, and 1.490 inches.
- Main headers, in order: Test Case, Pre-condition(s), Procedure(s), Test Data, Expected Result, Actual Result, and Status.
- Borders: preserve the reference's black single-line outer and internal grid.
- Status cells: vertically centered dropdown controls with choices Passed, Failed, Not Tested, Not Applicable, and Cannot be Tested.

## Content Flow and Slot Map

- `word/document.xml/body/tbl[1]`: editable metadata layout. Only value cells are rewritten; blue label cells are preserved.
- `word/document.xml/body/tbl[2]`: editable five-record test table. Header row is preserved. Body cells for Test Case through Expected Result are filled; Actual Result remains blank for the student tester; Status begins as Not Tested.
- The editable page pattern may be cloned for additional scenarios. Each cloned dropdown must receive a unique `w:id`.
- The final raster-example paragraph and its relationship-backed image are not part of the deliverable content and are removed from the visible body. The underlying media and relationship parts remain untouched as preserve-only package parts.
- Empty spacer paragraphs may be preserved or replaced with an explicit page-break paragraph between scenario pages.

## Package Preservation

- Editable part: `word/document.xml` only.
- Preserve-only parts and relationships: `word/styles.xml`, `word/theme/theme1.xml`, `word/numbering.xml`, `word/settings.xml`, `word/fontTable.xml`, `word/_rels/document.xml.rels`, `_rels/.rels`, `[Content_Types].xml`, and `word/media/image1.png`.
- Preserve-only SHA-256 values were captured during distillation and must remain byte-for-byte unchanged in the generated DOCX.
- Content controls are preserved structurally; only their IDs, selected value, displayed text, and value styling may change in cloned editable rows.

## Fidelity Gates

- Reference remains byte-for-byte unchanged at its recorded path.
- Final document remains one landscape legal section with 0.50-inch margins.
- Every scenario page visibly follows the same two-block metadata header and seven-column execution table.
- Dark-blue labels and headers, white uppercase header text, grid widths, and dropdown choices remain source-derived.
- No sample screenshot appears in the delivered document.
- No clipping, overlap, broken grid, unexpected pagination, or unreadably small text after rendering every final page.
- Final package audit confirms every preserve-only part is unchanged.
