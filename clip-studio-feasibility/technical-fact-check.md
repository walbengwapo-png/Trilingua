# Clip studio: technical fact check

Checked against current primary documentation on 5 October 2026. This checks the supplied plan, not an implemented application. No models were installed or benchmarked for this research. Local hardware and render measurements are reported separately.

## Conclusion

The architecture is feasible for a single-user local editor, subject to measured throughput and quality. The plan overstates automatic highlight judgment, face-based reframing, and guaranteed Quick Sync speed. Start with manual trimming, editable captions, one render preset, one worker, and cached transcripts. Add ranking only if it saves review time on actual content. This is an engineering recommendation, not a measured product result.

## Verified claims and necessary corrections

| Original proposal | Finding | Correction |
|---|---|---|
| faster-whisper small, CPU int8, VAD, word times | Supported. GPU implementation requires NVIDIA CUDA/cuDNN, not Intel Quick Sync. | Use CPU int8 without a supported NVIDIA GPU; explicitly enable word timestamps and VAD; review caption text/times. |
| Quick Sync is the fastest rendering on your CPU | Unsupported comparative claim. QSV is an Intel hardware video encoder; the full crop/caption pipeline may be CPU-bound. | Probe installed build, run actual captioned render, compare with libx264. Keep software fallback. |
| 3–4B Qwen and JSON schema | Supported in local runtimes; structure does not prove good judgment or valid sentence references. | Pin one model and runtime; validate IDs, ordering, bounds, duration and truncated responses in application code. |
| MediaPipe keeps the speaker centered | Detection supplies face boxes; it does not determine the person speaking or edit the crop. | Manual crop first; later add confidence threshold, smoothing, shot reset and manual override. |
| SQLite WAL and jobs make stages resumable | WAL supports database concurrency, not job semantics. | Add transactional claim, heartbeat/lease, retry policy, durable checkpoints and idempotent stage outputs. |
| SSE gives job progress | Suitable for notifications, but disconnects do not stop or recover a job. | Database is the source of truth; reconnect fetches current state. Polling is adequate initially. |
| Piper or Kokoro, check each voice license | Correct but incomplete: current Piper engine licensing also matters. | Audit engine, weights, selected voice and phonemizer before redistribution. |
| Pexels is free stock | Generally correct with restrictions; API has attribution and rate limits. | Preserve asset ID, URL, creator, retrieval date and license; show required API attribution. |

### Transcription and caption timing

The faster-whisper project documents CPU `int8`, `word_timestamps=True`, Silero VAD, Python 3.9+, and NVIDIA CUDA 12/cuDNN 9 for its current GPU dependencies. Its published small-model CPU reference uses an **i7-12700K with eight threads**, taking **1 minute 42 seconds / 1,477 MB** for the reference 13-minute recording; batching improves speed while raising RAM. Those figures are not a prediction for another CPU, another language, or the planned word-timing pipeline. Consume the returned segment generator when timing a benchmark; creating it alone does not execute transcription. System FFmpeg is still needed for the application's export, even though the transcription library uses bundled PyAV decoding. [Project documentation](https://github.com/SYSTRAN/faster-whisper)

Word boundaries are model estimates, not verified alignments. Recommendation: allow transcript corrections, caption timing changes, and re-render without re-transcribing; manually check representative speech, noise, overlap and silence. Use multilingual `small`, not `small.en`, for mixed-language material. Whisper's official language list includes Tagalog but does not list Cebuano; do not promise Bisaya/Cebuano accuracy without samples. [Official Whisper tokenizer](https://github.com/openai/whisper/blob/main/whisper/tokenizer.py)

### FFmpeg and Intel Quick Sync

