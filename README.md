# Projet Zephyr — station météo e-ink

Dashboard météo 800×480 (1-bit) pour Raspberry Pi 4 + écran **Waveshare 7.5″ e-Paper
HAT V2** (driver `epd7in5_V2`), rafraîchi toutes les 10 minutes par un timer systemd
(le rythme de mesure de la station Netatmo).

![Aperçu du dashboard](docs/apercu.png)

*Rendu réel du programme, en données de démonstration (`--dev --fake`). L'image
fait 800×480 en noir et blanc pur : c'est exactement ce que l'écran affiche.*

| Zone | Contenu | Source |
|---|---|---|
| Bandeau haut | Température extérieure en très grand + écart aux normales de saison, humidité + température d'hier à la même heure, pièces intérieures (température, humidité, CO₂ — 2 max), date, heure de mise à jour, lever/coucher du soleil | Netatmo (mesures + historique `getmeasure`) + normales ERA5 1991-2020 |
| Zone centrale | Graphique 24 h : courbe de température, barres de pluie, rafales de l'heure en cours (et pointe à venir si elle est nettement plus forte) ; cartouches « pluie vers HH:MM » (pas de 15 min) et conseil d'aération (thermique par temps chaud, CO₂ le soir — calculé depuis les capteurs Netatmo) | Open-Meteo, modèle AROME HD (`meteofrance_arome_france_hd`) |
| Bandeau bas | 7 jours : picto WMO, min/max, cumul de pluie | Open-Meteo, modèle ECMWF (`ecmwf_ifs025`) |

