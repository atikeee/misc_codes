#!/usr/bin/env python3
import os
import sys
import argparse
from mutagen import File
from mutagen.id3 import TIT2, TPE1, TPE2, TALB, TDRC, TRCK, TCON, COMM

# Global Cache for Configs
CONFIG_CACHE = {}

def load_config_mapped(ext):
    """
    Reads [ext].tags.conf. 
    Returns a dict: { 'KEY': 'VALUE_TO_WRITE' }
    If no value is provided (e.g. just 'TPE1'), value is None.
    """
    ext_clean = ext.lower().replace('.', '')
    if ext_clean in CONFIG_CACHE:
        return CONFIG_CACHE[ext_clean]

    conf_name = f"{ext_clean}.tags.conf"
    config_map = {}
    
    if os.path.exists(conf_name):
        with open(conf_name, 'r', encoding='utf-8') as f:
            for line in f:
                # Remove comments and whitespace
                line = line.split('#')[0].strip()
                if not line:
                    continue
                
                if '=' in line:
                    parts = line.split('=', 1)
                    key = parts[0].strip()
                    val = parts[1].strip()
                    # Only map if there is actual content after the '='
                    config_map[key] = val if val else None
                else:
                    config_map[line] = None
        CONFIG_CACHE[ext_clean] = config_map
        return config_map
    return None

def process_file(file_path, mode):
    ext = os.path.splitext(file_path)[1].lower()
    config = load_config_mapped(ext)
    
    if config is None:
        return # Skip files with no config

    audio = File(file_path)
    if audio is None or audio.tags is None:
        print(f"[!] Could not access tags for: {os.path.basename(file_path)}")
        return

    fname = os.path.basename(file_path)
    
    if mode == 'read':
        print(f"\n>>> READ: {fname}")
        for key in config.keys():
            val = audio.tags.get(key)
            # Handle ID3 vs Vorbis/MP4 display
            display = val.text[0] if hasattr(val, 'text') else str(val[0]) if isinstance(val, list) else str(val)
            print(f"{key:8} : {display if val else '[EMPTY]'}")

    elif mode == 'write':
        updated = False
        for key, new_val in config.items():
            if new_val: # Only update if a value was provided in config
                try:
                    if "ID3" in str(type(audio.tags)):
                        # ID3 Frame Mapping
                        frame_map = {
                            'TIT2': TIT2, 'TPE1': TPE1, 'TPE2': TPE2, 
                            'TALB': TALB, 'TDRC': TDRC, 'TRCK': TRCK, 
                            'TCON': TCON, 'COMM': COMM
                        }
                        if key in frame_map:
                            audio.tags.add(frame_map[key](encoding=3, text=[new_val]))
                            updated = True
                    else:
                        # OGG/FLAC/M4A Logic
                        audio.tags[key] = [new_val]
                        updated = True
                except Exception as e:
                    print(f"Error writing {key} to {fname}: {e}")

        if updated:
            audio.save()
            print(f">>> UPDATED: {fname}")

def main():
    parser = argparse.ArgumentParser(description="Direct Config-to-Tag Tool", add_help=False)
    m = parser.add_mutually_exclusive_group(required=True)
    m.add_argument("-r", "--read", action="store_true")
    m.add_argument("-w", "--write", action="store_true")
    
    t = parser.add_mutually_exclusive_group(required=True)
    t.add_argument("-f", "--file")
    t.add_argument("-d", "--dir")
    parser.add_argument("-h", "--help", action="help")

    args = parser.parse_args()
    target = args.file if args.file else args.dir
    mode = 'read' if args.read else 'write'

    if os.path.isfile(target):
        process_file(target, mode)
    else:
        for root, _, files in os.walk(target):
            for f in files:
                if f.lower().endswith('ogg'):
                    process_file(os.path.join(root, f), mode)

if __name__ == "__main__":
    main()