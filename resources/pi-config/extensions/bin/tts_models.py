#!/opt/coqui-tts/venv/bin/python3
"""List coqui-tts models and their download status.

Output: JSON object {model_uri: bool} where bool is whether cached locally.
"""
import json, sys
from pathlib import Path
from TTS.api import TTS

CACHE = Path.home() / ".local" / "share" / "tts"

def uri_to_cache_dir(uri: str) -> Path:
    return CACHE / uri.replace("/", "--")

models = TTS().list_models()
result = {}
for m in models:
    cached = uri_to_cache_dir(m).is_dir()
    result[m] = cached

json.dump(result, sys.stdout)
