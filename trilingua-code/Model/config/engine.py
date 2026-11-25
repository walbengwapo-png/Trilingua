"""Artifact and cache compatibility revision; deploy with Laravel's matching value."""
import os

DOCUMENT_ENGINE_REVISION = os.environ.get('DOCUMENT_ENGINE_REVISION', '2026-11-25-structure-v3')
