"""Load Python engine settings from the shared Laravel environment file."""

import os
from pathlib import Path


def load_engine_environment(env_path):
    path = Path(env_path)
    if not path.is_file():
        return
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        key, separator, value = line.strip().partition("=")
        key = key.strip()
        if not separator or not (
            key.startswith((
                "GEMINI_", "OLLAMA_", "GPTOSS_", "TRANSLATION_",
                "ANALYSIS_", "QUALITY_",
            )) or key in ("PYTHON_SERVICE_TOKEN", "APP_ENV")
        ):
            continue
        value = value.strip()
        if value.startswith(('"', "'")):
            quote = value[0]
            end = value.find(quote, 1)
            if end < 0:
                continue
            value = value[1:end]
        else:
            value = value.split(" #", 1)[0].rstrip()
        if value and not os.environ.get(key):
            os.environ[key] = value
