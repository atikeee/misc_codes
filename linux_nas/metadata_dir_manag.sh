#!/bin/bash

# metadata_dir_manager.sh - Directory-based metadata manager
# Usage: ./metadata_dir_manager.sh [OPTIONS] DIRECTORY
# Options:
#   -r, --read     Read metadata from all files and generate CSV (default)
#   -w, --write    Write metadata from CSV to files
#   -v, --verbose  Verbose output for debugging
#   -h, --help     Show help

VERSION="1.0"
SCRIPT_NAME=$(basename "$0")

# Default values
ACTION="read"
INPUT_DIR=""
CSV_SEPARATOR="|"
VERBOSE=false

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

# Supported media extensions
MEDIA_EXTENSIONS=("mp4" "mkv" "avi" "mov" "wmv" "flv" "webm" "mp3" "flac" "wav" "aac" "ogg" "m4a" "m4v" "3gp" "f4v")

# Function to display help
show_help() {
    cat << EOF
$SCRIPT_NAME v$VERSION - Directory Metadata Manager

USAGE:
    $SCRIPT_NAME [OPTIONS] DIRECTORY

OPTIONS:
    -r, --read              Read metadata from all media files and generate CSV (default)
    -w, --write             Write metadata from CSV to files (with rename functionality)
    -v, --verbose           Verbose output for debugging
    -h, --help              Show this help

DESCRIPTION:
    This script processes all media files in a directory and creates a CSV file
    with pipe (|) separators. The CSV file will have the same name as the directory.
    
    READ MODE:
    - Scans directory for media files
    - Extracts metadata from each file
    - Creates CSV with columns: filename|title|genre|album|album_artist|year|artist|comment|track
    - Replaces any pipe characters in metadata with ¦ symbol
    
    WRITE MODE:
    - Reads CSV file from directory
    - Renames files based on title column (keeping original extension)
    - Updates metadata for each file
    - Creates backup of original files

EXAMPLES:
    $SCRIPT_NAME /path/to/music/directory
    $SCRIPT_NAME -r /path/to/video/collection
    $SCRIPT_NAME -w /path/to/music/directory
    $SCRIPT_NAME -v /path/to/debug/directory

CSV FORMAT:
    filename|title|genre|album|album_artist|year|artist|comment|track

EOF
}

# Function for verbose output
verbose_echo() {
    if [[ "$VERBOSE" == true ]]; then
        echo -e "${CYAN}[DEBUG]${NC} $1"
    fi
}

