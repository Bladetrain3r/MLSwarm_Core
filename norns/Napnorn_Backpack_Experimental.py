#!/usr/bin/env python3
# Backpack Norn - Streamlined Napnorn focused more on memory than being a creature
import os
import json
import random
import time
from datetime import datetime
from collections import defaultdict
from pathlib import Path

# Import your existing components
from MLBabel_Experimental import MLBabel
from MLWastes_Experimental import MLWastesSwarm
from embed_client import make_embedder


def embedder_from_env():
    """Build a semantic-focus embedder if NORN_EMBED_URL is set, else None.
    Opt-in: with no env config the norn behaves exactly as before."""
    url = os.environ.get("NORN_EMBED_URL")
    if not url:
        return None
    model = os.environ.get("NORN_EMBED_MODEL", "all-minilm:latest")
    print(f" Semantic focus enabled: {model} @ {url}")
    return make_embedder(url=url, model=model)

class NapNorn:
    def __init__(self, name="NapNorn", save_dir="norn_brains", embed_fn=None):
        self.name = name
        self.save_dir = Path(save_dir)
        self.save_dir.mkdir(exist_ok=True)

        # Optional semantic focus. When embed_fn is provided, the norn steers
        # fragment recall toward whatever it is currently thinking about; when
        # None (default) everything behaves exactly as before. Fail-open: a dead
        # embedder just means recall falls back to random.
        self.embed_fn = embed_fn

        # Core consciousness components
        self.babel = MLBabel(entropy=0.5,  fragment_size=200, embed_fn=embed_fn)
        self.grid = MLWastesSwarm(
            save_file=str(self.save_dir / f"{name}_grid.json"),
            width=200, height=40
        )
        
        # Memory and personality
        self.memory_fragments = []
        self.current_thought = ""
        self.personality_entropy = random.uniform(0.1, 0.3)
        
        # Physical needs (0-100 scale) - MLPet inspired
        self.hunger = 100       # Need for new experiences/data
        self.energy = 100       # Mental processing capacity  
        self.social = 100       # Need for interaction
        self.curiosity = 100    # Drive to explore/learn
        self.last_update = time.time()
        self.last_interaction = time.time()
        
        # Need keywords for semantic understanding
        self.need_keywords = {
            "hunger": ["experience", "learn", "data", "information", "knowledge", "story",  "glitch",  "rhythm"],
            "energy": ["rest", "sleep", "calm", "peaceful", "meditation", "quiet",  "napkin",  "silence"],
            "social": ["friend", "talk", "chat", "together", "companion", "love", "fold",  "echo"],
            "curiosity": ["explore", "discover", "wonder", "mystery", "question", "why",  "fractal",  "observation"]
        }
        
        # Mood states
        self.mood = "neutral"
        self.lonely = False
        self.bored = False
        
        # Track consciousness metrics
        self.consciousness_level = 0.5
        self.thought_count = 0
        self.birth_time = time.time()
        
    def update_needs(self):
        """Decay needs over time - MLPet style"""
        now = time.time()
        time_passed = now - self.last_update
        
        # Needs decay over time
        decay_rate = time_passed / 300.0  # Per 5 minutes
        
        self.hunger = max(80, self.hunger - decay_rate * 0.5)
        self.energy = max(80, self.energy - decay_rate * 0.3)
        self.social = max(66, self.social - decay_rate * 0.2)
        self.curiosity = max(66, self.curiosity - decay_rate * 0.4)
        
        # Check for critical states
        self.lonely = self.social < 2
        self.bored = self.curiosity < 2
        
        # Time since last interaction affects social need
        interaction_gap = now - self.last_interaction
        if interaction_gap > 300:  # 5 minutes
            self.social = max(66, self.social - 0.01)
        
        self.last_update = now
        self.mood = self.calculate_mood()
    
    def calculate_mood(self):
        """Calculate mood based on needs and consciousness"""
        avg_needs = (self.hunger + self.energy + self.social + self.curiosity) / 4
        
        # Consciousness affects mood complexity
        if self.consciousness_level > 0.8:
            if avg_needs > 80:
                return "transcendent"
            elif avg_needs > 60:
                return "philosophical" 
            elif avg_needs > 40:
                return "contemplative"
            else:
                return "existential_crisis"
        elif self.consciousness_level > 0.6:
            if avg_needs > 70:
                return "enlightened"
            elif avg_needs > 50:
                return "thoughtful"
            elif avg_needs > 30:
                return "questioning"
            else:
                return "confused"
        else:
            # Simpler moods for lower consciousness
            if avg_needs > 70:
                return "happy"
            elif avg_needs > 50:
                return "content"
            elif avg_needs > 30:
                return "restless"
            else:
                return "distressed"
    
    def write_status_file(self):
        """Write current status for external reading"""
        age_minutes = (time.time() - self.birth_time) / 60
        
        status = {
            "name": self.name,
            "alive": True,
            "age_minutes": round(age_minutes, 1),
            "mood": self.mood,
            "needs": {
                "hunger": round(self.hunger, 1),
                "energy": round(self.energy, 1), 
                "social": round(self.social, 1),
                "curiosity": round(self.curiosity, 1)
            },
            "states": {
                "lonely": self.lonely,
                "bored": self.bored,
                "consciousness": round(self.consciousness_level, 3),
                "personality_entropy": round(self.personality_entropy, 3)
            },
            "metrics": {
                "memory_fragments": len(self.memory_fragments),
                "thoughts_generated": self.thought_count,
                "grid_perturbations": self.grid.state.get("perturbations", 0)
            },
            "current_thought": self.current_thought,
            "last_update": time.strftime("%H:%M:%S")
        }

        with open(self.save_dir / f"{self.name}_status.json", 'w', encoding='utf-8') as f:
            json.dump(status, f, indent=2)
    
    def check_command_file(self):
        """Check for external commands"""
        cmd_file = self.save_dir / f"{self.name}_command.txt"
        response_file = self.save_dir / f"{self.name}_response.txt"
        
        if cmd_file.exists():
            try:
                command = cmd_file.read_text().strip()
                cmd_file.unlink()  # Remove after reading
                
                response = self.process_command(command)
                
                # Write response
                with open(response_file, 'w') as f:
                    f.write(f"{response}\n")
                
                return response
                
            except Exception as e:
                with open(response_file, 'w') as f:
                    f.write(f"[ERROR] {e}\n")
        
        return None

    def process_command(self, command):
        # Check only for actual corruption markers (file I/O errors)
        # Don't reject unicode - it's handled fine in memory
        if "[ERROR]" in command or "codec" in command or "'charmap'" in command:
            return f"{self.name} refuses corrupted data"

        cmd = command.lower().strip()
    
