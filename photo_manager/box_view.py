# box_viewer.py

from flask import Flask, request, redirect, render_template_string
from boxsdk import OAuth2, Client
import json
import os
import threading
import shelve

# --- Configuration ---
# IMPORTANT: Replace these with your actual Box App credentials
CLIENT_ID = '54d4jiaguecu71hh7yc9vn9se334fq1f'
CLIENT_SECRET = 'uEw9MxFN04D3ZaK5C9YENqIYMhwBKz7q'
REDIRECT_URI = 'http://127.0.0.1:5000/callback' # Must match your Box App configuration
TOKEN_FILENAME = 'box_tokens_atikeee2'

# --- Flask App Initialization ---
app = Flask(__name__)
# The following is a simple way to store tokens. For a real app, use a database.
db = shelve.open(TOKEN_FILENAME)

# --- Box Authentication and Client Management ---
def get_box_client():
    """
    Initializes and returns a Box client.
    Handles token loading, refresh, and interactive authentication.
    
    NOTE: Your Box App must have the 'Read all files and folders' scope enabled.
    """
    def _store_tokens(access_token, refresh_token):
        """A callback to save tokens after they are created or refreshed."""
        db['access_token'] = access_token
        db['refresh_token'] = refresh_token
        db.sync() # Ensure the data is written to disk
    
    # Check if we have existing tokens
    access_token = db.get('access_token')
    refresh_token = db.get('refresh_token')

    # Initialize the OAuth2 object with the client credentials and token callback
    oauth = OAuth2(
        client_id=CLIENT_ID,
        client_secret=CLIENT_SECRET,
        store_tokens=_store_tokens,
        access_token=access_token,
        refresh_token=refresh_token,
    )

    # If no tokens exist, we need to perform the initial authentication
    if not access_token or not refresh_token:
        print("No tokens found. Please navigate to the /login endpoint to authenticate.")
        return None, oauth
    
    # Use the existing tokens to create a client
    client = Client(oauth)
    return client, oauth

# A global variable to hold the Box client
box_client, box_oauth = get_box_client()

# --- Flask Routes ---

@app.route('/')
def home():
    """Renders the main web page."""
    return render_template_string(HTML_CONTENT)

@app.route('/login')
def login():
    """Starts the Box OAuth2 authentication flow."""
    auth_url, csrf_token = box_oauth.get_authorization_url(REDIRECT_URI)
    
    # Store the CSRF token in the session for security
    db['csrf_token'] = csrf_token
    db.sync()
    
    return redirect(auth_url)

@app.route('/callback')
def callback():
    """Handles the redirect from Box after a user grants permission."""
    code = request.args.get('code')
    state = request.args.get('state')

    # Verify the CSRF token for security
    if state != db.get('csrf_token'):
        return "CSRF token mismatch. Authentication failed.", 403
    
    try:
        box_oauth.authenticate(code)
        # Re-initialize the client after successful authentication
        global box_client
        box_client, _ = get_box_client()
        return redirect('/')
    except Exception as e:
        return f"Authentication failed: {e}", 500

@app.route('/api/items/<folder_id>')
def get_folder_items(folder_id):
    """API endpoint to get the contents of a folder."""
    if not box_client:
        return {"error": "Authentication required. Please visit /login"}, 401
    
    try:
        folder_items = box_client.folder(folder_id).get_items()
        
        # Prepare a list of items with relevant data
        items_data = []
        for item in folder_items:
            # We only need the type, ID, and name for the front end
            item_info = {
                'type': item.type,
                'id': item.id,
                'name': item.name,
            }
            # If it's a file with an image extension, get a thumbnail URL.
            if item.type == 'file' and item.name.lower().endswith(('.png', '.jpg', '.jpeg', '.gif', '.bmp')):
                item_info['is_image'] = True
                try:
                    # Get a small thumbnail URL to display in the file list
                    # This URL is short-lived, so we only fetch it on page load.
                    item_info['thumbnail_url'] = box_client.file(item.id).get_thumbnail('128', '128', min_width='64', min_height='64').url
                except Exception:
                    # Fallback if no thumbnail can be generated
                    item_info['thumbnail_url'] = 'https://placehold.co/64x64/E2E8F0/64748B?text=IMG'
            
            items_data.append(item_info)

        return items_data
    except Exception as e:
        return {"error": str(e)}, 500

