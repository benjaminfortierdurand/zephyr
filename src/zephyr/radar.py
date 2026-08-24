"""Champ de précipitations observé par radar (RainViewer).

Le radar remplace la prévision pour la carte régionale. Une averse convective
naît en une demi-heure et couvre cinq kilomètres : aucun modèle ne sait dire
quelle commune la prendra, alors que le radar la voit. Le 21 août 2026, AROME
annonçait 0,0 mm pendant qu'une cellule intense se vidait sur le domicile.

Contrepartie assumée : le radar n'annonce rien. Il montre l'instant présent, et
la position d'une demi-heure plus tôt en contour donne le sens du déplacement.
Les prévisions restent l'affaire de la courbe 24 h et de la rangée 7 jours.

Données RainViewer (https://www.rainviewer.com), libres d'usage non commercial.
"""
from __future__ import annotations

import io
import logging
import math
from datetime import datetime

import requests
from PIL import Image, ImageChops

from .config import Config
from .models import PrecipGrid

log = logging.getLogger(__name__)

INDEX_URL = "https://api.rainviewer.com/public/weather-maps.json"
ZOOM = 7             # dernier niveau servi gratuitement, environ 0,8 km par pixel
TILE = 256
TIMEOUT = 20
CONTOUR_MIN = 30     # ancienneté de l'image tracée en contour
SAT_MIN = 120        # en deçà, la couleur est un écho ténu et non de la pluie franche
COUVERTURE_MIN = 0.25  # part de la cellule qu'un niveau doit couvrir pour la définir
# Seuils d'affichage de la carte. Un écho isolé à quarante kilomètres ne concerne
# pas le domicile : afficher la carte pour lui, c'est allumer un voyant qui ne
# veut rien dire, et le lecteur cesse de le regarder.
PROCHE_KM = 25       # au-delà, une averse ne nous concerne pas encore
MASSE_MIN = 20       # cellules soutenues qu'il faut pour parler d'un front

# Grille d'affichage : 40 × 22 cellules de 3 km, soit 120 × 66 km. Les mailles
# sont plus fines que du temps d'AROME (5 km) puisque le radar le permet.
GRID_COLS, GRID_ROWS, GRID_KM = 40, 22, 3.0

KM_PAR_DEG_LAT = 111.2


def _xy(lat: float, lon: float) -> tuple[float, float]:
    """Coordonnées de tuile Web Mercator, partie entière = numéro de tuile."""
    n = 2 ** ZOOM
    return ((lon + 180.0) / 360.0 * n,
            (1.0 - math.asinh(math.tan(math.radians(lat))) / math.pi) / 2.0 * n)


def _bounds(cfg: Config) -> tuple[float, float, float, float]:
    """Coin nord-ouest et sud-est de la zone couverte par la carte."""
    demi_lat = (GRID_ROWS * GRID_KM / 2) / KM_PAR_DEG_LAT
    demi_lon = (GRID_COLS * GRID_KM / 2) / (111.32 * math.cos(math.radians(cfg.lat)))
    return (cfg.lat + demi_lat, cfg.lon - demi_lon,
            cfg.lat - demi_lat, cfg.lon + demi_lon)


def _mosaique(host: str, chemin: str, cfg: Config):
    """Assemble les tuiles couvrant la zone, et rend l'origine de la mosaïque."""
    nord, ouest, sud, est = _bounds(cfg)
    x0f, y0f = _xy(nord, ouest)
    x1f, y1f = _xy(sud, est)
    tx0, ty0, tx1, ty1 = int(x0f), int(y0f), int(x1f), int(y1f)

    largeur, hauteur = (tx1 - tx0 + 1) * TILE, (ty1 - ty0 + 1) * TILE
    mos = Image.new("RGBA", (largeur, hauteur), (0, 0, 0, 0))
    for tx in range(tx0, tx1 + 1):
        for ty in range(ty0, ty1 + 1):
            url = f"{host}{chemin}/{TILE}/{ZOOM}/{tx}/{ty}/2/0_0.png"
            r = requests.get(url, timeout=TIMEOUT)
            # une tuile hors couverture renvoie un bandeau « Zoom Level Not
            # Supported », toujours nettement plus léger qu'une vraie image
            if r.status_code != 200 or len(r.content) < 3000:
                continue
            mos.paste(Image.open(io.BytesIO(r.content)).convert("RGBA"),
                      ((tx - tx0) * TILE, (ty - ty0) * TILE))
    return mos, tx0, ty0


def _niveaux(mos: Image.Image) -> Image.Image:
    """Image des intensités 0 à 3, sans boucle Python sur les pixels.

    RainViewer ignore le paramètre de palette et sert toujours la même rampe :
    des gris et beiges peu saturés pour les échos les plus ténus, puis des bleus
    du clair au foncé, puis du jaune au rouge pour les cœurs. La teinte suit donc
    l'intensité, à condition d'écarter d'abord les couleurs ternes, qui partagent
    leur teinte avec les oranges sans rien avoir de commun avec eux.
    """
    hsv = mos.convert("RGB").convert("HSV")
    teinte, saturation, valeur = hsv.split()
    present = mos.split()[3].point(lambda v: 255 if v > 0 else 0)
    vif = saturation.point(lambda v: 255 if v >= SAT_MIN else 0)
    # jaune à rouge d'un côté, magenta de l'autre : les deux bouts de la rampe
    chaud = teinte.point(lambda v: 255 if v < 60 or v > 200 else 0)
    fonce = valeur.point(lambda v: 255 if v < 200 else 0)

    def et(*masques):
        m = masques[0]
        for autre in masques[1:]:
            m = ImageChops.multiply(m, autre)
        return m

    lvl = Image.new("L", mos.size, 0)
    lvl.paste(1, mask=present)                      # tout écho, halo compris
    lvl.paste(2, mask=et(present, vif, fonce))      # bleu soutenu
    lvl.paste(3, mask=et(present, vif, chaud))      # cœur de la cellule
    return lvl


