"""Pilotage de l'écran Waveshare 7.5\" e-Paper HAT V2 (epd7in5_V2).

Full refresh à chaque cycle (anti-ghosting), jamais de partial refresh,
puis mise en veille de l'écran entre deux rafraîchissements.
"""
from __future__ import annotations

import logging

from PIL import Image

log = logging.getLogger(__name__)


def show(img: Image.Image) -> None:
    # import différé : la lib waveshare_epd n'existe que sur le Pi
    from waveshare_epd import epd7in5_V2

    epd = epd7in5_V2.EPD()
    try:
        epd.init()
        epd.display(epd.getbuffer(img))
        log.info("écran rafraîchi (full refresh)")
    finally:
        epd.sleep()
