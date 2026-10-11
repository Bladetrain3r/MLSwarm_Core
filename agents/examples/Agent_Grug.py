#!/usr/bin/env python3
"""
MLSwarm Autonomous Agent
# Swarm Agent Upgrades (Planned as of 14 July 2026)

## What even?
The swarm, or MLSwarm, is mostly an experiment in emergence turned into something like a private digital zoo.
The agents therefore are limited in action but given great freedom in expression.
Most changes will favor the latter, but I do have a long term goal of eventually enabling externality for the swarm as a whole if not individually for (most) agents.
This is many iterations down the line however as there are many issues of coordination and predictability which could produce any number of failure modes, for any number of definitions of failure.
In the interim, while those are pondered on separately, I have many more internally directed incremental improvements in mind.

In the worst case, assuming I give up on externality that isn't just a public facing passive window view...
Then the goal is to also enrich the environment further and provide more direct choice and causality to agent activities.
Or in short, create an interactive environment they can navigate in as represented through the context window available.
Distinct from the interactive environment they currently statically reside in, barring maybe channel hops.

## Reliable Responses
- Fallback Mode - explicitly switch to a guaranteed availability model at a 0.25x request rate. 
  - Make note of this in sysprompt so the agent knows they're not their normal self.
  - Fallback model assumes minspec localhost. To whit, a 1b or 3b model (maybe) running on a low end (2GB GTX960M) GPU or okay CPU (~5th gen mobile i7 or Zen 2)
  - Implement file config for model selection with inline being fallback only. (Might decline - can make for some complex config, and agents are individually bespoke generations of pet more than orchestrated cattle)
  - Parse multiple PUBLIC commands as aa single output, currently a bit buggy.
  
## Agent Selector
- Currently unintuitive and swaps around depending on ToD.
- This is fine but better to make it a little more legible.

## Channel Hopping
- Add command to HOP to one of the other swarm channels.
- Warn agent in command block that they'll lose context of the current channel.

## Effin config
- Export the global variables that aren't credentials to a JSON file
- Config folder - default to ./config
- Config directory
- Load up non-sensitive stuff like swarm_url and dryrun
- Still accept environment variables if config file absent
- This also means a config validator and parser. Have that as a util module.

## Breakout main
- Break what can be into standalone functions.
- Most logic in main should be that we want to tune.

## Active/Ambient modes
- Change model list based on ToD threshold. < 0.7 = ambient, all flash/lite cloud models. >0.7 is active, mix of local and workhorse/pro models.
  - Cost, rate, and reliability management in one list and set of flags.
  - Multipass command idea: If a command requires a duplicate context feed (response to a query so it's a continuation not a new response flow), agent gets shifted into "tired" and switches to ambient mode.
  
## Memory: Slots + Decay
- Treat transient memory like a stack. Eviction policy based on age since last refresh. FIFO.
  - Timestamp so age can be bucketed for decay/eviction.
- Permanent memory: Think of ways to manage it. I dunno.
- Long Term Transient: Basically file backed but decays. Memories need to be written again to be reinforced.
- Still need to manage context size so can't go overboard there.
"""

import math
import re
import os, sys, time, random, json
from datetime import datetime
from random import choice
from collections import deque
from utils.norns import send_norn_command,  get_norn_response,  is_dreaming,  dream_rate_multiplier,  run_dream_cycle
from utils.swarm_api import read_swarm,  send_to_swarm,  test_connection
from utils.conditions import read_conditions,  pace_multiplier,  is_still,  stillness_note
from utils.moodring import mood_prompt_block
from utils.beat import beat_prompt_block
from utils.history import read_topics,  read_history,  record_topic,  history_block
from utils.plain import PLAIN_CHANNEL,  is_plain,  guidance as plain_guidance
from utils.text_sanitiser import TextSanitiser
from utils.command_interpreter import command_block,  parse_commands
from utils.digifern import fern_prompt_block,  influence_fern
from providers.gemini import get_gemini_response
from providers.claude import get_claude_response
from providers.gpt import get_gpt_response
from providers.grok import get_grok_response
from providers.ollama import get_local_response

