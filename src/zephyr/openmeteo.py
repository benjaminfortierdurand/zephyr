"""Prévisions Open-Meteo : AROME HD (horaire 24 h) et ECMWF IFS (7 jours),
avec fallback sur best_match si le modèle demandé est indisponible."""
from __future__ import annotations

import logging
from datetime import date, datetime, timedelta

import requests

from .config import Config
from .models import DailyPoint, HourlyPoint, RainAlert

log = logging.getLogger(__name__)

API = "https://api.open-meteo.com/v1/forecast"
TIMEOUT = 20
MODEL_HOURLY = "meteofrance_arome_france_hd"
MODEL_DAILY = "ecmwf_ifs025"
FALLBACK = "best_match"

HOURLY_VARS = "temperature_2m,precipitation,wind_gusts_10m"
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
        return data
    except (requests.RequestException, ValueError) as e:
        if model == FALLBACK:
            raise
        log.warning("modèle %s indisponible (%s) — fallback %s", model, e, FALLBACK)
        return fetch_hourly(cfg, model=FALLBACK)


def fetch_daily(cfg: Config, model: str = MODEL_DAILY) -> dict:
    try:
        data = _get(dict(latitude=cfg.lat, longitude=cfg.lon, models=model,
                         daily=DAILY_VARS, forecast_days=7,
                         timezone="Europe/Paris"))
        _check(data, "daily", "temperature_2m_max", minimum=5)
        return data
    except (requests.RequestException, ValueError) as e:
        if model == FALLBACK:
            raise
        log.warning("modèle %s indisponible (%s) — fallback %s", model, e, FALLBACK)
        return fetch_daily(cfg, model=FALLBACK)


def _check(data: dict, section: str, key: str, minimum: int) -> None:
    block = data.get(section) or {}
    values = block.get(key) or []
    if len(values) < minimum or all(v is None for v in values):
        raise ValueError(f"réponse {section} vide ou incomplète")


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
            precip=float(precip or 0.0),
            gust=float(gust or 0.0),
        ))
    return points


def payload_to_sun(data: dict) -> tuple[datetime | None, datetime | None]:
    """Lever/coucher du soleil du jour (absents des caches antérieurs à l'ajout)."""
    daily = data.get("daily") or {}

    def first(key: str) -> datetime | None:
        values = daily.get(key) or []
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
    dl = data["daily"]
    days = []
    for t, tmin, tmax, mm, wmo in zip(dl["time"], dl["temperature_2m_min"],
                                      dl["temperature_2m_max"], dl["precipitation_sum"],
                                      dl["weather_code"]):
        if tmin is None or tmax is None:
            continue
        days.append(DailyPoint(
            day=date.fromisoformat(t),
            tmin=float(tmin),
            tmax=float(tmax),
            precip_mm=float(mm or 0.0),
            wmo=int(wmo) if wmo is not None else 3,
        ))
    return days
