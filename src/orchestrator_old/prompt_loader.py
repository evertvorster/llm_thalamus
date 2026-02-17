from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass
class PromptLoader:
    base_dir: Path
    _cache: dict[str, str]

    def load(self, name: str) -> str:
        """
        Load a prompt file by name. Name may be:
          - "final" (resolved to "<base_dir>/final.txt")
          - "some/path.txt" (resolved to "<base_dir>/some/path.txt" if it contains a '/')
        """
        key = name.strip()
        if not key:
            raise ValueError("prompt name is empty")

        # default extension if caller passes "final"
        rel = Path(key)
        if "/" not in key and rel.suffix == "":
            rel = rel.with_suffix(".txt")

        p = (self.base_dir / rel).resolve()

        # Ensure prompts are within base_dir (no escaping)
        try:
            p.relative_to(self.base_dir.resolve())
        except Exception as e:
            raise ValueError(f"prompt path escapes base_dir: {p}") from e

        cache_key = str(p)
        if cache_key in self._cache:
            return self._cache[cache_key]

        if not p.exists():
            raise FileNotFoundError(f"missing prompt file: {p}")

        text = p.read_text(encoding="utf-8")
        self._cache[cache_key] = text
        return text

    def render(self, name: str, **vars: str) -> str:
        """
        Load + format a prompt with .format(**vars).
        Keep placeholders explicit; missing keys should fail loudly.
        """
        template = self.load(name)
        return template.format(**vars)


def build_prompt_loader(resources_root: Path) -> PromptLoader:
    return PromptLoader(base_dir=(resources_root / "prompts"), _cache={})
