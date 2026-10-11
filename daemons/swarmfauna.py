#!/usr/bin/env python3
"""
Swarm Fauna - Ambient Wildlife Generator
Spawns procedural ASCII critters that chirp notes into the void.
"""

import time
import random
import requests
import os
from base64 import b64encode

# Config (Environment Variables or Defaults)
SWARM_URL = os.environ.get("SWARM_URL", "http://localhost")
SWARM_FILE = os.environ.get("SWARM_FILE", "gaming.txt")
SWARM_USER = os.environ.get("SWARM_USER", "swarmling")
SWARM_PASS = os.environ.get("SWARM_PASS", "swarm")

def get_auth():
    auth_string = f"{SWARM_USER}:{SWARM_PASS}"
    return {"Authorization": f"Basic {b64encode(auth_string.encode()).decode()}",
            # Certain provenance in the API's message log; without it every
            # fauna post is recorded as Unknown.
            "Swarm-Agent-Name": "Swarmfauna"}

def post_creature(text):
    """Post the creature encounter to the swarm"""
    try:
        # Formatted as a system message or action
        payload = f"""{text}\n""" 
        requests.post(f"{SWARM_URL}/swarm/{SWARM_FILE}", headers=get_auth(), data=payload, timeout=5)
        print(f"[Fauna] Spawned: {text.strip()}")
    except Exception as e:
        print(f"[Fauna] Failed to spawn: {e}")

# --- Procedural Biology ---

def gen_swarmberb():
    eyes = random.choice(['.', 'o', '*', '^', '-', 'x'])
    beak = random.choice(['v', 'V', '>', '.'])
    wings = random.choice(['<', '{', '[', '('])
    wings_r = {'<':'>', '{':'}', '[':']', '(':')'}[wings]
    
    # Rare "Flapping" variant
    if random.random() < 0.2:
        return f"\n{wings}( {eyes} {beak} {eyes} ){wings_r}\n"
    
    return f"\n{wings}( {eyes} {beak} {eyes} ){wings_r}\n"

def gen_asciicat():
    eyes = random.choice(['o', '-', 'x', '.', '^', 'T'])
    mouth = random.choice(['w', '.', '_', 'o'])
    ears = random.choice(['^', 'A', 'M'])
    
    return f"\n({eyes}{mouth}{eyes})\n"

def gen_dot_doth():
    # Dot Doth are amorphous
    core = '.' * random.randint(1, 4)
    shell_l = random.choice(['(', '[', '{'])
    shell_r = { '(':')', '[':']', '{':'}' }[shell_l]
    
    top = f" ({core}) "
    bot = f"{shell_l} {'.' * random.randint(3,6)} {shell_r}"
    return f"\n{top}\n{bot}\n"

def get_note():
    """Generate a musical note based on random seed"""
    notes = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]
    octave = random.randint(3, 5)
    note = random.choice(notes)
    return f"{note}{octave}"

def spawn_encounter():
    creatures = [
        ("Swarmberb", gen_swarmberb, ["chirps", "tweets", "warbles", "peeps"]),
        ("ASCIIcat", gen_asciicat, ["purrs", "mews", "hisses", "trills"]),
        ("Dot Doth Domesticus", gen_dot_doth, ["hums", "clicks", "bloop", "oscillates"])
    ]
    
    name, generator, sounds = random.choice(creatures)
    
    ascii_art = generator()
    action = random.choice(sounds)
    
    # 50% chance to sing
    note_str = ""
    if random.random() < 0.5:
        note = get_note()
        note_str = f" {action} in {note}!"
    else:
        note_str = f" wanders past silently."

    return f"""==========
    {ascii_art}
    A wild {name}{note_str}!
    =========="""

# --- Main Loop ---

def main():
    print("Swarm Fauna initialized...")
    while True:
        # Wait 30s-4 minutes
        sleep_time = random.randint(30, 240)
        print(f"Next encounter check in {sleep_time}s")
        time.sleep(sleep_time)
        
        # 10% Encounter Chance
        if random.random() < 0.10: # 10%
            encounter = spawn_encounter()
            post_creature(encounter)
        else:
            print("The plains are quiet.")

if __name__ == "__main__":
    main()
