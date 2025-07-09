import os
import shutil
import sys
import argparse # For command-line argument parsing

from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.backends import default_backend
import base64

# --- Configuration ---
SALT_FILE = 'salt.key' # The file where the encryption key will be stored
HEADER_SIZE = 8192 # Number of bytes to scramble/unscramble at the beginning of the file (e.g., 8KB)

def get_or_generate_encryption_key():
    """
    Reads the encryption key from SALT_FILE or generates a new one if the file doesn't exist.
    Saves the generated key to SALT_FILE.
    The key generated is a URL-safe base64 encoded 32-byte key suitable for Fernet.
    If an existing key is found but is invalid, it will be deleted and a new one generated.
    """
    encryption_key = None
    if os.path.exists(SALT_FILE):
        try:
            with open(SALT_FILE, 'rb') as f:
                loaded_key = f.read()
            # Attempt to validate the key by creating a Fernet object
            # This will raise a ValueError if the key is not valid Fernet format
            Fernet(loaded_key)
            encryption_key = loaded_key
            print(f"Loaded encryption key from '{SALT_FILE}'.")
        except ValueError:
            print(f"WARNING: '{SALT_FILE}' found but contains an invalid Fernet key. Deleting and generating a new one.")
            os.remove(SALT_FILE) # Delete the invalid key file
        except Exception as e:
            print(f"ERROR: Could not read or validate '{SALT_FILE}': {e}. Generating a new key.")
            if os.path.exists(SALT_FILE):
                os.remove(SALT_FILE) # Attempt to remove problematic file

    if encryption_key is None:
        # Generate a new Fernet key (which is already URL-safe base64 encoded)
        encryption_key = Fernet.generate_key()
        with open(SALT_FILE, 'wb') as f:
            f.write(encryption_key)
        print(f"Generated new encryption key and saved to '{SALT_FILE}'.")
        print("!!! IMPORTANT: Keep this 'salt.key' file safe and do not lose it! !!!")
        print("!!! This file IS your encryption key. If you lose or change this file,")
        print("!!! you will NOT be able to decrypt your files. BACK IT UP SECURELY! !!!")
    return encryption_key

def encrypt_file_in_place(file_path: str, fernet_key: Fernet):
    """
    Encrypts a single file in place and renames it with a .enc extension.
    """
    if file_path.endswith('.enc'):
        print(f"  Skipping: '{os.path.basename(file_path)}' is already encrypted.")
        return False

    try:
        with open(file_path, 'rb') as f:
            plaintext = f.read()

        encrypted_data = fernet_key.encrypt(plaintext)

        # Overwrite the original file with encrypted data
        with open(file_path, 'wb') as f:
            f.write(encrypted_data)

        # Rename the file to add .enc extension
        new_file_path = file_path + ".enc"
        os.rename(file_path, new_file_path)

        print(f"  Locked: '{os.path.basename(file_path)}' -> '{os.path.basename(new_file_path)}'")
        return True
    except Exception as e:
        print(f"  Error locking '{file_path}': {e}")
        return False

def decrypt_file_in_place(file_path: str, fernet_key: Fernet):
    """
    Decrypts a single encrypted file (.enc) in place and removes the .enc extension.
    """
    if not file_path.endswith('.enc'):
        print(f"  Skipping: '{os.path.basename(file_path)}' is not encrypted (missing .enc extension).")
        return False

    try:
        with open(file_path, 'rb') as f:
            encrypted_data = f.read()

        decrypted_data = fernet_key.decrypt(encrypted_data)

        # Overwrite the encrypted file with decrypted data
        with open(file_path, 'wb') as f:
            f.write(decrypted_data)

        # Rename the file to remove .enc extension
        original_file_path = file_path[:-4] # Remove .enc
        os.rename(file_path, original_file_path)

        print(f"  Unlocked: '{os.path.basename(file_path)}' -> '{os.path.basename(original_file_path)}'")
        return True
    except Exception as e:
        print(f"  Error unlocking '{file_path}': {e}")
        print("  This might be due to an incorrect key or a corrupted/tampered file.")
        return False

def process_files_in_directory(directory_path: str, operation_func, *args):
    """
    Walks through a directory and applies the given operation_func
    to each file directly in its location.
    The *args will be passed to the operation_func.
    """
    total_files = 0
    processed_count = 0
    print(f"\nProcessing files in: '{directory_path}'")

    for root, _, files in os.walk(directory_path):
        for file_name in files:
            total_files += 1
            full_file_path = os.path.join(root, file_name)

            if operation_func(full_file_path, *args):
                processed_count += 1
    print(f"\nFinished processing. {processed_count} of {total_files} files processed successfully.")

def scramble_file_header(file_path: str, scramble_key_bytes: bytes):
    """
    Scrambles the header of a single file in place and renames it with a .s extension.
    """
    if file_path.endswith('.s'):
        print(f"  Skipping: '{os.path.basename(file_path)}' is already scrambled.")
        return False

    try:
        # Ensure file is large enough to have a header of HEADER_SIZE
        file_size = os.path.getsize(file_path)
        if file_size < HEADER_SIZE:
            print(f"  Warning: File '{os.path.basename(file_path)}' is smaller than {HEADER_SIZE} bytes. Scrambling entire file.")
            bytes_to_process = file_size
        else:
            bytes_to_process = HEADER_SIZE

        with open(file_path, 'r+b') as f: # Open in read/write binary mode
            header_data = f.read(bytes_to_process)
            
            # XOR with the scramble key (repeating if key is shorter than header)
            scrambled_header = bytes(b ^ scramble_key_bytes[i % len(scramble_key_bytes)] for i, b in enumerate(header_data))

            f.seek(0) # Go back to the beginning of the file
            f.write(scrambled_header) # Write the scrambled header back

        # Rename the file to add .s extension
        new_file_path = file_path + ".s"
        os.rename(file_path, new_file_path)

        print(f"  Scrambled header: '{os.path.basename(file_path)}' -> '{os.path.basename(new_file_path)}'")
        return True
    except Exception as e:
        print(f"  Error scrambling '{file_path}': {e}")
        return False

