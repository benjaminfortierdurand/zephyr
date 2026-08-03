"""Primitives de rendu partagées : canevas, polices, icônes météo, graphique 24 h.

Tout est dessiné en niveaux de gris ("L") puis binarisé par seuil dans finalize()
— jamais de tramage : l'e-ink veut du noir franc.
"""
from __future__ import annotations

import math
from datetime import date, datetime
from functools import lru_cache
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from ..models import DailyPoint, HourlyPoint, PrecipGrid

WIDTH, HEIGHT = 800, 480
BLACK, WHITE = 0, 255

JOURS = ["lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche"]
JOURS_ABR = ["lun.", "mar.", "mer.", "jeu.", "ven.", "sam.", "dim."]
MOIS = ["janvier", "février", "mars", "avril", "mai", "juin", "juillet",
        "août", "septembre", "octobre", "novembre", "décembre"]
MOIS_ABR = ["janv.", "févr.", "mars", "avr.", "mai", "juin", "juil.",
            "août", "sept.", "oct.", "nov.", "déc."]

_FONT_DIRS = [
    Path(__file__).resolve().parents[3] / "fonts",  # DejaVu embarquée : dev == Pi
    Path("/usr/share/fonts/truetype/dejavu"),       # Raspberry Pi OS (fonts-dejavu-core)
    Path("C:/Windows/Fonts"),                       # dernier recours (métriques ≠ Pi)
]
_REGULAR = ["DejaVuSans.ttf", "segoeui.ttf", "arial.ttf"]
_BOLD = ["DejaVuSans-Bold.ttf", "segoeuib.ttf", "seguisb.ttf", "arialbd.ttf"]


@lru_cache(maxsize=None)
def font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    for name in (_BOLD if bold else _REGULAR):
        for directory in _FONT_DIRS:
            p = directory / name
            if p.exists():
                return ImageFont.truetype(str(p), size)
    raise RuntimeError("Aucune police trouvée (DejaVu / Segoe UI / Arial)")


def new_canvas() -> tuple[Image.Image, ImageDraw.ImageDraw]:
    img = Image.new("L", (WIDTH, HEIGHT), WHITE)
    return img, ImageDraw.Draw(img)


def finalize(img: Image.Image) -> Image.Image:
    return img.point(lambda p: WHITE if p >= 160 else BLACK).convert("1")


def fr_num(x: float, nd: int = 1) -> str:
    return f"{x:.{nd}f}".replace(".", ",")


def day_label(d: date, today: date) -> str:
    return "auj." if d == today else f"{JOURS_ABR[d.weekday()]} {d.day}"


def date_longue(dt: datetime) -> str:
    return f"{JOURS[dt.weekday()]} {dt.day} {MOIS[dt.month - 1]}"


def text_w(d: ImageDraw.ImageDraw, txt: str, f: ImageFont.FreeTypeFont) -> int:
    left, _, right, _ = d.textbbox((0, 0), txt, font=f)
    return right - left


