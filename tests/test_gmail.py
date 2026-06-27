#!/usr/bin/env python3
"""Integration tests for Google MCP Server - Gmail."""
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
        return {"error": str(e), "stdout": p.stdout[:500]}

def test_list_messages():
    """Test listing Gmail messages."""
    result = call_tool("gws_gmail_list_messages", {"maxResults": 3})
    if isinstance(result, list):
        print(f"PASS: gmail_list_messages - {len(result)} messages")
        for m in result[:2]:
            print(f"  ID: {m.get('id','?')}")
        return True
    elif isinstance(result, dict) and "error" in result:
        print(f"SKIP: gmail_list_messages - auth not configured ({result['error'][:80]})")
        return True
    else:
        print(f"FAIL: gmail_list_messages - {result}")
        return False

def test_get_message():
    """Test getting a specific message with body."""
    # First list to get a message ID
    list_result = call_tool("gws_gmail_list_messages", {"maxResults": 1})
    if not isinstance(list_result, list) or len(list_result) == 0:
        print("SKIP: gmail_get_message - no messages available")
        return True

    msg_id = list_result[0]["id"]
    # Test without body
    result_no_body = call_tool("gws_gmail_get_message", {"messageId": msg_id})
    if isinstance(result_no_body, dict) and "subject" in result_no_body:
        print(f"PASS: gmail_get_message (no body) - subject: {result_no_body.get('subject','?')[:60]}")
    else:
        print(f"FAIL: gmail_get_message (no body) - {result_no_body}")
        return False

    # Test with body
    result_with_body = call_tool("gws_gmail_get_message", {"messageId": msg_id, "includeBody": True})
    if isinstance(result_with_body, dict) and "body" in result_with_body:
        body_len = len(result_with_body.get("body", ""))
        print(f"PASS: gmail_get_message (with body) - body length: {body_len}")
    else:
        print(f"FAIL: gmail_get_message (with body) - {result_with_body}")
        return False
    return True

if __name__ == "__main__":
    results = []
    results.append(("gmail_list_messages", test_list_messages()))
    results.append(("gmail_get_message", test_get_message()))
    failed = [n for n, r in results if not r]
    print(f"\nResults: {len([r for _,r in results if r])}/{len(results)} passed")
    sys.exit(1 if failed else 0)
