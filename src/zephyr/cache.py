"""Cache disque du dernier payload de chaque source.

En cas d'échec réseau/API, le dernier payload connu est réutilisé et le
résultat est marqué périmé (stale) avec la date de sa récupération.
"""
from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

log = logging.getLogger(__name__)


@dataclass
class CacheResult:
    payload: Any
    stale: bool
    fetched_at: datetime


class SourceCache:
    def __init__(self, data_dir: Path):
        self.dir = data_dir / "cache"

    def _path(self, name: str) -> Path:
        return self.dir / f"{name}.json"

    def get(self, name: str, fetch: Callable[[], Any]) -> CacheResult:
        try:
            payload = fetch()
        except Exception as e:
            log.warning("source %s en échec : %s — repli sur le cache", name, e)
            path = self._path(name)
            if not path.exists():
                raise RuntimeError(
                    f"source {name} en échec et aucun cache disponible "
                    "(premier lancement : réseau et identifiants requis)") from e
            saved = json.loads(path.read_text(encoding="utf-8"))
            return CacheResult(saved["payload"], stale=True,
                               fetched_at=datetime.fromtimestamp(saved["fetched_at"]))

        now = datetime.now()
        self.dir.mkdir(parents=True, exist_ok=True)
        tmp = self._path(name).with_suffix(".tmp")
        tmp.write_text(json.dumps({"fetched_at": now.timestamp(), "payload": payload}),
                       encoding="utf-8")
        os.replace(tmp, self._path(name))
        return CacheResult(payload, stale=False, fetched_at=now)
