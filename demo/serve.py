#!/usr/bin/env python3
"""
NUC-SUB Live Preview — local run.

Builds all 16 themes and serves the gallery locally so you can inspect the
rendered output in your browser without any server or external service.

    python demo/serve.py          # build + serve at http://127.0.0.1:8080

Ctrl+C to stop the server.
"""
import functools
import http.server
import os
import socketserver
import subprocess
import sys
import threading
import webbrowser

DEMO = os.path.dirname(os.path.abspath(__file__))
SITE = os.path.join(DEMO, "site")
PORT = 8080

class QuietHandler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *args):
        pass


def main():
    print("rendering the 16 themes...")
    rc = subprocess.call([sys.executable, os.path.join(DEMO, "build.py")])
    if rc != 0 or not os.path.isfile(os.path.join(SITE, "index.html")):
        sys.exit("build failed — check the build.py output above")
    os.chdir(SITE)
    handler = functools.partial(QuietHandler, directory=SITE)
    with socketserver.TCPServer(("127.0.0.1", PORT), handler) as httpd:
        url = f"http://127.0.0.1:{PORT}/"
        print(f"\nnucsub preview: {url}  (Ctrl+C to stop)")
        threading.Timer(0.6, lambda: webbrowser.open(url)).start()
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\nstopped.")
    sys.exit(0)


if __name__ == "__main__":
    main()