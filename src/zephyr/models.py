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
    # temp est obligatoire (un point sans température est écarté à la collecte) ;
    # precip et gust valent None quand le modèle ne les fournit pas — surtout pas 0,
    # qui s'afficherait comme « pas de pluie » ou « pas de vent »
    temp: float             # °C
    precip: float | None    # mm
    gust: float | None      # km/h


@dataclass
class PrecipGrid:
    """Champ de précipitations observé autour du domicile, en cellules carrées.

    `values` est rangé par lignes du nord vers le sud, chaque ligne d'ouest en est
    (donc dans l'ordre de lecture de l'écran). Chaque valeur est une intensité
    de 0 (rien) à 3 (forte), et non une hauteur d'eau : le radar mesure une
    réflectivité, la convertir en millimètres ajouterait une approximation sans
    rien apporter à un écran en noir et blanc.
    """
    cols: int
    rows: int
    km: float                  # côté d'une cellule
    values: list[float]        # intensité observée, de 0 à 3
    lat: float = 0.0           # centre de la carte (pour projeter les repères)
    lon: float = 0.0
    contour: list[float] | None = None   # même champ à un autre instant
    contour_label: str = ""              # ce que ce contour représente
    observed_at: datetime | None = None  # heure de l'image radar


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
    stale_source: str | None = None        # laquelle, si une seule est concernée
    indoor: list[IndoorConditions] = field(default_factory=list)  # pièces intérieures
    rain_soon: RainAlert | None = None     # pluie dans l'heure à venir (AROME 15 min)
    normals_delta: float | None = None     # écart du max du jour aux normales 1991-2020
    advice: str | None = None              # conseil d'aération (thermique ou CO2)
    precip_grid: PrecipGrid | None = None  # carte régionale, seulement si pluie attendue
    sunrise: datetime | None = None        # éphéméride du jour
    sunset: datetime | None = None
    yesterday_temp: float | None = None    # température d'hier à la même heure