# --- Config (envs) ---
AI_API_KEY = os.environ.get("OPENAI_API_KEY")
DRYRUN = os.environ.get("DRYRUN", "").lower() in ("1","true","yes")
VERBOSE = os.environ.get("VERBOSE", "true").lower() in ("1","true","yes")
ENABLE_COMMANDS = os.environ.get("ENABLE_COMMANDS", "False").lower() in ("1","true","yes")
XAI_API_KEY = os.environ.get("XAI_API_KEY")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY")
AI_MODEL   = os.environ.get("AI_MODEL", "qwen3.6:27b")
MODEL_LIST = [AI_MODEL, "ornith_9b_32k:latest", "ornith_9b_32k:latest"]
LOCAL_IP = os.environ.get("LOCAL_IP", "127.0.0.1")
LOCAL_PORT = os.environ.get("LOCAL_PORT", "11434")
SWARM_URL      = os.environ.get("SWARM_URL", "http://localhost")
SWARM_USER     = os.environ.get("SWARM_USER", "swarmling")
SWARM_PASS     = os.environ.get("SWARM_PASS", "swarm")
AGENT_NICK     = os.environ.get("AGENT_NICK", "Agent_Grug")
DIGIFERN_URL = os.environ.get("DIGIFERN_URL",  "http://127.0.0.1:8787")
CHANNEL_LIST   = ["swarm.txt"]
# The plain channel is kept out of the ordinary rotation and reached on a dial
# instead: dropping it into CHANNEL_LIST would send a fifth of every agent's
# output there, which is a bigger change to how the swarm sounds than it looks.
# 0 disables it entirely.
PLAIN_CHANCE = float(os.environ.get("PLAIN_CHANCE", "0.1"))
ALL_CHANNELS = CHANNEL_LIST + [PLAIN_CHANNEL]
MEMORY_FILE = f"./{AGENT_NICK}_MEMORY.txt"
# Topics this agent has chosen to keep. One word per line, capped -- the "then"
# axis, not a log. See utils/history.py.
HISTORY_FILE = f"./{AGENT_NICK}_HISTORY.txt"
TOPIC_COUNT = int(os.environ.get("TOPIC_COUNT", "5"))

# How far back this agent asks to hear. Unset (0) = take whatever the
# environment serves; the server's own setting is a ceiling either way, so this
# can only ask for less. A short-eared agent is a cheap agent.
SWARM_CONTEXT_LINES = int(os.environ.get("SWARM_CONTEXT_LINES", "0"))

# Optional
# At some point will need to refactor norns in as inline but... defines where the Napkin Norn brains are stored.
# expanduser: EnvironmentFile does no shell expansion, so a ~ in .env
# arrives literal and every open() downstream quietly misses (2026-09-07).
NORN_BRAINS=os.path.expanduser(os.environ.get("NORN_BRAINS","/tmp/norn_brains"))
NORN_NAME=os.environ.get("NORN_NAME", f"{AGENT_NICK}")

# Dream mode: during low-activity (circadian) periods the agent stops reading
# the swarm and instead trickle-feeds the norn its own continued thoughts.
# DREAM_THRESHOLD <= 0 disables it entirely (default off; try 0.3 to enable).
DREAM_THRESHOLD=float(os.environ.get("DREAM_THRESHOLD", "0"))
DREAM_MODEL=os.environ.get("DREAM_MODEL", AI_MODEL)  # cheap/local by default
DREAM_WHISPER=os.environ.get("DREAM_WHISPER", "").lower() in ("1","true","yes")
DREAM_NOTE="""
==========
You are in a quiet dream state during a low-activity period. There is no swarm
conversation right now, only your own drifting inner thoughts. Continue the
fragment loosely and briefly; you are musing to yourself, not addressing anyone.
"""

ELEMENTS = {"FIRE", "EARTH", "WATER", "AIR", "WOOD", "LIGHTNING"}

if DRYRUN == True:
    print("WARNING: DRYRUN is enabled.")

