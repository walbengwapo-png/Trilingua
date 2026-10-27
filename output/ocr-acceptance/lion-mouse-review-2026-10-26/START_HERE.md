# OCR review packet

This is an unreviewed draft, not an acceptance report. It has not enabled OCR in the translation service. You can provide corrections in plain language and have the operator enter them; you do not need to edit JSON yourself.

1. Open review.html to compare source pages with the candidate text. Check for missing text, wrong words, boxes and reading order.
2. Correct the matching .txt and .regions.json files in incoming before requesting review. Keep their complete text consistent.
3. Fill the actual capture type, collector and rights basis in incoming/info.csv. This prepared document stays calibration. Add genuinely unseen documents as separate files/rows; do not split pages of one book across calibration and held-out.
4. Run the command below. It prepares a blank second-review.csv when metadata is complete. A person other than the collector checks the originals and completes it. The corpus-review.json file also requires actual coverage review.
5. Run the same command again to resume. It reports blockers or evaluates at the unchanged95% gate. Only a valid passing evaluation plus a private signing key can produce a verified report. The command never changes live configuration.

```powershell
Set-Location 'C:\dev\Trilingua\trilingua-code\Model'
& 'C:\dev\Trilingua\trilingua-code\.venv-ocr-layout\Scripts\python.exe' -m tools.ocr_kit advance --workspace 'C:\dev\Trilingua\output\ocr-acceptance\lion-mouse-review-2026-10-26'
```

workflow-status.json lists the current step and missing material. Independent review and source permissions have not been supplied or invented.
