# TriLingua feature-evidence audit

**Audit date:** 2026-09-19  
**Scope:** the implemented product, not the marketing copy alone.  Code was
inspected in `trilingua-code/config/translation.php`, the Laravel routes and
controllers, the Blade views, and the Python translation pipeline.

## Bottom line

TriLingua has real, implemented features, but it does **not** yet have the
research required to claim that its translations are accurate, that one mode is
better than another, or that its quality score represents actual translation
quality. No interview results, completed usability study, or completed
human-reviewed English--Cebuano--Filipino benchmark were found.

The repository's own benchmark README confirms this: all 12 current benchmark
records are marked `pending_human_review`. The root README also says NLLB-200
powers the app, but the current `Model/document_translator_v3.py` identifies
Gemini as the sole translation engine. That public claim must be corrected
before a presentation or deployment.

Literature can establish that a feature is *plausible* or follows a recognized
standard. It cannot verify that **this** product works for Philippine users or
these three language pairs. The last column below makes that boundary explicit.

## Evidence status

| Label | Meaning |
| --- | --- |
| **Supported principle** | A credible study or standard supports the general design principle, not TriLingua's result. |
| **Needs product validation** | Useful functionality, but no study found that demonstrates the claimed benefit for TriLingua. Test it with the intended users. |
| **Do not claim yet** | The application displays or promises a result that must be calibrated against human evidence first. |
| **Correct marketing** | The feature exists, but the present description is technically inaccurate. |

## Feature-by-feature evidence matrix

