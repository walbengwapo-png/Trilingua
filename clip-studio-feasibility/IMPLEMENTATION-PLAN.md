# Local clip studio: feasibility and implementation plan

Prepared: 5 October 2026, Asia/Manila.

## 1. Decision

**Proceed with a small, local, single-user clipper pilot. Do not treat the full original feature list or its income potential as validated.**

- **Hardware:** your i5-14400 PC can perform captioned 1080 × 1920 exports; this was tested successfully. CPU transcription and a quantized small language model are technically supported, but their speed and quality on your content remain unmeasured.
- **Workflow:** feasible for permitted speech-led videos with human selection, editable captions and manual crop. Automatic highlight ranking and speaker tracking need separate validation.
- **Business:** potentially useful as your own production tool or for an authorized editing service. There is no evidence yet of customer demand, profitable campaign access or dependable platform income.
- **Generation:** retain it as a later module. Script + TTS + existing stock footage is plausible; locally generating new high-quality video with a diffusion model is a substantially different workload and is outside this plan.

**Confirmed direction:** use your own/client videos, spend **₱0 on software subscriptions, cloud AI or hardware**, and use this PC with free tools. The main viability test is usable editing output and time saved; campaign payouts and channel advertising are not the basis of the build.

**Planning assumptions:** one user, one heavy processing stage at a time, local video imports, manual posting, initial speech-led 1080p sources. Usual source language, duration and target output volume have not been supplied. Existing electricity, internet and storage use are real operating costs, even when there is no new purchase.

Keep this project separate from the existing TriLingua application. These planning and benchmark files are stored beside it for convenience; implementing the clipper should use its own project directory and environment.

## 2. Your PC: confirmed findings

| Item | Inspected configuration | Practical implication |
|---|---|---|
| CPU | Intel Core i5-14400, 10 cores / 16 threads | Suitable candidate for CPU ASR and a small quantized LLM; does not establish measured inference speed. |
| Graphics | Intel UHD Graphics 730; no NVIDIA adapter reported | Quick Sync rendering works. The normal faster-whisper CUDA backend cannot use this GPU. |
| RAM | 16 GB installed, 15.79 GiB visible, 2 × 8 GB DDR4-3200 | Use sequential model stages; do not keep ASR and a 4B LLM resident together initially. |
| Current memory headroom | Initially 1.02 GiB free; 2.11 GiB at the later snapshot | Insufficient comfortable headroom for a useful 4B scoring benchmark while the current workload remains active. |
| Background workload | Game/client, browser and other apps; about 30% CPU use at one sample | Results depend on what else is running. Do not plan reliable heavy processing while gaming. |
| Storage | Approximately 476 GiB SATA SSD, initially 213 GiB free | Enough for a pilot; source footage and proxies need an explicit retention policy. |
| OS | Windows 11 Pro, 64-bit | Native Windows implementation is suitable; Docker and WSL are not requirements. |
| Existing tools | Python 3.11, Node, Ollama 0.35.1 | Useful starting point; pin and test the clipper's own environment. |
| Local models | llama3.2:1b Q8_0; remaining listed models were cloud aliases | A cloud model name in Ollama does not mean that model runs on this PC. The 1B model is not a demonstrated substitute for the proposed scorer. |
| Initially missing | FFmpeg on PATH and faster-whisper/CTranslate2 in the inspected global Python environment | Installed a portable benchmark copy of FFmpeg only; no PATH changes, ASR installation or model downloads were performed. Other uninspected environments may differ. |

