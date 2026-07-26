# -*- coding: utf-8 -*-
"""
Shared test fixtures for translation-layout-quality tests.

This module provides:
- A minimal fitz.Page mock for PDF testing
- A sample DOCX Document factory for DOCX testing
- A small block-list factory for general translation testing
- Fixture discovery for golden test documents
- Mock provider fixtures for regression testing
"""

import os
import pytest
from unittest.mock import MagicMock, Mock
from docx import Document
from docx.shared import Pt, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
import io


FIXTURES_DIR = os.path.join(os.path.dirname(__file__), "fixtures")


def pytest_configure(config):
    """Register custom marks and clean stale bytecode caches.

    Stale ``__pycache__/`` directories on Windows cause Python to load old
    bytecode even after ``.py`` source files are edited.  We remove every
    ``__pycache__/`` under ``Model/`` once before collection to guarantee
    a fresh compile from source.
    """
    import shutil

    model_root = os.path.normpath(os.path.join(os.path.dirname(__file__), ".."))
    for root, dirs, _ in os.walk(model_root):
        if "__pycache__" in dirs:
            shutil.rmtree(os.path.join(root, "__pycache__"), ignore_errors=True)

    config.addinivalue_line(
        "markers",
        "slow: marks tests as slow (e.g. end-to-end pipeline tests that load the NLLB model)",
    )
    config.addinivalue_line(
        "markers",
        "golden: marks tests that run against the golden test set for regression detection",
    )


def pytest_collect_file(parent, file_path):
    """Collect golden test fixture paths."""
    if parent.config.getoption("-k") and "golden" not in parent.config.getoption("-k"):
        return None
    return None


# ── Fixture Discovery ─────────────────────────────────────────────────────────

def _list_fixtures(suffix: str) -> list[str]:
    """List fixture files with the given suffix."""
    if not os.path.isdir(FIXTURES_DIR):
        return []
    return sorted(
        os.path.join(FIXTURES_DIR, f)
        for f in os.listdir(FIXTURES_DIR)
        if f.endswith(suffix) and f.startswith("golden_")
    )


@pytest.fixture(scope="session")
def fixtures_txt():
    """Return paths to all .txt golden fixtures."""
    return _list_fixtures(".txt")


@pytest.fixture(scope="session")
def fixtures_md():
    """Return paths to all .md golden fixtures."""
    return _list_fixtures(".md")


@pytest.fixture(scope="session")
def fixtures_all():
    """Return paths to ALL golden fixtures (txt, md)."""
    return _list_fixtures(".txt") + _list_fixtures(".md")


# ── Mock Providers ────────────────────────────────────────────────────────────

@pytest.fixture
def mock_translation_provider():
    """Return a MockTranslationProvider with zero delay."""
    from .mock_providers import MockTranslationProvider
    return MockTranslationProvider(delay_ms=0.0)


@pytest.fixture
def mock_analysis_provider():
    """Return a MockAnalysisProvider with zero delay."""
    from .mock_providers import MockAnalysisProvider
    return MockAnalysisProvider(delay_ms=0.0)


# ── Pipeline Fixtures ─────────────────────────────────────────────────────────

@pytest.fixture
def translation_pipeline(mock_translation_provider):
    """Build a TranslationPipeline wired to the mock provider."""
    from pipeline.translation_pipeline import TranslationPipeline
    return TranslationPipeline(mock_translation_provider)


@pytest.fixture
def document_pipeline(translation_pipeline, mock_analysis_provider):
    """Build a DocumentPipeline wired to mock providers."""
    from pipeline.document_pipeline import DocumentPipeline
    return DocumentPipeline(
        translation_pipeline,
        ai_analysis_provider=mock_analysis_provider,
    )


# ── Original Fixtures (Preserved) ─────────────────────────────────────────────

@pytest.fixture
def mock_fitz_page():
    """
    Returns a minimal mock of a fitz.Page object with:
    - get_pixmap() method
    - rect attribute (with width and height)
    - get_text() method returning a dict structure
    """
    page = MagicMock()
    
    # Mock rect attribute
    page.rect = MagicMock()
    page.rect.width = 612.0  # Standard US Letter width in points
    page.rect.height = 792.0  # Standard US Letter height in points
    
    # Mock get_pixmap() method
    pixmap = MagicMock()
    pixmap.width = 612
    pixmap.height = 792
    # Mock pixel() method to return white color by default
    pixmap.pixel = MagicMock(return_value=(255, 255, 255))
    page.get_pixmap = MagicMock(return_value=pixmap)
    
    # Mock get_text() method
    page.get_text = MagicMock(return_value={
        "blocks": [
            {
                "type": 0,  # text block
                "bbox": [50, 50, 500, 100],
                "lines": [
                    {
                        "spans": [
                            {
                                "text": "Sample text",
                                "size": 12.0,
                                "color": 0,
                                "flags": 0,
                                "font": "Helvetica"
                            }
                        ]
                    }
                ]
            }
        ]
    })
    
    return page


