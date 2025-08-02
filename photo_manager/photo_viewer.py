import os,shutil#, piexif
import tkinter as tk
from tkinter import filedialog, Listbox, Scrollbar
from PIL import Image, ImageTk, ExifTags
from pathlib import Path
from PIL.Image import Resampling

import platform
import datetime

import json

CONFIG_FILE = "image_viewer_config.json"

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



class ImageViewerApp:
    def __init__(self, root):
        self.root = root
        self.filename=""
        self.created=""
        self.root.title("JPG Image Viewer")
        self.selected_indices = []

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

        # Listbox for filenames
        #self.listbox = Listbox(self.left_frame, width=40)
        self.listbox =  Listbox(self.left_frame, selectmode=tk.EXTENDED)

        self.listbox.pack(side=tk.LEFT, fill=tk.Y)

        scrollbar = Scrollbar(self.left_frame)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.listbox.config(yscrollcommand=scrollbar.set)
        scrollbar.config(command=self.listbox.yview)

        self.listbox.bind("<<ListboxSelect>>", self.on_listbox_select)
        
        # Buttons at top
        top_buttons = tk.Frame(self.right_frame)
        top_buttons.pack(side=tk.TOP, fill=tk.X)

        tk.Button(top_buttons, text="Browse Folder (o)", command=self.browse_folder).pack(side=tk.LEFT, padx=5)
        #tk.Button(top_buttons, text="Browse Raw", command=self.browse_folder_raw).pack(side=tk.LEFT, padx=5)
        tk.Button(top_buttons, text="Previous (b)", command=self.prev_image).pack(side=tk.LEFT, padx=5)
        tk.Button(top_buttons, text="Next (n)", command=self.next_image).pack(side=tk.LEFT, padx=5)
        tk.Button(top_buttons, text="Delete (d)", command=self.delete_current_image).pack(side=tk.LEFT, padx=5)
        tk.Button(top_buttons, text="Rotate (r)", command=self.rotate_image).pack(side=tk.LEFT, padx=5)
        tk.Button(top_buttons, text="Move (m)", command=self.move_current_images).pack(side=tk.LEFT, padx=5)
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
        self.move_postfix_entry = tk.Entry(control_row, width=10)
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
        self.root.bind("b", self.prev_image)
        self.root.bind("d", self.delete_current_image)
        self.root.bind("<Delete>", self.delete_current_image)
        self.root.bind("o", self.browse_folder)
        self.root.bind("r", self.rotate_image)
        self.root.bind('m', self.move_current_images)

        # Resize event
        self.image_canvas.bind("<Configure>", lambda e: self.show_image())
        # Status bar for filename and date
        self.status_label = tk.Label(self.right_frame, text="", anchor=tk.W, fg="gray", font=("Arial", 10))
        self.status_label.pack(side=tk.BOTTOM, fill=tk.X)

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
        for path in self.image_paths:
            self.listbox.insert(tk.END, os.path.basename(path))

        self.current_index = 0
        self.rotation_angle = 0
        self.show_image()

    def show_image(self):
        if not self.image_paths:
            self.image_canvas.delete("all")
            return
        print("showing image")
        image_path = self.image_paths[self.current_index]
        try:
            self.current_image = Image.open(image_path)
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
            date_taken = get_file_creation_time(image_path)
                

            if self.rotation_angle != 0:
                self.current_image = self.current_image.rotate(self.rotation_angle, expand=True)

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
        if self.is_typing(): return
        if not self.image_paths:
            return

        indices_to_delete = self.selected_indices if self.selected_indices else [self.current_index]
        deleted_files = []

        for idx in sorted(indices_to_delete, reverse=True):
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

        self.selected_indices = []
        self.listbox.selection_clear(0, tk.END)

        if self.image_paths:
            self.current_index = min(indices_to_delete[0], len(self.image_paths) - 1)
            self.listbox.select_set(self.current_index)
            self.show_image()
        else:
            self.image_canvas.delete("all")
            self.status_label.config(text="All files deleted.")

        if deleted_files:
            self.set_status(f"{self.filename} ({self.created})", f"Deleted {len(deleted_files)} files.")

    def rotate_image(self, event=None):
        if self.is_typing(): return
        if not self.image_paths:
            return

        path = self.image_paths[self.current_index]
        try:
            image = Image.open(path)
            rotated = image.rotate(90, expand=True)  # PIL rotates counter-clockwise by default
            rotated.save(path)  # Overwrite original image
            print(f"Rotated and saved: {path}")
            self.rotation_angle = 0  # Reset rotation tracker
            self.show_image()  # Reload and display updated image
        except Exception as e:
            print(f"Error rotating image: {e}")
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
        if self.is_typing():
            return

        if not self.image_paths:
            return

        if not self.config.get("move_base_path", ""):
            self.set_status(f"{self.filename} ({self.created})","Destination path or postfix is missing.")
            return

        # If multiple files selected, use those; otherwise fallback to current image
        indices_to_move = self.selected_indices if self.selected_indices else [self.current_index]
        moved_files = []

        for idx in sorted(indices_to_move, reverse=True):  # Reverse to avoid index shift
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

            self.selected_indices = []
            self.listbox.selection_clear(0, tk.END)


            if self.image_paths:
                self.current_index = min(indices_to_move[0], len(self.image_paths) - 1)
                self.listbox.select_set(self.current_index)
                self.show_image()
            else:
                self.image_canvas.delete("all")
                self.status_label.config(text="All files moved.")

            if moved_files:
                self.set_status(f"{self.filename} ({self.created})", f"Moved {len(moved_files)} files.")
            else:
                self.set_status(f"{self.filename} ({self.created})", "All selected files already exist.")

    def is_typing(self):
        return isinstance(self.root.focus_get(), tk.Entry)  
if __name__ == "__main__":
    root = tk.Tk()
    root.geometry("1200x800")
    app = ImageViewerApp(root)
    root.mainloop()
