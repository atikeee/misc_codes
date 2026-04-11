#!/bin/bash
# yt_download.sh — Download YouTube videos from a text file
# Usage: ./yt_download.sh <input_file> [options]
#
# Text file format:
#   - One URL per line
#   - Lines starting with # are ignored (comments)
#   - Empty lines are ignored
#   - Supports optional per-line sections:  URL *00:01:00-00:03:00

# --- Colors -------------------------------------------------------------------
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m' # No Color

# --- Defaults -----------------------------------------------------------------
FORMAT="mp4"          # mp4 | mp3
DEFAULT_LINKS_FILE="yt-dld-links.txt"
QUALITY="0"           # 0=best
OUTPUT_DIR="/media/youtube"
SECTION=""            # e.g. *00:01:00-00:03:00
SLOW_TEMPO=""         # e.g. 0.75
DRY_RUN=false
COOKIE_FILE="yt_dld_cookies.txt"
# --- Usage --------------------------------------------------------------------
usage() {
  echo -e "${BOLD}Usage:${NC} $0 <input_file> [options]"
  echo ""
  echo -e "${BOLD}Options:${NC}"
  echo "  -f, --format   mp4 | mp3          (default: mp4)"
  echo "  -o, --output   output directory   (default: ./downloads)"
  echo "  -s, --section  time range         e.g. *00:01:00-00:03:00"
  echo "  -t, --tempo    slow down speed    e.g. 0.75 (mp3 only)"
  echo "  -d, --dry-run  preview only, no download"
  echo "  -h, --help     show this help"
  echo ""
  echo -e "${BOLD}Input file example:${NC}"
  echo "  # My playlist"
  echo "  https://www.youtube.com/watch?v=abc123"
  echo "  https://youtu.be/xyz456  *00:01:00-00:03:00"
  echo ""
  exit 0
}

# --- Argument parsing ---------------------------------------------------------
if [[ $# -gt 0 && "$1" != -* ]]; then 
  INPUT_FILE="$1"
shift
else
  INPUT_FILE="$DEFAULT_LINKS_FILE"
fi

while [[ $# -gt 0 ]]; do
  case "$1" in
    -f|--format)  FORMAT="$2";     shift 2 ;;
    -o|--output)  OUTPUT_DIR="$2"; shift 2 ;;
    -s|--section) SECTION="$2";    shift 2 ;;
    -t|--tempo)   SLOW_TEMPO="$2"; shift 2 ;;
    -d|--dry-run) DRY_RUN=true;    shift   ;;
    -h|--help)    usage ;;
    *) echo -e "${RED}Unknown option: $1${NC}"; usage ;;
  esac
done

# --- Validation ---------------------------------------------------------------
if [[ ! -f "$INPUT_FILE" ]]; then
  echo -e "${RED}Error: File not found — $INPUT_FILE${NC}"
  exit 1
fi

if ! command -v yt-dlp &>/dev/null; then
  echo -e "${RED}Error: yt-dlp not found. Install it first.${NC}"
  echo "  curl -L https://github.com/yt-dlp/yt-dlp/releases/latest/download/yt-dlp -o /usr/local/bin/yt-dlp"
  echo "  chmod a+rx /usr/local/bin/yt-dlp"
  exit 1
fi

if ! command -v ffmpeg &>/dev/null; then
  echo -e "${YELLOW}Warning: ffmpeg not found — audio extraction and trimming won't work.${NC}"
fi

# --- Setup --------------------------------------------------------------------
mkdir -p "$OUTPUT_DIR"

echo -e "${BOLD}${CYAN}=======================================${NC}"
echo -e "${BOLD}${CYAN}  YouTube Batch Downloader              ${NC}"
echo -e "${BOLD}${CYAN}=======================================${NC}"
echo -e "  File:    ${BOLD}$INPUT_FILE${NC}"
echo -e "  Format:  ${BOLD}$FORMAT${NC}"
echo -e "  Output:  ${BOLD}$OUTPUT_DIR${NC}"
[[ -n "$SECTION" ]]    && echo -e "  Section: ${BOLD}$SECTION${NC}"
[[ -n "$SLOW_TEMPO" ]] && echo -e "  Tempo:   ${BOLD}$SLOW_TEMPO${NC}"
[[ "$DRY_RUN" == true ]] && echo -e "  ${YELLOW}[DRY RUN — no downloads]${NC}"
echo ""

