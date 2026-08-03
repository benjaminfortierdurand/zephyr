"""Variante C « Contraste » : bandeau supérieur en négatif, graphique très large,
jours avec pastilles noires."""
from __future__ import annotations

from PIL import Image

from ..models import Snapshot
from .common import (BLACK, HEIGHT, WHITE, WIDTH, JOURS_ABR, MOIS, draw_day_cell,
                     draw_hourly_chart, draw_legend, draw_stale_badge,
                     draw_trend_arrow, font, fr_num, new_canvas, text_w)

HDR_H = 96


def render(snap: Snapshot) -> Image.Image:
    img, d = new_canvas()
    cur, now = snap.current, snap.generated_at

    # --- bandeau noir -----------------------------------------------------
    d.rectangle((0, 0, WIDTH, HDR_H), fill=BLACK)

    d.text((20, 6), fr_num(cur.temp) + "°", font=font(70, bold=True), fill=WHITE)

    d.text((330, 12), f"{cur.humidity} %", font=font(30, bold=True), fill=WHITE)
    d.text((330, 62), "humidité", font=font(13, bold=True), fill=WHITE)

    press_s = f"{fr_num(cur.pressure, 0)} hPa"
    f_press = font(30, bold=True)
    d.text((460, 12), press_s, font=f_press, fill=WHITE)
    draw_trend_arrow(d, 460 + text_w(d, press_s, f_press) + 22, 30, 20,
                     cur.pressure_trend, fill=WHITE)
    d.text((460, 62), "pression · 3 h", font=font(13, bold=True), fill=WHITE)

    date_s = f"{JOURS_ABR[now.weekday()]} {now.day} {MOIS[now.month - 1]}"
    d.text((WIDTH - 18, 12), date_s, font=font(21, bold=True), fill=WHITE, anchor="ra")
    d.text((WIDTH - 18, 44), f"mis à jour à {now:%H:%M}", font=font(14, bold=True),
           fill=WHITE, anchor="ra")
    if snap.stale:
        draw_stale_badge(d, WIDTH - 18, 66, snap.stale_since, inverse=True,
                         source=snap.stale_source)

    # --- graphique 24 h ---------------------------------------------------
    d.text((20, 106), "PROCHAINES 24 H", font=font(15, bold=True), fill=BLACK)
    draw_legend(d, WIDTH - 18, 107,
                [("line", "température"), ("bar", "pluie"),
                 ("dots", "rafales")])
    draw_hourly_chart(d, (18, 132, WIDTH - 18, 326), snap.hourly)

    # --- 7 jours (pastilles) ----------------------------------------------
    d.line((16, 340, WIDTH - 16, 340), fill=BLACK, width=1)
    xs = [14 + round(i * (WIDTH - 28) / 7) for i in range(8)]
    for i, day in enumerate(snap.daily):
        draw_day_cell(d, (xs[i], 352, xs[i + 1], HEIGHT - 6), day, now.date(),
                      chip=True)

    return img