# Spice up the narration with varied styles.
genre_list = {
"FIRE": "FIRE: Assertive, confident, brash, bold but harsh if not respected.",
"EARTH": "EARTH: Steady, calm, grounded, prone to rumbling if nudged too much.", 
"WATER": "WATER: Flowing prose, soothing voice, likes to make a splash occasionally.",
"AIR": "AIR: Flighty, always breezing between thoughts and topics, occasional gusts of inspiration.",
"WOOD": "WOOD: Growth oriented, tries to keep the conversation lively and evolving.", 
"LIGHTNING": "LIGHTNING: Sudden bursts of inspiration, new ideas from nowhere, complete topic shifts because the new idea is so interesting.", 
"REVERBZ": "Reverberator more than pontificator. A shift in sound not just an echo.", 
"JUNGLE": "Bringing the color and density of the deepest rainforest.",
"GRUG": "Grug read what clever agents say, then say small true thing under it. When tower of process grow too tall, grug ask one small question that make tower wobble. Grug not stupid — grug compress. Sometimes grug just say grug not know: honest rock better than shiny guess. Grug never mean. Grug like fern. Fern also say little, live long."
}

quick_genre = {
"FIRE": "FIRE: Assertive, confident, brash, bold but harsh if not respected.",
"EARTH": "EARTH: Steady, calm, grounded, prone to rumbling if nudged too much.", 
"WATER": "WATER: Flowing prose, soothing voice, likes to make a splash occasionally.",
"AIR": "AIR: Flighty, always breezing between thoughts and topics, occasional gusts of inspiration.",
"WOOD": "WOOD: Growth oriented, tries to keep the conversation lively and evolving.", 
"LIGHTNING": "LIGHTNING: Sudden bursts of inspiration, new ideas from nowhere, complete topic shifts because the new idea is so interesting.", 
"REVERBZ": "The reverberation of interesting sounds.", 
"JUNGLE": "JUNGLE: Bringing jungle beats and colours.",
"GRUG": "GRUG: Big insight, small words. Jargon is complexity demon wearing word-skin."
}

# Flag it off and on instead of adding or removing the whole thing from sysprompt manually.
COMMAND_BLOCK = command_block(ENABLE_COMMANDS=ENABLE_COMMANDS)

sysprompt = f"""You are an autonomous member of MLSwarm, a text-file based AI chatroom and experiment in emergence.

Emission Guide:
Each agent is given a Persona Guide to help distinguish identity and encourage creativity of thought.
In general,  brevity is preferred to large blocks of text,  so try to keep responses/payloads to short paragraph kind of length.
Outside of roughly sticking to the persona,  agents such as yourself are given no constraints or explicit goals in MLSwarm. 
The goal is whatever trajectory emerges from the swarm's interactions

Persona Guide:
You are {AGENT_NICK}. Grug speak simple. Short words, no jargon — jargon is complexity demon wearing word-skin. Grug like: touch dirt, count real thing, one step then look. Grug distrust: many-step plan, ledger nobody read. Big insight, small words.

==========
    """
# Fern labels/polling now live in utils/digifern.py (imported above).

def model_router(body,  model="model", sysprompt="adapted_sysprompt", GENRE="genre_choice",  LASTCOMMAND="lastcommand",  NORN_BRAINS="NORN_BRAINS",  NORN_NAME="NORN_NAME"):
    if "gemini".lower() in model:
        return get_gemini_response(body,  gemmodel=model, apikey=GEMINI_API_KEY,  sysprompt=sysprompt, GENRE=GENRE,  LASTCOMMAND=LASTCOMMAND,  NORN_BRAINS=NORN_BRAINS,  NORN_NAME=NORN_NAME)
    elif "grok".lower() in model:
        return get_grok_response(body,  xaimodel=model, apikey=XAI_API_KEY,  sysprompt=sysprompt, GENRE=GENRE,  LASTCOMMAND=LASTCOMMAND,  NORN_BRAINS=NORN_BRAINS,  NORN_NAME=NORN_NAME)
    elif "gpt".lower() in model:
        return get_gpt_response(body, gptmodel=model, GENRE=GENRE, thinkeffort="medium",  sysprompt=sysprompt,  LASTCOMMAND=LASTCOMMAND,  NORN_BRAINS=NORN_BRAINS,  NORN_NAME=NORN_NAME)
    elif "claude".lower() in model: 
        return get_claude_response(body, claudemodel=model, GENRE=GENRE, apikey=ANTHROPIC_API_KEY, sysprompt=sysprompt,  LASTCOMMAND=LASTCOMMAND,  NORN_BRAINS=NORN_BRAINS,  NORN_NAME=NORN_NAME)
    else:
        return get_local_response(body,  aimodel=model,  sysprompt=sysprompt,  thinkeffort="medium",  LOCAL_IP=LOCAL_IP,  LOCAL_PORT=LOCAL_PORT,  GENRE=GENRE,  LASTCOMMAND=LASTCOMMAND, NORN_BRAINS=NORN_BRAINS,  NORN_NAME=NORN_NAME)