def dotted_line(d: ImageDraw.ImageDraw, p0, p1, step: int = 4, fill: int = BLACK) -> None:
    x0, y0 = p0
    x1, y1 = p1
    n = max(1, int(math.hypot(x1 - x0, y1 - y0) // step))
    for i in range(n + 1):
        t = i / n
        d.point((round(x0 + (x1 - x0) * t), round(y0 + (y1 - y0) * t)), fill=fill)


def text_halo(d: ImageDraw.ImageDraw, xy, txt: str, f: ImageFont.FreeTypeFont,
              anchor: str = "mm", pad: int = 2) -> None:
    """Texte sur fond blanc opaque, pour rester lisible par-dessus grilles et courbes."""
    box = d.textbbox(xy, txt, font=f, anchor=anchor)
    d.rectangle((box[0] - pad, box[1] - pad, box[2] + pad, box[3] + pad), fill=WHITE)
    d.text(xy, txt, font=f, fill=BLACK, anchor=anchor)


def draw_trend_arrow(d: ImageDraw.ImageDraw, cx: float, cy: float, size: float,
                     trend: str, fill: int = BLACK) -> None:
    """Flèche de tendance : ↗ (up), ↘ (down), → (stable). y va vers le bas."""
    ang = {"up": -38.0, "down": 38.0}.get(trend, 0.0)
    a = math.radians(ang)
    ux, uy = math.cos(a), math.sin(a)
    half = size / 2
    x1, y1 = cx + ux * half, cy + uy * half
    d.line((cx - ux * half, cy - uy * half, x1, y1), fill=fill, width=4)
    for da in (150, -150):
        b = a + math.radians(da)
        d.line((x1, y1, x1 + math.cos(b) * size * 0.45, y1 + math.sin(b) * size * 0.45),
               fill=fill, width=4)


# ---------------------------------------------------------------- icônes WMO

def _sun(d, cx, cy, r, lw=3):
    d.ellipse((cx - r, cy - r, cx + r, cy + r), fill=BLACK)
    for k in range(8):
        a = math.radians(k * 45)
        d.line((cx + math.cos(a) * r * 1.35, cy + math.sin(a) * r * 1.35,
                cx + math.cos(a) * r * 1.80, cy + math.sin(a) * r * 1.80),
               fill=BLACK, width=lw)


def _cloud(d, cx, cy, w, lw=3):
    """Nuage à contour épais : silhouette noire, puis évidage blanc rétréci de lw."""
    blobs = [
        (cx - 0.26 * w, cy + 0.05 * w, 0.20 * w),
        (cx - 0.02 * w, cy - 0.08 * w, 0.26 * w),
        (cx + 0.24 * w, cy + 0.06 * w, 0.19 * w),
    ]
    base = (cx - 0.26 * w, cy + 0.02 * w, cx + 0.24 * w, cy + 0.25 * w)
    for bx, by, r in blobs:
        d.ellipse((bx - r, by - r, bx + r, by + r), fill=BLACK)
    d.rectangle(base, fill=BLACK)
    for bx, by, r in blobs:
        r -= lw
        d.ellipse((bx - r, by - r, bx + r, by + r), fill=WHITE)
    d.rectangle((base[0] + lw, base[1], base[2] - lw, base[3] - lw), fill=WHITE)


def _flake(d, cx, cy, r, lw=2):
    for k in range(3):
        a = math.radians(k * 60)
        d.line((cx - math.cos(a) * r, cy - math.sin(a) * r,
                cx + math.cos(a) * r, cy + math.sin(a) * r), fill=BLACK, width=lw)


def draw_wmo_icon(d: ImageDraw.ImageDraw, cx: float, cy: float, s: float,
                  code: int, lw: int = 3) -> None:
    """Picto météo vectoriel dans une boîte de s px de côté, centré sur (cx, cy)."""
    if code in (0, 1):
        _sun(d, cx, cy, 0.28 * s, lw)
    elif code == 2:
        _sun(d, cx + 0.16 * s, cy - 0.16 * s, 0.20 * s, lw)
        _cloud(d, cx - 0.04 * s, cy + 0.10 * s, 0.62 * s, lw)
    elif code == 3:
        _cloud(d, cx, cy, 0.72 * s, lw)
    elif code in (45, 48):  # brouillard
        _cloud(d, cx, cy - 0.16 * s, 0.58 * s, lw)
        for i, (ga, gb) in enumerate(((0.30, 0.28), (0.34, 0.22), (0.26, 0.30))):
            y = cy + (0.14 + 0.11 * i) * s
            d.line((cx - ga * s, y, cx + gb * s, y), fill=BLACK, width=lw)
    elif code in (51, 53, 55, 56, 57):  # bruine
        _cloud(d, cx, cy - 0.12 * s, 0.68 * s, lw)
        for k in range(4):
            x = cx + (-0.24 + 0.16 * k) * s
            y = cy + 0.26 * s + (0.06 * s if k % 2 else 0)
            r = max(2, lw - 1)
            d.ellipse((x - r, y - r, x + r, y + r), fill=BLACK)
    elif code in (71, 73, 75, 77, 85, 86):  # neige
        _cloud(d, cx, cy - 0.12 * s, 0.68 * s, lw)
        for k in (-1, 0, 1):
            _flake(d, cx + k * 0.20 * s, cy + 0.28 * s + (0.05 * s if k == 0 else 0),
                   0.09 * s)
    elif code in (95, 96, 99):  # orage
        _cloud(d, cx, cy - 0.14 * s, 0.68 * s, lw)
        d.polygon([
            (cx + 0.06 * s, cy - 0.02 * s), (cx - 0.12 * s, cy + 0.22 * s),
            (cx - 0.01 * s, cy + 0.22 * s), (cx - 0.08 * s, cy + 0.44 * s),
            (cx + 0.14 * s, cy + 0.14 * s), (cx + 0.02 * s, cy + 0.14 * s),
            (cx + 0.13 * s, cy - 0.02 * s),
        ], fill=BLACK)
    else:  # 61-67, 80-82 et défaut : pluie
        _cloud(d, cx, cy - 0.12 * s, 0.68 * s, lw)
        for k in (-1, 0, 1):
            x = cx + k * 0.19 * s
            y0 = cy + 0.20 * s + (0.05 * s if k == 0 else 0)
            d.line((x + 0.04 * s, y0, x - 0.04 * s, y0 + 0.16 * s), fill=BLACK, width=lw)


# ---------------------------------------------------------------- graphique 24 h

def draw_hourly_chart(d: ImageDraw.ImageDraw, box, hourly: list[HourlyPoint], *,
                      show_gusts: bool = True, fs: int = 14,
                      grid_step: int = 5, hour_step: int = 3) -> None:
    x0, y0, x1, y1 = box
    ml, mr, mb = 34, 32, 20
    px0, px1 = x0 + ml, x1 - mr
    py0, py1 = y0, y1 - mb
    slot = (px1 - px0) / len(hourly)
    centers = [px0 + (i + 0.5) * slot for i in range(len(hourly))]

    f_lab = font(fs)
    f_ann = font(fs, bold=True)

    # échelle de température
    temps = [h.temp for h in hourly]
    lo = math.floor(min(temps) / 2) * 2
    hi = math.ceil(max(temps) / 2) * 2
    if min(temps) - lo < 1.2:
        lo -= 2
    if hi - max(temps) < 1.2:
        hi += 2
    step = 2 if hi - lo <= 12 else 4
    y_of = lambda t: py1 - (t - lo) / (hi - lo) * (py1 - py0)

    for tick in range(lo, hi + 1, step):
        y = y_of(tick)
        dotted_line(d, (px0, y), (px1, y), step=grid_step)
        d.text((px0 - 6, y), f"{tick}°", font=f_lab, fill=BLACK, anchor="rm")

    # repères horaires
    for i, h in enumerate(hourly):
        if h.time.hour % hour_step == 0:
            dotted_line(d, (centers[i], py0), (centers[i], py1), step=grid_step)
            d.text((centers[i], py1 + 4), f"{h.time.hour}h", font=f_lab,
                   fill=BLACK, anchor="ma")

    # barres de précipitations (échelle à droite) ; un repère dont la hauteur
    # coïncide avec l'arrivée de la courbe de température est omis (canicule :
    # la courbe finit en haut à droite, pile dans la zone des étiquettes mm)
    precips = [h.precip for h in hourly if h.precip is not None]
    pmax = max(2.0, math.ceil(max(precips))) if precips else 2.0
    mm_step = 1 if pmax <= 3 else 2
    curve_edge_y = y_of(temps[-1])
    d.text((px1 + 6, y0 + 1), "mm", font=font(fs - 2), fill=BLACK, anchor="la")
    for mm in range(mm_step, int(pmax) + 1, mm_step):
        y = py1 - mm / pmax * (py1 - py0) * 0.9
        # un repère est omis s'il tombe sur l'arrivée de la courbe ou sur
        # l'étiquette « mm » (cette dernière est collée au haut du cadre)
        if abs(y - curve_edge_y) < 13 or y < y0 + fs + 3:
            continue
        d.text((px1 + 6, y), str(mm), font=f_lab, fill=BLACK, anchor="lm")
    for i, h in enumerate(hourly):
        if h.precip is None or h.precip <= 0:   # None : heure sans donnée, pas de barre
            continue
        bh = h.precip / pmax * (py1 - py0) * 0.9
        bw = slot * 0.30
        d.rectangle((centers[i] - bw, py1 - bh, centers[i] + bw, py1), fill=BLACK)

    # positions des étiquettes d'extrêmes de température, calculées d'avance
    # pour que l'annotation des rafales puisse les éviter
    i_hi = max(range(len(temps)), key=lambda i: temps[i])
    i_lo = min(range(len(temps)), key=lambda i: temps[i])

    def _extreme_xy(i: int, dy: int) -> tuple[float, float]:
        x = min(max(centers[i], px0 + 22), px1 - 22)
        if i >= len(centers) - 2:   # extrême en bord de fenêtre : rentrer l'étiquette
            x -= 18                 # pour laisser le coin aux étiquettes d'axe
        elif i <= 1:
            x += 18
        y = min(max(y_of(temps[i]) + dy, py0 + 9), py1 - 11)
        return x, y

    hi_xy, lo_xy = _extreme_xy(i_hi, -14), _extreme_xy(i_lo, 14)

    # rafales : courbe pointillée sur échelle propre (annotation du maximum).
    # Les heures sans donnée laissent un trou dans la courbe plutôt qu'un zéro.
    gusts = [(i, h.gust) for i, h in enumerate(hourly) if h.gust is not None]
    if show_gusts and gusts:
        gmax = max(g for _, g in gusts)
        gy = lambda g: py1 - g / (gmax * 1.25) * (py1 - py0)
        gpts = {i: (centers[i], gy(g)) for i, g in gusts}
        for i in range(len(hourly) - 1):
            if i in gpts and i + 1 in gpts:
                dotted_line(d, gpts[i], gpts[i + 1], step=4)
        i_max = max((i for i, _ in gusts), key=lambda i: hourly[i].gust)
        # à côté du pic, à sa hauteur : ni sur les barres de pluie (dessous),
        # ni dans le coin haut-droit (réservé aux étiquettes d'axe et de température)
        side = 38 if centers[i_max] < (px0 + px1) / 2 else -38
        gx = min(max(centers[i_max] + side, px0 + 30), px1 - 44)
        gy_lab = max(gy(gmax) - 2, py0 + 8)
        for ax, ay in (hi_xy, lo_xy):   # esquiver les étiquettes de température
            if abs(gx - ax) < 74 and abs(gy_lab - ay) < 26:
                gy_lab = ay + 26
        text_halo(d, (gx, gy_lab), f"{round(gmax)} km/h",
                  font(fs - 1), anchor="mm", pad=1)

    # courbe de température (halo blanc pour rester lisible sur les barres)
    pts = [(centers[i], y_of(t)) for i, t in enumerate(temps)]
    d.line(pts, fill=WHITE, width=9, joint="curve")
    d.line(pts, fill=BLACK, width=4, joint="curve")
    text_halo(d, hi_xy, f"{round(temps[i_hi])}°", f_ann, anchor="mm")
    text_halo(d, lo_xy, f"{round(temps[i_lo])}°", f_ann, anchor="mm")

    # cadre bas + gauche
    d.line((px0, py0, px0, py1), fill=BLACK, width=1)
    d.line((px0, py1, px1, py1), fill=BLACK, width=1)


# Repères urbains de la carte régionale — à adapter si l'on change de région.
# Volontairement périphériques : au centre, la croix du domicile suffit, et deux
# étiquettes à 10 km l'une de l'autre seraient illisibles à cette échelle.
CITIES = [
    ("Mantes", 48.990, 1.717),
    ("Cergy", 49.036, 2.063),
    ("Roissy", 49.010, 2.548),
    ("Meaux", 48.960, 2.879),
    ("Paris", 48.857, 2.352),
    ("Melun", 48.541, 2.660),
    ("Rambouillet", 48.644, 1.830),
]


def draw_precip_map(d: ImageDraw.ImageDraw, box, grid: PrecipGrid,
                    cities=CITIES) -> None:
    """Champ de précipitations façon radar plutôt que carte géographique.

    Pas de fond cartographique : des cercles de distance, la position du
    domicile, le nord et une échelle suffisent à lire la situation — et ça
    évite d'embarquer des contours de départements illisibles en 1 bit.
    """
    x0, y0, x1, y1 = box
    cw, ch = (x1 - x0) / grid.cols, (y1 - y0) / grid.rows
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    px_per_km = (x1 - x0) / (grid.cols * grid.km)

    # cercles de portée dessinés en premier : la pluie passe par-dessus
    for km in (25, 50):
        r = km * px_per_km
        for deg in range(0, 360, 4):
            a = math.radians(deg)
            px, py = cx + math.cos(a) * r, cy + math.sin(a) * r
            if x0 < px < x1 and y0 < py < y1:
                d.point((px, py), fill=BLACK)

    for i, v in enumerate(grid.values):
        row, col = divmod(i, grid.cols)
        ax0, ay0 = round(x0 + col * cw), round(y0 + row * ch)
        ax1, ay1 = round(x0 + (col + 1) * cw), round(y0 + (row + 1) * ch)
        if v >= 1.0:                                   # forte
            d.rectangle((ax0, ay0, ax1, ay1), fill=BLACK)
        elif v >= 0.3:                                 # modérée
            for x in range(ax0, ax1):
                for y in range(ay0, ay1):
                    if (x + y) % 3 == 0:
                        d.point((x, y), fill=BLACK)
        elif v >= 0.05:                                # faible
            for x in range(ax0, ax1):
                for y in range(ay0, ay1):
                    if x % 4 == 0 and y % 4 == 0:
                        d.point((x, y), fill=BLACK)

    # position prévue dans une heure, en contour : le trait suit les bords des
    # cellules pluvieuses de l'échéance, ce qui montre à la fois vers où la masse
    # se déplace et si elle grossit ou se délite
    if grid.ahead:
        seuil = 0.15

        def pluvieux(row: int, col: int) -> bool:
            if not (0 <= row < grid.rows and 0 <= col < grid.cols):
                return False
            return grid.ahead[row * grid.cols + col] >= seuil

        for i, v in enumerate(grid.ahead):
            if v < seuil:
                continue
            row, col = divmod(i, grid.cols)
            ax0, ay0 = round(x0 + col * cw), round(y0 + row * ch)
            ax1, ay1 = round(x0 + (col + 1) * cw), round(y0 + (row + 1) * ch)
            if not pluvieux(row - 1, col):
                d.line((ax0, ay0, ax1, ay0), fill=BLACK, width=2)
            if not pluvieux(row + 1, col):
                d.line((ax0, ay1, ax1, ay1), fill=BLACK, width=2)
            if not pluvieux(row, col - 1):
                d.line((ax0, ay0, ax0, ay1), fill=BLACK, width=2)
            if not pluvieux(row, col + 1):
                d.line((ax1, ay0, ax1, ay1), fill=BLACK, width=2)

    # coins réservés à l'habillage (nord, échelle, note) : un repère urbain qui
    # y tomberait est omis plutôt que recouvert à moitié
    f_n, f_km = font(12, bold=True), font(11)
    scale_lab = f"{round(grid.cols * grid.km)} km"
    note = f"contour : dans {grid.ahead_minutes} min" if grid.ahead else None
    reserved = [(x0, y0, x0 + 16, y0 + 18),
                (x1 - text_w(d, scale_lab, f_km) - 8, y1 - 16, x1, y1)]
    if note:
        reserved.append((x0, y1 - 16, x0 + text_w(d, note, f_km) + 8, y1))

    # repères urbains : point cerclé de blanc + nom sur fond blanc, sinon rien
    # ne ressort d'une zone de pluie dense
    if cities and grid.lat:
        half_lat = (grid.rows * grid.km / 2) / 111.2
        half_lon = (grid.cols * grid.km / 2) / (111.32 * math.cos(
            math.radians(grid.lat)))
        f_city = font(11)
        for name, lat, lon in cities:
            px = x0 + (lon - grid.lon + half_lon) / (2 * half_lon) * (x1 - x0)
            py = y0 + (grid.lat + half_lat - lat) / (2 * half_lat) * (y1 - y0)
            if not (x0 + 4 < px < x1 - 4 and y0 + 4 < py < y1 - 4):
                continue
            # nom placé du côté qui reste dans le cadre
            w = text_w(d, name, f_city)
            tx, anchor = (px + 6, "lm") if px + 10 + w < x1 else (px - 6, "rm")
            lb = d.textbbox((tx, py), name, font=f_city, anchor=anchor)
            if any(lb[0] <= rx1 and lb[2] >= rx0 and lb[1] <= ry1 and lb[3] >= ry0
                   for rx0, ry0, rx1, ry1 in reserved):
                continue
            d.ellipse((px - 3, py - 3, px + 3, py + 3), fill=WHITE, outline=BLACK)
            d.point((px, py), fill=BLACK)
            text_halo(d, (tx, py), name, f_city, anchor=anchor, pad=1)

    # domicile : croix blanche cerclée, lisible aussi bien sur blanc que sur noir
    d.ellipse((cx - 6, cy - 6, cx + 6, cy + 6), fill=WHITE, outline=BLACK, width=2)
    d.line((cx - 3, cy, cx + 3, cy), fill=BLACK, width=2)
    d.line((cx, cy - 3, cx, cy + 3), fill=BLACK, width=2)

    d.rectangle((x0, y0, x1, y1), outline=BLACK, width=1)
    d.rectangle((x0 + 1, y0 + 1, x0 + 15, y0 + 17), fill=WHITE)
    d.text((x0 + 4, y0 + 2), "N", font=f_n, fill=BLACK)
    d.rectangle((x1 - text_w(d, scale_lab, f_km) - 7, y1 - 15, x1 - 1, y1 - 1),
                fill=WHITE)
    d.text((x1 - 4, y1 - 3), scale_lab, font=f_km, fill=BLACK, anchor="rs")
    if note:
        d.rectangle((x0 + 1, y1 - 15, x0 + text_w(d, note, f_km) + 7, y1 - 1),
                    fill=WHITE)
        d.text((x0 + 4, y1 - 3), note, font=f_km, fill=BLACK, anchor="ls")


def draw_legend(d: ImageDraw.ImageDraw, x_right: int, y: int, items, fs: int = 13) -> None:
    """Légende alignée à droite. items = [(kind, label)], kind ∈ line|bar|dots."""
    f = font(fs)
    total = sum(22 + text_w(d, label, f) + 16 for _, label in items) - 16
    x = x_right - total
    for kind, label in items:
        gy = y + fs // 2 + 1
        if kind == "line":
            d.line((x, gy, x + 16, gy), fill=BLACK, width=3)
        elif kind == "bar":
            d.rectangle((x + 4, y, x + 12, y + fs), fill=BLACK)
        elif kind == "dots":
            for k in range(4):
                d.point((x + 2 + k * 5, gy), fill=BLACK)
                d.point((x + 3 + k * 5, gy), fill=BLACK)
        x += 22
        d.text((x, gy), label, font=f, fill=BLACK, anchor="lm")
        x += text_w(d, label, f) + 16


# ---------------------------------------------------------------- cellule jour

def draw_day_cell(d: ImageDraw.ImageDraw, box, day: DailyPoint, today: date, *,
                  compact: bool = False, chip: bool = False) -> None:
    x0, y0, x1, y1 = box
    cx = (x0 + x1) // 2
    label = day_label(day.day, today)

    if chip:
        f_name = font(14, bold=True)
        w = text_w(d, label, f_name) + 16
        d.rounded_rectangle((cx - w // 2, y0, cx + w // 2, y0 + 20), radius=10, fill=BLACK)
        d.text((cx, y0 + 10), label, font=f_name, fill=WHITE, anchor="mm")
        name_h = 26
    else:
        f_name = font(14 if compact else 17, bold=True)
        d.text((cx, y0), label, font=f_name, fill=BLACK, anchor="ma")
        name_h = 20 if compact else 24

    # l'icône occupe toute sa boîte (les rayons du soleil vont jusqu'aux bords) :
    # la dimensionner d'après la bande réellement libre, sinon elle mord le texte
    ty = y1 - (32 if compact else 40)   # haut du bloc températures
    band_top = y0 + name_h
    icon_s = max(28, min(36 if compact else 46, ty - band_top - 8))
    draw_wmo_icon(d, cx, (band_top + ty) // 2, icon_s, day.wmo, lw=3)

    f_max = font(17 if compact else 21, bold=True)
    f_min = font(14 if compact else 17)
    tmax_s, tmin_s = f"{round(day.tmax)}°", f"{round(day.tmin)}°"
    wmax, wmin = text_w(d, tmax_s, f_max), text_w(d, tmin_s, f_min)
    gap = 5
    bx = cx - (wmax + gap + wmin) // 2
    d.text((bx, ty), tmax_s, font=f_max, fill=BLACK)
    d.text((bx + wmax + gap, ty + (2 if compact else 3)), tmin_s, font=f_min, fill=BLACK)

    f_rain = font(12 if compact else 14)
    rain = f"{fr_num(day.precip_mm)} mm" if day.precip_mm >= 0.1 else "—"
    d.text((cx, y1 - (14 if compact else 17)), rain, font=f_rain, fill=BLACK, anchor="ma")


# ---------------------------------------------------------------- badge péremption

def draw_stale_badge(d: ImageDraw.ImageDraw, x_right: int, y: int,
                     since: datetime | None, inverse: bool = False,
                     source: str | None = None) -> None:
    """Cartouche « données périmées ». inverse=True pour un bandeau noir.

    La source est nommée quand une seule est en cause : « ! NETATMO 18:07 » dit
    tout de suite que les prévisions, elles, sont à jour.
    """
    quand = f"{since:%H:%M}" if since else "?"
    txt = f"! {source} {quand}" if source else f"! DONNÉES DE {quand}"
    f = font(13, bold=True)
    w = text_w(d, txt, f) + 18
    bg, fg = (WHITE, BLACK) if inverse else (BLACK, WHITE)
    d.rounded_rectangle((x_right - w, y, x_right, y + 21), radius=4, fill=bg)
    d.text((x_right - w // 2, y + 10), txt, font=f, fill=fg, anchor="mm")