@app.route('/api/image/<file_id>')
def get_image(file_id):
    """
    New API endpoint to get a fresh, temporary download link for a file.
    This endpoint now acts as a proxy to correctly serve the image content.
    """
    if not box_client:
        return "Authentication required.", 401
    try:
        # Get the download URL for the full-sized image
        download_url = box_client.file(file_id).get_download_url()

        # Use the requests library to fetch the actual image content
        response = requests.get(download_url)
        response.raise_for_status() # Raise an exception for bad status codes

        # Return the image content with the correct MIME type
        # The mimetype is read from the response headers, which is more reliable
        # than trying to guess from the file extension.
        mimetype = response.headers.get('Content-Type')
        return send_file(io.BytesIO(response.content), mimetype=mimetype)
    except Exception as e:
        return f"Failed to get image: {e}", 500

# The following is a single HTML/JS string for the front-end.
# This makes the entire application self-contained in one file.
HTML_CONTENT = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Box Image Viewer</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet">
    <style>
        body {
            font-family: 'Inter', sans-serif;
        }
    </style>
</head>
<body>
    <div id="root" class="container mx-auto p-4 bg-gray-50 min-h-screen">
        <div id="app-content"></div>
    </div>

    <script>
        const appContent = document.getElementById('app-content');
        let pathHistory = ['0']; // Start with the root folder
        let currentFolderId = '0'; 

        // Function to navigate to a new folder
        async function navigateToFolder(folderId) {
            pathHistory.push(folderId);
            currentFolderId = folderId;
            renderFileBrowser();
        }
        
        // Function to navigate back
        async function navigateBack() {
            if (pathHistory.length > 1) {
                pathHistory.pop(); // Remove current folder from history
                currentFolderId = pathHistory[pathHistory.length - 1]; // Get the previous folder
                renderFileBrowser();
            }
        }

        // Function to render the main file browser UI
        async function renderFileBrowser() {
            appContent.innerHTML = `<div class="text-center text-blue-600 font-medium">Loading...</div>`;
            try {
                const response = await fetch(`/api/items/${currentFolderId}`);
                const items = await response.json();

                if (response.status !== 200) {
                    appContent.innerHTML = `
                        <div class="flex flex-col items-center justify-center min-h-screen bg-gray-100 p-4">
                            <div class="bg-white p-8 rounded-xl shadow-lg w-full max-w-sm text-center">
                                <h1 class="text-2xl font-bold mb-4 text-gray-800">Box Image Viewer</h1>
                                <p class="text-gray-600 mb-6">Authentication required.</p>
                                <a href="/login" class="w-full px-6 py-3 rounded-lg bg-blue-600 text-white font-semibold hover:bg-blue-700 transition-colors inline-block">
                                    Connect to Box
                                </a>
                            </div>
                        </div>
                    `;
                    return;
                }

                let itemsHtml = items.map(item => {
                    const isImage = item.is_image;
                    const icon = item.type === 'folder' 
                        ? `<svg class="w-12 h-12 text-blue-500 mb-2" fill="currentColor" viewBox="0 0 20 20"><path d="M2 6a2 2 0 012-2h5l2 2h5a2 2 0 012 2v6a2 2 0 01-2 2H4a2 2 0 01-2-2V6z"></path></svg>`
                        : (isImage 
                            ? `<img src="${item.thumbnail_url}" class="w-12 h-12 object-cover rounded-md mb-2"/>`
                            : `<svg class="w-12 h-12 text-green-500 mb-2" fill="currentColor" viewBox="0 0 24 24"><path d="M4 3a2 2 0 00-2 2v14a2 2 0 002 2h16a2 2 0 002-2V7a2 2 0 00-2-2h-8l-2-2zM12 11a1 1 0 100 2h6a1 1 0 100-2h-6z"></path></svg>`);
                    
                    const onClickAction = item.type === 'folder' 
                        ? `navigateToFolder('${item.id}');` 
                        : (isImage ? `viewImage('${item.name}', '${item.id}')` : '');

                    return `
                        <div onclick="${onClickAction}" class="flex flex-col items-center p-4 bg-white rounded-lg shadow-md hover:shadow-lg transition-shadow cursor-pointer">
                            ${icon}
                            <span class="text-sm text-center font-medium truncate w-full">${item.name}</span>
                        </div>
                    `;
                }).join('');

                const backButton = pathHistory.length > 1 
                    ? `<div class="mt-8 text-center">
                           <button onclick="navigateBack();" class="px-4 py-2 bg-gray-300 text-gray-800 rounded-lg hover:bg-gray-400 transition-colors">
                               Go Back
                           </button>
                       </div>`
                    : '';

                appContent.innerHTML = `
                    <h1 class="text-3xl font-bold text-center text-gray-800 my-6">Your Box Files</h1>
                    <div class="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 gap-4">
                        ${itemsHtml}
                    </div>
                    ${backButton}
                `;

            } catch (error) {
                appContent.innerHTML = `<div class="text-center text-red-600 font-medium">Error: ${error.message}</div>`;
            }
        }

        // Function to display an image in a modal
        async function viewImage(name, fileId) {
            const modalHtml = `
                <div id="image-modal" class="fixed inset-0 z-50 flex items-center justify-center bg-black bg-opacity-80 p-4" onclick="document.getElementById('image-modal').remove()">
                    <div class="relative bg-white rounded-xl shadow-2xl p-4 max-w-5xl max-h-full overflow-hidden" onclick="event.stopPropagation()">
                        <button class="absolute top-2 right-2 text-xl font-bold text-gray-600 hover:text-gray-900" onclick="document.getElementById('image-modal').remove()">
                            &times;
                        </button>
                        <h2 class="text-lg font-semibold text-center mb-2">${name}</h2>
                        <div class="w-full h-auto max-h-[80vh] flex items-center justify-center text-gray-500">
                           Loading image...
                        </div>
                    </div>
                </div>
            `;
            document.body.insertAdjacentHTML('beforeend', modalHtml);
            const modal = document.getElementById('image-modal');
            const imageContainer = modal.querySelector('.max-h-[80vh]');
            let objectUrl; // To hold the URL created from the image blob

            try {
                // Fetch the image data directly from our new proxy endpoint
                const response = await fetch(`/api/image/${fileId}`);
                
                if (!response.ok) {
                    throw new Error(`HTTP error! status: ${response.status}`);
                }
                
                // Get the response as a blob (raw binary data)
                const imageBlob = await response.blob();
                
                // Create a temporary URL for the blob
                objectUrl = URL.createObjectURL(imageBlob);
                
                // Update the modal with the image once the URL is fetched
                imageContainer.innerHTML = `<img src="${objectUrl}" alt="${name}" class="max-w-full max-h-full object-contain mx-auto" onerror="this.onerror=null; this.src='https://placehold.co/600x400/FF0000/FFFFFF?text=Image+Load+Error';"/>`;
                
                // When the modal is removed, revoke the object URL to prevent memory leaks
                modal.addEventListener('remove', () => {
                    URL.revokeObjectURL(objectUrl);
                });
            } catch (error) {
                imageContainer.innerHTML = `<p class="text-center text-red-600">Failed to load image: ${error.message}</p>`;
            }
        }

        // Check for authentication and render the appropriate UI on page load
        document.addEventListener('DOMContentLoaded', () => {
            renderFileBrowser();
        });
    </script>
</body>
</html>
"""

if __name__ == '__main__':
    try:
        # This will run the Flask app and keep the script from exiting.
        print("Server is starting. Go to http://127.0.0.1:5000 in your browser.")
        print("Use Ctrl+C to stop the server.")
        app.run(debug=True, use_reloader=False)
    except Exception as e:
        print(f"An error occurred during server startup: {e}")
        # Optionally, you can log the full traceback for more detailed debugging
        import traceback
        traceback.print_exc()