@pytest.fixture
def sample_docx_factory():
    """
    Returns a factory function that creates a minimal DOCX Document with:
    - Configurable number of paragraphs
    - Optional table
    - Basic formatting (bold, font size, alignment, spacing)
    
    Usage:
        doc = sample_docx_factory(num_paragraphs=3, include_table=True)
    """
    def _create_docx(num_paragraphs=2, include_table=False, 
                     paragraph_texts=None, table_data=None):
        """
        Create a sample DOCX document.
        
        Args:
            num_paragraphs: Number of paragraphs to create
            include_table: Whether to include a table
            paragraph_texts: Optional list of paragraph text strings
            table_data: Optional 2D list for table content [[row1], [row2], ...]
        
        Returns:
            Document object
        """
        doc = Document()
        
        # Add paragraphs
        if paragraph_texts is None:
            paragraph_texts = [f"Paragraph {i+1} text." for i in range(num_paragraphs)]
        
        for i, text in enumerate(paragraph_texts[:num_paragraphs]):
            para = doc.add_paragraph(text)
            
            # Add some formatting variety
            if i == 0:
                para.style = 'Heading 1'
                para.alignment = WD_ALIGN_PARAGRAPH.CENTER
            else:
                para.style = 'Normal'
                para.alignment = WD_ALIGN_PARAGRAPH.LEFT
                para.paragraph_format.space_before = Pt(6)
                para.paragraph_format.space_after = Pt(6)
            
            # Make first run bold
            if para.runs:
                para.runs[0].bold = True
                para.runs[0].font.size = Pt(12)
                para.runs[0].font.color.rgb = RGBColor(0, 0, 0)
        
        # Add table if requested
        if include_table:
            if table_data is None:
                table_data = [
                    ["Header 1", "Header 2", "Header 3"],
                    ["Row 1 Col 1", "Row 1 Col 2", "Row 1 Col 3"],
                    ["Row 2 Col 1", "Row 2 Col 2", "Row 2 Col 3"]
                ]
            
            table = doc.add_table(rows=len(table_data), cols=len(table_data[0]))
            
            for row_idx, row_data in enumerate(table_data):
                for col_idx, cell_text in enumerate(row_data):
                    cell = table.rows[row_idx].cells[col_idx]
                    cell.text = cell_text
                    
                    # Make header row bold
                    if row_idx == 0 and cell.paragraphs:
                        for run in cell.paragraphs[0].runs:
                            run.bold = True
                            run.font.size = Pt(11)
        
        return doc
    
    return _create_docx


@pytest.fixture
def block_list_factory():
    """
    Returns a factory function that creates a list of block dictionaries
    suitable for testing translation components.
    
    Usage:
        blocks = block_list_factory(count=5, block_type='paragraph')
    """
    def _create_blocks(count=3, block_type='paragraph', include_position=False,
                       include_style=True, texts=None):
        """
        Create a list of block dictionaries.
        
        Args:
            count: Number of blocks to create
            block_type: Type of blocks ('paragraph' or 'table_cell')
            include_position: Whether to include position/page fields (for PDF)
            include_style: Whether to include style metadata
            texts: Optional list of text strings for blocks
        
        Returns:
            List of block dictionaries
        """
        blocks = []
        
        if texts is None:
            texts = [f"This is block number {i+1} with some sample text." 
                    for i in range(count)]
        
        for i, text in enumerate(texts[:count]):
            block = {
                "type": block_type,
                "text": text
            }
            
            if include_position:
                # Create non-overlapping vertical positions
                y_start = 50 + (i * 60)
                block["position"] = [50, y_start, 500, y_start + 50]
                block["page"] = 0
            
            if include_style:
                block["style"] = {
                    "font_size": 12.0,
                    "font": "Helvetica",
                    "color": 0,
                    "bold": False
                }
            
            # Add table-specific fields if needed
            if block_type == 'table_cell':
                block["table_index"] = 0
                block["row"] = i // 3  # Assume 3 columns
                block["col"] = i % 3
                block["row_span"] = 1
                block["col_span"] = 1
            
            blocks.append(block)
        
        return blocks
    
    return _create_blocks
