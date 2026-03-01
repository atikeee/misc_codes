"""
Installer command: 

pyinstaller --noconfirm --windowed --onefile --name "PhotoViewer" photo_viewer.py
pyinstaller PhotoViewer.spec 
a = Analysis(
    ['photo_viewer.py'],
    pathex=['C:\\github\\utils'],
    binaries=[],
    datas=[],
    hiddenimports=['boxsdk.object.folder', 'boxsdk.object.user'],
     excludes=['boxsdk.object.recent_item'],
     )
Need to install pywin32. 
add the bin folder to the env path. 
and jpegtran tools need to be installed. 
https://gnuwin32.sourceforge.net/packages/jpeg.htm
"""

import mimetypes
import os,shutil#, piexif
import threading
import platform
import datetime
import rawpy
import imageio
import requests
import json
import subprocess
import tkinter as tk
from tkinter import filedialog, ttk
from box_auth import BoxAuthenticator
from PIL import Image, ImageTk, ExifTags
from pathlib import Path
from PIL.Image import Resampling
from google.oauth2 import service_account
from googleapiclient.http import MediaFileUpload
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials


CONFIG_FILE = "image_viewer_config.json"
RAW_EXTS = [".cr2", ".cr3", ".arw", ".nef", ".rw2"]


def load_config():
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r") as f:
                return json.load(f)
        except:
            pass
    return {"move_base_path": "", "move_postfix": ""}

def save_config(config):
    try:
        with open(CONFIG_FILE, "w") as f:
            json.dump(config, f)
    except Exception as e:
        print(f"Failed to save config: {e}")


def get_file_creation_time(path):
    try:
        if platform.system() == 'Windows':
            ctime = os.path.getctime(path)
        else:
            stat = os.stat(path)
            ctime = getattr(stat, 'st_birthtime', stat.st_mtime)
        return datetime.datetime.fromtimestamp(ctime).strftime("%Y-%m-%d %I:%M %p")
    except Exception as e:
        return "Unknown"
        
def rotate_jpeg_lossless(path, clockwise=True):
    angle = '270' if clockwise else '90'
    try:
        subprocess.run([
            'jpegtran', '-rotate', angle, '-copy', 'all', '-perfect',
            '-outfile', path, path
        ], check=True)
        return True

    except subprocess.CalledProcessError as e:
        print(f"jpegtran failed: {e}")
        return False


