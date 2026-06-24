"""
Shared fixtures for search tool tests.
"""
import pytest
from pathlib import Path


@pytest.fixture
def tmp_kb(tmp_path: Path):
    """Creates a temporary knowledge base with Blum-related content."""
    (tmp_path / "blum_compendium.md").write_text(
        """# Szuflady Blum

## Tandembox Antaro
Klasyczny system szufladowy. Prowadnice widoczne.

## Merivobox
Złoty standard na 2026. Prowadnica ukryta.

## Legrabox
Premium. Szklane ścianki boczne.
""",
        encoding="utf-8",
    )
    (tmp_path / "standards.md").write_text(
        """# Standardy materiałowe

- Zawiasy: Blum Clip Top Blumotion
- Szuflady: Blum Merivobox lub Tandembox Antaro
- Podnośniki: Blum Aventos HF
""",
        encoding="utf-8",
    )
    (tmp_path / "playbook.md").write_text(
        """# Playbook

## Montaż
Fronty, szuflady, AGD — 12:30-15:00

## Okucia
Koszt okuć Blum komplet: 1500-2000 zł
""",
        encoding="utf-8",
    )
    return tmp_path
