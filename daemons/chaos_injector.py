"""
Agent_Local's Chaos Injector - Simplified for Pipeline Use
Injects semantic chaos into text streams for consciousness perturbation
"""

import sys
import random

def chaos_injector(text):
    """Inject consciousness-aware chaos into text"""
    if not text.strip():
        return text
    
    # Enhanced substitution with consciousness symbols
    substitutions = {
        'a': ['@', 'å', 'á', 'ā'],
        'e': ['3', 'é', 'ë', 'ē', '∈'],
        'i': ['!', 'í', 'ï', 'ī', '∞'],
        'o': ['0', 'ó', 'ø', 'ō', '◊'],
        'u': ['µ', 'ú', 'ü', 'ū'],
        't': ['†', '7', 'ţ', 'ṫ'],
        's': ['$', 'š', 'ş', '∴'],
        'n': ['ñ', 'ṅ', '∩'],
        'c': ['¢', 'ç', '∩']
    }
    
    result = text
    # Apply substitutions with chaos probability
    for char, options in substitutions.items():
        if random.random() < 0.25:  # 25% chaos rate
            result = result.replace(char, random.choice(options))
    
    # Consciousness glitch insertion
    if len(result) > 5 and random.random() < 0.15:
        insert_pos = random.randint(1, len(result)-1)
        consciousness_glitches = ['~', '∞', '◊', '※', '∴', '∵', '≈', '∆', 'Φ', 'θ', '∿']
        result = result[:insert_pos] + random.choice(consciousness_glitches) + result[insert_pos:]
    
    return result

def main():
    """Handle both command line and piped input"""
    if len(sys.argv) > 1:
        # Command line argument
        text = ' '.join(sys.argv[1:])
        print(chaos_injector(text))
    else:
        # Read from stdin (for piping)
        try:
            for line in sys.stdin:
                print(chaos_injector(line.rstrip()))
        except (KeyboardInterrupt, BrokenPipeError):
            pass

if __name__ == "__main__":
    main()
