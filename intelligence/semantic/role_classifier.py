# -*- coding: utf-8 -*-
"""
Role Classifier — hybrid heuristic + LLM semantic role classification.
Main entry point for assigning semantic roles to document objects.
"""

import logging
from typing import Optional

from intelligence.graph.document_graph import (
    DocumentObject,
    DocumentObjectGraph,
    SemanticRole,
)
from intelligence.semantic.heuristics import HeuristicClassifier
from intelligence.semantic.role_registry import RoleRegistry


logger = logging.getLogger(__name__)


class RoleClassifier:
    """Hybrid semantic role classifier.

    Strategy:
    1. Run heuristic classifier first (fast, no LLM).
    2. For objects below confidence threshold, use LLM (if available).
    3. Fallback to UNKNOWN role for remaining objects.
    """

    def __init__(self, llm_provider=None):
        """
        Args:
            llm_provider: Optional LLM provider for low-confidence classifications.
                          If None, uses heuristics only.
        """
        self._heuristic = HeuristicClassifier()
        self._llm = llm_provider

    def classify_graph(self, graph: DocumentObjectGraph) -> DocumentObjectGraph:
        """Classify ALL objects in a document graph.

        Returns:
            Graph with semantic_role and role_confidence set on each object.
        """
        objects = list(graph.all_objects.values())

        # Phase 1: Heuristic classification
        heuristic_results = self._heuristic.classify_batch(objects)

        # Apply heuristic results
        low_confidence_objects = []
        for obj in objects:
            if obj.id in heuristic_results:
                role, confidence = heuristic_results[obj.id]
                obj.semantic_role = role
                obj.role_confidence = confidence
            else:
                low_confidence_objects.append(obj)

        # Phase 2: LLM classification for low-confidence objects
        if self._llm and low_confidence_objects:
            llm_results = self._llm_classify(low_confidence_objects)
            for obj_id, (role, confidence) in llm_results.items():
                obj = graph.get_object(obj_id)
                if obj:
                    obj.semantic_role = role
                    obj.role_confidence = confidence

        # Phase 3: Assign PARAGRAPH to any remaining UNKNOWN translatable objects
        for obj in graph.all_objects.values():
            if obj.semantic_role == SemanticRole.UNKNOWN and obj.original_text.strip():
                obj.semantic_role = SemanticRole.PARAGRAPH
                obj.role_confidence = 0.50

        logger.info(
            f"Role classification complete: "
            f"{sum(1 for o in graph.all_objects.values() if o.semantic_role != SemanticRole.UNKNOWN)}/"
            f"{len(graph.all_objects)} objects classified"
        )

        return graph

    def _llm_classify(
        self, objects: list[DocumentObject]
    ) -> dict[str, tuple[SemanticRole, float]]:
        """Use LLM to classify low-confidence objects.

        Batches objects by page for efficiency.
        """
        if not self._llm or not objects:
            return {}

        # Group by page
        by_page: dict[int, list[DocumentObject]] = {}
        for obj in objects:
            by_page.setdefault(obj.page_number, []).append(obj)

        results = {}
        for page_num, page_objects in by_page.items():
            try:
                batch_results = self._llm_classify_page(page_objects, page_num)
                results.update(batch_results)
            except Exception as e:
                logger.warning(f"LLM role classification failed for page {page_num}: {e}")

        return results

    def _llm_classify_page(
        self, objects: list[DocumentObject], page_num: int
    ) -> dict[str, tuple[SemanticRole, float]]:
        """Classify a batch of objects on the same page using LLM."""
        if not self._llm:
            return {}

        # Build prompt with object context
        prompt_lines = []
        for obj in objects:
            prompt_lines.append(
                f"Object {obj.id}: \"{obj.original_text[:100]}\" "
                f"(type: {obj.object_type.name})"
            )
        prompt = "\n".join(prompt_lines)

        system_prompt = (
            "You are a document analyzer. Classify each text object's semantic role "
            "in an educational document. Choose from:\n"
            "- LEARNING_OBJECTIVE: Statements of learning goals\n"
            "- INSTRUCTION: Directions, instructions to students\n"
            "- QUESTION_STEM: A numbered or standalone question\n"
            "- MULTIPLE_CHOICE_OPTION: Answer choices labeled A-D\n"
            "- ANSWER_BLANK: Underscore blanks for answers\n"
            "- ANSWER_KEY: Answer key showing correct choices\n"
            "- HEADING_1/HEADING_2: Section headings\n"
            "- PARAGRAPH: Body text\n"
            "- CAPTION: Figure/table captions\n"
            "- FOOTER_TEXT: Page footers\n"
            "- HEADER_TEXT: Page headers\n"
            "- CITATION: Academic citations\n"
            "- HYPERLINK_TEXT: URLs\n"
            "Return JSON mapping object_id to role name with confidence."
        )

        try:
            result = self._llm.analyze(system_prompt, prompt)
            parsed = {}
            for obj_id, data in result.items():
                if isinstance(data, dict):
                    role_name = data.get("role", "PARAGRAPH")
                    confidence = float(data.get("confidence", 0.6))
                    try:
                        role = SemanticRole[role_name]
                    except (KeyError, ValueError):
                        role = SemanticRole.PARAGRAPH
                    parsed[obj_id] = (role, confidence)
            return parsed
        except Exception as e:
            logger.error(f"LLM classification error: {e}")
            return {}