"""The README's pictures exist, and every screenshot in docs/screenshots is used."""

import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]


def test_readme_images_exist_and_screenshots_are_used():
    text = (REPO / "README.md").read_text(encoding="utf-8")
    refs = set(re.findall(r'src="(docs/screenshots/[^"]+)"', text))
    assert refs, "no screenshots in the README"
    for ref in refs:
        assert (REPO / ref).is_file(), ref
    on_disk = {f"docs/screenshots/{f.name}" for f in (REPO / "docs" / "screenshots").glob("*.png")}
    assert on_disk == refs
