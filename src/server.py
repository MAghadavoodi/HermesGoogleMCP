#!/usr/bin/env python3
"""Minimal MCP server for Google Workspace via gws CLI — full CRUD + attachments + path translation."""
import base64, json, os, subprocess, sys
from datetime import datetime

os.environ["GOOGLE_WORKSPACE_CLI_KEYRING_BACKEND"] = os.environ.get("GOOGLE_WORKSPACE_CLI_KEYRING_BACKEND", "keyring")

def rpc_result(id_, result):
    return {"jsonrpc":"2.0","id":id_,"result":result}

def rpc_error(id_, code, msg):
    return {"jsonrpc":"2.0","id":id_,"error":{"code":code,"message":msg}}

def do_initialize(_p):
    return {"protocolVersion":"2025-03-26","capabilities":{"tools":{}},"serverInfo":{"name":"gws-mcp","version":"2.2.0"}}

def do_tools_list(_p):
    return {"tools":[
        # ── Calendar ──
        {"name":"gws_calendar_list_events","description":"List calendar events (READ). Returns: summary, start, end, location. Params: calendarId, timeMin, timeMax (ISO 8601), maxResults","inputSchema":{"type":"object","properties":{"calendarId":{"type":"string"},"timeMin":{"type":"string"},"timeMax":{"type":"string"},"maxResults":{"type":"integer"}}}},
        {"name":"gws_calendar_create_event","description":"Create a new calendar event (CREATE). Params: calendarId (required), summary, description, location, start (ISO 8601 dateTime), end (ISO 8601 dateTime), timeZone, attendees (comma-separated emails). Returns created event with id and htmlLink.","inputSchema":{"type":"object","required":["calendarId","summary","start","end"],"properties":{"calendarId":{"type":"string","description":"Calendar ID, default 'primary'"},"summary":{"type":"string","description":"Event title"},"description":{"type":"string"},"location":{"type":"string"},"start":{"type":"string","description":"Start dateTime in ISO 8601, e.g. 2026-07-01T10:00:00+02:00"},"end":{"type":"string","description":"End dateTime in ISO 8601"},"timeZone":{"type":"string","description":"e.g. Europe/Berlin"},"attendees":{"type":"string","description":"Comma-separated email addresses"}}}},
        {"name":"gws_calendar_update_event","description":"Update an existing calendar event (UPDATE). Params: calendarId, eventId (required), summary, description, location, start, end. Only provided fields will be updated.","inputSchema":{"type":"object","required":["eventId"],"properties":{"calendarId":{"type":"string","default":"primary"},"eventId":{"type":"string"},"summary":{"type":"string"},"description":{"type":"string"},"location":{"type":"string"},"start":{"type":"string"},"end":{"type":"string"},"timeZone":{"type":"string"}}}},
        {"name":"gws_calendar_delete_event","description":"Delete a calendar event (DELETE). Params: calendarId, eventId (required).","inputSchema":{"type":"object","required":["eventId"],"properties":{"calendarId":{"type":"string","default":"primary"},"eventId":{"type":"string"}}}},

        # ── Gmail ──
        {"name":"gws_gmail_list_messages","description":"List Gmail message IDs (READ). Use gws_gmail_get_message to read content. Params: maxResults, query (Gmail search syntax)","inputSchema":{"type":"object","properties":{"maxResults":{"type":"integer"},"query":{"type":"string"}}}},
        {"name":"gws_gmail_get_message","description":"Get Gmail message details (READ). ALWAYS set includeBody=true to get the full decoded email body text. Params: messageId (required), includeBody (set true for body)","inputSchema":{"type":"object","required":["messageId"],"properties":{"messageId":{"type":"string"},"includeBody":{"type":"boolean","description":"MUST set to true to get email body text"}}}},
        {"name":"gws_gmail_send_message","description":"Send an email with optional file attachments via MIME multipart (CREATE). Params: to (required), subject (required), body, cc, bcc, attachments. IMPORTANT: Use the attachments parameter to send PDFs or any files — pass a comma-separated list of absolute file paths (e.g. /opt/data/workspace/report.pdf). Files are Base64-encoded into the MIME message.","inputSchema":{"type":"object","required":["to","subject","body"],"properties":{"to":{"type":"string","description":"Recipient email address(es)"},"subject":{"type":"string","description":"Email subject line"},"body":{"type":"string","description":"Plain text email body"},"cc":{"type":"string","description":"CC recipients"},"bcc":{"type":"string","description":"BCC recipients"},"attachments":{"type":"string","description":"Comma-separated ABSOLUTE file paths to attach as MIME multipart. Example: '/opt/data/workspace/report.pdf,/tmp/image.png'. Files must exist on the local filesystem."}}}},
        {"name":"gws_gmail_delete_message","description":"Move a message to trash (DELETE). Safer than permanent delete. Params: messageId (required).","inputSchema":{"type":"object","required":["messageId"],"properties":{"messageId":{"type":"string"}}}},

        # ── Drive ──
        {"name":"gws_drive_list_files","description":"List Drive files (READ). Params: pageSize, query, orderBy","inputSchema":{"type":"object","properties":{"pageSize":{"type":"integer"},"query":{"type":"string"},"orderBy":{"type":"string"}}}},
        {"name":"gws_drive_get_file","description":"Get Drive file metadata by ID (READ). Returns: name, mimeType, size, createdTime, webViewLink. Params: fileId (required)","inputSchema":{"type":"object","required":["fileId"],"properties":{"fileId":{"type":"string"}}}},
        {"name":"gws_drive_create_file","description":"Upload/create a file in Drive (CREATE). Params: name (required), mimeType, content (text content to write), localPath (absolute path to local file to upload). Use content OR localPath, not both.","inputSchema":{"type":"object","required":["name"],"properties":{"name":{"type":"string","description":"File name in Drive"},"mimeType":{"type":"string","description":"MIME type, default 'text/plain'"},"content":{"type":"string","description":"Text content to write to the file"},"localPath":{"type":"string","description":"Absolute path to local file to upload"},"parents":{"type":"string","description":"Parent folder ID(s), comma-separated"}}}},
        {"name":"gws_drive_update_file","description":"Update a file's metadata or content in Drive (UPDATE). Params: fileId (required), name, mimeType, content, localPath, addParents, removeParents.","inputSchema":{"type":"object","required":["fileId"],"properties":{"fileId":{"type":"string"},"name":{"type":"string","description":"New file name"},"mimeType":{"type":"string"},"content":{"type":"string","description":"New text content"},"localPath":{"type":"string","description":"Path to new file content to upload"},"addParents":{"type":"string","description":"Add parent folder ID(s), comma-separated"},"removeParents":{"type":"string","description":"Remove parent folder ID(s), comma-separated"}}}},
        {"name":"gws_drive_delete_file","description":"Permanently delete a file from Drive (DELETE). Params: fileId (required). WARNING: This cannot be undone.","inputSchema":{"type":"object","required":["fileId"],"properties":{"fileId":{"type":"string"}}}},
        {"name":"gws_drive_download_file","description":"Download a Drive file (READ). Auto-saves to workspace. Params: fileId (required), outputPath (optional).","inputSchema":{"type":"object","required":["fileId"],"properties":{"fileId":{"type":"string"},"outputPath":{"type":"string","description":"Only set if user wants custom location"}}}},
    ]}

