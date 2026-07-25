"""Client Netatmo : OAuth2 refresh token (avec rotation) + lecture de la station.

Netatmo fait tourner les refresh tokens : chaque refresh peut en renvoyer un
nouveau, qui invalide l'ancien. L'état courant (access token, expiration,
refresh token à jour) est persisté dans data/netatmo_token.json ; le token du
.env ne sert que d'amorçage au premier lancement.
"""
from __future__ import annotations

import json
import logging
import os
import time
from datetime import datetime, timedelta

import requests

from .config import Config
from .models import CurrentConditions, IndoorConditions

log = logging.getLogger(__name__)

TOKEN_URL = "https://api.netatmo.com/oauth2/token"
STATION_URL = "https://api.netatmo.com/api/getstationsdata"
MEASURE_URL = "https://api.netatmo.com/api/getmeasure"
TIMEOUT = 15


class NetatmoError(RuntimeError):
    pass


class NetatmoClient:
    def __init__(self, cfg: Config):
        self.cfg = cfg
        self.token_path = cfg.data_dir / "netatmo_token.json"

    # ------------------------------------------------------------- tokens

    def _load_state(self) -> dict:
        if self.token_path.exists():
            return json.loads(self.token_path.read_text(encoding="utf-8"))
        return {"refresh_token": self.cfg.netatmo_refresh_token}

    def _save_state(self, state: dict) -> None:
        self.token_path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.token_path.with_suffix(".tmp")
        tmp.write_text(json.dumps(state), encoding="utf-8")
        os.replace(tmp, self.token_path)

    def _access_token(self, force_refresh: bool = False) -> str:
        state = self._load_state()
        if (not force_refresh and state.get("access_token")
                and state.get("expires_at", 0) > time.time() + 300):
            return state["access_token"]

        r = requests.post(TOKEN_URL, data={
            "grant_type": "refresh_token",
            "refresh_token": state["refresh_token"],
            "client_id": self.cfg.netatmo_client_id,
            "client_secret": self.cfg.netatmo_client_secret,
        }, timeout=TIMEOUT)
        if r.status_code != 200:
            raise NetatmoError(
                f"refresh du token refusé ({r.status_code}) : {r.text[:200]} — "
                "si invalid_grant, regénérer un refresh token sur dev.netatmo.com "
                "et supprimer data/netatmo_token.json")
        tok = r.json()
        state.update(
            access_token=tok["access_token"],
            refresh_token=tok.get("refresh_token", state["refresh_token"]),
            expires_at=time.time() + tok.get("expires_in", 10800),
        )
        self._save_state(state)
        log.info("access token Netatmo rafraîchi")
        return state["access_token"]

    # ------------------------------------------------------------- mesures

    def fetch_current(self) -> dict:
        """Payload JSON-sérialisable (stocké tel quel dans le cache disque)."""
        r = requests.get(STATION_URL,
                         headers={"Authorization": f"Bearer {self._access_token()}"},
                         timeout=TIMEOUT)
        if r.status_code in (401, 403):
            # access token révoqué avant son expiration théorique : un seul retry
            r = requests.get(STATION_URL,
                             headers={"Authorization":
                                      f"Bearer {self._access_token(force_refresh=True)}"},
                             timeout=TIMEOUT)
        if r.status_code != 200:
            raise NetatmoError(f"getstationsdata a répondu {r.status_code} : {r.text[:200]}")

        devices = r.json().get("body", {}).get("devices", [])
        if not devices:
            raise NetatmoError("aucune station sur ce compte")
        station = devices[0]
        base = station.get("dashboard_data", {})

        outdoor = next((m for m in station.get("modules", [])
                        if m.get("type") == "NAModule1" and "dashboard_data" in m), None)
        if outdoor is None:
            raise NetatmoError("module extérieur (NAModule1) introuvable ou muet")
        od = outdoor["dashboard_data"]

        if base.get("Pressure") is None:
            raise NetatmoError("pression absente (station de base muette)")

        # pièces intérieures : la base (souvent le salon) + les modules NAModule4
        indoor = []
        units = [station] + [m for m in station.get("modules", [])
                             if m.get("type") == "NAModule4"]
        for unit in units:
            dd = unit.get("dashboard_data") or {}
            if dd.get("Temperature") is None:
                continue
            indoor.append({
                "name": unit.get("module_name") or unit.get("station_name") or "intérieur",
                "temp": dd["Temperature"],
                "humidity": dd.get("Humidity"),
                "co2": dd.get("CO2"),
                "measured_at": dd.get("time_utc", 0),
            })
        return {
            "temp": od["Temperature"],
            "humidity": od["Humidity"],
            "pressure": base["Pressure"],
            "pressure_trend": base.get("pressure_trend", "stable"),
            "measured_at": od["time_utc"],  # epoch UTC
            "indoor": indoor,
            "station_id": station.get("_id"),   # MACs pour getmeasure (historique)
            "outdoor_id": outdoor.get("_id"),
        }

    # ----------------------------------------------------------- historique

    def fetch_yesterday_temp(self, payload: dict, now: datetime) -> float | None:
        """Température d'hier à la même heure (historique du module extérieur).
        Donnée décorative : None si indisponible (cache sans MACs, API en échec…)."""
        station_id = payload.get("station_id")
        outdoor_id = payload.get("outdoor_id")
        if not station_id or not outdoor_id:
            return None
        try:
            target = now - timedelta(days=1)
            past = self._measure(station_id, outdoor_id, "30min", "temperature",
                                 target - timedelta(minutes=45),
                                 target + timedelta(minutes=15))
            value = past[-1][0] if past and past[-1][0] is not None else None
            return float(value) if value is not None else None
        except Exception as e:
            log.warning("historique Netatmo indisponible : %s", e)
            return None

    def _measure(self, device: str, module: str, scale: str, types: str,
                 begin: datetime, end: datetime) -> list[list]:
        r = requests.get(MEASURE_URL,
                         headers={"Authorization": f"Bearer {self._access_token()}"},
                         params=dict(device_id=device, module_id=module, scale=scale,
                                     type=types, date_begin=int(begin.timestamp()),
                                     date_end=int(end.timestamp()), optimize="false"),
                         timeout=TIMEOUT)
        r.raise_for_status()
        body = r.json().get("body") or {}
        return [body[key] for key in sorted(body)]


