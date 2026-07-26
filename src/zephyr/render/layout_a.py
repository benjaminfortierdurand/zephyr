"""Variante A « Classique » : bandeau haut, graphique central, 7 jours en bas."""
from __future__ import annotations

from PIL import Image

from ..models import Snapshot
from .common import (BLACK, HEIGHT, JOURS_ABR, MOIS_ABR, WHITE, WIDTH,
                     dotted_line, draw_day_cell, draw_hourly_chart, draw_legend,
                     draw_stale_badge, draw_wmo_icon, font, fr_num,
                     new_canvas, text_w)


def _fit_room_label(d, room, avail: int, f_lab) -> str:
    """« nom · 46 % · 448 ppm » dégradé jusqu'à tenir dans avail : nom raccourci,
    puis humidité omise (le CO2 est plus utile), puis CO2 omis. Ne déborde jamais."""
    def build(name: str, hum: bool, co2: bool) -> str:
        parts = [name]
        if hum:
            parts.append(f"{room.humidity}%")
        if co2 and room.co2 is not None:
            parts.append(f"{room.co2} ppm")
        return " · ".join(parts)

    full = room.name.lower()
    label = full
    for hum, co2, min_len in ((True, True, 8), (False, True, 5), (False, False, 4)):
        name = full
        label = build(name, hum, co2)
        while text_w(d, label, f_lab) > avail and len(name) > min_len:
            name = name.rstrip("…")[:-1] + "…"
            label = build(name, hum, co2)
        if text_w(d, label, f_lab) <= avail:
            return label
    return label


def render(snap: Snapshot) -> Image.Image:
    img, d = new_canvas()
    cur, now = snap.current, snap.generated_at

    # --- bandeau haut -----------------------------------------------------
    temp_s = fr_num(cur.temp) + "°"
    f_big = font(80, bold=True)
    d.text((20, 4), temp_s, font=f_big, fill=BLACK)
    bx = 20 + text_w(d, temp_s, f_big) + 26

    # écart du max du jour aux normales de saison (1991-2020)
    if snap.normals_delta is not None:
        delta = snap.normals_delta
        norm_s = ("normales de saison" if abs(delta) < 1 else
                  f"{'+' if delta > 0 else '−'}{abs(round(delta))}° vs normales")
        d.text((24, 108), norm_s, font=font(13), fill=BLACK)

    # humidité seule en colonne 2 (la pression, peu consultée, n'est plus affichée
    # — elle reste collectée et en cache, la ré-afficher tient en quelques lignes)
    hum_s = f"{cur.humidity} %"
    f_hum = font(26, bold=True)
    d.text((bx, 18), hum_s, font=f_hum, fill=BLACK)
    d.text((bx, 54), "humidité", font=font(14), fill=BLACK)

    # température d'hier à la même heure (historique du module extérieur)
    if snap.yesterday_temp is not None:
        d.text((bx, 82), fr_num(snap.yesterday_temp) + "°",
               font=font(20, bold=True), fill=BLACK)
        d.text((bx, 110), f"hier à {now:%H:%M}", font=font(12), fill=BLACK)

    f_date, f_maj = font(20, bold=True), font(14)
    date_s = f"{JOURS_ABR[now.weekday()]} {now.day} {MOIS_ABR[now.month - 1]}"
    maj_s = f"màj à {now:%H:%M}"
    d.text((WIDTH - 20, 14), date_s, font=f_date, fill=BLACK, anchor="ra")
    d.text((WIDTH - 20, 46), maj_s, font=f_maj, fill=BLACK, anchor="ra")
    if snap.stale:
        draw_stale_badge(d, WIDTH - 20, 72, snap.stale_since)
    if snap.sunrise and snap.sunset:
        sun_s = f"{snap.sunrise:%H:%M} → {snap.sunset:%H:%M}"
        f_sun = font(14)
        d.text((WIDTH - 20, 100), sun_s, font=f_sun, fill=BLACK, anchor="ra")
        draw_wmo_icon(d, WIDTH - 20 - text_w(d, sun_s, f_sun) - 15, 109, 15, 0, lw=1)
    date_x = WIDTH - 20 - max(text_w(d, date_s, f_date), text_w(d, maj_s, f_maj))

    # pièces intérieures (2 max) : température + « nom · humidité · CO2 »
    if snap.indoor:
        ix = bx + max(text_w(d, hum_s, f_hum), 70) + 40
        dotted_line(d, (ix - 15, 16), (ix - 15, 116), step=4)
        avail = date_x - ix - 14
        f_val, f_lab = font(26, bold=True), font(13)
        for row, room in enumerate(snap.indoor[:2]):
            ry = 12 + row * 58
            d.text((ix, ry), fr_num(room.temp) + "°", font=f_val, fill=BLACK)
            d.text((ix, ry + 34), _fit_room_label(d, room, avail, f_lab),
                   font=f_lab, fill=BLACK)

    d.line((16, 132, WIDTH - 16, 132), fill=BLACK, width=2)

    # --- graphique 24 h ---------------------------------------------------
    d.text((20, 142), "PROCHAINES 24 H", font=font(16, bold=True), fill=BLACK)
    # cartouches transitoires : pluie imminente puis conseil d'aération ; un
    # cartouche qui déborderait sur la légende est simplement omis
    pills = []
    if snap.rain_soon:
        pills.append("pluie en cours" if snap.rain_soon.ongoing
                     else f"pluie vers {snap.rain_soon.at:%H:%M}")
    if snap.advice:
        pills.append(snap.advice)
    px = 20 + text_w(d, "PROCHAINES 24 H", font(16, bold=True)) + 18
    f_pill = font(14, bold=True)
    for pill_s in pills:
        pw = text_w(d, pill_s, f_pill) + 24
        if px + pw > 440:
            break
        d.rounded_rectangle((px, 138, px + pw, 161), radius=11, fill=BLACK)
        d.text((px + pw // 2, 149), pill_s, font=f_pill, fill=WHITE, anchor="mm")
        px += pw + 10
    draw_legend(d, WIDTH - 20, 144,
                [("line", "température"), ("bar", "pluie"),
                 ("dots", "rafales")])
    draw_hourly_chart(d, (20, 170, WIDTH - 20, 344), snap.hourly)

    d.line((16, 358, WIDTH - 16, 358), fill=BLACK, width=2)

    # --- 7 jours ----------------------------------------------------------
    xs = [16 + round(i * (WIDTH - 32) / 7) for i in range(8)]
    for i, day in enumerate(snap.daily):
        draw_day_cell(d, (xs[i], 366, xs[i + 1], HEIGHT - 6), day, now.date())
        if i:
            dotted_line(d, (xs[i], 370), (xs[i], HEIGHT - 12), step=4)

    return img
