# Translation quality benchmark v1

This corpus exercises all six English, Cebuano, and Filipino directions across
conversation, academic, government, business, health, instruction, and compact
document-layout text. References are **candidates**, not a claim of professional
review: each record remains `pending_human_review` until two qualified native
reviewers approve it.

Run the configured provider against the corpus:

```powershell
python benchmarks/run_benchmark.py --server-url http://127.0.0.1:5000
```

Run it once per provider/model configuration and compare the JSON reports. The
command records request latency and sacreBLEU/chrF when `sacrebleu` is installed.
Only approved records are included by default; use `--include-pending` while
building the reviewed corpus.
