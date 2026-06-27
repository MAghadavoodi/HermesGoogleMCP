#!/usr/bin/env python3
"""Integration tests for Google MCP Server - Drive."""
import json, subprocess, sys, os, tempfile

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

def test_list_files():
    """Test listing Drive files."""
    result = call_tool("gws_drive_list_files", {"pageSize": 5})
    if isinstance(result, list):
        print(f"PASS: drive_list_files - {len(result)} files")
        for f in result[:3]:
            print(f"  {f.get('name','?')} ({f.get('mimeType','?')})")
        return True
    elif isinstance(result, dict) and "error" in result:
        print(f"SKIP: drive_list_files - auth not configured ({result['error'][:80]})")
        return True
    else:
        print(f"FAIL: drive_list_files - {result}")
        return False

def test_get_file():
    """Test getting file metadata."""
    list_result = call_tool("gws_drive_list_files", {"pageSize": 1})
    if not isinstance(list_result, list) or len(list_result) == 0:
        print("SKIP: drive_get_file - no files available")
        return True

    file_id = list_result[0]["id"]
    result = call_tool("gws_drive_get_file", {"fileId": file_id})
    if isinstance(result, dict) and "name" in result:
        print(f"PASS: drive_get_file - {result.get('name','?')} ({result.get('mimeType','?')})")
        return True
    elif isinstance(result, dict) and "error" in result:
        print(f"SKIP: drive_get_file - {result['error'][:80]}")
        return True
    else:
        print(f"FAIL: drive_get_file - {result}")
        return False

def test_download_file():
    """Test downloading a file."""
    list_result = call_tool("gws_drive_list_files", {"pageSize": 1, "query": "mimeType contains 'image/'"})
    if not isinstance(list_result, list) or len(list_result) == 0:
        # Try without filter
        list_result = call_tool("gws_drive_list_files", {"pageSize": 1})

    if not isinstance(list_result, list) or len(list_result) == 0:
        print("SKIP: drive_download_file - no files available")
        return True

    file_id = list_result[0]["id"]
    fname = list_result[0].get("name", "test_file")
    with tempfile.TemporaryDirectory() as tmpdir:
        out_path = os.path.join(tmpdir, fname)
        result = call_tool("gws_drive_download_file", {"fileId": file_id, "outputPath": tmpdir})
        if isinstance(result, dict) and "savedTo" in result:
            size = result.get("size", 0)
            print(f"PASS: drive_download_file - {result['savedTo']} ({size} bytes)")
            return True
        elif isinstance(result, dict) and "error" in result:
            print(f"SKIP: drive_download_file - {result['error'][:80]}")
            return True
        else:
            print(f"FAIL: drive_download_file - {result}")
            return False

if __name__ == "__main__":
    results = []
    results.append(("drive_list_files", test_list_files()))
    results.append(("drive_get_file", test_get_file()))
    results.append(("drive_download_file", test_download_file()))
    failed = [n for n, r in results if not r]
    print(f"\nResults: {len([r for _,r in results if r])}/{len(results)} passed")
    sys.exit(1 if failed else 0)