class ImageViewerApp:
    def __init__(self, root):
        self.rawflag = False
        self.root = root
        self.filename=""
        self.created=""
        self.root.title("JPG Image Viewer")
        self.selected_indices = []
        self.converted_raw_cache = {}
        self.image_paths = []
        self.current_index = 0
        self.tk_image = None
        self.current_image = None
        self.rotation_angle = 0
        self.config = load_config()

        # Frames
        self.left_frame = tk.Frame(root)
        self.left_frame.pack(side=tk.LEFT, fill=tk.Y)

        self.right_frame = tk.Frame(root)
        self.right_frame.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True)

        # tk.Listbox for filenames
        #self.listbox = tk.Listbox(self.left_frame, width=40)
        self.listbox =  tk.Listbox(self.left_frame, selectmode=tk.EXTENDED)

        self.listbox.pack(side=tk.LEFT, fill=tk.Y)
        # Persistent marking of images
        self.marked_flags = set()  # store marked state {index: True/False}
        self.original_labels = {} 
        self.listbox.bind("<Control-Button-1>", self.toggle_mark)  # ctrl+click
        self.listbox.bind("<space>", self.toggle_mark_key)         # spacebar

        scrollbar = tk.Scrollbar(self.left_frame)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.listbox.config(yscrollcommand=scrollbar.set)
        scrollbar.config(command=self.listbox.yview)

        self.listbox.bind("<<ListboxSelect>>", self.on_listbox_select)
        
        # Buttons at top
        top_buttons = tk.Frame(self.right_frame)
        top_buttons.pack(side=tk.TOP, fill=tk.X)

        tk.Button(top_buttons, text="Browse Folder (o)", command=self.browse_folder).pack(side=tk.LEFT, padx=5)
        tk.Button(top_buttons, text="Browse Raw (p)", command=self.browse_folder_raw).pack(side=tk.LEFT, padx=5)
        tk.Button(top_buttons, text="Previous (b)", command=self.prev_image).pack(side=tk.LEFT, padx=5)
        tk.Button(top_buttons, text="Next (n)", command=self.next_image).pack(side=tk.LEFT, padx=5)
        tk.Button(top_buttons, text="Delete (d)", command=self.delete_current_image).pack(side=tk.LEFT, padx=5)
        tk.Button(top_buttons, text="Rotate (r)", command=self.rotate_image).pack(side=tk.LEFT, padx=5)
        tk.Button(top_buttons, text="Move (m)", command=self.move_current_images).pack(side=tk.LEFT, padx=5)
        tk.Button(top_buttons, text="Convert (c)", command=self.convert_raw_images).pack(side=tk.LEFT, padx=(5, 2))
        tk.Button(top_buttons, text="Google Drive(g)", command=self.upload_to_drive).pack(side=tk.LEFT, padx=5)
        tk.Button(top_buttons, text="box.atikeee(q)", command=self.upload_to_box1).pack(side=tk.LEFT, padx=5)
        tk.Button(top_buttons, text="box.atiqilafamily(x)", command=self.upload_to_box2).pack(side=tk.LEFT, padx=5)

        # Image display
        self.image_canvas = tk.Canvas(self.right_frame, bg="black")
        self.image_canvas.pack(fill=tk.BOTH, expand=True)
        # --- Compact control row (single line) ---
        control_row = tk.Frame(self.right_frame)
        control_row.pack(fill=tk.X, padx=10, pady=5)

        # Raw checkbox
        self.raw_var = tk.BooleanVar()
        tk.Checkbutton(control_row, text="Raw", variable=self.raw_var).pack(side=tk.LEFT)

        # Move base folder
        tk.Label(control_row, text="Destination:").pack(side=tk.LEFT)
        self.move_base_entry = tk.Entry(control_row, width=25, state="readonly")
        self.move_base_entry.config(state="normal")
        self.move_base_entry.insert(0, self.config.get("move_base_path", ""))
        self.move_base_entry.config(state="readonly")

