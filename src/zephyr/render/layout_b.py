"""Variante B « Colonne » : conditions actuelles à gauche, prévisions à droite."""
from __future__ import annotations

from PIL import Image

from ..models import Snapshot
from .common import (BLACK, HEIGHT, WIDTH, JOURS, MOIS, draw_day_cell,
                     draw_hourly_chart, draw_legend, draw_stale_badge,
                     draw_trend_arrow, font, fr_num, new_canvas, text_w)

LEFT_W = 248


def render(snap: Snapshot) -> Image.Image:
    img, d = new_canvas()
    cur, now = snap.current, snap.generated_at
    cx = LEFT_W // 2

    # --- colonne gauche ---------------------------------------------------
    d.line((LEFT_W, 0, LEFT_W, HEIGHT), fill=BLACK, width=2)

    d.text((cx, 18), fr_num(cur.temp) + "°", font=font(80, bold=True),
           fill=BLACK, anchor="ma")
    d.text((cx, 122), "extérieur · Netatmo", font=font(13), fill=BLACK, anchor="ma")

    d.line((28, 152, LEFT_W - 28, 152), fill=BLACK, width=1)

    d.text((cx, 168), f"{cur.humidity} %", font=font(38, bold=True),
           fill=BLACK, anchor="ma")
    d.text((cx, 214), "humidité", font=font(14), fill=BLACK, anchor="ma")

    press_s = f"{fr_num(cur.pressure, 0)} hPa"
    f_press = font(30, bold=True)
    pw = text_w(d, press_s, f_press) + 34
    d.text((cx - pw // 2, 248), press_s, font=f_press, fill=BLACK)
    draw_trend_arrow(d, cx - pw // 2 + pw - 12, 266, 20, cur.pressure_trend)
    d.text((cx, 288), "pression · 3 h", font=font(14), fill=BLACK, anchor="ma")

    d.line((28, 330, LEFT_W - 28, 330), fill=BLACK, width=1)

    d.text((cx, 366), JOURS[now.weekday()], font=font(22, bold=True),
           fill=BLACK, anchor="ma")
    d.text((cx, 396), f"{now.day} {MOIS[now.month - 1]}", font=font(22, bold=True),
           fill=BLACK, anchor="ma")
    d.text((cx, 432), f"mis à jour à {now:%H:%M}", font=font(14),
           fill=BLACK, anchor="ma")
    if snap.stale:
        draw_stale_badge(d, cx + 78, 452, snap.stale_since,
                         source=snap.stale_source)

    # --- graphique 24 h ---------------------------------------------------
    rx0 = LEFT_W + 14
    d.text((rx0, 12), "PROCHAINES 24 H", font=font(15, bold=True), fill=BLACK)
    draw_legend(d, WIDTH - 14, 13,
                [("line", "temp."), ("bar", "pluie"),
                 ("dots", "raf.")])
    draw_hourly_chart(d, (rx0, 40, WIDTH - 14, 282), snap.hourly)

    d.line((LEFT_W, 298, WIDTH, 298), fill=BLACK, width=2)

    # --- 7 jours (compact) ------------------------------------------------
    xs = [LEFT_W + 6 + round(i * (WIDTH - LEFT_W - 14) / 7) for i in range(8)]
    for i, day in enumerate(snap.daily):
        draw_day_cell(d, (xs[i], 310, xs[i + 1], HEIGHT - 6), day, now.date(),
                      compact=True)

    return img
