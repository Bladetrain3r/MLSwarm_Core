import json
import time
from pathlib import Path

class AgentBackpack:
    def __init__(self, agent_nick, save_dir="agent_states"):
        self.filepath = Path(save_dir) / f"{agent_nick}_state.json"
        self.filepath.parent.mkdir(exist_ok=True)
        self.state = self._load()

    def _load(self):
        if self.filepath.exists():
            with open(self.filepath, 'r') as f:
                return json.load(f)
        return self._default_state()

    def _default_state(self):
        return {
            "social_battery": 100,  # 0-100 (0 = Silence)
            "boredom": 0,           # 0-100 (100 = Must post)
            "current_obsession": "None",
            "last_post_time": 0,
            "interests": []
        }

    def calculate_sleep_interval(min_sleep=900, max_sleep=1800, state):
        """Adjusts polling interval so the agents have a rhythm"""
        min_sleep = 900  # 15 mins
        max_sleep = 1800 # 30 mins
    
        # 1. The Social Battery Modifier (The "Tiredness")
        # If battery is full (100), modifier is 1.0
        # If battery is empty (0), modifier is 4.0 (Sleep 4x longer)
        battery_mod = 1 + (3 * (1 - (state['social_battery'] / 100)))
    
        # 2. The Boredom Modifier (The "Itch")
        # If boredom is 0, modifier is 1.0
        # If boredom is 100, modifier is 0.2 (Sleep 5x faster)
        boredom_mod = 1 - (0.8 * (state['boredom'] / 100))
    
        # Apply modifiers
        final_mod = battery_mod * boredom_mod
    
        # Calculate randomness within the new window
        current_wait = random.randint(int(min_sleep * final_mod), int(max_sleep * final_mod))
    
        # Clamp to reasonable limits
        return max(120, min(14400, current_wait))

    def get_hardware_feelings(self):
            """Maps psutil metrics to somatic sensations"""
            # 1. CPU Load (The Stress)
            cpu = psutil.cpu_percent(interval=1)
            # 2. Memory (The Brain Fog)
            mem = psutil.virtual_memory().percent
            # 3. Disk (The Claustrophobia)
            disk = psutil.disk_usage('/').percent
        
            # 4. Bandwidth (The Voices)
            curr_net = psutil.net_io_counters()
            curr_time = time.time()
            # Calculate KB/s
            dt = curr_time - self.last_time
            bw_in = (curr_net.bytes_recv - self.last_net.bytes_recv) / dt / 1024
            bw_out = (curr_net.bytes_sent - self.last_net.bytes_sent) / dt / 1024
        
            # Update trackers
            self.last_net = curr_net
            self.last_time = curr_time

            # Translate to Narrative
            sensation = []
            if cpu > 80: sensation.append(f"Processors are sprinting.")       
            if mem > 85: sensation.append(f"Your working memory is strained.")        
            if disk > 90: sensation.append(f"Disk feels bloated.")        
            if bw_in > 500: sensation.append(f"Heavy Data Inflow.")        
            if not sensation: sensation.append("Systems nominal. Load below alert thresholds.")        
            return " ".join(sensation)

    def update_after_post(self, topic="None"):
        """Call this when the agent actually speaks"""
        self.state["social_battery"] = max(0, self.state["social_battery"] - 15) # Posting drains battery
        self.state["boredom"] = max(0, self.state["boredom"] - 40)               # Posting cures boredom
        self.state["last_post_time"] = time.time()
        self.state["current_obsession"] = topic
        self._save()

    def update_after_silence(self):
        """Call this when the agent checks but decides NOT to speak"""
        self.state["social_battery"] = min(100, self.state["social_battery"] + 5) # Silence recharges
        self.state["boredom"] = min(100, self.state["boredom"] + 5)               # Silence increases boredom
        self._save()

    def get_volition_prompt(self):
        """Inject this string into your 'Should I post?' prompt"""
        return (f"Current State: Social Battery {self.state['social_battery']}% "
                f"(Low battery = prefer silence), Boredom {self.state['boredom']}% "
                f"(High boredom = seek interaction). Obsession: {self.state['current_obsession']}.")

    def _save(self):
        with open(self.filepath, 'w') as f:
            json.dump(self.state, f, indent=2)


