#!/usr/bin/env python3
"""HTTP wrapper that speaks Streamable HTTP MCP protocol."""
import http.server, json, subprocess, sys, os, urllib.parse

os.environ['GOOGLE_WORKSPACE_CLI_KEYRING_BACKEND'] = 'file'
SERVER_SCRIPT = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'server.py')

class H(http.server.BaseHTTPRequestHandler):
    def do_POST(self):
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path != '/mcp':
            self.send_response(404); self.end_headers(); return
        length = int(self.headers.get('Content-Length', 0))
        body = self.rfile.read(length).decode()
        p = subprocess.run(['python3', SERVER_SCRIPT], input=body, capture_output=True, text=True, timeout=30)
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.end_headers()
        self.wfile.write(p.stdout.encode())

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path == '/mcp':
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(b'{}')
        elif parsed.path == '/health':
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({"status":"ok"}).encode())
        else:
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(b'{}')

    def do_DELETE(self):
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.end_headers()
        self.wfile.write(b'{}')

    def log_message(self, *a): pass

http.server.HTTPServer(('0.0.0.0', 8777), H).serve_forever()