> Le graphique n'affiche pas la couverture nuageuse : AROME HD ne fournit pas la
> variable `cloud_cover` (l'API renvoie `null` sur toutes les heures), et afficher
> une bande vide reviendrait à annoncer un ciel dégagé. L'ensoleillement se lit sur
> les pictogrammes de la rangée 7 jours.

Si un modèle Open-Meteo est indisponible, repli automatique sur `best_match`. Si une
source est en échec (réseau, API), le dernier payload est relu depuis le cache disque
(`data/cache/`) et un cartouche noir **« ! DONNÉES DE HH:MM »** apparaît dans le bandeau
haut. Une mesure Netatmo datant de plus d'une heure (module muet, pile vide) est aussi
marquée périmée.

Les **normales de saison** (moyennes 1991-2020 du lieu) sont calculées au premier
lancement depuis l'archive ERA5 d'Open-Meteo — un unique gros appel — puis mises en
cache définitivement dans `data/normals.json` ; si cet appel échoue, l'écart n'est
simplement pas affiché et un nouvel essai a lieu au cycle suivant.

La **pression** n'est plus affichée (peu consultée) mais reste collectée et en cache —
la ré-afficher tient en quelques lignes dans `render/layout_a.py`.

L'écran est piloté exclusivement en **full refresh** (anti-ghosting) puis mis en veille
entre deux cycles. Le rendu est fait en niveaux de gris avec Pillow puis binarisé par
seuil, jamais de tramage : l'aperçu PNG du mode dev est exactement ce que l'écran affiche.

## Arborescence

```
src/zephyr/
  main.py             # point d'entrée one-shot (python -m zephyr.main)
  config.py           # .env → Config
  collector.py        # assemble le Snapshot (3 sources + cache + péremption)
  netatmo.py          # OAuth2 refresh token (rotation persistée) + getstationsdata
  openmeteo.py        # AROME HD horaire, ECMWF journalier, fallback best_match
  cache.py            # cache disque du dernier payload de chaque source
  display.py          # driver e-ink (full refresh + sleep), importé seulement sur le Pi
  models.py           # dataclasses partagées
  fake_data.py        # données factices (mode démo)
  preview.py          # aperçu des 3 variantes de layout
  render/             # polices, icônes WMO vectorielles, graphique, layouts a/b/c/d
docs/
  apercu.png          # capture du README, régénérée par `--dev --fake`
deploy/
  zephyr.service      # unité systemd (Type=oneshot)
  zephyr.timer        # toutes les 10 min (OnUnitActiveSec)
```

## Mode dev (sur un poste de travail, sans matériel)

```bash
python -m venv .venv
.venv/Scripts/pip install -e .          # Linux/macOS : .venv/bin/pip
.venv/Scripts/python -m zephyr.main --dev --fake   # PNG ./out/dashboard.png, aucun réseau
.venv/Scripts/python -m zephyr.main --dev          # idem avec les vraies API (.env requis)
.venv/Scripts/python -m zephyr.preview             # rend les 3 variantes de layout
```

Le layout actif est la variante **D « Épuré »** (`--layout a|b|c|d` pour comparer).
Elle dérive de la variante A avec moins de traits : pas de légende ni de courbe de
rafales (elles passent en statistique sur la ligne de titre), pas de filets
verticaux, grille deux fois moins dense, et une hiérarchie en trois zones —
héros / pièces intérieures / métadonnées.

### Aperçu continu (« écran virtuel » sans matériel)

```bash
.venv/Scripts/python -m zephyr.main --dev --watch 15
```

régénère `out/dashboard.png` toutes les 15 minutes (Ctrl-C pour arrêter), et écrit
`out/preview.html` : ouvrez ce fichier dans un navigateur (double-clic), l'image se
recharge toute seule — aucun serveur web. Un cycle en échec (réseau coupé…) est loggué
et retenté au cycle suivant. Inutile de descendre sous ~10 minutes : Netatmo ne publie
une nouvelle mesure que toutes les 10 minutes environ.

## Installation sur le Raspberry Pi

### 0. Flasher la carte SD (depuis le poste Windows)

1. Installer **Raspberry Pi Imager** : `winget install --id RaspberryPi.Imager -e`
   (ou depuis <https://www.raspberrypi.com/software/>).
2. Dans l'Imager : appareil **Raspberry Pi 4** ; OS **Raspberry Pi OS Lite (64-bit)**
   (dans « Raspberry Pi OS (other) ») ; stockage : la carte SD (≥ 8 Go, elle sera
   effacée).
3. À la question « Would you like to apply OS customisation settings? » → **Edit
   settings** :
   - hostname : `zephyr` — le Pi sera joignable en `zephyr.local`
   - utilisateur : `benfd` + mot de passe (doit correspondre à `User=` dans
     `deploy/zephyr.service`)
   - Wi-Fi : SSID + mot de passe, pays `FR` (inutile si câble Ethernet)
   - locale : fuseau `Europe/Paris`, clavier `fr`
   - onglet **Services** : cocher **Enable SSH** (mot de passe)
4. Écrire, insérer la carte dans le Pi, brancher l'alimentation. Premier démarrage
   ~1 à 2 min, puis vérifier : `ssh benfd@zephyr.local`.

### 1. Activer le SPI

```bash
sudo raspi-config
# Interface Options → SPI → Yes, puis reboot
```

### 2. Copier le projet sur le Pi

Depuis le poste Windows (adapter `benfd@zephyr.local` : utilisateur et nom d'hôte
choisis au flashage de la carte SD). Ne pas copier `.venv/` (binaires Windows) ;
copier impérativement `data/netatmo_token.json` s'il existe — c'est lui qui contient
le refresh token Netatmo à jour, celui du `.env` ayant déjà été consommé :

```bash
ssh benfd@zephyr.local "mkdir -p ~/zephyr/data"
```

```bash
scp -r "D:\Projet Zephyr\src" "D:\Projet Zephyr\deploy" benfd@zephyr.local:zephyr/
```

```bash
scp "D:\Projet Zephyr\pyproject.toml" "D:\Projet Zephyr\.env" benfd@zephyr.local:zephyr/
```

```bash
scp "D:\Projet Zephyr\data\netatmo_token.json" benfd@zephyr.local:zephyr/data/
```

### 3. Installer les dépendances

```bash
sudo apt update && sudo apt install -y git python3-venv python3-pip python3-dev swig liblgpio-dev libopenjp2-7 fonts-dejavu-core
cd /home/benfd/zephyr
python3 -m venv .venv
.venv/bin/pip install -e .
# bibliothèque officielle Waveshare (fournit le paquet waveshare_epd)
.venv/bin/pip install "git+https://github.com/waveshareteam/e-Paper.git#subdirectory=RaspberryPi_JetsonNano/python"
# dépendances matérielles que le setup Waveshare ne déclare pas
.venv/bin/pip install spidev gpiozero lgpio
```

Le Pi doit être à l'heure locale : `sudo timedatectl set-timezone Europe/Paris`.

### 4. Créer l'application Netatmo et obtenir le refresh token

*(déjà fait si `.env` et `data/netatmo_token.json` ont été copiés depuis le poste dev
— passer à l'étape suivante)*

1. Aller sur <https://dev.netatmo.com>, se connecter avec le compte de la station.
2. **My apps → Create** : nom/description libres. Récupérer **client ID** et
   **client secret**.
3. Sur la page de l'app, section **Token generator** : choisir le scope
   `read_station` et générer. Copier le **refresh token**.
4. Renseigner le tout dans `.env` :

```bash
cp .env.example .env
nano .env   # NETATMO_CLIENT_ID, NETATMO_CLIENT_SECRET, NETATMO_REFRESH_TOKEN
```

**Pièces intérieures** : le bandeau affiche jusqu'à deux pièces (station de base
incluse — c'est elle qui mesure le salon en général). Attention : l'API météo
n'expose **pas** les noms de pièces de l'app ; elle renvoie le `module_name` de
chaque module, et pour la base souvent un `station_name` auto-généré du genre
« Maison (Indoor) ». D'où l'alias d'affichage dans `.env` :

```
NETATMO_INDOOR_MODULES=Maison (Indoor)=Salon,Chambre
```

(sélectionne et ordonne par nom API, insensible à la casse ; la partie après `=`
est le nom affiché ; vide = toutes les pièces trouvées, base en premier)

> **Rotation des tokens** : Netatmo remplace le refresh token à chaque
> rafraîchissement. Le token courant est persisté dans `data/netatmo_token.json`
> (celui du `.env` ne sert qu'au premier lancement). En cas d'erreur
> `invalid_grant` (token révoqué, par exemple regénéré à la main sur le site) :
> supprimer `data/netatmo_token.json`, regénérer un token via le Token generator,
> le remettre dans `.env`.
>
> **Une seule instance à la fois** : chaque refresh invalide le token précédent.
> Une fois le Pi en service, arrêter le watcher du poste dev (`--watch`), sinon les
> deux machines se volent le token à tour de rôle (`invalid_grant` garanti). Pour
> faire tourner les deux, générer un second refresh token dédié dans le Token
> generator et le donner au Pi.

### 5. Premier test

```bash
cd /home/benfd/zephyr
.venv/bin/python -m zephyr.main --dev   # vérifie la collecte, écrit out/dashboard.png
.venv/bin/python -m zephyr.main         # affiche sur l'écran e-ink
```

### 5 bis. Tester depuis le PC en attendant l'écran (facultatif)

Le Pi génère, le PC regarde — sans matériel ni vrai serveur web (module standard
Python, temporaire, disparaît au reboot) :

```bash
cd ~/zephyr && nohup .venv/bin/python -m zephyr.main --dev --watch 15 > /tmp/zephyr-watch.log 2>&1 &
cd ~/zephyr && nohup python3 -m http.server 8000 --directory out > /dev/null 2>&1 &
```

puis ouvrir `http://zephyr.local:8000/preview.html` depuis un navigateur du réseau
local. Avant d'activer le timer (étape 6), tout arrêter :

```bash
pkill -f "zephyr.main --dev --watch" ; pkill -f "http.server 8000"
```

### 5 ter. Brancher l'écran (à sa réception)

**Toujours Pi éteint** (`sudo poweroff`, attendre la LED verte éteinte, débrancher) :

1. **Nappe → HAT** : soulever le petit loquet du connecteur FPC du HAT, insérer la
   nappe de la dalle à fond (contacts côté carte, suivre la sérigraphie), rabattre
   le loquet. La nappe est fragile : ne pas la plier à angle vif.
2. **Interrupteurs du HAT** : `Display Config` sur **B**, `Interface Config` sur
   **0** (positions d'usine normalement — vérifier).
3. **HAT → Pi** : enficher le HAT sur les 40 broches GPIO, bien aligné et à fond.
4. Rebrancher l'alimentation.

Le full refresh fait clignoter l'écran en noir/blanc pendant ~4 s : c'est normal
(c'est le cycle anti-ghosting). Éviter le plein soleil direct (UV) pour la dalle.

### 6. Service systemd

```bash
sudo cp deploy/zephyr.service deploy/zephyr.timer /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now zephyr.timer
```

Vérifications :

```bash
systemctl list-timers zephyr.timer      # prochaine échéance
journalctl -u zephyr.service -f         # logs de collecte/rendu
```

### 7. Miroir web de l'écran (facultatif)

Le service écrit `out/dashboard.png` à chaque cycle, même en mode écran. Pour
consulter l'affichage depuis n'importe quel appareil du réseau local :

```bash
sudo cp ~/zephyr/deploy/zephyr-preview.service /etc/systemd/system/
sudo systemctl daemon-reload && sudo systemctl enable --now zephyr-preview.service
```

puis ouvrir `http://zephyr.local:8000/preview.html` — miroir exact de la dalle,
rechargé automatiquement (serveur de fichiers statique du module standard Python,
visible du LAN uniquement).

Pour changer l'intervalle, éditer `OnUnitActiveSec=` dans le timer (puis
`daemon-reload`). Si le projet n'est pas dans `/home/benfd/zephyr` ou que
l'utilisateur n'est pas `pi`, adapter `WorkingDirectory`, `ExecStart` et `User`
dans `zephyr.service`.

## Dépannage

- **Cartouche « ! DONNÉES DE HH:MM »** : au moins une source est servie depuis le
  cache (ou la mesure Netatmo a plus d'une heure). Regarder `journalctl -u
  zephyr.service` — la cause (timeout, 401, modèle indisponible) y est logguée.
- **`invalid_grant` au refresh Netatmo** : voir l'encadré rotation ci-dessus.
- **Erreur GPIO/SPI à l'affichage** : vérifier que le SPI est activé
  (`ls /dev/spidev*`) et que le HAT est bien enfiché. Sur Bookworm, si la lib
  Waveshare se plaint de GPIO : `.venv/bin/pip install gpiozero lgpio`.
- **Police manquante** (`RuntimeError: Aucune police trouvée`) : installer
  `fonts-dejavu-core` — Raspberry Pi OS **Lite** ne l'embarque pas, contrairement
  à la version bureau. Sur un poste Windows, Segoe UI/Arial sont utilisées.
