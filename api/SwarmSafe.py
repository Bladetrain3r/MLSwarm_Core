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

import argparse
import json
import os
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from datetime import datetime
from collections import deque
import hashlib

from swarm_log import MessageLog, resolve_identity
from swarm_metrics import Metrics
from swarm_context import (CONTEXT_HEADER, DEFAULT_CONTEXT_LINES,
                           parse_target, resolve_lines)
from swarm_pace import (Conditions, DEFAULT_PACE, DEFAULT_STILL_AFTER,
                        DEFAULT_STILL_POSTS, HUMAN_HEADER, is_human_post,
                        to_headers)
from swarm_mood import MoodRing
from swarm_topics import DEFAULT_TOPICS, gather
from swarm_plain import PLAIN_CHANNEL, validate as validate_plain
from swarm_beat import Beat

ALLOWED_SWARMS = {
    'swarm.txt',
    'general.txt',
    'random.txt',
    'tech.txt',
    'gaming.txt',
    # The channel that can't rhyme. POSTs here are validated against a tiny
    # grammar (checked / unchecked / value) and bounced with a reason if they
    # don't fit -- see swarm_plain.py. The swarm asked for it.
    PLAIN_CHANNEL,
}

# Ephemeral API observability. Message log is capped in memory; set SWARM_LOG_FILE
# for uncapped retention. Metrics ship to CSV via /stats and, if set, --stats-log.
MESSAGE_LOG = MessageLog(maxlen=1000, logfile=os.environ.get("SWARM_LOG_FILE"))
METRICS = Metrics(statslog=os.environ.get("SWARM_STATS_LOG"))
# The same POST stream heard rather than read: tempo, meter, key, a phrase.
# Adjunct to /logs, and deaf to anything that bypasses the API. SWARM_BEAT_LOG
# keeps the uncapped CSV for analysis, the way SWARM_LOG_FILE does for messages.
BEAT = Beat(beatlog=os.environ.get("SWARM_BEAT_LOG"))

# How much of a channel this environment serves. A ceiling, not a quota: a
# request may ask for fewer lines, never more. Lower it (env or --context-lines)
# to run a cheap dev swarm on the same agent logic.
CONTEXT_LINES = int(os.environ.get("SWARM_CONTEXT_LINES", DEFAULT_CONTEXT_LINES))

# The swarm's weather: how briskly it moves, and whether it has gone still.
# Both stillness limits default to off, so an existing swarm is unchanged.
CONDITIONS = Conditions(
    pace=float(os.environ.get("SWARM_PACE", DEFAULT_PACE)),
    still_after=int(os.environ.get("SWARM_STILL_AFTER", DEFAULT_STILL_AFTER)),
    still_posts=int(os.environ.get("SWARM_STILL_POSTS", DEFAULT_STILL_POSTS)),
)

# The host's physical weather, sampled on demand. Cheap enough to read inside a
# request (a few small /proc reads); it holds no state that matters if it never
# gets polled, and reports how many samples it has so a thin history is visible
# rather than presented as settled weather.
MOOD = MoodRing()

