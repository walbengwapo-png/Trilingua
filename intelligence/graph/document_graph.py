# -*- coding: utf-8 -*-
"""
Document Object Graph — Canonical document representation.
This is the CENTRAL data structure all components operate on.
Format adapters produce it. Semantic analysis annotates it.
Context engine queries it. Translation engine modifies it.
Reconstructor consumes it.
"""

from dataclasses import dataclass, field, asdict
from typing import Optional, Any
from enum import Enum, auto


# ── Enums ──────────────────────────────────────────────────────────────


class ObjectType(Enum):
    """Physical type of a document object."""
    TEXT = auto()
    TABLE = auto()
    IMAGE = auto()
    SHAPE = auto()
    TEXTBOX = auto()
    HEADER = auto()
    FOOTER = auto()
    PAGE_NUMBER = auto()
    LIST_ITEM = auto()
    HYPERLINK = auto()


class SemanticRole(Enum):
    """Semantic purpose/role of a document object in its context."""

    # Educational document roles
    LEARNING_OBJECTIVE = auto()
    INSTRUCTION = auto()
    QUESTION_STEM = auto()
    MULTIPLE_CHOICE_OPTION = auto()
    ANSWER_BLANK = auto()
    ANSWER_KEY = auto()
    WORKSHEET_TITLE = auto()

    # Structural roles
    HEADING_1 = auto()
    HEADING_2 = auto()
    HEADING_3 = auto()
    PARAGRAPH = auto()
    CAPTION = auto()
    TABLE_HEADER = auto()
    TABLE_CELL = auto()
    FOOTER_TEXT = auto()
    HEADER_TEXT = auto()
    PAGE_NUMBER_TEXT = auto()

    # Reference roles
    FIGURE_REFERENCE = auto()
    TABLE_REFERENCE = auto()
    CITATION = auto()
    HYPERLINK_TEXT = auto()
    GLOSSARY_TERM = auto()
    REFERENCE_ENTRY = auto()

    # Fallback
    UNKNOWN = auto()


class ObjectRelationType(Enum):
    """Type of relationship between two document objects."""
    PARENT = auto()
    CHILD = auto()
    NEXT_SIBLING = auto()
    PREV_SIBLING = auto()
    GROUP_MEMBER = auto()
    CROSS_REFERENCE = auto()
    CONTINUATION = auto()


# ── Position / Bounding Box ──────────────────────────────────────────


@dataclass
class BoundingBox:
    """Position on the page in points (1/72 inch)."""
    x0: float = 0.0
    y0: float = 0.0
    x1: float = 0.0
    y1: float = 0.0

    @property
    def width(self) -> float:
        return self.x1 - self.x0

    @property
    def height(self) -> float:
        return self.y1 - self.y0

    @property
    def center_x(self) -> float:
        return (self.x0 + self.x1) / 2

    @property
    def center_y(self) -> float:
        return (self.y0 + self.y1) / 2

    def intersects(self, other: "BoundingBox") -> bool:
        """Check if this bbox intersects another."""
        return not (
            self.x1 < other.x0
            or self.x0 > other.x1
            or self.y1 < other.y0
            or self.y0 > other.y1
        )

    def to_dict(self) -> dict:
        return {"x0": self.x0, "y0": self.y0, "x1": self.x1, "y1": self.y1}


# ── Style Information ────────────────────────────────────────────────


@dataclass
class TextStyle:
    """Text formatting/style attributes."""
    font_family: str = "helv"
    font_size: float = 11.0
    bold: bool = False
    italic: bool = False
    underline: bool = False
    color: Optional[int] = None  # RGB integer (0xRRGGBB)
    alignment: Optional[str] = None  # "left", "center", "right", "justify"
    line_spacing: Optional[float] = None
    character_spacing: Optional[float] = None

    def to_dict(self) -> dict:
        return {
            "font_family": self.font_family,
            "font_size": self.font_size,
            "bold": self.bold,
            "italic": self.italic,
            "underline": self.underline,
            "color": self.color,
            "alignment": self.alignment,
            "line_spacing": self.line_spacing,
            "character_spacing": self.character_spacing,
        }


