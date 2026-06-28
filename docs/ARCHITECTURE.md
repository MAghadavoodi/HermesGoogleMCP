# Google MCP Server — Architektur & Design

> Stand: Juni 2026 · Projektpfad: `~/Development/Google_MCP/`
> Version: 2.2.0 (Full CRUD + Attachments + Path Translation + Tempfile Fix)

---

## 1. Überblick

Der **Google MCP Server** (`gws-mcp`) ist ein schlanker, in reinem Python (stdlib-only) implementierter MCP-Server, der Google Workspace APIs (Calendar, Gmail, Drive) über die authentifizierte [gws CLI](https://github.com/google/google-workspace-cli) bereitstellt.

**Version 2.0** erweitert den Server von 6 reinen Lese-Tools auf **14 CRUD-Tools** — Create, Read, Update, Delete für alle drei Services.

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
│  • tools/list      → 14 Tools (CRUD Calendar/Gmail/Drive)    │
│  • tools/call      → gws CLI Subprocess                      │
│                                                              │
│  Tools (14 — Full CRUD):                                     │
│  ┌─────────────────────────────────────────────────────────┐ │
│  │ Calendar (4)                                             │ │
│  │   gws_calendar_list_events       READ                    │ │
│  │   gws_calendar_create_event      CREATE                  │ │
│  │   gws_calendar_update_event      UPDATE                  │ │
│  │   gws_calendar_delete_event      DELETE                  │ │
│  │                                                         │ │
│  │ Gmail (4)                                               │ │
│  │   gws_gmail_list_messages        READ                    │ │
│  │   gws_gmail_get_message          READ                    │ │
│  │   gws_gmail_send_message         CREATE (send + attachments) │ │
│  │   gws_gmail_delete_message       DELETE (trash)          │ │
│  │                                                         │ │
│  │ Drive (6)                                               │ │
│  │   gws_drive_list_files           READ                    │ │
│  │   gws_drive_get_file             READ                    │ │
│  │   gws_drive_download_file        READ                    │ │
│  │   gws_drive_create_file          CREATE (upload)         │ │
│  │   gws_drive_update_file          UPDATE                  │ │
│  │   gws_drive_delete_file          DELETE                  │ │
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
│  Aufrufe (READ):                                             │
│  • gws calendar events list --params '{...}'                 │
│  • gws gmail users messages list --params '{...}'            │
│  • gws gmail users messages get --params '{...}'             │
│  • gws drive files list --params '{...}'                     │
│  • gws drive files get --params '{...}' --output <file>      │
│                                                              │
│  Aufrufe (CREATE):                                           │
│  • gws calendar events insert --params '{...}' --json '{...}'│
│  • gws gmail users messages send --params '{...}' --json '..'│
│  • gws drive files create --json '{...}' --upload <file>    │
│                                                              │
│  Aufrufe (UPDATE):                                           │
│  • gws calendar events update --params '{...}' --json '{...}'│
│  • gws drive files update --params '{...}' --json '{...}'    │
│                                                              │
│  Aufrufe (DELETE):                                           │
│  • gws calendar events delete --params '{...}'              │
│  • gws gmail users messages trash --params '{...}'           │
│  • gws drive files delete --params '{...}'                  │
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

### 3.1 `server.py` — MCP JSON-RPC Engine (v2.2.0)

**Aufgabe:** Implementiert das MCP-Protokoll (JSON-RPC 2.0 über stdin/stdout).

**Methoden:**
| Methode | Handler | Beschreibung |
|---------|---------|-------------|
| `initialize` | `do_initialize()` | Server-Metadaten + Capabilities (v2.2.0) |
| `tools/list` | `do_tools_list()` | Alle 14 Tools mit JSON-Schema |
| `tools/call` | `do_tool_call()` | Tool-Ausführung via gws CLI |

**Design-Entscheidungen:**
- **Reines Python stdlib** — keine externen Abhängigkeiten
- **Stateless** — jeder Request startet einen frischen gws-Prozess
- **Path Translation** — Docker-Pfade (`/opt/data/...`) → Host-Pfade (`~/Development/.../hermes-data/...`) automatisch
- **Gmail Send** — baut MIME-Nachricht via `email.mime.text`, Base64-kodiert als `raw`; Attachments via `MIMEMultipart` + `MIMEBase`
- **Drive Create/Update** — `content` schreibt in Temp-Datei im **CWD** (`dir="."`), da gws CLI `--upload` nur mit Dateien im aktuellen Verzeichnis erlaubt
- **Calendar CRUD** — `insert`/`update`/`delete` mit `--json` Body
- **Gmail Delete** — verwendet `trash` statt `delete` (sicherer)

### 3.2 `http_server.py` — HTTP-Wrapper

**Aufgabe:** Macht den stdin/stdout-basierten MCP-Server über HTTP erreichbar.

**Endpunkte:**
| Methode | Pfad | Content-Type | Zweck |
|---------|------|-------------|-------|
| GET | `/mcp` | `application/json` | Health-Check (Hermes prüft diesen!) |
| POST | `/mcp` | `application/json` | MCP JSON-RPC Requests |
| GET | `/health` | `application/json` | Docker Health-Check |

**Warum HTTP statt stdio?**
Der Hermes-Gateway-MCP-Client hat einen asyncio-Bug (`unhandled errors in a TaskGroup`), der bei stdio-basierten MCP-Servern auftritt. HTTP-Transport umgeht diesen Bug.

### 3.3 `gws` CLI — Google API Client

- **Version:** 0.22.5 (npm `@googleworkspace/cli`)
- **Authentifizierung:** OAuth 2.0 Desktop-App, Tokens in `~/.config/gws/`
- **Keyring-Backend:** `file` (nicht OS-Keyring)

**Erst-Authentifizierung:**
```bash
npm install -g @googleworkspace/cli
GOOGLE_WORKSPACE_CLI_KEYRING_BACKEND=file gws auth login
```

---

## 4. CRUD-Matrix

| Service | CREATE | READ | UPDATE | DELETE |
|---|---|---|---|---|
| **Calendar** | `create_event` (insert) | `list_events` | `update_event` | `delete_event` |
| **Gmail** | `send_message` (send) | `list_messages`, `get_message` | — (nicht via gws CLI) | `delete_message` (trash) |
| **Drive** | `create_file` (create+upload) | `list_files`, `get_file`, `download_file` | `update_file` | `delete_file` |

---

## 5. Datenfluss (Beispiel: "Sende E-Mail")

```
1. Agent ruft: gws_gmail_send_message({"to":"user@example.com","subject":"Test","body":"Hallo"})
2. server.py → baut MIME-Nachricht (email.mime.text.MIMEText)
3. server.py → Base64-kodiert → {"raw":"Q29udGVudC1UeXBlOiB0ZXh0L3Bs..."}
4. server.py → gws gmail users messages send --params '{"userId":"me"}' --json '{"raw":"..."}'
5. Google Gmail API → {id:"18ab...", threadId:"18ab...", labelIds:["SENT"]}
6. server.py → {"id":"18ab...","threadId":"18ab...","sent":true}
```

### 5.1 Sende E-Mail mit Attachment

```
1. Agent ruft: gws_gmail_send_message({"to":"abap.core@gmail.com","subject":"Test","body":"Text","attachments":"/tmp/report.pdf"})
2. server.py → erkennt attachments-Parameter → baut MIMEMultipart
3. server.py → MIMEText (body) + MIMEBase (attachment, base64-kodiert)
4. server.py → gesamte MIME-Message Base64-kodiert → {"raw":"..."}
5. server.py → gws gmail users messages send --params '{"userId":"me"}' --json '{"raw":"..."}'
6. Google Gmail API → {id:"19f0...", threadId:"19f0...", labelIds:["SENT"]}
7. server.py → {"id":"19f0...","sent":true,"attachments":1}
```

### 5.2 Path Translation (Docker → Host)

```
1. Hermes-Agent (Docker) ruft: attachments="/opt/data/workspace/report.pdf"
2. server.py → Übersetzung: "/opt/data/" → "~/Development/HermesProject/hermes-data/"
3. server.py → öffnet Host-Datei: ~/Development/HermesProject/hermes-data/workspace/report.pdf
4. server.py → bettet Datei als MIME-Attachment ein
```

Der gws-mcp Server läuft auf dem **Host** (nicht im Docker). Der Hermes-Agent im Container sieht Dateien unter `/opt/data/...`. Die Übersetzung stellt sicher, dass der Server die korrekten Host-Pfade verwendet.

---

## 6. Datenfluss (Beispiel: "Erstelle Kalender-Eintrag")

```
1. Agent ruft: gws_calendar_create_event({"summary":"Meeting","start":"2026-07-01T10:00:00+02:00","end":"2026-07-01T11:00:00+02:00","attendees":"team@example.com"})
2. server.py → baut Event-Body mit start/end/attendees
3. server.py → gws calendar events insert --params '{"calendarId":"primary"}' --json '{...}'
4. Google Calendar API → {id:"abc123...", htmlLink:"https://...", status:"confirmed"}
5. server.py → {"id":"abc123...","summary":"Meeting","htmlLink":"https://...","status":"confirmed"}
```

---

## 7. Datenfluss (Beispiel: "Lade Datei in Drive hoch")

```
1. Agent ruft: gws_drive_create_file({"name":"bericht.txt","mimeType":"text/plain","content":"Inhalt..."})
2. server.py → schreibt content in tempfile.NamedTemporaryFile
3. server.py → gws drive files create --json '{"name":"bericht.txt","mimeType":"text/plain"}' --upload /tmp/tmpXXX
4. Google Drive API → {id:"xyz789...", name:"bericht.txt", webViewLink:"https://..."}
5. server.py → löscht Temp-Datei
6. server.py → {"id":"xyz789...","name":"bericht.txt","webViewLink":"https://..."}
```

---

## 8. Verzeichnisstruktur

```
Google_MCP/
├── src/
│   ├── __init__.py          # Package-Info
│   ├── server.py            # MCP JSON-RPC Server v2.0.0 (14 CRUD-Tools)
│   └── http_server.py       # HTTP-Wrapper (Port 8777)
├── tests/
│   ├── test_all_crud.py     # Alle CRUD-Tests (14 Tests)
│   ├── test_calendar.py     # Calendar CRUD (4 Tests)
│   ├── test_gmail.py        # Gmail CRUD (4 Tests)
│   └── test_drive.py        # Drive CRUD (6 Tests)
├── docs/
│   └── ARCHITECTURE.md      # Diese Datei
├── client_secret.json       # OAuth 2.0 Desktop-Client (NIE in Git!)
├── Dockerfile               # Container-Image
├── docker-compose.yml       # Docker-Compose Setup
├── requirements.txt         # Abhängigkeiten (stdlib only)
└── .gitignore
```

---

## 9. Deployment

### 9.1 Direkt (Host — empfohlen)

```bash
nohup python3 src/http_server.py &>/tmp/gws-mcp.log &
```

### 9.2 Docker Compose

```bash
cd ~/Development/Google_MCP
docker compose up -d
```

### 9.3 Hermes config.yaml

```yaml
mcp_servers:
  gws-mcp:
    url: http://172.17.0.1:8777/mcp
    enabled: true

platform_toolsets:
  cli:
  - hermes-cli
  - gws-mcp
  matrix:
  - hermes-matrix
  - gws-mcp
```

---

## 10. Tests

```bash
cd ~/Development/Google_MCP

# Alle CRUD-Tests (14 Tests)
python3 tests/test_all_crud.py

# Einzeln
python3 tests/test_calendar.py    # 4 Tests (list/create/update/delete)
python3 tests/test_gmail.py       # 4 Tests (list/get/send/delete)
python3 tests/test_drive.py       # 6 Tests (list/get/create/update/delete/download)
```

**Voraussetzung:** gws CLI muss authentifiziert sein (`gws auth login`).

---

## 11. gws CLI Referenz (CRUD)

| Befehl | Operation |
|--------|-----------|
| `gws auth login` | OAuth-Login |
| `gws auth status` | Auth-Status |
| **Calendar** | |
| `gws calendar events list --params '{...}'` | READ |
| `gws calendar events insert --params '{...}' --json '{...}'` | CREATE |
| `gws calendar events update --params '{...}' --json '{...}'` | UPDATE |
| `gws calendar events delete --params '{...}'` | DELETE |
| **Gmail** | |
| `gws gmail users messages list --params '{...}'` | READ |
| `gws gmail users messages get --params '{...}'` | READ |
| `gws gmail users messages send --params '{...}' --json '{...}'` | CREATE |
| `gws gmail users messages trash --params '{...}'` | DELETE |
| **Drive** | |
| `gws drive files list --params '{...}'` | READ |
| `gws drive files get --params '{...}'` | READ (metadata) |
| `gws drive files get --params '{"alt":"media"}' --output <pfad>` | READ (download) |
| `gws drive files create --json '{...}' --upload <pfad>` | CREATE |
| `gws drive files update --params '{...}' --json '{...}'` | UPDATE |
| `gws drive files delete --params '{...}'` | DELETE |

---

## 12. Bekannte Einschränkungen

1. **Kein Streaming** — große Dateien werden komplett in den Speicher geladen
2. **gws 0.22.5** — hat keinen nativen MCP-Modus
3. **Kein OAuth-Handling im Server** — Authentifizierung via `gws auth login`
4. **Gmail Update** — nicht via gws CLI unterstützt (nur `modify` für Labels)
5. **Kein Export** — Google Docs/Sheets/Slides können nicht als PDF/Office exportiert werden
6. **Temp-Dateien für Drive Create/Update** — Text-Inhalte werden temporär gespeichert
7. **Gmail Attachments** — Dateien werden Base64-kodiert in die MIME-Nachricht eingebettet (kein Streaming großer Dateien)
