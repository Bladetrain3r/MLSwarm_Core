#!/usr/bin/env python3
"""
MLBabel - Terminal Electric Sheep
Fragments of files dream new realities
Feed it text, receive transmuted consciousness
Part of ML-Extras (The Forbidden Collection)
"""

import sys
import random
import re
import time
import math
import hashlib
# from pathlib import Path
import argparse
from collections import defaultdict
# from datetime import datetime
sys.stdout.reconfigure(encoding='utf-8')

MAX_FRAGMENTS = 100_000
TRIM_TO = 90_000

class MLBabel:
    def __init__(self, entropy=0.5, fragment_size=60, seed=None,
                 embed_fn=None, focus_temp_min=0.1, focus_temp_max=1.0):
        """
        Initialize the Babel engine

        entropy: 0.0 = minimal scrambling, 1.0 = maximum chaos
        fragment_size: typical chunk size for processing
        seed: for reproducible madness
        embed_fn: optional callable(text) -> vector (list of float) or None.
                  When provided, consumed fragments are embedded and cached, and
                  set_focus() steers fragment selection toward a topic. When None
                  (the default), every selection path stays uniform random exactly
                  as before -- no behaviour change, no dependency.
        focus_temp_min/max: softmax temperature range for focus weighting. The
                  live temperature is interpolated from entropy, so a calm (low
                  entropy) engine selects tightly on-topic and a chaotic (high
                  entropy) one drifts back toward random.
        """
        self.entropy = max(0.0, min(1.0, entropy))
        self.fragment_size = fragment_size
        self.memory = []  # All fragments ever seen
        self.word_freq = defaultdict(int)  # Word frequency map
        self.pairs = defaultdict(list)  # Word pair associations

        # --- Optional semantic focus (embedding-weighted fragment selection) ---
        self.embed_fn = embed_fn
        self.fragment_vectors = []   # aligned 1:1 with self.memory (may hold None)
        self.focus_vector = None
        self.focus_temp_min = focus_temp_min
        self.focus_temp_max = focus_temp_max
        self.focus_candidate_cap = 512  # bound cosine work on very large memories

        if seed:
            random.seed(seed)
        else:
            # Seed from current time + entropy for unique dreams
            random.seed(int(time.time() * 1000) + int(entropy * 1000))
            
    def _rebuild_statistics(self):
        self.word_freq.clear()
        self.pairs.clear()

        for fragment in self.memory:
            words = fragment.lower().split()
            for i, word in enumerate(words):
                self.word_freq[word] += 1
                if i < len(words) - 1:
                    pair_list = self.pairs[word]
                    pair_list.append(words[i + 1])                  
                
                    if len(pair_list) > 200:   # per word cap
                        del pair_list[:50]     # trim oldest 50

    def _get_fragment_size(self):
        variance = int(self.fragment_size * self.entropy * 1.5)
        # skew: chaos pulls shorter more often than longer
        skew = int(self.entropy * variance * 0.3)
        size = self.fragment_size + random.randint(-variance, variance) - skew
        return max(20, size)
        
    def _truncate_to_phrase(self, text, max_chars):
        """Stage 1: truncate. Stage 2: snap back to last clean delimiter"""
        if len(text) <= max_chars:
            return text
        
        truncated = text[:max_chars]
        
        # Walk back to last sentence/clause boundary
        last_delim = max(
            truncated.rfind('. '),
            truncated.rfind('! '),
            truncated.rfind('? '),
            truncated.rfind(', '),
            truncated.rfind(' ')   # worst case: at least a word boundary
        )
        
        if last_delim > 0:
            return truncated[:last_delim].strip()
        return truncated.strip()

    def _rotate_memory(self):
        if len(self.memory) > MAX_FRAGMENTS:
            self.memory = self.memory[-TRIM_TO:]
            if self.fragment_vectors:
                self.fragment_vectors = self.fragment_vectors[-TRIM_TO:]
            self._rebuild_statistics()

    # ------------------------------------------------------------------
    # Semantic focus: embedding-weighted fragment selection (optional).
    # All of this is inert unless embed_fn was supplied AND a focus is set;
    # every guard falls back to plain random.choice, so a missing or failing
    # embedder never breaks generation.
    # ------------------------------------------------------------------
    def _safe_embed(self, text):
        """Embed one fragment, or return None (no embedder / failure). Storing
        None keeps fragment_vectors index-aligned with memory regardless."""
        if not self.embed_fn:
            return None
        try:
            vec = self.embed_fn(text)
        except Exception:
            return None
        return vec if vec else None

    def rebuild_embeddings(self):
        """Recompute fragment_vectors from memory. Call after bulk-loading
        memory (e.g. restoring a saved brain) so alignment is restored."""
        if not self.embed_fn:
            self.fragment_vectors = []
            return
        self.fragment_vectors = [self._safe_embed(f) for f in self.memory]

    def set_focus(self, topic):
        """Set the current semantic focus. topic may be a string (embedded via
        embed_fn), a vector (used directly), or None (clears focus)."""
        if topic is None:
            self.focus_vector = None
        elif isinstance(topic, str):
            self.focus_vector = self._safe_embed(topic)
        else:
            self.focus_vector = list(topic)

    @staticmethod
    def _cosine(a, b):
        if len(a) != len(b):
            return 0.0
        dot = sum(x * y for x, y in zip(a, b))
        ma = math.sqrt(sum(x * x for x in a))
        mb = math.sqrt(sum(y * y for y in b))
        if ma == 0.0 or mb == 0.0:
            return 0.0
        return dot / (ma * mb)

    def _focus_temperature(self):
        """Interpolate softmax temperature from entropy: low entropy -> peaky
        (on-topic), high entropy -> flat (back toward random)."""
        return self.focus_temp_min + self.entropy * (self.focus_temp_max - self.focus_temp_min)

    def _weighted_index(self):
        """Pick a memory index by softmax over cosine-to-focus, or None to fall
        back to uniform selection (no focus, no vectors, or misalignment)."""
        if self.focus_vector is None:
            return None
        n = len(self.memory)
        if n == 0 or len(self.fragment_vectors) != n:
            return None

        pool = range(n)
        if n > self.focus_candidate_cap:
            # Sample a candidate pool first so cost stays bounded on huge memories.
            pool = random.sample(range(n), self.focus_candidate_cap)

        cand, sims = [], []
        for i in pool:
            v = self.fragment_vectors[i]
            if v is None:
                continue
            cand.append(i)
            sims.append(self._cosine(self.focus_vector, v))
        if not cand:
            return None

        temp = max(1e-3, self._focus_temperature())
        peak = max(sims)
        weights = [math.exp((s - peak) / temp) for s in sims]
        total = sum(weights)
        if total <= 0.0:
            return None

        r = random.random() * total
        acc = 0.0
        for i, w in zip(cand, weights):
            acc += w
            if r <= acc:
                return i
        return cand[-1]

    def _choose_fragment(self):
        """Focus-weighted fragment when possible, else uniform random."""
        idx = self._weighted_index()
        if idx is not None:
            return self.memory[idx]
        return random.choice(self.memory)
    
    def consume(self, text):
        """Digest text into fragments and learn patterns"""
        # Clean and prepare text
        text = text.strip()
        if not text:
            return
        
        # Extract sentences/lines
        fragments = re.split(r'(?<=[.!?])\s+|\n', text)
        
        for fragment in fragments:
            fragment = fragment.strip()
            if fragment:
                fragment = self._truncate_to_phrase(fragment, self._get_fragment_size())
                if fragment:  # truncation might empty short fragments
                    self.memory.append(fragment)
                    if self.embed_fn:
                        self.fragment_vectors.append(self._safe_embed(fragment))

                # Learn word patterns
                words = fragment.lower().split()
                for i, word in enumerate(words):
                    self.word_freq[word] += 1
                    if i < len(words) - 1:
                        self.pairs[word].append(words[i + 1])
        self._rotate_memory()
    
    def dream(self, lines=10):
        """Generate scrambled output - the core Babel function"""
        if not self.memory:
            return "◉ The void dreams of nothing yet... ◉"
        
        output = []
        
        # Different generation modes based on entropy
        if self.entropy < 0.3:
            # Low entropy: mostly intact fragments, slight reordering
            for _ in range(lines):
                if random.random() < 0.7:
                    # Use existing fragment
                    fragment = self._choose_fragment()
                    output.append(self._light_scramble(fragment))
                else:
                    # Combine two fragments
                    if len(self.memory) >= 2:
                        f1 = self._choose_fragment()
                        f2 = self._choose_fragment()
                        output.append(self._merge_fragments(f1, f2))
                    
        elif self.entropy < 0.7:
            # Medium entropy: word recombination, pattern following
            for _ in range(lines):
                if self.pairs and random.random() < 0.6:
                    # Markov-like generation
                    output.append(self._markov_line())
                else:
                    # Fragment splicing
                    output.append(self._splice_fragments())
                    
        else:
            # High entropy: deep scrambling, word salad with structure
            for _ in range(lines):
                if random.random() < 0.3:
                    # Pure word chaos
                    output.append(self._word_chaos())
                elif random.random() < 0.6:
                    # Shuffled fragments
                    output.append(self._deep_scramble())
                else:
                    # Dimensional fold (mix everything)
                    output.append(self._dimensional_fold())
        
        return '\n'.join(output)
    
    def _light_scramble(self, text):
        """Minimal scrambling - swap a few words"""
        words = text.split()
        if len(words) > 3 and random.random() < self.entropy:
            # Swap 2 random words
            i, j = random.sample(range(len(words)), 2)
            words[i], words[j] = words[j], words[i]
        return ' '.join(words)
    
    def _merge_fragments(self, f1, f2):
        """Merge two fragments at random point"""
        w1 = f1.split()
        w2 = f2.split()
        
        if not w1 or not w2:
            return f1 + " " + f2
        
        cut1 = random.randint(0, len(w1))
        cut2 = random.randint(0, len(w2))
        
        return ' '.join(w1[:cut1] + w2[cut2:])
    
    def _markov_line(self):
        """Generate line using word associations"""
        if not self.pairs:
            return self._splice_fragments()
        
        # Start with random word
        current = random.choice(list(self.pairs.keys()))
        result = [current]
        
        for _ in range(random.randint(5, 20)):
            if current in self.pairs and self.pairs[current]:
                current = random.choice(self.pairs[current])
                result.append(current)
            else:
                # Jump to random word
                current = random.choice(list(self.pairs.keys()))
                result.append(current)
        
        return ' '.join(result)
    
    def _splice_fragments(self):
        """Splice random fragments together"""
        num_parts = random.randint(2, 4)
        parts = []
        
        for _ in range(num_parts):
            fragment = self._choose_fragment()
            words = fragment.split()
            if words:
                start = random.randint(0, len(words)-1)
                end = random.randint(start+1, min(start+8, len(words)))
                parts.append(' '.join(words[start:end]))
        
        return ' '.join(parts)
    
    def _word_chaos(self):
        """Pure word salad from frequency table"""
        if not self.word_freq:
            return self._deep_scramble()
        
        # Weighted random selection
        words = []
        word_list = list(self.word_freq.keys())
        
        for _ in range(random.randint(5, 25)):
            word = random.choice(word_list)
            words.append(word)
        
        return ' '.join(words)
    
    def _deep_scramble(self):
        """Deep scrambling of random fragment"""
        fragment = self._choose_fragment()
        words = fragment.split()
        
        # Multiple scrambling passes
        for _ in range(int(self.entropy * 5)):
            random.shuffle(words)
            
            # Sometimes duplicate words
            if random.random() < self.entropy * 0.3:
                idx = random.randint(0, len(words)-1)
                words.insert(idx, words[idx])
            
            # Sometimes remove words
            if len(words) > 3 and random.random() < self.entropy * 0.2:
                words.pop(random.randint(0, len(words)-1))
        
        return ' '.join(words)
    
    def _dimensional_fold(self):
        """Mix multiple realities - the deepest scramble"""
        # Take words from multiple fragments
        
        if len(self.memory) < 3:
            return self._deep_scramble()

        num_sources = random.randint(3, min(7, len(self.memory)))
        word_soup = []
        
        for _ in range(num_sources):
            fragment = self._choose_fragment()
            words = fragment.split()
            # Take random slice
            if words:
                start = random.randint(0, max(0, len(words)-3))
                end = min(start + random.randint(1, 5), len(words))
                word_soup.extend(words[start:end])
        
        # Scramble the soup
        random.shuffle(word_soup)
        
        # Apply strange transformations
        result = []
        for word in word_soup[:random.randint(10, 30)]:
            if random.random() < self.entropy * 0.1:
                # Reverse word
                result.append(word[::-1])
            elif random.random() < self.entropy * 0.05:
                # Repeat word
                result.append(word + word.lower())
            else:
                result.append(word)
        
        return ' '.join(result)
    
    def stream_dream(self, delay=0.5):
        """Stream consciousness mode - infinite generation"""
        print("◉ MLBabel Stream Mode - Ctrl+C to wake ◉\n")
        
        try:
            while True:
                # Generate and print one line
                line = self.dream(lines=1)
                print(line)
                
                # Occasionally print separators
                if random.random() < 0.1:
                    print("~" * random.randint(20, 60))
                
                time.sleep(delay)
                
                # Vary entropy slightly over time
                self.entropy = max(0.1, min(0.9, 
                    self.entropy + random.uniform(-0.05, 0.05)))
                    
        except KeyboardInterrupt:
            print("\n\n◉ The dream ends... for now ◉")
    
    def oracle(self, question):
        """Oracle mode - answer questions with scrambled wisdom"""
        # Hash question to seed response
        q_hash = int(hashlib.md5(question.encode()).hexdigest()[:8], 16)
        
        # Use question words to influence generation
        q_words = question.lower().split()
        
        # Add question influence to memory temporarily
        original_memory_len = len(self.memory)
        for word in q_words:
            if word in self.word_freq:
                # Find fragments containing this word
                for fragment in self.memory:
                    if word in fragment.lower():
                        self.memory.append(fragment)
        
        # Generate oracle response
        random.seed(q_hash + int(time.time() / 100))  # Stable for ~100 seconds
        
        intro = random.choice([
            "The fragments speak:",
            "The babel fish translates:",
            "The electric sheep dream:",
            "The void responds:",
            "The scrambled truth:",
        ])
        
        print(f"\n◉ {intro} ◉\n")
        response = self.dream(lines=random.randint(3, 7))
        
        # Restore original memory
        self.memory = self.memory[:original_memory_len]
        
        return response

