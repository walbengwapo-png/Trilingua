# -*- coding: utf-8 -*-
"""
Document Worker — processes a single document translation job.
Designed to work with Celery or as a standalone function.
"""

import logging
import json
import os
import time
from typing import Optional

from pipeline.orchestrator import PipelineOrchestrator
from pipeline.checkpoint_manager import CheckpointManager

logger = logging.getLogger(__name__)


class DocumentWorker:
    """Processes a single document translation job.

    Can be used directly or as a Celery task.
    """

    def __init__(
        self,
        llm_provider=None,
        ai_analysis_provider=None,
        ai_reviewer=None,
        adapter=None,
    ):
        self._orchestrator = PipelineOrchestrator(
            llm_provider=llm_provider,
            ai_analysis_provider=ai_analysis_provider,
            ai_reviewer=ai_reviewer,
            adapter=adapter,
        )
        self._checkpoint_mgr = None

    def process(
        self,
        job_id: str,
        file_path: str,
        source_lang: str,
        target_lang: str,
        source_format: str = "",
        mode: str = "balanced",
        output_dir: Optional[str] = None,
        progress_callback=None,
    ) -> dict:
        """Process a document translation job.

        Args:
            job_id: Unique job identifier.
            file_path: Path to source document.
            source_lang: Source language.
            target_lang: Target language.
            source_format: File format (e.g., "pdf", "docx").
            mode: Processing mode.
            output_dir: Output directory for translated file.
            progress_callback: Optional progress callback.

        Returns:
            Dict with translation results.
        """
        logger.info(
            f"Starting job {job_id}: {file_path} "
            f"({source_lang} → {target_lang}, mode={mode})"
        )

        self._checkpoint_mgr = CheckpointManager(job_id, mode=mode)

        # Run pipeline
        result = self._orchestrator.translate_document(
            file_path=file_path,
            source_lang=source_lang,
            target_lang=target_lang,
            source_format=source_format,
            document_id=job_id,
            progress_callback=progress_callback,
        )

        # Clean up checkpoints on success
        if result["success"]:
            self._checkpoint_mgr.cleanup()

        # Save result summary
        if output_dir:
            os.makedirs(output_dir, exist_ok=True)
            report_path = os.path.join(output_dir, f"{job_id}_result.json")
            with open(report_path, "w", encoding="utf-8") as f:
                json.dump({
                    "job_id": job_id,
                    "success": result["success"],
                    "error": result.get("error", ""),
                    "execution_time_ms": result.get("execution_time_ms", 0),
                    "output_path": result.get("output_path", ""),
                    "quality_score": (
                        result["quality_report"].overall_score
                        if result.get("quality_report") else None
                    ),
                }, f, indent=2)

        return result


# Celery task wrapper (if celery is available)
try:
    from celery import Celery
    celery_app = Celery('trilingua_workers')

    @celery_app.task(bind=True, max_retries=3)
    def translate_document_task(self, job_id, file_path, source_lang, target_lang,
                                 source_format="", mode="balanced"):
        """Celery task for document translation."""
        worker = DocumentWorker()
        try:
            result = worker.process(
                job_id=job_id,
                file_path=file_path,
                source_lang=source_lang,
                target_lang=target_lang,
                source_format=source_format,
                mode=mode,
            )
            return result
        except Exception as exc:
            logger.error(f"Task {job_id} failed: {exc}")
            raise self.retry(exc=exc, countdown=60)
except ImportError:
    logger.debug("Celery not available. DocumentWorker will run synchronously.")