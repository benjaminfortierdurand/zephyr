"""Modèles de données partagés entre les sources (Netatmo, Open-Meteo) et le rendu."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime


@dataclass
class CurrentConditions:
    """Mesures du module extérieur Netatmo."""
    temp: float            # °C
    humidity: int          # %
    pressure: float        # hPa
    pressure_trend: str    # "up" | "down" | "stable" (tendance 3 h)
    measured_at: datetime


@dataclass
class IndoorConditions:
    """Mesures d'une pièce intérieure : station de base (NAMain) ou module NAModule4."""
    name: str              # nom du module dans l'app Netatmo (ex. « Chambre », « Salon »)
    temp: float            # °C
    humidity: int          # %
    co2: int | None        # ppm
    measured_at: datetime


@dataclass
class HourlyPoint:
    """Une heure de prévision AROME HD."""
    time: datetime
    temp: float        # °C
    precip: float      # mm
    gust: float        # km/h


@dataclass
class RainAlert:
    """Pluie imminente détectée sur le pas de 15 min d'AROME."""
    at: datetime       # début du créneau de 15 min concerné
    ongoing: bool      # True si le créneau est déjà en cours


@dataclass
class DailyPoint:
    """Un jour de prévision ECMWF IFS."""
    day: date
    tmin: float
    tmax: float
    precip_mm: float
    wmo: int           # code météo WMO


@dataclass
class Snapshot:
    """Tout ce qu'il faut pour rendre un écran."""
    current: CurrentConditions
    hourly: list[HourlyPoint]
    daily: list[DailyPoint]
    generated_at: datetime
    stale: bool = False                    # au moins une source servie depuis le cache
    stale_since: datetime | None = None    # date du payload le plus ancien utilisé
    indoor: list[IndoorConditions] = field(default_factory=list)  # pièces intérieures
    rain_soon: RainAlert | None = None     # pluie dans l'heure à venir (AROME 15 min)
    normals_delta: float | None = None     # écart du max du jour aux normales 1991-2020
    advice: str | None = None              # conseil d'aération (thermique ou CO2)
    sunrise: datetime | None = None        # éphéméride du jour
    sunset: datetime | None = None
    yesterday_temp: float | None = None    # température d'hier à la même heure
