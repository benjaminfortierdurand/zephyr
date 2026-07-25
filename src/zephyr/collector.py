"""Assemble un Snapshot complet à partir des trois sources (avec cache et péremption)."""
from __future__ import annotations

import logging
from datetime import datetime, timedelta

from .cache import SourceCache
from .config import Config
from .models import CurrentConditions, IndoorConditions, Snapshot
from .netatmo import (NetatmoClient, payload_to_current, payload_to_indoor,
                      select_indoor)
from .normals import get_normals, normals_delta
from .openmeteo import (fetch_daily, fetch_hourly, payload_to_daily,
                        payload_to_hourly, payload_to_rain_alert, payload_to_sun)

log = logging.getLogger(__name__)

NETATMO_MAX_AGE = timedelta(hours=1)  # au-delà, la mesure est considérée périmée


def aeration_advice(current: CurrentConditions, indoor: list[IndoorConditions],
                    now: datetime) -> str | None:
    """Conseil d'aération depuis les capteurs : CO2 le soir, thermique en chaleur.
    Les règles thermiques ne s'activent que par temps chaud, sinon « dehors plus
    frais » serait affiché tout l'hiver."""
    for room in indoor:
        if room.co2 is not None and room.co2 >= 1000 and 19 <= now.hour <= 23:
            return f"CO₂ {room.name.lower()} : aérez"
    salon = indoor[0] if indoor else None
    if salon is not None:
        if current.temp <= salon.temp - 1.0 and salon.temp >= 24.0:
            return "plus frais dehors : aérez"
        if current.temp >= salon.temp + 1.0 and current.temp >= 27.0:
            return "plus chaud dehors : fermez"
    return None


def collect(cfg: Config) -> Snapshot:
    cache = SourceCache(cfg.data_dir)
    netatmo = NetatmoClient(cfg)

    cur_r = cache.get("netatmo", netatmo.fetch_current)
    hr_r = cache.get("arome_hourly", lambda: fetch_hourly(cfg))
    dy_r = cache.get("ecmwf_daily", lambda: fetch_daily(cfg))

    now = datetime.now().replace(second=0, microsecond=0)
    current = payload_to_current(cur_r.payload)
    hourly = payload_to_hourly(hr_r.payload)
    daily = payload_to_daily(dy_r.payload)
    indoor = payload_to_indoor(select_indoor(cur_r.payload.get("indoor") or [],
                                             cfg.netatmo_indoor_modules))
    sunrise, sunset = payload_to_sun(dy_r.payload)
    yesterday_temp = netatmo.fetch_yesterday_temp(cur_r.payload, now)

    # cache horaire ancien : ne pas afficher des heures déjà passées
    future = [p for p in hourly if p.time >= now - timedelta(minutes=45)]
    if future:
        hourly = future

    stale_dates = [r.fetched_at for r in (cur_r, hr_r, dy_r) if r.stale]
    # station en ligne mais mesure trop vieille (module HS, pile vide…)
    if not cur_r.stale and now - current.measured_at > NETATMO_MAX_AGE:
        log.warning("mesure Netatmo datée de %s — marquée périmée", current.measured_at)
        stale_dates.append(current.measured_at)

    return Snapshot(
        current=current,
        hourly=hourly,
        daily=daily,
        generated_at=now,
        stale=bool(stale_dates),
        stale_since=min(stale_dates) if stale_dates else None,
        indoor=indoor,
        rain_soon=payload_to_rain_alert(hr_r.payload, now),
        normals_delta=(normals_delta(get_normals(cfg), daily[0].day, daily[0].tmax)
                       if daily else None),
        advice=aeration_advice(current, indoor, now),
        sunrise=sunrise,
        sunset=sunset,
        yesterday_temp=yesterday_temp,
    )