#        self.move_base_entry.insert(0, self.config.get("move_base_path", ""))
        self.move_base_entry.pack(side=tk.LEFT, padx=2)

        # Browse button
        tk.Button(control_row, text="📁", command=self.browse_destination).pack(side=tk.LEFT)
        
        self.no_date_var = tk.BooleanVar(value=False)
        self.no_date_check = tk.Checkbutton(control_row, text="No Date", variable=self.no_date_var)
        self.no_date_check.pack(side=tk.LEFT, padx=(5, 0))

        # Postfix
        tk.Label(control_row, text="Postfix:").pack(side=tk.LEFT, padx=(10, 0))
        self.move_postfix_entry = tk.Entry(control_row, width=30)
        self.move_postfix_entry.insert(0, self.config.get("move_postfix", ""))
        self.move_postfix_entry.pack(side=tk.LEFT, padx=2)
        self.move_postfix_entry.bind("<Return>", self.save_postfix_and_lock)
        self.move_postfix_entry.bind("<Button-1>", self.unlock_postfix)


        # Save button
        #tk.Button(control_row, text="💾", command=self.save_move_settings).pack(side=tk.LEFT, padx=(5, 2))

        # Move button
        #tk.Button(control_row, text="📦 Move", command=self.move_current_images).pack(side=tk.LEFT, padx=(5, 0))

        # Key bindings
        self.root.bind("<Left>", self.prev_image)
        self.root.bind("<Right>", self.next_image)
        self.root.bind("n", self.next_image)
        self.root.bind("N", self.next_image)
        self.root.bind("b", self.prev_image)
        self.root.bind("B", self.prev_image)
        self.root.bind("d", self.delete_current_image)
        self.root.bind("D", self.delete_current_image)
        self.root.bind("<Delete>", self.delete_current_image)
        self.root.bind("o", self.browse_folder)
        self.root.bind("O", self.browse_folder)
        self.root.bind("p", self.browse_folder_raw)
        self.root.bind("P", self.browse_folder_raw)
        self.root.bind("R", self.rotate_image)
        self.root.bind("r", self.rotate_image)
        self.root.bind("C", self.convert_raw_images)
        self.root.bind("c", self.convert_raw_images)
        self.root.bind('M', self.move_current_images)
        self.root.bind('m', self.move_current_images)
        self.root.bind('g',self.upload_to_drive)
        self.root.bind('G',self.upload_to_drive)
        self.root.bind('x',self.upload_to_box2)
        self.root.bind('X',self.upload_to_box2)
        self.root.bind('q',self.upload_to_box1)
        self.root.bind('Q',self.upload_to_box1)
        # Resize event
        self.image_canvas.bind("<Configure>", lambda e: self.show_image())
        # Status bar for filename and date
        self.status_label = tk.Label(self.right_frame, text="", anchor=tk.W, fg="gray", font=("Arial", 10))
        self.status_label.pack(side=tk.BOTTOM, fill=tk.X)
    def toggle_mark(self, event):
        """Toggle mark on ctrl+click"""
        idx = self.listbox.nearest(event.y)
        if idx < 0 or idx >= len(self.image_paths):
            return
        self._flip_mark(idx)

    def toggle_mark_key(self, event):
        """Toggle mark on space key for current selection"""
        idx = self.current_index
        idx = self.current_index
        if idx is None or idx < 0 or idx >= len(self.image_paths):
            return
        self._flip_mark(idx)


    def _flip_mark(self, idx):
        if idx < 0 or idx >= len(self.image_paths):
            return

        if idx in self.marked_flags:
            self.marked_flags.remove(idx)
            self.listbox.delete(idx)
            self.listbox.insert(idx, self.original_labels[idx])
        else:
            self.marked_flags.add(idx)
            self.listbox.delete(idx)
            self.listbox.insert(idx, f"{self.original_labels[idx]}✅")


    def get_marked_indices(self):
        """Return list of marked indices"""
        #return [i for i, marked in self.marked_flags.items() if marked]
        return list(self.marked_flags)

    def show_progress_dialog(self, message="Processing..."):
        self.progress_dialog = tk.Toplevel(self.root)
        self.progress_dialog.title("Please wait")
        self.progress_dialog.geometry("300x100")
        self.progress_dialog.resizable(False, False)
        self.progress_dialog.grab_set()

        tk.Label(self.progress_dialog, text=message).pack(pady=10)
        self.progress_bar = ttk.Progressbar(self.progress_dialog, mode='indeterminate')
        self.progress_bar.pack(fill=tk.X, padx=20, pady=5)
        self.progress_bar.start(10)

        # Disable all other controls
        self.disable_ui()

    def close_progress_dialog(self):
        self.progress_bar.stop()
        self.progress_dialog.destroy()
        self.enable_ui()

    def disable_ui(self):
        self.root.attributes("-disabled", True)

    def enable_ui(self):
        self.root.attributes("-disabled", False)



    def on_listbox_select(self, event):
        if not self.image_paths:
            return
        selections = self.listbox.curselection()
        if not selections:
            return

        self.selected_indices = list(selections)
        self.current_index = self.selected_indices[0]
        self.show_image()




    def set_status(self, info,message=None):
        #current_text = self.status_label.cget("text")
        #parts = current_text.split(" | ")
        if message:
            info += f"| {message}"
        self.status_label.config(text=info)


    def browse_folder(self, event=None):
        self.rawflag = False

        if self.is_typing(): return
        folder = filedialog.askdirectory()
        if not folder:
            return

        self.image_paths = [
            str(p) for p in Path(folder).rglob("*")
            if p.suffix.lower() == ".jpg"
        ]
        self.image_paths.sort()

        self.listbox.delete(0, tk.END)
        #for path in self.image_paths:
        #    self.listbox.insert(tk.END, os.path.basename(path))
        self.marked_flags.clear()       # reset marked state
        self.original_labels.clear()    # reset clean labels

        for i, path in enumerate(self.image_paths):
            name = os.path.basename(path)
            self.listbox.insert(tk.END, name)
            self.original_labels[i] = name   # save clean 
        self.current_index = 0
        self.rotation_angle = 0
        self.show_image()
        
    def browse_folder_raw(self, event = None):
        folder = filedialog.askdirectory()
        if not folder:
            return

        raw_files = []
        for ext in RAW_EXTS:
            raw_files.extend(Path(folder).rglob(f"*{ext}"))

        raw_files = sorted(str(p) for p in raw_files)

        if not raw_files:
            self.set_status("No RAW images found.")
            return
        self.rawflag = True

        self.image_paths = raw_files
        self.current_index = 0
        self.selected_indices = set()
        self.rotation_angle = 0

        self.listbox.delete(0, tk.END)
        for f in self.image_paths:
            self.listbox.insert(tk.END, os.path.basename(f))
        self.marked_flags.clear()        # reset tick-mark state
        self.original_labels.clear()     # reset clean labels

        for i, f in enumerate(self.image_paths):
            name = os.path.basename(f)
            self.listbox.insert(tk.END, name)
            self.original_labels[i] = name   # save clean name for tick toggling
        self.listbox.select_set(0)
        self.listbox.event_generate("<<ListboxSelect>>")

        self.set_status(f"Loaded {len(raw_files)} RAW files.")
        self.show_image()
        
    def show_image(self):
        if not self.image_paths:
            self.image_canvas.delete("all")
            return

        image_path = self.image_paths[self.current_index]
        self.filename = os.path.basename(image_path)
        self.created = None
        try:
            if self.rawflag and Path(image_path).suffix.lower() in RAW_EXTS:
                with rawpy.imread(image_path) as raw:
                    rgb = raw.postprocess()
                self.current_image = Image.fromarray(rgb)
                self.created = get_file_creation_time(image_path)  # RAW has no EXIF typically
            else:
                self.current_image = Image.open(image_path).copy()
            #exif_data = {}
            #date_taken = None
            #try:
            #    print(self.current_image.info)
            #    exif_dict = piexif.load(self.current_image.info.get("exif", None))
            #    print(exif_dict,"hhh")
            #    date_taken = exif_dict["Exif"].get(piexif.ExifIFD.DateTimeOriginal)
            #    if date_taken:
            #        date_taken = date_taken.decode()
            #        print("EXIF DateTimeOriginal:", date_taken)
            #    else:
            #        print("EXIF DateTimeOriginal not found.")
            #except Exception as e:
            #    print("piexif error:", e)


            # Use file creation date if EXIF missing
            #if not date_taken:
            #date_taken = get_file_creation_time(image_path)
                

            #if not self.rawflag and self.rotation_angle != 0:
            #    self.current_image = self.current_image.rotate(self.rotation_angle, expand=True)

            # Resize to fit canvas while preserving aspect ratio
            canvas_width = self.image_canvas.winfo_width()
            canvas_height = self.image_canvas.winfo_height()

            img_ratio = self.current_image.width / self.current_image.height
            canvas_ratio = canvas_width / canvas_height

            if img_ratio > canvas_ratio:
                new_width = canvas_width
                new_height = int(canvas_width / img_ratio)
            else:
                new_height = canvas_height
                new_width = int(canvas_height * img_ratio)

            #resized = self.current_image.resize((new_width, new_height), Image.LANCZOS)
            
            resized = self.current_image.resize((new_width, new_height), Resampling.LANCZOS)
            self.tk_image = ImageTk.PhotoImage(resized)

            self.image_canvas.delete("all")
            self.image_canvas.create_image(
                canvas_width // 2,
                canvas_height // 2,
                anchor=tk.CENTER,
                image=self.tk_image
            )
            # Highlight selected image in list
            #self.listbox.select_clear(0, tk.END)
            #self.listbox.select_set(self.current_index)
            #self.listbox.see(self.current_index)
            # Highlight selection only if not multi-selecting
            if len(self.selected_indices) <= 1:
                self.listbox.select_clear(0, tk.END)
                self.listbox.select_set(self.current_index)
                self.listbox.see(self.current_index)

            # Update status bar
            self.filename = os.path.basename(image_path)
            self.created = get_file_creation_time(image_path)
            #self.status_label.config(text=f"File: {filename} | Created: {created}")
            self.set_status(f"{self.filename} ({self.created})")

        except Exception as e:
            print(f"Error showing image: {e}")

    def next_image(self, event=None):
        if self.is_typing(): return
        if self.current_index < len(self.image_paths) - 1:
            self.current_index += 1
            self.rotation_angle = 0
            self.show_image()

    def prev_image(self, event=None):
        if self.is_typing(): return
        if self.current_index > 0:
            self.current_index -= 1
            self.rotation_angle = 0
            self.show_image()

    def delete_current_image(self, event=None):
        if self.is_typing() or not self.image_paths:
            return
        self.show_progress_dialog("Deleting images...")

        def task():
            try:
                self._delete_current_image()
            finally:
                self.close_progress_dialog()

        threading.Thread(target=task).start()
        if self.is_typing(): return
        if not self.image_paths:
            return

    def _delete_current_image(self):
        #indices = self.selected_indices if self.selected_indices else [self.current_index]
        indices = self.get_marked_indices() or [self.current_index]
        deleted_files = []
        
        for idx in sorted(indices, reverse=True):
            current_path = Path(self.image_paths[idx])
            base_name = current_path.stem
            folder = current_path.parent

            try:
                if self.raw_var.get():
                    for f in folder.iterdir():
                        if f.stem == base_name and f.exists():
                            f.unlink()
                            deleted_files.append(f.name)
                else:
                    if current_path.exists():
                        current_path.unlink()
                        deleted_files.append(current_path.name)

                del self.image_paths[idx]
                self.listbox.delete(idx)
            except Exception as e:
                print(f"Error deleting {current_path}: {e}")

        self.marked_flags.clear()
        
        self.listbox.selection_clear(0, tk.END)

        if self.image_paths:
            self.current_index = min(indices[0], len(self.image_paths) - 1)
            self.listbox.select_set(self.current_index)
            self.show_image()
        else:
            self.image_canvas.delete("all")
            self.status_label.config(text="All files deleted.")

        if deleted_files:
            self.set_status(f"{self.filename} ({self.created})", f"Deleted {len(deleted_files)} files.")
    def rotate_image(self, event=None):
        if self.rawflag or not self.image_paths:
            return

        path = self.image_paths[self.current_index]
        clockwise = (event.char == 'r')
        success = rotate_jpeg_lossless(path, clockwise)
        if success:
            self.show_image()

    def save_move_settings(self):
        self.config["move_base_path"] = self.move_base_entry.get().strip()
        self.config["move_postfix"] = self.move_postfix_entry.get().strip()
        save_config(self.config)
        print("Settings saved.")

    def browse_destination(self):
        folder = filedialog.askdirectory()
        if folder:
            self.move_base_entry.config(state="normal")
            self.move_base_entry.delete(0, tk.END)
            self.move_base_entry.insert(0, folder)
            self.move_base_entry.config(state="readonly")

            self.config["move_base_path"] = folder
            save_config(self.config)


    def save_postfix_and_lock(self, event=None):
        new_postfix = self.move_postfix_entry.get().strip()
        self.config["move_postfix"] = new_postfix
        save_config(self.config)
        self.set_status(f"{self.filename} ({self.created})", f"Saved postfix: {new_postfix}")
        self.move_postfix_entry.config(state="readonly")
        # Return focus to root so hotkeys work
        self.root.focus()

    def unlock_postfix(self, event=None):
        if self.move_postfix_entry["state"] == "readonly":
            self.move_postfix_entry.config(state="normal")
            self.move_postfix_entry.focus()
            # Move cursor to end
            self.move_postfix_entry.icursor(tk.END)

    def move_current_images(self, event=None):
        if self.is_typing() or not self.image_paths:
            return
        self.show_progress_dialog("Moving images...")

        def task():
            try:
                self._move_images_internal()
            finally:
                self.close_progress_dialog()

        threading.Thread(target=task).start()


    def _move_images_internal(self):
    #def move_current_images(self, event=None):
        if self.is_typing(): return

        if not self.image_paths:
            return

        if not self.config.get("move_base_path", ""):
            self.set_status(f"{self.filename} ({self.created})","Destination path or postfix is missing.")
            return

        # If multiple files selected, use those; otherwise fallback to current image
        #indices = self.selected_indices if self.selected_indices else [self.current_index]
        indices = self.get_marked_indices() or [self.current_index]
        moved_files = []

        for idx in sorted(indices, reverse=True):  # Reverse to avoid index shift
            src_path = Path(self.image_paths[idx])
            created = get_file_creation_time(str(src_path))

            postfix = self.move_postfix_entry.get().strip()
            created = get_file_creation_time(str(src_path))  # Keep this
            date_prefix = datetime.datetime.strptime(created, "%Y-%m-%d %I:%M %p").strftime("%Y%m%d")
            base_path = self.move_base_entry.get().strip()
            if not postfix or not base_path:
                self.set_status(f"{self.filename} ({self.created})", "Missing base path or postfix.")
                return
            if self.no_date_var.get():
                folder_name = postfix
            else:
                folder_name = f"{date_prefix}_{postfix}"

            dest_dir = Path(base_path) / folder_name

            
            


            
            #postfix = self.config.get("move_postfix", "").strip()
            #dest_dir = Path(self.config.get("move_base_path", "")) /  f"{date_prefix}_{postfix}"
            dest_dir.mkdir(parents=True, exist_ok=True)

            files_to_move = [src_path]
            if self.raw_var.get():  # If RAW checkbox is on, get all matching base name files
                files_to_move = list(src_path.parent.glob(src_path.stem + '.*'))

            for file_path in files_to_move:
                dest_path = dest_dir / file_path.name
                if dest_path.exists():
                    self.set_status(f"{self.filename} ({self.created})",f"Already exists: {file_path.name}")
                    continue
                shutil.copy2(str(file_path), str(dest_path))
                moved_files.append(file_path)

            # Remove from list
            del self.image_paths[idx]
            self.listbox.delete(idx)
            
            self.listbox.selection_clear(0, tk.END)


            if self.image_paths:
                self.current_index = min(indices[0], len(self.image_paths) - 1)
                self.listbox.select_set(self.current_index)
                self.show_image()
            else:
                self.image_canvas.delete("all")
                self.status_label.config(text="All files moved.")

            if moved_files:
                self.set_status(f"{self.filename} ({self.created})", f"Moved {len(moved_files)} files.")
            else:
                self.set_status(f"{self.filename} ({self.created})", "All selected files already exist.")
        self.marked_flags.clear()


    def convert_raw_images(self,event=None):
        if not self.rawflag:
            self.set_status("ERROR", "No need to convert jpg")
            return
        if self.is_typing(): return
        self.show_progress_dialog("Converting Raw images...")

        def task():
            try:
                self._convert_raw_images_internal()
            finally:
                self.close_progress_dialog()

        threading.Thread(target=task).start()

    def _convert_raw_images_internal(self):
        
        #indices = self.selected_indices if self.selected_indices else [self.current_index]
        indices = self.get_marked_indices() or [self.current_index]
        postfix = self.move_postfix_entry.get().strip()
        base_path = self.move_base_entry.get().strip()
        if not postfix or not base_path:
            self.set_status(self.filename, "Missing base path or postfix.")
            return

        
        converted = []

        for idx in sorted(indices):
            src_path = Path(self.image_paths[idx])
            if src_path.suffix.lower() not in RAW_EXTS:
                continue

            try:
                # Load RAW and convert to JPEG
                with rawpy.imread(str(src_path)) as raw:
                    rgb = raw.postprocess()
                output_img = Image.fromarray(rgb)

                created = get_file_creation_time(str(src_path))
                date_prefix = datetime.datetime.strptime(created, "%Y-%m-%d %I:%M %p").strftime("%Y%m%d")

                if self.no_date_var.get():
                    folder_name = postfix
                else:
                    folder_name = f"{date_prefix}_{postfix}"

                dest_dir = Path(base_path) / folder_name
                dest_dir.mkdir(parents=True, exist_ok=True)

                dest_file = dest_dir / f"{src_path.stem}.jpg"
                if dest_file.exists():
                    self.set_status(src_path.name, "File already exists.")
                    continue

                #output_img.save(dest_file, "JPEG", quality=95)
                output_img.save(dest_file, "JPEG", quality=95, subsampling=0, optimize=True, progressive=True,dpi=(300, 300))
                converted.append(dest_file.name)

            except Exception as e:
                print(f"Failed to convert {src_path}: {e}")
                self.set_status(src_path.name, f"Conversion error: {e}")
                
        self.marked_flags.clear()
        if converted:
            self.set_status(f"{len(converted)} RAW converted to JPEG")
        else:
            self.set_status("No RAW images converted.")
            
    def upload_to_drive(self, event=None):
        if self.rawflag:
            self.set_status("ERROR", "google upload is not possible for raw files")
            return
        self.show_progress_dialog("Uploading to Google drive...")

        def task():
            try:
                self._upload_to_drive_internal()
            finally:
                self.close_progress_dialog()

        threading.Thread(target=task).start()                

    def _upload_to_drive_internal(self):

        SCOPES = ['https://www.googleapis.com/auth/drive.file']
        creds = None

        # Load cached token or log in
        if os.path.exists('token.json'):
            creds = Credentials.from_authorized_user_file('token.json', SCOPES)
        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
            else:
                flow = InstalledAppFlow.from_client_secrets_file('credentialsgp.json', SCOPES)
                creds = flow.run_local_server(port=0)
            with open('token.json', 'w') as token:
                token.write(creds.to_json())

        service = build('drive', 'v3', credentials=creds)
        postfix = self.move_postfix_entry.get().strip()
        base_path = self.move_base_entry.get().strip()
        if not postfix or not base_path:
            self.set_status(self.filename, "Missing base path or postfix.")
            return
        
        
        folder_name = postfix
        folder_query = f"name='{folder_name}' and mimeType='application/vnd.google-apps.folder' and trashed=false"
        folder_list = service.files().list(q=folder_query, spaces='drive').execute().get('files', [])
        if folder_list:
            folder_id = folder_list[0]['id']
        else:
            folder_metadata = {'name': folder_name, 'mimeType': 'application/vnd.google-apps.folder'}
            folder_id = service.files().create(body=folder_metadata, fields='id').execute()['id']

        # Determine files to upload
        #indices = self.selected_indices if self.selected_indices else [self.current_index]
        indices = self.get_marked_indices() or [self.current_index]
        uploaded = []

        for idx in indices:
            src_path = Path(self.image_paths[idx])
            filename = src_path.stem + ".jpg" if src_path.suffix.lower() in RAW_EXTS else src_path.name
            local_path = self.converted_raw_cache.get(str(src_path), str(src_path))  # use converted path if RAW

            # Check for duplicate in Drive folder
            query = f"name='{filename}' and '{folder_id}' in parents and trashed=false"
            exists = service.files().list(q=query, spaces='drive').execute().get("files", [])
            if exists:
                self.set_status(filename, "Already exists in Drive.")
                continue

            mime_type = mimetypes.guess_type(local_path)[0] or 'application/octet-stream'
            metadata = {'name': filename, 'parents': [folder_id]}
            media = MediaFileUpload(local_path, mimetype=mime_type)

            try:
                service.files().create(body=metadata, media_body=media, fields='id').execute()
                uploaded.append(filename)
            except Exception as e:
                self.set_status(filename, f"Upload failed: {e}")
        self.marked_flags.clear()
        if uploaded:
            self.set_status(f"Uploaded to Drive: {', '.join(uploaded)}")

    def upload_to_box1(self, event=None):
        if self.rawflag:
            self.set_status("ERROR", "google upload is not possible for raw files")
            return
        self.show_progress_dialog("Uploading to Box. account atikeee")

        def task():
            try:
                self._upload_to_box("atikeee")
            finally:
                self.close_progress_dialog()

        threading.Thread(target=task).start()                
    def upload_to_box2(self, event=None):
        if self.rawflag:
            self.set_status("ERROR", "google upload is not possible for raw files")
            return
        self.show_progress_dialog("Uploading to Box. account atikeee")

        def task():
            try:
                self._upload_to_box("atiqilafamily")
            finally:
                self.close_progress_dialog()

        threading.Thread(target=task).start()         

    def _upload_to_box(self,account):
        box_auth = BoxAuthenticator(
            account = account ,
            redirect_uri='http://localhost:8000/'
        )

        client = box_auth.client

        if client:
            # Now you can use the client to make API calls!
            me = client.user().get()
            print(f"\nAuthentication successful! Hello, {me.name} ({me.id})!")

            indices = self.get_marked_indices() or [self.current_index]
            uploaded = []
            for idx in indices:
                src_path = Path(self.image_paths[idx])
                created = get_file_creation_time(str(src_path))

                postfix = self.move_postfix_entry.get().strip()
                created = get_file_creation_time(str(src_path))  # Keep this
                date_prefix = datetime.datetime.strptime(created, "%Y-%m-%d %I:%M %p").strftime("%Y%m%d")
                if self.no_date_var.get():
                    folder_name = postfix
                else:
                    folder_name = f"{date_prefix}_{postfix}"
                box_auth.upload_file_to_folder(folder_name,src_path)
            
        else:
            print("\nAuthentication failed. Exiting.")
        

    
    def upload_to_one_drive(self, event=None):
        if self.rawflag:
            self.set_status("ERROR", "Onedrive upload is not possible for raw files")
            return
        self.show_progress_dialog("Uploading to OneDrive...")

        def task():
            try:
                self._upload_to_one_drive_internal()
            finally:
                self.close_progress_dialog()

        threading.Thread(target=task).start()
    def _upload_to_one_drive_internal(self,):
        
        self.set_status("ERROR", "Not implemented yet")
        pass

    def upload_to_google_photos(self, event=None):
        if self.rawflag:
            self.set_status("ERROR", "google upload is not possible for raw files")
            return
        self.show_progress_dialog("Uploading to Google...")

        def task():
            try:
                self._upload_to_google_photos_internal()
            finally:
                self.close_progress_dialog()

        threading.Thread(target=task).start()


    
    def _upload_to_google_photos_internal(self):
        
        SCOPES = ['https://www.googleapis.com/auth/photoslibrary.appendonly']
        #SCOPES = ['https://www.googleapis.com/auth/photoslibrary']
        

        creds = None
        if os.path.exists('token_photos.json'):
            creds = Credentials.from_authorized_user_file('token_photos.json', SCOPES)

        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
            else:
                flow = InstalledAppFlow.from_client_secrets_file('credential_gp.json', SCOPES)
                creds = flow.run_local_server(port=0)
            with open('token_photos.json', 'w') as token:
                token.write(creds.to_json())

        headers = {
            'Authorization': f'Bearer {creds.token}',
            'Content-type': 'application/octet-stream',
            'X-Goog-Upload-Protocol': 'raw',
        }

        indices = self.selected_indices if self.selected_indices else [self.current_index]
        uploaded = []

        for idx in indices:
            src_path = Path(self.image_paths[idx])
            # Only upload JPGs (or converted RAWs)
            
            local_path = str(src_path)

            try:
                with open(local_path, 'rb') as f:
                    upload_token = requests.post(
                        'https://photoslibrary.googleapis.com/v1/uploads',
                        data=f,
                        headers=headers
                    ).text

                if not upload_token:
                    self.set_status(src_path.name, "Upload token failed.")
                    continue

                create_body = {
                    "newMediaItems": [
                        {
                            "description": "",
                            "simpleMediaItem": {
                                "uploadToken": upload_token
                            }
                        }
                    ]
                }

                create_response = requests.post(
                    'https://photoslibrary.googleapis.com/v1/mediaItems:batchCreate',
                    headers={'Authorization': f'Bearer {creds.token}'},
                    json=create_body
                )

                if create_response.status_code == 200:
                    #print("200 response")
                    uploaded.append(os.path.basename(local_path))
                else:
                    self.set_status(src_path.name, f"Create failed: {create_response.text}")
                    print(f"{create_response.text}")

            except Exception as e:
                self.set_status(src_path.name, f"Upload error: {e}")

        if uploaded:
            self.set_status(f"Uploaded to Google Photos: {', '.join(uploaded)}")

    def is_typing(self):
        return isinstance(self.root.focus_get(), tk.Entry)  
if __name__ == "__main__":
    root = tk.Tk()
    root.geometry("1200x800")
    app = ImageViewerApp(root)
    root.mainloop()
