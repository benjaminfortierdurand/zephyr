"""Variante D « Épuré » : même contenu que A, moins de traits.

Trois partis pris par rapport à A :
- une hiérarchie en trois zones (héros / pièces / métadonnées) au lieu de quatre
  colonnes de poids voisin, et aucun filet vertical — c'est le blanc qui sépare ;
- la légende disparaît : sans la courbe de rafales il ne reste que la courbe de
  température et les barres de pluie, qui se lisent d'elles-mêmes (le maximum de
  rafales passe en statistique sur la ligne de titre) ;
- grille du graphique deux fois moins dense (repères horaires toujours toutes les 3 h).
"""
from __future__ import annotations

from PIL import Image

from ..models import Snapshot
from .common import (BLACK, HEIGHT, JOURS_ABR, MOIS_ABR, WHITE, WIDTH,
                     draw_day_cell, draw_hourly_chart, draw_stale_badge,
                     draw_wmo_icon, font, fr_num, new_canvas, text_w)
from .layout_a import _fit_room_label

ROOMS_X = 300   # colonne des pièces intérieures
MARGIN = 22


def render(snap: Snapshot) -> Image.Image:
    img, d = new_canvas()
    cur, now = snap.current, snap.generated_at

    # --- héros : température + deux lignes de contexte ---------------------
    temp_s = fr_num(cur.temp) + "°"
    d.text((MARGIN - 2, 2), temp_s, font=font(84, bold=True), fill=BLACK)
    d.text((MARGIN, 92), f"{cur.humidity} % d'humidité", font=font(14), fill=BLACK)

    ctx = []
    if snap.normals_delta is not None:
        delta = snap.normals_delta
        ctx.append("normales de saison" if abs(delta) < 1 else
                   f"{'+' if delta > 0 else '−'}{abs(round(delta))}° vs normales")
    if snap.yesterday_temp is not None:
        ctx.append(f"hier {fr_num(snap.yesterday_temp)}°")
    if ctx:
        d.text((MARGIN, 111), " · ".join(ctx), font=font(13), fill=BLACK)

    # --- métadonnées, alignées à droite -----------------------------------
    f_date = font(21, bold=True)
    date_s = f"{JOURS_ABR[now.weekday()]} {now.day} {MOIS_ABR[now.month - 1]}"
    d.text((WIDTH - MARGIN, 10), date_s, font=f_date, fill=BLACK, anchor="ra")
    d.text((WIDTH - MARGIN, 44), f"màj à {now:%H:%M}", font=font(14),
           fill=BLACK, anchor="ra")
    if snap.stale:
        draw_stale_badge(d, WIDTH - MARGIN, 68, snap.stale_since)
    if snap.sunrise and snap.sunset:
        sun_s = f"{snap.sunrise:%H:%M} → {snap.sunset:%H:%M}"
        f_sun = font(14)
        d.text((WIDTH - MARGIN, 100), sun_s, font=f_sun, fill=BLACK, anchor="ra")
        draw_wmo_icon(d, WIDTH - MARGIN - text_w(d, sun_s, f_sun) - 15, 109,
                      15, 0, lw=1)
    meta_x = WIDTH - MARGIN - text_w(d, date_s, f_date)

    # --- pièces intérieures (2 max) ---------------------------------------
    avail = meta_x - ROOMS_X - 30
    f_val, f_lab = font(26, bold=True), font(13)
    for row, room in enumerate(snap.indoor[:2]):
        ry = 12 + row * 58
        d.text((ROOMS_X, ry), fr_num(room.temp) + "°", font=f_val, fill=BLACK)
        d.text((ROOMS_X, ry + 34), _fit_room_label(d, room, avail, f_lab),
               font=f_lab, fill=BLACK)

    d.line((MARGIN, 134, WIDTH - MARGIN, 134), fill=BLACK, width=1)

    # --- graphique 24 h ---------------------------------------------------
    f_title = font(16, bold=True)
    d.text((MARGIN, 146), "PROCHAINES 24 H", font=f_title, fill=BLACK)

    pills = []
    if snap.rain_soon:
        pills.append("pluie en cours" if snap.rain_soon.ongoing
                     else f"pluie vers {snap.rain_soon.at:%H:%M}")
    if snap.advice:
        pills.append(snap.advice)

    # statistique de rafales à droite (remplace la courbe pointillée)
    gust_w = 0
    if snap.hourly:
        gust_s = f"rafales {round(max(h.gust for h in snap.hourly))} km/h"
        f_gust = font(14)
        gust_w = text_w(d, gust_s, f_gust)
        d.text((WIDTH - MARGIN, 148), gust_s, font=f_gust, fill=BLACK, anchor="ra")

    px = MARGIN + text_w(d, "PROCHAINES 24 H", f_title) + 20
    limit = WIDTH - MARGIN - gust_w - 24
    f_pill = font(14, bold=True)
    for pill_s in pills:
        pw = text_w(d, pill_s, f_pill) + 24
        if px + pw > limit:
            break
        d.rounded_rectangle((px, 142, px + pw, 165), radius=11, fill=BLACK)
        d.text((px + pw // 2, 153), pill_s, font=f_pill, fill=WHITE, anchor="mm")
        px += pw + 10

    draw_hourly_chart(d, (MARGIN, 176, WIDTH - MARGIN, 340), snap.hourly,
                      show_gusts=False, grid_step=9)

    d.line((MARGIN, 354, WIDTH - MARGIN, 354), fill=BLACK, width=1)

    # --- 7 jours : pas de filets, le jour courant en pastille -------------
    xs = [16 + round(i * (WIDTH - 32) / 7) for i in range(8)]
    for i, day in enumerate(snap.daily):
        draw_day_cell(d, (xs[i], 360, xs[i + 1], HEIGHT - 6), day, now.date(),
                      chip=(day.day == now.date()))

    return img
