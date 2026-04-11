import os
import re

# Configuration
FOLDER_PATH = '/media/youtube/t' # Change this to your directory
RESERVED_PREFIX = "" # Optional: add a prefix to numbered files like 'video_'

def clean_filename(filename):
    # 1. Remove the extension to process text
    name, ext = os.path.splitext(filename)
    
    # 2. Remove metadata patterns (e.g., 2.4K reactions, 4M views, 77 shares)
    # This looks for numbers followed by K/M and common keywords
    name = re.sub(r'\d+(\.\d+)?[KM]?\s+(views|reactions|shares)', '', name, flags=re.IGNORECASE)
    
    # 3. Remove the ID at the end in brackets [12345...]
    name = re.sub(r'\[\d+\]', '', name)
    
    # 4. Remove hashtags and the symbol ↗️ or |
    name = re.sub(r'#[a-zA-Z0-9_]+', '', name)
    name = re.sub(r'[｜|↗️]', '', name)
    
    # 5. Remove any remaining emojis or non-ASCII special characters
    name = name.encode('ascii', 'ignore').decode('ascii')
    
    # 6. Final cleanup: strip extra whitespace and normalize
    name = name.strip().lower()
    
    return name, ext

def rename_files(path):
    counter = 1
    files = [f for f in os.listdir(path) if os.path.isfile(os.path.join(path, f))]
    
    for filename in files:
        old_path = os.path.join(path, filename)
        clean_name, ext = clean_filename(filename)
        
        # If the name is empty after cleaning (like your second example), use numbering
        if not clean_name or clean_name == "":
            while True:
                new_name = f"{counter:03d}{ext}"
                new_path = os.path.join(path, new_name)
                if not os.path.exists(new_path):
                    break
                counter += 1
        else:
            # Replace internal spaces with single space and use the cleaned name
            clean_name = re.sub(r'\s+', ' ', clean_name)
            new_name = f"{clean_name}{ext}"
            new_path = os.path.join(path, new_name)
            
            # Handle collisions for named files too
            if os.path.exists(new_path):
                new_name = f"{clean_name}_{counter:02d}{ext}"
                new_path = os.path.join(path, new_name)
        
        print(f"Renaming: {filename} -> {new_name}")
        os.rename(old_path, new_path)

if __name__ == "__main__":
    # Ensure you back up your files before running!
    rename_files(FOLDER_PATH)