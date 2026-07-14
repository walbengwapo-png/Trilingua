# -*- coding: utf-8 -*-
"""
Document pipeline.

Orchestrates the complete document translation flow:
1. Read file (via extractor)
2. Extract elements (paragraphs, tables, images, headers, footers)
3. Chunking
4. Translation via TranslationPipeline
5. Reconstruction
6. Layout validation
7. Return document

The provider never manipulates documents directly.
"""

import os
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
from memory.glossary import GlossaryStore
from validators.translation_validator import LayoutValidator, BLEUReporter
from pipeline.translation_pipeline import TranslationPipeline


class DocumentPipeline:
    """Orchestrates the complete document translation process."""

    def __init__(self, translation_pipeline: TranslationPipeline):
        self.translation_pipeline = translation_pipeline
        self.layout_validator = LayoutValidator()
        self.bleu_reporter = BLEUReporter()

    def translate(self, request: DocumentTranslationRequest) -> DocumentTranslationResponse:
        """Translate a document through the full pipeline.

        Args:
            request: The document translation request.

        Returns:
            A DocumentTranslationResponse.
        """
        import time as _time
        start_time = _time.time()

        ext = os.path.splitext(request.file_path)[1].lower()

        # Build glossary
        glossary_store = GlossaryStore(request.glossary_pairs) if request.glossary_pairs else None

        # Build output path
        output_file = choose_output_path(request.file_path)

        # ── In-place translation for DOCX, PPTX, XLSX ──
        if ext == ".docx":
            print("[INPUT] Translating DOCX in-place...")
            _translate_docx_inplace_with_translator(
                request.file_path, output_file,
                translate_fn=lambda text, block_type="paragraph": self._translate_single(
                    text, request.source_lang, request.target_lang, block_type
                ),
                glossary_store=glossary_store,
            )
            elapsed = (_time.time() - start_time) * 1000
            return DocumentTranslationResponse(
                output_path=output_file,
                provider=self.translation_pipeline.provider.name,
                model=self.translation_pipeline.provider.model_name,
                total_execution_time_ms=elapsed,
            )

        if ext == ".pptx":
            print("[INPUT] Translating PPTX in-place...")
            translate_pptx_inplace(
                request.file_path, output_file,
                translate_fn=lambda text, block_type="paragraph": self._translate_single(
                    text, request.source_lang, request.target_lang, block_type
                ),
                glossary_store=glossary_store,
            )
            elapsed = (_time.time() - start_time) * 1000
            return DocumentTranslationResponse(
                output_path=output_file,
                provider=self.translation_pipeline.provider.name,
                model=self.translation_pipeline.provider.model_name,
                total_execution_time_ms=elapsed,
            )

        if ext == ".xlsx":
            print("[INPUT] Translating XLSX in-place...")
            translate_xlsx_inplace(
                request.file_path, output_file,
                translate_fn=lambda text, block_type="table_cell": self._translate_single(
                    text, request.source_lang, request.target_lang, "table_cell"
                ),
                glossary_store=glossary_store,
            )
            elapsed = (_time.time() - start_time) * 1000
            return DocumentTranslationResponse(
                output_path=output_file,
                provider=self.translation_pipeline.provider.name,
                model=self.translation_pipeline.provider.model_name,
                total_execution_time_ms=elapsed,
            )

        # ── PDF: try LibreOffice pipeline first ──
        if ext == ".pdf":
            if _is_libreoffice_available():
                print("[INPUT] Translating PDF via LibreOffice (DOCX round-trip)...")
                try:
                    translate_pdf_via_libreoffice(
                        request.file_path, output_file,
                        translate_fn=lambda text, block_type="paragraph": self._translate_single(
                            text, request.source_lang, request.target_lang, block_type
                        ),
                        glossary_store=glossary_store,
                    )
                    elapsed = (_time.time() - start_time) * 1000
                    return DocumentTranslationResponse(
                        output_path=output_file,
                        provider=self.translation_pipeline.provider.name,
                        model=self.translation_pipeline.provider.model_name,
                        total_execution_time_ms=elapsed,
                    )
                except Exception as e:
                    print(f"  ⚠️  LibreOffice PDF translation failed: {e}")
                    print("  Falling back to PyMuPDF direct translation...")
            else:
                print("[INPUT] LibreOffice not available, using PyMuPDF for PDF...")

        # ── Extract → Translate → Reconstruct pipeline ──
        print("[INPUT] Reading document...")
        data, detected_ext = analyze_document(request.file_path, pdf_column_mode=request.pdf_column_mode)

        # Handle CSV separately
        if detected_ext == ".csv":
            csv_data = data
            print(f"  Found {len(csv_data.get('data', []))} rows in CSV.")
            print("[TRANSLATE] Translating...")
            translated_rows = []
            for row_idx, row in enumerate(csv_data["data"]):
                translated_row = []
                for col_idx, cell in enumerate(row):
                    if cell.strip() and len(cell.split()) >= 1:
                        translated_row.append(
                            self._translate_single(cell, request.source_lang, request.target_lang)
                        )
                    else:
                        translated_row.append(cell)
                translated_rows.append(translated_row)
            print("\n[OUTPUT] Rebuilding CSV ->", output_file)
            write_csv(translated_rows, output_file)

            total_chunks = sum(len(row) for row in translated_rows)
            elapsed = (_time.time() - start_time) * 1000
            return DocumentTranslationResponse(
                output_path=output_file,
                provider=self.translation_pipeline.provider.name,
                model=self.translation_pipeline.provider.model_name,
                total_chunks=total_chunks,
                total_execution_time_ms=elapsed,
            )

        blocks = data
        print(f"  Found {len(blocks)} text block(s) after filtering.")

        if not blocks:
            raise ValueError(
                "No translatable text extracted. "
                "If this is a scanned PDF, OCR is required. "
                "For bilingual PDFs, try pdf_column_mode='left' or 'right'."
            )

        # Translate blocks
        print("[TRANSLATE] Translating...")
        translated_blocks = self.translation_pipeline.batch_translate_blocks(
            blocks, request.source_lang, request.target_lang,
            glossary_store=glossary_store,
        )

        # Validate layout
        layout_warnings = self.layout_validator.validate(blocks, translated_blocks)
        if layout_warnings:
            for w in layout_warnings:
                print(f"  ⚠️  Layout: {w}")

        # Reconstruct document
        print(f"[OUTPUT] Rebuilding document -> {output_file}")
        reconstruct_document(translated_blocks, output_file, request.file_path, detected_ext)

        # BLEU scoring
        bleu_score = None
        if request.reference_file is not None:
            bleu_score = self.bleu_reporter.compute(translated_blocks, request.reference_file)
            if bleu_score is not None:
                print(f"  [BLEU] Score: {bleu_score:.2f}")

        elapsed = (_time.time() - start_time) * 1000
        return DocumentTranslationResponse(
            output_path=output_file,
            translated_blocks=translated_blocks,
            provider=self.translation_pipeline.provider.name,
            model=self.translation_pipeline.provider.model_name,
            total_chunks=len(translated_blocks),
            total_execution_time_ms=elapsed,
            bleu_score=bleu_score,
            warnings=layout_warnings,
        )

    def _translate_single(self, text: str, source_lang: str, target_lang: str,
                          block_type: str = "paragraph") -> str:
        """Translate a single text block via the pipeline and return just the text."""
        from dto.requests import TranslationRequest

        request = TranslationRequest(
            text=text,
            source_lang=source_lang,
            target_lang=target_lang,
            block_type=block_type,
        )
        response = self.translation_pipeline.translate(request)
        return response.translated_text