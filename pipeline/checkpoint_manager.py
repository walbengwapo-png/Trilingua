# -*- coding: utf-8 -*-
"""
Checkpoint Manager — save/resume for long-running translations.
Enables recovery from crashes during large document processing.
"""

import json
import logging
import os
import time
from typing import Optional

from intelligence.graph.document_graph import DocumentObjectGraph
from exceptions import CheckpointError

logger = logging.getLogger(__name__)


class CheckpointManager:
    """Manages save/resume for long-running translations.

    Saves checkpoints at configurable page intervals.
    Enables recovery from crashes during large document processing.
    """

    CHECKPOINT_INTERVAL = {
        "fast": 50,       # Save every 50 pages
        "balanced": 25,   # Save every 25 pages
        "thorough": 10,   # Save every 10 pages
    }

    def __init__(self, job_id: str, mode: str = "balanced"):
        """
        Args:
            job_id: Unique job identifier.
            mode: Processing mode (determines checkpoint frequency).
        """
        self.job_id = job_id
        self.interval = self.CHECKPOINT_INTERVAL.get(mode, 25)
        self.last_save_page = 0
        self.checkpoint_dir = os.path.join(
            os.environ.get("TEMP", "/tmp"),
            "trilingua",
            job_id,
            "checkpoints",
        )

    def should_checkpoint(self, current_page: int) -> bool:
        """Check if we should save a checkpoint based on page progress."""
        return (current_page - self.last_save_page) >= self.interval

    def save(
        self,
        graph: DocumentObjectGraph,
        current_page: int,
        context_data: Optional[dict] = None,
    ) -> str:
        """Save a checkpoint to disk.

        Args:
            graph: Current state of the document graph.
            current_page: Last translated page number.
            context_data: Optional context engine state to save.

        Returns:
            Path to the saved checkpoint file.
        """
        try:
            os.makedirs(self.checkpoint_dir, exist_ok=True)
            path = os.path.join(self.checkpoint_dir, f"page_{current_page}.json")

            checkpoint_data = {
                "job_id": self.job_id,
                "version": 2,
                "timestamp": time.time(),
                "current_page": current_page,
                "total_pages": len(graph.pages),
                "total_objects": len(graph.all_objects),
                "graph": graph.to_dict(),
                "context_engine": context_data or {},
            }

            with open(path, "w", encoding="utf-8") as f:
                json.dump(checkpoint_data, f, indent=2, ensure_ascii=False)

            self.last_save_page = current_page
            file_size = os.path.getsize(path)
            logger.info(
                f"Checkpoint saved: page {current_page} → {path} "
                f"({file_size / 1024:.1f} KB)"
            )
            return path

        except (IOError, OSError) as e:
            raise CheckpointError(f"Failed to save checkpoint: {e}") from e

    def restore(self, graph: DocumentObjectGraph) -> int:
        """Restore from the latest checkpoint.

        Args:
            graph: Document graph to restore into.

        Returns:
            Last translated page number (0 if no checkpoint found).
        """
        if not os.path.exists(self.checkpoint_dir):
            logger.info("No checkpoint directory found, starting from beginning")
            return 0

        try:
            # Find latest checkpoint
            checkpoints = sorted(
                [f for f in os.listdir(self.checkpoint_dir) if f.endswith(".json")]
            )
            if not checkpoints:
                return 0

            latest = checkpoints[-1]
            path = os.path.join(self.checkpoint_dir, latest)

            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)

            # Restore graph state
            restored_graph = DocumentObjectGraph.from_dict(data.get("graph", {}))
            page_num = data.get("current_page", 0)

            # Merge restored data into current graph
            for page in restored_graph.pages.values():
                if page.number not in graph.pages:
                    graph.add_page(page)
                else:
                    # Update existing page objects with translated text
                    existing_page = graph.pages[page.number]
                    for obj_id, obj in page.objects.items():
                        if obj_id in existing_page.objects:
                            existing_page.objects[obj_id].translated_text = obj.translated_text
                        else:
                            existing_page.objects[obj_id] = obj
                            graph.all_objects[obj_id] = obj

            logger.info(f"Restored from checkpoint: page {page_num} ({path})")
            return page_num

        except (IOError, json.JSONDecodeError) as e:
            raise CheckpointError(f"Failed to restore checkpoint: {e}") from e

    def cleanup(self) -> None:
        """Remove all checkpoint files for this job."""
        if os.path.exists(self.checkpoint_dir):
            try:
                for f in os.listdir(self.checkpoint_dir):
                    os.remove(os.path.join(self.checkpoint_dir, f))
                os.rmdir(self.checkpoint_dir)
                logger.info(f"Cleaned up checkpoints: {self.checkpoint_dir}")
            except (IOError, OSError) as e:
                logger.warning(f"Failed to clean up checkpoints: {e}")

    def get_checkpoint_count(self) -> int:
        """Get the number of saved checkpoints."""
        if not os.path.exists(self.checkpoint_dir):
            return 0
        return len([f for f in os.listdir(self.checkpoint_dir) if f.endswith(".json")])