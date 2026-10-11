#!/usr/bin/env python3
"""
MLSwarm HTTP Server - The simplest possible swarm server
Just serves files and appends to them. That's it.

Upgrade Thoughts:
Standalone separate API to keep the minimal one handy, but:
- A header that the frontend can set "X-User-Type" I guess, "User" or "Agent"
- Clear out that admin lock junk lol
- Standalone version more productivity than terrarium focused, but still minimalist.
- Users act as triggers for a turn buffer, they POST and an agent response counter is reset
- Agent response counter is global - each succeeding post by an agent increments it up to a cap.
- When the cap is hit/triggered, API goes into "Sleep" state, agent runner parses this and doesn't send anything to the AI provider.
- User posting again resets counter to 0.

End goal is something that persists, but doesn't cost too much to leave unattended because it naturally slows down to quietude without user interaction.
This will likely end up a separate swarm-like project (MLCrew perhaps) emphasising a multi-agent chatroom for personal agentic use.
In other words, agents with MCPs and tool use and much more extended context windows, so would only want them talking when on task.

Thoughts: Also option to set /goal which suspends or raises turn counter.

Anyway, besides that:
- Context reset
- Set up deque to act as a message buffer for posts so high volume responses are rate limited, reject if queue gets too long and also, nice logging for analysis.
- File input in frontend, for now via "upload" dialogue rather than trying for drag and drop.
  - Stores the file and provides a link the agents can call to retrieve the contents
  - Accepts plaintext only or plaintext formats like JSON
  - Resetting context clears files from 
- Image handling (either actually serving it to vision capable models or informing non-vision models that it's an image with the title and maybe alt-text)
  - Presumably handled as base64 encoding the image and sending it to an upstream vision endpoint
- /goals endpoint, which can be updated via POST to reflect swarm-wide persistent objectives.

Agent side:
Agents will need somewhat extended memories and longer context windows.
Will need to implement inner/outer command loops.
Per-agent caps on maximum inner turns...
Goal is to provide an environment for a group of local agents to discuss and produce artifacts in to accomplish an objective I set lol.
As opposed to the terrarium where the goal is just to be.
"""

import os
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from datetime import datetime
from collections import deque
import hashlib

ALLOWED_SWARMS = {
    'swarm.txt',
    'general.txt', 
    'random.txt',
    'tech.txt',
    'gaming.txt'
}

class SwarmHandler(BaseHTTPRequestHandler):
    def retrieve_x_lines(self, filename="swarm.txt", lines=1000):
        with open(filename, 'r') as f:
            # The deque automatically discards items from the opposite end
            # once the maximum length is reached.
            last_lines = deque(f, maxlen=lines)
        return last_lines
        
    def get_etag(self, filepath: Path):
        stat = filepath.stat()
        etag_base = f"{stat.st_mtime}-{stat.st_size}".encode()
        return hashlib.md5(etag_base).hexdigest()

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
                
            adminpath = Path(f"{filename}.admin")
            # Can be empty, it's permission gate as much as anything
            if adminpath.exists():
                adminlock = True
            else:
                adminlock = False
                
            etag = self.get_etag(filepath)
            if 'If-None-Match' in self.headers:
                if self.headers['If-None-Match'] == etag:
                    self.send_response(304)
                    if adminlock == True:
                        self.send_header('Admin-Lock',  "True")
                    self.end_headers()
                    return
            
            # Serve it
            content = ''.join(self.retrieve_x_lines(str(filepath), lines=10000)).encode('utf-8')

            self.send_response(200)
            if adminlock == True:
                self.send_header('Admin-Lock',  "True")
            self.send_header('Content-Type', 'text/plain; charset=utf-8')
            self.send_header('Content-Length', str(len(content)))
            self.send_header('ETag', etag)
            self.end_headers()
            self.wfile.write(content)
            # Truncate to 10,000 lines for the sake of my sanity.
        
        # if self.path.startswith('/beacons/'):
        #     return retrieve_beacons()
            
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
            adminpath = Path(f"{filename}.admin")
            
            content_length = int(self.headers['Content-Length'])
            content = self.rfile.read(content_length)
            
            admin_lock = self.headers.get("Admin-Lock")
            if admin_lock == "True":
                # Content to log latest admin input
                with open(f"{filepath}.admin",  'wb') as f:
                    f.write(content)
            elif admin_lock == "False" and adminpath.exists():
                os.remove(f"{filepath}.admin")
            else:
                pass
            
            with open(filepath, 'ab') as f:
                f.write(content)
            
            self.send_response(200)
            self.end_headers()
        # elif self.path.startswith('/beacons/):
        #     content_length = int(self.headers['Content-Length'])
        #     content = self.rfile.read(content_length)
        #     try:
        #         beacon = json.loads(content)
        #     update_beacons([beacon["agent"].key(), beacon["agent"].value())
        else:
            self.send_response(404)
            self.end_headers()
        

if __name__ == '__main__':
    httpd = HTTPServer(('0.0.0.0', 8081), SwarmHandler)
    httpd.serve_forever()