def select_indoor(indoor: list[dict], entries: tuple[str, ...]) -> list[dict]:
    """Filtre et ordonne les pièces selon la config. Chaque entrée est un nom de
    module API, avec alias d'affichage optionnel : « Maison (Indoor)=Salon ».
    (L'API météo n'expose pas les noms de pièces de l'app ; l'alias comble ça.)
    Appliqué à l'assemblage — le cache garde toutes les pièces, brutes."""
    if not entries:
        return indoor
    by_name = {i["name"].lower(): i for i in indoor}
    selected = []
    for entry in entries:
        api_name, _, display = entry.partition("=")
        item = by_name.get(api_name.strip().lower())
        if item is None:
            log.warning("module intérieur introuvable : %r (disponibles : %s)",
                        api_name.strip(), [i["name"] for i in indoor])
            continue
        if display.strip():
            item = {**item, "name": display.strip()}
        selected.append(item)
    return selected


def payload_to_current(payload: dict) -> CurrentConditions:
    return CurrentConditions(
        temp=float(payload["temp"]),
        humidity=int(payload["humidity"]),
        pressure=float(payload["pressure"]),
        pressure_trend=str(payload.get("pressure_trend", "stable")),
        measured_at=datetime.fromtimestamp(payload["measured_at"]),
    )


def payload_to_indoor(items: list | None) -> list[IndoorConditions]:
    """items peut être absent des caches écrits avant l'ajout des pièces intérieures."""
    rooms = []
    for p in items or []:
        rooms.append(IndoorConditions(
            name=str(p.get("name") or "intérieur"),
            temp=float(p["temp"]),
            humidity=int(p.get("humidity") or 0),
            co2=int(p["co2"]) if p.get("co2") is not None else None,
            measured_at=datetime.fromtimestamp(p.get("measured_at") or 0),
        ))
    return rooms
