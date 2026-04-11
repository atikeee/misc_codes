#!/bin/bash
# rotate_inplace.sh - Rotate image and overwrite original

rotate_inplace() {
    local image_file="$1"
    local direction="$2"
    local backup="${3:-true}"
    
    if [ ! -f "$image_file" ]; then
        echo "Error: File '$image_file' not found"
        return 1
    fi
    
    if [[ ! "$direction" =~ ^[12]$ ]]; then
        echo "Error: Direction must be 1 (left) or 2 (right)"
        return 1
    fi
    
    # Create backup if requested
    if [ "$backup" = "true" ]; then
        local backup_file="${image_file}.backup"
        cp "$image_file" "$backup_file"
        echo "Backup created: $(basename "$backup_file")"
    fi
    
    # Set rotation angle
    local angle
    local direction_text
    if [ "$direction" = "1" ]; then
        angle="-90"
        direction_text="left (counter-clockwise)"
    else
        angle="90"
        direction_text="right (clockwise)"
    fi
    
    echo "Rotating $(basename "$image_file") $direction_text..."
    
    # Create temporary file
    local temp_file=$(mktemp --suffix=.jpg)
    
    # Rotate image
    if convert "$image_file" -rotate "$angle" "$temp_file"; then
        # Replace original with rotated version
        mv "$temp_file" "$image_file"
        echo "✓ Image rotated successfully and saved"
        return 0
    else
        echo "✗ Failed to rotate image"
        rm -f "$temp_file"
        return 1
    fi
}

# Usage
if [ $# -lt 2 ]; then
    echo "Usage: $0 <image_file> <direction> [backup]"
    echo ""
    echo "Arguments:"
    echo "  image_file: Path to image file"
    echo "  direction: 1 (rotate left) or 2 (rotate right)"
    echo "  backup: true/false (default: true - creates .backup file)"
    echo ""
    echo "Examples:"
    echo "  $0 /media/photo.jpg 1"
    echo "  $0 /media/photo.jpg 2 false"
    exit 1
fi

backup="${3:-true}"
rotate_inplace "$1" "$2" "$backup"