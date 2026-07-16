# -*- coding: utf-8 -*-
"""
Batch Worker — processes multiple document translations.
Handles job queuing, parallel execution, and result aggregation.
"""

import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Optional

from workers.document_worker import DocumentWorker

logger = logging.getLogger(__name__)


class BatchWorker:
    """Processes multiple document translations with concurrency control."""

    def __init__(self, max_concurrent: int = 2, **worker_kwargs):
        """
        Args:
            max_concurrent: Maximum concurrent document translations.
            **worker_kwargs: Arguments to pass to DocumentWorker constructor.
        """
        self._max_concurrent = max_concurrent
        self._worker_kwargs = worker_kwargs

    def process_batch(self, jobs: list[dict]) -> list[dict]:
        """Process a batch of translation jobs.

        Args:
            jobs: List of job dicts, each containing:
                  - job_id: str
                  - file_path: str
                  - source_lang: str
                  - target_lang: str
                  - source_format: str (optional)
                  - mode: str (optional)

        Returns:
            List of result dicts in same order as input jobs.
        """
        results = [None] * len(jobs)
        worker = DocumentWorker(**self._worker_kwargs)

        with ThreadPoolExecutor(max_workers=self._max_concurrent) as executor:
            future_to_idx = {}
            for idx, job in enumerate(jobs):
                future = executor.submit(
                    worker.process,
                    job_id=job.get("job_id", f"batch_{idx}"),
                    file_path=job["file_path"],
                    source_lang=job["source_lang"],
                    target_lang=job["target_lang"],
                    source_format=job.get("source_format", ""),
                    mode=job.get("mode", "balanced"),
                )
                future_to_idx[future] = idx

            for future in as_completed(future_to_idx):
                idx = future_to_idx[future]
                try:
                    results[idx] = future.result()
                except Exception as e:
                    logger.error(f"Batch job {idx} failed: {e}")
                    results[idx] = {
                        "success": False,
                        "error": str(e),
                    }

        return results