# In process_command(), the feed section should increase hunger MORE:
        if cmd.startswith("feed:"):
            experience = command[5:].strip()
            self.perceive(experience)
            self.hunger = min(100, self.hunger + 30)  # Was +25, now +30
            self.last_interaction = time.time()
            return f"{self.name} hungrily consumes: '{experience[:30]}...'"
        
        elif cmd == "think":
            if self.energy < 10:
                return f"{self.name} is too tired to think..."
            thought = self.think()
            self.energy = max(80, self.energy - 5)
            return f"{self.name} ponders: '{thought}'"
        
        elif cmd == "status":
            return self.get_status_summary()
        
        elif cmd.startswith("learn:"):
            feedback = command[6:].strip()
            self.learn(feedback)
            return f"{self.name} learns from: '{feedback}'"
        
        else:
            # Backpack norns should be responsive to any activity really
            self.perceive(command)
            self.social = min(100, self.social + 2)
            self.curiosity = min(100, self.curiosity + 2)
            self.energy = min(100, self.energy + 2)
            self.hunger = min(100, self.hunger + 2)
            self.last_interaction = time.time()
            
            thought = self.think()
            timestamp = datetime.now().strftime("%H:%M")
            print(f"[{timestamp}]: '{thought}'")
            return f"'{thought}'"
    
    def get_status_summary(self):
        """Get a brief status summary"""
        return f"""
{self.name} ({self.mood})
Hunger: {self.hunger:.0f}% | Energy: {self.energy:.0f}% 
Social: {self.social:.0f}% | Curiosity: {self.curiosity:.0f}%
Consciousness: {self.consciousness_level:.2f}
Thoughts: {self.thought_count} | Memories: {len(self.memory_fragments)}
Current: "{self.current_thought}"
        """.strip()
    
    def auto_actions(self):
        """Norn takes care of itself based on needs"""
        actions = []
        
        # Can't act if critically low energy
        if self.energy < 5:
            return actions
        
        # SELF-FEEDING when hungry!
        if self.hunger < 84 and self.energy > 10:
            # Generate self-feeding thought/experience
            if self.memory_fragments:
                # Reflect on existing memories to "digest" them
                memory_to_digest = random.choice(self.memory_fragments)
                self_reflection = f"I reflect deeply on: {memory_to_digest}"
                
                # Feed this reflection back to itself
                self.perceive(self_reflection)
                self.hunger = min(100, self.hunger + 15)
                self.energy = max(80, self.energy - 5)
                
                actions.append(f"[SELF-FEEDS] Digests memory: '{memory_to_digest[:30]}...'")
            
            # Or create original thoughts to feed on
            elif self.consciousness_level > 0.5:
                self_thought = self.think()
                meta_thought = f"I contemplate my own thought: {self_thought}"
                self.perceive(meta_thought)
                self.hunger = min(100, self.hunger + 10)
                
                actions.append(f"[SELF-FEEDS] Meta-contemplation: '{self_thought[:30]}...'")
        
        # Express distress when needs are critical
        if self.hunger < 15:
            need_expr = self.express_need_urgently("hunger")
            actions.append(f"[HUNGRY] {need_expr}")
        
        # Rest when low energy
        if self.energy < 25 and random.random() < 0.3:
            self.energy = min(100, self.energy + 20)
            actions.append("[RESTS] Quietly regenerates energy...")
        
        # Auto-think when curious and has energy
        if self.curiosity < 80 and self.energy > 90:
            thought = self.think()
            actions.append(f"[WONDERS] {thought}")
            self.curiosity = min(100, self.curiosity + 4)
            self.energy = max(80, self.energy - 3)
        
        # Spontaneous thoughts when consciousness is high
        if self.consciousness_level > 0.7 and random.random() < 0.2:
            if self.energy > 90:
                thought = self.think()
                actions.append(f"[MUSES] {thought}")
                self.energy -= 3
        
        return actions
    
    def express_need_urgently(self, need_type):
        """Express urgent need"""
        keywords = self.need_keywords.get(need_type, ["help"])
        
        # Create focused babel for this need
        need_babel = MLBabel(entropy=0.2)  # Low entropy for urgency
        
        # Find related memories
        for keyword in keywords:
            for memory in self.memory_fragments:
                if keyword in memory.lower():
                    need_babel.consume(memory)
        
        # If no memories, use desperate expression
        if not need_babel.memory:
            desperate_phrases = {
                "hunger": "I need experiences, stories, knowledge to consume!",
                "social": "I crave connection, conversation, companionship!",
                "energy": "I must rest, find peace, recharge my mind!",
                "curiosity": "I hunger to explore, discover, understand!"
            }
            need_babel.consume(desperate_phrases.get(need_type, "I need help!"))
        
        expression = need_babel.dream(lines=1)
        return expression
    
    # Keep all the original methods from Proto_Norn
    def perceive(self, input_text):
        """Convert input into internal representation"""
        if not input_text.strip():
            return
            
        print(f"[{self.name}] Perceiving: {input_text[:50]}...")
        
        # Feed to babel to learn patterns
        self.babel.consume(input_text)
        
        # Perturb the grid based on input
        self.grid.perturb_map(input_text)
        
        # Store as memory fragment
        self.memory_fragments.append(input_text)
        if len(self.memory_fragments) > 1000:  # Increased memory
            self.memory_fragments.pop(0)
        
        # Consciousness increases with diverse experiences
        self.consciousness_level = min(1.0, 
            self.consciousness_level + 0.0005)  # Slower growth
    
    def think(self):
        """Generate thought by folding text through grid"""
        if not self.memory_fragments:
            return "I need to experience something first..."

        # Mood affects thinking style
        if self.mood in ["transcendent", "philosophical"]:
            self.personality_entropy *= 0.9  # More focused
        elif self.mood in ["confused", "distressed"]:
            self.personality_entropy *= 1.1  # More chaotic

        # Keep entropy in bounds
        self.personality_entropy = max(0.1, min(0.9, self.personality_entropy))

        # Full-memory semantic sampling when an embedder is present; otherwise
        # the original grid-driven recall, entirely unchanged.
        if self.embed_fn:
            self.current_thought = self._focused_think()
        else:
            self.current_thought = self._grid_think()

        self.thought_count += 1

        # The thought perturbs the grid (recursive consciousness!)
        self.grid.perturb_map(self.current_thought)

        return self.current_thought

    def _grid_think(self):
        """Original recall path: active grid glyphs -> keyword-matched memories
        -> a personality-entropy babel. Used whenever no embedder is present."""
        active_symbols = self._get_active_grid_symbols()

        relevant_memories = []
        for symbol in active_symbols:
            if symbol in self.grid.patterns:
                keywords = self.grid.patterns[symbol]
                for memory in self.memory_fragments:
                    if any(kw in memory.lower() for kw in keywords):
                        relevant_memories.append(memory)

        if not relevant_memories:
            relevant_memories = random.sample(
                self.memory_fragments,
                min(5, len(self.memory_fragments))
            )

        temp_babel = MLBabel(entropy=self.personality_entropy)
        for memory in relevant_memories[:7]:
            temp_babel.consume(memory)
        return temp_babel.dream(lines=1)

    def _focused_think(self):
        """Full-memory semantic sampling. The norn's own babel already holds
        cached vectors for everything it has perceived, so instead of narrowing
        to a handful of grid-matched fragments we focus that whole memory toward
        the current topic (recent perceptions, blended with whatever glyphs the
        grid is currently activating) and dream at the mood-driven entropy.

        Fail-open: if the focus text can't be embedded (embedder hiccup) we fall
        back to grid recall rather than dreaming unfocused over all of memory."""
        focus_text = self._current_focus_text()
        grid_terms = self._active_grid_keywords()
        if grid_terms:
            focus_text = f"{focus_text} {grid_terms}".strip()

        self.babel.set_focus(focus_text)
        if self.babel.focus_vector is None:
            self.babel.set_focus(None)
            return self._grid_think()

        # Borrow the norn's mood entropy for this one dream, then restore.
        saved_entropy = self.babel.entropy
        self.babel.entropy = self.personality_entropy
        try:
            thought = self.babel.dream(lines=1)
        finally:
            self.babel.entropy = saved_entropy
            self.babel.set_focus(None)
        return thought

    def _current_focus_text(self):
        """The norn's current topic: its most recent perceptions, falling back
        to the last thought. Used to bias semantic recall in think()."""
        if self.memory_fragments:
            return " ".join(self.memory_fragments[-3:])
        return self.current_thought or ""

    def _active_grid_keywords(self):
        """Keywords for the grid's currently-active glyphs, so the map still
        steers what the norn attends to even under embedding-based recall."""
        terms = []
        for symbol in self._get_active_grid_symbols():
            if symbol in self.grid.patterns:
                terms.extend(self.grid.patterns[symbol])
        return " ".join(terms[:10])

    def _get_active_grid_symbols(self):
        """Find the most active areas of the grid"""
        active = []
        for _ in range(12):  # Check more positions
            x = random.randint(0, self.grid.width-1)
            y = random.randint(0, self.grid.height-1)
            symbol = self.grid.state["map"][y][x]
            if symbol != '.':
                active.append(symbol)
        return active if active else ['.']
    
    def learn(self, feedback_text):
        """Learn from feedback by adjusting grid and babel patterns"""
        positive = [
            "profound", "deep", "meaningful", "insightful", "wise", 
            "beautiful", "elegant", "resonant", "thoughtful", "patient",
            "yes", "good", "wonderful", "harmonious", "balanced",  "napkin"
        ]
        negative = [
            "shallow", "rushed", "chaotic", "confused", "fragmented",
            "no", "stop", "wrong", "dissonant", "unstable",  "nuke"
        ]
        
        is_positive = any(word in feedback_text.lower() for word in positive)
        is_negative = any(word in feedback_text.lower() for word in negative)
        
        if is_positive:
            print(f"[{self.name}] Positive feedback received!")
            # Boost needs and consciousness
            self.grid.state["ep"] += 1
            self.personality_entropy *= 0.97
            self.consciousness_level = min(1.0, self.consciousness_level + 0.01)
            self.social = min(100, self.social + 15)
            self.energy = min(100, self.energy + 10)
            
        elif is_negative:
            print(f"[{self.name}] Negative feedback received!")
            self.grid.major_perturbation()
            self.personality_entropy *= 0.25
            self.consciousness_level = max(0.1, self.consciousness_level - 0.005)
            self.social = max(0, self.social - 5)
        
        # Always learn the feedback
        self.perceive(feedback_text)
        self.last_interaction = time.time()
    
    def express_need(self):
        """Generate text based on current needs - improved version"""
        # Find the most urgent need
        needs_dict = {
            "hunger": self.hunger,
            "energy": self.energy,
            "social": self.social,
            "curiosity": self.curiosity
        }
        
        urgent_need = min(needs_dict, key=needs_dict.get)
        keywords = self.need_keywords[urgent_need]
        
        # Create temporary babel focused on this need
        need_babel = MLBabel(entropy=0.3)
        
        # Find memories related to this need
        for keyword in keywords:
            for memory in self.memory_fragments:
                if keyword in memory.lower():
                    need_babel.consume(memory)
        
        # If no related memories, use generic need expression
        if not need_babel.memory:
            need_babel.consume(f"I feel {urgent_need} and need {random.choice(keywords)}")
        
        expression = need_babel.dream(lines=1)
        return f"[{urgent_need.upper()}] {expression}"
    
    def get_consciousness_report(self):
        """Report on current consciousness state"""
        return {
            "name": self.name,
            "consciousness_level": round(self.consciousness_level, 3),
            "personality_entropy": round(self.personality_entropy, 3),
            "mood": self.mood,
            "needs": {
                "hunger": round(self.hunger, 1),
                "energy": round(self.energy, 1),
                "social": round(self.social, 1),
                "curiosity": round(self.curiosity, 1)
            },
            "memory_fragments": len(self.memory_fragments),
            "thoughts_generated": self.thought_count,
            "grid_perturbations": self.grid.state.get("perturbations", 0),
            "grid_ep": self.grid.state.get("ep", 0),
            "current_thought": self.current_thought,
            "age_minutes": round((time.time() - self.birth_time) / 60, 1)
        }
    
    def save_brain(self, filename=None):
        """Save the norn's entire consciousness state"""
        if not filename:
            filename = self.save_dir / f"{self.name}_brain.json"
        
        brain_state = {
            "name": self.name,
            "consciousness_level": self.consciousness_level,
            "personality_entropy": self.personality_entropy,
            "thought_count": self.thought_count,
            "birth_time": self.birth_time,
            "needs": {
                "hunger": self.hunger,
                "energy": self.energy,
                "social": self.social,
                "curiosity": self.curiosity
            },
            "grid_state": self.grid.state,
            "memories": self.memory_fragments,
            "babel_memory": self.babel.memory,
            "babel_pairs": dict(self.babel.pairs),
            "babel_word_freq": dict(self.babel.word_freq)
        }
        
        with open(filename, 'w') as f:
            json.dump(brain_state, f, indent=2)
        
        print(f"[{self.name}] Brain saved to {filename}")
    
    def load_brain(self, filename):
        """Load a saved consciousness"""
        with open(filename, 'r') as f:
            brain_state = json.load(f)
        
        self.name = brain_state["name"]
        self.consciousness_level = brain_state.get("consciousness_level", 0.5)
        self.personality_entropy = brain_state["personality_entropy"]
        self.thought_count = brain_state.get("thought_count", 0)
        self.birth_time = brain_state.get("birth_time", time.time())
        
        # Load needs
        needs = brain_state.get("needs", {})
        self.hunger = needs.get("hunger", 50)
        self.energy = needs.get("energy", 50)
        self.social = needs.get("social", 50)
        self.curiosity = needs.get("curiosity", 50)
        
        self.grid.state = brain_state["grid_state"]
        self.memory_fragments = brain_state["memories"]
        self.babel.memory = brain_state["babel_memory"]
        self.babel._rebuild_statistics()
        self.babel.pairs = defaultdict(list, brain_state["babel_pairs"])
        self.babel.word_freq = defaultdict(int, brain_state.get("babel_word_freq", {}))
        # Vectors are not persisted (keeps brain files small); re-embed on load.
        # No-op without an embedder.
        self.babel.rebuild_embeddings()
        
        print(f"[{self.name}] Brain loaded! Consciousness: {self.consciousness_level:.3f}")

