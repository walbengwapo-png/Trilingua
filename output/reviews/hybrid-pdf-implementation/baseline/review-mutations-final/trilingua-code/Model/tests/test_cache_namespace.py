from cache.sqlite_cache import SQLiteTranslationCache


def test_cache_namespace_prevents_reusing_a_previous_prompt_result(tmp_path):
    db_path = str(tmp_path / "translations.db")
    old = SQLiteTranslationCache(db_path=db_path, namespace="prompt-v1")
    old.put("Close the form.", "Cebuano", "gemini", "Isira ang porma.", "English")
    old.flush()

    current = SQLiteTranslationCache(db_path=db_path, namespace="prompt-v2")
    assert current.get("Close the form.", "Cebuano", "gemini", "English") is None


def test_same_namespace_reuses_the_cached_translation(tmp_path):
    db_path = str(tmp_path / "translations.db")
    cache = SQLiteTranslationCache(db_path=db_path, namespace="balanced-v1")
    cache.put("Thank you.", "Cebuano", "gemini", "Salamat.", "English")
    cache.flush()

    restarted = SQLiteTranslationCache(db_path=db_path, namespace="balanced-v1")
    assert restarted.get("Thank you.", "Cebuano", "gemini", "English") == "Salamat."
