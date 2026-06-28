#!/usr/bin/env python3
"""Integration tests for Google MCP Server - Calendar (CRUD)."""
import json, subprocess, sys, os

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
    if not isinstance(result, dict): return False
    err = result.get("error", "")
    return any(kw in str(err).lower() for kw in ["auth", "credential", "login", "token", "scope"])

def test_list_events():
    result = call_tool("gws_calendar_list_events", {"maxResults": 5})
    if isinstance(result, list):
        print(f"PASS: calendar_list_events - {len(result)} events")
        for e in result[:2]:
            print(f"  {e.get('summary','?')} at {e.get('start',{}).get('dateTime','?')}")
        return True
    elif is_auth_error(result):
        print(f"SKIP: calendar_list_events - auth not configured")
        return True
    else:
        print(f"FAIL: calendar_list_events - {result}")
        return False

def test_create_event():
    result = call_tool("gws_calendar_create_event", {
        "summary": "Test Event from MCP",
        "start": "2027-01-01T09:00:00+01:00",
        "end": "2027-01-01T10:00:00+01:00",
        "description": "Created by integration test."
    })
    if is_auth_error(result):
        print("SKIP: calendar_create_event - auth not configured")
        return True
    event_id = result.get("id")
    if event_id:
        print(f"PASS: calendar_create_event - id={event_id[:30]}..., htmlLink={result.get('htmlLink','')[:60]}")
        # Clean up
        call_tool("gws_calendar_delete_event", {"eventId": event_id})
        return True
    else:
        print(f"FAIL: calendar_create_event - {result}")
        return False

def test_update_event():
    created = call_tool("gws_calendar_create_event", {
        "summary": "Test Event - will update",
        "start": "2027-06-01T12:00:00+02:00",
        "end": "2027-06-01T13:00:00+02:00"
    })
    if is_auth_error(created):
        print("SKIP: calendar_update_event - auth not configured")
        return True
    event_id = created.get("id")
    if not event_id:
        print(f"FAIL: calendar_update_event setup - {created}")
        return False
    updated = call_tool("gws_calendar_update_event", {
        "eventId": event_id,
        "summary": "Test Event UPDATED",
        "description": "Updated description."
    })
    call_tool("gws_calendar_delete_event", {"eventId": event_id})
    if updated.get("summary") == "Test Event UPDATED":
        print(f"PASS: calendar_update_event")
        return True
    else:
        print(f"FAIL: calendar_update_event - {updated}")
        return False

def test_delete_event():
    created = call_tool("gws_calendar_create_event", {
        "summary": "Test Event - to delete",
        "start": "2027-06-02T10:00:00+02:00",
        "end": "2027-06-02T11:00:00+02:00"
    })
    if is_auth_error(created):
        print("SKIP: calendar_delete_event - auth not configured")
        return True
    event_id = created.get("id")
    if not event_id:
        print(f"FAIL: calendar_delete_event setup - {created}")
        return False
    deleted = call_tool("gws_calendar_delete_event", {"eventId": event_id})
    if deleted.get("deleted"):
        print(f"PASS: calendar_delete_event")
        return True
    else:
        print(f"FAIL: calendar_delete_event - {deleted}")
        return False

if __name__ == "__main__":
    results = []
    results.append(("calendar_list_events", test_list_events()))
    results.append(("calendar_create_event", test_create_event()))
    results.append(("calendar_update_event", test_update_event()))
    results.append(("calendar_delete_event", test_delete_event()))
    failed = [n for n, r in results if not r]
    print(f"\nResults: {sum(1 for _,r in results if r)}/{len(results)} passed")
    sys.exit(1 if failed else 0)
