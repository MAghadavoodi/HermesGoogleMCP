#!/usr/bin/env python3
"""Integration tests for Google MCP Server - Gmail (CRUD)."""
import json, subprocess, sys, os, time

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
        return {"error": str(e), "stdout": p.stdout[:500]}

def is_auth_error(result):
    if not isinstance(result, dict): return False
    err = result.get("error", "")
    return any(kw in str(err).lower() for kw in ["auth", "credential", "login", "token", "scope"])

def test_list_messages():
    result = call_tool("gws_gmail_list_messages", {"maxResults": 3})
    if isinstance(result, list):
        print(f"PASS: gmail_list_messages - {len(result)} messages")
        for m in result[:2]:
            print(f"  ID: {m.get('id','?')}")
        return True
    elif is_auth_error(result):
        print(f"SKIP: gmail_list_messages - auth not configured")
        return True
    else:
        print(f"FAIL: gmail_list_messages - {result}")
        return False

def test_get_message():
    list_result = call_tool("gws_gmail_list_messages", {"maxResults": 1})
    if not isinstance(list_result, list) or len(list_result) == 0:
        print("SKIP: gmail_get_message - no messages")
        return True
    msg_id = list_result[0]["id"]
    result = call_tool("gws_gmail_get_message", {"messageId": msg_id})
    if isinstance(result, dict) and "subject" in result:
        print(f"PASS: gmail_get_message (metadata) - {result.get('subject','?')[:60]}")
        result_body = call_tool("gws_gmail_get_message", {"messageId": msg_id, "includeBody": True})
        if "body" in result_body:
            print(f"PASS: gmail_get_message (with body) - {len(result_body.get('body',''))} chars")
            return True
    elif is_auth_error(result):
        print("SKIP: gmail_get_message - auth not configured")
        return True
    else:
        print(f"FAIL: gmail_get_message - {result}")
        return False

def test_send_message():
    ts = int(time.time())
    result = call_tool("gws_gmail_send_message", {
        "to": "me",
        "subject": f"GWS-MCP Test {ts}",
        "body": "Integration test email - safe to delete."
    })
    if is_auth_error(result):
        print("SKIP: gmail_send_message - auth not configured")
        return True
    msg_id = result.get("id")
    if msg_id and result.get("sent"):
        print(f"PASS: gmail_send_message - id={msg_id[:20]}...")
        call_tool("gws_gmail_delete_message", {"messageId": msg_id})
        return True
    else:
        print(f"FAIL: gmail_send_message - {result}")
        return False

def test_send_with_attachment():
    """Test sending email with file attachment to abap.core@gmail.com."""
    import tempfile
    ts = int(time.time())
    # Create a temporary test file
    with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False, encoding="utf-8") as f:
        f.write(f"GWS-MCP Attachment Integration Test {ts}\nTimestamp: {time.ctime()}\n\nThis file was sent via gws-mcp v2.0 CRUD attachment feature.")
        tmp_path = f.name
    result = call_tool("gws_gmail_send_message", {
        "to": "abap.core@gmail.com",
        "subject": f"GWS-MCP Attachment Test {ts}",
        "body": "Hallo,\n\ndiese E-Mail enthält einen Dateianhang, gesendet via gws-mcp v2.0.\n\nGrüße,\nHermes Agent",
        "attachments": tmp_path
    })
    os.unlink(tmp_path)
    if is_auth_error(result):
        print("SKIP: gmail_send_attachment - auth not configured")
        return True
    if result.get("sent") and result.get("attachments") == 1:
        print(f"PASS: gmail_send_attachment - id={result.get('id','')[:20]}..., {result.get('attachments')} attachment(s)")
        return True
    else:
        print(f"FAIL: gmail_send_attachment - {result}")
        return False

def test_delete_message():
    # Send one first
    sent = call_tool("gws_gmail_send_message", {
        "to": "me",
        "subject": "Will be trashed",
        "body": "Delete me."
    })
    if is_auth_error(sent):
        print("SKIP: gmail_delete_message - auth not configured")
        return True
    msg_id = sent.get("id")
    if not msg_id:
        print(f"FAIL: gmail_delete_message setup - {sent}")
        return False
    trashed = call_tool("gws_gmail_delete_message", {"messageId": msg_id})
    if trashed.get("trashed"):
        print(f"PASS: gmail_delete_message")
        return True
    else:
        print(f"FAIL: gmail_delete_message - {trashed}")
        return False

if __name__ == "__main__":
    results = []
    results.append(("gmail_list_messages", test_list_messages()))
    results.append(("gmail_get_message", test_get_message()))
    results.append(("gmail_send_message", test_send_message()))
    results.append(("gmail_send_attachment", test_send_with_attachment()))
    results.append(("gmail_delete_message", test_delete_message()))
    failed = [n for n, r in results if not r]
    print(f"\nResults: {sum(1 for _,r in results if r)}/{len(results)} passed")
    sys.exit(1 if failed else 0)
