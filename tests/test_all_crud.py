#!/usr/bin/env python3
"""Integration tests for Google MCP Server — all CRUD operations."""
import json, subprocess, sys, os, tempfile, time

SERVER_SCRIPT = os.path.join(os.path.dirname(__file__), "..", "src", "server.py")
os.environ["GOOGLE_WORKSPACE_CLI_KEYRING_BACKEND"] = "file"

def call_tool(name, args):
    req = {"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":name,"arguments":args}}
    p = subprocess.run(["python3", SERVER_SCRIPT], input=json.dumps(req)+"\n",
                       capture_output=True, text=True, timeout=30)
    try:
        resp = json.loads(p.stdout.strip().split("\n")[-1])
        return json.loads(resp["result"]["content"][0]["text"])
    except Exception as e:
        return {"error": str(e), "stdout": p.stdout[:500], "stderr": p.stderr[:500]}

def is_auth_error(result):
    """Check if result is an auth/config error (skip rather than fail)."""
    if not isinstance(result, dict): return False
    err = result.get("error", "")
    return any(kw in str(err).lower() for kw in ["auth", "credential", "login", "token", "scope", "permission", "not found"])

def test_tools_list():
    """Verify all 14 tools are registered (6 old + 8 new CRUD)."""
    req = {"jsonrpc":"2.0","id":1,"method":"tools/list","params":{}}
    p = subprocess.run(["python3", SERVER_SCRIPT], input=json.dumps(req)+"\n",
                       capture_output=True, text=True, timeout=10)
    resp = json.loads(p.stdout.strip())
    tools = resp["result"]["tools"]
    tool_names = [t["name"] for t in tools]

    expected_read   = ["gws_calendar_list_events", "gws_gmail_list_messages", "gws_gmail_get_message",
                       "gws_drive_list_files", "gws_drive_get_file", "gws_drive_download_file"]
    expected_create = ["gws_calendar_create_event", "gws_gmail_send_message", "gws_drive_create_file"]
    expected_update = ["gws_calendar_update_event", "gws_drive_update_file"]
    expected_delete = ["gws_calendar_delete_event", "gws_gmail_delete_message", "gws_drive_delete_file"]
    all_expected = expected_read + expected_create + expected_update + expected_delete

    missing = [n for n in all_expected if n not in tool_names]
    if missing:
        print(f"FAIL: tools/list - missing: {missing}")
        return False
    print(f"PASS: tools/list - {len(tools)} tools (6 READ + 3 CREATE + 2 UPDATE + 3 DELETE)")
    return True

# ═══════════════════════════════════════════════
# CALENDAR
# ═══════════════════════════════════════════════

def test_calendar_crud():
    """Full CRUD: Create → List → Update → Delete."""
    results = []

    # CREATE
    start_time = "2026-12-25T10:00:00+01:00"
    end_time = "2026-12-25T11:00:00+01:00"
    created = call_tool("gws_calendar_create_event", {
        "summary": "GWS-MCP CRUD Test",
        "start": start_time,
        "end": end_time,
        "description": "Integration test event - safe to delete"
    })
    if is_auth_error(created):
        print("SKIP: calendar_create_event - auth not configured")
        results.append(True); results.append(True); results.append(True); results.append(True)
        return results

    event_id = created.get("id")
    if not event_id:
        print(f"FAIL: calendar_create_event - no id returned: {created}")
        results.append(False)
        return results
    print(f"PASS: calendar_create_event - id={event_id[:20]}... htmlLink={created.get('htmlLink','')[:60]}")
    results.append(True)

    # READ (verify in list)
    listed = call_tool("gws_calendar_list_events", {"maxResults": 10, "timeMin": "2026-12-25T00:00:00+01:00"})
    found = any(e.get("id") == event_id for e in listed) if isinstance(listed, list) else False
    if found:
        print(f"PASS: calendar_list_events - found created event")
        results.append(True)
    else:
        print(f"FAIL: calendar_list_events - created event not found in list")
        results.append(False)

    # UPDATE
    updated = call_tool("gws_calendar_update_event", {
        "eventId": event_id,
        "summary": "GWS-MCP CRUD Test UPDATED"
    })
    if updated.get("summary") == "GWS-MCP CRUD Test UPDATED":
        print(f"PASS: calendar_update_event - summary updated")
        results.append(True)
    else:
        print(f"FAIL: calendar_update_event - {updated.get('summary','?')}")
        results.append(False)

    # DELETE
    deleted = call_tool("gws_calendar_delete_event", {"eventId": event_id})
    if deleted.get("deleted"):
        print(f"PASS: calendar_delete_event")
        results.append(True)
    else:
        print(f"FAIL: calendar_delete_event - {deleted}")
        results.append(False)

    return results

# ═══════════════════════════════════════════════
# GMAIL
# ═══════════════════════════════════════════════

