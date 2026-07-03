"""Print the DAH_Flawless LLM alignment guide."""

from __future__ import annotations

from pathlib import Path


def main() -> None:
    project_root = Path(__file__).resolve().parents[1]
    guide = project_root / "docs" / "llm_alignment_guide.md"
    print(guide.read_text(encoding="utf-8"))


if __name__ == "__main__":
    main()
