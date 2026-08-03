"""Prévisions Open-Meteo : AROME HD (horaire 24 h) et ECMWF IFS (7 jours),
avec fallback sur best_match si le modèle demandé est indisponible."""
from __future__ import annotations

import logging
import math
from datetime import date, datetime, timedelta

import requests

from .config import Config
from .models import DailyPoint, HourlyPoint, PrecipGrid, RainAlert

log = logging.getLogger(__name__)

API = "https://api.open-meteo.com/v1/forecast"
TIMEOUT = 20
MODEL_HOURLY = "meteofrance_arome_france_hd"
MODEL_DAILY = "ecmwf_ifs025"
# AROME standard (et non HD) pour les deux premiers jours de la rangée : c'est le
# seul de la famille à fournir un code météo, indispensable au pictogramme. Ses
# températures ne s'écartent de la version HD que d'un dixième de degré.
MODEL_DAILY_FINE = "meteofrance_arome_france"
FALLBACK = "best_match"

HOURLY_VARS = "temperature_2m,precipitation,wind_gusts_10m"

# Carte régionale : 24 × 13 cellules de 5 km, soit 120 × 65 km autour du domicile.
# Les proportions sont calées sur la zone d'affichage pour des cellules carrées.
GRID_COLS, GRID_ROWS, GRID_KM = 24, 13, 5.0
GRID_AHEAD_MIN = 60          # échéance superposée en contour, pour voir venir
DAILY_VARS = ("temperature_2m_min,temperature_2m_max,precipitation_sum,weather_code,"
              "sunrise,sunset")


def _get(params: dict) -> dict:
    r = requests.get(API, params=params, timeout=TIMEOUT)
    r.raise_for_status()
    return r.json()


def fetch_hourly(cfg: Config, model: str = MODEL_HOURLY) -> dict:
    try:
        data = _get(dict(latitude=cfg.lat, longitude=cfg.lon, models=model,
                         hourly=HOURLY_VARS, forecast_hours=24,
                         minutely_15="precipitation", forecast_minutely_15=8,
                         timezone="Europe/Paris"))
        _check(data, "hourly", "temperature_2m", minimum=12)
        _warn_absent(data, "hourly", HOURLY_VARS)
        return data
    except (requests.RequestException, ValueError) as e:
        if model == FALLBACK:
            raise
        log.warning("modèle %s indisponible (%s) — fallback %s", model, e, FALLBACK)
        return fetch_hourly(cfg, model=FALLBACK)


def fetch_daily(cfg: Config, model: str = MODEL_DAILY) -> dict:
    """Rangée des 7 jours, en interrogeant deux modèles d'un coup.

    Open-Meteo accepte une liste de modèles et suffixe alors chaque variable de
    son nom. On y gagne les deux premiers jours vus par AROME, sans requête
    supplémentaire ; au-delà il ne renvoie rien et ECMWF garde la main.
    """
    models = model if model == FALLBACK else f"{model},{MODEL_DAILY_FINE}"
    try:
        data = _get(dict(latitude=cfg.lat, longitude=cfg.lon, models=models,
                         daily=DAILY_VARS, forecast_days=7,
                         timezone="Europe/Paris"))
        if len(_daily_series(data, "temperature_2m_max", model)) < 5:
            raise ValueError("réponse daily vide ou incomplète")
        return data
    except (requests.RequestException, ValueError) as e:
        if model == FALLBACK:
            raise
        log.warning("modèle %s indisponible (%s) — fallback %s", model, e, FALLBACK)
        return fetch_daily(cfg, model=FALLBACK)


def _daily_series(data: dict, var: str, model: str) -> list:
    """Une variable du bloc daily, que la réponse soit suffixée ou non.

    Open-Meteo ne suffixe les noms que lorsque plusieurs modèles sont demandés :
    le repli sur un modèle unique renvoie des clés nues.
    """
    block = data.get("daily") or {}
    series = block.get(f"{var}_{model}")
    if series is None:
        series = block.get(var)
    return series or []


def _check(data: dict, section: str, key: str, minimum: int) -> None:
    block = data.get(section) or {}
    values = block.get(key) or []
    if len(values) < minimum or all(v is None for v in values):
        raise ValueError(f"réponse {section} vide ou incomplète")


def _warn_absent(data: dict, section: str, requested: str) -> None:
    """Journalise les variables demandées que le modèle n'a pas fournies.

    C'est exactement ce contrôle qui manquait le jour où AROME HD a cessé de
    fournir `cloud_cover` : l'API répondait 200, le champ était plein de null,
    et le code les prenait pour des zéros. Une variable entièrement absente est
    désormais visible dans les journaux (`journalctl -u zephyr.service`).
    """
    block = data.get(section) or {}
    absent = [name for name in requested.split(",")
              if all(v is None for v in (block.get(name) or [None]))]
    if absent:
        log.warning("%s : le modèle ne fournit pas %s", section, ", ".join(absent))


def payload_to_hourly(data: dict) -> list[HourlyPoint]:
    h = data["hourly"]
    points = []
    for t, temp, precip, gust in zip(h["time"], h["temperature_2m"],
                                     h["precipitation"], h["wind_gusts_10m"]):
        if temp is None:
            continue
        points.append(HourlyPoint(
            time=datetime.fromisoformat(t),
            temp=float(temp),
            precip=float(precip) if precip is not None else None,
            gust=float(gust) if gust is not None else None,
        ))
    return points


