#!/bin/bash

FILE="/config/scripts/yt-dld-links.txt"
SCRIPT="/config/scripts/yt_dld.sh"

# 1. Check if inotifywait exists
if ! command -v inotifywait &> /dev/null; then
    echo "ERROR: inotifywait not found. Install with: apt install inotify-tools"
    exit 1
fi

# 2. Check if the file exists (inotifywait needs a real file to watch)
if [ ! -f "$FILE" ]; then
    echo "ERROR: Target file $FILE does not exist. Creating it..."
    touch "$FILE"
fi

echo "Watching $FILE for changes..."

# 3. The Loop
while inotifywait -e close_write "$FILE"; do
    echo "Change detected! Running script..."
    /bin/bash "$SCRIPT"
done
