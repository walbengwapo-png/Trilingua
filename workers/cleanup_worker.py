# -*- coding: utf-8 -*-
"""
Cleanup Worker — removes temporary files and expired checkpoints.
Designed to run as a scheduled task.
"""

import logging
import os
import shutil
import time
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)


class CleanupWorker:
    """Removes temporary files and expired checkpoints."""

    # Default TTLs in hours
    TEMP_FILE_TTL = 24  # Temp files older than 24h
    CHECKPOINT_TTL = 48  # Checkpoints older than 48h

    def __init__(self, temp_dir: str = None, checkpoint_base_dir: str = None):
        self.temp_dir = temp_dir or os.environ.get(
            "TRILINGUA_TEMP_DIR",
            os.path.join(os.environ.get("TEMP", "/tmp"), "trilingua"),
        )

    def cleanup_temp_files(self, max_age_hours: int = None) -> int:
        """Remove expired temp files.

        Args:
            max_age_hours: Max age in hours before deletion.

        Returns:
            Number of files deleted.
        """
        max_age = max_age_hours or self.TEMP_FILE_TTL
        cutoff = datetime.now() - timedelta(hours=max_age)
        deleted = 0

        if not os.path.exists(self.temp_dir):
            return 0

        for root, dirs, files in os.walk(self.temp_dir):
            for fname in files:
                fpath = os.path.join(root, fname)
                try:
                    mtime = datetime.fromtimestamp(os.path.getmtime(fpath))
                    if mtime < cutoff:
                        os.remove(fpath)
                        deleted += 1
                except (OSError, IOError) as e:
                    logger.warning(f"Failed to remove {fpath}: {e}")

            # Remove empty directories
            for dname in dirs:
                dpath = os.path.join(root, dname)
                try:
                    if not os.listdir(dpath):
                        os.rmdir(dpath)
                except (OSError, IOError):
                    pass

        if deleted > 0:
            logger.info(f"Cleanup: removed {deleted} expired temp files")

        return deleted

    def cleanup_checkpoints(self, max_age_hours: int = None) -> int:
        """Remove expired checkpoint directories.

        Args:
            max_age_hours: Max age in hours before deletion.

        Returns:
            Number of checkpoint directories removed.
        """
        max_age = max_age_hours or self.CHECKPOINT_TTL
        cutoff = datetime.now() - timedelta(hours=max_age)
        removed = 0

        if not os.path.exists(self.temp_dir):
            return 0

        checkpoints_dir = os.path.join(self.temp_dir)
        for job_id in os.listdir(checkpoints_dir):
            job_dir = os.path.join(checkpoints_dir, job_id)
            if not os.path.isdir(job_dir):
                continue

            try:
                mtime = datetime.fromtimestamp(os.path.getmtime(job_dir))
                if mtime < cutoff:
                    shutil.rmtree(job_dir, ignore_errors=True)
                    removed += 1
            except (OSError, IOError) as e:
                logger.warning(f"Failed to remove checkpoint dir {job_dir}: {e}")

        if removed > 0:
            logger.info(f"Cleanup: removed {removed} expired checkpoint directories")

        return removed

    def run_cleanup(self) -> dict:
        """Run all cleanup tasks. Returns summary."""
        temp_deleted = self.cleanup_temp_files()
        checkpoint_removed = self.cleanup_checkpoints()

        return {
            "temp_files_deleted": temp_deleted,
            "checkpoint_dirs_removed": checkpoint_removed,
            "timestamp": datetime.now().isoformat(),
        }