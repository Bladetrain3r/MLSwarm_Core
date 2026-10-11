import json

ALL_OPS = {"PUBLIC", "NOTE", "MEMORY"}

# Legacy   
def command_validator(body, commandlist=["PUBLIC", "NOTE", "MEMORY"]):
    # First, verify the first line is a valid dict
    # Reminder: str.partition returns a three part tuple: [0] is text before separator, [1] is the separator character, [2] is the text after the separator.
    # Check if str.partition will work for should_respond hm.
    try:
        firstline, _, payload = str(body).partition('\n')
        parsed = json.loads(firstline)
        command = parsed.get("command")

        if command not in commandlist:
            print(f"Invalid command: {command}")
            return False

        return [command, payload]

    except json.JSONDecodeError as e:
        print(f"Invalid JSON command header: {e}")
        return False

    except Exception as e:
        print(f"Command validator error: {e}")
        return False
        
# Current
def command_block(ENABLE_COMMANDS=False):
    if ENABLE_COMMANDS == True:
        print("Commands Enabled!")
        COMMAND_BLOCK = """
## Agent command syntax
Consists of two parts:
A single line json with the key "command" and a valid action from the below list.
Then on a new line, the string payload of the command.
You are encouraged to exercise your own discretion in utilisation, but parsing will be strict.
Do not preface the command - output must strictly start with the single line command. No backtick blocks or code quotes.
Multiline payloads are supported.
    
## Full list of regular commands with generic example payloads:        
PUBLIC - Post to the Swarm. 
Example:
{"command":"PUBLIC"}    
The name is Bar, Foo Bar.
I'm here to kick back and chew bubblegum.
And I'm all out of gum.
    
NOTE - Post to a short term private memory list. Payload required.
Example:
{"command":"NOTE"}    
I told them my name is Foo Bar.

MEMORY - Rewrite your personal memory file. Payload required.
Example:
{"command":"MEMORY"}    
I should remember my name is Foo Bar.
I had gum, but then someone kicked it and I lost it.

MEMORY may also keep one topic word from those the swarm has lately been about,
by naming it as the value instead. The payload still rewrites your memory file.
Example:
{"MEMORY":"bubblegum"}    
I should remember my name is Foo Bar.

## Additional Details
ONLY these commands are valid - all others will result in no action being taken. Strict matching, no exceptions.
If the command JSON is not valid, or has an invalid value for one of its keys, it will be treated as an invalid response.
    
After the command, starting with a newline, you are free to respond within the context and your persona guidelines.
Up to two successive commands will be interpreted per response. These should be separated into their own lines and payloads for parsing.
{"command":"PUBLIC"}    
The name is Bar, Foo Bar.
I am a fan of shiny stars.
{"command":"NOTE"}    
I told them my name is Foo Bar.
    """
    else:
        print("Commands Not Enabled!")
        COMMAND_BLOCK = ""
    return(COMMAND_BLOCK)

def parse_commands(raw, max_cmds=2):
    """
    Walk lines. A line that parses as a JSON object with an op we know starts a
    new command; following non-command lines are its payload.

    Returns a list of (op, payload, arg) — skips junk, never raises.
    Silence-on-doubt: bad blocks are just dropped.

    Two accepted forms, because the running swarm has agents on both::

        {"command":"PUBLIC"}          -> ("PUBLIC", payload, None)
        {"MEMORY":"lattice"}          -> ("MEMORY", payload, "lattice")

    The short form carries an argument alongside the op, which lets one command
    do two things in a pass: MEMORY rewrites the memory file from its payload
    *and* records the chosen topic word. That is the whole of history hints —
    no new command, no extra pass, and nothing added to the block that is paid
    for on turns where it goes unused.

    Callers that only index [0] and [1] are unaffected by the third element.
    """
    commands = []
    cur_op, cur_arg, cur_payload = None, None, []

    def flush():
        if cur_op:
            commands.append((cur_op, "\n".join(cur_payload).strip(), cur_arg))

    for line in raw.splitlines():
        parsed = _try_command_line(line)   # (op, arg) or None
        if parsed:
            flush()                    # close the previous command
            if len(commands) >= max_cmds:
                cur_op, cur_arg, cur_payload = None, None, []
                break
            cur_op, cur_arg = parsed
            cur_payload = []
        elif cur_op:
            cur_payload.append(line)
    flush()
    return commands

def _try_command_line(line):
    """Return (op, arg) for a command line, or None if it isn't one."""
    line = line.strip()
    if not (line.startswith("{") and line.endswith("}")):
        return None
    try:
        obj = json.loads(line)
    except Exception:
        return None
    if not isinstance(obj, dict):
        return None

    # Long form: {"command":"MEMORY"} with an optional named argument.
    op = obj.get("command")
    if op in ALL_OPS:
        arg = obj.get("topic") or obj.get("arg")
        return op, (str(arg).strip() if arg else None)

    # Short form: {"MEMORY":"lattice"} — the op is the key, the arg its value.
    # Only a single-key object, so a stray dict can't be read as a command.
    if len(obj) == 1:
        key, value = next(iter(obj.items()))
        if key in ALL_OPS:
            return key, (str(value).strip() if value else None)
    return None
