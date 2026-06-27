# Google MCP Server — Architektur & Design

> Stand: Juni 2026 · Projektpfad: `~/Development/HermesProject/Google_MCP/`

---

## 1. Überblick

Der **Google MCP Server** (`gws-mcp`) ist ein schlanker, in reinem Python (stdlib-only) implementierter MCP-Server, der Google Workspace APIs (Calendar, Gmail, Drive) über die authentifizierte [gws CLI](https://github.com/google/google-workspace-cli) bereitstellt.

Er wurde entwickelt, weil keiner der drei in der Hermes-Anleitung beschriebenen Wege im Docker-Container-Setup funktionierte (siehe `Fehleranalyse_MCP_Integration.md`).

---

## 2. Architektur

```
┌──────────────────────────────────────────────────────────────┐
│                     Hermes Agent (TUI/Gateway)               │
│                                                              │
│  config.yaml:                                                │
│    mcp_servers:                                              │
│      gws-mcp:                                                │
│        url: http://172.17.0.1:8777/mcp                       │
│        enabled: true                                         │
└──────────────────────┬───────────────────────────────────────┘
                       │ HTTP POST /mcp (JSON-RPC)
                       ▼
┌──────────────────────────────────────────────────────────────┐
│  http_server.py  (Python http.server, Port 8777)             │
│                                                              │
│  • GET  /mcp    → {} (Health-Check für Hermes)               │
│  • POST /mcp    → JSON-RPC an server.py weiterleiten         │
│  • GET  /health → {"status":"ok"}                            │
│                                                              │
│  Content-Type: application/json (Pflicht für Hermes-MCP!)    │
└──────────────────────┬───────────────────────────────────────┘
                       │ subprocess (stdin/stdout)
                       ▼
┌──────────────────────────────────────────────────────────────┐
│  server.py  (MCP JSON-RPC Engine)                            │
│                                                              │
│  • initialize      → Server-Info + Capabilities              │
│  • tools/list      → 6 Tools (Calendar, Gmail, Drive)        │
│  • tools/call      → gws CLI Subprocess                      │
│                                                              │
│  Tools:                                                      │
│  ┌─────────────────────────────────────────────────────────┐ │
│  │ gws_calendar_list_events   │ Kalender auflisten         │ │
│  │ gws_gmail_list_messages    │ E-Mail-IDs auflisten       │ │
│  │ gws_gmail_get_message      │ E-Mail-Inhalt + Body       │ │
│  │ gws_drive_list_files       │ Dateien auflisten          │ │
│  │ gws_drive_get_file         │ Datei-Metadaten            │ │
│  │ gws_drive_download_file    │ Datei herunterladen        │ │
│  └─────────────────────────────────────────────────────────┘ │
└──────────────────────┬───────────────────────────────────────┘
                       │ subprocess (CLI-Aufruf)
                       ▼
┌──────────────────────────────────────────────────────────────┐
│  gws CLI  (Node.js, npm @googleworkspace/cli v0.22.5)        │
│                                                              │
│  Authentifizierung: OAuth 2.0 via Desktop-App-Client         │
│  Tokens: ~/.config/gws/credentials.enc (file-Backend)        │
│  Key:    ~/.config/gws/.encryption_key                       │
│                                                              │
│  Aufrufe:                                                    │
│  • gws calendar events list --params '{...}'                 │
│  • gws gmail users messages list --params '{...}'            │
│  • gws gmail users messages get --params '{...}'             │
│  • gws drive files list --params '{...}'                     │
│  • gws drive files get --params '{...}' --output <file>      │
└──────────────────────┬───────────────────────────────────────┘
                       │ HTTPS (Google API)
                       ▼
┌──────────────────────────────────────────────────────────────┐
│  Google Workspace APIs                                        │
│  • Calendar API v3                                            │
│  • Gmail API v1                                               │
│  • Drive API v3                                               │
└──────────────────────────────────────────────────────────────┘
```

---

## 3. Komponenten

### 3.1 `server.py` — MCP JSON-RPC Engine

**Aufgabe:** Implementiert das MCP-Protokoll (JSON-RPC 2.0 über stdin/stdout).

**Methoden:**
| Methode | Handler | Beschreibung |
|---------|---------|-------------|
| `initialize` | `do_initialize()` | Server-Metadaten + Capabilities |
| `tools/list` | `do_tools_list()` | Alle 6 Tools mit JSON-Schema |
| `tools/call` | `do_tool_call()` | Tool-Ausführung via gws CLI |

**Design-Entscheidungen:**
- **Reines Python stdlib** — keine externen Abhängigkeiten (kein pip install nötig)
- **Stateless** — jeder Request startet einen frischen gws-Prozess
- **Notifications** werden ignoriert (kein `id`-Feld → keine Antwort)
- **Kompakte JSON-Ausgabe** (`separators=(",",":")`) für minimale Übertragung
- **`GOOGLE_WORKSPACE_CLI_KEYRING_BACKEND=file`** — erzwingt file-basiertes Keyring (Container-kompatibel)

### 3.2 `http_server.py` — HTTP-Wrapper

**Aufgabe:** Macht den stdin/stdout-basierten MCP-Server über HTTP erreichbar.

**Endpunkte:**
| Methode | Pfad | Content-Type | Zweck |
|---------|------|-------------|-------|
| GET | `/mcp` | `application/json` | Health-Check (Hermes prüft diesen!) |
| POST | `/mcp` | `application/json` | MCP JSON-RPC Requests |
| GET | `/health` | `application/json` | Docker Health-Check |

**Warum HTTP statt stdio?**
Der Hermes-Gateway-MCP-Client hat einen asyncio-Bug (`unhandled errors in a TaskGroup`), der bei stdio-basierten MCP-Servern auftritt. HTTP-Transport (wie bei `cogninote` und `doc2md`) umgeht diesen Bug.

**Warum `172.17.0.1`?**
Der Gateway läuft im Docker-Container. `172.17.0.1` ist die Docker-Bridge-Gateway-IP, über die der Container den Host erreicht.

### 3.3 `gws` CLI — Google API Client

- **Version:** 0.22.5 (npm `@googleworkspace/cli`)
- **Authentifizierung:** OAuth 2.0 Desktop-App, Tokens in `~/.config/gws/`
- **Keyring-Backend:** `file` (nicht OS-Keyring, da im Container nicht verfügbar)

**Erst-Authentifizierung:**
```bash
npm install -g @googleworkspace/cli
GOOGLE_WORKSPACE_CLI_KEYRING_BACKEND=file gws auth login
```

---

## 4. Datenfluss (Beispiel: "Lade image.jpeg aus Drive")

```
1. Agent ruft: gws_drive_list_files({"query":"name='image.jpeg'"})
2. server.py → gws drive files list --params '{"q":"name='\''image.jpeg'\''"}'
3. Google Drive API → {files: [{id:"118piuw...", name:"image.jpeg", ...}]}
4. server.py → JSON-Antwort mit Datei-Liste
5. Agent ruft: gws_drive_download_file({"fileId":"118piuw..."})
6. server.py → gws drive files get --params '{"fileId":"...","alt":"media"}' --output image.jpeg
7. Google Drive API → Binärdaten (2,6 MB JPEG)
8. server.py → Datei gespeichert unter:
   ~/Development/HermesProject/hermes-data/workspace/google_mcp/drive/20260627_141223/image.jpeg
9. server.py → {"savedTo": "...", "size": 2659950}
10. Agent zeigt Pfad dem Nutzer
```

---

## 5. Verzeichnisstruktur

```
Google_MCP/
├── src/
│   ├── __init__.py          # Package-Info
│   ├── server.py            # MCP JSON-RPC Server (Hauptlogik)
│   └── http_server.py       # HTTP-Wrapper (Port 8777)
├── tests/
│   ├── test_calendar.py     # Kalender-Integrationstests
│   ├── test_gmail.py        # Gmail-Integrationstests
│   └── test_drive.py        # Drive-Integrationstests
├── docs/
│   └── ARCHITECTURE.md      # Diese Datei
├── client_secret.json       # OAuth 2.0 Desktop-Client (NIE in Git!)
├── Dockerfile               # Container-Image
├── docker-compose.yml       # Docker-Compose Setup
├── requirements.txt         # Abhängigkeiten (stdlib only)
└── .gitignore
```

---

## 6. Deployment

### 6.1 Docker Compose (empfohlen)

```bash
cd ~/Development/HermesProject/Google_MCP
docker compose up -d
```

Der Container:
- Bindet Port `8777` an den Host
- Mountet `~/.config/gws/` für gws-Credentials
- Mountet `~/Development/HermesProject/hermes-data/workspace/` für Downloads
- Registriert sich im `hermesproject_default`-Netzwerk

### 6.2 Hermes config.yaml

```yaml
mcp_servers:
  gws-mcp:
    url: http://172.17.0.1:8777/mcp
    enabled: true

platform_toolsets:
  cli:
  - hermes-cli
  - cogninote
  - gws-mcp
```

### 6.3 Direkt (ohne Docker)

```bash
nohup python3 src/http_server.py &>/tmp/gws-mcp.log &
```

---

## 7. Tests

```bash
cd ~/Development/HermesProject/Google_MCP

# Einzeln
python3 tests/test_calendar.py
python3 tests/test_gmail.py
python3 tests/test_drive.py

# Alle
python3 -m pytest tests/ -v
```

**Voraussetzung für Tests:** gws CLI muss authentifiziert sein (`gws auth login`).

---

## 8. Bekannte Einschränkungen

1. **Kein Streaming** — große Dateien werden komplett in den Speicher geladen
2. **gws 0.22.5** — hat keinen nativen MCP-Modus (kein `gws mcp`-Subbefehl)
3. **Kein OAuth-Handling im Server** — Authentifizierung erfolgt einmalig via `gws auth login`
4. **Keine Paginierung** — `gws_gmail_list_messages` gibt nur eine Seite zurück
5. **Kein Export** — Google Docs/Sheets/Slides können nicht als PDF/Office exportiert werden

---

## 9. gws CLI Referenz

| Befehl | Beschreibung |
|--------|-------------|
| `gws auth login` | OAuth-Login (öffnet Browser) |
| `gws auth status` | Auth-Status prüfen |
| `gws calendar events list --params '{...}'` | Kalender auflisten |
| `gws gmail users messages list --params '{...}'` | E-Mails auflisten |
| `gws gmail users messages get --params '{...}'` | Einzelne E-Mail |
| `gws drive files list --params '{...}'` | Dateien auflisten |
| `gws drive files get --params '{...}' --output <pfad>` | Datei herunterladen |
