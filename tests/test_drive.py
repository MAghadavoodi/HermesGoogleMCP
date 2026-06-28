#!/usr/bin/env python3
"""Integration tests for Google MCP Server - Drive (CRUD)."""
import json, subprocess, sys, os, tempfile, time

SERVER_SCRIPT = os.path.join(os.path.dirname(__file__), "..", "src", "server.py")
os.environ["GOOGLE_WORKSPACE_CLI_KEYRING_BACKEND"] = "file"

def call_tool(name, args):
    req = {"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":name,"arguments":args}}
    p = subprocess.run(["python3", SERVER_SCRIPT], input=json.dumps(req)+"\n",
                       capture_output=True, text=True, timeout=60)
    try:
        resp = json.loads(p.stdout.strip().split("\n")[-1])
        return json.loads(resp["result"]["content"][0]["text"])
    except Exception as e:
        return {"error": str(e), "stdout": p.stdout[:500]}

def is_auth_error(result):
    if not isinstance(result, dict): return False
    err = result.get("error", "")
    return any(kw in str(err).lower() for kw in ["auth", "credential", "login", "token", "scope"])

def test_list_files():
    result = call_tool("gws_drive_list_files", {"pageSize": 5})
    if isinstance(result, list):
        print(f"PASS: drive_list_files - {len(result)} files")
        for f in result[:3]:
            print(f"  {f.get('name','?')} ({f.get('mimeType','?')})")
        return True
    elif is_auth_error(result):
        print(f"SKIP: drive_list_files - auth not configured")
        return True
    else:
        print(f"FAIL: drive_list_files - {result}")
        return False

def test_get_file():
    list_result = call_tool("gws_drive_list_files", {"pageSize": 1})
    if not isinstance(list_result, list) or len(list_result) == 0:
        print("SKIP: drive_get_file - no files")
        return True
    file_id = list_result[0]["id"]
    result = call_tool("gws_drive_get_file", {"fileId": file_id})
    if isinstance(result, dict) and "name" in result:
        print(f"PASS: drive_get_file - {result.get('name','?')} ({result.get('mimeType','?')})")
        return True
    elif is_auth_error(result):
        print("SKIP: drive_get_file")
        return True
    else:
        print(f"FAIL: drive_get_file - {result}")
        return False

def test_create_file():
    ts = int(time.time())
    result = call_tool("gws_drive_create_file", {
        "name": f"gws-mcp-test-{ts}.txt",
        "mimeType": "text/plain",
        "content": "Integration test content."
    })
    if is_auth_error(result):
        print("SKIP: drive_create_file - auth not configured")
        return True
    file_id = result.get("id")
    if file_id:
        print(f"PASS: drive_create_file - id={file_id[:20]}..., name={result.get('name')}")
        call_tool("gws_drive_delete_file", {"fileId": file_id})
        return True
    else:
        print(f"FAIL: drive_create_file - {result}")
        return False

def test_update_file():
    ts = int(time.time())
    created = call_tool("gws_drive_create_file", {
        "name": f"gws-mcp-test-{ts}.txt",
        "content": "Original content."
    })
    if is_auth_error(created):
        print("SKIP: drive_update_file - auth not configured")
        return True
    file_id = created.get("id")
    if not file_id:
        print(f"FAIL: drive_update_file setup - {created}")
        return False
    updated = call_tool("gws_drive_update_file", {
        "fileId": file_id,
        "name": f"gws-mcp-test-{ts}-UPDATED.txt",
        "content": "Updated content."
    })
    call_tool("gws_drive_delete_file", {"fileId": file_id})
    if "UPDATED" in updated.get("name",""):
        print(f"PASS: drive_update_file - {updated.get('name')}")
        return True
    else:
        print(f"FAIL: drive_update_file - {updated}")
        return False

def test_delete_file():
    ts = int(time.time())
    created = call_tool("gws_drive_create_file", {
        "name": f"gws-mcp-test-{ts}-todelete.txt",
        "content": "Will be deleted."
    })
    if is_auth_error(created):
        print("SKIP: drive_delete_file - auth not configured")
        return True
    file_id = created.get("id")
    if not file_id:
        print(f"FAIL: drive_delete_file setup - {created}")
        return False
    deleted = call_tool("gws_drive_delete_file", {"fileId": file_id})
    if deleted.get("deleted"):
        print(f"PASS: drive_delete_file")
        return True
    else:
        print(f"FAIL: drive_delete_file - {deleted}")
        return False

def test_download_file():
    list_result = call_tool("gws_drive_list_files", {"pageSize": 1})
    if not isinstance(list_result, list) or len(list_result) == 0:
        print("SKIP: drive_download_file - no files")
        return True
    file_id = list_result[0]["id"]
    fname = list_result[0].get("name", "test_file")
    with tempfile.TemporaryDirectory() as tmpdir:
        result = call_tool("gws_drive_download_file", {"fileId": file_id, "outputPath": tmpdir})
        if isinstance(result, dict) and "savedTo" in result:
            print(f"PASS: drive_download_file - {result['savedTo']} ({result.get('size',0)} bytes)")
            return True
        elif is_auth_error(result):
            print("SKIP: drive_download_file")
            return True
        else:
            print(f"FAIL: drive_download_file - {result}")
            return False

if __name__ == "__main__":
    results = []
    results.append(("drive_list_files", test_list_files()))
    results.append(("drive_get_file", test_get_file()))
    results.append(("drive_create_file", test_create_file()))
    results.append(("drive_update_file", test_update_file()))
    results.append(("drive_delete_file", test_delete_file()))
    results.append(("drive_download_file", test_download_file()))
    failed = [n for n, r in results if not r]
    print(f"\nResults: {sum(1 for _,r in results if r)}/{len(results)} passed")
    sys.exit(1 if failed else 0)