| Implemented feature | What the cited study/standard actually supports | Study / standard | Status and required action |
| --- | --- | --- | --- |
| English, Cebuano, and Filipino text translation in all directions | NLLB demonstrated large-scale multilingual MT and evaluated 40,000+ directions with a human-translated benchmark; it does **not** validate TriLingua's Gemini output. | [NLLB Team et al., 2022](https://arxiv.org/abs/2207.04672) | **Needs product validation.** Evaluate all six directions with qualified bilingual reviewers and locally relevant content. |
| “Accurate translation” claim | High-quality MT needs human, context-aware error evaluation; system rankings can change with inadequate evaluation. | [Freitag et al., 2021](https://aclanthology.org/2021.tacl-1.87/) | **Do not claim yet.** Replace “accurate” with “AI-assisted translation; review important content” until the benchmark is complete. |
| Direct Cebuano ↔ Filipino translation | Multilingual translation research makes non-English-centric directions feasible, but capability varies materially by language and direction. | [NLLB Team et al., 2022](https://arxiv.org/abs/2207.04672) | **Needs product validation.** Report each direction separately; do not infer Cebuano ↔ Filipino quality from English-centred results. |
| Quick text translation, 8,000-character limit, language swap, clear input | These are interaction conveniences, not an accuracy method. No product-specific evidence or rationale for the 8,000-character limit was found. | [WCAG 2.2 — input, names, roles and status](https://www.w3.org/TR/WCAG22/) | **Needs product validation.** Test task completion and whether the limit is clear and appropriate. Keep labels, keyboard access, errors and live status accessible. |
| Translation modes: fast, balanced, thorough, and auto | A latency–quality trade-off is a reasonable hypothesis, but no experiment in the repository shows these modes differ as advertised. | [Scarton et al., 2019](https://aclanthology.org/2019.iwslt-1.23/) | **Do not claim yet.** Benchmark the same corpus in every mode; publish median/p90 time and human quality, not names such as “thorough” as a quality guarantee. |
| Document translation (DOCX, PDF, TXT, MD, RTF, ODT, CSV, PPTX, XLSX) | Document-level context can improve document MT over sentence-only MT in evaluated settings; this does not prove support or fidelity for every file type. | [Sun et al., 2022](https://aclanthology.org/2022.findings-acl.279/) | **Needs product validation.** Build a per-format preservation suite with tables, slides, formulas, headers/footers and long documents, then report pass rates. |
| Document context, terminology/style analysis, chunking and reconstruction | Context-aware document MT is a researched direction; it still requires a document-level human evaluation, especially for reference, terminology and layout errors. | [Wang et al., 2023](https://aclanthology.org/2023.emnlp-main.1036/) | **Needs product validation.** Blindly compare context-enabled output against a no-context baseline and annotate discourse/terminology errors. |
| PDF column selector (auto / single / left / right) | It is an engineering control for extraction ambiguity. No study or in-repository evaluation establishes its accuracy. | [Sun et al., 2022](https://aclanthology.org/2022.findings-acl.279/) | **Needs product validation.** Test multi-column, bilingual and scanned PDFs; expose a clear “check reading order” warning. |
| OCR fallback for scanned PDFs | OCR enables text extraction from images, but OCR mistakes propagate into translation; the current setup's language packs and accuracy were not evaluated. | [ICDAR Robust Reading Competition framework](https://rrc.cvc.uab.es/) | **Needs product validation.** Measure character/word error rate separately for English, Filipino and Cebuano scans; require user review for low-confidence OCR. |
| Download translated document / re-download original | A necessary task-completion and traceability facility, not evidence of translation quality or layout fidelity. | [W3C WCAG 2.2](https://www.w3.org/TR/WCAG22/) | **Needs product validation.** In usability testing, measure whether participants can obtain and identify the correct file; add a visual-diff/preservation test before claiming format preservation. |
| Copy output and save text as `.txt` | Reduces retyping and is consistent with accessible interaction, but no result shows it is needed by TriLingua users. | [W3C WCAG 2.2 — accessible authentication examples include copy/paste](https://www.w3.org/WAI/WCAG22/Understanding/accessible-authentication-minimum.html) | **Needs product validation.** Keep it as a low-risk convenience; verify discoverability in task testing. |
| Read source and translation aloud | Can support an alternative output/input modality, but browser speech quality and voice availability for Filipino and Cebuano are device-dependent. | [W3C Web Speech API](https://webaudio.github.io/web-speech-api/) | **Needs product validation.** Test actual browser/OS voices with target users; never claim Cebuano voice coverage without a device matrix. |
| Progress indicator and asynchronous document jobs | Communicating status is an accessibility requirement; it is not evidence that the queue is understandable or timely for users. | [WCAG 2.2, Success Criterion 4.1.3](https://www.w3.org/TR/WCAG22/#status-messages) | **Supported principle.** Retain ARIA status; test wait-time comprehension and cancellation/retry needs. |
| Saved translation history, details, rename, delete and re-download | Supports recall and record management, but no evidence says which records users need to retain or for how long. | [Nielsen's heuristic: recognition rather than recall](https://www.nngroup.com/articles/recognition-and-recall/) | **Needs product validation.** Interview users about retention, privacy and retrieval tasks before treating history as a core value proposition. |
| Search, sort, language-pair/status filter and grouping | These are information-retrieval controls; no evidence establishes the chosen filters, grouping, or order for the target population. | [ISO 9241-11 usability framework](https://www.iso.org/standard/63500.html) | **Needs product validation.** Measure success/time for “find a prior translation” tasks and collect search logs. |
| Bookmarks and priority-review request | These express user intent, but no research is present on whether they match users' real workflow or whether priority changes service outcomes fairly. | [ISO 9241-11 usability framework](https://www.iso.org/standard/63500.html) | **Needs product validation.** Ask interview participants how they revisit and escalate translations; instrument usage before expanding it. |
| Retranslate a stored document to another target language | A plausible reuse feature. It does not establish semantic equivalence or safety across a second translation. | [Freitag et al., 2021](https://aclanthology.org/2021.tacl-1.87/) | **Needs product validation.** Treat it as a new translation and re-evaluate it with human review. |
| User dashboard: counts, language mix, activity, recent work | Activity dashboards may inform a user's work, but none of the shown metrics establishes translation quality or user value. | [ISO 9241-11 usability framework](https://www.iso.org/standard/63500.html) | **Needs product validation.** Interview users about decisions they make from each card. Remove unused or misleading metrics. |
| “Average Quality Score” and quality-by-language-pair dashboard | An AI score is not a validated quality measure merely because the app calculates it. Quality estimates need calibration against expert human assessments. | [Freitag et al., 2021](https://aclanthology.org/2021.tacl-1.87/) | **Do not claim yet.** Hide the score or label it “automated risk signal — not human-verified” until correlation/calibration is measured for each direction. |
| Notifications for completed/failed translations | Notifications can help users resume a job, but their timing, content and interruption cost have not been studied here. | [WCAG 2.2 status messages](https://www.w3.org/TR/WCAG22/#status-messages) | **Needs product validation.** Test whether users want notifications, what they should say, and whether they should be optional. |
| Light/dark theme preference | Theme choice is a user preference/accessibility accommodation; no universal productivity or readability claim follows from its presence. | [WCAG 2.2 contrast guidance](https://www.w3.org/WAI/WCAG22/Understanding/contrast-minimum.html) | **Supported principle.** Check contrast in both themes and ask users which they prefer; do not claim that dark mode improves performance. |
| Responsive UI, labelled controls, ARIA live regions and error messages | WCAG provides testable criteria for names/roles/values, contrast, resize and status messages. It is a standard, not proof that this UI passes. | [WCAG 2.2](https://www.w3.org/TR/WCAG22/) | **Needs conformance test.** Run automated and manual keyboard/screen-reader testing, then publish the conformance level only if it passes. |
| Registration, login, password reset, Google sign-in and account settings | Authentication and account recovery are expected security/accessibility functions. Their security cannot be inferred from the feature list. | [NIST SP 800-63B-4](https://pages.nist.gov/800-63-4/sp800-63b.html) | **Needs security review.** Threat-model account recovery, test rate limits and session handling, and document data retention. |
| File-upload validation, quotas and server-side processing | File uploads are an attack surface; extension checks alone are not sufficient. | [OWASP File Upload Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/File_Upload_Cheat_Sheet.html) | **Supported principle; needs security test.** Run malware/content-type/path-traversal tests and verify storage access controls. |
| Admin review queue, edit/verify/flag actions and audit log | Human-in-the-loop review is appropriate for assessing MT, and expert document-context evaluation is materially stronger than unstructured crowd ratings. | [Freitag et al., 2021](https://aclanthology.org/2021.tacl-1.87/) | **Supported principle.** Define reviewer qualifications, a shared error rubric and a disagreement process; audit log does not itself guarantee quality. |
| AI post-edit / regeneration after admin edits | Automatic post-editing can improve outputs in evaluated settings, but benefits are language-pair and baseline dependent. | [Chatterjee et al., 2020](https://aclanthology.org/2020.wmt-1.75/) | **Needs product validation.** Compare regenerated files against the human-approved version; prevent an automatic step from overwriting verified edits. |
| Admin quality, turnaround and system-health analytics / CSV exports | Operational monitoring is useful, but quality metrics need defined provenance and validation before they drive decisions. | [Freitag et al., 2021](https://aclanthology.org/2021.tacl-1.87/) | **Do not claim quality insights yet.** Define each metric, data source, missing-data treatment and decision it informs; validate score thresholds. |

## Claims that must change now

These edits do not require waiting for a study:

1. Remove “powered by NLLB-200” from the root README and any demo material,
   unless the deployed engine is changed back and evidenced. The current Python
   implementation names Gemini as the sole translator.
2. Replace “fast, accurate translation” with “AI-assisted translation” and show
   a prominent review warning for legal, medical, government, academic and
   safety-critical content.
3. Do not describe `fast`, `balanced`, or `thorough` as measured quality tiers.
   Use neutral names such as “processing option” until their trade-off is
   benchmarked.
4. Do not present a 0–100 quality score as translation quality. It is an
   uncalibrated automated signal until compared with expert MQM annotations.
5. Do not claim document-format or layout preservation for every listed format
   until each is tested with a representative preservation suite.

## Minimum research needed to verify TriLingua

### 1. Discovery interviews — establish the right features

Recruit intended users before changing the roadmap: students, teachers,
government/community staff and professional translators who use English,
Filipino and/or Cebuano. Include native/primary users of Cebuano and Filipino;
do not use English-only participants as a proxy.

Use semi-structured interviews to learn:

- the last real document they needed translated, its format, destination and
  consequences of an error;
- whether they need text, document, OCR, history, retranslation, bookmarking,
  priority review, read-aloud and dashboards;
- terminology, code-switching, formality and regional-language expectations;
- data sensitivity, retention and consent expectations; and
- which quality and failure information lets them decide whether to trust,
  edit, download or escalate a result.

Do not ask “Would you use this feature?” alone. Have each participant perform a
realistic task with a prototype, then ask about observed friction. Obtain
informed consent, avoid collecting sensitive source documents unless approved,
and anonymize interview data.

### 2. Translation-quality study — establish the core product claim

Build a held-out corpus for **each of the six directions**: English ↔ Cebuano,
English ↔ Filipino and Cebuano ↔ Filipino. It must contain the document types
and domains users named in interviews, not only convenient sentences. Keep a
separate test set that was never used in prompting, tuning or reviewer
training.

For each direction and domain:

1. Have two qualified bilingual reviewers independently annotate blinded model
   output with an MQM-style rubric (accuracy, terminology, fluency, style,
   locale, safety and document-context errors).
2. Reconcile disagreements with a third reviewer and record agreement rather
   than silently averaging it away.
3. Report major-error rate, error categories, human adequacy/fluency ratings,
   and confidence intervals by language direction and domain. Automated BLEU
   and chrF may be supplementary, never the sole evidence.
4. For document translation, review the full document and separately score
   reading order, tables, headers/footers, slides, spreadsheets and formatting.
5. Publish the model/provider/version, prompt policy, date, corpus composition,
   reviewer qualifications and known limitations with the result.

NLLB's work is a useful model here: it combined a human-translated multilingual
benchmark with human evaluation rather than relying on a model name alone.

### 3. Mode and score validation — establish the current UI claims

Run the exact held-out corpus through fast, balanced, thorough and auto modes.
For each mode report median and p90 latency, failure rate, cost (if relevant),
and the same human-quality outcomes. A mode may be labelled “faster” or
“higher-quality” only when its results justify it.

For the displayed quality score, freeze a scored sample and compare its output
against human MQM results per language direction. Report correlation, false
reassurance (high automated score but major human error) and the rationale for
any threshold. If the score cannot reliably triage review, remove it from user
and admin decision screens.

### 4. Usability and accessibility study — establish supporting features

Run moderated task tests with the same intended-user groups. Tasks should cover
text translation, document upload, PDF-column choice, reading/downloading the
result, finding a saved translation, bookmarking/priority review, responding to
a notification, and using account recovery. Capture completion rate, time,
critical errors, observed confusion and post-task confidence; administer the
[System Usability Scale](https://digital.ahrq.gov/health-it-tools-and-resources/evaluation-resources/workflow-assessment-health-it-toolkit/all-workflow-tools/system-usability-scale-sus)
only as a usability measure, not proof of translation accuracy.

Also perform a WCAG 2.2 AA audit across keyboard-only navigation, screen reader
announcements, both themes, zoom/reflow, form errors and the translated text's
language metadata. Browser-based text-to-speech needs its own device/voice
coverage matrix.

## Evidence sources used

1. NLLB Team et al. (2022), *No Language Left Behind: Scaling Human-Centered
   Machine Translation* — [paper](https://arxiv.org/abs/2207.04672).
2. Freitag et al. (2021), *Experts, Errors, and Context: A Large-Scale Study of
   Human Evaluation for Machine Translation* — [paper](https://aclanthology.org/2021.tacl-1.87/).
3. Sun et al. (2022), *Rethinking Document-level Neural Machine Translation* —
   [paper](https://aclanthology.org/2022.findings-acl.279/).
4. Wang et al. (2023), *Document-Level Machine Translation with Large Language
   Models* — [paper](https://aclanthology.org/2023.emnlp-main.1036/).
5. Scarton et al. (2019), *Estimating post-editing effort* —
   [paper](https://aclanthology.org/2019.iwslt-1.23/).
6. Chatterjee et al. (2020), *Findings of the WMT 2020 Shared Task on Automatic
   Post-Editing* — [paper](https://aclanthology.org/2020.wmt-1.75/).
7. World Wide Web Consortium, *Web Content Accessibility Guidelines 2.2* —
   [standard](https://www.w3.org/TR/WCAG22/).
8. National Institute of Standards and Technology, *SP 800-63B-4: Digital
   Identity Guidelines* — [standard](https://pages.nist.gov/800-63-4/sp800-63b.html).
9. OWASP, *File Upload Cheat Sheet* —
   [guidance](https://cheatsheetseries.owasp.org/cheatsheets/File_Upload_Cheat_Sheet.html).

## What this audit does and does not verify

It verifies the feature inventory against the checked-out code and links each
feature to the strongest applicable research or standard found. It does **not**
pretend that literature or code inspection is an actual interview, human
translation evaluation, accessibility conformance review or security audit.
Those are the studies still required to make product claims responsibly.