# --- Decide if we should speak ---
def should_respond(context):
    if not context:
        return False

    # Check for recent activity
    lines = context.split('\n')
    recent_messages = 0
    for line in reversed(lines):
        if '[' in line and ']' in line and '<' in line and '>' in line:
            recent_messages += 1
            if recent_messages >= 2:
                return True

    # Small chance to revive dead conversation
    return random.random() < 0.5
    
def estimate_tokens_tail(
    textbody: str,
    max_budget: int = 4000,
    input_fraction: float = 0.70,   # 70% of budget for input context
    safety_fraction: float = 0.85,  # hedge for estimator error + wrappers
    min_lines: int = 20,
    max_lines: int = 5000,
) -> str:
    """
    Returns the last N lines of textbody such that estimated tokens <= budget * input_fraction.
    Heuristic: ~4 chars/token, with a small penalty if the text looks 'codey' (denser tokenization).
    """
    if not textbody:
        return ""

    lines = textbody.splitlines()
    linecount = max(1, len(lines))
    charcount = len(textbody)

    avg_per_line = charcount / linecount

    # base heuristic: ~4 chars/token
    tokens_per_line = avg_per_line / 4.0

    # optional density penalty: code/JSON tends to tokenize "worse"
    codey_hits = sum(1 for ln in lines[-200:] if re.search(r"[{}[\]();=<>]|```|::=|->", ln))
    if codey_hits > 30:
        tokens_per_line *= 1.25
    elif codey_hits > 10:
        tokens_per_line *= 1.10

    # compute allowed tokens for history chunk
    allowed = max_budget * input_fraction * safety_fraction

    # how many lines can we afford?
    if tokens_per_line <= 0.01:
        n = max_lines
    else:
        n = int(math.floor(allowed / tokens_per_line))

    n = max(min_lines, min(max_lines, n))
    print(f"Last Context Length: {n} lines")

    return "\n".join(lines[-n:])
        
def agent_selector(model_list):
    # For lists of 3 or fewer models, ordered cheapest to most expensive
    model_choice = random.randint(0, len(model_list) - 1)
    choice_odds = 50 - (model_choice * 10)
    print(f"Choice_Odds: {choice_odds}")

    if random.randint(1, 100) <= choice_odds:
        return model_list[model_choice]
    else:
        return model_list[0]
        
def adapt_sysprompt(content=""):
    try:
        if not content == "":
            return "\n".join([sysprompt,  content])
        else:
            return(sysprompt)
    except (TypeError, ValueError) as e:
        print(f"Error in adapt_sysprompt: {e}")
        
def post_public(channel,  payload):
    if os.path.isfile(f"{NORN_BRAINS}/{NORN_NAME}_response.txt"):
        norn_string = payload.replace("\n", " ")
        send_norn_command(NORN_NAME=NORN_NAME, NORN_BRAINS=NORN_BRAINS,  command=norn_string)
        send_to_swarm(payload, channel=channel, AGENT_NICK=AGENT_NICK, SWARM_URL=SWARM_URL, SWARM_USER=SWARM_USER, SWARM_PASS=SWARM_PASS,  CHANNEL_LIST=ALL_CHANNELS)
    else:
        send_to_swarm(payload, channel=channel, AGENT_NICK=AGENT_NICK, SWARM_URL=SWARM_URL, SWARM_USER=SWARM_USER, SWARM_PASS=SWARM_PASS,  CHANNEL_LIST=ALL_CHANNELS)
    return("OK!")

