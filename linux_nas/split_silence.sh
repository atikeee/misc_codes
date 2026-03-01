#!/bin/bash

INPUT_FILE="$1"

# --- CONFIGURABLE PARAMETERS ---
# noise: how quiet must it be? (e.g., -30dB). Closer to 0 is "louder" silence.
# duration: how many seconds must the silence last?
DEFAULT_NOISE="-30dB"
DEFAULT_DURATION="2.0"

# Allow user to override via environment or prompt
read -p "Enter noise threshold (default $DEFAULT_NOISE): " NOISE
NOISE=${NOISE:-$DEFAULT_NOISE}
read -p "Enter min silence duration in seconds (default $DEFAULT_DURATION): " DUR
DUR=${DUR:-$DEFAULT_DURATION}

if [[ ! -f "$INPUT_FILE" ]]; then
    echo "Error: File '$INPUT_FILE' not found."
    exit 1
fi

DIR_PATH=$(dirname "$INPUT_FILE")
BASE_NAME=$(basename "$INPUT_FILE" | sed 's/\.[^.]*$//')
OUTPUT_DIR="$DIR_PATH/$BASE_NAME"

echo "--- PHASE 1: SCANNING FOR SILENCE ---"
echo "Searching with Noise: $NOISE and Duration: $DUR..."

# We use ffmpeg to find the gaps and store them in a temp file
# We extract 'silence_start' and 'silence_end'
TEMP_LOG="silence_scan.tmp"
ffmpeg -i "$INPUT_FILE" -af silencedetect=noise=$NOISE:d=$DUR -f null - 2>&1 | grep "silence_" > "$TEMP_LOG"


# Build the timestamp list
# Logic: The end of one silence is the START of a track. 
# The start of the next silence is the END of that track.
echo -e "Track\tStart\t\tEnd\t\tDuration"
echo -e "----------------------------------------------------"

START="0"
COUNT=1
POINTS_FOUND=0

# Create a processing list for Phase 2
echo -n "" > "tracks.list"

while read -l; do
    if [[ "$l" == *"silence_start"* ]]; then
        END=$(echo "$l" | awk '{print $NF}')
        DIFF=$(echo "$END - $START" | bc)
        # Only keep tracks longer than 0.5s to avoid glitches
        if (( $(echo "$DIFF > 0.5" | bc -l) )); then
            echo -e "$COUNT\t$START\t\t$END\t\t$DIFF"
            echo "$START|$END|$COUNT" >> "tracks.list"
            ((COUNT++))
            POINTS_FOUND=1
        fi
    elif [[ "$l" == *"silence_end"* ]]; then
        START=$(echo "$l" | awk '{print $NF}')
    fi
done < "$TEMP_LOG"

# Handle the final track (from last silence end to end of file)
TOTAL_DUR=$(ffprobe -v error -show_entries format=duration -of default=noprint_wrappers=1:nokey=1 "$INPUT_FILE")
DIFF=$(echo "$TOTAL_DUR - $START" | bc)
if (( $(echo "$DIFF > 1.0" | bc -l) )); then
    echo -e "$COUNT\t$START\t\t$TOTAL_DUR\t\t$DIFF"
    echo "$START|$TOTAL_DUR|$COUNT" >> "tracks.list"
fi

if [[ $POINTS_FOUND -eq 0 ]]; then
    echo "No silence points found. Try a louder noise threshold (e.g., -20dB)."
    rm "$TEMP_LOG" "tracks.list"
    exit 0
fi

echo "----------------------------------------------------"
read -p "Found $(cat tracks.list | wc -l) tracks. Split now? (y/n): " confirm
[[ $confirm != "y" ]] && { rm "$TEMP_LOG" "tracks.list"; exit 0; }

mkdir -p "$OUTPUT_DIR"

# --- PHASE 2: SPLITTING ---
while IFS="|" read -r s e c; do
    OUT_FILE="$OUTPUT_DIR/Track_$(printf "%03d" $c).ogg"
    echo ">>> Writing $OUT_FILE..."
    ffmpeg -nostdin -y -ss "$s" -to "$e" -i "$INPUT_FILE" -vn -c:a copy "$OUT_FILE" > /dev/null 2>&1
done < "tracks.list"

rm "$TEMP_LOG" "tracks.list"
echo "--- FINISHED: Files in $OUTPUT_DIR ---"