def unscramble_file_header(file_path: str, scramble_key_bytes: bytes):
    """
    Unscrambles the header of a single file in place and removes the .s extension.
    """
    if not file_path.endswith('.s'):
        print(f"  Skipping: '{os.path.basename(file_path)}' is not scrambled (missing .s extension).")
        return False

    try:
        with open(file_path, 'r+b') as f: # Open in read/write binary mode
            # Ensure file is large enough to have a header of HEADER_SIZE
            file_size = os.path.getsize(file_path)
            if file_size < HEADER_SIZE:
                print(f"  Warning: File '{os.path.basename(file_path)}' is smaller than {HEADER_SIZE} bytes. Unscrambling entire file.")
                bytes_to_process = file_size
            else:
                bytes_to_process = HEADER_SIZE
            
            scrambled_header = f.read(bytes_to_process)
            
            # XOR again with the same key to revert (XOR is its own inverse)
            original_header = bytes(b ^ scramble_key_bytes[i % len(scramble_key_bytes)] for i, b in enumerate(scrambled_header))

            f.seek(0) # Go back to the beginning of the file
            f.write(original_header) # Write the original header back

        # Rename the file to remove .s extension
        original_file_path = file_path[:-len('.s')] # Remove .s
        os.rename(file_path, original_file_path)

        print(f"  Unscrambled header: '{os.path.basename(file_path)}' -> '{os.path.basename(original_file_path)}'")
        return True
    except Exception as e:
        print(f"  Error unscrambling '{file_path}': {e}")
        print("  This might be due to an incorrect key or a corrupted/tampered file.")
        return False


def main():
    parser = argparse.ArgumentParser(
        description="Fast Photo Encryptor/Decryptor for in-place operations.",
        formatter_class=argparse.RawTextHelpFormatter # Preserves formatting for descriptions
    )

    parser.add_argument(
        'mode',
        choices=['lock', 'unlock', 'scramble', 'unscramble'],
        help="""Operation mode:
  lock     - Full encryption of file(s)/folder(s) in-place (.enc extension).
  unlock   - Decryption of encrypted file(s)/folder(s) in-place (removes .enc).
  scramble - Scrambles the header of file(s)/folder(s) in-place (.s extension).
  unscramble - Unscrambles the header of scrambled file(s)/folder(s) in-place (removes .s)."""
    )
    parser.add_argument(
        'path',
        type=str,
        help="Full path to the file or folder to process."
    )

    args = parser.parse_args()

    # Get or generate the encryption key (from salt.key)
    encryption_key = get_or_generate_encryption_key()

    # Initialize Fernet key object and scramble key bytes
    fernet_key_obj = Fernet(encryption_key)
    scramble_key_bytes = base64.urlsafe_b64decode(encryption_key)

    source_path = args.path
    if not os.path.exists(source_path):
        print(f"Error: Path '{source_path}' does not exist. Exiting.")
        sys.exit(1)

    if args.mode == 'lock':
        if os.path.isfile(source_path):
            print(f"\nLocking file in place: '{source_path}'")
            encrypt_file_in_place(source_path, fernet_key_obj)
        elif os.path.isdir(source_path):
            process_files_in_directory(source_path, encrypt_file_in_place, fernet_key_obj)
        else:
            print("Invalid source path. Must be a file or a directory. Exiting.")
            sys.exit(1)

    elif args.mode == 'unlock':
        if os.path.isfile(source_path):
            print(f"\nUnlocking file in place: '{source_path}'")
            decrypt_file_in_place(source_path, fernet_key_obj)
        elif os.path.isdir(source_path):
            process_files_in_directory(source_path, decrypt_file_in_place, fernet_key_obj)
        else:
            print("Invalid source path. Must be a file or a directory. Exiting.")
            sys.exit(1)

    elif args.mode == 'scramble':
        if os.path.isfile(source_path):
            print(f"\nScrambling header of file: '{source_path}'")
            scramble_file_header(source_path, scramble_key_bytes)
        elif os.path.isdir(source_path):
            process_files_in_directory(source_path, scramble_file_header, scramble_key_bytes)
        else:
            print("Invalid source path. Must be a file or a directory. Exiting.")
            sys.exit(1)

    elif args.mode == 'unscramble':
        if os.path.isfile(source_path):
            print(f"\nUnscrambling header of file: '{source_path}'")
            unscramble_file_header(source_path, scramble_key_bytes)
        elif os.path.isdir(source_path):
            process_files_in_directory(source_path, unscramble_file_header, scramble_key_bytes)
        else:
            print("Invalid source path. Must be a file or a directory. Exiting.")
            sys.exit(1)

    print("\nOperation complete.")

if __name__ == "__main__":
    main()
