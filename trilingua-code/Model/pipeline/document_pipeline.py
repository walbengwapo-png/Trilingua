# -*- coding: utf-8 -*-
"""
Document pipeline.

Orchestrates the complete document translation flow:
1. Read file (via extractor)
2. AI Document Analysis (Phase 1) — when mode permits
3. Document Memory initialization (Phase 2) — when mode permits
4. Semantic Chunking (Phase 3) — when mode permits
5. Translation via TranslationPipeline
6. AI Quality Review (Phase 5) — when mode permits
7. AI Layout Planning (Phase 8) — when mode permits (PDF only)
8. Reconstruction (existing, untouched)
9. Layout validation (existing, untouched)
10. Logging via DocumentContext

The provider never manipulates documents directly.
Deterministic engineering is preserved at all times.
"""

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
    _is_libreoffice_available,
    translate_pdf_via_libreoffice,
)
from document.document_analyzer import DocumentAnalyzer
from document.semantic_chunker import SemanticChunker
from document.layout_planner import LayoutPlanner
from memory.glossary import GlossaryStore
from memory.document_memory import DocumentMemory
from memory.translation_cache import TranslationCache
from validators.translation_validator import LayoutValidator, BLEUReporter
from validators.ai_quality_reviewer import AIQualityReviewer
from pipeline.translation_pipeline import TranslationPipeline
from pipeline.document_context import DocumentContext


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

        self._default_mode = mode

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

        # ── In-place translation for DOCX, PPTX, XLSX ──
        # These use the existing deterministic pipeline with slightly enhanced
        # context via DocumentMemory (if enabled)
        if ext in (".docx", ".pptx", ".xlsx"):
            return self._translate_inplace(request, ext, output_file, glossary_store, ctx)

        # ── PDF: try LibreOffice pipeline first ──
        if ext == ".pdf":
            if _is_libreoffice_available():
                print("[INPUT] Translating PDF via LibreOffice (DOCX round-trip)...")
                try:
                    return self._translate_inplace(
                        request, ".docx", output_file, glossary_store, ctx,
                        pdf_roundtrip=True
                    )
                except Exception as e:
                    print(f"  ⚠️  LibreOffice PDF translation failed: {e}")
                    print("  Falling back to PyMuPDF direct translation...")
            else:
                print("[INPUT] LibreOffice not available, using PyMuPDF for PDF...")

        # ── Extract → Analyze → Translate → Reconstruct pipeline ──
        t0 = _time.time()
        print("[INPUT] Reading document...")
        data, detected_ext = analyze_document(request.file_path, pdf_column_mode=request.pdf_column_mode)
        ctx.extraction_time_ms = (_time.time() - t0) * 1000
        ctx.total_blocks = len(data) if isinstance(data, list) else 0

        # Handle CSV separately
        if detected_ext == ".csv":
            return self._translate_csv(data, request, output_file, glossary_store, ctx)

        blocks = data
        print(f"  Found {len(blocks)} text block(s) after filtering.")

        if not blocks:
            raise ValueError(
                "No translatable text extracted. "
                "If this is a scanned PDF, OCR is required. "
                "For bilingual PDFs, try pdf_column_mode='left' or 'right'."
            )

        # ── Phase 1: AI Document Analysis ────────────────────────────────
        if ctx.mode.document_analyzer and self._document_analyzer:
            t0 = _time.time()
            print("[ANALYZE] Running AI document analysis...")
            profile = self._document_analyzer.analyze(blocks)
            ctx.analysis_time_ms = (_time.time() - t0) * 1000
            ctx.document_profile = profile
        else:
            ctx.document_profile = None

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
        if ctx.mode.translation_cache:
            ctx.translation_cache = TranslationCache()
        else:
            ctx.translation_cache = None

        # ── Phase 3: Semantic Chunking & Translation ─────────────────────
        print("[TRANSLATE] Translating...")
        t0 = _time.time()
        translated_blocks = self.translation_pipeline.batch_translate_blocks(
            blocks, request.source_lang, request.target_lang,
            glossary_store=glossary_store,
            document_memory=ctx.document_memory,
            mode=ctx.mode,
            translation_cache=ctx.translation_cache,
            quality_reviewer=self._quality_reviewer if ctx.mode.ai_quality_review else None,
            semantic_chunker=self._semantic_chunker if ctx.mode.semantic_chunking else None,
            document_profile=ctx.document_profile,
        )
        ctx.translation_time_ms = (_time.time() - t0) * 1000
        ctx.translated_chunks = len(translated_blocks)

        # Validate layout
        layout_warnings = self.layout_validator.validate(blocks, translated_blocks)
        for w in layout_warnings:
            ctx.add_warning(f"Layout: {w}")

        # ── Phase 8: AI Layout Planning (PDF only) ───────────────────────
        if ctx.mode.layout_planner and self._layout_planner and ext == ".pdf":
            print("[LAYOUT] Planning layout adjustments...")
            ctx.layout_plan = self._layout_planner.plan(
                blocks, translated_blocks,
                request.source_lang, request.target_lang,
                doc_format="pdf",
                document_type=ctx.document_profile.document_type if ctx.document_profile else "",
            )

        # ── Reconstruct document ─────────────────────────────────────────
        t0 = _time.time()
        print(f"[OUTPUT] Rebuilding document -> {output_file}")
        reconstruct_document(translated_blocks, output_file, request.file_path, detected_ext)
        ctx.reconstruction_time_ms = (_time.time() - t0) * 1000

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
        if ctx.translation_cache:
            ctx.translation_cache.clear()

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

    def _translate_inplace(self, request, ext, output_file, glossary_store, ctx,
                           pdf_roundtrip=False):
        """Translate a document in-place (DOCX/PPTX/XLSX or LibreOffice PDF)."""
        # Initialize document memory if enabled
        if ctx.mode.document_memory:
            memory = DocumentMemory()
            ctx.document_memory = memory

        # Initialize translation cache if enabled
        if ctx.mode.translation_cache:
            ctx.translation_cache = TranslationCache()

        # Build the translate function with enhanced context
        def _translate_fn(text, block_type="paragraph"):
            # Check cache first
            if ctx.translation_cache:
                cached = ctx.translation_cache.get(
                    text, request.source_lang, request.target_lang
                )
                if cached is not None:
                    ctx.cache_stat(hit=True)
                    return cached

            ctx.cache_stat(hit=False)

            # Build context from document memory
            context = ""
            if ctx.document_memory:
                context = ctx.document_memory.get_context_for_block(
                    {"text": text, "type": block_type}, 0
                )

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
            if ctx.translation_cache:
                ctx.translation_cache.put(
                    text, request.source_lang, request.target_lang, translated
                )

            return translated

        # Choose the right in-place translator
        if ext == ".docx" or pdf_roundtrip:
            actual_input = request.file_path
            if pdf_roundtrip:
                from document.reconstructor import translate_pdf_via_libreoffice
                translate_pdf_via_libreoffice(
                    request.file_path, output_file, _translate_fn,
                    glossary_store=glossary_store,
                )
            else:
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
        if ctx.translation_cache:
            ctx.translation_cache.clear()

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

    def _translate_single(self, text, source_lang, target_lang,
                          block_type="paragraph", ctx=None):
        """Translate a single text block via the pipeline."""
        from dto.requests import TranslationRequest

        # Check cache
        if ctx and ctx.translation_cache:
            cached = ctx.translation_cache.get(text, source_lang, target_lang)
            if cached is not None:
                ctx.cache_stat(hit=True)
                return cached
            ctx.cache_stat(hit=False)

        # Build context from memory
        context = ""
        if ctx and ctx.document_memory:
            context = ctx.document_memory.get_context_for_block(
                {"text": text, "type": block_type}, 0
            )

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
        if ctx and ctx.translation_cache:
            ctx.translation_cache.put(text, source_lang, target_lang, translated)

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