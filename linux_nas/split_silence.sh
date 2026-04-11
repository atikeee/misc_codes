#!/bin/bash

CONFIG_FILE="config.txt"

# 1. Load Configuration (With Auto-Clean for Windows CRLF)
if [[ ! -f "$CONFIG_FILE" ]]; then
    echo "Error: Configuration file '$CONFIG_FILE' not found."
    exit 1
fi

NOISE_NUM=$(grep "NOISE_DB" "$CONFIG_FILE" | cut -d'=' -f2 | tr -d '\r' | tr -d ' ')
DUR_REQ=$(grep "SILENCE_DURATION" "$CONFIG_FILE" | cut -d'=' -f2 | tr -d '\r' | tr -d ' ')
DIR_PATH=$(grep "FOLDER_PATH" "$CONFIG_FILE" | cut -d'=' -f2 | tr -d '\r' | tr -d ' ')
EXT=$(grep "EXTENSION" "$CONFIG_FILE" | cut -d'=' -f2 | tr -d '\r' | tr -d ' ')

NOISE="-${NOISE_NUM}dB"

# 2. Determine Mode
if [[ -n "$1" ]]; then
    FILES=("$1")
else
    FILES=("$DIR_PATH"/*."$EXT")
fi

# 3. Processing Loop
for INPUT_FILE in "${FILES[@]}"; do
    
    if [[ ! -e "$INPUT_FILE" ]]; then continue; fi

    BASE_PATH="${INPUT_FILE%.*}"
    CSV_FILE="${BASE_PATH}.csv"
    
    echo "Processing: $(basename "$INPUT_FILE")"

    # Get Total Duration
    TOTAL_DUR=$(ffprobe -v error -show_entries format=duration -of default=noprint_wrappers=1:nokey=1 "$INPUT_FILE" | awk '{print int($1)}')

    # Initialize timestamps array with 0
    TIMESTAMPS=(0)

    # Detect silence and extract timestamps
    while IFS= read -r LINE; do
        if [[ "$LINE" == *"silence_start:"* ]]; then
            RAW_TS=$(echo "$LINE" | sed 's/.*silence_start: //;s/ .*//')
            VAL=$(echo "$RAW_TS" | awk '{print int($1)}')
            
            # Avoid duplicates
            if [[ "$VAL" -gt "${TIMESTAMPS[-1]}" ]]; then
                TIMESTAMPS+=("$VAL")
            fi
        fi
    done < <(ffmpeg -hide_banner -vn -i "$INPUT_FILE" -map a -af silencedetect=noise=$NOISE:d=$DUR_REQ -f null - 2>&1)

    # Add the final duration point
    TIMESTAMPS+=("$TOTAL_DUR")

    # 4. Generate Output File
    # Format: Start(4), ID(2), Dur(3), MM:SS(5)
    printf "%4s, %2s, %3s, %5s\n" "STRT" "ID" "DUR" "MM:SS" > "$CSV_FILE"

    NUM_POINTS=${#TIMESTAMPS[@]}
    
    for (( i=0; i<$((NUM_POINTS-1)); i++ )); do
        START=${TIMESTAMPS[$i]}
        NEXT=${TIMESTAMPS[$((i+1))]}
        DURATION=$((NEXT - START))
        ID=$((i+1))

        # Calculate MM:SS (Minutes can exceed 60)
        MINS=$((START / 60))
        SECS=$((START % 60))
        MMSS=$(printf "%02d:%02d" "$MINS" "$SECS")

        # Formatted Output
        printf "%4d, %2d, %3d, %5s\n" "$START" "$ID" "$DURATION" "$MMSS" >> "$CSV_FILE"
    done

    echo "  >> Generated: $(basename "$CSV_FILE")"
done

echo "--------------------------------------------------------"
echo "Done."