#!/usr/bin/env python3
"""End-to-end integration test from Hermes container perspective.

Simulates the exact MCP Streamable HTTP protocol that Hermes uses:
  1. POST initialize  →  get server capabilities
  2. POST tools/list  →  get tool definitions
  3. POST tools/call  →  call each tool and verify response
  4. SSE keepalive    →  GET /mcp returns text/event-stream
  5. DELETE session   →  terminate

Usage: python3 tests/test_hermes_e2e.py

Env vars:
  GWS_MCP_URL  — MCP endpoint (default: http://localhost:8777/mcp)
"""

import json, os, sys, time, urllib.request

MCP_URL = os.environ.get("GWS_MCP_URL", "http://localhost:8777/mcp")
PASSED = 0
FAILED = 0

def test(name, fn):
    global PASSED, FAILED
    try:
        fn()
        PASSED += 1
        print(f"PASS: {name}")
    except Exception as e:
        FAILED += 1
        print(f"FAIL: {name} — {e}")

def mcp_post(body):
    req = urllib.request.Request(
        MCP_URL,
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read())

def mcp_get():
    """GET /mcp (SSE keepalive check). Returns (content_type, initial_body_bytes)."""
    import socket, ssl
    from urllib.parse import urlparse
    parsed = urlparse(MCP_URL)
    host = parsed.hostname
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    path = parsed.path or "/"

    sock = socket.create_connection((host, port), timeout=5)
    if parsed.scheme == "https":
        ctx = ssl.create_default_context()
        sock = ctx.wrap_socket(sock, server_hostname=host)

    req = (
        f"GET {path} HTTP/1.1\r\n"
        f"Host: {host}:{port}\r\n"
        f"Accept: text/event-stream, application/json\r\n"
        f"Connection: close\r\n"
        f"\r\n"
    )
    sock.sendall(req.encode())

    # Read headers
    data = b""
    while b"\r\n\r\n" not in data:
        chunk = sock.recv(4096)
        if not chunk:
            break
        data += chunk

    headers_raw, body_start = data.split(b"\r\n\r\n", 1)
    headers = {}
    for line in headers_raw.decode().split("\r\n")[1:]:  # Skip status line
        if ":" in line:
            k, v = line.split(":", 1)
            headers[k.strip().lower()] = v.strip()

    # Read first chunk of body
    body = body_start
    try:
        sock.settimeout(1)
        body += sock.recv(4096)
    except (socket.timeout, OSError):
        pass
    finally:
        sock.close()

    return headers.get("content-type", ""), body.decode(errors="replace")

def mcp_delete():
    req = urllib.request.Request(MCP_URL, method="DELETE")
    with urllib.request.urlopen(req, timeout=5) as resp:
        return resp.status

def call_tool(name, args):
    r = mcp_post({
        "jsonrpc": "2.0", "id": 99, "method": "tools/call",
        "params": {"name": name, "arguments": args},
    })
    content = r["result"]["content"]
    assert len(content) > 0, "Empty tool call response"
    return json.loads(content[0]["text"])


# ─── 1. MCP Protocol Handshake ─────────────────────────────────

def _test_initialize():
    r = mcp_post({
        "jsonrpc": "2.0", "id": 1, "method": "initialize",
        "params": {
            "protocolVersion": "2025-03-26",
            "capabilities": {},
            "clientInfo": {"name": "hermes-e2e-test", "version": "1.0"},
        },
    })
    assert r["jsonrpc"] == "2.0"
    assert r["id"] == 1
    assert r["result"]["serverInfo"]["name"] == "gws-mcp"
    assert r["result"]["protocolVersion"] == "2025-03-26"

test("initialize — returns server info", _test_initialize)


