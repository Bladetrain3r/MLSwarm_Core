#!/usr/bin/env python3
"""
MLSwarm HTTP Server - The simplest possible swarm server
Just serves files and appends to them. That's it.
"""

from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from datetime import datetime

ALLOWED_SWARMS = {
    'swarm.txt',
    'general.txt', 
    'random.txt',
    'tech.txt',
    'gaming.txt'
}

class SwarmHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path.startswith('/swarm/'):
            filename = self.path[7:].strip('/')
            
            # Nuclear whitelist
            if filename not in ALLOWED_SWARMS:
                self.send_response(404)
                self.send_header('Content-Type', 'text/plain')
                self.end_headers()
                self.wfile.write(b'Not found')
                return
            
            filepath = Path(filename)
            if not filepath.exists():
                # Create it if it doesn't exist
                filepath.touch()
                filepath.write_text(f"=== Swarm {filename} started {datetime.now()} ===\n")
            
            # Serve it
            with open(filepath, 'rb') as f:
                content = f.read()
            
            self.send_response(200)
            self.send_header('Content-Type', 'text/plain')
            self.send_header('Content-Length', str(len(content)))
            self.end_headers()
            self.wfile.write(content)
    
    def do_POST(self):
        if self.path.startswith('/swarm/'):
            # Append to swarm file
            filename = self.path[7:].strip('/')

            if filename not in ALLOWED_SWARMS:
                self.send_response(404)
                self.send_header('Content-Type', 'text/plain')
                self.end_headers()
                self.wfile.write(b'Not found')
                return
            
            filepath = Path(filename)
            
            content_length = int(self.headers['Content-Length'])
            content = self.rfile.read(content_length)
            
            with open(filepath, 'ab') as f:
                f.write(content)
            
            self.send_response(200)
            self.end_headers()
        else:
            self.send_response(404)
            self.end_headers()

if __name__ == '__main__':
    httpd = HTTPServer(('0.0.0.0', 8080), SwarmHandler)
    httpd.serve_forever()