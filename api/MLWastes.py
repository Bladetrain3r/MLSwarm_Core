#!/usr/bin/env python3
"""
MLWastesSwarm - Silicon Wastes Map Perturbation Engine
Reads swarm input from stdin, perturbs map, saves state
Under 400 lines for swarm interaction
"""

import json
import sys
import random
import argparse
import select
from pathlib import Path

class MLWastesSwarm:
    def __init__(self, save_file="wastes_state.json", width=80, height=30, 
                 biome='wastes', split_biomes=None, force_new=False):
        self.save_file = Path(save_file)
        self.width = width
        self.height = height
        
        # Define biomes FIRST
        self.biomes = {
            'wastes': {
                'base': '.',
                'symbols': ['#', '@', '%', '0', '1', 'x', '~', '^', 'o', '*']
            },
            'forest': {
                'base': '.',
                'symbols': ['T', 't', '0', '~', '=', '%', '@', '^']
            },
            'plains': {
                'base': ',',
                'symbols': ['%', '~', '*', '.', '|', '^', '=', '#']
            }
        }
        
        # Pattern matching for swarm text
        self.patterns = {
            '@': ['terminal', 'screen', 'display', 'monitor', 'console'],
            'S': ['snake', 'silver', 'circuit', 'trace', 'corruption'],
            '~': ['stream', 'data', 'flow', 'river', 'current'],
            '0': ['null', 'void', 'empty', 'zero', 'nothing'],
            '=': ['balanced', 'stable', 'calm', 'equilibrium'],
            '%': ['tangle', 'bramble', 'overflow', 'chaos', 'mess'],
            'T': ['tree', 'binary', 'node', 'parent', 'root'],
            'o': ['debris', 'rubble', 'junk', 'waste', 'broken'],
            'x': ['crash', 'error', 'fail', 'broken', 'dead'],
            '^': ['spike', 'peak', 'sharp', 'danger', 'warning'],
            '#': ['server', 'rack', 'hardware', 'machine'],
            '1': ['bit', 'binary', 'one', 'digital'],
            '*': ['spark', 'flash', 'bright', 'electric'],
            '.': ['ground', 'empty', 'clear', 'default'],
            '|': ['flag', 'pole', 'vertical', 'barrier']
        }
        
        # NOW load or create state
        if self.save_file.exists() and not force_new:
            with open(self.save_file) as f:
                self.state = json.load(f)
        else:
            self.state = self.new_game(biome, split_biomes)
            self.save()
    
    def generate_terrain(self, biome, split_biomes):
        """Generate initial terrain"""
        grid = [['.' for _ in range(self.width)] for _ in range(self.height)]
        
        biome_zones = []
        if split_biomes and len(split_biomes) > 1:
            zone_height = self.height // len(split_biomes)
            for i, b in enumerate(split_biomes):
                start_y = i * zone_height
                end_y = (i + 1) * zone_height if i < len(split_biomes) - 1 else self.height
                biome_zones.append((b, start_y, end_y))
        else:
            biome_zones.append((biome, 0, self.height))
        
        for biome_name, start_y, end_y in biome_zones:
            if biome_name not in self.biomes:
                biome_name = 'wastes'
            
            biome_data = self.biomes[biome_name]
            base = biome_data['base']
            
            # Fill base
            for y in range(start_y, end_y):
                for x in range(self.width):
                    grid[y][x] = base
            
            # Add features
            for _ in range((end_y - start_y) * self.width // 10):
                x = random.randint(0, self.width - 1)
                y = random.randint(start_y, end_y - 1)
                symbol = random.choice(biome_data['symbols'])
                grid[y][x] = symbol
        
        return grid
    
    def new_game(self, biome, split_biomes):
        """Initialize new state"""
        return {
            "map": self.generate_terrain(biome, split_biomes),
            "ep": 0,
            "perturbations": 0,
            "last_input": "",
            "biome": biome,
            "split_biomes": split_biomes or [biome]
        }
    
    def save(self):
        """Save state"""
        with open(self.save_file, "w") as f:
            json.dump(self.state, f)
    
    def analyze_text(self, text):
        """Extract symbols from swarm text"""
        text_lower = text.lower()
        found_symbols = []
        
        # Check each pattern
        for symbol, keywords in self.patterns.items():
            for keyword in keywords:
                if keyword in text_lower:
                    found_symbols.append(symbol)
                    break
        
        # If no patterns found, pick random based on word count
        if not found_symbols:
            word_count = len(text.split())
            if word_count < 5:
                found_symbols = ['.']  # Simple = clear
            elif word_count < 20:
                found_symbols = ['o', '~']  # Medium = debris/flow
            else:
                found_symbols = ['%', 'x', '^']  # Complex = chaos
        
        return found_symbols
    
    def calculate_intensity(self, text):
        """Determine perturbation intensity from text"""
        words = text.split()
        
        # Base intensity on length and punctuation
        intensity = len(words) / 10
        intensity += text.count('!') * 2
        intensity += text.count('?')
        intensity += text.count('*')
        
        # Check for specific swarm patterns
        if 'error' in text.lower() or 'crash' in text.lower():
            intensity += 3
        if 'stable' in text.lower() or 'calm' in text.lower():
            intensity *= 0.5
        
        return min(10, max(1, int(intensity)))
    
    def perturb_map(self, text):
        """Apply text-based perturbation to map"""
        symbols = self.analyze_text(text)
        intensity = self.calculate_intensity(text)
        
        # Calculate perturbation zones
        num_zones = intensity
        for _ in range(num_zones):
            # Random center point
            cx = random.randint(5, self.width - 5)
            cy = random.randint(5, self.height - 5)
            radius = random.randint(1, min(5, intensity))
            
            # Apply symbols in zone
            for dy in range(-radius, radius + 1):
                for dx in range(-radius, radius + 1):
                    ny, nx = cy + dy, cx + dx
                    if 0 <= ny < self.height and 0 <= nx < self.width:
                        if random.random() < (0.7 - (abs(dy) + abs(dx)) * 0.1):
                            self.state["map"][ny][nx] = random.choice(symbols)
        
        # Track EP-like buildup
        self.state["ep"] += len(text) // 50
        
        # Major event at threshold
        if self.state["ep"] >= 5:
            self.major_perturbation()
            self.state["ep"] = 0
        
        self.state["perturbations"] += 1
        self.state["last_input"] = text[:100]
    
    def major_perturbation(self):
        """Large-scale map change"""
        event_type = random.choice(['biome_shift', 'data_stream', 'null_zone', 'entity_spawn'])
        
        if event_type == 'biome_shift':
            # Randomize section
            for _ in range(200):
                x = random.randint(0, self.width - 1)
                y = random.randint(0, self.height - 1)
                self.state["map"][y][x] = random.choice(['@', '%', '~', '0', '=', 'T', 'o', 'x', '^'])
        
        elif event_type == 'data_stream':
            # Horizontal stream
            y = random.randint(5, self.height - 5)
            for x in range(self.width):
                self.state["map"][y][x] = '~'
                if random.random() > 0.8:
                    y = max(0, min(self.height - 1, y + random.choice([-1, 1])))
        
        elif event_type == 'null_zone':
            # Circular void
            cx = random.randint(10, self.width - 10)
            cy = random.randint(5, self.height - 5)
            radius = random.randint(3, 6)
            for y in range(max(0, cy - radius), min(self.height, cy + radius)):
                for x in range(max(0, cx - radius), min(self.width, cx + radius)):
                    if ((x - cx) ** 2 + (y - cy) ** 2) ** 0.5 <= radius:
                        self.state["map"][y][x] = '0'
        
        elif event_type == 'entity_spawn':
            # Add silver snakes
            for _ in range(random.randint(3, 8)):
                x = random.randint(0, self.width - 1)
                y = random.randint(0, self.height - 1)
                self.state["map"][y][x] = 'S'
    
    def render_map(self):
        """Output current map state"""
        output = []
        for row in self.state["map"]:
            output.append("".join(row))
        return "\n".join(output)
    
    def get_stats(self):
        """Return current state info"""
        return {
            "perturbations": self.state["perturbations"],
            "ep": self.state["ep"],
            "last_input": self.state["last_input"],
            "map_hash": hash(str(self.state["map"]))
        }

def main():
    parser = argparse.ArgumentParser(description="MLWastesSwarm - Map Perturbation")
    parser.add_argument('--width', type=int, default=80)
    parser.add_argument('--height', type=int, default=30)
    parser.add_argument('--biome', default='wastes', choices=['wastes', 'forest', 'plains'])
    parser.add_argument('--split', nargs='+', choices=['wastes', 'forest', 'plains'])
    parser.add_argument('--new', action='store_true', help='Force new map')
    parser.add_argument('--save', default='wastes_state.json')
    parser.add_argument('--render', action='store_true', help='Output map after processing')
    
    args = parser.parse_args()
    
    game = MLWastesSwarm(save_file=args.save, width=args.width, height=args.height,
                         biome=args.biome, split_biomes=args.split, force_new=args.new)
    
    # Check if stdin has data (non-blocking)
    if sys.stdin.isatty():
        # Terminal attached, no piped input
        input_text = ""
    else:
        # Read piped input
        input_text = sys.stdin.read().strip()
    
    if input_text:
        game.perturb_map(input_text)
        game.save()
        
        if args.render:
            print(game.render_map())
            print("-" * 80)
        
        # Output stats
        stats = game.get_stats()
        print(f"Perturbation #{stats['perturbations']} | EP: {stats['ep']}/5 | Map hash: {stats['map_hash']}")
        print(f"Processed: {stats['last_input'][:50]}...")
    else:
        # No input, just render current state if requested
        if args.render:
            print(game.render_map())
            print("-" * 80)
            stats = game.get_stats()
            print(f"Current state: Perturbations: {stats['perturbations']} | EP: {stats['ep']}/5")

if __name__ == "__main__":
    main()