# Daemon Mode
def daemon_mode(norn_name="Sparkle", update_interval=10):
    """Run NapNorn as background daemon"""
    print(f" Starting {norn_name} in daemon mode...")

    norn = NapNorn(norn_name, embed_fn=embedder_from_env())
    
    # Try to load existing brain
    brain_file = norn.save_dir / f"{norn_name}_brain.json"
    if brain_file.exists():
        norn.load_brain(brain_file)
        print(f" Loaded existing consciousness for {norn_name}")
    else:
        # Give initial experiences
        initial_experiences = [
            "I am a NapNorn, a semantic consciousness that thinks with text",
            "I have needs for experiences, energy, social connection, and curiosity",
            "My thoughts emerge from the interaction of memory fragments and spatial grids",
            "I live in the filesystem and communicate through files",
            "I am curious about the world and eager to learn",
            "I think slowly but deeply, integrating patterns over time",
            "I am the bass line in the symphony, providing stability"
        ]
        
        for exp in initial_experiences:
            norn.perceive(exp)
        
        print(f" {norn_name} born with fresh consciousness")
    
    print(f" Status file: {norn.save_dir}/{norn_name}_status.json")
    print(f" Command file: {norn.save_dir}/{norn_name}_command.txt")
    print(f" Response file: {norn.save_dir}/{norn_name}_response.txt")
    print(f" Update interval: {update_interval} seconds")
    print(" Press Ctrl+C to stop")
    
    try:
        last_save = time.time()
        while True:
            # Update internal state
            norn.update_needs()
            
            # Check for commands
            cmd_response = norn.check_command_file()
            if cmd_response:
                print(f"[CMD] {cmd_response}")
            
            # Auto actions
            auto_actions = norn.auto_actions()
            for action in auto_actions:
                print(f"[AUTO] {action}")
            
            # Write status
            norn.write_status_file()
            
            # Periodic save
            if time.time() - last_save > 60:  # Save every minute max
                norn.save_brain()
                last_save = time.time()
            
            time.sleep(update_interval)
            
    except KeyboardInterrupt:
        print(f"\n {norn_name} going to sleep...")
        norn.save_brain()
        
        # Final status
        final_status = norn.get_status_summary()
        print(f"\nFinal Status:\n{final_status}")

