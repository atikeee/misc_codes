import os
import tkinter as tk
from tkinter import filedialog, messagebox, Listbox, Scrollbar
from PIL import Image, ImageTk
from pathlib import Path

class ImageViewerApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Cross-Platform JPG Viewer")
        self.image_paths = []
        self.current_index = 0
        self.image_label = None

        # Layout frames
        self.left_frame = tk.Frame(root)
        self.left_frame.pack(side=tk.LEFT, fill=tk.Y)

        self.right_frame = tk.Frame(root)
        self.right_frame.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True)

        # File list with scrollbar
        self.listbox = Listbox(self.left_frame, width=40)
        self.listbox.pack(side=tk.LEFT, fill=tk.Y)

        scrollbar = Scrollbar(self.left_frame)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        self.listbox.config(yscrollcommand=scrollbar.set)
        scrollbar.config(command=self.listbox.yview)

        self.listbox.bind("<<ListboxSelect>>", self.on_listbox_select)

        # Buttons
        top_button_frame = tk.Frame(self.right_frame)
        top_button_frame.pack(side=tk.TOP, fill=tk.X)

        tk.Button(top_button_frame, text="Browse Folder", command=self.browse_folder).pack(side=tk.LEFT)
        tk.Button(top_button_frame, text="Delete Image", command=self.delete_current_image).pack(side=tk.LEFT)

        # Image display
        self.image_canvas = tk.Canvas(self.right_frame, bg="black")
        self.image_canvas.pack(fill=tk.BOTH, expand=True)

        self.root.bind("<Left>", self.prev_image)
        self.root.bind("<Right>", self.next_image)

    def browse_folder(self):
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
            print (path)

        self.current_index = 0
        self.show_image()

    def show_image(self):
        if not self.image_paths:
            return

        image_path = self.image_paths[self.current_index]
        try:
            image = Image.open(image_path)
            # Resize to fit canvas
            canvas_width = self.image_canvas.winfo_width()
            canvas_height = self.image_canvas.winfo_height()

            if canvas_width == 1 or canvas_height == 1:
                canvas_width, canvas_height = 800, 600  # default

            image.thumbnail((canvas_width, canvas_height))
            self.tk_image = ImageTk.PhotoImage(image)

            self.image_canvas.delete("all")
            self.image_canvas.create_image(
                canvas_width // 2,
                canvas_height // 2,
                anchor=tk.CENTER,
                image=self.tk_image,
            )
            self.listbox.select_clear(0, tk.END)
            self.listbox.select_set(self.current_index)
            self.listbox.see(self.current_index)
        except Exception as e:
            print(f"Error loading image: {e}")

    def next_image(self, event=None):
        if self.current_index < len(self.image_paths) - 1:
            self.current_index += 1
            self.show_image()

    def prev_image(self, event=None):
        if self.current_index > 0:
            self.current_index -= 1
            self.show_image()

    def on_listbox_select(self, event):
        selection = event.widget.curselection()
        if selection:
            self.current_index = selection[0]
            self.show_image()

    def delete_current_image(self):
        if not self.image_paths:
            return
        path = self.image_paths[self.current_index]
        try:
            os.remove(path)
            print(f"Deleted: {path}")
            del self.image_paths[self.current_index]
            self.listbox.delete(self.current_index)
            if self.current_index >= len(self.image_paths):
                self.current_index = max(0, len(self.image_paths) - 1)
            self.show_image()
        except Exception as e:
            print(f"Error deleting file: {e}")

if __name__ == "__main__":
    root = tk.Tk()
    root.geometry("1000x700")
    app = ImageViewerApp(root)
    root.mainloop()
