import http.server, socketserver, os, sys

root = sys.argv[1]
portfile = sys.argv[2]
os.chdir(root)


class Handler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *args):
        pass


socketserver.TCPServer.allow_reuse_address = True
with socketserver.TCPServer(("127.0.0.1", 0), Handler) as httpd:
    with open(portfile, "w") as fh:
        fh.write(str(httpd.server_address[1]))
    httpd.serve_forever()
