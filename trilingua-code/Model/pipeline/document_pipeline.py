# -*- coding: utf-8 -*-
"""
Document pipeline.

Orchestrates the complete document translation flow:
1. Read file (via extractor)
2. AI Document Analysis (Phase 1) — when mode permits
3. Prepass (Phase 7) — when mode permits (Task 5)
4. Document Memory initialization (Phase 2) — when mode permits
5. Semantic Chunking (Phase 3) — when mode permits
6. Translation via TranslationPipeline (async, batched, cached)
7. AI Quality Review (Phase 5) — when mode permits
8. AI Layout Planning (Phase 8) — when mode permits (PDF only)
9. Reconstruction (existing, untouched)
10. Layout validation (existing, untouched)
11. Logging via DocumentContext

The provider never manipulates documents directly.
Deterministic engineering is preserved at all times.

OPTIMIZATIONS:
- Task 2: Persistent SQLite cache integration
- Task 5: Two-pass context injection (prepass)
"""

import json
import os
import time as _time

from config.processing_modes import MODES, VALID_MODES, get_mode
from dto.requests import DocumentTranslationRequest, LANGUAGES
from dto.responses import DocumentTranslationResponse
from document.extractor import analyze_document
from document.reconstructor import (
    _translate_docx_inplace_with_translator,
    translate_pptx_inplace,
    translate_xlsx_inplace,
    choose_output_path,
    reconstruct_document,
    write_csv,
)
from document.document_analyzer import DocumentAnalyzer
from document.semantic_chunker import SemanticChunker
from document.layout_planner import LayoutPlanner
from memory.glossary import GlossaryStore
from memory.document_memory import DocumentMemory
from cache.sqlite_cache import SQLiteTranslationCache
from validators.translation_validator import LayoutValidator, BLEUReporter
from validators.ai_quality_reviewer import AIQualityReviewer
from pipeline.translation_pipeline import TranslationPipeline
from pipeline.document_context import DocumentContext
from pipeline.phase_profiler import phase_profile, llm_call_profile
from prompts.prepass import (
    build_prepass_system_prompt,
    build_prepass_user_prompt,
    build_prepass_injection,
)

from concurrent.futures import ThreadPoolExecutor

# OPTIMIZATION: Env var for prepass (Task 5)
_TRANSLATION_PREPASS_ENABLED = os.environ.get(
    "TRANSLATION_PREPASS_ENABLED", "true"
).lower() == "true"
_TRANSLATION_CACHE_ENABLED = os.environ.get(
    "TRANSLATION_CACHE_ENABLED", "true"
).lower() == "true"
_TRANSLATION_CACHE_TTL_DAYS = int(os.environ.get(
    "TRANSLATION_CACHE_TTL_DAYS", "30"
))
_TRANSLATION_CONCURRENCY = int(os.environ.get(
    "TRANSLATION_CONCURRENCY", "16"
))

# OPTIMIZATION: Analyzer mode for Phase C Tier 2a
# "sequential": analyzer then prepass (original behavior)
# "merged":     single AI call for both analyzer + prepass
# "concurrent": run analyzer and prepass in parallel
_TRANSLATION_ANALYZER_MODE = os.environ.get(
    "TRANSLATION_ANALYZER_MODE", "merged"
).lower()
_VALID_ANALYZER_MODES = {"sequential", "merged", "concurrent"}


