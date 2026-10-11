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
import hashlib
import argparse
from collections import defaultdict
sys.stdout.reconfigure(encoding='utf-8')

class MLBabel:
    def __init__(self, entropy=0.5, fragment_size=40, seed=None):
        """
        Initialize the Babel engine
        
        entropy: 0.0 = minimal scrambling, 1.0 = maximum chaos
        fragment_size: typical chunk size for processing
        seed: for reproducible madness
        """
        self.entropy = max(0.0, min(1.0, entropy))
        self.fragment_size = fragment_size
        self.memory = []  # All fragments ever seen
        self.word_freq = defaultdict(int)  # Word frequency map
        self.pairs = defaultdict(list)  # Word pair associations
        
        if seed:
            random.seed(seed)
        else:
            # Seed from current time + entropy for unique dreams
            random.seed(int(time.time() * 1000) + int(entropy * 1000))
    
    def consume(self, text):
        """Digest text into fragments and learn patterns"""
        # Clean and prepare text
        text = text.strip()
        if not text:
            return
        
        # Extract sentences/lines
        fragments = re.split(r'(?<=[.!?])\s+|\n', text)
        
        for fragment in fragments:
            if len(fragment.strip()) > 0:
                self.memory.append(fragment.strip())
                
                # Learn word patterns
                words = fragment.lower().split()
                for i, word in enumerate(words):
                    self.word_freq[word] += 1
                    if i < len(words) - 1:
                        self.pairs[word].append(words[i + 1])
    
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
                    fragment = random.choice(self.memory)
                    output.append(self._light_scramble(fragment))
                else:
                    # Combine two fragments
                    f1, f2 = random.sample(self.memory, 2)
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
            fragment = random.choice(self.memory)
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
        fragment = random.choice(self.memory)
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
        # Guard: randint(3, min(7, n)) raises ValueError below 3 memories
        if len(self.memory) < 3:
            return self._deep_scramble()
        # Take words from multiple fragments
        num_sources = random.randint(3, min(7, len(self.memory)))
        word_soup = []
        
        for _ in range(num_sources):
            fragment = random.choice(self.memory)
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
