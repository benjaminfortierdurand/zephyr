"""Point d'entrée : génère le dashboard et l'affiche sur l'e-ink, ou l'écrit en PNG (--dev).

Exécution one-shot : la récurrence (15 min) est gérée par le timer systemd.

    python -m zephyr.main                  # Pi : collecte + affichage e-ink
    python -m zephyr.main --dev            # poste de travail : PNG dans ./out/
    python -m zephyr.main --dev --fake     # PNG avec données factices, aucun réseau
    python -m zephyr.main --dev --watch 15 # PNG régénéré toutes les 15 min
                                           # (aperçu auto-rechargé : out/preview.html)
"""
from __future__ import annotations

import argparse
import logging
import sys
import time
from pathlib import Path

from .render import layout_a, layout_b, layout_c, layout_d
from .render.common import finalize

LAYOUTS = {"a": layout_a, "b": layout_b, "c": layout_c, "d": layout_d}
log = logging.getLogger("zephyr")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dev", action="store_true",
                    help="écrit un PNG dans ./out/ au lieu de piloter l'écran")
    ap.add_argument("--fake", action="store_true",
                    help="données factices, aucun appel réseau (démo/layout)")
    ap.add_argument("--layout", default="d", choices=list(LAYOUTS))
    ap.add_argument("--watch", type=float, metavar="MIN", default=None,
                    help="avec --dev : régénère le PNG toutes les MIN minutes "
                         "(Ctrl-C pour arrêter)")
    args = ap.parse_args()

    logging.basicConfig(stream=sys.stdout, level=logging.INFO,
                        format="%(levelname)s %(name)s: %(message)s")

    if args.watch is not None and not args.dev:
        ap.error("--watch nécessite --dev (sur le Pi, la récurrence vient du timer systemd)")

    def run_cycle() -> None:
        if args.fake:
            from .fake_data import make_snapshot
            snap = make_snapshot()
        else:
            from .collector import collect
            from .config import load_config
            snap = collect(load_config())

        img = finalize(LAYOUTS[args.layout].render(snap))

        # miroir PNG à chaque cycle, même en mode écran : sert l'aperçu web
        # (zephyr-preview.service) et le diagnostic à distance
        out = Path("out")
        out.mkdir(parents=True, exist_ok=True)
        path = out / "dashboard.png"
        img.save(path)
        if not (out / "preview.html").exists():
            from .devpreview import write_preview_html
            write_preview_html(out)

        if args.dev:
            log.info("dashboard écrit : %s", path)
        else:
            from .display import show
            show(img)

        log.info("cycle terminé (%s)",
                 f"données périmées depuis {snap.stale_since:%H:%M}" if snap.stale
                 else "données fraîches")

    if args.watch is None:
        run_cycle()
        return

    from .devpreview import write_preview_html
    preview = write_preview_html(Path("out"))
    log.info("aperçu auto-rechargé : ouvrir %s dans un navigateur", preview.resolve())
    while True:
        try:
            run_cycle()
        except Exception:
            log.exception("cycle en échec — nouvel essai dans %g min", args.watch)
        try:
            time.sleep(args.watch * 60)
        except KeyboardInterrupt:
            log.info("watch arrêté")
            return


if __name__ == "__main__":
    main()
