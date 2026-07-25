"""Normales de saison 1991-2020, calculées une fois depuis l'archive ERA5 d'Open-Meteo.

Le résultat (une table jour-de-l'année → tmin/tmax moyens) est persisté dans
data/normals.json : le premier cycle après déploiement fait un unique gros appel
(~30 ans de données journalières), les suivants lisent le fichier local.
"""
from __future__ import annotations

import json
import logging
import os
from datetime import date, timedelta

import requests

from .config import Config

log = logging.getLogger(__name__)

ARCHIVE_API = "https://archive-api.open-meteo.com/v1/archive"
PERIOD = ("1991-01-01", "2020-12-31")


def _fetch_table(cfg: Config) -> dict:
    r = requests.get(ARCHIVE_API, params=dict(
        latitude=cfg.lat, longitude=cfg.lon,
        start_date=PERIOD[0], end_date=PERIOD[1],
        daily="temperature_2m_max,temperature_2m_min",
        timezone="Europe/Paris",
    ), timeout=120)
    r.raise_for_status()
    daily = r.json()["daily"]

    acc: dict[str, list[float]] = {}  # "MM-DD" -> [somme_max, somme_min, n]
    for t, tmax, tmin in zip(daily["time"], daily["temperature_2m_max"],
                             daily["temperature_2m_min"]):
        if tmax is None or tmin is None:
            continue
        entry = acc.setdefault(t[5:], [0.0, 0.0, 0])
        entry[0] += tmax
        entry[1] += tmin
        entry[2] += 1
    return {key: {"tmax": round(s_max / n, 1), "tmin": round(s_min / n, 1)}
            for key, (s_max, s_min, n) in acc.items() if n >= 10}


def get_normals(cfg: Config) -> dict | None:
    """Table des normales, depuis le cache disque ou l'API. None si indisponible."""
    path = cfg.data_dir / "normals.json"
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    try:
        table = _fetch_table(cfg)
    except Exception as e:
        log.warning("normales indisponibles (%s) — nouvel essai au prochain cycle", e)
        return None
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(table), encoding="utf-8")
    os.replace(tmp, path)
    log.info("normales 1991-2020 calculées et mises en cache (%d jours)", len(table))
    return table


def normals_delta(table: dict | None, day: date, tmax: float) -> float | None:
    """Écart du max prévu du jour à la normale. Le 29 février retombe sur le 28."""
    if not table:
        return None
    for d in (day, day - timedelta(days=1)):
        entry = table.get(f"{d:%m-%d}")
        if entry:
            return round(tmax - entry["tmax"], 1)
    return None
