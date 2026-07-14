# -*- coding: utf-8 -*-
"""
Translation prompt builder.

Builds the user message for translation requests.
Contains few-shot examples and language-specific instructions.

Contains NO provider-specific code.
Changing prompts here affects all providers.
"""


def build_translation_prompt(text: str, source_lang: str, target_lang: str,
                             block_type: str = "paragraph") -> str:
    """Build the user prompt for a translation request.

    Args:
        text: The source text to translate.
        source_lang: Source language name (e.g. "English").
        target_lang: Target language name (e.g. "Cebuano").
        block_type: Type of text block (paragraph, header, table_cell, etc.).

    Returns:
        A user prompt string.
    """
    # Map block type to human-readable description
    type_descriptions = {
        "paragraph":  "a body paragraph",
        "header":     "a document header",
        "footer":     "a document footer",
        "text_box":   "a text box",
        "table_cell": "a table cell",
        "heading":    "a document heading",
        "list_item":  "a list item",
    }
    type_desc = type_descriptions.get(block_type, block_type)

    user_msg = f"Translate this {type_desc} from {source_lang} to {target_lang}.\n"

    # Add few-shot examples for Cebuano and Filipino
    if target_lang.lower() in ("cebuano", "filipino"):
        user_msg += f"\nExamples:\n"
        if target_lang.lower() == "cebuano":
            user_msg += (
                "  EN: I am going to the market. → CEB: Moadto ko sa merkado.\n"
                "  EN: What is your name? → CEB: Unsa imong pangalan?\n"
                "  EN: The cat sat on the mat. → CEB: Lingkod ang iring sa banig.\n"
                "  EN: 123 Main Street → CEB: 123 Main Street\n"
            )
        elif target_lang.lower() == "filipino":
            user_msg += (
                "  EN: I am going to the market. → FIL: Pupunta ako sa palengke.\n"
                "  EN: What is your name? → FIL: Ano ang pangalan mo?\n"
                "  EN: The cat sat on the mat. → FIL: Umupo ang pusa sa banig.\n"
                "  EN: 123 Main Street → FIL: 123 Main Street\n"
            )

    user_msg += f"\nSource text:\n{text}"
    return user_msg


def build_validation_prompt(source_text: str, translated_text: str) -> str:
    """Build a prompt to validate a translation.

    Args:
        source_text: The original source text.
        translated_text: The translated text to validate.

    Returns:
        A prompt string for quality validation.
    """
    return (
        f"Source text:\n{source_text}\n\n"
        f"Translation:\n{translated_text}\n\n"
        "Is this translation accurate and complete? "
        "Check: missing content, added content, number preservation, "
        "name preservation, and naturalness. "
        "Respond with 'PASS' or 'FAIL: <reason>'."
    )