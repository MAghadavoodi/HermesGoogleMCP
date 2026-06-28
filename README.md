# Hermes Google MCP Server

> Schlanker MCP-Server für Google Workspace (Calendar · Gmail · Drive) — entwickelt für den [Hermes Agent](https://github.com/NousResearch/hermes-agent) im Docker-Setup.

## Warum dieses Projekt?

Die in der Hermes-Dokumentation beschriebenen drei Standard-Wege zur Google-Anbindung scheiterten im Docker-Container-Setup:

| Weg | Problem |
|-----|---------|
| **gws CLI MCP** | `gws` v0.22.5 hat keinen `mcp`-Subbefehl |
| **google_workspace_mcp** | asyncio `TaskGroup`-Fehler beim Gateway-Connect |
| **Google Remote MCP** | OAuth-Flow im Container nicht möglich (kein Browser) |

Dieser Server löst alle drei Probleme: Reines Python (stdlib-only), HTTP-Transport (umgeht den asyncio-Bug), nutzt die funktionierende `gws`-CLI-Authentifizierung.

## Architektur

```
Hermes Gateway (Docker)         Host (masoud)
─────────────────────────       ─────────────────────────
config.yaml:                    ┌──────────────────────┐
  gws-mcp:                      │ gws-mcp Container    │
    url: http://172.17.0.1 ───► │  http_server.py      │
    :8777/mcp                   │  :8777 → server.py   │
                                │      → gws CLI       │
                                │      → Google APIs   │
                                └──────────────────────┘
                                  ▲ Port 8777 (forwarded)
                                  ▼
                          Google Workspace APIs
                          (Calendar v3 · Gmail v1 · Drive v3)
```

## Container-Resilienz

Der Docker-Container ist gegen Port-Konflikte und unsauberes Herunterfahren abgesichert:

| Maßnahme | Ort | Wirkung |
|----------|-----|---------|
| `init: true` | `docker-compose.yml` | Tini als Init-Prozess — fängt Signale korrekt ab, verhindert Zombie-Prozesse |
| `stop_grace_period: 10s` | `docker-compose.yml` | 10 Sekunden für sauberes Herunterfahren vor SIGKILL |
| `signal.signal(SIGTERM, ...)` | `http_server.py` | Schließt den HTTP-Socket bei Docker-Stop — Port sofort frei |
| `restart: unless-stopped` | `docker-compose.yml` | Container startet nach Crash oder Reboot automatisch neu |

**Ablauf bei `docker stop` / Reboot:**
1. Docker sendet `SIGTERM` an den Container
2. `http_server.py` fängt das Signal und ruft `server.server_close()` auf
3. Port 8777 wird sofort freigegeben — kein Port-Konflikt beim Neustart
4. Container beendet mit Exit-Code `0` (statt 137/SIGKILL)
5. Nach Reboot startet Docker den Container automatisch (`unless-stopped`)

**Manuelle Fehlerbehebung** (falls Container im Status `Exited (137)` hängt):
```bash
docker start gws-mcp
```

## Attachments & Pfadübersetzung

`gws_gmail_send_message` unterstützt Dateianhänge per MIME-Multipart. Da unterschiedliche MCP-Clients
verschiedene Pfadformate übergeben, übersetzt der Server automatisch:

| Quelle | Pfadbeispiel | Container-Pfad |
|--------|-------------|----------------|
| **Hermes TUI** (Docker) | `/opt/data/workspace/report.pdf` | `/workspace/report.pdf` |
| **OpenCode** (Host) | `/home/masoud/.../workspace/report.pdf` | `/workspace/report.pdf` |

**Funktionsweise** (`server.py` Zeile 176–183):

```python
# 1. Hermes Docker-Pfad: /opt/data/workspace/ → /workspace/
p = p.replace("/opt/data/workspace/", "/workspace/")

# 2. Host-Pfad (OpenCode & Co.): Extrahiere alles ab /workspace/
parts = p.split("/workspace/", 1)
if len(parts) == 2:
    p = "/workspace/" + parts[1]
```

Voraussetzung: Der Workspace ist als Volume in den Container eingehängt
(`docker-compose.yml` → `~/Development/HermesProject/hermes-data/workspace:/workspace`).

## Tools

| Tool | Dienst | CRUD | Beschreibung |
|------|--------|------|-------------|
| `gws_calendar_list_events` | Calendar | READ | Events auflisten (Zeitraum, max. Anzahl) |
| `gws_calendar_create_event` | Calendar | CREATE | Termin erstellen mit Teilnehmern |
| `gws_calendar_update_event` | Calendar | UPDATE | Termin ändern |
| `gws_calendar_delete_event` | Calendar | DELETE | Termin löschen |
| `gws_gmail_list_messages` | Gmail | READ | E-Mail-IDs auflisten (Suchfilter) |
| `gws_gmail_get_message` | Gmail | READ | E-Mail-Inhalt + Body (includeBody=true) |
| `gws_gmail_send_message` | Gmail | CREATE | E-Mail senden mit Anhängen (MIME) |
| `gws_gmail_delete_message` | Gmail | DELETE | E-Mail in Papierkorb verschieben |
| `gws_drive_list_files` | Drive | READ | Dateien/Ordner auflisten |
| `gws_drive_get_file` | Drive | READ | Datei-Metadaten abrufen |
| `gws_drive_create_file` | Drive | CREATE | Datei erstellen/hochladen |
| `gws_drive_update_file` | Drive | UPDATE | Datei ändern/ersetzen |
| `gws_drive_delete_file` | Drive | DELETE | Datei permanent löschen |
| `gws_drive_download_file` | Drive | READ | Datei herunterladen → workspace/ |

## Voraussetzungen

- **gws CLI** (`npm install -g @googleworkspace/cli`)
- **OAuth 2.0 Desktop-Client** (Google Cloud Console → Credentials)
- **Authentifizierung** via `gws auth login`

## Deployment

Der Server läuft als Docker-Container mit systemd-Integration für automatischen Start nach Reboot.

### Docker Compose

```bash
# 1. Projekt klonen
git clone https://github.com/MAghadavoodi/HermesGoogleMCP.git ~/Development/Google_MCP
cd ~/Development/Google_MCP

# 2. Container bauen & starten
docker compose up -d gws-mcp

# 3. Status prüfen
docker ps --filter name=gws-mcp
```

### systemd-Service (automatischer Start)

```bash
# Service aktivieren (startet Container bei Login)
systemctl --user enable --now gws-mcp.service

# Service verwalten
systemctl --user status gws-mcp
systemctl --user stop gws-mcp
systemctl --user start gws-mcp
```

Die systemd-Unit delegiert an Docker (`docker start`/`docker stop`).  
Die `restart: unless-stopped`-Policy im Container stellt sicher, dass er bei Crash oder Reboot automatisch neu startet.

### Hermes-Konfiguration

In `hermes-data/config.yaml`:

```yaml
mcp_servers:
  gws-mcp:
    url: http://172.17.0.1:8777/mcp
    enabled: true

platform_toolsets:
  cli:
  - gws-mcp
  matrix:
  - gws-mcp
```

## Tests

```bash
python3 tests/test_calendar.py   # Calendar CRUD
python3 tests/test_gmail.py      # Gmail CRUD
python3 tests/test_drive.py      # Drive CRUD
python3 tests/test_all_crud.py   # Full CRUD integration
```

## Projektstruktur

```
Google_MCP/
├── src/
│   ├── server.py          # MCP JSON-RPC Engine (CRUD + Attachments)
│   └── http_server.py     # HTTP-Wrapper (Port 8777, SIGTERM-Handler)
├── tests/
│   ├── test_calendar.py
│   ├── test_gmail.py
│   ├── test_drive.py
│   └── test_all_crud.py
├── docs/
│   └── ARCHITECTURE.md    # Detaillierte Architektur-Doku
├── Dockerfile             # Docker-Image (ubuntu:24.04 + gws CLI)
├── docker-compose.yml     # Docker Compose (init, stop_grace_period)
├── requirements.txt       # stdlib-only, keine pip-Abhängigkeiten
└── .gitignore
```

## Lizenz

MIT — siehe [LICENSE](LICENSE)