# Function to check dependencies
check_dependencies() {
    local missing_deps=()
    
    verbose_echo "Checking dependencies..."
    
    if ! command -v ffprobe >/dev/null 2>&1; then
        missing_deps+=("ffprobe (part of ffmpeg)")
    else
        verbose_echo "ffprobe found: $(which ffprobe)"
    fi
    
    if ! command -v ffmpeg >/dev/null 2>&1; then
        missing_deps+=("ffmpeg")
    else
        verbose_echo "ffmpeg found: $(which ffmpeg)"
    fi
    
    if [[ ${#missing_deps[@]} -gt 0 ]]; then
        echo -e "${RED}Error: Missing required dependencies:${NC}"
        printf '%s\n' "${missing_deps[@]}"
        echo ""
        echo "Install with:"
        echo "  Ubuntu/Debian: sudo apt install ffmpeg"
        echo "  CentOS/RHEL:   sudo yum install ffmpeg"
        echo "  macOS:         brew install ffmpeg"
        exit 1
    fi
    
    verbose_echo "All dependencies found"
}

# Function to validate directory
validate_directory() {
    local dir="$1"
    
    verbose_echo "Validating directory: $dir"
    
    if [[ ! -d "$dir" ]]; then
        echo -e "${RED}Error: Directory '$dir' does not exist${NC}" >&2
        exit 1
    fi
    
    if [[ ! -r "$dir" ]]; then
        echo -e "${RED}Error: Directory '$dir' is not readable${NC}" >&2
        exit 1
    fi
    
    verbose_echo "Directory validation passed"
    
    # List directory contents for debugging
    if [[ "$VERBOSE" == true ]]; then
        echo -e "${CYAN}[DEBUG]${NC} Directory contents:"
        ls -la "$dir" | head -20
        echo -e "${CYAN}[DEBUG]${NC} Total files in directory: $(find "$dir" -maxdepth 1 -type f | wc -l)"
    fi
}

# Function to check if file is a supported media file
is_media_file() {
    local file="$1"
    local extension="${file##*.}"
    extension=$(echo "$extension" | tr '[:upper:]' '[:lower:]')
    
    verbose_echo "Checking file: $(basename "$file"), extension: $extension"
    
    for ext in "${MEDIA_EXTENSIONS[@]}"; do
        if [[ "$extension" == "$ext" ]]; then
            verbose_echo "File is supported media type: $extension"
            return 0
        fi
    done
    
    verbose_echo "File is not a supported media type: $extension"
    return 1
}

# Function to sanitize metadata (replace pipes with alternative)
sanitize_metadata() {
    local value="$1"
    # Replace pipe characters with broken bar character
    echo "$value" | sed 's/|/¦/g'
}

# Function to get metadata from file
get_file_metadata() {
    local file="$1"
    local -A metadata
    
    verbose_echo "Extracting metadata from: $(basename "$file")"
    
    # Initialize all fields as empty
    metadata["title"]=""
    metadata["genre"]=""
    metadata["album"]=""
    metadata["album_artist"]=""
    metadata["year"]=""
    metadata["artist"]=""
    metadata["comment"]=""
    metadata["track"]=""
    
    # Test if ffprobe can read the file
    if ! ffprobe -v quiet -print_format flat -show_format "$file" >/dev/null 2>&1; then
        verbose_echo "Warning: ffprobe cannot read file: $(basename "$file")"
        echo "${metadata["title"]}${CSV_SEPARATOR}${metadata["genre"]}${CSV_SEPARATOR}${metadata["album"]}${CSV_SEPARATOR}${metadata["album_artist"]}${CSV_SEPARATOR}${metadata["year"]}${CSV_SEPARATOR}${metadata["artist"]}${CSV_SEPARATOR}${metadata["comment"]}${CSV_SEPARATOR}${metadata["track"]}"
        return
    fi
    
    # Get format metadata
    while IFS='=' read -r key value; do
        # Remove quotes from value
        value=$(echo "$value" | sed 's/^"//;s/"$//')
        value=$(sanitize_metadata "$value")
        
        verbose_echo "Found metadata: $key = $value"
        
        case "$key" in
            "format.tags.title"|"format.tags.TITLE")
                metadata["title"]="$value"
                ;;
            "format.tags.genre"|"format.tags.GENRE")
                metadata["genre"]="$value"
                ;;
            "format.tags.album"|"format.tags.ALBUM")
                metadata["album"]="$value"
                ;;
            "format.tags.album_artist"|"format.tags.ALBUM_ARTIST"|"format.tags.albumartist"|"format.tags.ALBUMARTIST")
                metadata["album_artist"]="$value"
                ;;
            "format.tags.date"|"format.tags.DATE"|"format.tags.year"|"format.tags.YEAR")
                metadata["year"]="$value"
                ;;
            "format.tags.artist"|"format.tags.ARTIST")
                metadata["artist"]="$value"
                ;;
            "format.tags.comment"|"format.tags.COMMENT")
                metadata["comment"]="$value"
                ;;
            "format.tags.track"|"format.tags.TRACK")
                metadata["track"]="$value"
                ;;
        esac
    done < <(ffprobe -v quiet -print_format flat -show_format "$file" 2>/dev/null)
    
    # Output in CSV format
    echo "${metadata["title"]}${CSV_SEPARATOR}${metadata["genre"]}${CSV_SEPARATOR}${metadata["album"]}${CSV_SEPARATOR}${metadata["album_artist"]}${CSV_SEPARATOR}${metadata["year"]}${CSV_SEPARATOR}${metadata["artist"]}${CSV_SEPARATOR}${metadata["comment"]}${CSV_SEPARATOR}${metadata["track"]}"
}