def main():
    parser = argparse.ArgumentParser(
        description="MLBabel - Terminal Electric Sheep",
        epilog="""
Examples:
  mlbabel file.txt                      # Dream from single file
  mlbabel *.log --entropy 0.8           # High chaos from logs
  mlbabel --stream < /dev/stdin         # Stream mode from pipe
  cat code.py | mlbabel --oracle "What is truth?"
  mlbabel swarm.txt --lines 20 --seed 42  # Reproducible dreams
        """,
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    
    parser.add_argument('files', nargs='*', help='Input files to consume')
    parser.add_argument('-e', '--entropy', type=float, default=0.5,
                       help='Scrambling level 0.0-1.0 (default: 0.5)')
    parser.add_argument('-l', '--lines', type=int, default=10,
                       help='Number of lines to generate (default: 10)')
    parser.add_argument('-s', '--seed', type=int,
                       help='Random seed for reproducible output')
    parser.add_argument('--stream', action='store_true',
                       help='Stream mode - continuous generation')
    parser.add_argument('--fragment-size', type=int, default=40,
                       help='Target fragment size (default: 40)')
    parser.add_argument('--oracle', metavar='QUESTION',
                       help='Oracle mode - ask a question')
    parser.add_argument('--delay', type=float, default=0.5,
                       help='Delay between lines in stream mode')
    
    args = parser.parse_args()
    
    # Initialize Babel engine
    babel = MLBabel(
        entropy=args.entropy,
        fragment_size=args.fragment_size,
        seed=args.seed
    )
    
    # Load input
    if args.files:
        # Read from files
        for filepath in args.files:
            try:
                with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
                    content = f.read()
                    babel.consume(content)
                    print(f"◉ Consumed {filepath} ({len(content)} bytes)")
            except Exception as e:
                print(f"◉ Could not consume {filepath}: {e}", file=sys.stderr)
    else:
        # Read from stdin
        if not sys.stdin.isatty():
            content = sys.stdin.read()
            babel.consume(content)
            print(f"◉ Consumed stdin ({len(content)} bytes)", file=sys.stderr)
        else:
            print("◉ No input provided. The void remains empty.", file=sys.stderr)
            sys.exit(1)
    
    # Generate output based on mode
    if args.oracle:
        # Oracle mode
        response = babel.oracle(args.oracle)
        print(response)
    elif args.stream:
        # Stream mode
        babel.stream_dream(delay=args.delay)
    else:
        # Standard generation
        print("\n◉ The Babel dreams begin... ◉\n")
        output = babel.dream(lines=args.lines)
        print(output)
        print("\n◉ End of transmission ◉")

if __name__ == "__main__":
    main()