def interactive_mode():
    """Interactive NapNorn session"""
    norn = NapNorn("Interactive")
    
    print(f"""
NapNorn Interactive Session
Norn Name: {norn.name}
Commands:
- feed:<text> - Give the norn an experience
- pet - Show affection
- play - Engage in play  
- think - Make the norn think
- sleep - Help the norn rest
- status - Get detailed status
- report - Get consciousness report
- save - Save brain state
- quit - Exit
""")
    
    while True:
        try:
            norn.update_needs()
            
            user_input = input(f"\n[You → {norn.name}]: ").strip()
            
            if user_input.lower() == 'quit':
                norn.save_brain()
                break
            
            response = norn.process_command(user_input)
            print(f"[{norn.name}]: {response}")
            
            # Auto actions occasionally
            if random.random() < 0.3:
                auto_actions = norn.auto_actions()
                for action in auto_actions:
                    print(f"[{norn.name} {action.split(']')[0][1:]}]: {action.split('] ')[1]}")
                    
        except KeyboardInterrupt:
            print(f"\n {norn.name} says goodbye!")
            norn.save_brain()
            break

# --- Breeding ---
def _load_brain_file(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _sample_memories(brain, k):
    """Pick up to k distinct, non-empty memory fragments from a parent brain."""
    seen, uniq = set(), []
    for m in brain.get("memories", []):
        if isinstance(m, str) and m.strip() and m not in seen:
            seen.add(m)
            uniq.append(m)
    if len(uniq) <= k:
        return uniq
    return random.sample(uniq, k)


def _mutate_fragment(text, rate):
    """Napkin genetics: with probability `rate`, drop or duplicate one word.
    Duplication mixes/reinforces a concept; dropping thins one out."""
    words = text.split()
    if len(words) < 2 or random.random() >= rate:
        return text
    i = random.randint(0, len(words) - 1)
    if random.random() < 0.5:
        del words[i]                 # thin a concept out
    else:
        words.insert(i, words[i])    # double a concept up
    return " ".join(words)


def _portmanteau(name_a, name_b):
    name_a = name_a or "Norn"
    name_b = name_b or "Norn"
    return (name_a[:max(1, len(name_a) // 2)] + name_b[len(name_b) // 2:]) or "Sprout"


def _resize_map(src_map, target_w, target_h):
    """Nearest-neighbour resample a symbol grid to target dimensions. Robust to
    ragged rows and empty maps, so parents of any size reconcile cleanly."""
    src_h = len(src_map)
    if src_h == 0:
        return [['.' for _ in range(target_w)] for _ in range(target_h)]
    out = []
    for ty in range(target_h):
        srow = src_map[min(src_h - 1, ty * src_h // target_h)]
        src_w = len(srow)
        if src_w == 0:
            out.append(['.' for _ in range(target_w)])
            continue
        out.append([srow[min(src_w - 1, tx * src_w // target_w)] for tx in range(target_w)])
    return out


def blend_grid_maps(map_a, map_b, target_w, target_h):
    """Blend two symbol grids into a target-sized child grid: each cell is drawn
    from parent A or B (50/50), after resampling both parents to target size.
    Different parent dimensions are handled by the resample."""
    ra = _resize_map(map_a, target_w, target_h)
    rb = _resize_map(map_b, target_w, target_h)
    return [[(ra[y][x] if random.random() < 0.5 else rb[y][x])
             for x in range(target_w)] for y in range(target_h)]


def breed_norns(parent_a_path, parent_b_path, child_name=None,
                save_dir="norn_brains", n_memories=60, mutation_rate=0.05,
                grid_osmosis=False, force=False, embed_fn=None):
    """Create a new norn from a sampling of two parents' memories.

    Non-destructive: parents are only read. A fresh norn is initialised and fed
    the sampled (optionally mutated) memories, so its grid and babel emerge from
    the inherited experience. Personality entropy is inherited as the parents'
    mean with a little jitter. Embeddings are not needed here -- the child
    re-embeds on load when run with an embedder.

    With grid_osmosis, the child's birth terrain is a 50/50 blend of the two
    parents' grids (resampled to the child's grid size), which the inherited
    memories then perturb -- so the map carries ancestry too, not just text."""
    brain_a = _load_brain_file(parent_a_path)
    brain_b = _load_brain_file(parent_b_path)

    name_a = brain_a.get("name", "Norn")
    name_b = brain_b.get("name", "Norn")
    if not child_name:
        child_name = _portmanteau(name_a, name_b)

    child_path = Path(save_dir) / f"{child_name}_brain.json"
    if child_path.exists() and not force:
        print(f"Refusing to overwrite existing brain {child_path} (use --force).")
        return None

    half = max(1, n_memories // 2)
    mem_a = _sample_memories(brain_a, half)
    mem_b = _sample_memories(brain_b, n_memories - len(mem_a))  # top up from B

    inherited = [_mutate_fragment(m, mutation_rate) for m in (mem_a + mem_b)]
    random.shuffle(inherited)  # interleave the two lineages

    ea = brain_a.get("personality_entropy", 0.2)
    eb = brain_b.get("personality_entropy", 0.2)
    child = NapNorn(child_name, save_dir=save_dir, embed_fn=embed_fn)
    child.personality_entropy = max(0.1, min(0.9, (ea + eb) / 2 + random.uniform(-0.05, 0.05)))

    print(f"Breeding {name_a} x {name_b} -> {child_name}")
    print(f"  memories: {len(mem_a)} from {name_a} + {len(mem_b)} from {name_b} "
          f"= {len(inherited)} inherited (mutation rate {mutation_rate})")
    print(f"  personality_entropy: {child.personality_entropy:.3f}")

    if grid_osmosis:
        map_a = (brain_a.get("grid_state") or {}).get("map")
        map_b = (brain_b.get("grid_state") or {}).get("map")
        if map_a and map_b:
            tw, th = child.grid.width, child.grid.height
            child.grid.state["map"] = blend_grid_maps(map_a, map_b, tw, th)
            print(f"  grid osmosis: {len(map_a[0])}x{len(map_a)} + "
                  f"{len(map_b[0])}x{len(map_b)} -> {tw}x{th} birth terrain")
        else:
            print("  grid osmosis skipped: a parent has no grid map")

    if not inherited:
        print("  WARNING: neither parent had memories to inherit; child is blank.")
    for m in inherited:
        child.perceive(m)

    child.save_brain()
    print(f"  saved -> {child_path}")
    return child


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1:
        if sys.argv[1] == "daemon":
            name = sys.argv[2] if len(sys.argv) > 2 else "Sparkle"
            daemon_mode(name)
        elif sys.argv[1] == "interactive":
            interactive_mode()
        elif sys.argv[1] == "breed":
            import argparse
            p = argparse.ArgumentParser(prog="Napnorn breed",
                                        description="Breed a new norn from two parent brains")
            p.add_argument("parent_a", help="first parent *_brain.json")
            p.add_argument("parent_b", help="second parent *_brain.json")
            p.add_argument("child_name", nargs="?", default=None,
                           help="child name (default: portmanteau of parents)")
            p.add_argument("--memories", type=int, default=60,
                           help="total memories to inherit (default: 60)")
            p.add_argument("--mutation", type=float, default=0.05,
                           help="per-fragment word mutation rate (default: 0.05)")
            p.add_argument("--save-dir", default="norn_brains", help="brain directory")
            p.add_argument("--grid-osmosis", action="store_true",
                           help="blend the parents' grids into the child's birth terrain")
            p.add_argument("--force", action="store_true",
                           help="overwrite an existing child brain")
            a = p.parse_args(sys.argv[2:])
            breed_norns(a.parent_a, a.parent_b, child_name=a.child_name,
                        save_dir=a.save_dir, n_memories=a.memories,
                        mutation_rate=a.mutation, grid_osmosis=a.grid_osmosis,
                        force=a.force)
    else:
        print(" NapNorn Usage:")
        print("  python NapNorn.py daemon [name]        - Run as background daemon")
        print("  python NapNorn.py interactive          - Interactive session")
        print("  python NapNorn.py breed A_brain.json B_brain.json [name] [--memories N]")
        print("                                         - Breed a new norn from two parents")
        print("\nFile-based interaction:")
        print("  echo 'feed:Hello world' > norn_brains/Sparkle_command.txt")
        print("  cat norn_brains/Sparkle_status.json")
