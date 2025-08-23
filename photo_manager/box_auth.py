# box_auth.py

import os
import json
import shelve
import uuid
from boxsdk import OAuth2, Client
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs

# --- Configuration ---
# Hardcoded client credentials. REPLACE THESE with your actual values.
CLIENT_ID1 = '54d4jiaguecu71hh7yc9vn9se334fq1f'
CLIENT_SECRET1 = 'uEw9MxFN04D3ZaK5C9YENqIYMhwBKz7q'
TOKEN_FILENAME1 = 'box_tokens_atikeee'

CLIENT_ID2 = '54d4jiaguecu71hh7yc9vn9se334fq1f'
CLIENT_SECRET2 = 'uEw9MxFN04D3ZaK5C9YENqIYMhwBKz7q'
TOKEN_FILENAME2 = 'box_tokens_atiqilafamily'
# --- The temporary web server handler ---
# This class is used internally to capture the authorization code
# and state from the redirect URI.
class BoxOAuthRequestHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        """Handle GET requests from the Box redirect."""
        
        # Parse the URL to get query parameters
        query_components = parse_qs(urlparse(self.path).query)
        self.server.code = query_components.get('code', [None])[0]
        self.server.state = query_components.get('state', [None])[0]

        # Send a response to the user's browser
        self.send_response(200)
        self.send_header('Content-type', 'text/html')
        self.end_headers()
        self.wfile.write(b"<h1>Authentication successful!</h1>")
        self.wfile.write(b"<p>You can close this window and return to your application.</p>")

        # Shut down the server after one request
        self.server.should_stop = True

# --- The main authenticator class ---
class BoxAuthenticator:
    """
    A class to handle the Box.com OAuth2 authentication flow.

    This class simplifies the process of authenticating with Box, storing
    tokens, and automatically refreshing them.
    """
    def __init__(self,  account, redirect_uri):
        self.redirect_uri = redirect_uri
        if(account=="atikeee"):
            self.token_filename = TOKEN_FILENAME1
            tokens = self._load_tokens_from_file()

            self.oauth = OAuth2(
            client_id=CLIENT_ID1,
            client_secret=CLIENT_SECRET1,
            store_tokens=self._store_tokens,
            access_token=tokens.get('access_token') if tokens else None,
            refresh_token=tokens.get('refresh_token') if tokens else None
            )
        elif(account=="atiqilafamily"):
            self.token_filename = TOKEN_FILENAME2
            tokens = self._load_tokens_from_file()

            self.oauth = OAuth2(
            client_id=CLIENT_ID2,
            client_secret=CLIENT_SECRET2,
            store_tokens=self._store_tokens,
            access_token=tokens.get('access_token') if tokens else None,
            refresh_token=tokens.get('refresh_token') if tokens else None
            )

        # Initialize the OAuth2 object with a token storage callback
        if tokens and 'access_token' in tokens and 'refresh_token' in tokens:
            print("Existing tokens found. Creating Box client...")
            self.client = Client(self.oauth)
        else:
            self._interactive_authenticate()
            self.client = Client(self.oauth)

    def _store_tokens(self, access_token, refresh_token):
        """A private helper method to save tokens to a file."""
        print("Storing new tokens...")
        with shelve.open(self.token_filename) as db:
            db['access_token'] = access_token
            db['refresh_token'] = refresh_token

    def _load_access_token(self):
        """A private helper method to load the access token from a file."""
        with shelve.open(self.token_filename) as db:
            return db.get('access_token', None)

    def _load_refresh_token(self):
        """A private helper method to load the refresh token from a file."""
        with shelve.open(self.token_filename) as db:
            return db.get('refresh_token', None)

    def _store_tokens(self, access_token, refresh_token):
        with open(self.token_filename+'.json', 'w') as f:
            json.dump({
                'access_token': access_token,
                'refresh_token': refresh_token
            }, f)
    def _load_tokens_from_file(self):
        import json
        if os.path.exists(self.token_filename+'.json'):
            try:
                with open(self.token_filename+'.json', 'r') as f:
                    data = f.read().strip()
                    if not data:
                        return None  # empty file
                    return json.loads(data)
            except json.JSONDecodeError:
                return None  # corrupted file
        return None     
    
    def _interactive_authenticate(self):
        """Performs the full interactive OAuth2 authentication flow."""
        print("Starting interactive authentication flow...")
        # Generate the authorization URL and a CSRF token
        auth_url, csrf_token = self.oauth.get_authorization_url(self.redirect_uri)
        
        print("\nPlease go to the following URL in your browser to authorize this application:")
        print(f"\n{auth_url}\n")
        print("Waiting for you to authorize the app and for the callback...")
        
        # Parse the redirect_uri to get the host and port for the local server
        redirect_parts = urlparse(self.redirect_uri)
        host = redirect_parts.hostname
        port = redirect_parts.port

        # Start a local web server to capture the callback
        server = HTTPServer((host, port), BoxOAuthRequestHandler)
        server.should_stop = False
        server.code = None
        server.state = None

        # Keep the server running until it receives the callback
        while not server.should_stop:
            server.handle_request()

        # Check if we got a code and a valid state
        if server.code and server.state == csrf_token:
            print("Successfully received authorization code. Exchanging for tokens...")
            # Authenticate to get the access and refresh tokens
            self.oauth.authenticate(server.code)
            print("Tokens acquired and stored.")
            return True
        else:
            print("Authentication failed: either no code received or CSRF token mismatch.")
            return False
       
    
    def upload_file_to_folder(self, folder_name, local_file_path, overwrite=False):
        
        # Step 1: Look for folder by name in the root folder
        root_folder = self.client.folder(folder_id='0')
        target_folder = None
        for item in root_folder.get_items(limit=1000):
            if item.type == 'folder' and item.name == folder_name:
                target_folder = item
                break

        # Step 2: If folder not found, create it
        if not target_folder:
            print(f"Folder '{folder_name}' not found. Creating...")
            target_folder = root_folder.create_subfolder(folder_name)

        file_name = os.path.basename(local_file_path)

        # Step 3: Check if file exists in the folder
        existing_file = None
        for item in target_folder.get_items(limit=1000):
            if item.type == 'file' and item.name == file_name:
                existing_file = item
                break

        if existing_file:
            if overwrite:
                print(f"File '{file_name}' exists — overwriting...")
                existing_file.update_contents(local_file_path)
                print(f"✅ File '{file_name}' overwritten in '{folder_name}'.")
            else:
                print(f"⚠️ File '{file_name}' already exists in '{folder_name}'. Skipping upload.")
            return

        # Step 4: Upload the file if not found
        uploaded_file = target_folder.upload(local_file_path, file_name=file_name)
        print(f"✅ Uploaded '{file_name}' to '{folder_name}' (File ID: {uploaded_file.id})")



# --- Example usage block ---
if __name__ == '__main__':
    # Note: The redirect URI must be configured in your Box developer app
    # to point to localhost on the port you choose (e.g., http://localhost:8000/callback)
    box_auth = BoxAuthenticator(
        account = "atiqilafamily" ,
        redirect_uri='http://localhost:8000/'
    )

    client = box_auth.client

    if client:
        # Now you can use the client to make API calls!
        me = client.user().get()
        print(f"\nAuthentication successful! Hello, {me.name} ({me.id})!")

        # Example: list the items in the root folder
        root_folder_items = client.folder(folder_id='0').get_items()
        print("\nItems in your root folder:")
        for item in root_folder_items:
            print(f"- {item.type.capitalize()}: {item.name}")
        box_auth.upload_file_to_folder('test','1.jpg')
        
    else:
        print("\nAuthentication failed. Exiting.")
