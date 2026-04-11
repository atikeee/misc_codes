#!/bin/bash
# simple_rating.sh - Read rating from a single image

read_rating() {
    local image_file="$1"
    
    # Check if file exists
    if [ ! -f "$image_file" ]; then
        echo "Error: File '$image_file' not found"
        return 1
    fi
    
    # Read rating using exiftool
    local rating=$(exiftool -Rating -s -s -s "$image_file" 2>/dev/null)
    
    # Print result
    if [ -n "$rating" ] && [ "$rating" != "-" ]; then
        echo "$(basename "$image_file"): $rating stars"
    else
        echo "$(basename "$image_file"): No rating"
    fi
}

# Usage check
if [ $# -eq 0 ]; then
    echo "Usage: $0 <image_file>"
    echo "Example: $0 /media/photo.jpg"
    exit 1
fi

# Read rating
read_rating "$1"