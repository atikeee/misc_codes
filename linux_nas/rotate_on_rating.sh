#!/bin/bash
# rotate_on_rating.sh - Simple in-place rotation based on rating

if [ $# -ne 1 ]; then
    echo "Usage: $0 <directory>"
    echo "Example: $0 /photos1"
    exit 1
fi

directory="$1"

if [ ! -d "$directory" ]; then
    echo "Error: Directory '$directory' not found"
    exit 1
fi

echo "Processing JPG files in: $directory"
echo "Rating 1 = Rotate Left, Rating 2 = Rotate Right"
echo "=============================================="

total=0
rotated=0

find "$directory" -type f -iname "*.jpg" | while read -r image_file; do
    
    rating=$(exiftool -Rating -s -s -s "$image_file" 2>/dev/null)
    
    if [ "$rating" = "1" ] || [ "$rating" = "2" ]; then
        
        filename=$(basename "$image_file")
        echo "Processing: $filename (Rating: $rating)"
        
        if [ "$rating" = "1" ]; then
            angle="-90"
            direction="left"
        else
            angle="90"
            direction="right"
        fi
        
        temp_file=$(mktemp --suffix=.jpg)
        
        if convert "$image_file" -rotate "$angle" -quality 95 "$temp_file"; then
            if mv "$temp_file" "$image_file"; then
                exiftool -Rating= "$image_file" -overwrite_original >/dev/null 2>&1
                echo "✓ Rotated $direction and reset rating: $filename"
                rotated=$((rotated + 1))
            else
                echo "✗ Failed to save: $filename"
                rm -f "$temp_file"
            fi
        else
            echo "✗ Failed to rotate: $filename"
            rm -f "$temp_file"
        fi
        
        total=$((total + 1))
    fi
    
done

echo "=============================================="
echo "Processed: $total images"
echo "Rotated: $rotated images"
echo "Done!"