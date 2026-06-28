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
─────────────────────────       ─────────────────────
config.yaml:                       
  gws-mcp:                    POST /mcp (JSON-RPC)
    url: http://172.17.0.1 ───► http_server.py (Port 8777)
    :8777/mcp                      │
                                   │ subprocess stdin/stdout
                                   ▼
                               server.py (MCP Engine)
                                   │
                                   │ subprocess CLI
                                   ▼
                               gws CLI (OAuth 2.0)
                                   │
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

## Tools

| Tool | Dienst | Beschreibung |
|------|--------|-------------|
| `gws_calendar_list_events` | Calendar | Events auflisten (Zeitraum, max. Anzahl) |
| `gws_gmail_list_messages` | Gmail | E-Mail-IDs auflisten (mit Suchfilter) |
| `gws_gmail_get_message` | Gmail | E-Mail-Inhalt + Body (includeBody=true) |
| `gws_drive_list_files` | Drive | Dateien/Ordner auflisten (mit Suchfilter) |
| `gws_drive_get_file` | Drive | Datei-Metadaten abrufen |
| `gws_drive_download_file` | Drive | Datei herunterladen → workspace/ |

## Voraussetzungen

- **gws CLI** (`npm install -g @googleworkspace/cli`)
- **OAuth 2.0 Desktop-Client** (Google Cloud Console → Credentials)
- **Authentifizierung** via `gws auth login`

## Schnellstart

```bash
# 1. Abhängigkeiten installieren
npm install -g @googleworkspace/cli

# 2. Authentifizieren (einmalig)
GOOGLE_WORKSPACE_CLI_KEYRING_BACKEND=file gws auth login

# 3. Server starten
git clone https://github.com/MAghadavoodi/HermesGoogleMCP.git
cd HermesGoogleMCP
python3 src/http_server.py &

# 4. Hermes config.yaml
mcp_servers:
  gws-mcp:
    url: http://172.17.0.1:8777/mcp
    enabled: true

platform_toolsets:
  cli:
  - gws-mcp
  matrix:
  - gws-mcp

# 5. Reload
hermes mcp reload
```

## Tests

```bash
python3 tests/test_calendar.py   # 2/2 ✅
python3 tests/test_gmail.py      # 2/2 ✅
python3 tests/test_drive.py      # 3/3 ✅
```

## Projektstruktur

```
HermesGoogleMCP/
├── src/
│   ├── server.py          # MCP JSON-RPC Engine (6 Tools)
│   └── http_server.py     # HTTP-Wrapper (Port 8777)
├── tests/
│   ├── test_calendar.py
│   ├── test_gmail.py
│   └── test_drive.py
├── docs/
│   └── ARCHITECTURE.md    # Detaillierte Architektur-Doku
├── Dockerfile             # Docker-Image (experimentell)
├── docker-compose.yml     # Docker-Compose (experimentell)
├── requirements.txt       # stdlib-only, keine pip-Abhängigkeiten
└── .gitignore
```

## Lizenz

MIT — siehe [LICENSE](LICENSE)