# Function to read metadata from directory
read_metadata_from_directory() {
    local dir="$1"
    local dir_name=$(basename "$dir")
    local csv_file="$dir/${dir_name}.csv"
    
    echo -e "${BLUE}Reading metadata from directory: ${CYAN}$dir${NC}"
    echo -e "${BLUE}Output CSV file: ${CYAN}$csv_file${NC}"
    echo "===========================================" 
    
    verbose_echo "Directory name: $dir_name"
    verbose_echo "CSV file path: $csv_file"
    
    # Create CSV header
    echo "filename${CSV_SEPARATOR}title${CSV_SEPARATOR}genre${CSV_SEPARATOR}album${CSV_SEPARATOR}album_artist${CSV_SEPARATOR}year${CSV_SEPARATOR}artist${CSV_SEPARATOR}comment${CSV_SEPARATOR}track" > "$csv_file"
    verbose_echo "CSV header written"
    
    local file_count=0
    local media_file_count=0
    
    # Process all files in directory
    verbose_echo "Starting file processing..."
    
    while IFS= read -r -d '' file; do
        ((file_count++))
        verbose_echo "Processing file #$file_count: $(basename "$file")"
        
        if is_media_file "$file"; then
            ((media_file_count++))
            local filename=$(basename "$file")
            local metadata_line=$(get_file_metadata "$file")
            
            echo "${filename}${CSV_SEPARATOR}${metadata_line}" >> "$csv_file"
            echo -e "${GREEN}Processed: ${NC}$filename"
            verbose_echo "Added to CSV: $filename"
        fi
    done < <(find "$dir" -maxdepth 1 -type f -print0)
    
    verbose_echo "Total files found: $file_count"
    verbose_echo "Media files processed: $media_file_count"
    
    echo ""
    echo -e "${GREEN}Successfully processed $media_file_count media files out of $file_count total files${NC}"
    echo -e "${GREEN}CSV file created: $csv_file${NC}"
    
    # Show CSV file size and first few lines for verification
    if [[ -f "$csv_file" ]]; then
        local csv_lines=$(wc -l < "$csv_file")
        echo -e "${BLUE}CSV file contains $csv_lines lines${NC}"
        
        if [[ "$VERBOSE" == true ]]; then
            echo -e "${CYAN}[DEBUG]${NC} First 5 lines of CSV:"
            head -5 "$csv_file"
        fi
    fi
}

# Function to create safe filename from title
create_safe_filename() {
    local title="$1"
    local extension="$2"
    
    # Remove or replace problematic characters
    local safe_name=$(echo "$title" | sed 's/[<>:"/\\|?*]//g' | sed 's/  */ /g' | sed 's/^ *//;s/ *$//')
    
    # If title is empty, use "Untitled"
    if [[ -z "$safe_name" ]]; then
        safe_name="Untitled"
    fi
    
    echo "${safe_name}.${extension}"
}