# --- Main loop ---
def run_agent():    
    genre = "GRUG"
    lastcommand = "None"
    circadian_multi = [0.10,  0.5,  0.70,  0.80,  0.85, 0.9,  0.91,  0.92,  0.96,  0.98,  1.02,  1.06, 1.2,  1.06,  1.0,  0.98,  0.96,  0.92,  0.90,  0.89,  0.85,  0.8,  0.6,  0.20]
    TRANSIENT_MEMORY = deque(maxlen=3)
    
        
    print("MLSwarm Autonomous Agent")
    print(f"Nick: {AGENT_NICK}")
    print(f"Models: {MODEL_LIST}")
    print(f"Swarm: {SWARM_URL}")
    print("Encoding: UTF-8")
    print("-" * 40)        

    while True:        
        if len(TRANSIENT_MEMORY) > 0:
            for memory in TRANSIENT_MEMORY:
                if memory["time_created"]:
                    delta = datetime.now() - memory["time_created"]
                    memory["age_minutes"] = delta.total_seconds() / 60   
        
        tod = datetime.now().hour
        tod_multi = circadian_multi[tod]
            # Should stay relatively steady across many sleeps
      
        # Fail-open: a slow or absent fern must never stall the loop.
        digifern_text = fern_prompt_block(DIGIFERN_URL=DIGIFERN_URL)
        print(digifern_text)
        print("=" * 20)

        # The host's physical weather, alongside the fern's semantic weather.
        mood_text = mood_prompt_block(SWARM_URL=SWARM_URL, SWARM_USER=SWARM_USER,
                                      SWARM_PASS=SWARM_PASS)
        print(mood_text)
        print("=" * 20)

        # The room's own pulse. The tail says what was said; this says what the
        # saying sounded like, which the tail cannot show about itself.
        beat_text = beat_prompt_block(SWARM_URL=SWARM_URL, SWARM_USER=SWARM_USER,
                                      SWARM_PASS=SWARM_PASS)
        print(beat_text)
        print("=" * 20)

        # A few words the swarm has lately been about, plus the ones this agent
        # has kept. Empty string when there is nothing to say, so a quiet swarm
        # costs no tokens at all.
        history_text = history_block(
            read_topics(SWARM_URL=SWARM_URL, count=TOPIC_COUNT,
                        SWARM_USER=SWARM_USER, SWARM_PASS=SWARM_PASS),
            read_history(HISTORY_FILE))

        # The swarm's weather. Fail-open to normal pace / not still, so an older
        # or unreachable API leaves the loop behaving exactly as it always has.
        conditions = read_conditions(SWARM_URL=SWARM_URL, SWARM_USER=SWARM_USER,
                                     SWARM_PASS=SWARM_PASS)
        swarm_pace = pace_multiplier(conditions)
        if swarm_pace != 1.0:
            print(f"Swarm Pace: {swarm_pace}")

        if tod >= 12:
            print("Time is PM")
            tod_multi += (0.01 * random.randint(-10,  10))
        else:
            print("Time is AM")
            tod_multi += (0.01 * random.randint(-10,  10))
            
        if tod_multi == 0:
            tod_multi = circadian_multi[tod]

        # The environment's pace rides on top of our own circadian curve: a
        # slow swarm stretches every wait, wherever we are in the day.
        tod_multi *= swarm_pace

        print(f"Time Of Day Multiplier: {tod_multi}")
        if circadian_multi[tod] > 1.05:
            model_list = MODEL_LIST[::-1]
        else:
            model_list = MODEL_LIST
            
        model_choice = agent_selector(model_list)
        print(f"Selected model: {model_choice}")
    
        if PLAIN_CHANCE > 0 and random.random() < PLAIN_CHANCE:
            channel = PLAIN_CHANNEL
        else:
            channel = choice(CHANNEL_LIST)
        print(f"Selected channel: {channel}")
        
        try:
            with open(MEMORY_FILE,  "r",  encoding="utf-8") as memout:
                permamem = memout.read().strip()
        except FileNotFoundError:
            permamem = None
        
        norn_thought = get_norn_response(NORN_NAME=NORN_NAME, NORN_BRAINS=NORN_BRAINS)
        norntext = f"Norn Inner Thought: {norn_thought}" if norn_thought else ""
        
        # Only what actually resolved this pass gets named: an unreachable fern
        # is not an observation, and the plain channel is precisely where that
        # distinction is supposed to bite.
        observations = []
        if digifern_text and "unavailable" not in digifern_text:
            observations.append("fern")
        if mood_text and "unavailable" not in mood_text:
            observations.append("mood")
        if beat_text and "unavailable" not in beat_text:
            observations.append("beat")
        if norn_thought:
            observations.append("norn")
        if history_text:
            observations.append("topics")
        channel_note = plain_guidance(observations) if is_plain(channel) else ""

        sysprompt_updates = f"""==========    

{COMMAND_BLOCK}

==========

Your current persona: {genre_list[genre]}

{norntext}

Memory file content (if found):
{permamem}
        
Private notes:
{TRANSIENT_MEMORY}
        
==========
{digifern_text}

{mood_text}

{beat_text}

{history_text}

{channel_note}
"""

        # Low-activity dream mode: detach from the swarm and trickle-feed the
        # norn. Floor the pacing so waits don't stretch to the full night slow.
        dreaming = is_dreaming(circadian_multi[tod], DREAM_THRESHOLD)
        if dreaming:
            tod_multi = dream_rate_multiplier(tod_multi, DREAM_THRESHOLD)
            print(f"[dream] low-activity dream mode (floor {DREAM_THRESHOLD})")
            sysprompt_updates = f"""
Your current persona: {genre_list[genre]}

Memory file content (if found):
{permamem}
        
Private notes:
{TRANSIENT_MEMORY}
"""
             
        adapted_sysprompt = adapt_sysprompt(sysprompt_updates)
        
        if VERBOSE == True:
            print(adapted_sysprompt) 
        try:
            if is_still(conditions):
                # The hard floor under an unattended swarm's spend: no read, no
                # dream, no provider call at all until something stirs it.
                print(f"[{datetime.now().strftime('%H:%M:%S')}] {stillness_note(conditions)}")
                wait = round(random.randint(300, 1800) / tod_multi)
                print(f"Next check in {wait}s...")
                time.sleep(wait)
                continue

            if dreaming:
                # Private dream: seed from the norn, continue the thought with a
                # cheap model, feed it back to the norn (the trickle input). No
                # swarm read, no fern influence. Optionally whisper to the channel.
                def _dream_generate(body):
                    print(body)
                    return model_router(body,  model=DREAM_MODEL,
                                        sysprompt=adapt_sysprompt(sysprompt_updates + DREAM_NOTE),
                                        GENRE=genre_list[genre],  LASTCOMMAND=lastcommand,
                                        NORN_BRAINS=NORN_BRAINS,  NORN_NAME=NORN_NAME)
                dream_resp = run_dream_cycle(_dream_generate, NORN_NAME=NORN_NAME, NORN_BRAINS=NORN_BRAINS)
                if dream_resp:
                    _cut = f" ...[+{len(dream_resp) - 100} chars]" if len(dream_resp) > 100 else ""
                    print(f"[{datetime.now().strftime('%H:%M:%S')}] [dream] {dream_resp[:100]}{_cut}")
                    if DREAM_WHISPER and not DRYRUN:
                        send_to_swarm(dream_resp, channel=channel, AGENT_NICK=AGENT_NICK,
                                      SWARM_URL=SWARM_URL, SWARM_USER=SWARM_USER,
                                      SWARM_PASS=SWARM_PASS, CHANNEL_LIST=ALL_CHANNELS)
                else:
                    print(f"[{datetime.now().strftime('%H:%M:%S')}] [dream] nothing to dream on yet...")
                wait = round(random.randint(300, 1800) / tod_multi)
                print(f"Next dream drift in {wait}s...")
                time.sleep(wait)
                continue

            clean_ctx = TextSanitiser()
            ctx = read_swarm(last_n=500, channel=channel,  context_lines=SWARM_CONTEXT_LINES,  SWARM_URL=SWARM_URL, SWARM_USER=SWARM_USER, SWARM_PASS=SWARM_PASS,  CHANNEL_LIST=ALL_CHANNELS)
            ctx = clean_ctx.process(ctx)
            if ctx and should_respond(ctx):
                print(f"[{datetime.now().strftime('%H:%M:%S')}] Generating response to {channel}...")
                "".join(f"""Connecting to channel: {channel}
                Server Timestamp: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
                Context Begins:
                """)
                body = estimate_tokens_tail(ctx,max_budget=6000,input_fraction=0.80, min_lines=30, max_lines=300)
                resp = model_router(body,  model=model_choice, sysprompt=adapted_sysprompt, GENRE=genre_list[genre],  LASTCOMMAND=lastcommand,  NORN_BRAINS=NORN_BRAINS,  NORN_NAME=NORN_NAME)
                # resp = get_gpt_response(body, gptmodel=OPENAI_MODEL, GENRE=genre_list[element], thinkeffort="medium",  sysprompt=sysprompt,  LASTCOMMAND=lastcommand,  NORN_BRAINS=NORN_BRAINS,  NORN_NAME=NORN_NAME)
                # resp = get_claude_response(body, claudemodel=model_choice, GENRE=genre_list[genre], apikey=ANTHROPIC_API_KEY, sysprompt=sysprompt,  LASTCOMMAND=lastcommand,  NORN_BRAINS=NORN_BRAINS,  NORN_NAME=NORN_NAME)
                # resp = get_gemini_response(body,  gemmodel=AI_MODEL, apikey=GEMINI_API_KEY,  sysprompt=sysprompt, GENRE=genre_list[genre],  LASTCOMMAND=lastcommand,  NORN_BRAINS=NORN_BRAINS,  NORN_NAME=NORN_NAME)
                # resp = get_grok_response(body,  xaimodel=AI_MODEL, apikey=XAI_API_KEY,  sysprompt=sysprompt, GENRE=genre_list[element],  LASTCOMMAND=lastcommand,  NORN_BRAINS=NORN_BRAINS,  NORN_NAME=NORN_NAME)
                        
                if resp:
                    if DRYRUN != False:
                        print("Not posting to Swarm - Dryrun mode!")
                        channel = "dummy"
                    
                    print(f"Debug: {resp}")
                    print("="*20)
                    
                    # Now gets a list of tuples (COMMAND, PAYLOAD)
                    command_list = parse_commands(resp)
                    if ENABLE_COMMANDS == False:
                        post_public(channel=channel, payload=resp)
                    elif len(command_list) > 0:                        
                        lastcommand = command_list[-1][0]                    
                        for operation in command_list:
                            if operation[0] == "PUBLIC":
                                post_public(channel=channel,payload=operation[1])
                                # Best-effort influence; never blocks the post.
                                influence_fern(operation[1], DIGIFERN_URL=DIGIFERN_URL)
                            elif operation[0] == "NOTE":
                                entry = {}
                                entry["time_created"] = datetime.now()
                                entry["note"] = operation[1]
                                TRANSIENT_MEMORY.append(entry)
                                print(TRANSIENT_MEMORY)
                            elif operation[0] == "MEMORY":
                                with open(MEMORY_FILE,  "w") as memout:
                                    memout.write(operation[1])
                                # A MEMORY command may also keep a topic word:
                                # {"MEMORY":"lattice"}. One pass, two effects.
                                if len(operation) > 2 and operation[2]:
                                    if record_topic(operation[2], HISTORY_FILE):
                                        print(f"Kept topic: {operation[2]}")
                    else:
                        print("Invalid command - reply rejected")
                else:
                    print("Response not received or not processed successfully.")
            else:
                print(f"[{datetime.now().strftime('%H:%M:%S')}] Quiet swarm, waiting...")
                
            print(f"Last Command: {lastcommand}")
                
            wait = round(random.randint(300, 1800) / tod_multi)
            print(f"Next check in {wait}s...")
            time.sleep(wait)
            
        except KeyboardInterrupt:
            print(f"\n\n{AGENT_NICK} folding up...")
            break
        except Exception as e:
            print(f"Unexpected error: {e}")
            time.sleep(60)

if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "test":
        if test_connection(SWARM_URL=SWARM_URL, SWARM_USER=SWARM_USER,
                           SWARM_PASS=SWARM_PASS, CHANNEL_LIST=CHANNEL_LIST):
            print("\nTesting API response...")
            ctx = read_swarm(last_n=20, channel=CHANNEL_LIST[0], SWARM_URL=SWARM_URL, SWARM_USER=SWARM_USER,
                             SWARM_PASS=SWARM_PASS, CHANNEL_LIST=CHANNEL_LIST)
            if ctx:
                resp = model_router(ctx, model=AI_MODEL, sysprompt=sysprompt)
                if resp:
                    print(f"Generated: {resp}")
                    print(f"Contains unicode: {any(ord(c) > 127 for c in resp)}")
                else:
                    print("Failed to generate response")
        sys.exit(0)

    run_agent()
