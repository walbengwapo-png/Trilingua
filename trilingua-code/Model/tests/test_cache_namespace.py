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


def test_document_outer_cache_cannot_serve_a_legacy_unversioned_result(tmp_path, document_pipeline, monkeypatch):
    import pipeline.document_pipeline as module
    path = str(tmp_path/'document-cache.db')
    old = SQLiteTranslationCache(db_path=path)
    old.put('Close the form.', 'Cebuano', document_pipeline.translation_pipeline.provider.name,
            'Old incorrect result', source_lang='English')
    old.flush()
    monkeypatch.setattr(module, '_TRANSLATION_CACHE_ENABLED', True)
    monkeypatch.setattr(module, 'SQLiteTranslationCache', lambda **kwargs: SQLiteTranslationCache(db_path=path, **kwargs))
    current = document_pipeline._get_cache()
    assert current.get('Close the form.', 'Cebuano', document_pipeline.translation_pipeline.provider.name,
                       source_lang='English') is None
