# Connected OCR advisory coordinator - 26 October 2026

Status: implemented and live-connected; production OCR acceptance remains unchanged. Base5ae47df on codex/hybrid-ocr-functional.

## Behavior

`python -m tools.ocr_kit coordinate --workspace <review-packet>` uses the existing configured analysis route without starting the server. It gathers bounded workflow facts and visible native-PDF text missing from calibration drafts. The AI can select program-grounded candidate IDs for separate draft proposals, ask known workflow questions, or stop. The program validates every action/ID/argument and rechecks source fingerprints before writing. No model action can execute commands, edit canonical references, invent permissions/reviewers, evaluate acceptance, sign a report or change live settings.

The coordinator is text/geometry based. It does NOT inspect page pixels, independently certify OCR/translation quality, or send held-out text/geometry to a provider. It is useful for preparation and triage, not an automatic acceptance authority. Proposal geometry/reading order remains unreviewed. Generated notes never count as independent human sign-off.

One decision is requested per invocation, with a90-second request-local transport allowance and a late-response check. Gemini gets one attempt, followed only by the already configured Ollama fallback if enabled. This is not a hard DNS/OS process-cancellation guarantee or a recurring background monitor. Inputs/outputs stay inside the selected workspace, subject to documented file/page/candidate/prompt limits. Existing offline commands remain offline; the new command explicitly uses the configured provider and may incur its ordinary cost.

## Live evidence

On the existing Lion/Mouse review packet, the real CLI made one HTTP200 Gemini Interactions request using the configured gemini-3.5-flash-lite model. Provider transport22.141seconds; total22.375seconds. No fallback request was observed. The AI selected prepare_proposals for the two program-identified visible page numbers1 and2. New separate reference drafts contain10 regions, versus the original8. Original source, intake references, review statements and live .env hashes stayed unchanged. No acceptance report/key or reviewer approval was issued.

Actual decision/report/proposals are under `output/ocr-acceptance/lion-mouse-review-2026-10-26/coordinator-runs/ca39fba9d61e4a83973dbe3f703b4701/`. Start with that folder's review.html, or the packet's AI_COORDINATOR.md. HTML was rendered in installed Chrome, inspected visually, and all three links were checked against actual local files. No page images or held-out content were sent to Gemini; it selected actions from text/geometry observations, rather than discovering the omissions through vision.

## Checks

Selected offline suite:337 Python tests passed, including16 new coordinator tests and30 existing analysis-resilience tests.52 PHP tests/255 assertions and4 browser checks passed. The new cases cover separate-draft preparation, hidden native text exclusion, held-out content exclusion, unsafe actions/IDs/extra arguments, provider failure, concurrent input changes, path escape rejection, escaped HTML and provider selection. Model responses and generated test material in unit tests are explicitly mocked; only the separately logged actual request is live-provider evidence.

The initial combined run exposed six order-dependent failures in existing mocked provider tests: earlier modules loaded the live Gemini3.5 setting, while those fixtures return Gemini2.5 GenerateContent envelopes. The analysis module passed alone. A test-local fixture now pins its intended Gemini2.5 model; explicit Gemini3 Interactions tests remain intact. No production model or application behavior was changed to obtain a passing result.

No dependency installed, server started/restarted, acceptance threshold lowered, default provider changed, or unrelated Phase A/provider/admin hunk modified. Only intended existing CLI/docs/test-fixture files changed, plus the new coordinator and its tests. Preservation hashes and live request logs are under `output/reviews/ocr-ai-coordinator-2026-10-26/`.

## Remaining

The existing acceptance workflow still needs genuine acquisition/rights/capture details, corrected complete references, independent human review and unseen representative material. The connected AI can organize those requirements, but cannot truthfully supply another person's confirmation. Existing Cebuano translation-quality concerns and final translated-image replacement verification remain separate release blockers.