# ── Document Objects ─────────────────────────────────────────────────


@dataclass
class DocumentObject:
    """A single object in the document. The atomic unit of processing."""
    id: str  # Unique within document (e.g., "page_3_obj_14")
    object_type: ObjectType
    semantic_role: SemanticRole = SemanticRole.UNKNOWN
    role_confidence: float = 0.0  # 0.0 - 1.0
    original_text: str = ""
    translated_text: str = ""
    bbox: Optional[BoundingBox] = None
    style: TextStyle = field(default_factory=TextStyle)
    page_number: int = 0
    layer: int = 0  # Z-order (0 = background, 1+ = foreground)
    reading_order: int = 0  # Position in reading sequence
    metadata: dict[str, Any] = field(default_factory=dict)

    # Structure preservation
    format_markers: dict[str, str] = field(default_factory=dict)
    """Preserved structural elements, e.g.:
       {"answer_blank": "______", "number_prefix": "1.", "choice_letter": "A"}"""

    def is_translatable(self) -> bool:
        """Whether this object should be sent to the LLM."""
        return self.semantic_role not in (
            SemanticRole.ANSWER_BLANK,
        )

    @property
    def word_count(self) -> int:
        return len(self.original_text.split())

    @property
    def char_count(self) -> int:
        return len(self.original_text)

    def to_dict(self) -> dict:
        """Serialize to JSON-safe dict for checkpointing."""
        return {
            "id": self.id,
            "object_type": self.object_type.name,
            "semantic_role": self.semantic_role.name,
            "role_confidence": self.role_confidence,
            "original_text": self.original_text,
            "translated_text": self.translated_text,
            "bbox": self.bbox.to_dict() if self.bbox else None,
            "style": self.style.to_dict(),
            "page_number": self.page_number,
            "layer": self.layer,
            "reading_order": self.reading_order,
            "metadata": self.metadata,
            "format_markers": self.format_markers,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "DocumentObject":
        """Deserialize from dict."""
        obj = cls(
            id=data["id"],
            object_type=ObjectType[data["object_type"]],
            semantic_role=SemanticRole[data.get("semantic_role", "UNKNOWN")],
            role_confidence=data.get("role_confidence", 0.0),
            original_text=data.get("original_text", ""),
            translated_text=data.get("translated_text", ""),
            page_number=data.get("page_number", 0),
            layer=data.get("layer", 0),
            reading_order=data.get("reading_order", 0),
            metadata=data.get("metadata", {}),
            format_markers=data.get("format_markers", {}),
        )
        if data.get("bbox"):
            obj.bbox = BoundingBox(**data["bbox"])
        if data.get("style"):
            obj.style = TextStyle(**data["style"])
        return obj


# ── Object Relations ─────────────────────────────────────────────────


@dataclass
class ObjectRelation:
    """A relationship between two objects in the document."""
    source_id: str
    target_id: str
    relation_type: ObjectRelationType
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "source_id": self.source_id,
            "target_id": self.target_id,
            "relation_type": self.relation_type.name,
            "metadata": self.metadata,
        }


# ── Object Groups ────────────────────────────────────────────────────


@dataclass
class ObjectGroup:
    """A semantic group of objects (e.g., question + options)."""
    id: str
    group_type: str  # "question_group", "section", "list"
    member_ids: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "group_type": self.group_type,
            "member_ids": self.member_ids,
            "metadata": self.metadata,
        }


# ── Page ─────────────────────────────────────────────────────────────


