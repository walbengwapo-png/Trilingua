from pathlib import Path
from docx import Document
from docx.shared import Inches, Pt, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.table import WD_TABLE_ALIGNMENT, WD_CELL_VERTICAL_ALIGNMENT
from docx.enum.section import WD_SECTION
from docx.oxml import OxmlElement
from docx.oxml.ns import qn

OUT = Path(r"C:\dev\Trilingua\chatgpt\Part2 test\TriLingua Third Iteration Provider Neutral Unit Pipeline Report.docx")

NAVY = "17365D"
BLUE = "DCE6F1"
PALE = "F4F7FB"
GRID = "D9D9D9"
TEXT = "1F2937"

def shade(cell, fill):
    tcPr = cell._tc.get_or_add_tcPr()
    shd = OxmlElement("w:shd")
    shd.set(qn("w:fill"), fill)
    tcPr.append(shd)

def borders(cell, color=GRID):
    tcPr = cell._tc.get_or_add_tcPr()
    tcBorders = tcPr.first_child_found_in("w:tcBorders")
    if tcBorders is None:
        tcBorders = OxmlElement("w:tcBorders")
        tcPr.append(tcBorders)
    for edge in ("top", "left", "bottom", "right", "insideH", "insideV"):
        tag = "w:" + edge
        el = tcBorders.find(qn(tag))
        if el is None:
            el = OxmlElement(tag)
            tcBorders.append(el)
        el.set(qn("w:val"), "single")
        el.set(qn("w:sz"), "5")
        el.set(qn("w:color"), color)

def margins(cell, top=100, start=110, bottom=100, end=110):
    tc = cell._tc
    tcPr = tc.get_or_add_tcPr()
    m = tcPr.first_child_found_in("w:tcMar")
    if m is None:
        m = OxmlElement("w:tcMar")
        tcPr.append(m)
    for side, value in (("top", top), ("start", start), ("bottom", bottom), ("end", end)):
        node = m.find(qn("w:" + side))
        if node is None:
            node = OxmlElement("w:" + side)
            m.append(node)
        node.set(qn("w:w"), str(value))
        node.set(qn("w:type"), "dxa")

def set_repeat_table_header(row):
    trPr = row._tr.get_or_add_trPr()
    el = OxmlElement("w:tblHeader")
    el.set(qn("w:val"), "true")
    trPr.append(el)

def set_cell_text(cell, text, bold=False, color=TEXT, size=8.5, align=None):
    cell.text = ""
    p = cell.paragraphs[0]
    if align is not None:
        p.alignment = align
    p.paragraph_format.space_after = Pt(0)
    p.paragraph_format.line_spacing = 1.04
    r = p.add_run(str(text))
    r.bold = bold
    r.font.name = "Aptos"
    r._element.rPr.rFonts.set(qn("w:ascii"), "Aptos")
    r._element.rPr.rFonts.set(qn("w:hAnsi"), "Aptos")
    r.font.size = Pt(size)
    r.font.color.rgb = RGBColor.from_string(color)
    cell.vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.CENTER
    margins(cell)
    borders(cell)

def add_table(doc, headers, rows, widths=None, font_size=8.5):
    table = doc.add_table(rows=1, cols=len(headers))
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    table.style = "Table Grid"
    table.autofit = False
    hdr = table.rows[0]
    set_repeat_table_header(hdr)
    for i, h in enumerate(headers):
        set_cell_text(hdr.cells[i], h, bold=True, color="FFFFFF", size=font_size, align=WD_ALIGN_PARAGRAPH.CENTER)
        shade(hdr.cells[i], NAVY)
        if widths:
            hdr.cells[i].width = Inches(widths[i])
    for ridx, row in enumerate(rows):
        cells = table.add_row().cells
        for i, value in enumerate(row):
            align = WD_ALIGN_PARAGRAPH.CENTER if i > 0 and len(str(value)) < 28 else WD_ALIGN_PARAGRAPH.LEFT
            set_cell_text(cells[i], value, size=font_size, align=align)
            if ridx % 2 == 1:
                shade(cells[i], PALE)
            if widths:
                cells[i].width = Inches(widths[i])
    doc.add_paragraph().paragraph_format.space_after = Pt(2)
    return table

