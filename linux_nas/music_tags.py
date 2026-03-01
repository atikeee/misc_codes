#!/usr/bin/env python3
import os
import sys
import argparse
import shutil
from mutagen import File

SEPARATOR = "|"
CSV_NAME = "metadata.csv"

# --- CONFIGURATION ---
DEST_LIBRARY_ROOT = r"\\192.168.0.140\Media\Audio\Hindi\chk"
# ---------------------

SUPPORTED_EXTS = {".mp3", ".flac", ".ogg", ".m4a", ".mp4", ".m4b", ".aac", ".wma", ".wav"}

def sanitize(value: str) -> str:
    if value is None: return ""
    for char in ["/", "\\", ":", "*", "?", "\"", "<", ">", "|"]:
        value = str(value).replace(char, "_")
    return value.strip()

def read_tags(path):
    try:
        audio = File(path, easy=True)
        if audio is None: return None
        def get_first(tag_name):
            if tag_name not in audio: return ""
            val = audio[tag_name]
            return val[0] if isinstance(val, list) and val else str(val)
        return {
            "artist": get_first("artist"),
            "album":  get_first("album"),
            "title":  get_first("title"),
        }
    except Exception:
        return None

def process_file_update(row, current_folder):
    filename = row["filepath"]
    original_abs_path = os.path.join(current_folder, filename)
    
    if not os.path.exists(original_abs_path):
        print(f"   [!] File not found: {filename}")
        return

    try:
        audio = File(original_abs_path, easy=True)
        if audio is not None:
            audio["artist"] = [row["artist"]]
            audio["album"]  = [row["album"]]
            audio["title"]  = [row["title_newname"]]
            audio.save()
    except Exception as e:
        print(f"   [!] Metadata Error for {filename}: {e}")

    try:
        ext = os.path.splitext(original_abs_path)[1]
        new_filename = sanitize(row["title_newname"]) + ext
        album_folder = sanitize(row["album"]) if row["album"] else "Unknown Album"
        
        target_dir = os.path.join(DEST_LIBRARY_ROOT, album_folder)
        target_path = os.path.join(target_dir, new_filename)

        os.makedirs(target_dir, exist_ok=True)
        shutil.move(original_abs_path, target_path)
        print(f"   [OK] {filename} -> {album_folder}/{new_filename}")
    except Exception as e:
        print(f"   [!] Move Error for {filename}: {e}")

def mode_read(root_dir):
    print(f"--- STARTING SCAN ---")
    print(f"Target Root: {root_dir}")
    
    folder_count = 0
    csv_count = 0

    for dirpath, _, filenames in os.walk(root_dir):
        folder_count += 1
        # Filter for audio files
        audio_files = [f for f in filenames if os.path.splitext(f)[1].lower() in SUPPORTED_EXTS]
        
        if not audio_files:
            continue
            
        csv_path = os.path.join(dirpath, CSV_NAME)
        try:
            with open(csv_path, "w", encoding="utf-8") as f:
                f.write(f"filepath{SEPARATOR}title_newname{SEPARATOR}album{SEPARATOR}artist\n")
                for fname in sorted(audio_files):
                    abs_path = os.path.join(dirpath, fname)
                    tags = read_tags(abs_path)
                    title = (tags["title"] if tags else "") or os.path.splitext(fname)[0]
                    album = (tags["album"] if tags else "")
                    artist = (tags["artist"] if tags else "")
                    line = SEPARATOR.join([fname, sanitize(title), sanitize(album), sanitize(artist)])
                    f.write(line + "\n")
            print(f"CREATED: {csv_path} ({len(audio_files)} songs)")
            csv_count += 1
        except Exception as e:
            print(f"ERROR: Could not write to {dirpath}: {e}")

    print(f"--- SCAN FINISHED ---")
    print(f"Folders Checked: {folder_count}")
    print(f"CSVs Generated: {csv_count}")

def mode_write(root_dir):
    print(f"--- STARTING UPDATE ---")
    for dirpath, _, filenames in os.walk(root_dir):
        if CSV_NAME in filenames:
            csv_path = os.path.join(dirpath, CSV_NAME)
            print(f"Processing: {csv_path}")
            try:
                with open(csv_path, "r", encoding="utf-8") as f:
                    lines = f.readlines()
                for line in lines[1:]:
                    if not line.strip(): continue
                    parts = [p.strip() for p in line.split(SEPARATOR)]
                    if len(parts) < 4: continue
                    row = {"filepath": parts[0], "title_newname": parts[1], "album": parts[2], "artist": parts[3]}
                    process_file_update(row, dirpath)
            except Exception as e:
                print(f"Error reading {csv_path}: {e}")
    print(f"--- UPDATE FINISHED ---")

def main():
    parser = argparse.ArgumentParser(description="Recursive Music Metadata Organizer")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("-r", "--read", action="store_true")
    group.add_argument("-w", "--write", action="store_true")
    parser.add_argument("directory", help="The root folder to scan")
    
    args = parser.parse_args()
    source_root = os.path.abspath(args.directory)

    if args.read:
        mode_read(source_root)
    elif args.write:
        if not os.path.exists(DEST_LIBRARY_ROOT):
            os.makedirs(DEST_LIBRARY_ROOT, exist_ok=True)
        mode_write(source_root)

if __name__ == "__main__":
    main()