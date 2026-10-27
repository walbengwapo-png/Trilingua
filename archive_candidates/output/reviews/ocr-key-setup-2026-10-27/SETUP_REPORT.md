# Persistent local OCR keys - 27 October 2026

Completed the two durable private-key settings in the shared local .env:
- OCR_ACCEPTANCE_KEY_FILE: a valid private acceptance-verification key.
- OCR_PLAN_KEY_FILE: a separate valid private rendering-plan key.

Keys are stored outside the repository under the current account's LocalAppData/TriLingua/ocr/keys folder. Folder and file ACL checks allow only the current Windows account, SYSTEM and Administrators. No key values were printed or committed. A byte-verified .env backup is in the same protected folder. Only the two key-path entries were added; unrelated .env content was preserved. The .env file is ignored by Git.

Checked purpose/version/material and independent32-byte secrets, rendering-signature round-trip, and tamper rejection. A second fresh Python process loaded the persistent settings, inventoried the actual Lion/Mouse source and signed/verified its reconstruction plan without a temporary override. The source stayed unchanged; six native blocks and four held image regions were recorded. No translated PDF, acceptance report or provider request was produced by this setup test.

Still pending:
- OCR_ACCEPTANCE_REPORT: there is no qualifying reviewed evaluation report yet.
- OCR_CORPUS_MANIFEST: there is no frozen, reviewed corpus catalog yet.

No placeholder or AI-generated approval was installed. English scan/photo/screenshot acceptance still holds. This is a configuration improvement, not evidence that hybrid translation is ready.

The already-running backend was not inspected/restarted. A fresh process sees the keys; a running service must reload settings before relying on them. This setup does not rotate any previously configured persistent key. Older test plans signed with temporary keys retain their original key association; their downloaded PDFs are unaffected.

Evidence: setup-result.json and fresh-process-check.json in this folder. No application code or default provider was changed.
