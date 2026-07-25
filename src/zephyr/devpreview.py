"""Page d'aperçu locale pour le mode --watch : recharge le PNG automatiquement.

Ouverte en file:// dans n'importe quel navigateur — aucun serveur web.
"""
from __future__ import annotations

from pathlib import Path

PREVIEW_HTML = """\
<!doctype html>
<html lang="fr">
<meta charset="utf-8">
<title>Zephyr — aperçu</title>
<style>
  body  { margin:0; min-height:100vh; display:grid; place-items:center; background:#2b2b2b; }
  .frame{ background:#fff; padding:18px 18px 26px; border-radius:6px;
          box-shadow:0 8px 30px rgba(0,0,0,.5); }
  img   { display:block; width:800px; max-width:90vw; image-rendering:pixelated; }
  p     { color:#999; font:13px system-ui, sans-serif; text-align:center; margin:10px 0 0; }
</style>
<body>
  <div>
    <div class="frame"><img id="dash" src="dashboard.png" alt="dashboard Zephyr"></div>
    <p id="info">chargement…</p>
  </div>
  <script>
    const img = document.getElementById('dash');
    const info = document.getElementById('info');
    function reload() {
      img.src = 'dashboard.png?t=' + Date.now();
      info.textContent = 'aperçu rechargé à ' +
        new Date().toLocaleTimeString('fr-FR', {hour: '2-digit', minute: '2-digit'});
    }
    setInterval(reload, 30000);
    reload();
  </script>
</body>
</html>
"""


def write_preview_html(out_dir: Path) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / "preview.html"
    path.write_text(PREVIEW_HTML, encoding="utf-8")
    return path
