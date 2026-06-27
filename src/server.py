#!/usr/bin/env python3
"""Minimal MCP server for Google Workspace via gws CLI."""
import base64, json, os, subprocess, sys
from datetime import datetime

os.environ["GOOGLE_WORKSPACE_CLI_KEYRING_BACKEND"] = "file"

def rpc_result(id_, result):
    return {"jsonrpc":"2.0","id":id_,"result":result}

def rpc_error(id_, code, msg):
    return {"jsonrpc":"2.0","id":id_,"error":{"code":code,"message":msg}}

def do_initialize(_p):
    return {"protocolVersion":"2025-03-26","capabilities":{"tools":{}},"serverInfo":{"name":"gws-mcp","version":"1.0.0"}}

def do_tools_list(_p):
    return {"tools":[
        {"name":"gws_calendar_list_events","description":"List calendar events. Returns: summary, start, end, location. Params: calendarId, timeMin, timeMax (ISO 8601), maxResults","inputSchema":{"type":"object","properties":{"calendarId":{"type":"string"},"timeMin":{"type":"string"},"timeMax":{"type":"string"},"maxResults":{"type":"integer"}}}},
        {"name":"gws_gmail_list_messages","description":"List Gmail message IDs. Use gws_gmail_get_message to read content. Params: maxResults, query (Gmail search syntax)","inputSchema":{"type":"object","properties":{"maxResults":{"type":"integer"},"query":{"type":"string"}}}},
        {"name":"gws_gmail_get_message","description":"Get Gmail message details. ALWAYS set includeBody=true to get the full decoded email body text. Without it only returns headers+snippet. Params: messageId (required), includeBody (set true for body)","inputSchema":{"type":"object","required":["messageId"],"properties":{"messageId":{"type":"string"},"includeBody":{"type":"boolean","description":"MUST set to true to get email body text"}}}},
        {"name":"gws_drive_list_files","description":"List Drive files. Params: pageSize, query, orderBy","inputSchema":{"type":"object","properties":{"pageSize":{"type":"integer"},"query":{"type":"string"},"orderBy":{"type":"string"}}}},
        {"name":"gws_drive_get_file","description":"Get Drive file metadata by ID. Returns: name, mimeType, size, createdTime, webViewLink. Params: fileId (required)","inputSchema":{"type":"object","required":["fileId"],"properties":{"fileId":{"type":"string"}}}},
        {"name":"gws_drive_download_file","description":"Download a Drive file. DO NOT set outputPath - it auto-saves to ~/Development/HermesProject/hermes-data/workspace/google_mcp/drive/<timestamp>/<filename>. Returns savedTo (full path) and size. ALWAYS show user the savedTo path. Params: fileId (required), outputPath (optional, only if user wants custom location)","inputSchema":{"type":"object","required":["fileId"],"properties":{"fileId":{"type":"string"},"outputPath":{"type":"string","description":"Only set if user wants custom location. Default: auto workspace path"}}}},
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

    if name == "gws_calendar_list_events":
        pd = {"calendarId": args.get("calendarId","primary")}
        for k in ("timeMin","timeMax","maxResults"):
            if k in args: pd[k] = args[k]
        data = run_gws(["gws","calendar","events","list","--params",json.dumps(pd)])
        # Simplify output
        items = data.get("items",[])
        result = [{"summary":e.get("summary",""),"start":e.get("start",{}),"end":e.get("end",{}),"location":e.get("location","")} for e in items]

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
                # Fallback: check body directly
                if not body_text and "data" in part.get("body", {}):
                    try:
                        body_text = base64.urlsafe_b64decode(part["body"]["data"]).decode("utf-8", errors="replace")
                    except: pass
                return bool(body_text)
            extract_body(payload)
            result["body"] = body_text[:5000] if body_text else "(no text body found)"

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
        data = run_gws(["gws","drive","files","get","--params",json.dumps({"fileId":fid,"fields":"id,name,mimeType,size,createdTime,webViewLink,owners"})])
        result = data

    elif name == "gws_drive_download_file":
        fid = args["fileId"]
        base = args.get("outputPath", os.path.expanduser("~/Development/HermesProject/hermes-data/workspace/google_mcp/drive"))
        # Get file metadata for original name
        meta = run_gws(["gws","drive","files","get","--params",json.dumps({"fileId":fid,"fields":"name"})])
        fname = meta.get("name", fid)
        # Create timestamped subdirectory
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