def fetch_precip_grid(cfg: Config) -> PrecipGrid | None:
    """Champ de précipitations AROME autour du domicile, en une seule requête.

    Open-Meteo accepte des listes de coordonnées : les 312 points reviennent
    ensemble. Donnée décorative — None en cas d'échec, ni cache ni badge.
    N'est appelée que lorsque de la pluie est attendue (voir collector), pour
    rester très en deçà des quotas de l'offre gratuite.
    """
    km_per_lat = 111.2
    km_per_lon = 111.32 * math.cos(math.radians(cfg.lat))
    half_lat = (GRID_ROWS * GRID_KM / 2) / km_per_lat
    half_lon = (GRID_COLS * GRID_KM / 2) / km_per_lon

    lats, lons = [], []
    for row in range(GRID_ROWS):        # ligne 0 = nord, comme à l'écran
        for col in range(GRID_COLS):
            lats.append(round(cfg.lat + half_lat
                              - 2 * half_lat * (row + 0.5) / GRID_ROWS, 4))
            lons.append(round(cfg.lon - half_lon
                              + 2 * half_lon * (col + 0.5) / GRID_COLS, 4))
    steps = GRID_AHEAD_MIN // 15 + 1        # instant courant + échéance à afficher
    try:
        data = _get(dict(latitude=",".join(map(str, lats)),
                         longitude=",".join(map(str, lons)),
                         models=MODEL_HOURLY, minutely_15="precipitation",
                         forecast_minutely_15=steps, timezone="Europe/Paris"))
        if not isinstance(data, list) or len(data) != GRID_COLS * GRID_ROWS:
            raise ValueError(f"grille incomplète ({len(data)} points)")
        series = [point.get("minutely_15", {}).get("precipitation") or []
                  for point in data]
        values = [(s[0] if s else None) or 0.0 for s in series]
        # l'échéance manque si le modèle ne va pas assez loin : on s'en passe
        ahead = ([(s[steps - 1] if len(s) >= steps else None) or 0.0 for s in series]
                 if all(len(s) >= steps for s in series) else None)
    except Exception as e:
        log.warning("carte des précipitations indisponible : %s", e)
        return None
    return PrecipGrid(cols=GRID_COLS, rows=GRID_ROWS, km=GRID_KM, values=values,
                      lat=cfg.lat, lon=cfg.lon, ahead=ahead,
                      ahead_minutes=GRID_AHEAD_MIN)


def payload_to_sun(data: dict) -> tuple[datetime | None, datetime | None]:
    """Lever/coucher du soleil du jour (absents des caches antérieurs à l'ajout)."""
    def first(key: str) -> datetime | None:
        values = _daily_series(data, key, MODEL_DAILY)
        return datetime.fromisoformat(values[0]) if values else None

    return first("sunrise"), first("sunset")


def payload_to_rain_alert(data: dict, now: datetime) -> RainAlert | None:
    """Premier créneau de 15 min avec de la pluie dans les ~75 prochaines minutes."""
    block = data.get("minutely_15") or {}
    for t, p in zip(block.get("time") or [], block.get("precipitation") or []):
        if p is None or p < 0.15:
            continue
        at = datetime.fromisoformat(t)
        if at + timedelta(minutes=15) <= now:   # créneau déjà entièrement passé
            continue
        if at - now > timedelta(minutes=75):    # trop loin pour être « imminent »
            return None
        return RainAlert(at=at, ongoing=at <= now)
    return None


def payload_to_daily(data: dict) -> list[DailyPoint]:
    """Rangée des 7 jours, chaque journée prise chez un seul modèle.

    AROME l'emporte tant qu'il fournit ses quatre variables, soit les deux
    premiers jours ; ECMWF prend la suite. Le choix se fait par journée entière
    et jamais variable par variable : mélanger les sources afficherait un
    pictogramme d'averses au-dessus d'un cumul nul, ce qui s'est produit tant
    que seules les températures étaient reprises.
    """
    times = _daily_series(data, "time", MODEL_DAILY)
    VARS = ("temperature_2m_min", "temperature_2m_max",
            "precipitation_sum", "weather_code")
    coarse = {v: _daily_series(data, v, MODEL_DAILY) for v in VARS}
    fine = {v: (data.get("daily") or {}).get(f"{v}_{MODEL_DAILY_FINE}") or []
            for v in VARS}

    days = []
    for i, t in enumerate(times):
        src = fine if all(i < len(fine[v]) and fine[v][i] is not None
                          for v in VARS) else coarse
        if i >= len(src["temperature_2m_min"]) or i >= len(src["temperature_2m_max"]):
            continue
        tmin, tmax = src["temperature_2m_min"][i], src["temperature_2m_max"][i]
        if tmin is None or tmax is None:
            continue
        mm = src["precipitation_sum"][i] if i < len(src["precipitation_sum"]) else None
        wmo = src["weather_code"][i] if i < len(src["weather_code"]) else None
        days.append(DailyPoint(
            day=date.fromisoformat(t),
            tmin=float(tmin),
            tmax=float(tmax),
            precip_mm=float(mm) if mm is not None else 0.0,
            wmo=int(wmo) if wmo is not None else 3,
        ))
    return days
