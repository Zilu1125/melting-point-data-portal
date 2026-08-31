import tkinter as tk
from tkinter import ttk, messagebox
from pathlib import Path

try:
    from PIL import Image, ImageTk
except ImportError:
    raise ImportError("NEED Pillow，run: pip install pillow")


class FrameViewer:
    def __init__(self, root):
        self.root = root
        self.root.title("OPM Frame Viewer")
        self.root.geometry("1100x800")
        self.root.minsize(900, 650)

        self.base_dirs = {
            "Left": Path("left_frames"),
            "Centre": Path("centre_frames"),
            "Right": Path("right_frames"),
        }

        self.current_position = tk.StringVar(value="Left")
        self.frame_paths = []
        self.current_index = 0
        self.photo = None

        self.is_playing = False
        self.play_job = None
        self.speed_var = tk.IntVar(value=120)  # ms per frame

        self.build_ui()
        self.load_position()

        self.root.bind("<Left>", self.prev_frame)
        self.root.bind("<Right>", self.next_frame)
        self.root.bind("<Up>", self.prev_frame)
        self.root.bind("<Down>", self.next_frame)
        self.root.bind("<MouseWheel>", self.on_mousewheel)
        self.root.bind("<Configure>", self.on_window_resize)

    def build_ui(self):
        top = ttk.Frame(self.root, padding=10)
        top.pack(fill="x")

        ttk.Label(top, text="Position:").pack(side="left")

        position_box = ttk.Combobox(
            top,
            textvariable=self.current_position,
            values=["Left", "Centre", "Right"],
            state="readonly",
            width=10,
        )
        position_box.pack(side="left", padx=8)
        position_box.bind("<<ComboboxSelected>>", lambda e: self.change_position())

        ttk.Button(top, text="Previous", command=self.prev_frame).pack(side="left", padx=5)
        ttk.Button(top, text="Next", command=self.next_frame).pack(side="left", padx=5)

        self.play_button = ttk.Button(top, text="Play", command=self.toggle_play)
        self.play_button.pack(side="left", padx=(12, 5))

        ttk.Label(top, text="Speed (ms):").pack(side="left", padx=(10, 5))
        speed_box = ttk.Combobox(
            top,
            textvariable=self.speed_var,
            values=[50, 80, 120, 200, 300, 500],
            state="readonly",
            width=6,
        )
        speed_box.pack(side="left")

        ttk.Label(top, text="Go to frame:").pack(side="left", padx=(20, 5))
        self.goto_entry = ttk.Entry(top, width=8)
        self.goto_entry.pack(side="left")
        ttk.Button(top, text="Go", command=self.goto_frame).pack(side="left", padx=5)

        self.info_label = ttk.Label(top, text="")
        self.info_label.pack(side="right")

        middle = ttk.Frame(self.root, padding=(10, 0, 10, 0))
        middle.pack(fill="both", expand=True)

        self.image_label = ttk.Label(middle, anchor="center", background="#e9e9e9")
        self.image_label.pack(fill="both", expand=True)

        bottom = ttk.Frame(self.root, padding=10)
        bottom.pack(fill="x")

        self.slider = ttk.Scale(
            bottom,
            from_=0,
            to=0,
            orient="horizontal",
            command=self.on_slider_move
        )
        self.slider.pack(fill="x")

        self.hint_label = ttk.Label(
            self.root,
            text="mouse wheel / left-right keys / slider / play",
            padding=(10, 0, 10, 10)
        )
        self.hint_label.pack()

    def load_position(self):
        self.stop_play()

        folder = self.base_dirs[self.current_position.get()]
        if not folder.exists():
            messagebox.showerror("Error", f"Folder not found: {folder}")
            self.frame_paths = []
            self.image_label.config(image="", text="No images found")
            self.info_label.config(text="")
            return

        self.frame_paths = sorted(folder.glob("frame_*.png"))
        if not self.frame_paths:
            messagebox.showerror("Error", f"No frame PNG files found in: {folder}")
            self.image_label.config(image="", text="No images found")
            self.info_label.config(text="")
            return

        self.current_index = 0
        self.slider.configure(to=len(self.frame_paths) - 1)
        self.update_image()

    def change_position(self):
        self.load_position()

    def update_image(self):
        if not self.frame_paths:
            return

        img_path = self.frame_paths[self.current_index]
        img = Image.open(img_path)

        label_w = max(self.image_label.winfo_width(), 400)
        label_h = max(self.image_label.winfo_height(), 300)

        max_w = int(label_w * 0.92)
        max_h = int(label_h * 0.92)

        img = img.copy()
        img.thumbnail((max_w, max_h))

        self.photo = ImageTk.PhotoImage(img)
        self.image_label.config(image=self.photo, text="")

        self.info_label.config(
            text=f"{self.current_position.get()} | Frame {self.current_index + 1}/{len(self.frame_paths)}"
        )

        self.slider.set(self.current_index)

    def prev_frame(self, event=None):
        self.stop_play_if_manual()
        if self.current_index > 0:
            self.current_index -= 1
            self.update_image()

    def next_frame(self, event=None):
        self.stop_play_if_manual()
        if self.current_index < len(self.frame_paths) - 1:
            self.current_index += 1
            self.update_image()

    def goto_frame(self):
        self.stop_play_if_manual()
        try:
            value = int(self.goto_entry.get())
        except ValueError:
            messagebox.showwarning("Warning", "Please enter an integer frame number.")
            return

        idx = value - 1
        if 0 <= idx < len(self.frame_paths):
            self.current_index = idx
            self.update_image()
        else:
            messagebox.showwarning("Warning", "Frame number out of range.")

    def on_slider_move(self, value):
        if not self.frame_paths:
            return
        idx = int(float(value))
        if idx != self.current_index:
            self.current_index = idx
            self.update_image()

    def on_mousewheel(self, event):
        self.stop_play_if_manual()
        if event.delta > 0:
            if self.current_index > 0:
                self.current_index -= 1
                self.update_image()
        else:
            if self.current_index < len(self.frame_paths) - 1:
                self.current_index += 1
                self.update_image()

    def toggle_play(self):
        if not self.frame_paths:
            return

        if self.is_playing:
            self.stop_play()
        else:
            self.start_play()

    def start_play(self):
        self.is_playing = True
        self.play_button.config(text="Pause")
        self.play_loop()

    def stop_play(self):
        self.is_playing = False
        self.play_button.config(text="Play")
        if self.play_job is not None:
            self.root.after_cancel(self.play_job)
            self.play_job = None

    def stop_play_if_manual(self):
        if self.is_playing:
            self.stop_play()

    def play_loop(self):
        if not self.is_playing or not self.frame_paths:
            return

        if self.current_index < len(self.frame_paths) - 1:
            self.current_index += 1
            self.update_image()
            delay = int(self.speed_var.get())
            self.play_job = self.root.after(delay, self.play_loop)
        else:
            self.stop_play()

    def on_window_resize(self, event):
        if event.widget == self.root and self.frame_paths:
            self.update_image()


if __name__ == "__main__":
    root = tk.Tk()
    app = FrameViewer(root)
    root.mainloop()