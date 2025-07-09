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
HEADER_SIZE = 8192 # Number of bytes to scramble/unscramble at the beginning of the file (e.g., 8KB)

def read_encryption_key(key_file_path: str) -> bytes:
    """
    Reads the encryption key from the specified file.
    Raises FileNotFoundError if the file does not exist.
    Raises ValueError if the key format is invalid.
    """
    if not os.path.exists(key_file_path):
        raise FileNotFoundError(f"Error: Key file '{key_file_path}' not found.")

    try:
        with open(key_file_path, 'rb') as f:
            loaded_key = f.read()
        # Attempt to validate the key by creating a Fernet object
        Fernet(loaded_key) # This will raise a ValueError if the key is not valid Fernet format
        print(f"Loaded encryption key from '{key_file_path}'.")
        return loaded_key
    except ValueError as e:
        raise ValueError(f"Error: Key file '{key_file_path}' contains an invalid Fernet key: {e}")
    except Exception as e:
        raise IOError(f"Error: Could not read key file '{key_file_path}': {e}")

def generate_new_encryption_key(output_file_path: str, force_overwrite: bool = False):
    """
    Generates a new Fernet encryption key and saves it to the specified file.
    Asks for confirmation if the file already exists, unless force_overwrite is True.
    """
    if os.path.exists(output_file_path) and not force_overwrite:
        confirm = input(f"WARNING: Key file '{output_file_path}' already exists. Overwrite? (y/N): ").lower()
        if confirm != 'y':
            print("Key generation cancelled.")
            sys.exit(0)
        else:
            print(f"Overwriting existing key file '{output_file_path}'.")

    try:
        encryption_key = Fernet.generate_key()
        with open(output_file_path, 'wb') as f:
            f.write(encryption_key)
        print(f"Successfully generated new encryption key and saved to '{output_file_path}'.")
        print("!!! IMPORTANT: Keep this key file safe and do not lose it! !!!")
        print("!!! This file IS your encryption key. If you lose or change this file,")
        print("!!! you will NOT be able to decrypt your files. BACK IT UP SECURELY! !!!")
    except Exception as e:
        print(f"Error: Could not generate or save key to '{output_file_path}': {e}")
        sys.exit(1)

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

    # Use subparsers for different command structures
    subparsers = parser.add_subparsers(dest='command', help='Available commands')

    # Parser for 'generate-key' command
    generate_parser = subparsers.add_parser(
        'generate-key',
        help='Generate a new encryption key file.',
        description="Generates a new encryption key and saves it to the specified path."
    )
    generate_parser.add_argument(
        'output_path',
        type=str,
        help="Full path where the new key file will be saved."
    )
    generate_parser.add_argument(
        '-f', '--force',
        action='store_true',
        help="Overwrite the key file if it already exists without prompt."
    )

    # Parent parser for operations that require a key file and a path
    process_parent_parser = argparse.ArgumentParser(add_help=False) # Don't add help here, will be added by sub-subparsers
    process_parent_parser.add_argument(
        'path',
        type=str,
        help="Full path to the file or folder to process."
    )
    process_parent_parser.add_argument(
        '-k', '--key-file',
        type=str,
        required=True, # Key file is now mandatory for these operations
        help="Path to the encryption key file."
    )

    # Parser for 'lock' command
    lock_parser = subparsers.add_parser(
        'lock',
        parents=[process_parent_parser],
        help='Full encryption of file(s)/folder(s) in-place (.enc extension).',
        description="Performs full AES encryption on the specified file(s) or folder(s) in-place. "
                    "Original files are overwritten with encrypted data and renamed with a '.enc' extension."
    )

    # Parser for 'unlock' command
    unlock_parser = subparsers.add_parser(
        'unlock',
        parents=[process_parent_parser],
        help='Decryption of encrypted file(s)/folder(s) in-place (removes .enc).',
        description="Decrypts previously encrypted file(s) or folder(s) in-place. "
                    "Encrypted files are overwritten with original data and '.enc' extension is removed."
    )

    # Parser for 'scramble' command
    scramble_parser = subparsers.add_parser(
        'scramble',
        parents=[process_parent_parser],
        help='Scrambles the header of file(s)/folder(s) in-place (.s extension).',
        description="Modifies the header of specified file(s) or folder(s) in-place, making them unreadable "
                    "by most applications. Files are renamed with a '.s' extension. This is faster than full encryption."
    )

    # Parser for 'unscramble' command
    unscramble_parser = subparsers.add_parser(
        'unscramble',
        parents=[process_parent_parser],
        help='Unscrambles the header of scrambled file(s)/folder(s) in-place (removes .s).',
        description="Restores the original header of previously scrambled file(s) or folder(s) in-place. "
                    "Scrambled files are overwritten with original data and '.s' extension is removed."
    )

    args = parser.parse_args()

    # Handle 'generate-key' command separately as it doesn't require an existing key
    if args.command == 'generate-key':
        generate_new_encryption_key(args.output_path, args.force)
        sys.exit(0) # Exit after generating key

    # For other commands, a key file is required
    try:
        encryption_key = read_encryption_key(args.key_file)
    except (FileNotFoundError, ValueError, IOError) as e:
        print(e)
        sys.exit(1)

    # Initialize Fernet key object and scramble key bytes
    fernet_key_obj = Fernet(encryption_key)
    scramble_key_bytes = base64.urlsafe_b64decode(encryption_key)

    source_path = args.path
    if not os.path.exists(source_path):
        print(f"Error: Path '{source_path}' does not exist. Exiting.")
        sys.exit(1)
    
    # Execute the chosen command
    if args.command == 'lock':
        if os.path.isfile(source_path):
            print(f"\nLocking file in place: '{source_path}'")
            encrypt_file_in_place(source_path, fernet_key_obj)
        elif os.path.isdir(source_path):
            process_files_in_directory(source_path, encrypt_file_in_place, fernet_key_obj)
        else:
            print("Invalid source path. Must be a file or a directory. Exiting.")
            sys.exit(1)

    elif args.command == 'unlock':
        if os.path.isfile(source_path):
            print(f"\nUnlocking file in place: '{source_path}'")
            decrypt_file_in_place(source_path, fernet_key_obj)
        elif os.path.isdir(source_path):
            process_files_in_directory(source_path, decrypt_file_in_place, fernet_key_obj)
        else:
            print("Invalid source path. Must be a file or a directory. Exiting.")
            sys.exit(1)

    elif args.command == 'scramble':
        if os.path.isfile(source_path):
            print(f"\nScrambling header of file: '{source_path}'")
            scramble_file_header(source_path, scramble_key_bytes)
        elif os.path.isdir(source_path):
            process_files_in_directory(source_path, scramble_file_header, scramble_key_bytes)
        else:
            print("Invalid source path. Must be a file or a directory. Exiting.")
            sys.exit(1)

    elif args.command == 'unscramble':
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