# --- Parse links --------------------------------------------------------------
TOTAL=0
SUCCESS=0
FAILED=0
SKIPPED=0
FAILED_URLS=()

while IFS= read -r raw_line || [[ -n "$raw_line" ]]; do

  # Strip leading/trailing whitespace
  line="$(echo "$raw_line" | sed 's/^[[:space:]]*//;s/[[:space:]]*$//')"

  # Skip empty lines and comments
  [[ -z "$line" ]]        && continue
  [[ "$line" == \#* ]]    && continue

  # Split line into URL and optional inline section (URL *hh:mm:ss-hh:mm:ss)
  url="$(echo "$line" | awk '{print $1}')"
  inline_section="$(echo "$line" | awk '{print $2}')"

  # Validate it looks like a YouTube URL
  if [[ ! "$url" =~ (youtube\.com|youtu\.be|fb\.com|facebook\.com|fb.\watch|share/r) ]]; then
    echo -e "${YELLOW}  Skipping non-YouTube URL: $url${NC}"
    ((SKIPPED++))
    continue
  fi

  ((TOTAL++))
  echo -e "${CYAN}[${TOTAL}]${NC} ${BOLD}$url${NC}"

  # Use inline section if present, else global section
  active_section="${inline_section:-$SECTION}"

  # --- Build yt-dlp command --------------------------------------------------
  CMD="yt-dlp"
  CMD+=" -o \"${OUTPUT_DIR}/%(title).80s [%(id)s].%(ext)s\""
  CMD+=" --user-agent \"facebookexternalhit/1.1\""
   
# This single flag handles both YT and FB if the data is in the JSON
if [[ -f "$COOKIE_FILE" ]]; then
  CMD+=" --cookies \"$COOKIE_FILE\""
fi

  if [[ "$FORMAT" == "mp3" ]]; then
    CMD+=" -x --audio-format mp3 --audio-quality ${QUALITY}"
    # Apply tempo (slow down) for mp3
    if [[ -n "$SLOW_TEMPO" ]]; then
      CMD+=" --postprocessor-args \"ffmpeg:-filter:a atempo=${SLOW_TEMPO}\""
    fi
  else
    #CMD+=" -f \"bv*+ba/b\" --merge-output-format mp4"
   CMD+=" -f \"bestvideo[height<=1080][ext=mp4]+bestaudio[ext=m4a]/bestvideo[height<=1080]+bestaudio/best[ext=mp4]/best\""
   CMD+=" --merge-output-format mp4"
  fi

  # Apply section/time range if set
  if [[ -n "$active_section" ]]; then
    CMD+=" --download-sections \"${active_section}\""
  fi

  CMD+=" \"$url\""

  echo -e "  ${YELLOW}-> ${CMD}${NC}"

  # --- Execute --------------------------------------------------------------
  if [[ "$DRY_RUN" == false ]]; then
    eval "$CMD"
    if [[ $? -eq 0 ]]; then
      echo -e "  ${GREEN}[OK] Done${NC}"
      ((SUCCESS++))
    else
      echo -e "  ${RED}[FAIL] Failed${NC}"
      ((FAILED++))
      FAILED_URLS+=("$url")
    fi
  else
    ((SUCCESS++))
  fi

  echo ""

done < "$INPUT_FILE"

# --- Summary ------------------------------------------------------------------
echo -e "${BOLD}${CYAN}=======================================${NC}"
echo -e "${BOLD}  Summary${NC}"
echo -e "${CYAN}=======================================${NC}"
echo -e "  Total:    ${BOLD}$TOTAL${NC}"
echo -e "  ${GREEN}Success:  $SUCCESS${NC}"
[[ $FAILED  -gt 0 ]] && echo -e "  ${RED}Failed:   $FAILED${NC}"
[[ $SKIPPED -gt 0 ]] && echo -e "  ${YELLOW}Skipped:  $SKIPPED${NC}"

if [[ ${#FAILED_URLS[@]} -gt 0 ]]; then
  echo ""
  echo -e "${RED}Failed URLs:${NC}"
  for u in "${FAILED_URLS[@]}"; do
    echo -e "  ${RED}[FAIL] $u${NC}"
  done
fi

echo ""
echo -e "  Files saved to: ${BOLD}$OUTPUT_DIR${NC}"
echo ""
