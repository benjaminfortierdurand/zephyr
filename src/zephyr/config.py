"""Configuration via .env (python-dotenv) ou variables d'environnement.

Toutes les dates manipulées dans le projet sont naïves, en heure locale : le Pi
doit être à l'heure de Paris (timedatectl set-timezone Europe/Paris) et Open-Meteo
est interrogé avec timezone=Europe/Paris.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


@dataclass(frozen=True)
class Config:
    lat: float
    lon: float
    netatmo_client_id: str
    netatmo_client_secret: str
    netatmo_refresh_token: str  # valeur d'amorçage ; ensuite data/netatmo_token.json fait foi
    netatmo_indoor_modules: tuple[str, ...]  # pièces à afficher, dans l'ordre (vide = toutes)
    data_dir: Path
    out_dir: Path


def load_config() -> Config:
    load_dotenv()

    def req(name: str) -> str:
        v = os.environ.get(name, "").strip()
        if not v:
            raise SystemExit(f"Variable {name} manquante — copier .env.example vers .env "
                             "et la renseigner (voir README).")
        return v

    return Config(
        # repli : Paris centre. Les vraies coordonnées vivent dans .env (non suivi).
        lat=float(os.environ.get("ZEPHYR_LAT", "48.8566")),
        lon=float(os.environ.get("ZEPHYR_LON", "2.3522")),
        netatmo_client_id=req("NETATMO_CLIENT_ID"),
        netatmo_client_secret=req("NETATMO_CLIENT_SECRET"),
        netatmo_refresh_token=req("NETATMO_REFRESH_TOKEN"),
        netatmo_indoor_modules=tuple(
            s.strip() for s in os.environ.get("NETATMO_INDOOR_MODULES", "").split(",")
            if s.strip()),
        data_dir=Path(os.environ.get("ZEPHYR_DATA_DIR", "data")),
        out_dir=Path(os.environ.get("ZEPHYR_OUT_DIR", "out")),
    )