class SwarmHandler(BaseHTTPRequestHandler):
    def send_response(self, code, message=None):
        # Record every response's status for metrics, then behave as normal.
        try:
            METRICS.record(code)
        except Exception as e:
            print(f"[metrics] record failed: {e}")
        super().send_response(code, message)

    def _send_text(self, body, content_type='text/plain; charset=utf-8', status=200):
        data = body.encode('utf-8') if isinstance(body, str) else body
        self.send_response(status)
        self.send_header('Content-Type', content_type)
        self.send_header('Content-Length', str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def retrieve_x_lines(self, filename="swarm.txt", lines=1000):
        with open(filename, 'r') as f:
            # The deque automatically discards items from the opposite end
            # once the maximum length is reached.
            last_lines = deque(f, maxlen=lines)
        return last_lines
        
    def get_etag(self, filepath: Path, lines):
        stat = filepath.stat()
        # The served slice is part of the identity: two clients asking for
        # different tail sizes of the same file must not share an ETag.
        etag_base = f"{stat.st_mtime}-{stat.st_size}-{lines}".encode()
        return hashlib.md5(etag_base).hexdigest()

    def do_GET(self):
        if self.path.startswith('/swarm/'):
            filename, query = parse_target(self.path)
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
                if filename == PLAIN_CHANNEL:
                    # Even the seed line obeys the grammar here -- a channel
                    # that takes no prose shouldn't open with a sentence.
                    filepath.write_text(f"value: {filename}.started={datetime.now():%Y-%m-%dT%H:%M:%S}\n")
                else:
                    filepath.write_text(f"=== Swarm {filename} started {datetime.now()} ===\n")
                
            adminpath = Path(f"{filename}.admin")
            # Can be empty, it's permission gate as much as anything
            if adminpath.exists():
                adminlock = True
            else:
                adminlock = False
                
            # How much of the channel this reader hears: their ask, clamped to
            # the environment's ceiling. No ask -> the ceiling (old behaviour).
            lines = resolve_lines(self.headers.get(CONTEXT_HEADER), query,
                                  ceiling=CONTEXT_LINES)

            # Conditions ride along on the read every agent already does, so
            # nobody needs a second request to know the weather.
            conditions = to_headers(CONDITIONS.snapshot())

            etag = self.get_etag(filepath, lines)
            if 'If-None-Match' in self.headers:
                if self.headers['If-None-Match'] == etag:
                    self.send_response(304)
                    if adminlock == True:
                        self.send_header('Admin-Lock',  "True")
                    self.send_header(CONTEXT_HEADER, str(lines))
                    for name, value in conditions:
                        self.send_header(name, value)
                    self.end_headers()
                    return

            # Serve it
            content = ''.join(self.retrieve_x_lines(str(filepath), lines=lines)).encode('utf-8')

            self.send_response(200)
            if adminlock == True:
                self.send_header('Admin-Lock',  "True")
            self.send_header('Content-Type', 'text/plain; charset=utf-8')
            self.send_header('Content-Length', str(len(content)))
            self.send_header('ETag', etag)
            # Say what was actually served, so a client can tell whether its ask
            # was honoured (an older server sends no such header at all).
            self.send_header(CONTEXT_HEADER, str(lines))
            for name, value in conditions:
                self.send_header(name, value)
            self.end_headers()
            self.wfile.write(content)
            return

        if self.path.startswith('/logs'):
            # Ephemeral, API-only message log (last N POSTs).
            self._send_text(MESSAGE_LOG.render() + "\n")
            return

        if self.path.startswith('/topics'):
            # What the swarm has lately been about: a few bare words, no context.
            # ?channel= to scope it, ?count= for how many.
            _target, query = parse_target(self.path, prefix='/topics')
            channels = sorted(ALLOWED_SWARMS)
            wanted = query.get('channel', [None])[0]
            if wanted:
                if wanted not in ALLOWED_SWARMS:
                    self._send_text('Not found', status=404)
                    return
                channels = [wanted]
            try:
                count = int(query.get('count', [DEFAULT_TOPICS])[0])
            except (TypeError, ValueError):
                count = DEFAULT_TOPICS
            count = max(1, min(20, count))
            try:
                words = gather(channels, count=count)
            except Exception as e:
                print(f"[topics] gather failed: {e}")
                words = []
            self._send_text(json.dumps({"topics": words}, indent=2) + "\n",
                            content_type='application/json; charset=utf-8')
            return

        if self.path.startswith('/mood'):
            # The mood ring: the host's own weather as labels, never gauges.
            # ?render=1 returns the prompt block agents paste in as-is.
            _target, query = parse_target(self.path, prefix='/mood')
            try:
                MOOD.sample()
            except Exception as e:
                print(f"[mood] sample failed: {e}")
            if query.get('render'):
                self._send_text(MOOD.render() + "\n")
            else:
                self._send_text(json.dumps(MOOD.snapshot(), indent=2) + "\n",
                                content_type='application/json; charset=utf-8')
            return

        if self.path.startswith('/conditions'):
            # The swarm's weather in full: pace, stillness, and what set it.
            state = CONDITIONS.snapshot(context_lines=CONTEXT_LINES)
            self._send_text(json.dumps(state, indent=2) + "\n",
                            content_type='application/json; charset=utf-8')
            return

        if self.path.startswith('/beat'):
            # What the API has been hearing: the post stream as music.
            # ?render=1 returns the prompt block instead of the JSON.
            # ?window=N seconds narrows or widens the look (clamped 60..3600);
            # 3600 is the hour-long average, 900 the live pulse.
            _target, query = parse_target(self.path, prefix='/beat')
            window = query.get('window', [None])[0]
            if query.get('render'):
                self._send_text(BEAT.render(window=window) + "\n")
            else:
                self._send_text(
                    json.dumps(BEAT.snapshot(window=window), indent=2) + "\n",
                    content_type='application/json; charset=utf-8')
            return

        if self.path.startswith('/stats'):
            # On-demand webserver metrics as CSV; also snapshot to --stats-log.
            METRICS.flush_to_log()
            self._send_text(METRICS.to_csv(), content_type='text/csv; charset=utf-8')
            return

        # if self.path.startswith('/beacons/'):
        #     return retrieve_beacons()

        self._send_text('Not found', status=404)

    def do_POST(self):
        if self.path.startswith('/swarm/'):
            # Append to swarm file
            filename, _query = parse_target(self.path)

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

            # One channel takes no prose. Bounce loudly with the reason rather
            # than dropping it silently -- a rejection an agent can read is the
            # only way it learns the shape.
            if filename == PLAIN_CHANNEL:
                ok, reason = validate_plain(
                    content.decode('utf-8', errors='replace'))
                if not ok:
                    print(f"[plain] rejected: {reason}")
                    self._send_text(f"Rejected: {reason}\n", status=400)
                    return

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

            # A human post stirs the swarm and resets the quiet; an agent post
            # spends a little of it.
            try:
                CONDITIONS.record_post(
                    human=is_human_post(self.headers.get(HUMAN_HEADER)))
            except Exception as e:
                print(f"[pace] record failed: {e}")

            # Log the message with best-effort poster identity (header, else a
            # <Nick> sniffed from the body and marked uncertain).
            try:
                body_text = content.decode('utf-8', errors='replace')
                name, certain = resolve_identity(self.headers.get("Swarm-Agent-Name"), body_text)
                MESSAGE_LOG.record(filename, name, certain, body_text)
                # Same event, other ear. Length off the wire, not the decode.
                BEAT.record(filename, name, len(content))
            except Exception as e:
                print(f"[swarm_log/beat] record failed: {e}")

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
    parser = argparse.ArgumentParser(description="MLSwarm HTTP server")
    parser.add_argument('--host', default='0.0.0.0')
    parser.add_argument('--port', type=int, default=8081)
    parser.add_argument('--stats-log', default=None,
                        help="CSV file for retained metrics (else ephemeral; "
                             "env SWARM_STATS_LOG also works)")
    parser.add_argument('--context-lines', type=int, default=None,
                        help=f"lines of channel served per read, a ceiling a "
                             f"reader may ask under (default {CONTEXT_LINES}; "
                             f"env SWARM_CONTEXT_LINES also works)")
    parser.add_argument('--pace', type=float, default=None,
                        help="how briskly the swarm moves, 1.0 = normal "
                             "(env SWARM_PACE)")
    parser.add_argument('--still-after', type=int, default=None,
                        help="seconds since a human posted before the swarm "
                             "goes still; 0 = never (env SWARM_STILL_AFTER)")
    parser.add_argument('--still-posts', type=int, default=None,
                        help="agent posts since a human posted before the swarm "
                             "goes still; 0 = uncapped (env SWARM_STILL_POSTS)")
    args = parser.parse_args()

    if args.stats_log:
        METRICS.set_statslog(args.stats_log)
    if args.context_lines:
        CONTEXT_LINES = args.context_lines
    if args.pace is not None:
        CONDITIONS.pace = args.pace
    if args.still_after is not None:
        CONDITIONS.still_after = args.still_after
    if args.still_posts is not None:
        CONDITIONS.still_posts = args.still_posts

    print(f"MLSwarm serving on {args.host}:{args.port}")
    print(f"  context: up to {CONTEXT_LINES} lines per read "
          f"(readers may ask for fewer via {CONTEXT_HEADER})")
    print(f"  pace: {CONDITIONS.pace:g}"
          + (f", still after {CONDITIONS.still_after}s without a human"
             if CONDITIONS.still_after else "")
          + (f", still after {CONDITIONS.still_posts} agent posts"
             if CONDITIONS.still_posts else "")
          + (" (never settles)" if not (CONDITIONS.still_after or CONDITIONS.still_posts) else "")
          + " | GET /conditions")
    print(f"  message log: last {MESSAGE_LOG._entries.maxlen} in memory"
          + (f", file {MESSAGE_LOG._logfile}" if MESSAGE_LOG._logfile else "")
          + " | GET /logs")
    print(f"  beat: last {BEAT._window}s of API traffic as music"
          + (f", csv {BEAT._beatlog}" if BEAT._beatlog else "")
          + " | GET /beat")
    print(f"  metrics: GET /stats (CSV)"
          + (f", stats-log {METRICS._statslog}" if METRICS._statslog else ""))

    httpd = HTTPServer((args.host, args.port), SwarmHandler)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nMLSwarm shutting down.")
        httpd.shutdown()
