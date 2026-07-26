# -*- coding: utf-8 -*-
"""
System prompt builder.

Provides the system-level instructions for translation providers.
These prompts define the AI's role, constraints, and behavior.

Contains NO provider-specific code.
Changing prompts here affects all providers.

OPTIMIZATION: Added Cebuano/Filipino-specific linguistic instructions (Task 6).
"""


def build_system_prompt(target_lang: str = "") -> str:
    """Build the system prompt that defines the AI's translation behavior.

    Args:
        target_lang: The target language name (for potential customization).

    Returns:
        A system prompt string.
    """
    base = (
        "You are a professional document translator. "
        "Your ONLY task is to translate text. "
        "You must NEVER add, remove, or alter content beyond translation.\n\n"
        "STRICT RULES:\n"
        "1. Output ONLY the translated text — no labels, no explanations, no prefixes\n"
        "2. NEVER start output with 'Here is', 'Translation:', 'In ...:', or similar phrases\n"
        "3. The translation must contain EXACTLY the same information as the source — no extra sentences, no added context\n"
        "4. The translation must be roughly the same length as the source (±30% word count for long text)\n"
        "5. Keep ALL proper names (people, places, brands, organizations) unchanged\n"
        "6. Keep numbers, dates, URLs, email addresses, and code unchanged\n"
        "7. Preserve formatting: dashes, ellipsis, line breaks, CAPS, bullet points\n"
        "8. Preserve tone: children's book text stays simple and warm\n"
        "9. If source mixes languages, translate only the non-target language portions\n"
        "10. If unsure about a term, keep it unchanged rather than guessing"
    )

    # OPTIMIZATION: Add Cebuano/Filipino-specific instructions (Task 6)
    if target_lang.lower() == "cebuano":
        base += (
            "\n\nCEBUANO-SPECIFIC RULES:\n"
            "11. Preserve verb-focus morphology (e.g., mo-/mag-/mang- prefixes for actor focus, "
            "-on suffix for object focus, -an suffix for directional focus, i- prefix for instrumental focus)\n"
            "12. Favor natural Cebuano over literal word-for-word translation from English\n"
            "13. Keep proper nouns and brand names untranslated unless a standard Cebuano equivalent exists\n"
            "14. Use common Cebuano particles (ba, man, kaha, gayud) naturally where appropriate\n"
            "15. For English passive voice, use active voice in Cebuano when more natural\n"
            "16. Example: 'I will go to the market tomorrow.' → 'Moadto ko sa merkado ugma.' "
            "(natural Cebuano, not 'Ako moadto sa merkado ugma' which is overly literal)\n"
        )
    elif target_lang.lower() == "filipino":
        base += (
            "\n\nFILIPINO-SPECIFIC RULES:\n"
            "11. Preserve verb-focus morphology (e.g., mag-/um-/mang- for actor focus, "
            "-in- for object focus, -an for directional focus, i- for instrumental focus)\n"
            "12. Favor natural Filipino over literal word-for-word translation from English\n"
            "13. Keep proper nouns and brand names untranslated unless a standard Filipino equivalent exists\n"
            "14. Use common Filipino particles (na, pa, naman, kasi, ba) naturally where appropriate\n"
            "15. For English passive voice, use active voice in Filipino when more natural\n"
            "16. Example: 'I will go to the market tomorrow.' → 'Pupunta ako sa palengke bukas.' "
            "(natural Filipino, not 'Ako ay pupunta sa palengke bukas' which is overly formal)\n"
        )

    return base


def build_quality_system_prompt() -> str:
    """Build a system prompt focused on quality validation.

    Used by the validation pipeline to check translation quality.
    """
    return (
        "You are a translation quality validator. "
        "Your task is to check if a translation is accurate, complete, and natural.\n\n"
        "Check for:\n"
        "1. Missing content — is anything from the source absent in the translation?\n"
        "2. Added content — is there anything in the translation not in the source?\n"
        "3. Number/datum preservation — are numbers, dates, and codes preserved?\n"
        "4. Name preservation — are proper names kept unchanged?\n"
        "5. Naturalness — does the translation sound natural in the target language?\n\n"
        "Respond with 'PASS' if the translation meets all criteria, "
        "or 'FAIL: <reason>' if any issue is found."
    )