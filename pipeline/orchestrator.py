# -*- coding: utf-8 -*-
"""
Pipeline Orchestrator — coordinates the complete document translation pipeline.
Connects Document Intelligence Layer, Semantic Analysis, Context Engine,
Translation Engine, Layout Reconstruction, and Quality Validation.
"""

import logging
import time
from typing import Optional, Callable

from intelligence.graph.document_graph import (
    DocumentObjectGraph,
    SemanticRole,
)
from intelligence.semantic.role_classifier import RoleClassifier
from intelligence.semantic.group_detector import GroupDetector
from intelligence.context.context_engine import ContextEngine
from translation.engine import TranslationEngine
from validation.engine import ValidationEngine
from validation.severity import QualityReport
from exceptions import (
    InputError,
    ParseError,
    TranslationError,
    ValidationError,
    CheckpointError,
)
from pipeline.checkpoint_manager import CheckpointManager

logger = logging.getLogger(__name__)


class PipelineOrchestrator:
    """Master orchestrator for the complete document translation pipeline.

    Stages:
    1. Document Intelligence (parse → Object Graph)
    2. Semantic Analysis (role classification + group detection)
    3. Context Engine Initialization
    4. Page-Window Translation (TM → LLM → post-process)
    5. Layout Reconstruction
    6. Quality Validation → QA Report
    """

    def __init__(
        self,
        llm_provider=None,
        ai_analysis_provider=None,
        ai_reviewer=None,
        adapter=None,
        mode: str = "balanced",
    ):
        """
        Args:
            llm_provider: Translation LLM provider.
            ai_analysis_provider: Analysis LLM provider (for role classification).
            ai_reviewer: AI quality reviewer.
            adapter: Format adapter for parsing documents.
            mode: Processing mode ('fast', 'balanced', 'thorough').
        """
        self._llm = llm_provider
        self._ai_analysis = ai_analysis_provider
        self._ai_reviewer = ai_reviewer
        self._adapter = adapter
        self._mode = mode

        # Initialize components
        self._role_classifier = RoleClassifier(llm_provider=ai_analysis_provider)
        self._group_detector = GroupDetector()
        self._translation_engine = TranslationEngine(llm_provider=llm_provider)
        self._validation_engine = ValidationEngine(ai_reviewer=ai_reviewer)

    # ── Main Pipeline Entry Point ─────────────────────────────────

    def translate_document(
        self,
        file_path: str,
        source_lang: str = "",
        target_lang: str = "",
        source_format: str = "",
        document_id: str = "",
        progress_callback: Optional[Callable] = None,
    ) -> dict:
        """Run the full translation pipeline on a document.

        Args:
            file_path: Path to the source document.
            source_lang: Source language name/code.
            target_lang: Target language name/code.
            source_format: File format (auto-detected if empty).
            document_id: Unique document identifier.
            progress_callback: Optional callable(stage, percent, message).

        Returns:
            Dict with results: {
                "graph": DocumentObjectGraph,
                "translated_graph": DocumentObjectGraph,
                "quality_report": QualityReport,
                "output_path": str,
                "execution_time_ms": float,
                "success": bool,
                "error": str
            }
        """
        start_time = time.time()
        result = {
            "success": False,
            "error": "",
            "execution_time_ms": 0,
            "graph": None,
            "translated_graph": None,
            "quality_report": None,
            "output_path": "",
        }

        try:
            # Stage 1: Parse Document
            self._report_progress(progress_callback, "parsing", 0, "Parsing document...")
            graph = self._parse_document(file_path, source_format, document_id)
            result["graph"] = graph
            logger.info(f"Stage 1 complete: {len(graph.all_objects)} objects, {len(graph.pages)} pages")

            # Stage 2: Semantic Analysis
            self._report_progress(
                progress_callback, "analyzing", 15,
                "Classifying semantic roles..."
            )
            graph = self._role_classifier.classify_graph(graph)
            graph = self._group_detector.detect_groups(graph)
            logger.info(f"Stage 2 complete: {len(graph.groups)} groups detected")

            # Stage 3: Context Engine
            self._report_progress(
                progress_callback, "context", 25,
                "Initializing context engine..."
            )
            context = ContextEngine(graph)
            context.initialize()
            logger.info(f"Stage 3 complete: TM entries={len(context._tm_exact)}")

            # Stage 4: Translation
            self._report_progress(
                progress_callback, "translating", 30,
                "Translating document..."
            )

            def _translation_progress(completed, total, msg):
                pct = 30 + int((completed / total) * 50) if total > 0 else 50
                self._report_progress(
                    progress_callback, "translating", pct,
                    f"{msg} ({completed}/{total})"
                )

            translated_graph = self._translation_engine.translate_graph(
                graph, context,
                source_lang=source_lang,
                target_lang=target_lang,
                progress_callback=_translation_progress,
            )
            result["translated_graph"] = translated_graph
            logger.info(f"Stage 4 complete: TM hits={context.tm_hits}, fuzzy={context.tm_fuzzy_hits}")

            # Stage 5: Layout Reconstruction
            self._report_progress(
                progress_callback, "reconstructing", 85,
                "Reconstructing document layout..."
            )
            output_path = self._reconstruct_document(translated_graph, file_path)
            result["output_path"] = output_path
            logger.info(f"Stage 5 complete: output={output_path}")

            # Stage 6: Quality Validation
            self._report_progress(
                progress_callback, "validating", 92,
                "Running quality validation..."
            )
            quality_report = self._validation_engine.validate(graph, translated_graph)
            result["quality_report"] = quality_report

            if not quality_report.passed:
                logger.warning(
                    f"Quality report: score={quality_report.overall_score:.2f}, "
                    f"critical={quality_report.critical_count}"
                )

            # Finalize
            elapsed = (time.time() - start_time) * 1000
            result["execution_time_ms"] = elapsed
            result["success"] = True

            self._report_progress(
                progress_callback, "completed", 100,
                f"Translation complete ({elapsed:.0f}ms)"
            )

            # Log stats
            logger.info(
                f"Pipeline complete: {elapsed:.0f}ms, "
                f"quality={quality_report.overall_score:.2f}, "
                f"TM hits={context.tm_hits}, misses={context.tm_misses}"
            )

            context.clear()

        except (InputError, ParseError) as e:
            result["error"] = str(e)
            logger.error(f"Input/Parse error: {e}")
        except TranslationError as e:
            result["error"] = f"Translation failed: {e}"
            logger.error(f"Translation error: {e}")
        except ValidationError as e:
            result["error"] = f"Validation failed: {e}"
            result["quality_report"] = QualityReport(
                overall_score=0.0, passed=False,
                recommendation=str(e)
            )
            logger.error(f"Validation error: {e}")
        except Exception as e:
            result["error"] = f"Unexpected error: {e}"
            logger.exception(f"Pipeline failed: {e}")

        return result

    # ── Pipeline Stages ───────────────────────────────────────────

    def _parse_document(
        self, file_path: str, source_format: str, document_id: str
    ) -> DocumentObjectGraph:
        """Stage 1: Parse document into Object Graph."""
        if not self._adapter:
            # No adapter — return empty graph
            graph = DocumentObjectGraph(
                document_id=document_id or "unknown",
                filename=file_path.split("/")[-1],
                file_format=source_format,
            )
            return graph

        try:
            graph = self._adapter.parse(file_path, source_format)
            graph.document_id = document_id or graph.document_id
            return graph
        except Exception as e:
            raise ParseError(f"Failed to parse document: {e}") from e

    def _reconstruct_document(
        self, graph: DocumentObjectGraph, original_path: str
    ) -> str:
        """Stage 5: Reconstruct document from translated graph."""
        # Placeholder — actual implementation depends on format adapter
        output_path = original_path.replace(".", "_translated.")
        logger.info(f"Reconstruction would write to: {output_path}")
        return output_path

    # ── Progress Reporting ────────────────────────────────────────

    def _report_progress(self, callback, stage, percent, message):
        """Report progress if callback is provided."""
        if callback:
            try:
                callback(stage, percent, message)
            except Exception:
                pass

    # ── Single Text Translation (Non-Document) ────────────────────

    def translate_text(
        self,
        text: str,
        source_lang: str = "",
        target_lang: str = "",
        role: str = "paragraph",
    ) -> str:
        """Translate a single text block (bypasses full document pipeline).

        Returns translated text.
        """
        # Map role string to SemanticRole
        role_map = {
            "paragraph": SemanticRole.PARAGRAPH,
            "heading": SemanticRole.HEADING_1,
            "question": SemanticRole.QUESTION_STEM,
            "instruction": SemanticRole.INSTRUCTION,
            "mc_option": SemanticRole.MULTIPLE_CHOICE_OPTION,
            "learning_objective": SemanticRole.LEARNING_OBJECTIVE,
        }
        semantic_role = role_map.get(role.lower(), SemanticRole.PARAGRAPH)

        return self._translation_engine.translate_text(
            text=text,
            source_lang=source_lang,
            target_lang=target_lang,
            role=semantic_role,
        )