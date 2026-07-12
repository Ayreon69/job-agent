"""Tests for scoring/geography.py, covering every case from check_geography_rules_spec.md."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scoring.geography import check_geography_rules

CASES = [
    ("Genève, Suisse", "suisse_romande", 1, True),
    ("Zurich (ZH)", "suisse_autre", 4, True),
    ("Lyon 3e arrondissement", "rhone_alpes", 2, False),
    ("Civrieux (01)", "rhone_alpes", 2, False),
    ("Bourgoin-Jallieu (38300)", "rhone_alpes", 2, False),
    ("Villefranche-sur-Saône, 69400", "rhone_alpes", 2, False),
    ("Dubai, UAE", "uae_gcc", 3, True),
    ("Paris 8e", "autre_france", None, False),
    ("Suisse", "inconnu", None, False),
    ("Full remote", "inconnu", None, False),
    ("Fribourg", "suisse_romande", 1, True),
    # Correctif session 11 (scraping jobup.ch réel) : villes vaudoises/
    # neuchâteloises réelles absentes de SUISSE_ROMANDE_VILLES à l'origine,
    # découvert par un scraping réel (4/34 offres mal classées avant
    # correctif — voir ROADMAP.md).
    ("Gland", "suisse_romande", 1, True),
    ("Renens VD", "suisse_romande", 1, True),
    ("Palézieux", "suisse_romande", 1, True),
    ("Marin-Epagnier (NE)", "suisse_romande", 1, True),
    # Repli abréviation cantonale (SUISSE_ROMANDE_CANTON_ABBR_RE) pour une
    # commune non énumérée explicitement — le mécanisme générique, pas
    # seulement les 4 villes ci-dessus qui ont aussi été ajoutées en dur.
    ("Villaz-Saint-Pierre FR", "suisse_romande", 1, True),
    # Non-régression : une abréviation cantonale suisse-alémanique connue ne
    # doit jamais être classée romande — la ville connue (suisse_autre) doit
    # gagner avant que le repli cantonal romand ne soit même consulté.
    ("Winterthur ZH", "suisse_autre", 4, True),
]


def main() -> None:
    failures = 0
    for location, expected_zone, expected_rank, expected_mobility in CASES:
        verdict = check_geography_rules(location)
        ok = (
            verdict.zone == expected_zone
            and verdict.priority_rank == expected_rank
            and verdict.mobility_signal_allowed == expected_mobility
        )
        status = "OK" if ok else "FAIL"
        if not ok:
            failures += 1
        print(
            f"[{status}] {location!r:40} -> zone={verdict.zone!r} rank={verdict.priority_rank} "
            f"mobility={verdict.mobility_signal_allowed} method={verdict.match_method} "
            f"matched={verdict.matched_keyword!r}"
        )
        if not ok:
            print(f"       attendu: zone={expected_zone!r} rank={expected_rank} mobility={expected_mobility}")

    print(f"\n{len(CASES) - failures}/{len(CASES)} cas passés")
    if failures:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