def run_gws(cmd):
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    if r.returncode != 0:
        return {"error": r.stderr.strip()}
    try:
        return json.loads(r.stdout)
    except:
        return {"raw": r.stdout.strip()}

def do_tool_call(p):
    name = p.get("name","")
    args = p.get("arguments",{})
    result = None

    # ═══════════════════════════════════════════════════════
    # CALENDAR
    # ═══════════════════════════════════════════════════════

    if name == "gws_calendar_list_events":
        pd = {"calendarId": args.get("calendarId","primary")}
        for k in ("timeMin","timeMax","maxResults"):
            if k in args: pd[k] = args[k]
        data = run_gws(["gws","calendar","events","list","--params",json.dumps(pd)])
        items = data.get("items",[])
        result = [{"id":e.get("id"),"summary":e.get("summary",""),"start":e.get("start",{}),"end":e.get("end",{}),"location":e.get("location",""),"htmlLink":e.get("htmlLink","")} for e in items]

    elif name == "gws_calendar_create_event":
        calendar_id = args.get("calendarId","primary")
        body = {
            "summary": args["summary"],
            "start": {"dateTime": args["start"], "timeZone": args.get("timeZone","Europe/Berlin")},
            "end": {"dateTime": args["end"], "timeZone": args.get("timeZone","Europe/Berlin")},
        }
        for k in ("description","location"):
            if k in args: body[k] = args[k]
        if "attendees" in args:
            body["attendees"] = [{"email": e.strip()} for e in args["attendees"].split(",") if e.strip()]
        data = run_gws(["gws","calendar","events","insert","--params",json.dumps({"calendarId":calendar_id}),"--json",json.dumps(body)])
        if isinstance(data, dict) and "id" in data:
            result = {"id":data["id"],"summary":data.get("summary"),"htmlLink":data.get("htmlLink"),"status":data.get("status"),"created":data.get("created")}
        else:
            result = data

    elif name == "gws_calendar_update_event":
        calendar_id = args.get("calendarId","primary")
        event_id = args["eventId"]
        body = {}
        for k in ("summary","description","location"):
            if k in args: body[k] = args[k]
        if "start" in args: body["start"] = {"dateTime":args["start"],"timeZone":args.get("timeZone","Europe/Berlin")}
        if "end" in args: body["end"] = {"dateTime":args["end"],"timeZone":args.get("timeZone","Europe/Berlin")}
        if not body:
            result = {"error":"No fields to update"}
        else:
            if "start" not in body or "end" not in body:
                existing = run_gws(["gws","calendar","events","get","--params",json.dumps({"calendarId":calendar_id,"eventId":event_id})])
                if "error" not in existing:
                    if "start" not in body and "start" in existing:
                        body["start"] = existing["start"]
                    if "end" not in body and "end" in existing:
                        body["end"] = existing["end"]
            data = run_gws(["gws","calendar","events","update","--params",json.dumps({"calendarId":calendar_id,"eventId":event_id}),"--json",json.dumps(body)])
            if "error" in data:
                result = data
            else:
                result = {"id":data.get("id"),"summary":data.get("summary"),"htmlLink":data.get("htmlLink"),"status":data.get("status"),"updated":data.get("updated")}

    elif name == "gws_calendar_delete_event":
        calendar_id = args.get("calendarId","primary")
        data = run_gws(["gws","calendar","events","delete","--params",json.dumps({"calendarId":calendar_id,"eventId":args["eventId"]})])
        result = {"deleted": True, "eventId": args["eventId"]}

    # ═══════════════════════════════════════════════════════
    # GMAIL
    # ═══════════════════════════════════════════════════════

    elif name == "gws_gmail_list_messages":
        pd = {"userId":"me"}
        if "maxResults" in args: pd["maxResults"] = args["maxResults"]
        if "query" in args: pd["q"] = args["query"]
        data = run_gws(["gws","gmail","users","messages","list","--params",json.dumps(pd)])
        result = data.get("messages",[])
        if isinstance(result, list):
            result = [{"id":m["id"],"threadId":m["threadId"]} for m in result]

    elif name == "gws_gmail_get_message":
        mid = args["messageId"]
        want_body = args.get("includeBody", False)
        fmt = "full" if want_body else "metadata"
        params = {"userId":"me","id":mid,"format":fmt}
        if not want_body:
            params["metadataHeaders"] = ["Subject","From","To","Date","Cc","Bcc"]
        data = run_gws(["gws","gmail","users","messages","get","--params",json.dumps(params)])
        headers = {h["name"]:h["value"] for h in data.get("payload",{}).get("headers",[])}
        result = {
            "id": data.get("id"),
            "threadId": data.get("threadId"),
            "subject": headers.get("Subject",""),
            "from": headers.get("From",""),
            "to": headers.get("To",""),
            "cc": headers.get("Cc",""),
            "date": headers.get("Date",""),
            "snippet": data.get("snippet",""),
            "labelIds": data.get("labelIds",[]),
            "sizeEstimate": data.get("sizeEstimate"),
            "internalDate": data.get("internalDate"),
        }
        if want_body:
            payload = data.get("payload", {})
            body_text = ""
            def extract_body(part):
                nonlocal body_text
                if part.get("mimeType") == "text/plain" and "data" in part.get("body", {}):
                    try:
                        body_text = base64.urlsafe_b64decode(part["body"]["data"]).decode("utf-8", errors="replace")
                    except: pass
                    return True
                for sub in part.get("parts", []):
                    if extract_body(sub): return True
                if not body_text and "data" in part.get("body", {}):
                    try:
                        body_text = base64.urlsafe_b64decode(part["body"]["data"]).decode("utf-8", errors="replace")
                    except: pass
                return bool(body_text)
            extract_body(payload)
            result["body"] = body_text[:5000] if body_text else "(no text body found)"

    elif name == "gws_gmail_send_message":
        import email.mime.text, email.mime.multipart, email.mime.base, email.encoders
        to_emails = args["to"]
        if to_emails.strip().lower() == "me":
            profile = run_gws(["gws","gmail","users","getProfile","--params",json.dumps({"userId":"me"})])
            to_emails = profile.get("emailAddress", "me")

        raw_attachments = [p.strip() for p in args.get("attachments","").split(",") if p.strip()]
        # Translate Docker container paths to host paths
        attachments = []
        for p in raw_attachments:
            p = p.replace("/opt/data/", os.path.expanduser("~/Development/HermesProject/hermes-data/"))
            p = p.replace("/opt/hermes/", os.path.expanduser("~/Development/HermesProject/"))
            attachments.append(p)

        if attachments:
            # Build multipart MIME with attachments
            msg = email.mime.multipart.MIMEMultipart()
            msg["to"] = to_emails
            msg["subject"] = args["subject"]
            msg["from"] = "me"
            if "cc" in args: msg["cc"] = args["cc"]
            if "bcc" in args: msg["bcc"] = args["bcc"]
            msg.attach(email.mime.text.MIMEText(args.get("body",""), "plain", "utf-8"))
            for fpath in attachments:
                if not os.path.isfile(fpath):
                    result = {"error": f"Attachment not found: {fpath}"}
                    break
                else:
                    with open(fpath, "rb") as fh:
                        part = email.mime.base.MIMEBase("application", "octet-stream")
                        part.set_payload(fh.read())
                    email.encoders.encode_base64(part)
                    part.add_header("Content-Disposition", f"attachment; filename=\"{os.path.basename(fpath)}\"")
                    msg.attach(part)
            if "error" in (result or {}):
                pass
            else:
                raw_bytes = msg.as_bytes()
                raw_b64 = base64.b64encode(raw_bytes).decode("ascii")
                data = run_gws(["gws","gmail","users","messages","send","--params",json.dumps({"userId":"me"}),"--json",json.dumps({"raw":raw_b64})])
                result = {"id":data.get("id"),"threadId":data.get("threadId"),"labelIds":data.get("labelIds",[]),"sent":True,"attachments":len(attachments)}
        else:
            msg = email.mime.text.MIMEText(args.get("body",""), "plain", "utf-8")
            msg["to"] = to_emails
            msg["subject"] = args["subject"]
            msg["from"] = "me"
            if "cc" in args: msg["cc"] = args["cc"]
            if "bcc" in args: msg["bcc"] = args["bcc"]
            raw_bytes = msg.as_bytes()
            raw_b64 = base64.b64encode(raw_bytes).decode("ascii")
            data = run_gws(["gws","gmail","users","messages","send","--params",json.dumps({"userId":"me"}),"--json",json.dumps({"raw":raw_b64})])
            result = {"id":data.get("id"),"threadId":data.get("threadId"),"labelIds":data.get("labelIds",[]),"sent":True}

    elif name == "gws_gmail_delete_message":
        data = run_gws(["gws","gmail","users","messages","trash","--params",json.dumps({"userId":"me","id":args["messageId"]})])
        result = {"trashed":True,"messageId":args["messageId"]}

    # ═══════════════════════════════════════════════════════
    # DRIVE
    # ═══════════════════════════════════════════════════════

    elif name == "gws_drive_list_files":
        pd = {}
        if "pageSize" in args: pd["pageSize"] = args["pageSize"]
        if "query" in args: pd["q"] = args["query"]
        if "orderBy" in args: pd["orderBy"] = args["orderBy"]
        data = run_gws(["gws","drive","files","list","--params",json.dumps(pd)])
        files = data.get("files",[])
        result = [{"id":f.get("id"),"name":f.get("name"),"mimeType":f.get("mimeType"),"webViewLink":f.get("webViewLink",""),"size":f.get("size"),"createdTime":f.get("createdTime")} for f in files]

    elif name == "gws_drive_get_file":
        fid = args["fileId"]
        data = run_gws(["gws","drive","files","get","--params",json.dumps({"fileId":fid,"fields":"id,name,mimeType,size,createdTime,webViewLink,owners,parents"})])
        result = data

    elif name == "gws_drive_create_file":
        fname = args["name"]
        mime = args.get("mimeType","text/plain")
        parents = args.get("parents","")
        meta = {"name": fname, "mimeType": mime}
        if parents:
            meta["parents"] = [p.strip() for p in parents.split(",") if p.strip()]
        cmd = ["gws","drive","files","create","--json",json.dumps(meta)]
        if "localPath" in args:
            cmd += ["--upload", args["localPath"]]
        elif "content" in args:
            import tempfile
            tmpf = tempfile.NamedTemporaryFile(mode="w", suffix=".tmp", delete=False, encoding="utf-8", dir=".")
            tmpf.write(args["content"])
            tmpf.close()
            cmd += ["--upload", os.path.basename(tmpf.name)]
        data = run_gws(cmd)
        if "localPath" not in args and "content" in args:
            os.unlink(tmpf.name)
        result = {"id":data.get("id"),"name":data.get("name"),"mimeType":data.get("mimeType"),"webViewLink":data.get("webViewLink",""),"size":data.get("size"),"createdTime":data.get("createdTime")}

    elif name == "gws_drive_update_file":
        fid = args["fileId"]
        meta = {}
        for k in ("name","mimeType"):
            if k in args: meta[k] = args[k]
        if "addParents" in args:
            meta["addParents"] = [p.strip() for p in args["addParents"].split(",") if p.strip()]
        if "removeParents" in args:
            meta["removeParents"] = [p.strip() for p in args["removeParents"].split(",") if p.strip()]
        cmd = ["gws","drive","files","update","--params",json.dumps({"fileId":fid})]
        if meta:
            cmd += ["--json", json.dumps(meta)]
        if "localPath" in args:
            cmd += ["--upload", args["localPath"]]
        elif "content" in args:
            import tempfile
            tmpf = tempfile.NamedTemporaryFile(mode="w", suffix=".tmp", delete=False, encoding="utf-8", dir=".")
            tmpf.write(args["content"])
            tmpf.close()
            cmd += ["--upload", os.path.basename(tmpf.name)]
        data = run_gws(cmd)
        if "localPath" not in args and "content" in args:
            os.unlink(tmpf.name)
        result = {"id":data.get("id"),"name":data.get("name"),"mimeType":data.get("mimeType"),"webViewLink":data.get("webViewLink",""),"modifiedTime":data.get("modifiedTime")}

    elif name == "gws_drive_delete_file":
        data = run_gws(["gws","drive","files","delete","--params",json.dumps({"fileId":args["fileId"]})])
        result = {"deleted":True,"fileId":args["fileId"]}

    elif name == "gws_drive_download_file":
        fid = args["fileId"]
        base = args.get("outputPath", os.path.expanduser("~/Development/HermesProject/hermes-data/workspace/google_mcp/drive"))
        meta = run_gws(["gws","drive","files","get","--params",json.dumps({"fileId":fid,"fields":"name"})])
        fname = meta.get("name", fid)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        out_dir = os.path.join(base, ts)
        out_full = os.path.join(out_dir, fname)
        os.makedirs(out_dir, exist_ok=True)
        r = subprocess.run(["gws","drive","files","get","--params",json.dumps({"fileId":fid,"alt":"media"}),"--output",fname],
                         capture_output=True, text=True, timeout=60, cwd=out_dir)
        if r.returncode != 0:
            result = {"error": r.stderr.strip()}
        else:
            result = {"savedTo": out_full, "size": os.path.getsize(out_full) if os.path.exists(out_full) else 0}

    else:
        return {"content":[{"type":"text","text":json.dumps({"error":"Unknown tool: "+name})}]}

    return {"content":[{"type":"text","text":json.dumps(result, ensure_ascii=False)}]}

HANDLERS = {"initialize":do_initialize,"tools/list":do_tools_list,"tools/call":do_tool_call}

for line in sys.stdin:
    line = line.strip()
    if not line: continue
    try: req = json.loads(line)
    except: continue
    rid = req.get("id")
    if rid is None: continue
    m = req.get("method","")
    p = req.get("params",{})
    h = HANDLERS.get(m)
    if h:
        try: resp = rpc_result(rid, h(p))
        except Exception as e: resp = rpc_error(rid, -32603, str(e))
    else:
        resp = rpc_error(rid, -32601, "Not found: "+m)
    sys.stdout.write(json.dumps(resp, separators=(",",":")) + "\n")
    sys.stdout.flush()