FFmpeg exposes `h264_qsv`, but encoder presence only shows build capability. Hardware, driver and requested options must work at runtime. `ffmpeg -encoders`, `-filters`, and `-h encoder=h264_qsv` are inventory checks; a completed output is the acceptance test. FFmpeg notes QSV settings can change according to the system; verbose logs reveal actual settings. [FFmpeg CLI documentation](https://www.ffmpeg.org/ffmpeg.html), [QSV encoder documentation](https://ffmpeg.org/ffmpeg-codecs.html#QSV-Encoders)

ASS/subtitles use libass and require the relevant FFmpeg build support. The ordinary crop/subtitles chain operates in system memory. Hardware-frame pipelines may require `hwdownload`, compatible pixel format conversion and upload; adding QSV encoding does not automatically accelerate those filters. An initial software decode/crop/subtitles followed by QSV encode is simpler than forcing every stage onto hardware. Benchmark this complete chain at 720×1280 and 1080×1920; compare speed, CPU load, file size and visible quality. FFmpeg's special QSV accelerated transcoding mode is documented separately from general filtering. [FFmpeg filter documentation](https://www.ffmpeg.org/ffmpeg-filters.html#subtitles), [hardware-frame transfers](https://www.ffmpeg.org/ffmpeg-filters.html#hwdownload), [QSV CLI behavior](https://www.ffmpeg.org/ffmpeg.html)

### Model choice and moment ranking

Qwen provides an official Qwen3-4B GGUF with a Q4_K_M file of about **2.5 GB**, Apache-2.0 licensing, multilingual support and switchable thinking. Disk size is not peak RAM; context/KV cache, runtime buffers and other processes add memory. Keep context near 4K initially, one scoring request at a time, and bounded output. [Official model card](https://huggingface.co/Qwen/Qwen3-4B-GGUF), [official files](https://huggingface.co/Qwen/Qwen3-4B-GGUF/tree/main)

For short ranking outputs, **Qwen3-4B-Instruct-2507** is a reasonable candidate because its official card explicitly describes a non-thinking-only model. It is a candidate to benchmark, not a claim that it is the newest or best small model. Obtain a compatible quantization with clear provenance; do not confuse it with the base Qwen3-4B or Thinking-2507 variant. [Official Instruct model card](https://huggingface.co/Qwen/Qwen3-4B-Instruct-2507)

Local Ollama accepts JSON schema in `format`; llama.cpp converts a supported subset of JSON Schema into grammar constraints. The schema still needs to be described in the prompt. Independently validate every response, including available sentence IDs, `start <= end`, media bounds and configured duration. Clamp or reject invalid scores; one bounded retry, then manual review. A schema-shaped result can still be factually wrong or select an incoherent clip. [Ollama structured outputs](https://docs.ollama.com/capabilities/structured-outputs), [llama.cpp grammars](https://github.com/ggml-org/llama.cpp/blob/master/grammars/README.md)

Engineering recommendations: use sentence IDs mapped to original timestamps; preserve offsets through VAD and clip-relative captions. Budget transcript windows by tokens as well as duration. Do not force 5–10 candidates when fewer valid moments exist. Treat ranking as a heuristic rather than a probability of going viral. Compare suggested selections with a human-selected baseline and record minutes of review saved. Audio energy does not prove importance; add it only if it improves measured selection quality.

### Face detection and reframing

MediaPipe returns face boxes, confidence and keypoints; video mode can use tracking to reduce repeated detection. Nothing in this interface identifies the active speaker or guarantees a good composition. Multi-person panels, screen shares, occlusion, profile shots, graphics and no-face scenes require fallback handling. Manual fixed crop or fit/pad should remain available. If automation is later added, analyze a small proxy, reset tracking at cuts, and smooth only within a shot. [Google's Face Detector Python guide](https://developers.google.com/edge/mediapipe/solutions/vision/face_detector/python)

### SQLite, worker recovery, and progress

SQLite WAL lets readers and a writer run concurrently, but only one writer at a time; WAL is intended for connections on the same host. **Current safety correction:** the official docs disclose a rare WAL-reset corruption race fixed in **3.51.3+**, with backports **3.44.6** and **3.50.7**. Verify the SQLite library actually used by Python, not just Python's version. For the proposed API+worker WAL setup, use a patched version. This is a dependency verification item, not grounds for replacing SQLite. [Official WAL documentation](https://sqlite.org/wal.html)

Claim a job in one short transaction (`BEGIN IMMEDIATE`, select/update, commit, or equivalent atomic conditional update); do not hold the database write transaction during inference/rendering. Suggested application fields: status, stage, attempts, worker token, lease expiry, heartbeat and last error. On restart recover expired claims; save each successful stage; write to temporary output, verify media, then rename. Retry an interrupted stage rather than claiming byte-level render resume. These are application design requirements inferred from transaction semantics. [SQLite transactions](https://sqlite.org/lang_transaction.html)

Use SQLite's online backup API or a fully stopped/checkpointed database for backup; copying just the main database while live in WAL mode can omit committed data. Restore-test a backup before trusting the migration workflow. [SQLite backup API](https://sqlite.org/backup.html), [WAL file lifetime](https://sqlite.org/wal.html)

SSE supports one-way server notifications and reconnects; under HTTP/1 browsers commonly limit a domain to six connections. Use one stream per app rather than one per job; reload state from the database after reconnect. Polling every couple of seconds is simpler for the first local version. [MDN SSE guide](https://developer.mozilla.org/en-US/docs/Web/API/Server-sent_events/Using_server-sent_events)

### Later generation: TTS and stock footage

The old rhasspy Piper repo is archived and directs development to OHF-Voice. The current maintained engine is **GPL-3.0**; old MIT-engine assumptions do not apply automatically to current packages. Individual voice models need separate review. Local personal use and redistribution are different licensing situations. [Archived Piper repository](https://github.com/rhasspy/piper), [maintained Piper repository](https://github.com/OHF-Voice/piper1-gpl)

Kokoro-82M publishes Apache-2.0 weights and a small architecture, supporting its use as a local TTS candidate. CPU speed and Windows phonemizer installation still need measurement. Its documented voices cover English, Japanese, Mandarin, Spanish, French, Hindi, Italian and Brazilian Portuguese; Tagalog/Cebuano are not listed. Some voice entries include dataset attribution references, so inspect the chosen voice rather than assuming a blanket engine license settles everything. [Official Kokoro model card](https://huggingface.co/hexgrad/Kokoro-82M), [voice list](https://huggingface.co/hexgrad/Kokoro-82M/blob/main/VOICES.md)

Pexels permits personal/commercial use and modification, but prohibits unaltered resale, misleading endorsement, certain offensive depictions and stock-library redistribution. Content-license attribution is generally optional; **API use separately requires a prominent Pexels link and creator credit when possible**. Default API limits are **200 requests/hour and 20,000/month**. Current video endpoints use `/v1/videos/`; retain metadata and cache responsibly. [Pexels license](https://www.pexels.com/license/), [API documentation](https://www.pexels.com/api/documentation/)

## Minimal phase gates to carry into the main plan

1. Establish throughput: representative 10-minute transcript with actual word times and VAD; one constrained scoring request; one captioned vertical export. Record wall time, peak memory, working responsiveness and quality. Installed packages or model loading alone do not satisfy this gate.
2. Deliver a manual workflow: import with permission record, transcript edit, select/trim, fixed crop/fit, readable captions, valid MP4. Keep one caption style and no semantic search.
3. Evaluate ranking on at least three different permitted sources and real intended languages. Require valid ranges plus human-accepted suggestions and less review time than manual selection.
4. Add database/one worker only after the pipeline works; test kill/restart, missing source, bad media, full disk, duplicate enqueue, cancellation and backup restore. Completed stages are reused; interrupted stages are retried safely.
5. Add UI/library, then campaign bookkeeping and optional face tracking. TTS/stock generation follows only after clip workflow produces useful work reliably.

Performance figures for this PC remain unverified until model and end-to-end pipeline benchmarks run. Technical feasibility does not establish demand, campaign eligibility, copyright permission or monetization.