def _echantillonner(lvl: Image.Image, tx0: int, ty0: int,
                    cfg: Config) -> list[float]:
    """Intensité représentative de chaque cellule.

    Ni la moyenne, qui dilue un noyau intense dans la maille, ni le maximum, qui
    ferait passer la cellule entière au noir dès qu'un pixel isolé y touche. On
    retient le niveau atteint par au moins un quart de la surface.
    """
    nord, ouest, sud, est = _bounds(cfg)
    x0f, y0f = _xy(nord, ouest)
    x1f, y1f = _xy(sud, est)
    px0, py0 = (x0f - tx0) * TILE, (y0f - ty0) * TILE
    px1, py1 = (x1f - tx0) * TILE, (y1f - ty0) * TILE
    cw, ch = (px1 - px0) / GRID_COLS, (py1 - py0) / GRID_ROWS

    valeurs = []
    for row in range(GRID_ROWS):
        for col in range(GRID_COLS):
            boite = (max(0, int(px0 + col * cw)), max(0, int(py0 + row * ch)),
                     min(lvl.width, int(px0 + (col + 1) * cw) + 1),
                     min(lvl.height, int(py0 + (row + 1) * ch) + 1))
            if boite[2] <= boite[0] or boite[3] <= boite[1]:
                valeurs.append(0.0)
                continue
            hist = lvl.crop(boite).histogram()[:4]
            total = sum(hist)
            cumul, retenu = 0, 0
            for niveau in (3, 2, 1):
                cumul += hist[niveau]
                if total and cumul >= total * COUVERTURE_MIN:
                    retenu = niveau
                    break
            valeurs.append(float(retenu))
    return valeurs


def _distance_km(index: int) -> float:
    """Distance du centre de la cellule au domicile."""
    row, col = divmod(index, GRID_COLS)
    return math.hypot((row + 0.5) - GRID_ROWS / 2,
                      (col + 0.5) - GRID_COLS / 2) * GRID_KM


def merite_affichage(valeurs: list[float]) -> bool:
    """La carte a-t-elle quelque chose à raconter ?

    Deux cas seulement : de la pluie assez proche pour arriver dans l'heure, ou
    une masse organisée même lointaine, dont on veut voir l'approche. Quelques
    cellules éparses à quarante kilomètres ne sont ni l'un ni l'autre.
    """
    if any(v >= 1 and _distance_km(i) <= PROCHE_KM for i, v in enumerate(valeurs)):
        return True
    return sum(1 for v in valeurs if v >= 2) >= MASSE_MIN


def rain_here(grid: PrecipGrid) -> bool:
    """Le radar voit-il de la pluie sur le domicile même ?

    On regarde les quatre cellules qui entourent le centre, soit six kilomètres
    de côté : à cette maille, viser la seule cellule centrale rendrait la réponse
    dépendante d'un arrondi.
    """
    milieu_r, milieu_c = grid.rows // 2, grid.cols // 2
    return any(grid.values[r * grid.cols + c] >= 1
               for r in (milieu_r - 1, milieu_r)
               for c in (milieu_c - 1, milieu_c))


def fetch_radar(cfg: Config) -> PrecipGrid | None:
    """Champ radar courant, avec la position d'il y a 30 min en contour.

    Rend None quand rien dans la zone ne concerne le domicile (voir
    merite_affichage) : la carte n'a alors rien à montrer.
    """
    try:
        idx = requests.get(INDEX_URL, timeout=TIMEOUT).json()
        host = idx["host"]
        passees = idx.get("radar", {}).get("past") or []
        if not passees:
            raise ValueError("aucune image radar disponible")

        recente = passees[-1]
        mos, tx0, ty0 = _mosaique(host, recente["path"], cfg)
        valeurs = _echantillonner(_niveaux(mos), tx0, ty0, cfg)
        if not merite_affichage(valeurs):
            # rien qui nous concerne : on s'arrête là, sans même télécharger
            # la mosaïque plus ancienne destinée au contour
            return None

        # image d'il y a une demi-heure, la plus proche de l'écart voulu
        contour = None
        cible = recente["time"] - CONTOUR_MIN * 60
        anciennes = [f for f in passees[:-1] if f["time"] <= cible]
        if anciennes:
            vieille = max(anciennes, key=lambda f: f["time"])
            mos2, tx2, ty2 = _mosaique(host, vieille["path"], cfg)
            contour = _echantillonner(_niveaux(mos2), tx2, ty2, cfg)
            ecart = round((recente["time"] - vieille["time"]) / 60)
            label = f"contour : il y a {ecart} min"
        else:
            label = ""

        return PrecipGrid(
            cols=GRID_COLS, rows=GRID_ROWS, km=GRID_KM, values=valeurs,
            lat=cfg.lat, lon=cfg.lon, contour=contour, contour_label=label,
            observed_at=datetime.fromtimestamp(recente["time"]))
    except Exception as e:
        log.warning("radar indisponible : %s", e)
        return None
