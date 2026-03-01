import mutagen

def debug_ogg(file_path, max_len=100):
    try:
        audio = mutagen.File(file_path)
        
        if audio is None:
            print("Error: Mutagen couldn't recognize the file format.")
            return

        print(f"--- Technical Info ---")
        print(f"Type:     {type(audio).__name__}")
        print(f"Length:   {audio.info.length:.2f} seconds")
        print(f"Bitrate:  {getattr(audio.info, 'bitrate', 'Unknown')} bps")
        print(f"--- Metadata ---")

        if not audio.tags:
            print("No tags found.")
            return

        # Iterate through the dictionary keys directly
        for tag in audio.tags.keys():
            # In Opus/Vorbis, audio.tags[tag] returns a list of strings
            values = audio.tags[tag]
            val_str = "|".join(map(str, values))
            
            if len(val_str) > max_len:
                print(f"{tag:20}: [Large Value - {len(val_str)} chars] (Skipped)")
            else:
                print(f"{tag:20}: {val_str}")
                
    except Exception as e:
        print(f"Detailed Error: {e}")
        # This will print the exact line where it fails
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    # Ensure this points to your file
    debug_ogg(r"\\192.168.0.140\Media\Audio\English\Soft Eng\12.ogg")