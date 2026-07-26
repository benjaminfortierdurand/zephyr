"""Données factices réalistes (Île-de-France, juillet) pour itérer sur le layout."""
from __future__ import annotations

import math
from datetime import datetime, timedelta

from .models import (CurrentConditions, DailyPoint, HourlyPoint, IndoorConditions,
                     RainAlert, Snapshot)

# Rafales (km/h) heure par heure : une averse orageuse passe environ 4-6 h après
# le début de la fenêtre, puis le vent retombe.
_GUSTS = [22, 24, 26, 30, 38, 45, 41, 33, 28, 26, 24, 22,
          20, 19, 18, 17, 16, 15, 14, 14, 13, 12, 12, 11]
_PRECIP = {4: 1.2, 5: 2.6, 6: 0.8, 15: 0.2}

# 7 jours : (décalage tmin, tmax, cumul mm, code WMO)
_DAILY = [
    (17.2, 28.9, 4.6, 80),   # aujourd'hui : averses
    (17.8, 27.1, 8.2, 95),   # orage
    (16.1, 23.8, 1.4, 61),   # pluie
    (15.3, 25.6, 0.0, 3),    # couvert
    (15.9, 29.7, 0.0, 0),    # grand soleil
    (17.5, 31.2, 0.0, 2),    # variable
    (18.1, 27.4, 0.3, 1),    # peu nuageux
]


def make_snapshot(stale: bool = False) -> Snapshot:
    now = datetime.now().replace(second=0, microsecond=0)
    start = now.replace(minute=0)

    hourly = []
    for i in range(24):
        t = start + timedelta(hours=i)
        h = t.hour
        temp = 23.0 + 6.0 * math.cos((h - 16.0) * math.pi / 12.0)
        if i in _PRECIP:
            temp -= 1.5  # rafraîchissement sous l'averse
        hourly.append(HourlyPoint(
            time=t,
            temp=round(temp, 1),
            precip=_PRECIP.get(i, 0.0),
            gust=float(_GUSTS[i]),
        ))

    daily = [
        DailyPoint(day=(now + timedelta(days=k)).date(),
                   tmin=tmin, tmax=tmax, precip_mm=mm, wmo=wmo)
        for k, (tmin, tmax, mm, wmo) in enumerate(_DAILY)
    ]

    current = CurrentConditions(
        temp=26.4,
        humidity=52,
        pressure=1013.8,
        pressure_trend="down",
        measured_at=now - timedelta(minutes=3),
    )

    # noms volontairement réalistes (dont un long, comme la vraie station de base)
    indoor = [
        IndoorConditions(name="Salon", temp=23.1, humidity=51, co2=640,
                         measured_at=now - timedelta(minutes=3)),
        IndoorConditions(name="Chambre", temp=21.8, humidity=58, co2=910,
                         measured_at=now - timedelta(minutes=4)),
    ]

    return Snapshot(
        current=current,
        hourly=hourly,
        daily=daily,
        generated_at=now,
        stale=stale,
        stale_since=(now - timedelta(minutes=47)) if stale else None,
        indoor=indoor,
        rain_soon=RainAlert(at=now + timedelta(minutes=35), ongoing=False),
        normals_delta=6.4,
        advice="plus frais dehors : aérez",
        sunrise=now.replace(hour=6, minute=22),
        sunset=now.replace(hour=21, minute=41),
        yesterday_temp=24.3,
    )
