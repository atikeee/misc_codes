#!/bin/bash

CONFIG_FILE="config.txt"

# 1. Load Configuration
if [[ ! -f "$CONFIG_FILE" ]]; then
    echo "Error: Configuration file '$CONFIG_FILE' not found."
    exit 1
fi

DIR_PATH=$(grep "FOLDER_PATH" "$CONFIG_FILE" | cut -d'=' -f2 | tr -d '\r' | tr -d ' ')
EXT=$(grep "EXTENSION" "$CONFIG_FILE" | cut -d'=' -f2 | tr -d '\r' | tr -d ' ')

# Improved Time Detection (Supports S, MM:SS, and HH:MM:SS)
to_seconds() {
    local input=$1
    echo "$input" | awk -F: '{
        if (NF == 1) print $1;
        else if (NF == 2) print ($1 * 60) + $2;
        else if (NF == 3) print ($1 * 3600) + ($2 * 60) + $3;
    }'
}

if [[ -n "$1" ]]; then
    FILES=("$1")
else
    FILES=("$DIR_PATH"/*."$EXT")
fi

for AUDIO_FILE in "${FILES[@]}"; do
    [[ -e "$AUDIO_FILE" ]] || continue
    
    BASE_DIR="${AUDIO_FILE%.*}"
    CSV_FILE="${BASE_DIR}.csv"
    
    if [[ ! -f "$CSV_FILE" ]]; then
        echo "Skipping: No CSV found for $(basename "$AUDIO_FILE")"
        continue
    fi

    # Create folder
    mkdir -p "$BASE_DIR"

    echo "--------------------------------------------------------"
    echo "Splitting: $(basename "$AUDIO_FILE")"
    
    # Load lines into array - keep spaces but remove Windows carriage returns
    mapfile -t LINES < <(tail -n +2 "$CSV_FILE" | tr -d '\r')

    NUM_LINES=${#LINES[@]}
    TOTAL_DUR=$(ffprobe -v error -show_entries format=duration -of default=noprint_wrappers=1:nokey=1 "$AUDIO_FILE" | awk '{print int($1)}')

    for (( i=0; i<$NUM_LINES; i++ )); do
        # Use a local IFS to prevent word splitting issues during read
        IFS=',' read -r START_RAW ID_RAW REST <<< "${LINES[$i]}"
        
        # Trim whitespace specifically
        START_VAL=$(echo "$START_RAW" | xargs)
        ID_VAL=$(echo "$ID_RAW" | xargs)
        START=$(to_seconds "$START_VAL")
        
        # Determine End Time Logic
        if [[ $i -lt $((NUM_LINES - 1)) ]]; then
            IFS=',' read -r NEXT_START_RAW NEXT_ID_RAW NEXT_REST <<< "${LINES[$((i+1))]}"
            NEXT_START=$(to_seconds "$(echo "$NEXT_START_RAW" | xargs)")
            END=$((NEXT_START - 1))
        else
            END=$TOTAL_DUR
        fi

        CLIP_DURATION=$((END - START))

        if [[ $CLIP_DURATION -lt 30 ]]; then
            echo "  >> Skipping $ID_VAL: Too short (${CLIP_DURATION}s)"
            continue
        fi

        # Generate safe filename and PATH
        CLEAN_ID_FILE="${ID_VAL// /_}"
        # We quote the entire path to prevent space-induced duplication
        OUTPUT_NAME="$BASE_DIR/${CLEAN_ID_FILE}.${EXT}"
        
        echo "  >> Extracting: $CLEAN_ID_FILE (${CLIP_DURATION}s)"
        
        # Fixed FFmpeg command with proper quoting audio only 
        ffmpeg -hide_banner -loglevel error -y -ss "$START" -to "$END" -i "$AUDIO_FILE" -vn -map_metadata 0 -map 0:a -c copy "$OUTPUT_NAME"
        # should include vdo
        #ffmpeg -hide_banner -loglevel error -y -ss "$START" -to "$END" -i "$AUDIO_FILE" -map 0 -c copy -avoid_negative_ts make_zero "$OUTPUT_NAME"
    done

    echo "  >> Finalizing: Moving original file and CSV to $BASE_DIR/"
    mv "$AUDIO_FILE" "$BASE_DIR/"
    mv "$CSV_FILE" "$BASE_DIR/"
done

echo "--------------------------------------------------------"
echo "Splitting Complete."