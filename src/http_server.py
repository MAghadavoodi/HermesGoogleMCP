#!/usr/bin/env python3
"""HTTP wrapper that speaks Streamable HTTP MCP protocol."""
import http.server, json, signal, subprocess, sys, os, urllib.parse, time, socketserver

os.environ['GOOGLE_WORKSPACE_CLI_KEYRING_BACKEND'] = 'file'
SERVER_SCRIPT = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'server.py')

class H(http.server.BaseHTTPRequestHandler):
    protocol_version = 'HTTP/1.1'

    def _json_response(self, data, status=200):
        body = json.dumps(data, separators=(",",":")).encode()
        self.send_response(status)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path != '/mcp':
            self._json_response({"error": "not found"}, 404)
            return
        length = int(self.headers.get('Content-Length', 0))
        if length == 0:
            return
        body = self.rfile.read(length).decode()
        p = subprocess.run(['python3', SERVER_SCRIPT], input=body, capture_output=True, text=True, timeout=30)
        output = p.stdout.strip()
        if output:
            try:
                data = json.loads(output)
            except json.JSONDecodeError:
                data = {"jsonrpc":"2.0","result":{},"id":None}
            self._json_response(data)
        else:
            self.send_response(202)
            self.send_header('Content-Length', '0')
            self.end_headers()

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path == '/mcp':
            self.send_response(200)
            self.send_header('Content-Type', 'text/event-stream')
            self.send_header('Cache-Control', 'no-cache')
            self.send_header('Connection', 'keep-alive')
            self.send_header('X-Accel-Buffering', 'no')
            self.end_headers()
            self.wfile.write(b':ok\n\n')
            self.wfile.flush()
            while True:
                try:
                    time.sleep(15)
                    self.wfile.write(b':ping\n\n')
                    self.wfile.flush()
                except (BrokenPipeError, ConnectionResetError):
                    break
        elif parsed.path == '/health':
            self._json_response({"status":"ok"})
        else:
            self.send_response(404)
            self.send_header('Content-Length', '0')
            self.end_headers()

    def do_DELETE(self):
        self.send_response(200)
        self.send_header('Content-Length', '0')
        self.end_headers()

    def log_message(self, *a): pass

class ThreadingHTTPServer(socketserver.ThreadingMixIn, http.server.HTTPServer):
    daemon_threads = True

server = ThreadingHTTPServer(('0.0.0.0', 8777), H)

def shutdown(signum, frame):
    server.server_close()
    sys.exit(0)

signal.signal(signal.SIGTERM, shutdown)
signal.signal(signal.SIGINT, shutdown)

server.serve_forever()
