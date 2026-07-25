"""Aperçu des layouts en mode dev : PNG dans ./out/, aucune dépendance matérielle.

    python -m zephyr.preview            # les 3 variantes
    python -m zephyr.preview --layout b
    python -m zephyr.preview --stale    # simule une source en échec
"""
from __future__ import annotations

import argparse
from pathlib import Path

from .fake_data import make_snapshot
from .render import layout_a, layout_b, layout_c, layout_d
from .render.common import finalize

LAYOUTS = {"a": layout_a, "b": layout_b, "c": layout_c, "d": layout_d}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--layout", default="all", choices=[*LAYOUTS, "all"])
    ap.add_argument("--stale", action="store_true",
                    help="active l'indicateur « données périmées »")
    ap.add_argument("--out", default="out", help="dossier de sortie (défaut : ./out)")
    args = ap.parse_args()

    outdir = Path(args.out)
    outdir.mkdir(parents=True, exist_ok=True)
    snap = make_snapshot(stale=args.stale)

    keys = list(LAYOUTS) if args.layout == "all" else [args.layout]
    for key in keys:
        img = finalize(LAYOUTS[key].render(snap))
        path = outdir / f"layout_{key}{'_stale' if args.stale else ''}.png"
        img.save(path)
        print(path)


if __name__ == "__main__":
    main()
