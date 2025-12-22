import tkinter as tk
from tkinter import messagebox
from mega_dl import download_album

def on_drop(event):
    url = event.data.strip()
    status.set("Downloading...")
    root.update()
    try:
        result = download_album(url)
        status.set(result)
    except Exception as e:
        messagebox.showerror("Error", str(e))
        status.set("Error")

root = tk.Tk()
root.title("MegaDL")
root.geometry("420x180")

label = tk.Label(root, text="Drag & drop Pixeldrain album link here",
                 relief="ridge", padx=20, pady=40)
label.pack(expand=True, fill="both", padx=10, pady=10)

status = tk.StringVar(value="Idle")
tk.Label(root, textvariable=status).pack()

# Windows drag & drop
try:
    import tkinterdnd2 as dnd
    root = dnd.TkinterDnD.Tk()
    label.drop_target_register(dnd.DND_TEXT)
    label.dnd_bind("<<Drop>>", on_drop)
except ImportError:
    pass

root.mainloop()