@dataclass
class Page:
    """A single page in the document."""
    number: int
    width: float = 612.0  # Points (default US Letter)
    height: float = 792.0  # Points (default US Letter)
    objects: dict[str, DocumentObject] = field(default_factory=dict)
    """object_id → DocumentObject. Maintained as dict for O(1) lookup."""

    def get_reading_order(self) -> list[DocumentObject]:
        """Return objects sorted by reading order."""
        return sorted(
            self.objects.values(),
            key=lambda o: (o.reading_order, o.bbox.center_y if o.bbox else 0),
        )

    def add_object(self, obj: DocumentObject) -> None:
        """Add an object to this page."""
        self.objects[obj.id] = obj

    def remove_object(self, object_id: str) -> Optional[DocumentObject]:
        """Remove and return an object from this page."""
        return self.objects.pop(object_id, None)

    def to_dict(self) -> dict:
        return {
            "number": self.number,
            "width": self.width,
            "height": self.height,
            "objects": [o.to_dict() for o in self.objects.values()],
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Page":
        page = cls(
            number=data["number"],
            width=data.get("width", 612.0),
            height=data.get("height", 792.0),
        )
        for obj_data in data.get("objects", []):
            obj = DocumentObject.from_dict(obj_data)
            page.objects[obj.id] = obj
        return page


# ── Document Graph ───────────────────────────────────────────────────


class DocumentObjectGraph:
    """The canonical representation of a document.

    This is the CENTRAL data structure that all components operate on.
    Format adapters produce it. Semantic analysis annotates it.
    Context engine queries it. Translation engine modifies it.
    Reconstructor consumes it.
    """

    def __init__(
        self,
        document_id: str = "",
        filename: str = "",
        file_format: str = "",
    ):
        self.document_id = document_id
        self.filename = filename
        self.file_format = file_format  # "docx", "pdf", "pptx", etc.

        # Metadata
        self.metadata: dict[str, Any] = {
            "title": "",
            "author": "",
            "total_pages": 0,
            "total_objects": 0,
            "source_lang": "",
            "target_lang": "",
            "created_at": "",
        }

        # Structure
        self.pages: dict[int, Page] = {}  # page_number → Page

        # Global lookups
        self.all_objects: dict[str, DocumentObject] = {}
        """object_id → DocumentObject (flattened across all pages)"""

        # Relations
        self.relations: list[ObjectRelation] = []

        # Groups
        self.groups: list[ObjectGroup] = []

        # Document-level
        self.glossary: list[str] = []  # Extracted glossary terms
        self.repeated_phrases: list[str] = []  # Phrases appearing 3+ times
        self.errors: list[str] = []  # Warnings/errors from parsing (non-fatal)

    # ── Page Management ──────────────────────────────────────────────

    def add_page(self, page: Page) -> None:
        """Add a page to the graph."""
        self.pages[page.number] = page
        self.metadata["total_pages"] = len(self.pages)
        # Register all objects
        for obj in page.objects.values():
            self.all_objects[obj.id] = obj
        self.metadata["total_objects"] = len(self.all_objects)

    def get_page(self, page_num: int) -> Optional[Page]:
        """Get a page by number."""
        return self.pages.get(page_num)

    # ── Object Queries ──────────────────────────────────────────────

    def get_object(self, object_id: str) -> Optional[DocumentObject]:
        """Get an object by its ID."""
        return self.all_objects.get(object_id)

    def get_objects_by_role(self, role: SemanticRole) -> list[DocumentObject]:
        """Get all objects with a specific semantic role."""
        return [o for o in self.all_objects.values() if o.semantic_role == role]

    def get_objects_by_type(self, obj_type: ObjectType) -> list[DocumentObject]:
        """Get all objects of a specific physical type."""
        return [o for o in self.all_objects.values() if o.object_type == obj_type]

    def get_page_objects(self, page_num: int) -> list[DocumentObject]:
        """Get all objects on a specific page."""
        page = self.pages.get(page_num)
        return list(page.objects.values()) if page else []

    def get_group_objects(self, group_id: str) -> list[DocumentObject]:
        """Get all objects belonging to a group."""
        group = next((g for g in self.groups if g.id == group_id), None)
        if not group:
            return []
        return [self.all_objects[oid] for oid in group.member_ids if oid in self.all_objects]

    def get_neighbors(
        self, object_id: str, distance: int = 1
    ) -> list[DocumentObject]:
        """Get neighboring objects in reading order on the same page."""
        obj = self.all_objects.get(object_id)
        if not obj:
            return []
        page = self.pages.get(obj.page_number)
        if not page:
            return []
        reading_order = page.get_reading_order()
        try:
            idx = next(i for i, o in enumerate(reading_order) if o.id == object_id)
        except StopIteration:
            return []
        start = max(0, idx - distance)
        end = min(len(reading_order), idx + distance + 1)
        return [o for o in reading_order[start:end] if o.id != object_id]

    def get_objects_by_page_window(
        self, page_num: int, window_size: int = 3
    ) -> list[DocumentObject]:
        """Get objects from a range of pages centered on page_num."""
        start_page = max(1, page_num - window_size // 2)
        end_page = page_num + window_size // 2
        result = []
        for pn in range(start_page, end_page + 1):
            result.extend(self.get_page_objects(pn))
        return result

    # ── Group Management ─────────────────────────────────────────────

    def add_group(self, group: ObjectGroup) -> None:
        """Add a semantic group."""
        self.groups.append(group)

    # ── Relation Management ──────────────────────────────────────────

    def add_relation(self, relation: ObjectRelation) -> None:
        """Add a relationship between objects."""
        self.relations.append(relation)

    # ── Validation ─────────────────────────────────────────────────

    def validate_integrity(self) -> list[str]:
        """Validate graph completeness. Returns list of issues."""
        issues = []
        for page in self.pages.values():
            for obj in page.objects.values():
                if obj.id not in self.all_objects:
                    issues.append(
                        f"Page {page.number} has object {obj.id} not in all_objects"
                    )
        for obj_id in self.all_objects:
            obj = self.all_objects[obj_id]
            page = self.pages.get(obj.page_number)
            if page and obj_id not in page.objects:
                issues.append(
                    f"Object {obj_id} references page {obj.page_number} but not found there"
                )
        return issues

    # ── Serialization ────────────────────────────────────────────────

    def to_dict(self) -> dict:
        """Serialize the entire graph to a JSON-safe dict for checkpointing."""
        return {
            "document_id": self.document_id,
            "filename": self.filename,
            "file_format": self.file_format,
            "metadata": self.metadata,
            "pages": [p.to_dict() for p in sorted(self.pages.values(), key=lambda p: p.number)],
            "relations": [r.to_dict() for r in self.relations],
            "groups": [g.to_dict() for g in self.groups],
            "glossary": self.glossary,
            "repeated_phrases": self.repeated_phrases,
            "errors": self.errors,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "DocumentObjectGraph":
        """Deserialize from a dict (checkpoint restore)."""
        graph = cls(
            document_id=data.get("document_id", ""),
            filename=data.get("filename", ""),
            file_format=data.get("file_format", ""),
        )
        graph.metadata = data.get("metadata", {})
        for page_data in data.get("pages", []):
            page = Page.from_dict(page_data)
            graph.pages[page.number] = page
            for obj in page.objects.values():
                graph.all_objects[obj.id] = obj
        for rel_data in data.get("relations", []):
            graph.relations.append(
                ObjectRelation(
                    source_id=rel_data["source_id"],
                    target_id=rel_data["target_id"],
                    relation_type=ObjectRelationType[rel_data["relation_type"]],
                    metadata=rel_data.get("metadata", {}),
                )
            )
        for grp_data in data.get("groups", []):
            graph.groups.append(
                ObjectGroup(
                    id=grp_data["id"],
                    group_type=grp_data["group_type"],
                    member_ids=grp_data.get("member_ids", []),
                    metadata=grp_data.get("metadata", {}),
                )
            )
        graph.glossary = data.get("glossary", [])
        graph.repeated_phrases = data.get("repeated_phrases", [])
        graph.errors = data.get("errors", [])
        return graph

    # ── Memory Estimate ─────────────────────────────────────────────

    def estimate_memory_mb(self) -> float:
        """Estimate memory footprint for this graph."""
        total = 0.0
        for obj in self.all_objects.values():
            total += len(obj.original_text) * 2  # Unicode: 2 bytes/char
            total += 512  # Overhead for dataclass fields
        total += len(self.pages) * 256  # Page overhead
        return total / (1024 * 1024)