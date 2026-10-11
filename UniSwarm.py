#!/usr/bin/env python3
"""
MLSwarmGUI - Graphical interface for MLSwarm
Using UniText's aesthetic as the base
Part of the ML-Extras collection
"""

import tkinter as tk
from tkinter import scrolledtext, messagebox, filedialog
import threading
import sys
import os
from datetime import datetime
from pathlib import Path
import time

# Constants matching ML style
WINDOW_WIDTH = 800
WINDOW_HEIGHT = 600
COLORS = {
    'dark_gray': '#3C3C3C',
    'light_gray': '#C0C0C0', 
    'green': '#00FF00',
    'white': '#FFFFFF',
    'black': '#000000',
    'cyan': '#00FFFF',
    'yellow': '#FFFF00'
}

class MLSwarmGUI:
    def __init__(self, root, swarm_file=None):
        self.root = root
        self.root.title("MLSwarm - File-based Chat")
        self.root.geometry(f"{WINDOW_WIDTH}x{WINDOW_HEIGHT}")
        self.root.configure(bg=COLORS['dark_gray'])
        
        # Chat state
        self.swarm_file = Path(swarm_file) if swarm_file else Path('swarm.txt')
        self.nick = os.environ.get('USER', 'anon')
        self.last_size = 0
        self.running = True
        self.auto_scroll = True
        
        self._create_ui()
        self._start_watcher()
        
        # Load existing content
        self._load_existing()
    
    def _create_ui(self):
        """Create the UI matching ML aesthetic"""
        # Title bar
        title_frame = tk.Frame(self.root, bg=COLORS['light_gray'], 
                              height=40, relief='raised', bd=2)
        title_frame.pack(fill='x')
        title_frame.pack_propagate(False)
        
        # Title with swarm info
        self.title_label = tk.Label(
            title_frame, 
            text=f"MLSwarm - {self.swarm_file.name} - {self.nick}",
            bg=COLORS['green'], 
            fg=COLORS['black'],
            font=('Courier', 14, 'bold')
        )
        self.title_label.pack(expand=True, fill='both', padx=2, pady=2)
        
        # Main chat area
        chat_frame = tk.Frame(self.root, bg=COLORS['dark_gray'])
        chat_frame.pack(fill='both', expand=True, padx=10, pady=5)
        
        # Chat display
        self.chat_area = scrolledtext.ScrolledText(
            chat_frame,
            wrap=tk.WORD,
            bg=COLORS['black'],
            fg=COLORS['white'],
            font=('Courier', 11),
            insertbackground=COLORS['green'],
            state='disabled',  # Read-only
            height=20
        )
        self.chat_area.pack(fill='both', expand=True)
        
        # Configure tags for different message types
        self.chat_area.tag_config('system', foreground=COLORS['cyan'])
        self.chat_area.tag_config('timestamp', foreground=COLORS['yellow'])
        self.chat_area.tag_config('nick', foreground=COLORS['green'])
        self.chat_area.tag_config('own_nick', foreground=COLORS['cyan'], font=('Courier', 11, 'bold'))
        
        # Input area
        input_frame = tk.Frame(self.root, bg=COLORS['dark_gray'])
        input_frame.pack(fill='x', padx=10, pady=5)
        
        # Nick label
        nick_label = tk.Label(
            input_frame,
            text=f"{self.nick}>",
            bg=COLORS['dark_gray'],
            fg=COLORS['green'],
            font=('Courier', 12)
        )
        nick_label.pack(side='left', padx=(0, 5))
        
        # Input entry
        self.input_entry = tk.Entry(
            input_frame,
            bg=COLORS['black'],
            fg=COLORS['white'],
            insertbackground=COLORS['green'],
            font=('Courier', 12),
            relief='solid',
            bd=1
        )
        self.input_entry.pack(side='left', fill='x', expand=True)
        self.input_entry.focus()
        
        # Send button
        send_btn = tk.Button(
            input_frame,
            text="Send",
            bg=COLORS['light_gray'],
            fg=COLORS['black'],
            font=('Courier', 10, 'bold'),
            bd=1,
            padx=20,
            command=self.send_message
        )
        send_btn.pack(side='left', padx=(5, 0))
        
        # Status bar
        status_frame = tk.Frame(self.root, bg=COLORS['light_gray'])
        status_frame.pack(fill='x')
        
        self.status_label = tk.Label(
            status_frame,
            text=f"Connected to {self.swarm_file}",
            bg=COLORS['light_gray'],
            fg=COLORS['black'],
            anchor='w',
            padx=5
        )
        self.status_label.pack(side='left', fill='x', expand=True)
        
        # Control buttons in status bar
        controls_frame = tk.Frame(status_frame, bg=COLORS['light_gray'])
        controls_frame.pack(side='right')
        
        # Auto-scroll toggle
        self.scroll_btn = tk.Button(
            controls_frame,
            text="📜",
            bg=COLORS['light_gray'],
            fg=COLORS['black'],
            font=('Courier', 10),
            bd=1,
            padx=5,
            command=self.toggle_autoscroll,
            relief='sunken' if self.auto_scroll else 'raised'
        )
        self.scroll_btn.pack(side='left', padx=2)
        
        # Clear button
        tk.Button(
            controls_frame,
            text="Clear",
            bg=COLORS['light_gray'],
            fg=COLORS['black'],
            font=('Courier', 10),
            bd=1,
            padx=5,
            command=self.clear_chat
        ).pack(side='left', padx=2)
        
        # File button
        tk.Button(
            controls_frame,
            text="File",
            bg=COLORS['light_gray'],
            fg=COLORS['black'],
            font=('Courier', 10),
            bd=1,
            padx=5,
            command=self.change_file
        ).pack(side='left', padx=2)
        
        # Help button
        tk.Button(
            controls_frame,
            text="?",
            bg=COLORS['light_gray'],
            fg=COLORS['black'],
            font=('Courier', 10, 'bold'),
            bd=1,
            padx=10,
            command=self.show_help
        ).pack(side='left', padx=5)
        
        # Keyboard bindings
        self.input_entry.bind('<Return>', lambda e: self.send_message())
        self.root.bind('<Control-q>', lambda e: self.quit())
        self.root.bind('<Control-n>', lambda e: self.change_nick())
        self.root.bind('<Control-o>', lambda e: self.change_file())
    
    def _load_existing(self):
        """Load existing chat content"""
        if self.swarm_file.exists():
            try:
                with open(self.swarm_file, 'r', encoding='utf-8') as f:
                    content = f.read()
                    if content:
                        self._append_to_chat(content, is_initial=True)
                self.last_size = self.swarm_file.stat().st_size
            except Exception as e:
                self._append_to_chat(f"Error loading file: {e}\n", tag='system')
    
    def _append_to_chat(self, text, tag=None, is_initial=False):
        """Append text to chat area with optional formatting"""
        self.chat_area.config(state='normal')
        
        if is_initial:
            # Just dump initial content
            self.chat_area.insert('end', text)
        else:
            # Parse and format new messages
            for line in text.splitlines():
                if line.startswith('==='):
                    # System message
                    self.chat_area.insert('end', line + '\n', 'system')
                elif line.startswith('[') and '] <' in line:
                    # Chat message - parse components
                    try:
                        timestamp_end = line.index(']')
                        timestamp = line[1:timestamp_end]
                        
                        nick_start = line.index('<', timestamp_end) + 1
                        nick_end = line.index('>', nick_start)
                        nick = line[nick_start:nick_end]
                        
                        message = line[nick_end + 2:]  # Skip "> "
                        
                        # Insert with formatting
                        self.chat_area.insert('end', '[', 'timestamp')
                        self.chat_area.insert('end', timestamp, 'timestamp')
                        self.chat_area.insert('end', '] <', 'timestamp')
                        
                        if nick == self.nick:
                            self.chat_area.insert('end', nick, 'own_nick')
                        else:
                            self.chat_area.insert('end', nick, 'nick')
                        
                        self.chat_area.insert('end', '> ')
                        self.chat_area.insert('end', message + '\n')
                    except:
                        # Fallback for malformed lines
                        self.chat_area.insert('end', line + '\n')
                else:
                    # Other content
                    self.chat_area.insert('end', line + '\n', tag)
        
        self.chat_area.config(state='disabled')
        
        # Auto-scroll if enabled
        if self.auto_scroll:
            self.chat_area.see('end')
    
    def _watcher_thread(self):
        """Background thread to watch for new messages"""
        while self.running:
            try:
                if self.swarm_file.exists():
                    current_size = self.swarm_file.stat().st_size
                    
                    if current_size != self.last_size:
                        with open(self.swarm_file, 'rb') as f:
                            # Handle file truncation
                            if current_size < self.last_size:
                                f.seek(0)
                                self.last_size = 0
                                # Clear chat on file reset
                                self.root.after(0, self.clear_chat)
                            else:
                                f.seek(self.last_size)
                            
                            new_content = f.read().decode('utf-8', errors='ignore')
                            if new_content.strip():
                                # Use after() to update GUI from main thread
                                self.root.after(0, lambda: self._append_to_chat(new_content))
                        
                        self.last_size = current_size
            except Exception as e:
                pass  # Silently handle file access errors
            
            time.sleep(0.5)  # Check twice per second
    
    def _start_watcher(self):
        """Start the file watcher thread"""
        watcher = threading.Thread(target=self._watcher_thread, daemon=True)
        watcher.start()
    
    def send_message(self):
        """Send a message to the swarm"""
        message = self.input_entry.get().strip()
        if not message:
            return
        
        # Special commands
        if message == '/quit':
            self.quit()
            return
        elif message == '/clear':
            self.clear_chat()
            self.input_entry.delete(0, 'end')
            return
        elif message.startswith('/nick '):
            new_nick = message[6:].strip()
            if new_nick:
                self.nick = new_nick
                self.title_label.config(text=f"MLSwarm - {self.swarm_file.name} - {self.nick}")
                self._append_to_chat(f"Nick changed to: {self.nick}\n", tag='system')
            self.input_entry.delete(0, 'end')
            return
        
        # Send normal message
        timestamp = datetime.now().strftime('%H:%M')
        chat_line = f"[{timestamp}] <{self.nick}> {message}\n"
        
        try:
            with open(self.swarm_file, 'a', encoding='utf-8') as f:
                f.write(chat_line)
            
            self.input_entry.delete(0, 'end')
            
            # Update status
            self.status_label.config(text=f"Sent at {timestamp}")
        except Exception as e:
            messagebox.showerror("Send Error", f"Could not send message:\n{e}")
    
    def toggle_autoscroll(self):
        """Toggle auto-scroll behavior"""
        self.auto_scroll = not self.auto_scroll
        self.scroll_btn.config(relief='sunken' if self.auto_scroll else 'raised')
        if self.auto_scroll:
            self.chat_area.see('end')
    
    def clear_chat(self):
        """Clear the chat display (not the file)"""
        self.chat_area.config(state='normal')
        self.chat_area.delete('1.0', 'end')
        self.chat_area.config(state='disabled')
        self._append_to_chat("=== Chat display cleared ===\n", tag='system')
    
    def change_nick(self):
        """Change nickname via dialog"""
        dialog = tk.Toplevel(self.root)
        dialog.title("Change Nick")
        dialog.geometry("300x70")
        dialog.transient(self.root)
        
        tk.Label(dialog, text="New nick:").pack(side='left', padx=5)
        entry = tk.Entry(dialog, width=20)
        entry.pack(side='left', padx=5)
        entry.insert(0, self.nick)
        entry.select_range(0, 'end')
        entry.focus()
        
        def set_nick(event=None):
            new_nick = entry.get().strip()
            if new_nick:
                self.nick = new_nick
                self.title_label.config(text=f"MLSwarm - {self.swarm_file.name} - {self.nick}")
                self._append_to_chat(f"Nick changed to: {self.nick}\n", tag='system')
            dialog.destroy()
        
        entry.bind('<Return>', set_nick)
        tk.Button(dialog, text="OK", command=set_nick).pack(side='left')
    
    def change_file(self):
        """Change or create swarm file"""
        filepath = filedialog.asksaveasfilename(
            title="Select Swarm File",
            defaultextension=".txt",
            filetypes=[("Text files", "*.txt"), ("All files", "*.*")],
            initialfile=self.swarm_file.name
        )
        
        if filepath:
            self.swarm_file = Path(filepath)
            self.last_size = 0
            
            # Create if doesn't exist
            if not self.swarm_file.exists():
                with open(self.swarm_file, 'w') as f:
                    f.write(f"=== Swarm started by {self.nick} at {datetime.now()} ===\n")
            
            # Reload
            self.clear_chat()
            self._load_existing()
            
            # Update UI
            self.title_label.config(text=f"MLSwarm - {self.swarm_file.name} - {self.nick}")
            self.status_label.config(text=f"Connected to {self.swarm_file}")
    
    def show_help(self):
        """Show help dialog"""
        help_text = """MLSwarm GUI v1.0 - File-based Chat

Commands in chat:
  /quit         Exit the application
  /clear        Clear chat display
  /nick NAME    Change your nickname

Keyboard Shortcuts:
  Ctrl+Q        Quit
  Ctrl+N        Change nickname
  Ctrl+O        Open/change swarm file
  Enter         Send message

Features:
• Multiple people can chat via shared file
• Works over any shared filesystem
• Auto-updates when new messages arrive
• No server needed - just file access

Tips:
• Use network shares, Dropbox, etc.
• Create multiple files for different chats
• The file persists all chat history

Part of ML-Extras collection
🦊 zerofuchs.co.za"""
        
        messagebox.showinfo("MLSwarm Help", help_text)
    
    def quit(self):
        """Clean shutdown"""
        self.running = False
        self.root.quit()

def main():
    """Main entry point"""
    import argparse
    
    parser = argparse.ArgumentParser(description="MLSwarm GUI - Graphical file-based chat")
    parser.add_argument('file', nargs='?', default='swarm.txt', 
                       help='Swarm file to use (default: swarm.txt)')
    parser.add_argument('-n', '--nick', help='Your nickname')
    
    args = parser.parse_args()
    
    root = tk.Tk()
    
    # Set nick from args or environment
    if args.nick:
        os.environ['USER'] = args.nick
    
    app = MLSwarmGUI(root, args.file)
    
    # Create file if it doesn't exist
    if not app.swarm_file.exists():
        with open(app.swarm_file, 'w') as f:
            f.write(f"=== Swarm started by {app.nick} at {datetime.now()} ===\n")
    
    root.mainloop()

if __name__ == "__main__":
    main()