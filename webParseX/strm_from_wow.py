import re
import os

def sanitize_filename(name):
    """Remove characters that are invalid in filenames."""
    return re.sub(r'[<>:"/\\|?*]', '', name).strip()

def extract_title(extinf_line):
    """Extract the title after the last pipe '|' separator, or fallback to end of line."""
    # Try to get the part after the last comma (full title section)
    match = re.search(r',(.+)$', extinf_line)
    if not match:
        return "untitled"
    
    full_title = match.group(1)
    
    # If there's a pipe, take everything before it and strip leading junk like "444.[ignore] - "
    if '|' in full_title:
        full_title = full_title.split('|')[0].strip()
    
    # Remove leading pattern like "444.[ignore] - " or "123.[anything] - "
    full_title = re.sub(r'^\d*\.\[.*?\]\s*-\s*', '', full_title).strip()
    
    return sanitize_filename(full_title)

def split_m3u(input_file, output_dir):
    os.makedirs(output_dir, exist_ok=True)
    
    with open(input_file, 'r', encoding='utf-8') as f:
        lines = [line.strip() for line in f if line.strip()]
    
    # Remove the #EXTM3U header if present
    if lines and lines[0].startswith('#EXTM3U'):
        lines = lines[1:]

    count = 0
    i = 0
    while i < len(lines) - 1:
        extinf_line = lines[i]
        url_line = lines[i + 1]
        
        if extinf_line.startswith('#EXTINF') and url_line.startswith('http'):
            title = extract_title(extinf_line)
            filename = os.path.join(output_dir, f"{title}.strm")
            
            with open(filename, 'w', encoding='utf-8') as f:
                f.write(url_line)
            
            print(f"Created: {filename}")
            count += 1
            i += 2
        else:
            i += 1
    
    print(f"\nDone! Created {count} .strm files in '{output_dir}/'")

if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("Usage: python split_m3u.py <input.m3u> [output_dir]")
        sys.exit(1)
    
    input_file = sys.argv[1]
    output_dir = sys.argv[2] if len(sys.argv) > 2 else "strm_output"
    split_m3u(input_file, output_dir)