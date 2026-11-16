"""Build every deck: content module -> Markdown source + PPTX.

Run from the repository root:
    .\\.venv\\Scripts\\python.exe presentations\\build_decks.py
"""

from __future__ import annotations

import importlib
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from deckbuild import render_deck, render_markdown  # noqa: E402
from pptx import Presentation  # noqa: E402

DECKS = [
    "content.plan_v1",
    "content.requirements_design",
    "content.status_03",
    "content.sprint01_review",
    "content.sprint01_retro",
    "content.sprint02_review",
    "content.sprint02_retro",
]


def main() -> int:
    source_dir = ROOT / "source"
    output_dir = ROOT
    built: list[str] = []
    for module_name in DECKS:
        module = importlib.import_module(module_name)
        deck = module.DECK
        markdown_path = render_markdown(deck, source_dir / f"{deck['slug']}.md")
        pptx_path = render_deck(deck, output_dir / f"{deck['slug']}.pptx")
        built.append(f"{pptx_path.name} ({len(Presentation(pptx_path).slides)} slides)")
        print(f"built {markdown_path.relative_to(ROOT.parent)} and "
              f"{pptx_path.relative_to(ROOT.parent)}")
    print("\n".join(["", "Decks built:"] + [f"  - {item}" for item in built]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