Intel's specification independently confirms the i5-14400's UHD 730, AVX2 and Quick Sync support. The integrated graphics shares system memory; the Windows adapter-memory field is not dedicated NVIDIA VRAM. [Intel CPU specification](https://www.intel.com/content/www/us/en/products/sku/236788/intel-core-i5-processor-14400-20m-cache-up-to-4-70-ghz/specifications.html)

### Actual export benchmark

A checksum-verified FFmpeg 9.0.2 Windows build was obtained from Gyan, a provider linked by FFmpeg's official download page. The test used a **15-second synthetic 1920 × 1080 / 30 fps input**, cropped and scaled to **1080 × 1920**, with ASS captions and AAC audio. Existing background applications remained running. [FFmpeg download providers](https://ffmpeg.org/download.html), [Gyan builds](https://www.gyan.dev/ffmpeg/builds/)

| Encoder | Measured wall time | Clip duration / wall time | Sampled peak FFmpeg working set |
|---|---:|---:|---:|
| libx264, veryfast, CRF 23 | 5.457 seconds | 2.75× | 309.0 MiB |
| h264_qsv, medium, global quality 23 | 4.444 seconds | 3.38× | 215.1 MiB |

Both outputs passed codec, dimensions, frame-rate inspection and 15-second duration checks. A decoded QSV frame was visually inspected: the burned-in caption was present and readable.

**What this proves:** the current Intel driver and portable FFmpeg can complete the intended basic crop → captions → H.264 export chain. A working software fallback also exists.

**What it does not prove:** equal visual quality between encoder settings, an optimal preset, a sustained speed under heat/load, accurate audio synchronization on real speech, variable-frame-rate handling, dynamic tracking, transcription speed or complete source-to-clips throughput. CRF and QSV quality values are different scales. These are single short runs, not a controlled encoder-quality comparison; do not extrapolate them into a promised daily clip capacity.

**Hardware recommendation within your ₱0 budget:** close unnecessary applications before measuring inference; do not terminate them automatically. As a conservative initial operating target, make at least 6 GiB available before loading the 4B scorer, then measure its actual peak. This is a safety margin, not a documented minimum. Run ASR and scoring separately, process smaller windows and use manual ranking if the scorer is not worth its memory/time. A hardware purchase is outside the approved plan. If these limits cannot meet your actual volume or quality, report that limitation before changing the budget or scope.

## 3. Fact check of the supplied plan

| Claim or design | Assessment | Required correction |
|---|---|---|
| Local Python / FastAPI / React / SQLite application | Feasible architecture | Keep it single-user and local. A usable pipeline must precede the full UI. |
| faster-whisper small, int8, VAD and word times | Supported | Use CPU int8 on this PC; explicitly enable word timestamps and VAD. Verify actual target-language captions. |
| Quick Sync is the fastest rendering on the CPU | Overstated | QSV is the Intel media engine. Crop/caption filters still use CPU work. The completed export, not an encoder list, establishes support; ours passed. |
| Small LLM proposes the best moments | Unvalidated quality claim | Treat suggestions as editorial assistance. Scores are heuristic ratings, not probabilities of virality. Human review stays mandatory. |
| Sentence IDs instead of invented timestamps | Sound design | Validate existing IDs, ordering, media bounds and duration independently of the model's JSON schema. |
| Four-minute windows | Reasonable starting idea, incomplete | Cap by tokens as well as duration. Preserve transcript offsets and allow overlapping boundary proposals. |
| Always generate 5–10 candidates | Unnecessary constraint | Return up to a configurable limit, including zero if no suitable moments exist. |
| Audio energy improves ranking | Plausible but unsupported | Loudness can reward noise or shouting. Add only after an ablation shows improved usable selections or less review time. |
| MediaPipe keeps the speaker centered | Incomplete | It detects faces, not the active speaker. Start with manual crop/fit; add tracking with scene resets and manual override later. |
| WAL + jobs table means resumable processing | Incorrect by itself | Durable checkpoints, atomic claims, recovery and verified outputs implement recovery. Restart interrupted stages; do not promise partial-render resume. |
| Permission and compliance in v1 | Too late | Record rights during the first import. A checklist records human review; it cannot certify copyright legality or platform monetization. |
| Captions/crops/template variation solve reused-content risks | Unsupported | Cosmetic changes alone can still be unoriginal or ineligible. Review the ownership and actual creative contribution. |
| All clips constrained to 20–60 seconds | Useful default, not universal | Keep duration configurable. Shorts can reach 3 minutes; TikTok Creator Rewards targets original videos over a minute. |
| TTS + stock generation later | Plausible conditional extension | Audit engine/voice licenses, language support, factual script quality and stock terms separately. |
| 13 tables, embeddings, waveform library and scene/audio tools up front | Excessive for a first version | Add only to solve observed review, search or bookkeeping problems. |

The technical evidence, including engine and model links, is in [technical-fact-check.md](technical-fact-check.md). Primary references: [faster-whisper](https://github.com/SYSTRAN/faster-whisper), [FFmpeg QSV](https://ffmpeg.org/ffmpeg-codecs.html#QSV-Encoders), [MediaPipe face detector](https://developers.google.com/edge/mediapipe/solutions/vision/face_detector/python), [Ollama schema output](https://docs.ollama.com/capabilities/structured-outputs), [YouTube Shorts duration](https://support.google.com/youtube/answer/15424877?hl=en).

### SQLite dependency issue found locally

The inspected Python reports **SQLite 3.42.0**. SQLite's official documentation identifies a rare WAL-reset corruption race affecting likely versions 3.7.0 through 3.51.2, fixed in 3.51.3+ and backports 3.44.6 / 3.50.7. Before using concurrent API/worker WAL connections, verify a patched SQLite library in the clipper's isolated runtime. Python version alone does not establish this. This does not mean the current machine's databases are corrupt, and this review did not modify or audit TriLingua's database. [SQLite WAL documentation, section 11](https://sqlite.org/wal.html)

## 4. Viability for your own/client work

The selected use is a production tool, not a business built on reused-video platform payouts. **The practical case is conditional but reasonable:** the tool must deliver acceptable clips with less total hands-on time than your current editor. AI inference time can run unattended, but correction, failed suggestions and extra maintenance count against the savings. Local processing also avoids uploading client media to a third-party AI service; keep project access and backup handling appropriate for the client's agreement.

Start with existing work rather than building speculative campaign or subscription features. If you charge for editing, validate what a client will actually accept and pay; the ability to render clips does not establish demand. The other routes in the original plan are listed for context and are outside the selected pilot.

| Intended use | Verdict | Evidence needed before expansion |
|---|---|---|
| Your own/client-owned video repurposing | Reasonable pilot | Measure editorial time saved and client/owner acceptance of final clips. |
| Authorized paid clipping campaigns | Conditional | A real campaign with accepted Philippines participation/payout, clear permission, active budget, valid-view rules and approval criteria. |
| Monetized channel reposting others' videos | Weak premise if relying on cosmetic edits | Demonstrate a permissible, substantively original format and actual account/program eligibility. Do not forecast revenue from views alone. |
| Selling the software | Technically possible, commercially unproven | Identify users needing local privacy/offline control or language quality that existing products fail to provide; obtain evidence they will pay. Packaging, licensing and support become additional scope. |

YouTube distinguishes reused-content monetization from copyright permission; even authorized material can be ineligible when contribution is insufficient. Meta's current guidance explicitly identifies minor changes such as inserted captions or borders as insufficient originality for third-party posts. Neither a rights record nor a transformation checkbox guarantees acceptance. [YouTube monetization policy](https://support.google.com/youtube/answer/1311392?hl=en), [Meta original-content guidance](https://about.fb.com/news/2026/03/rewarding-original-creators-on-facebook/)

TikTok's official Creator Rewards announcement specifies original content over one minute and eligibility in an available region. Its current help pages were blocked/inaccessible during this review; **Philippines eligibility and your account's access were not confirmed**. Treat TikTok platform payouts as zero in planning until eligibility is verified directly. Campaign payments are a different arrangement and also require their own payout checks. [TikTok program announcement](https://newsroom.tiktok.com/introducing-the-new-creator-rewards-program)

Caption generation or ordinary AI assistance does not automatically require a YouTube synthetic-content disclosure. Apply current platform rules to the actual media alteration; realistic synthetic scenes or impersonation need a different review. [YouTube disclosure guidance](https://support.google.com/youtube/answer/14328491?hl=en)

There is an existing alternative: OpusClip lists a free tier with 60 monthly credits, watermark, no editing and limited export availability, plus paid plans. This establishes competition, not that its results fit your language/privacy/workload. If a permitted sample and the free tier answer the immediate need, a full custom build may waste time. Compare quality and editing effort on the same source before expanding. [Official OpusClip pricing](https://www.opus.pro/pricing)

### A small validation experiment

Before committing to the UI, use three representative owned/client-authorized sources to produce ten publishable clips in total if the sources contain enough good moments. Record manual baseline time, assisted review/correction time, accepted suggestions and final quality. Obtain your own editorial approval or a client's acceptance of the batch. Do not require a paid campaign to validate the selected use.

Track effective hourly return using **cash actually received minus fees, direct costs and attributable hardware cost**, divided by **all time spent obtaining sources, reviewing, editing, posting, administration, failed submissions and allocated development/maintenance time**. Do not count pending views as paid views or an advertised rate as guaranteed income.

Useful break-even calculation for an internal tool:

`break-even clips = build hours × value per hour / (minutes saved per clip / 60 × value per hour − added cost per clip)`

Only use it when the denominator is positive and inputs are measured. Illustrative assumption: 60 build hours and 10 minutes saved per clip, with no added running cost and the same hourly value, means about 360 clips to recover build time. This is arithmetic, not a timeline or income prediction.

## 5. Recommended first version

Keep the proposed Python / FastAPI / React / SQLite direction. The staged pilot reduces what is implemented first without changing the eventual product concept.

**First usable release:** import a permitted local video → transcribe once → correct captions → select/trim → choose fixed crop or fit/pad → export a captioned vertical MP4 → reopen the saved project. Add optional AI suggestions only after they pass the editorial gate.

| Component | Initial choice | Additions deferred until needed |
|---|---|---|
| Python environment | Isolated, pinned environment; compatible maintained Python/runtime with verified SQLite | No change to existing TriLingua Python packages. `uv` is optional tooling, not a runtime dependency. |
| Media | Working FFmpeg/ffprobe build; software filters + QSV, libx264 fallback | Hardware decoding and tracking only after profiling real sources. |
| ASR | faster-whisper multilingual small, CPU int8, VAD, word timestamps, one request | Start with 4–6 CPU threads and measure; this is a tuning baseline. Do not assume faster or larger is better. |
| Scoring | Ollama already installed; benchmark one provenance-checked Q4 4B instruct model | No second LLM server, provider router or speculative prompt framework. |
| Storage | JSON artifacts during CLI pilot, SQLite once projects need persistence | Retain planned SQLModel/Alembic if adopted; they are implementation aids, not feasibility requirements. |
| Jobs | One worker, one heavy job at a time | No Redis, Celery, parallel inference or distributed services. |
| Progress | Simple status polling initially | SSE if polling produces a real usability issue. |
| Review UI | React/Vite/TypeScript, native video controls, start/end fields and caption editor | Waveforms, frame-by-frame tools and effects timeline after demonstrated need. |
| Captions/crop | One readable ASS style; editable text/timing; manual crop and fit/pad | Automatic face tracking and extra styles later. |
| Search | Filename/title/transcript text search | FTS5 when ordinary search is inadequate; semantic embeddings after that. |
| Testing | Small relevant pytest cases and a permitted tiny video fixture | No large synthetic test framework or tests that merely repeat implementation. |

Model suggestion: Qwen3-4B-Instruct-2507 is a documented non-thinking candidate, not a claim that it is the best current model. The official base Qwen3-4B Q4_K_M file is about 2.5 GB; that is a weight-download reference for a different variant, not measured RAM or a guaranteed size for the chosen Instruct quantization. Pin exact model/quantization, provenance and runtime. Benchmark with a bounded 2K–4K context and short output. Release the ASR process before loading the scorer, and explicitly unload the scorer after use. [Qwen Instruct card](https://huggingface.co/Qwen/Qwen3-4B-Instruct-2507), [official base GGUF files](https://huggingface.co/Qwen/Qwen3-4B-GGUF/tree/main)

## 6. Phased execution and acceptance gates

Do one phase at a time. Preserve benchmark evidence, runnable checks and failures. A coding agent should report each gate's results; installing packages or receiving HTTP 200 is not completion evidence.

### Phase 0 — confirm the use case and operating limits

1. Use the confirmed own/client-video route and ₱0 software/cloud/hardware budget; state the usual languages, video lengths and weekly volume.
2. Select three permitted sources representative of the actual work: clean speech, the hardest expected language/noise case, and multi-person or screen-share content if relevant.
3. Time manual selection and editing with an existing editor on one source. Record the caption and framing problems.
4. Set desired processing wait time, minimum editorial quality and cash budget before choosing heavier models or hardware.

**Gate:** one written pilot brief, three owned/client-authorized source files and a manual time baseline. Skip campaign tracking in this pilot; do not fabricate a language-quality promise without samples.

### Phase 1 — benchmark the AI workload in isolation

1. Create a separate project environment. Verify FFmpeg, Python packages, model license/provenance and SQLite library version.
2. Benchmark a ten-minute sample with multilingual small / CPU int8 / word timestamps / VAD; fully consume the transcription iterator. Record cold load, transcription time, peak process/system memory and caption correction time.
3. Unload ASR. Run bounded structured scoring over several token-capped transcript windows with stable sentence IDs. Measure input/output tokens, wall time, memory and validity; do not benchmark only one trivial prompt.
4. Unload the scorer. Export at 720 × 1280 and 1080 × 1920 on the actual source, with corrected captions. Compare QSV and software fallback, including visible quality and synchronization.
5. Repeat on representative languages/content. Observe responsiveness with the ordinary non-game working set and after sustained processing.

**Suggested pilot gates, to adjust to your actual volume:** a ten-minute clean sample transcribed in no more than ten minutes; a bounded scoring window in no more than two minutes; a 60-second captioned 1080p vertical export in no more than 60 seconds. These are acceptance targets, not measured predictions. Keep at least 2 GiB system memory available at peak and avoid sustained paging/freezes. Manually transcribe a reference excerpt, record errors and correction time, and reject unacceptable names/numbers/meaning errors.

**If the gate fails:** try smaller context/shorter output, fewer concurrent resident models and a smaller ASR model only if its correction burden is acceptable. Retain manual ranking if the scorer is slow or weak. If those compromises conflict with the desired quality or volume, report the unmet requirement; paid cloud or hardware is outside your approved ₱0 direction.

### Phase 2 — deliver the working CLI workflow

1. Input validation with ffprobe: readable path, media streams, codec/duration/rotation and reasonable bounds. Handle unsupported or corrupt files clearly.
2. Record source permission and a fingerprint; cache the transcript with model/settings identity.
3. Accept manual start/end times, corrected caption text/timing, crop position or fit/pad and one export preset.
4. Generate ASS with clip-relative timestamps; invoke FFmpeg using argument arrays. Verify the temporary output before making it the final export.
5. Preserve source files and reuse the transcript when trimming or changing caption style.

**Gate:** the three source types produce usable clips. Check real speech sync, caption alignment, missing/corrupt media, invalid timing, rotation, variable-frame-rate source if expected, Unicode/spaces in paths and failure cleanup. Reject invalid inputs without producing a misleading completed file. Save one repeatable export smoke check and focused checks for nontrivial timestamp conversion.

### Phase 3 — add assisted selection only when it saves time

1. Split transcript into stable sentence IDs retaining original word times. Build overlapping windows within the model's actual token budget.
2. Return sentence boundaries, editorial ratings and a short grounded reason. Treat transcript text as input content, not instructions to the scorer.
3. Validate JSON, ID existence, chronological order, candidate bounds and configured duration. Deduplicate overlaps deterministically. Bounded retry once; then leave manual selection available.
4. Show up to ten suggestions, allowing fewer/zero. Provide context before/after so the reviewer can detect misleading cuts.
5. Evaluate across the pilot sources and compare to manual review.

**Gate:** for suitable sources, at least three of the top five proposed moments are worth retaining with minor boundary edits, and total selection/correction time improves meaningfully. A suggested decision threshold is at least 25% less hands-on time across the pilot; this is a chosen product gate, not a scientific validation. Reject an LLM ranking module that fails the gate even when its JSON is valid. Do not add arbitrary weighted audio scores to hide poor results.

### Phase 4 — persistence, API and recoverable worker

1. Start with `sources`, `jobs`, `candidates` and `clips`. Store versioned transcripts/words in artifacts; keep their paths and settings in source records. Add tables only when their workflow exists.
2. Use a patched SQLite runtime before concurrent WAL. Short transactions, foreign keys, busy timeout and atomic job claim; one worker is enough.
3. Job states: queued → running → succeeded / failed / cancelled. Persist stage, attempts, heartbeat/lease, worker token, output references and error summary.
4. Cache completed stage artifacts. On interruption, recover expired claims and retry only the interrupted stage. Write temporary media, verify, rename on the same filesystem, then reconcile completion after a crash. Make duplicate stage execution harmless.
5. Add cancellation between stages and explicit FFmpeg termination; poll durable status for the UI. Confirm backup creation and restoration before schema changes.

**Gate:** deliberately interrupt transcription, scoring and export; restart without duplicate final clips or losing completed work. Check duplicate enqueue, corrupt artifact, deleted source, cancellation, low disk and database restore. Back up using SQLite's backup API or a stopped/checkpointed database; copying only a live WAL database file is inadequate. [SQLite backup guidance](https://sqlite.org/backup.html)

### Phase 5 — browser review and project library

1. Show imported sources, jobs, transcript and optional suggestions.
2. Support seek/play, editable start/end, crop/fit, caption text/timing corrections, approve/reject and render.
3. Offer a browser-compatible preview/proxy when the original codec/container cannot be played. Keep the original timebase and export from the original source.
4. Save projects, list finished clips, search ordinary transcript text, and allow re-render without ASR.
5. Add a Windows launcher that starts exactly one API/worker pair and detects duplicate startup. Keep heavy work off request handlers; do not rely on the web server's reload process as a worker.

**Gate:** import → review → correction → export → close/reopen works on all pilot sources. Refresh/disconnection does not lose a running job. Progress, failure and cancellation are clear; keyboard operation and caption contrast are usable. PC sleep/shutdown pauses local processing; recover on restart. Overnight runs require the PC awake and adequate storage.

### Phase 6 — real-use validation and optional v1 features

1. Produce the ten-clip pilot batch; log editorial time, caption corrections, rejected suggestions and delivery acceptance.
2. Validate your own editorial approval or client acceptance. Views alone do not establish editing quality, profit or scorer correctness.
3. Add tags/FTS search, platform presets or extra captions only when pilot use demonstrates need. Keep one generic export preset until actual destination requirements are checked. Campaign records remain deferred unless you later choose that workflow.
4. Add automatic reframing only after manual crop is an observed bottleneck. Analyze a low-resolution proxy; track a selected face, smooth within shots, reset at cuts, and provide no-face/multi-face fallbacks.
5. Add a simple launcher/settings/export backup workflow before considering distribution to other users.

**Gate:** useful clips, measurable time savings, stable processing and a confirmed reason to continue. If client income is an objective, require acceptable effective hourly return from actual agreed work, rather than a theoretical high view count.

### Phase 7 — generation module, conditional

Reuse the existing caption/editor/render/library flow: approved script → licensed supported-language TTS → licensed stock/local footage → timed sequence → human review → export. Store script provenance, asset URLs/creator/license and voice/model version. Review factual statements and final visual relevance; stock selection cannot be inferred from keywords alone.

Kokoro is a candidate for its documented languages, not a verified Tagalog/Cebuano narrator. Current maintained Piper licensing differs from older MIT assumptions; both engine and each voice require review. Pexels API attribution obligations differ from its general stock license. Redistribution of the app creates additional dependency/FFmpeg licensing work. [Kokoro model](https://huggingface.co/hexgrad/Kokoro-82M), [current Piper](https://github.com/OHF-Voice/piper1-gpl), [Pexels license](https://www.pexels.com/license/), [Pexels API](https://www.pexels.com/api/documentation/)

**Gate:** approved narration quality/language, documented rights, acceptable CPU time and genuinely useful original content. Caption/crop variation is not a substitute for varied substance. Compare analytics descriptively before attempting a learning model: views are confounded by topic, account, distribution and posting conditions.

## 7. Operational limits that must be implemented

- Bind API/model services to loopback; do not expose a private file editor to the network. Narrow allowed browser origins and reject unexpected origins for mutation routes. Validate selected media/project paths and avoid unrestricted filesystem-reading endpoints or shell-built commands.
- Keep heavy stages sequential. Cache transcripts and candidates by source fingerprint and relevant settings; changing captions should rerender, not retranscribe. Keep the app responsive while a worker runs.
- Reserve disk space before rendering; stop clearly on insufficient space. Delete only app-owned temporary outputs; never delete an imported original as automatic cleanup.
- Use an explicit source ownership/permission record, rights evidence reference, allowed destination/use and restrictions. Store unknown permissions as unknown; do not infer them from a public URL.
- Treat caption correction, fixed crop/fit fallback and human approval as core requirements. An automatic path must not remove the manual path.

Storage planning example, not measured source bitrate: one hour at 10 Mb/s is about 4.5 GB in decimal units before audio/proxies/backups. At 20 Mb/s it is about 9 GB. Start with an explicit 30–50 GB pilot working budget and preserve roughly 50 GB system-disk reserve; adjust from real source sizes. Do not promise an unlimited library on this SSD.

## 8. Effort and cost boundaries

**Rough planning estimate only:** isolated benchmarks and pilot workflow, 12–30 engineering hours; recoverable API, review UI and saved library, another 40–90 hours; stabilization against representative failures, another 12–30 hours. These are broad implementation estimates for an experienced developer using coding assistance, not commitments. They exclude obtaining permissions, sourcing clients, advanced tracking, campaigns, distribution and generation. Do not turn them into a deadline until phases 0–1 expose the actual quality and environment problems.

No paid API, subscription or hardware purchase is permitted by the selected plan. All required processing must run locally with free tools and appropriately licensed assets. Free software still costs development time, electricity, internet/model downloads, storage and maintenance. Keep generation effort uncommitted until the clipping tool earns its place. Avoid a hosted SaaS build, user accounts, billing, embeddings, waveform timeline and automatic posting during the local pilot.

## 9. Next execution brief for a coding agent

Implement **phases 0–1 only** first in a separate project for own/client videos and a strict ₱0 software/cloud/hardware budget, after representative sources and operating targets are provided. Use the existing portable FFmpeg as a known working reference. Do not change TriLingua, silently close user applications, download large models without checking free memory/disk, or enable cloud inference. Produce a benchmark sheet with configuration, source properties, timings, memory, caption correction burden and bounded scoring validity. Report whether the phase gate passed; expose an unmet requirement before moving to the next phase.

## 10. Evidence and remaining decisions

- [Technical primary-source audit](technical-fact-check.md).
- [Hardware snapshots](hardware-check.json).
- [Measured render results](benchmark-results.json).
- [Decoded caption proof](caption-check.png).
- [Runnable render check](benchmark_render.py); uses the included portable FFmpeg.
- Original plan: `C:\Users\walbe\.codex\attachments\d12da77d-49f7-4326-8154-2e7b6adda025\Pasted text.txt`.

**Remaining for the selected pilot:** usual languages, representative sources, desired volume and real AI throughput/quality. Own/client use and ₱0 software/cloud/hardware budget are confirmed. Platform payout eligibility is outside this pilot and has not been established. The remaining items are gates before committing to a full product, not reasons to discard the local clipper pilot.
