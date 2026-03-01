#!/bin/bash

INPUT_FILE="$1"
LOG_FILE="split_debug.log"

echo "--- Starting Split Session: $(date) ---" > "$LOG_FILE"

if [[ ! -f "$INPUT_FILE" ]]; then
    echo "Error: File '$INPUT_FILE' not found." | tee -a "$LOG_FILE"
    exit 1
fi

DIR_PATH=$(dirname "$INPUT_FILE")
FILE_NAME=$(basename "$INPUT_FILE")
BASE_NAME="${FILE_NAME%.*}"
OUTPUT_DIR="$DIR_PATH/$BASE_NAME"

# 1. Preview Chapters
echo "--- CHAPTER LIST ---"
ffprobe -v error -print_format csv -show_chapters "$INPUT_FILE" | cut -d ',' -f '5,7,8' | sed 's/,/  |  /g'
echo "--------------------"

read -p "Split into folder [$BASE_NAME]? (y/n): " confirm
[[ $confirm != "y" ]] && exit 0

mkdir -p "$OUTPUT_DIR"

# 2. Process Chapters
ffprobe -v error -print_format csv -show_chapters "$INPUT_FILE" | cut -d ',' -f '5,7,8' | tr ',' '|' > chapters.tmp

while IFS="|" read -r start end title; do
    SAFE_TITLE=$(echo "$title" | sed 's/[^a-zA-Z0-9\x80-\xff ]/_/g' | xargs)
    [[ -z "$SAFE_TITLE" ]] && SAFE_TITLE="track_$start"
    OUT_FILE="$OUTPUT_DIR/${SAFE_TITLE}.ogg"

    echo ">>> Processing: $SAFE_TITLE"
    
    # NEW COMMAND: -vn (No Video) and -c:a copy (Audio Copy only)
    echo "CMD: ffmpeg -nostdin -y -ss $start -to $end -i \"$INPUT_FILE\" -vn -c:a copy \"$OUT_FILE\"" >> "$LOG_FILE"
    ffmpeg -nostdin -y -ss "$start" -to "$end" -i "$INPUT_FILE" -vn -c:a copy "$OUT_FILE" >> "$LOG_FILE" 2>&1
    
    RESULT=$?
    if [[ $RESULT -eq 0 && -s "$OUT_FILE" ]]; then
        echo "    DONE: ${SAFE_TITLE}.ogg"
    else
        echo "    FAILED: Check $LOG_FILE for details." | tee -a "$LOG_FILE"
    fi
done < chapters.tmp

rm chapters.tmp
echo "--- FINISHED ---"