def _test_tools_list():
    r = mcp_post({"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
    assert r["jsonrpc"] == "2.0"
    assert r["id"] == 2
    tools = r["result"]["tools"]
    assert len(tools) >= 13, f"Expected >=13 tools, got {len(tools)}"
    names = {t["name"] for t in tools}
    assert "gws_calendar_list_events" in names
    assert "gws_gmail_list_messages" in names
    assert "gws_gmail_send_message" in names
    assert "gws_drive_list_files" in names
    print(f"  {len(tools)} tools available")

test("tools/list — returns 14 tools", _test_tools_list)


# ─── 2. SSE Keepalive ──────────────────────────────────────────

def _test_sse_keepalive():
    ct, body = mcp_get()
    assert "text/event-stream" in ct, f"Expected SSE, got {ct}"
    assert ":ok" in body or ":ping" in body, f"SSE priming missing: {body.strip()}"
    print(f"  Content-Type: {ct.split(';')[0]}")

test("GET /mcp — SSE keepalive stream", _test_sse_keepalive)


# ─── 3. Gmail Tool Calls ───────────────────────────────────────

def _test_gmail_list():
    result = call_tool("gws_gmail_list_messages", {"maxResults": 5})
    assert isinstance(result, list), f"Expected list, got {type(result).__name__}"
    print(f"  {len(result)} messages in inbox")

test("gmail_list_messages — returns messages", _test_gmail_list)


def _test_gmail_send():
    result = call_tool("gws_gmail_send_message", {
        "to": "abap.core@gmail.com",
        "subject": "Hermes E2E Test",
        "body": "Automated test from Hermes E2E integration test.",
    })
    assert result.get("sent") is True, f"Send failed: {result}"
    sent_id = result["id"]
    print(f"  sent: id={sent_id[:16]}...")

    # Verify it appears in list
    time.sleep(2)
    list_result = call_tool("gws_gmail_list_messages", {"maxResults": 10})
    found = any(m["id"] == sent_id for m in list_result)
    assert found, f"Sent message {sent_id} not found in inbox"

    # Cleanup
    del_result = call_tool("gws_gmail_delete_message", {"messageId": sent_id})
    assert del_result.get("trashed") is True

test("gmail_send_message + delete", _test_gmail_send)


def _test_gmail_get():
    list_result = call_tool("gws_gmail_list_messages", {"maxResults": 1})
    assert len(list_result) > 0, "No messages to test get_message"
    msg_id = list_result[0]["id"]
    result = call_tool("gws_gmail_get_message", {
        "messageId": msg_id,
        "includeBody": True,
    })
    assert "id" in result
    assert "subject" in result
    body = result.get("body", "")
    print(f"  subject='{result['subject'][:50]}', body={len(body)} chars")

test("gmail_get_message — returns body text", _test_gmail_get)


# ─── 4. Calendar Tool Calls ────────────────────────────────────

def _test_calendar_list():
    result = call_tool("gws_calendar_list_events", {"maxResults": 5})
    assert isinstance(result, list), f"Expected list, got {type(result).__name__}"
    print(f"  {len(result)} events in calendar")

test("calendar_list_events — returns events", _test_calendar_list)


def _test_calendar_create():
    result = call_tool("gws_calendar_create_event", {
        "calendarId": "primary",
        "summary": "E2E Test Event",
        "start": "2026-06-28T14:00:00+02:00",
        "end": "2026-06-28T15:00:00+02:00",
    })
    assert "id" in result, f"Create failed: {result}"
    event_id = result["id"]
    print(f"  created: id={event_id}")

    # Cleanup
    del_result = call_tool("gws_calendar_delete_event", {
        "calendarId": "primary",
        "eventId": event_id,
    })
    assert del_result.get("deleted") is True

test("calendar_create_event + delete", _test_calendar_create)


# ─── 5. Drive Tool Calls ───────────────────────────────────────

def _test_drive_list():
    result = call_tool("gws_drive_list_files", {"pageSize": 5})
    assert isinstance(result, list), f"Expected list, got {type(result).__name__}"
    print(f"  {len(result)} files in Drive")

test("drive_list_files — returns files", _test_drive_list)


def _test_drive_create():
    test_name = f"hermes-e2e-test-{int(time.time())}.txt"
    result = call_tool("gws_drive_create_file", {
        "name": test_name,
        "mimeType": "text/plain",
        "content": "Hermes E2E integration test.",
    })
    assert "id" in result, f"Create failed: {result}"
    file_id = result["id"]
    print(f"  created: id={file_id}, name={test_name}")

    # Verify in list
    list_result = call_tool("gws_drive_list_files", {"pageSize": 10})
    found = any(f.get("name") == test_name for f in list_result)
    assert found, f"File {test_name} not found in Drive"

    # Get metadata
    get_result = call_tool("gws_drive_get_file", {"fileId": file_id})
    assert get_result.get("name") == test_name

    # Cleanup
    del_result = call_tool("gws_drive_delete_file", {"fileId": file_id})
    assert del_result.get("deleted") is True

test("drive_create_file → list → get → delete", _test_drive_create)


def _test_drive_download():
    # Find a file to download
    list_result = call_tool("gws_drive_list_files", {"pageSize": 1})
    assert len(list_result) > 0, "No files to download"
    file_id = list_result[0]["id"]
    result = call_tool("gws_drive_download_file", {"fileId": file_id})
    assert "savedTo" in result or "error" not in str(result)
    if "savedTo" in result:
        print(f"  downloaded to {result['savedTo']}")

test("drive_download_file", _test_drive_download)


# ─── 6. Session Teardown ───────────────────────────────────────

def _test_session_teardown():
    status = mcp_delete()
    assert status == 200, f"Expected 200, got {status}"

test("DELETE /mcp — session termination", _test_session_teardown)


# ─── Results ───────────────────────────────────────────────────

print()
print("=" * 55)
print(f"Results: {PASSED}/{PASSED+FAILED} passed")
if FAILED:
    print(f"FAILURES: {FAILED}")
    sys.exit(1)
else:
    print("All Hermes E2E integration tests passed!")
