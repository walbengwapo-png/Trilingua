# -*- coding: utf-8 -*-
"""
Group Detector — identifies semantic groups of objects.
E.g., question + 4 MC options + answer blank = QuestionGroup.
"""

import logging
from typing import Optional

from intelligence.graph.document_graph import (
    DocumentObject,
    DocumentObjectGraph,
    ObjectGroup,
    ObjectRelation,
    ObjectRelationType,
    SemanticRole,
)

logger = logging.getLogger(__name__)


class GroupDetector:
    """Detects semantic groups of objects in a document graph.

    Groups detected:
    - question_group: Question stem + MC options + answer blank
    - section: Heading + following paragraphs
    - list: Consecutive list items
    """

    def detect_groups(self, graph: DocumentObjectGraph) -> DocumentObjectGraph:
        """Run all group detection strategies on the graph.

        Returns:
            Graph with groups and relations populated.
        """
        self._detect_question_groups(graph)
        self._detect_sections(graph)
        self._detect_lists(graph)
        logger.info(f"Group detection complete: {len(graph.groups)} groups found")
        return graph

    def _detect_question_groups(self, graph: DocumentObjectGraph) -> None:
        """Detect question groups: Question + MC Options + Answer Blank."""
        questions = graph.get_objects_by_role(SemanticRole.QUESTION_STEM)
        mc_options = graph.get_objects_by_role(SemanticRole.MULTIPLE_CHOICE_OPTION)
        blanks = graph.get_objects_by_role(SemanticRole.ANSWER_BLANK)

        if not questions:
            return

        # Sort by page and reading order
        questions.sort(key=lambda o: (o.page_number, o.reading_order))
        mc_options.sort(key=lambda o: (o.page_number, o.reading_order))
        blanks.sort(key=lambda o: (o.page_number, o.reading_order))

        group_id_counter = 0

        for question in questions:
            page_objects = graph.get_page_objects(question.page_number)
            q_idx = next(
                (i for i, o in enumerate(page_objects) if o.id == question.id),
                -1,
            )
            if q_idx < 0:
                continue

            # Look ahead for MC options and blanks on the same page
            group_members = [question.id]
            for offset in range(1, min(10, len(page_objects) - q_idx)):
                candidate = page_objects[q_idx + offset]
                if candidate.semantic_role in (
                    SemanticRole.MULTIPLE_CHOICE_OPTION,
                    SemanticRole.ANSWER_BLANK,
                    SemanticRole.INSTRUCTION,
                ):
                    group_members.append(candidate.id)
                elif candidate.semantic_role == SemanticRole.QUESTION_STEM:
                    break  # Next question starts
                elif candidate.semantic_role in (
                    SemanticRole.HEADING_1,
                    SemanticRole.HEADING_2,
                    SemanticRole.HEADING_3,
                ):
                    break  # New section starts

            if len(group_members) > 1:
                group_id = f"q_{group_id_counter}"
                group_id_counter += 1
                graph.add_group(
                    ObjectGroup(
                        id=group_id,
                        group_type="question_group",
                        member_ids=group_members,
                        metadata={"question_text": question.original_text[:100]},
                    )
                )
                # Add relations
                for member_id in group_members[1:]:
                    graph.add_relation(
                        ObjectRelation(
                            source_id=question.id,
                            target_id=member_id,
                            relation_type=ObjectRelationType.GROUP_MEMBER,
                            metadata={"group": group_id},
                        )
                    )

    def _detect_sections(self, graph: DocumentObjectGraph) -> None:
        """Detect sections: Heading + following content."""
        headings = []
        for role in (SemanticRole.HEADING_1, SemanticRole.HEADING_2, SemanticRole.HEADING_3):
            headings.extend(graph.get_objects_by_role(role))
        headings.sort(key=lambda o: (o.page_number, o.reading_order))

        section_id_counter = 0
        for i, heading in enumerate(headings):
            page_objects = graph.get_page_objects(heading.page_number)
            h_idx = next(
                (j for j, o in enumerate(page_objects) if o.id == heading.id), -1
            )
            if h_idx < 0:
                continue

            # Determine end: next heading or end of page
            next_heading = headings[i + 1] if i + 1 < len(headings) else None
            members = [heading.id]

            for offset in range(1, len(page_objects) - h_idx):
                candidate = page_objects[h_idx + offset]
                if next_heading and candidate.id == next_heading.id:
                    break
                if candidate.semantic_role not in (
                    SemanticRole.HEADING_1,
                    SemanticRole.HEADING_2,
                    SemanticRole.HEADING_3,
                ):
                    members.append(candidate.id)

            if len(members) > 1:
                graph.add_group(
                    ObjectGroup(
                        id=f"sec_{section_id_counter}",
                        group_type="section",
                        member_ids=members,
                        metadata={"heading": heading.original_text[:100]},
                    )
                )
                section_id_counter += 1

    def _detect_lists(self, graph: DocumentObjectGraph) -> None:
        """Detect consecutive list items as a list group."""
        # Detect list items by role
        list_items = [
            o for o in graph.all_objects.values()
            if o.semantic_role == SemanticRole.LIST_ITEM
        ]
        list_items.sort(key=lambda o: (o.page_number, o.reading_order))

        if not list_items:
            return

        list_id_counter = 0
        current_list = [list_items[0].id]

        for i in range(1, len(list_items)):
            prev = list_items[i - 1]
            curr = list_items[i]

            # Same page and consecutive reading order
            if curr.page_number == prev.page_number and (
                curr.reading_order - prev.reading_order <= 2
            ):
                current_list.append(curr.id)
            else:
                if len(current_list) >= 2:
                    graph.add_group(
                        ObjectGroup(
                            id=f"list_{list_id_counter}",
                            group_type="list",
                            member_ids=current_list,
                        )
                    )
                    list_id_counter += 1
                current_list = [curr.id]

        if len(current_list) >= 2:
            graph.add_group(
                ObjectGroup(
                    id=f"list_{list_id_counter}",
                    group_type="list",
                    member_ids=current_list,
                )
            )