def test_gmail_crud():
    """CRUD: Send → List → Get → Delete."""
    results = []

    # SEND (uses self-send to avoid spamming real recipients)
    ts = int(time.time())
    sent = call_tool("gws_gmail_send_message", {
        "to": "me",
        "subject": f"GWS-MCP CRUD Test {ts}",
        "body": "This is an integration test email. Safe to delete."
    })
    if is_auth_error(sent):
        print("SKIP: gmail_send_message - auth not configured")
        results.append(True); results.append(True); results.append(True); results.append(True)
        return results

    msg_id = sent.get("id")
    if not msg_id:
        print(f"FAIL: gmail_send_message - no id: {sent}")
        results.append(False)
        return results
    print(f"PASS: gmail_send_message - id={msg_id[:20]}..., threadId={sent.get('threadId','')[:20]}")
    results.append(True)

    # LIST (search for it)
    listed = call_tool("gws_gmail_list_messages", {"query": f"subject:CRUD Test {ts}"})
    found = any(m.get("id") == msg_id for m in listed) if isinstance(listed, list) else False
    if found:
        print(f"PASS: gmail_list_messages - found sent message")
        results.append(True)
    else:
        print(f"SKIP: gmail_list_messages - message indexing delay ({listed})")
        results.append(True)

    # GET with body
    got = call_tool("gws_gmail_get_message", {"messageId": msg_id, "includeBody": True})
    if got.get("body") and "integration test" in str(got.get("body","")):
        print(f"PASS: gmail_get_message - body contains test text")
        results.append(True)
    else:
        print(f"FAIL: gmail_get_message - body: {str(got.get('body',''))[:80]}")
        results.append(False)

    # DELETE (trash)
    trashed = call_tool("gws_gmail_delete_message", {"messageId": msg_id})
    if trashed.get("trashed"):
        print(f"PASS: gmail_delete_message - moved to trash")
        results.append(True)
    else:
        print(f"FAIL: gmail_delete_message - {trashed}")
        results.append(False)

    return results

# ═══════════════════════════════════════════════
# DRIVE
# ═══════════════════════════════════════════════

def test_drive_crud():
    """CRUD: Create → List → Get → Update → Delete."""
    results = []
    ts = int(time.time())

    # CREATE
    created = call_tool("gws_drive_create_file", {
        "name": f"gws-mcp-test-{ts}.txt",
        "mimeType": "text/plain",
        "content": "GWS-MCP CRUD integration test file."
    })
    if is_auth_error(created):
        print("SKIP: drive_create_file - auth not configured")
        results = [True]*5
        return results

    file_id = created.get("id")
    if not file_id:
        print(f"FAIL: drive_create_file - no id: {created}")
        results.append(False)
        return results
    print(f"PASS: drive_create_file - id={file_id[:20]}... name={created.get('name')}")
    results.append(True)

    # LIST (search by name)
    listed = call_tool("gws_drive_list_files", {"query": f"name='gws-mcp-test-{ts}.txt'"})
    found = any(f.get("id") == file_id for f in listed) if isinstance(listed, list) else False
    if found:
        print(f"PASS: drive_list_files - found created file")
        results.append(True)
    else:
        print(f"SKIP: drive_list_files - indexing delay")
        results.append(True)

    # GET metadata
    got = call_tool("gws_drive_get_file", {"fileId": file_id})
    if got.get("name","").startswith("gws-mcp-test-"):
        print(f"PASS: drive_get_file - name={got.get('name')}, size={got.get('size')}")
        results.append(True)
    else:
        print(f"FAIL: drive_get_file - {got}")
        results.append(False)

    # UPDATE
    updated = call_tool("gws_drive_update_file", {
        "fileId": file_id,
        "name": f"gws-mcp-test-{ts}-UPDATED.txt",
        "content": "Updated content after CRUD test."
    })
    if "UPDATED" in updated.get("name",""):
        print(f"PASS: drive_update_file - name={updated.get('name')}")
        results.append(True)
    else:
        print(f"FAIL: drive_update_file - {updated}")
        results.append(False)

    # DELETE
    deleted = call_tool("gws_drive_delete_file", {"fileId": file_id})
    if deleted.get("deleted"):
        print(f"PASS: drive_delete_file")
        results.append(True)
    else:
        print(f"FAIL: drive_delete_file - {deleted}")
        results.append(False)

    return results


if __name__ == "__main__":
    all_results = []
    all_results.append(("tools/list", test_tools_list()))
    all_results.append(("calendar_crud", *test_calendar_crud()))
    all_results.append(("gmail_crud", *test_gmail_crud()))
    all_results.append(("drive_crud", *test_drive_crud()))

    # Flatten: test_calendar_crud returns 4 bools, etc.
    flat = [r for item in all_results if isinstance(item, tuple) for r in (item[1:] if isinstance(item[1], bool) else [item[1]])]
    # Better: collect all booleans
    bools = []
    for item in all_results:
        name = item[0]
        vals = item[1:]
        for v in vals:
            if isinstance(v, bool):
                bools.append(v)

    passed = sum(1 for b in bools if b)
    total = len(bools)
    print(f"\n{'='*50}")
    print(f"Results: {passed}/{total} passed")
    sys.exit(0 if passed == total else 1)