# Function to write metadata from CSV
write_metadata_from_csv() {
    local dir="$1"
    local dir_name=$(basename "$dir")
    local csv_file="$dir/${dir_name}.csv"
    
    if [[ ! -f "$csv_file" ]]; then
        echo -e "${RED}Error: CSV file '$csv_file' not found${NC}" >&2
        echo "Run with -r option first to generate the CSV file"
        exit 1
    fi
    
    echo -e "${BLUE}Writing metadata from CSV: ${CYAN}$csv_file${NC}"
    echo "===========================================" 
    
    # Create backup directory
    local backup_dir="$dir/backup_$(date +%Y%m%d_%H%M%S)"
    mkdir -p "$backup_dir"
    echo -e "${YELLOW}Backup directory created: $backup_dir${NC}"
    
    local line_number=0
    local processed_files=0
    
    while IFS="$CSV_SEPARATOR" read -r filename title genre album album_artist year artist comment track; do
        ((line_number++))
        
        # Skip header line
        if [[ $line_number -eq 1 ]]; then
            continue
        fi
        
        local original_file="$dir/$filename"
        
        if [[ ! -f "$original_file" ]]; then
            echo -e "${YELLOW}Warning: File not found: $filename${NC}"
            continue
        fi
        
        # Get file extension from original filename
        local extension="${filename##*.}"
        
        # Create new filename from title
        local new_filename
        if [[ -n "$title" ]]; then
            new_filename=$(create_safe_filename "$title" "$extension")
        else
            new_filename="$filename"
        fi
        
        local new_file="$dir/$new_filename"
        
        # Create backup
        cp "$original_file" "$backup_dir/"
        
        # Build ffmpeg command for metadata writing
        local ffmpeg_cmd="ffmpeg -i \"$original_file\" -c copy"
        
        # Add metadata parameters
        [[ -n "$title" ]] && ffmpeg_cmd+=" -metadata title=\"$title\""
        [[ -n "$genre" ]] && ffmpeg_cmd+=" -metadata genre=\"$genre\""
        [[ -n "$album" ]] && ffmpeg_cmd+=" -metadata album=\"$album\""
        [[ -n "$album_artist" ]] && ffmpeg_cmd+=" -metadata album_artist=\"$album_artist\""
        [[ -n "$year" ]] && ffmpeg_cmd+=" -metadata date=\"$year\""
        [[ -n "$artist" ]] && ffmpeg_cmd+=" -metadata artist=\"$artist\""
        [[ -n "$comment" ]] && ffmpeg_cmd+=" -metadata comment=\"$comment\""
        [[ -n "$track" ]] && ffmpeg_cmd+=" -metadata track=\"$track\""
        
        # Temporary file for processing
        local temp_file="$dir/temp_$$.${extension}"
        ffmpeg_cmd+=" \"$temp_file\""
        
        echo -e "${CYAN}Processing: $filename -> $new_filename${NC}"
        
        # Execute ffmpeg command
        if eval "$ffmpeg_cmd" >/dev/null 2>&1; then
            # Move temp file to final location
            mv "$temp_file" "$new_file"
            
            # Remove original file if renamed
            if [[ "$original_file" != "$new_file" ]]; then
                rm "$original_file"
            fi
            
            echo -e "${GREEN}✓ Successfully processed: $new_filename${NC}"
            ((processed_files++))
        else
            echo -e "${RED}✗ Error processing: $filename${NC}"
            # Clean up temp file if it exists
            [[ -f "$temp_file" ]] && rm "$temp_file"
        fi
        
    done < "$csv_file"
    
    echo ""
    echo -e "${GREEN}Successfully processed $processed_files files${NC}"
    echo -e "${GREEN}Backup created in: $backup_dir${NC}"
}

# Parse command line arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        -r|--read)
            ACTION="read"
            shift
            ;;
        -w|--write)
            ACTION="write"
            shift
            ;;
        -v|--verbose)
            VERBOSE=true
            shift
            ;;
        -h|--help)
            show_help
            exit 0
            ;;
        -*)
            echo -e "${RED}Unknown option: $1${NC}" >&2
            show_help
            exit 1
            ;;
        *)
            if [[ -z "$INPUT_DIR" ]]; then
                INPUT_DIR="$1"
            else
                echo -e "${RED}Multiple directories not supported${NC}" >&2
                exit 1
            fi
            shift
            ;;
    esac
done

# Main execution
main() {
    echo -e "${BLUE}$SCRIPT_NAME v$VERSION${NC}"
    echo -e "${BLUE}Action: $ACTION${NC}"
    echo -e "${BLUE}Directory: $INPUT_DIR${NC}"
    echo ""
    
    # Check if input directory is provided
    if [[ -z "$INPUT_DIR" ]]; then
        echo -e "${RED}Error: No directory specified${NC}" >&2
        show_help
        exit 1
    fi
    
    # Check dependencies
    check_dependencies
    
    # Validate input directory
    validate_directory "$INPUT_DIR"
    
    # Execute action
    case "$ACTION" in
        "read")
            read_metadata_from_directory "$INPUT_DIR"
            ;;
        "write")
            write_metadata_from_csv "$INPUT_DIR"
            ;;
        *)
            echo -e "${RED}Unknown action: $ACTION${NC}" >&2
            exit 1
            ;;
    esac
}

# Run main function
main