def add_run(p, text, bold=False, italic=False, size=10, color=TEXT):
    r = p.add_run(text)
    r.bold = bold
    r.italic = italic
    r.font.name = "Aptos"
    r._element.rPr.rFonts.set(qn("w:ascii"), "Aptos")
    r._element.rPr.rFonts.set(qn("w:hAnsi"), "Aptos")
    r.font.size = Pt(size)
    r.font.color.rgb = RGBColor.from_string(color)
    return r

def para(doc, text="", lead=None):
    p = doc.add_paragraph()
    p.paragraph_format.space_after = Pt(7)
    p.paragraph_format.line_spacing = 1.12
    if lead:
        add_run(p, lead, bold=True)
    add_run(p, text)
    return p

def bullet(doc, text, level=0):
    p = doc.add_paragraph(style="List Bullet" if level == 0 else "List Bullet 2")
    p.paragraph_format.space_after = Pt(3)
    p.paragraph_format.line_spacing = 1.05
    add_run(p, text, size=9.5)
    return p

def heading(doc, text, level=1):
    p = doc.add_paragraph(style=f"Heading {level}")
    p.paragraph_format.space_before = Pt(13 if level == 1 else 9)
    p.paragraph_format.space_after = Pt(5)
    r = p.add_run(text)
    r.font.name = "Aptos Display" if level == 1 else "Aptos"
    r._element.rPr.rFonts.set(qn("w:ascii"), r.font.name)
    r._element.rPr.rFonts.set(qn("w:hAnsi"), r.font.name)
    r.font.size = Pt(15 if level == 1 else 11.5)
    r.font.color.rgb = RGBColor(0, 0, 0)
    r.bold = True
    return p

def page_break(doc):
    doc.add_page_break()

def footer(section):
    p = section.footer.paragraphs[0]
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p.paragraph_format.space_before = Pt(4)
    add_run(p, "TriLingua third iteration report  |  22 September 2026  |  Page ", size=8, color="606B78")
    fld = OxmlElement("w:fldSimple")
    fld.set(qn("w:instr"), "PAGE")
    p._p.append(fld)

def keep_with_next(p):
    pPr = p._p.get_or_add_pPr()
    el = OxmlElement("w:keepNext")
    pPr.append(el)

