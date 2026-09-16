# Serves the current directory over HTTP and stores PUT uploads in ./uploads. Run: python3 serve.py [port]
from http.server import HTTPServer, SimpleHTTPRequestHandler
import os, sys
os.makedirs("uploads", exist_ok=True)
class H(SimpleHTTPRequestHandler):
    def __init__(self, *a, **k): super().__init__(*a, directory=".", **k)
    def do_PUT(self):
        n = int(self.headers["Content-Length"])
        with open("uploads/" + os.path.basename(self.path), "wb") as f: f.write(self.rfile.read(n))
        self.send_response(201); self.end_headers()
HTTPServer(("", int(sys.argv[1]) if len(sys.argv) > 1 else 8000), H).serve_forever()
