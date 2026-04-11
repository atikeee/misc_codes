#!/bin/bash
# write_rating.sh - Set rating for a single image

write_rating() {
    local image_file="$1"
    local rating="$2"
    
    # Check if file exists
    if [ ! -f "$image_file" ]; then
        echo "Error: File '$image_file' not found"
        return 1
    fi
    
    # Validate rating (1-5 or 0 to remove)
    if [[ ! "$rating" =~ ^[0-5]$ ]]; then
        echo "Error: Rating must be 0-5 (0 removes rating)"
        return 1
    fi
    
    # Set rating using exiftool
    if [ "$rating" = "0" ]; then
        # Remove rating
        exiftool -Rating= "$image_file" -overwrite_original
        echo "Rating removed from: $(basename "$image_file")"
    else
        # Set rating
        exiftool -Rating="$rating" "$image_file" -overwrite_original
        echo "Rating set to $rating stars for: $(basename "$image_file")"
    fi
}

# Usage check
if [ $# -ne 2 ]; then
    echo "Usage: $0 <image_file> <rating>"
    echo "Rating: 1-5 stars, or 0 to remove rating"
    echo "Example: $0 /media/photo.jpg 5"
    exit 1
fi

# Write rating
write_rating "$1" "$2"