def build():
    doc = Document()
    sec = doc.sections[0]
    sec.top_margin = Inches(0.72)
    sec.bottom_margin = Inches(0.66)
    sec.left_margin = Inches(0.72)
    sec.right_margin = Inches(0.72)
    footer(sec)
    styles = doc.styles
    styles["Normal"].font.name = "Aptos"
    styles["Normal"]._element.rPr.rFonts.set(qn("w:ascii"), "Aptos")
    styles["Normal"]._element.rPr.rFonts.set(qn("w:hAnsi"), "Aptos")
    styles["Normal"].font.size = Pt(10)

    # Cover
    p = doc.add_paragraph(style="Title")
    p.paragraph_format.space_before = Pt(86)
    p.paragraph_format.space_after = Pt(13)
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    r = p.add_run("TriLingua Third Iteration\nProvider Neutral Unit Pipeline Report")
    r.font.name = "Aptos Display"
    r._element.rPr.rFonts.set(qn("w:ascii"), "Aptos Display")
    r._element.rPr.rFonts.set(qn("w:hAnsi"), "Aptos Display")
    r.font.size = Pt(27)
    r.font.color.rgb = RGBColor(0, 0, 0)
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p.paragraph_format.space_after = Pt(22)
    add_run(p, "Phase 1 through Phase 6 implementation, verification and acceptance evidence", size=13, color="4B5563")
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    add_run(p, "Test basis: Part2 bilingual story-book corpus and second test plan", size=11, color="4B5563")
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    add_run(p, "Prepared 22 September 2026", size=10, color="4B5563")
    para(doc, "This report records the third iteration of the document-translation improvement work. It connects the provider-neutral design, the Phase 1 to 5 implementation changes, and the Phase 6 controlled live acceptance benchmark into one auditable account. The report is intended for project review and production-readiness decisions.")
    page_break(doc)

    heading(doc, "Executive summary")
    para(doc, "The third iteration delivered a provider-neutral, DTO-based translation-unit pipeline and exercised it with GPT-OSS under a controlled Phase 6 benchmark. The implementation preserves legacy behavior behind a restart-gated feature flag, adds semantic batching, protected-span handling, layout preflight, provider capability scheduling, systemic fail-fast semantics, and detailed timing metrics.")
    para(doc, "The Phase 6 acceptance verdict is CONDITIONAL PASS. All six live runs preserved the 25-page story-book structure, kept all 49 source blocks present and ordered, passed layout validation, and recorded zero provider retries or failures. The report does not claim that the new pipeline is superior to the supplied GPT-OSS artifacts: its observed median automatic scores were lower, and that older baseline lacks runtime and configuration metadata needed for a controlled causal comparison.")
    add_table(doc,
        ["Decision area", "Current conclusion", "Evidence"],
        [
            ["Architecture", "Ready for controlled use", "Provider-neutral interfaces and unit-pipeline checks passed on every live run."],
            ["Structural and layout integrity", "Pass", "25 pages, 49/49 blocks, ordered results, and layout validation passed in all 6 runs."],
            ["Reliability", "Pass under test", "No provider retries or provider failures; timeout path verified to fail fast."],
            ["Quality promotion", "Not yet approved", "Scores differ from supplied GPT-OSS artifacts; a matched legacy-mode benchmark is required."],
            ["Known defects", "Follow up before default-on", "A verse numeral is lost in Cebuano to English; one short block is intentionally passed through."],
        ], [1.75, 1.55, 3.2], 8.6)
    heading(doc, "Scope and test basis", 2)
    para(doc, "The governing test case for this report is the second Part2 test plan, the bilingual story-book corpus. It contains two parallel 25-page editions: English to Cebuano and Cebuano to English. It is appropriate for testing document context, page reconstruction, protected spans, structural survival, and end-to-end latency. It is not a complete layout fixture suite because it contains no complex tables; conclusions about table layout therefore remain intentionally limited.")
    add_table(doc, ["Corpus property", "English source", "Cebuano source"], [
        ["Document", "60 Heaven God s Beautiful Home", "60 Langit Ang Nindot nga Puluy anan sa Dios"],
        ["Pages", "25", "25"],
        ["Extracted source text", "5,763 characters", "7,114 characters"],
        ["Direction", "English to Cebuano", "Cebuano to English"],
        ["Reference", "Parallel Cebuano edition", "Parallel English edition"],
    ], [2.1, 2.2, 2.2])

    heading(doc, "Background and decision context")
    para(doc, "The initiative is a pipeline improvement, not a provider replacement project. GPT-OSS was treated as a quality candidate rather than the architectural reference. NLLB remains the reproducible local Part2 baseline, not the prescribed design. Every provider should receive the same document context, protected-span controls, quality review and repair, layout safeguards, scheduling rules, and observability before a production selection is made.")
    add_table(doc, ["Iteration", "Purpose", "What the evidence supports"], [
        ["Iteration 1", "NLLB Part2 evaluation", "A reproducible local fast-mode baseline with stable short samples and intact 25-page output."],
        ["Iteration 2", "Supplied GPT-OSS artifacts", "Higher automatic scores on the story-book corpus, but no captured runtime, cache, fallback, or model-configuration metadata."],
        ["Iteration 3", "Phases 1 to 6 unit-pipeline work", "A controlled GPT-OSS-only acceptance run with full pipeline evidence; conditional, not final, production promotion."],
    ], [1.15, 2.0, 3.35])
    para(doc, "Automatic metrics are regression signals, not a substitute for bilingual acceptance. BLEU and chrF measure similarity to these particular published editions after whitespace-only normalization; they do not independently establish naturalness, theological accuracy, age appropriateness, terminology consistency, or page-level visual quality.")

    page_break(doc)
    heading(doc, "Implementation report")
    para(doc, "The following phases show what changed in the third iteration, why the change was made, and how it was verified. The implementation deliberately preserves a narrow compatibility boundary: legacy dictionaries are adapted to typed units once, and legacy output shapes remain available to the surrounding application.")

    phases = [
        ("Phase 1 Typed translation units and document map", "Scope", "Introduced allocation-light DTOs in dto pipeline.py: TranslationUnit, TranslationUnitResult, ProtectedSpan and ProviderCapabilities. Added document map.py and protected spans.py, with unit adapters as the single dictionary-to-DTO and DTO-to-dictionary boundary.", "Why it matters", "A typed core makes unit identity, reading order, geometry, source text, contextual metadata and protected spans explicit without inserting Pydantic validation or JSON serialization in the hot path. Legacy dictionary shapes remain supported at the boundary."),
        ("Phase 2 Context parity and safe routing", "Scope", "Added unit adapters build_provider_hint and the TRANSLATION_UNIT_PIPELINE feature-flag branch that routes document pipeline work to batch_translate_units when enabled.", "Why it matters", "The provider receives the same relevant document context as the legacy path. The default is off and the setting is read once at import, so switching modes is restart-gated and supports non-breaking A/B comparison."),
        ("Phase 3 Semantic boundaries and layout preflight", "Scope", "Added semantic-boundary batching and document layout_preflight.py. Semantic chunks provide context and batch boundaries only; they never merge translation units. Preflight persists advisory fit information as a sidecar.", "Why it matters", "Semantic grouping improves consistency while preserving each unit's independent source identity. Layout preflight improves reconstruction decisions without mutating source geometry or silently changing document structure."),
        ("Phase 4 Capability batching and fair scheduling", "Scope", "Added capability-aware batching and the process-wide FairDocumentBatchScheduler for GPT-OSS. It uses str(id(ctx)) to identify document work and no thread pool. Full DTO execution now covers echo guard, quality review and repair, cache storage and protected-span restoration.", "Why it matters", "The scheduler obeys provider limits and records queue behavior. Systemic failures use a RuntimeError gate and abort instead of returning source text as a false success. Per-unit paths retain their own identity and error evidence."),
        ("Phase 4 1 Completion of the DTO execution path", "Scope", "Completed the application of DTOs through provider dispatch, quality handling, restoration and result collection, while exposing scheduler metrics to the engine metrics surface.", "Why it matters", "This removes the gap between defining typed units and using them for the real document path. The acceptance suite can now verify both actual provider metrics and layout-preflight presence."),
        ("Phase 5 GPT OSS batched provider behavior", "Scope", "Implemented GPTOSSProvider translate_many with capability packing, ID-keyed U uid batch prompts, junk-tolerant response parsing, systemic-error markers and GPTOSSProviderError. Added isolated failure retention and provider request, retry and failure metrics surfaced through engine metrics.", "Why it matters", "ID-keyed results prevent an unrelated malformed response from corrupting positional mapping. Explicit systemic markers prevent rate-limit, timeout and server-failure responses from being misrepresented as translated source text."),
        ("Phase 6 Controlled live acceptance", "Scope", "Ran GPT-OSS only against both story-book directions, three times each, with balanced mode, unit-pipeline flag on, cache off and fallback disabled. Captured structure, spans, automatic metrics, per-stage times and output hashes.", "Why it matters", "The evidence tests the full new path under known conditions. It creates a reproducible current baseline and exposes both correctness and performance limits before default-on deployment."),
    ]
    for title, l1, t1, l2, t2 in phases:
        heading(doc, title, 2)
        para(doc, t1, lead=l1 + ": ")
        para(doc, t2, lead=l2 + ": ")

    page_break(doc)
    heading(doc, "Architecture map")
    para(doc, "The implementation separates document interpretation, provider-independent orchestration, provider-specific transport, and reconstruction. The unit boundary is the key control point: a unit carries enough context to translate safely while retaining a stable identity for scheduling, retry, restoration and audit.")
    add_table(doc, ["Layer", "Key files", "Responsibility"], [
        ["Typed core", "dto pipeline.py", "Defines translation units, results, protected spans and provider capabilities using slots-based DTOs."],
        ["Document understanding", "document map.py; protected spans.py; semantic chunker.py", "Preserves reading order and structure; identifies spans that must survive unchanged; creates semantic context boundaries."],
        ["Unit adaptation", "pipeline unit adapters.py", "Performs the single legacy dictionary and typed-unit conversion and builds provider context hints."],
        ["Orchestration", "pipeline document pipeline.py; translation pipeline.py", "Routes through the restart-gated unit pipeline and manages review, repair, cache and restoration."],
        ["Scheduling", "pipeline fair scheduler.py", "Batches work within provider capabilities, controls document fairness and records queue metrics."],
        ["Provider", "providers gptoss.py; providers base.py", "Performs ID-keyed batch translation, isolates unit errors and classifies systemic failures."],
        ["Layout", "document layout preflight.py; reconstructor.py", "Creates non-mutating fit advice, reconstructs the PDF and validates layout."],
        ["Configuration and metrics", "config runtime.py; engine metrics surface", "Reads the pipeline flag at startup and exposes provider, scheduler and stage timing evidence."],
    ], [1.25, 2.0, 3.25], 8.2)
    heading(doc, "Execution flow", 2)
    add_table(doc, ["Step", "Data or decision", "Safety property"], [
        ["1 Extract", "PDF structure, geometry and reading order become a document map.", "Source layout is observed before translation."],
        ["2 Prepare", "Protected spans and semantic context are attached to each unit.", "URLs, emails, numbers and designated literals can be restored."],
        ["3 Schedule", "Compatible units are packed according to provider capabilities.", "Unit identities are not merged; scheduler limits are explicit."],
        ["4 Translate", "Provider returns ID-keyed results for U uid records.", "Malformed or isolated failures stay attached to the affected unit."],
        ["5 Review", "Echo guard, quality review and selective repair run on typed results.", "Source echo does not silently pass as a translation."],
        ["6 Rebuild", "Layout preflight advises fit; reconstruction paints and validates output.", "Preflight does not mutate source geometry."],
        ["7 Evidence", "Metrics, span checks, structure checks and hashes are persisted.", "A result can be evaluated without treating source text as success on systemic failure."],
    ], [0.7, 3.3, 2.5], 8.5)

    page_break(doc)
    heading(doc, "Testing and verification evidence")
    para(doc, "Verification combined focused unit-pipeline coverage, targeted regression, the broader non-live suite, isolated analysis-resilience tests, code inspection and the controlled Phase 6 live benchmark. The tests are complementary: unit tests establish expected local behavior; end-to-end acceptance demonstrates that the exercised pipeline keeps structure, spans and failure semantics under a real provider.")
    add_table(doc, ["Evidence set", "Result", "Interpretation"], [
        ["Unit-pipeline tests", "73 tests", "Covers DTO conversion, batching, scheduling, provider batch parsing, protected spans and pipeline behavior."],
        ["Targeted regression", "265 passed; 2 skipped", "Confirms relevant regression suite behavior after the pipeline work."],
        ["Full non-live suite", "363 passed; 1 pre-existing issue", "The existing hypothesis 0 0 issue is recorded as pre-existing rather than attributed to this iteration."],
        ["Analysis-resilience tests", "28 isolated", "Exercises document-analysis resilience separately from the live provider acceptance."],
        ["Phase 6 live acceptance", "6 completed runs", "Tests both Part2 story-book directions three times each under stated controlled settings."],
    ], [1.55, 1.35, 3.6], 8.5)
    heading(doc, "Phase 6 method", 2)
    bullet(doc, "Provider and model: gptoss, gpt-oss:20b-cloud. No NLLB or Gemini provider participated in these runs.")
    bullet(doc, "Mode: balanced. Unit-pipeline feature flag enabled. Translation cache disabled. Translation fallback disabled.")
    bullet(doc, "Repetitions: three per direction, for six live runs in total. Quality scoring: corpus BLEU and chrF over all PDF pages after whitespace normalization only.")
    bullet(doc, "Hard checks: 25-page structure, non-empty extracted text, ordered 49-block survival, layout validation, protected spans, runtime verification data and systemic fail-fast behavior.")
    bullet(doc, "Reproducibility: source and reference hashes, output hashes, run metadata, benchmark manifest and detailed findings were retained. Different output hashes across runs are expected generative variance, not a structural failure.")
    heading(doc, "Acceptance criteria and outcome", 2)
    add_table(doc, ["Criterion", "Observed outcome", "Status"], [
        ["Layout fidelity", "25 pages and layout validation pass in all 6 runs.", "PASS"],
        ["Block survival and order", "49 of 49 blocks present and ordered in every run.", "PASS"],
        ["Unit-pipeline verification", "Provider metrics and layout-preflight evidence present in every run.", "PASS"],
        ["Systemic fail-fast", "Batch timeout aborts through the RuntimeError gate; no false source-as-success result.", "PASS"],
        ["Emails, URLs, placeholders", "No missing protected email, URL or placeholder span in any run.", "PASS"],
        ["Numbers", "11 of 11 preserved en to ceb; 11 of 12 preserved ceb to en due to numeral 22.", "CONDITIONAL"],
        ["Quality versus supplied GPT-OSS", "Lower medians in both directions; historical comparison is not method-matched.", "OBSERVED VARIANCE"],
        ["Provider retries and failures", "0 retries and 0 recorded failures in all six runs.", "PASS"],
    ], [1.65, 3.9, 0.95], 8.3)

    page_break(doc)
    heading(doc, "Phase 6 acceptance results")
    para(doc, "All latency figures are median wall time from the three live runs. The supplied GPT-OSS numbers are retained as historical quality comparison only. They do not have runtime metadata, configuration, cache state or fallback state, so no performance comparison or causal pipeline-regression claim can be made from them.")
    add_table(doc, ["Direction", "Live median BLEU", "Supplied BLEU", "Live median chrF", "Supplied chrF", "Median wall", "Result"], [
        ["English to Cebuano", "28.27", "29.68", "60.77", "61.86", "831.8 s", "Conditional"],
        ["Cebuano to English", "44.55", "52.52", "70.71", "74.33", "838.7 s", "Conditional"],
    ], [1.3, 0.85, 0.8, 0.85, 0.8, 0.8, 1.05], 8.2)
    heading(doc, "English to Cebuano run detail", 2)
    add_table(doc, ["Run", "Wall s", "BLEU", "chrF", "Blocks", "Batches", "Echo retries", "Repolish", "Output hash"], [
        ["1", "772.8", "29.38", "60.77", "49/49", "3", "1", "6", "0dbbafd05ea3"],
        ["2", "831.8", "27.84", "60.91", "49/49", "3", "0", "9", "a92aaed56fea"],
        ["3", "990.4", "28.27", "60.02", "49/49", "3", "1", "8", "a858152806c3"],
    ], [0.45, 0.65, 0.55, 0.55, 0.75, 0.6, 0.8, 0.65, 1.35], 8.1)
    para(doc, "Median result: BLEU 28.27, chrF 60.77 and 831.8 seconds. All 49 blocks were translated and batched. No protected email, URL, number or placeholder was missing. No provider retries or failures were recorded.")
    heading(doc, "Cebuano to English run detail", 2)
    add_table(doc, ["Run", "Wall s", "BLEU", "chrF", "Blocks", "Batches", "Echo retries", "Repolish", "Output hash"], [
        ["1", "620.5", "44.76", "70.80", "49/49", "3", "6", "16", "ce3b7fc59ef6"],
        ["2", "838.7", "44.55", "70.71", "49/49", "3", "6", "14", "8ac058460289"],
        ["3", "870.3", "43.83", "70.19", "49/49", "3", "6", "15", "f86f200dbd8f"],
    ], [0.45, 0.65, 0.55, 0.55, 0.75, 0.6, 0.8, 0.65, 1.35], 8.1)
    para(doc, "Median result: BLEU 44.55, chrF 70.71 and 838.7 seconds. Forty-eight units were translated and batched; one short unit was intentionally retained by the pass-through pre-filter. The block remains present, so this is visible behavior rather than content loss. One verse numeral, 22, was missing in all three runs.")
    heading(doc, "Latency decomposition", 2)
    para(doc, "The 10 to 16 minute end-to-end duration is not evidence of a general pipeline slowdown. Remote model and balanced-mode LLM work dominate. Each document's 48 to 49 translated units packed into three translate_many posts, and the environment set GPTOSS_TRANSLATION_SLOTS and TRANSLATION_MAX_CONCURRENT to one. The posts therefore ran serially, and scheduler queue time accumulated while GPT-OSS generated.")
    add_table(doc, ["Measured driver", "Observed range or condition", "Effect"], [
        ["Provider HTTP time", "170 to 436 seconds per run", "A material portion of the translation stage is waiting for remote model generation."],
        ["Scheduler queue wait", "Up to 638 seconds", "Three provider batches serialize with one available slot."],
        ["Balanced-mode work", "About 57 to 71 LLM calls per run", "Per-block review, document analysis and 6 to 16 coherence-repolish chunks add quality work."],
        ["Echo guard", "6 re-translations on every ceb to en run", "Protects against source-language echoes but adds provider calls and latency."],
    ], [1.45, 1.75, 3.4], 8.4)

    page_break(doc)
    heading(doc, "Findings, risks and tradeoffs")
    heading(doc, "Findings from the current acceptance run", 2)
    add_table(doc, ["Finding", "Evidence", "Impact and interpretation"], [
        ["Verse numeral loss", "The numeral 22 is omitted from the multi-number scripture citation in all three Cebuano to English outputs.", "Minor but deterministic protected-number defect. It prevents an unconditional release verdict for this direction."],
        ["Pass-through block", "One short Cebuano to English block is deliberately kept verbatim in each run.", "No block is lost and the result is traceable, but the behavior needs product review before default-on use."],
        ["Quality variance", "Live medians are 28.27 / 60.77 and 44.55 / 70.71 versus supplied 29.68 / 61.86 and 52.52 / 74.33.", "Cannot be assigned to the pipeline without recreating the legacy-mode comparison in the same environment."],
        ["Serialization lever", "One scheduler slot means the three provider batches are serial.", "Increasing concurrency may lower latency, but must be reviewed against provider limits, error behavior and output quality."],
        ["Story-book coverage limit", "The corpus has no complex tables.", "Passing layout checks does not demonstrate robust table, multi-column or complex caption behavior."],
    ], [1.45, 2.45, 2.7], 8.2)
    heading(doc, "Decisions already embodied in the design", 2)
    bullet(doc, "No Pydantic or JSON serialization is introduced in the translation hot path. The slots-based DTOs keep the typed core light while keeping the conversion boundary explicit.")
    bullet(doc, "Systemic provider failure is fail-fast. Rate limit, timeout and server-side failure indicators should abort visibly rather than returning the source as a successful translation.")
    bullet(doc, "The pipeline flag is restart-gated. This makes behavior deterministic during a running process and supports deliberate A/B benchmarks, at the cost of not allowing an instant runtime toggle.")
    bullet(doc, "Preflight is advisory. It may record fit guidance but does not mutate source geometry, avoiding untracked layout drift before reconstruction.")
    bullet(doc, "A provider is selected by a shared quality, reliability and measured-latency gate. GPT-OSS is a candidate, not an architectural dependency or automatic default.")
    heading(doc, "Risk register", 2)
    add_table(doc, ["Risk", "Current control", "Remaining action"], [
        ["Automatic-score comparison may overstate a pipeline effect", "Historical values are labelled as supplied and not runtime-comparable.", "Run legacy mode with the same corpus, harness and environment."],
        ["Protected numeric data can be lost in composite citations", "Protected-span checks identify the loss.", "Extend numeric-token restoration to multi-number lists and add a regression fixture."],
        ["Slow live runs may be unacceptable in production", "Scheduler/provider/stage metrics isolate waits and provider time.", "Benchmark safe slot and concurrency settings under the same acceptance gate."],
        ["Layout confidence is corpus-bound", "All changed pages passed validation on this corpus.", "Add table, long-cell, column, header/footer and mixed-font fixtures with rendered review."],
        ["Intentional pass-through may surprise users", "Metric blocks_passthrough makes it observable.", "Define product policy and reviewer handling for short untranslated candidates."],
    ], [1.7, 2.2, 2.7], 8.1)

    page_break(doc)
    heading(doc, "Recommendations and release path")
    para(doc, "Do not switch the unit pipeline on by default for all production work yet. The architecture and hard correctness checks are strong enough for controlled use, but the deterministic numeral defect and unmatched historical-quality comparison warrant a short, evidence-driven follow-up cycle.")
    add_table(doc, ["Priority", "Recommendation", "Completion evidence"], [
        ["1", "Fix and test numeric-token restoration for multi-number scripture citations, including 22.", "New unit and end-to-end fixture passes with every expected numeric span preserved."],
        ["2", "Run a matched legacy-mode benchmark: feature flag off, same two PDFs, same three repetitions, provider, model, balanced mode, cache and fallback settings.", "Side-by-side manifest and metrics isolate pipeline effect from provider drift or harness differences."],
        ["3", "Review safe production concurrency. Test more than one provider slot only within GPT-OSS service limits and repeat the full acceptance gate.", "Median latency, provider failures, retries, structure, spans and bilingual quality remain acceptable."],
        ["4", "Define the policy for short pass-through units and reviewer escalation.", "Product decision is encoded in acceptance checks and user-visible result handling."],
        ["5", "Extend layout fixtures beyond the story-book corpus.", "Rendered checks cover tables, long cells, columns, captions, headers/footers, image-adjacent labels and mixed fonts."],
        ["6", "Perform bilingual human review before a provider default decision.", "Review captures grammar, naturalness, tone, cohesion, terminology and meaning preservation, not automatic scores alone."],
    ], [0.6, 3.55, 2.45], 8.2)
    heading(doc, "Release recommendation", 2)
    para(doc, "Approve the third-iteration pipeline for continued controlled evaluation with GPT-OSS. Keep the feature flag off by default until the numeral restoration fix and a matched legacy-mode benchmark are complete. When those results are available, use the same provider-neutral acceptance gate to decide whether the unit pipeline becomes the default for a defined quality profile.")

    heading(doc, "Evidence inventory and traceability")
    para(doc, "The following artifacts form the basis for this report. They should be retained with the release decision so that the story-book corpus, measured results and configuration remain distinguishable from earlier supplied artifacts.")
    add_table(doc, ["Artifact", "Role in this report"], [
        ["TriLingua Provider Neutral Pipeline Improvement Report", "Architecture rationale, provider-neutral interfaces and original improvement order."],
        ["Part2 Translation Quality Layout and Speed Improvement Report", "NLLB baseline, prior quality/layout/speed observations and corpus limitations."],
        ["Part2 Iteration 1 NLLB Evaluation", "Reproducible NLLB fast-mode baseline and stability evidence."],
        ["Part2 Iteration Comparison and Current State Logging Audit", "Historical GPT-OSS comparison limitations and operational evidence context."],
        ["Phase 6 ACCEPTANCE.md", "Current verdict, acceptance matrix, per-run results, latency decomposition and findings."],
        ["Phase 6 findings.json and benchmark-manifest.json", "Machine-readable settings, source/reference hashes, output hashes, timings, spans, metrics and per-run observations."],
        ["Model DTO, document, pipeline and provider source files", "Implementation inventory for the Phase 1 through Phase 5 description."],
    ], [2.6, 4.0], 8.4)
    para(doc, "Report conclusion: the third iteration establishes a sound, auditable provider-neutral pipeline path and a first controlled GPT-OSS baseline. It has passed structural, layout and reliability checks on the defined story-book corpus, with targeted follow-up required before broad default-on deployment.")

    # Ensure title style has no visual line/border and metadata is clean.
    props = doc.core_properties
    props.title = "TriLingua Third Iteration Provider Neutral Unit Pipeline Report"
    props.subject = "Phase 1 through Phase 6 implementation and acceptance evidence"
    props.author = "TriLingua Project"
    props.comments = ""
    OUT.parent.mkdir(parents=True, exist_ok=True)
    doc.save(OUT)
    print(OUT)

if __name__ == "__main__":
    build()