class DocumentPipeline:
    """Orchestrates the complete document translation process."""

    def __init__(self, translation_pipeline: TranslationPipeline,
                 ai_analysis_provider=None, mode: str = "balanced"):
        """Initialize the document pipeline.

        Args:
            translation_pipeline: The TranslationPipeline for text translation.
            ai_analysis_provider: Optional AIAnalysisProvider for AI-assisted features.
            mode: Default processing mode ('fast', 'balanced', 'thorough', 'auto').
        """
        self.translation_pipeline = translation_pipeline
        self.layout_validator = LayoutValidator()
        self.bleu_reporter = BLEUReporter()

        # AI-assisted components (Phase 1-8)
        self._ai_provider = ai_analysis_provider
        self._document_analyzer = DocumentAnalyzer(ai_analysis_provider) if ai_analysis_provider else None
        self._semantic_chunker = SemanticChunker() if ai_analysis_provider else None
        self._quality_reviewer = AIQualityReviewer(ai_analysis_provider) if ai_analysis_provider else None
        self._layout_planner = LayoutPlanner(ai_analysis_provider) if ai_analysis_provider else None

        # OPTIMIZATION: Shared SQLite cache (Task 2)
        self._shared_cache: SQLiteTranslationCache | None = None

        self._default_mode = mode

    def _get_cache(self) -> SQLiteTranslationCache | None:
        """Get or create the shared SQLite cache."""
        if self._shared_cache is None and _TRANSLATION_CACHE_ENABLED:
            self._shared_cache = SQLiteTranslationCache(
                ttl_days=_TRANSLATION_CACHE_TTL_DAYS,
                enabled=_TRANSLATION_CACHE_ENABLED,
            )
        return self._shared_cache

    def translate(self, request: DocumentTranslationRequest) -> DocumentTranslationResponse:
        """Translate a document through the full pipeline.

        Args:
            request: The document translation request.

        Returns:
            A DocumentTranslationResponse.
        """
        # ── Initialize DocumentContext ────────────────────────────────────
        ctx = DocumentContext()
        ctx.start_timer()
        ctx.source_file = request.file_path
        ctx.source_lang = request.source_lang
        ctx.target_lang = request.target_lang
        ctx.concurrency_level = _TRANSLATION_CONCURRENCY

        # ── Determine processing mode ─────────────────────────────────────
        ctx.mode = self._determine_mode(request)

        ext = os.path.splitext(request.file_path)[1].lower()
        ctx.source_format = ext
        print(f"\n{'='*60}")
        print(f"  Document Translation — Mode: {ctx.mode.name}")
        print(f"{'='*60}")
        print(f"  File: {request.file_path}")
        print(f"  Language: {request.source_lang} → {request.target_lang}")
        print(f"  Format: {ext}")

        # Build glossary
        glossary_store = GlossaryStore(request.glossary_pairs) if request.glossary_pairs else None

        # Build output path
        output_file = choose_output_path(request.file_path)

        # OPTIMIZATION: Get shared cache (Task 2)
        translation_cache = self._get_cache()
        if translation_cache:
            ctx.translation_cache = translation_cache

        # ── In-place translation for DOCX, PPTX, XLSX ──
        if ext in (".docx", ".pptx", ".xlsx"):
            return self._translate_inplace(request, ext, output_file, glossary_store, ctx)

        # ── PDF: direct PyMuPDF extraction ──
        if ext == ".pdf":
            print("[INPUT] Using PyMuPDF for PDF...")

        # ── Extract → Analyze → Translate → Reconstruct pipeline ──
        print("[INPUT] Reading document...")
        with phase_profile("extraction", ctx):
            data, detected_ext = analyze_document(request.file_path, pdf_column_mode=request.pdf_column_mode)
        ctx.extraction_time_ms = ctx.phase_times.get("extraction", 0)
        ctx.total_blocks = len(data) if isinstance(data, list) else 0

        # Handle CSV separately
        if detected_ext == ".csv":
            return self._translate_csv(data, request, output_file, glossary_store, ctx)

        blocks = data
        print(f"  Found {len(blocks)} text block(s) after filtering.")

        if not blocks and ext == ".pdf":
            # Attempt OCR fallback for image-based/scanned PDFs
            print("[OCR] No text blocks found via PyMuPDF extraction.")
            print("[OCR] Attempting OCR fallback...")
            try:
                from document.ocr_extractor import ocr_extract_pdf
                ocr_blocks = ocr_extract_pdf(request.file_path)
                if ocr_blocks:
                    blocks = ocr_blocks
                    print(f"  [OCR] Successfully extracted {len(blocks)} block(s) via OCR")
                else:
                    raise ValueError(
                        "No translatable text extracted. OCR yielded no text. "
                        "For bilingual PDFs, try pdf_column_mode='left' or 'right'."
                    )
            except ImportError:
                raise ValueError(
                    "No translatable text extracted from PDF. "
                    "OCR fallback is not available (pytesseract not installed). "
                    "Install: pip install pytesseract, and install Tesseract OCR."
                )
            except Exception as ocr_err:
                raise ValueError(
                    f"No translatable text extracted. OCR fallback also failed: {ocr_err}"
                )
        elif not blocks:
            raise ValueError(
                "No translatable text extracted. "
                "If this is a scanned PDF, OCR is required. "
                "For bilingual PDFs, try pdf_column_mode='left' or 'right'."
            )

        # Phase 1 + 7: AI Document Analysis & Prepass
        # Three modes controlled by TRANSLATION_ANALYZER_MODE env var:
        #   sequential: analyzer then prepass (original)
        #   merged:     single AI call for both
        #   concurrent: run analyzer and prepass in parallel
        analyzer_mode = _TRANSLATION_ANALYZER_MODE
        if analyzer_mode not in _VALID_ANALYZER_MODES:
            print(f"  [Analyzer] Unknown mode '{analyzer_mode}', falling back to sequential")
            analyzer_mode = "sequential"
        
        if analyzer_mode == "merged":
            # Option A: Single merged call for analyzer + prepass
            if ctx.mode.document_analyzer and self._document_analyzer:
                print("[ANALYZER] Running merged document analysis + prepass...")
                with phase_profile("document_analyzer", ctx):
                    with llm_call_profile(ctx):
                        profile, prepass_data = self._document_analyzer.analyze_with_prepass(
                            blocks,
                            source_lang=request.source_lang,
                            target_lang=request.target_lang,
                        )
                ctx.analysis_time_ms = ctx.phase_times.get("document_analyzer", 0)
                ctx.document_profile = profile
        
                if _TRANSLATION_PREPASS_ENABLED and prepass_data:
                    ctx.prepass_summary = prepass_data.get("summary", "")
                    ctx.prepass_domain = prepass_data.get("domain", "")
                    ctx.prepass_terms = prepass_data.get("terms", [])
            else:
                ctx.document_profile = None
        
        elif analyzer_mode == "concurrent":
            # Option B: Run analyzer and prepass concurrently
            if ctx.mode.document_analyzer and self._document_analyzer:
                print("[ANALYZER] Running AI document analysis (concurrent)...")
                pool = ThreadPoolExecutor(max_workers=2)
        
                def _run_analyzer():
                    with phase_profile("document_analyzer", ctx):
                        return self._document_analyzer.analyze(blocks)
        
                analyzer_future = pool.submit(_run_analyzer)
        
                prepass_future = None
                if (_TRANSLATION_PREPASS_ENABLED and ctx.mode.prepass and
                        self._ai_provider):
                    prepass_future = pool.submit(
                        self._execute_prepass_concurrent, blocks, request, ctx
                    )
        
                # Wait for analyzer
                try:
                    profile = analyzer_future.result()
                    ctx.analysis_time_ms = ctx.phase_times.get("document_analyzer", 0)
                    ctx.document_profile = profile
                except Exception as e:
                    print(f"  [Analyzer] Concurrent analysis failed: {e}")
                    ctx.document_profile = None
        
                # Wait for prepass if submitted
                if prepass_future:
                    try:
                        prepass_future.result()
                    except Exception as e:
                        print(f"  [Prepass] Concurrent prepass failed: {e}")
        
                pool.shutdown(wait=True)
            else:
                ctx.document_profile = None
        
        else:
            # Sequential: original behavior (analyzer then prepass)
            if ctx.mode.document_analyzer and self._document_analyzer:
                print("[ANALYZE] Running AI document analysis...")
                with phase_profile("document_analyzer", ctx):
                    profile = self._document_analyzer.analyze(blocks)
                ctx.analysis_time_ms = ctx.phase_times.get("document_analyzer", 0)
                ctx.document_profile = profile
            else:
                ctx.document_profile = None
        
            # OPTIMIZATION: Phase 7 - Prepass (Task 5)
            if (_TRANSLATION_PREPASS_ENABLED and ctx.mode.prepass and
                    self._ai_provider and blocks):
                print("[PREPASS] Running two-pass context injection...")
                with phase_profile("prepass", ctx):
                    try:
                        prepass_text = ""
                        token_count = 0
                        for block in blocks:
                            text = block.get("text", "")
                            words = text.split()
                            if token_count + len(words) > 500:
                                remaining = 500 - token_count
                                if remaining > 0:
                                    prepass_text += " " + " ".join(words[:remaining])
                                break
                            prepass_text += " " + text
                            token_count += len(words)
        
                        prepass_text = prepass_text.strip()
        
                        if prepass_text:
                            with llm_call_profile(ctx):
                                sys_prompt = build_prepass_system_prompt()
                                user_prompt = build_prepass_user_prompt(
                                    prepass_text, request.source_lang, request.target_lang
                                )
                                prepass_result = self._ai_provider.analyze(sys_prompt, user_prompt)
        
                            summary = prepass_result.get("summary", "")
                            domain = prepass_result.get("domain", "")
                            terms_raw = prepass_result.get("terms", [])
                            terms = []
                            if isinstance(terms_raw, list):
                                for t in terms_raw:
                                    if isinstance(t, dict):
                                        src = t.get("source", "")
                                        tgt = t.get("target", "")
                                        if src and tgt:
                                            terms.append((src, tgt))
        
                            ctx.prepass_summary = summary
                            ctx.prepass_domain = domain
                            ctx.prepass_terms = terms
        
                            print(f"  [Prepass] Summary: {summary[:80]}...")
                            print(f"  [Prepass] Domain: {domain}")
                            print(f"  [Prepass] Terms: {len(terms)}")
        
                    except Exception as e:
                        print(f"  [Prepass] Warning: Prepass failed: {e}")
                        print(f"  [Prepass] Continuing without prepass context")
        
                ctx.analysis_time_ms += ctx.phase_times.get("prepass", 0)
        
        # ── Phase 2: Document Memory ──────────────────────────────────────
        if ctx.mode.document_memory:
            memory = DocumentMemory()
            if ctx.document_profile:
                memory.store_profile(ctx.document_profile)
            else:
                memory.initialize_from_blocks(blocks)
            ctx.document_memory = memory
        else:
            ctx.document_memory = None

        # ── Phase 6: Translation Cache ────────────────────────────────────
        # (Already handled via shared SQLite cache above)

        # ── Phase 3: Semantic Chunking & Translation ─────────────────────
        print("[TRANSLATE] Translating...")

        # OPTIMIZATION: Build prepass injection for context (Task 5)
        prepass_preamble = ""
        if ctx.prepass_summary or ctx.prepass_domain or ctx.prepass_terms:
            prepass_preamble = build_prepass_injection(
                ctx.prepass_summary, ctx.prepass_domain, ctx.prepass_terms
            )

        # OPTIMIZATION: Pass ctx to batch_translate_blocks for stats (Tasks 1-4)
        with phase_profile("translation", ctx):
            translated_blocks = self.translation_pipeline.batch_translate_blocks(
                blocks, request.source_lang, request.target_lang,
                glossary_store=glossary_store,
                document_memory=ctx.document_memory,
                mode=ctx.mode,
                translation_cache=translation_cache,
                quality_reviewer=self._quality_reviewer if ctx.mode.ai_quality_review else None,
                semantic_chunker=self._semantic_chunker if ctx.mode.semantic_chunking else None,
                document_profile=ctx.document_profile,
                ctx=ctx,
            )
        ctx.translation_time_ms = ctx.phase_times.get("translation", 0)
        ctx.translated_chunks = len(translated_blocks)

        # Validate layout
        with phase_profile("layout_validation", ctx):
            layout_warnings = self.layout_validator.validate(blocks, translated_blocks)
        for w in layout_warnings:
            ctx.add_warning(f"Layout: {w}")

        # ── Phase 8: AI Layout Planning (PDF only) ───────────────────────
        if ctx.mode.layout_planner and self._layout_planner and ext == ".pdf":
            print("[LAYOUT] Planning layout adjustments...")
            with phase_profile("layout_planning", ctx):
                ctx.layout_plan = self._layout_planner.plan(
                    blocks, translated_blocks,
                    request.source_lang, request.target_lang,
                    doc_format="pdf",
                    document_type=ctx.document_profile.document_type if ctx.document_profile else "",
                )

        # ── Reconstruct document ─────────────────────────────────────────
        print(f"[OUTPUT] Rebuilding document -> {output_file}")
        with phase_profile("reconstruction", ctx):
            reconstruct_document(translated_blocks, output_file, request.file_path, detected_ext,
                                 source_lang=request.source_lang, target_lang=request.target_lang,
                                 layout_plan=ctx.layout_plan)
        ctx.reconstruction_time_ms = ctx.phase_times.get("reconstruction", 0)

        # BLEU scoring
        bleu_score = None
        if request.reference_file is not None:
            bleu_score = self.bleu_reporter.compute(translated_blocks, request.reference_file)
            if bleu_score is not None:
                print(f"  [BLEU] Score: {bleu_score:.2f}")

        # ── Finalize ─────────────────────────────────────────────────────
        ctx.stop_timer()
        ctx.log_summary()

        # Cleanup memory
        if ctx.document_memory:
            ctx.document_memory.clear()
        if translation_cache:
            translation_cache.clear_document_cache()

        return DocumentTranslationResponse(
            output_path=output_file,
            translated_blocks=translated_blocks,
            provider=self.translation_pipeline.provider.name,
            model=self.translation_pipeline.provider.model_name,
            total_chunks=len(translated_blocks),
            total_execution_time_ms=ctx.total_time_ms,
            bleu_score=bleu_score,
            warnings=ctx.warnings,
            mode=ctx.mode.name,
            document_type=ctx.document_profile.document_type if ctx.document_profile else "",
        )

    # ── In-place Translation ────────────────────────────────────────────────

    def _translate_inplace(self, request, ext, output_file, glossary_store, ctx):
        """Translate a document in-place (DOCX/PPTX/XLSX)."""
        # Initialize document memory if enabled
        if ctx.mode.document_memory:
            memory = DocumentMemory()
            ctx.document_memory = memory

        # OPTIMIZATION: Get shared cache (Task 2)
        translation_cache = self._get_cache()
        if translation_cache:
            ctx.translation_cache = translation_cache

        # Build the translate function with enhanced context
        def _translate_fn(text, block_type="paragraph"):
            # Check cache first
            if translation_cache:
                cached = translation_cache.get(
                    text, request.target_lang,
                    self.translation_pipeline.provider.name,
                )
                if cached is not None:
                    ctx.cache_stat(hit=True)
                    ctx.blocks_cached += 1
                    return cached

            ctx.cache_stat(hit=False)

            # Build context from document memory
            context = ""
            if ctx.document_memory:
                context = ctx.document_memory.get_context_for_block(
                    {"text": text, "type": block_type}, 0
                )

            # OPTIMIZATION: Inject prepass context (Task 5)
            if ctx.prepass_summary or ctx.prepass_domain or ctx.prepass_terms:
                prepass_preamble = build_prepass_injection(
                    ctx.prepass_summary, ctx.prepass_domain, ctx.prepass_terms
                )
                if context:
                    context = prepass_preamble + "\n" + context
                else:
                    context = prepass_preamble

            # Translate via pipeline
            from dto.requests import TranslationRequest
            treq = TranslationRequest(
                text=text,
                source_lang=request.source_lang,
                target_lang=request.target_lang,
                block_type=block_type,
                context_hint=context,
                document_type=ctx.document_profile.document_type if ctx.document_profile else "",
            )
            resp = self.translation_pipeline.translate(treq)
            translated = resp.translated_text

            # Apply glossary
            if glossary_store is not None:
                translated = glossary_store.apply(translated)

            # Cache the result
            if translation_cache:
                translation_cache.put(
                    text, request.target_lang,
                    self.translation_pipeline.provider.name, translated,
                )

            ctx.blocks_translated += 1
            return translated

        # Choose the right in-place translator
        if ext == ".docx":
            _translate_docx_inplace_with_translator(
                request.file_path, output_file, _translate_fn,
                glossary_store=glossary_store,
            )
        elif ext == ".pptx":
            translate_pptx_inplace(
                request.file_path, output_file, _translate_fn,
                glossary_store=glossary_store,
            )
        elif ext == ".xlsx":
            translate_xlsx_inplace(
                request.file_path, output_file, _translate_fn,
                glossary_store=glossary_store,
            )

        ctx.total_time_ms = ctx.stop_timer()
        ctx.log_summary()

        if ctx.document_memory:
            ctx.document_memory.clear()
        if translation_cache:
            translation_cache.clear_document_cache()

        return DocumentTranslationResponse(
            output_path=output_file,
            provider=self.translation_pipeline.provider.name,
            model=self.translation_pipeline.provider.model_name,
            total_execution_time_ms=ctx.total_time_ms,
            mode=ctx.mode.name,
        )

    # ── CSV Translation ─────────────────────────────────────────────────────

    def _translate_csv(self, csv_data, request, output_file, glossary_store, ctx):
        """Translate a CSV file."""
        print(f"  Found {len(csv_data.get('data', []))} rows in CSV.")
        print("[TRANSLATE] Translating...")

        translated_rows = []
        for row_idx, row in enumerate(csv_data["data"]):
            translated_row = []
            for col_idx, cell in enumerate(row):
                if cell.strip() and len(cell.split()) >= 1:
                    translated = self._translate_single(
                        cell, request.source_lang, request.target_lang,
                        ctx=ctx,
                    )
                    translated_row.append(translated)
                else:
                    translated_row.append(cell)
            translated_rows.append(translated_row)

        print("\n[OUTPUT] Rebuilding CSV ->", output_file)
        write_csv(translated_rows, output_file)

        ctx.stop_timer()
        ctx.log_summary()
        total_chunks = sum(len(row) for row in translated_rows)

        return DocumentTranslationResponse(
            output_path=output_file,
            provider=self.translation_pipeline.provider.name,
            model=self.translation_pipeline.provider.model_name,
            total_chunks=total_chunks,
            total_execution_time_ms=ctx.total_time_ms,
            mode=ctx.mode.name,
        )

    # ── Single Block Translation Helper ─────────────────────────────────────


    def _execute_prepass_concurrent(self, blocks, request, ctx):
        """Run the prepass phase. Designed for concurrent execution."""
        with phase_profile("prepass", ctx):
            try:
                prepass_text = ""
                token_count = 0
                for block in blocks:
                    text = block.get("text", "")
                    words = text.split()
                    if token_count + len(words) > 500:
                        remaining = 500 - token_count
                        if remaining > 0:
                            prepass_text += " " + " ".join(words[:remaining])
                        break
                    prepass_text += " " + text
                    token_count += len(words)
    
                prepass_text = prepass_text.strip()
    
                if prepass_text:
                    with llm_call_profile(ctx):
                        sys_prompt = build_prepass_system_prompt()
                        user_prompt = build_prepass_user_prompt(
                            prepass_text, request.source_lang, request.target_lang
                        )
                        prepass_result = self._ai_provider.analyze(sys_prompt, user_prompt)
    
                    summary = prepass_result.get("summary", "")
                    domain = prepass_result.get("domain", "")
                    terms_raw = prepass_result.get("terms", [])
                    terms = []
                    if isinstance(terms_raw, list):
                        for t in terms_raw:
                            if isinstance(t, dict):
                                src = t.get("source", "")
                                tgt = t.get("target", "")
                                if src and tgt:
                                    terms.append((src, tgt))
    
                    ctx.prepass_summary = summary
                    ctx.prepass_domain = domain
                    ctx.prepass_terms = terms
    
                    print(f"  [Prepass] Summary: {summary[:80]}...")
                    print(f"  [Prepass] Domain: {domain}")
                    print(f"  [Prepass] Terms: {len(terms)}")
    
            except Exception as e:
                print(f"  [Prepass] Concurrent prepass warning: {e}")
    
    def _translate_single(self, text, source_lang, target_lang,
                          block_type="paragraph", ctx=None):
        """Translate a single text block via the pipeline."""
        from dto.requests import TranslationRequest

        # OPTIMIZATION: Check cache (Task 2)
        translation_cache = self._get_cache()
        if translation_cache:
            cached = translation_cache.get(
                text, target_lang, self.translation_pipeline.provider.name
            )
            if cached is not None:
                if ctx:
                    ctx.cache_stat(hit=True)
                    ctx.blocks_cached += 1
                return cached
            if ctx:
                ctx.cache_stat(hit=False)

        # Build context from memory
        context = ""
        if ctx and ctx.document_memory:
            context = ctx.document_memory.get_context_for_block(
                {"text": text, "type": block_type}, 0
            )

        # OPTIMIZATION: Inject prepass context (Task 5)
        if ctx and (ctx.prepass_summary or ctx.prepass_domain or ctx.prepass_terms):
            prepass_preamble = build_prepass_injection(
                ctx.prepass_summary, ctx.prepass_domain, ctx.prepass_terms
            )
            if context:
                context = prepass_preamble + "\n" + context
            else:
                context = prepass_preamble

        request = TranslationRequest(
            text=text,
            source_lang=source_lang,
            target_lang=target_lang,
            block_type=block_type,
            context_hint=context,
            document_type=ctx.document_profile.document_type if ctx and ctx.document_profile else "",
        )
        response = self.translation_pipeline.translate(request)
        translated = response.translated_text

        # Cache the result
        if translation_cache:
            translation_cache.put(
                text, target_lang,
                self.translation_pipeline.provider.name, translated,
            )

        if ctx:
            ctx.blocks_translated += 1

        return translated

    # ── Adaptive Mode Selection (Phase 9) ────────────────────────────────────

    def _determine_mode(self, request: DocumentTranslationRequest):
        """Automatically select processing mode based on document.

        If mode is 'auto', analyzes document characteristics to choose.
        Otherwise uses the requested mode.

        Phase 9 — Adaptive Processing.
        """
        if request.mode not in VALID_MODES:
            print(f"  [Mode] Unknown mode '{request.mode}', falling back to balanced")
            return get_mode("balanced")

        if request.mode != "auto":
            return get_mode(request.mode)

        # Auto-detect mode based on document characteristics
        ext = os.path.splitext(request.file_path)[1].lower()
        blocks = []
        try:
            data, _ = analyze_document(request.file_path,
                                       pdf_column_mode=request.pdf_column_mode)
            if isinstance(data, list):
                blocks = data
        except Exception:
            # If we can't analyze, default to balanced
            print("  [Mode] Cannot analyze document, using balanced")
            return get_mode("balanced")

        num_blocks = len(blocks)
        total_words = sum(len(b.get("text", "").split()) for b in blocks)

        # Simple text files — fast
        if ext in (".txt", ".md", ".csv"):
            if total_words < 500:
                print("  [Mode] Auto-selected: fast (small text file)")
                return get_mode("fast")
            print("  [Mode] Auto-selected: balanced (text file)")
            return get_mode("balanced")

        # Short documents — balanced
        if num_blocks < 10 and total_words < 1000:
            print("  [Mode] Auto-selected: balanced (short document)")
            return get_mode("balanced")

        # Check complexity
        has_tables = any(b.get("type") == "table_cell" for b in blocks)
        has_headers = any(b.get("type") in ("header", "heading") for b in blocks)

        # Complex documents — thorough
        if ext == ".pdf" or has_tables or num_blocks > 50 or total_words > 5000:
            print("  [Mode] Auto-selected: thorough (complex document)")
            return get_mode("thorough")

        print("  [Mode] Auto-selected: balanced")
        return get_mode("balanced")