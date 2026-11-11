# photo_viewer.py
# V1
# V2
# V3
# photo_viewer.py
# Tkinter viewer for the photo-analysis DuckDB database.
# Search syntax per field: terms separated by space = AND,
# groups separated by '|' = OR. Fields are combined with AND.
# Thumbnails are cached on disk (.thumbcache).

import hashlib
import os
import sys
import tkinter as tk
from tkinter import ttk

import duckdb
from PIL import Image, ImageTk

Image.MAX_IMAGE_PIXELS = None

DB_PATH = r"H:\mistral-photo-analysis\photos.duckdb"
RIBBON_LIMIT = 500          # max thumbnails per folder/search
THUMB_SIZE = 110            # thumbnail px
THUMB_CACHE = os.path.join(
    os.path.dirname(os.path.abspath(DB_PATH)), ".thumbcache")
FONT = ("Segoe UI", 14)
FONT_SMALL = ("Segoe UI", 12)
FONT_PATH = ("Segoe UI", 12, "underline")


def build_clause(expr, text):
    """'a b|c' -> ((expr ILIKE %a% AND expr ILIKE %b%) OR (expr ILIKE %c%)).
    Space = AND within a group; '|' = OR between groups.
    Returns (sql, params) or (None, []) if the text is empty."""
    text = text.strip()
    if not text:
        return None, []
    or_groups, params = [], []
    for group in text.split("|"):
        terms = [t for t in group.split() if t]
        if not terms:
            continue
        conds = " AND ".join(f"({expr} ILIKE ?)" for t in terms)
        params.extend(f"%{t}%" for t in terms)
        or_groups.append(f"({conds})")
    if not or_groups:
        return None, []
    return "(" + " OR ".join(or_groups) + ")", params


class PhotoApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Photo Viewer - DuckDB")
        self.geometry("1400x900")

        self.conn = duckdb.connect(DB_PATH, read_only=True)

        self.current_photo = None      # selected photo row
        self.current_pil_image = None
        self.ribbon_images = []
        self._folder_cache = None      # [(path, count), ...]
        os.makedirs(THUMB_CACHE, exist_ok=True)

        self.setup_ui()
        self.load_folders()
        self.update_idletasks()

    # ------------------------------------------------------------------
    # UI
    # ------------------------------------------------------------------
    def setup_ui(self):
        # TOP BAR: full_path, clickable to open in default Windows viewer
        top = ttk.Frame(self)
        top.pack(side=tk.TOP, fill=tk.X, padx=8, pady=4)
        self.lbl_path = tk.Label(
            top, text="Select a photo...",
            fg="blue", cursor="hand2", font=FONT_PATH, anchor="w",
        )
        self.lbl_path.pack(side=tk.LEFT, fill=tk.X, expand=True)
        self.lbl_path.bind("<Button-1>", self.open_in_viewer)
        self.lbl_path.bind("<Button-3>", self.copy_path)
        ttk.Button(top, text="Copy path", command=self.copy_path).pack(side=tk.RIGHT)

        # MAIN SPLIT: left sidebar | right area
        main = ttk.PanedWindow(self, orient=tk.HORIZONTAL)
        main.pack(fill=tk.BOTH, expand=True)

        # LEFT SIDEBAR: search panel + folder list
        left = ttk.Frame(main, width=330)
        main.add(left, weight=1)

        ttk.Label(left, text="Search  (space = AND, | = OR):",
                  font=FONT_SMALL).pack(anchor="w", padx=6, pady=(6, 0))

        self.search_vars = {}
        for field, label in (("path", "Path:"),
                             ("caption", "Caption:"),
                             ("tags", "Tags:")):
            ttk.Label(left, text=label, font=FONT_SMALL).pack(
                anchor="w", padx=6, pady=(4, 0))
            var = tk.StringVar()
            self.search_vars[field] = var
            entry = ttk.Entry(left, textvariable=var, font=FONT_SMALL)
            entry.pack(fill=tk.X, padx=6, pady=1)
            entry.bind("<Return>", lambda e: self.do_search())
            entry.bind("<Escape>", lambda e: self.clear_search())

        ttk.Button(left, text="Search", command=self.do_search).pack(
            fill=tk.X, padx=6, pady=4)
        ttk.Button(left, text="Clear search", command=self.clear_search).pack(
            fill=tk.X, padx=6, pady=(0, 4))

        ttk.Label(left, text="Folders:", font=FONT_SMALL).pack(
            anchor="w", padx=6, pady=(6, 0))
        self.lbl_folder_info = ttk.Label(left, text="-", font=FONT_SMALL)
        self.lbl_folder_info.pack(anchor="w", padx=6)

        folder_frame = ttk.Frame(left)
        folder_frame.pack(fill=tk.BOTH, expand=True, padx=6, pady=2)
        scroll = ttk.Scrollbar(folder_frame)
        scroll.pack(side=tk.RIGHT, fill=tk.Y)
        self.folder_listbox = tk.Listbox(
            folder_frame, yscrollcommand=scroll.set,
            exportselection=False, font=("Segoe UI", 11),
        )
        scroll.config(command=self.folder_listbox.yview)
        self.folder_listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.folder_listbox.bind("<<ListboxSelect>>", self.on_folder_select)

        # RIGHT AREA: photo (expands) / info (fixed) / ribbon (fixed height)
        right = ttk.Frame(main)
        main.add(right, weight=4)

        self.main_canvas = tk.Canvas(right, bg="#1e1e1e", highlightthickness=0)
        self.main_canvas.pack(fill=tk.BOTH, expand=True)
        self.main_canvas.bind("<Configure>", lambda e: self.draw_main_image())

        # INFO PANEL: caption + date taken
        info = ttk.LabelFrame(right, text="Caption / Date taken", padding=6)
        info.pack(fill=tk.X, side=tk.BOTTOM, padx=6, pady=4)
        self.lbl_caption = ttk.Label(info, text="Caption: -", font=FONT,
                                     wraplength=900, justify=tk.LEFT)
        self.lbl_caption.pack(anchor="w")
        self.lbl_date = ttk.Label(info, text="Date taken: -", font=FONT)
        self.lbl_date.pack(anchor="w")

        # RIBBON: exactly as tall as the thumbnails - no dead space
        bottom = ttk.Frame(right, height=THUMB_SIZE + 30)
        bottom.pack(fill=tk.X, side=tk.BOTTOM, padx=6, pady=(0, 6))
        bottom.pack_propagate(False)
        self.ribbon_canvas = tk.Canvas(bottom, bg="#2d2d2d",
                                       height=THUMB_SIZE + 20,
                                       highlightthickness=0)
        rscroll = ttk.Scrollbar(bottom, orient=tk.HORIZONTAL,
                                command=self.ribbon_canvas.xview)
        self.ribbon_canvas.configure(xscrollcommand=rscroll.set)
        rscroll.pack(side=tk.BOTTOM, fill=tk.X)
        self.ribbon_canvas.pack(side=tk.TOP, fill=tk.BOTH, expand=True)
        self.ribbon_inner = ttk.Frame(self.ribbon_canvas)
        self.ribbon_canvas.create_window((0, 0), window=self.ribbon_inner,
                                          anchor="nw")
        self.ribbon_inner.bind(
            "<Configure>",
            lambda e: self.ribbon_canvas.configure(
                scrollregion=self.ribbon_canvas.bbox("all")))
        for w in (self.ribbon_canvas, self.ribbon_inner):
            w.bind("<MouseWheel>", self.on_ribbon_wheel)
            w.bind("<Shift-MouseWheel>", self.on_ribbon_wheel)

    def on_ribbon_wheel(self, event):
        if event.delta:
            self.ribbon_canvas.xview_scroll(
                int(-event.delta / 120) * 3, "units")

    # ------------------------------------------------------------------
    # DATA
    # ------------------------------------------------------------------
    def get_folders(self):
        """Folder list cached in memory after the first query."""
        if self._folder_cache is None:
            self._folder_cache = self.conn.execute(
                "SELECT path, count(*) FROM photos "
                "GROUP BY path ORDER BY path").fetchall()
        return self._folder_cache

    def load_folders(self, filtered=None):
        rows = filtered if filtered is not None else self.get_folders()
        self.folder_listbox.delete(0, tk.END)
        self.folder_data = {}
        for i, (folder, count) in enumerate(rows):
            name = folder.replace("\\", "/").rstrip("/").rpartition("/")[2] or folder
            self.folder_listbox.insert(tk.END, f"{name}  ({count})")
            self.folder_data[i] = folder
        self.lbl_folder_info.config(text=f"{len(rows)} folders")

    def on_folder_select(self, event):
        sel = self.folder_listbox.curselection()
        if not sel:
            return
        folder = self.folder_data[sel[0]]
        rows = self.conn.execute(
            """
            SELECT full_path, caption, tags, exif, mtime, width, height
            FROM photos WHERE path = ?
            ORDER BY filename LIMIT ?
            """,
            [folder, RIBBON_LIMIT],
        ).fetchall()
        self.lbl_folder_info.config(text=f"{len(rows)} photos in {folder}")
        self.populate_ribbon(rows)

    def build_where(self):
        """Combine the three search fields with AND.
        Inside each field: space = AND, '|' = OR."""
        clauses, params, desc = [], [], []
        for field, expr in (("path", "full_path"),
                            ("caption", "caption"),
                            ("tags", "array_to_string(tags, ' ')")):
            sql, p = build_clause(expr, self.search_vars[field].get())
            if sql:
                clauses.append(sql)
                params.extend(p)
                desc.append(f"{field}='{self.search_vars[field].get().strip()}'")
        if not clauses:
            return None, [], ""
        return " AND ".join(clauses), params, "  ".join(desc)

    def do_search(self):
        where, params, desc = self.build_where()
        if not where:
            return
        rows = self.conn.execute(
            """
            SELECT full_path, caption, tags, exif, mtime, width, height
            FROM photos WHERE """ + where + """
            ORDER BY full_path LIMIT ?
            """,
            params + [RIBBON_LIMIT],
        ).fetchall()
        self.lbl_folder_info.config(
            text=f"search {desc}: {len(rows)} photos (max {RIBBON_LIMIT})")
        self.populate_ribbon(rows)
        # narrow the cached folder list to folders containing matches
        matched = self.conn.execute(
            "SELECT DISTINCT path FROM photos WHERE " + where + " ORDER BY path",
            params).fetchall()
        counts = dict(self.get_folders())
        self.load_folders([(m, counts[m]) for (m,) in matched if m in counts])

    def clear_search(self):
        for var in self.search_vars.values():
            var.set("")
        self.load_folders()

    # ------------------------------------------------------------------
    # THUMBNAILS: disk cache + async loading
    # ------------------------------------------------------------------
    def _cache_file(self, full_path):
        key = hashlib.md5(full_path.lower().encode("utf-8")).hexdigest()
        return os.path.join(THUMB_CACHE, key + ".jpg")

    def get_thumbnail(self, full_path):
        """Return a PIL thumbnail, using the disk cache when possible."""
        cache_path = self._cache_file(full_path)
        try:
            if os.path.exists(cache_path):
                return Image.open(cache_path)
        except Exception:
            pass
        if not os.path.exists(full_path):
            return None
        with Image.open(full_path) as img:
            try:
                img.draft("RGB", (THUMB_SIZE * 2, THUMB_SIZE * 2))
            except Exception:
                pass
            img = img.convert("RGB")
            img.thumbnail((THUMB_SIZE, THUMB_SIZE))
            try:
                img.save(cache_path, "JPEG", quality=80)
            except Exception:
                pass
            return img

    def clear_ribbon(self):
        for w in self.ribbon_inner.winfo_children():
            w.destroy()
        self.ribbon_images.clear()

    def populate_ribbon(self, rows):
        self.clear_ribbon()
        self._thumb_batch(rows, 0)

    def _thumb_batch(self, rows, i):
        if i >= len(rows):
            return
        row = rows[i]
        try:
            thumb_pil = self.get_thumbnail(row[0])
            if thumb_pil is not None:
                thumb = ImageTk.PhotoImage(thumb_pil)
                self.ribbon_images.append(thumb)
                btn = tk.Button(
                    self.ribbon_inner, image=thumb, relief="flat", bd=1,
                    command=lambda r=row: self.show_photo(r),
                )
                btn.pack(side=tk.LEFT, padx=3, pady=3)
                btn.bind("<MouseWheel>", self.on_ribbon_wheel)
                self.ribbon_canvas.configure(
                    scrollregion=self.ribbon_canvas.bbox("all"))
        except Exception as exc:
            print(f"thumb error {row[0]}: {exc}")
        self.after(5, lambda: self._thumb_batch(rows, i + 1))

    # ------------------------------------------------------------------
    # MAIN PHOTO + INFO
    # ------------------------------------------------------------------
    def show_photo(self, row):
        full_path, caption, tags, exif, mtime, width, height = row
        self.current_photo = row
        self.lbl_path.config(text=full_path)

        date_taken = None
        try:
            date_taken = self.conn.execute(
                "select json_extract_string(?, '$.DateTimeOriginal')",
                [exif if exif else "{}"],
            ).fetchone()[0]
        except Exception:
            pass
        if not date_taken and mtime:
            date_taken = str(mtime)[:19]
        self.lbl_caption.config(text=f"Caption: {caption or '(none)'}")
        self.lbl_date.config(text=f"Date taken: {date_taken or 'unknown'}")

        try:
            with Image.open(full_path) as img:
                self.current_pil_image = img.copy()
            self.draw_main_image()
        except Exception as exc:
            print(f"main image error {full_path}: {exc}")

    def draw_main_image(self):
        if not self.current_pil_image:
            return
        w = self.main_canvas.winfo_width()
        h = self.main_canvas.winfo_height()
        if w < 10 or h < 10:
            return
        img = self.current_pil_image.copy()
        img.thumbnail((w, h), Image.Resampling.BICUBIC)
        self.main_photo_tk = ImageTk.PhotoImage(img)
        self.main_canvas.delete("all")
        self.main_canvas.create_image(w // 2, h // 2,
                                      image=self.main_photo_tk,
                                      anchor=tk.CENTER)

    # ------------------------------------------------------------------
    # TOP BAR ACTIONS
    # ------------------------------------------------------------------
    def open_in_viewer(self, event=None):
        path = self.current_photo[0] if self.current_photo else None
        if path and os.path.exists(path):
            try:
                os.startfile(path)      # Windows default viewer (Photos app)
                return
            except Exception:
                pass
            try:
                import webbrowser
                webbrowser.open("file:///" + path.replace("\\", "/"))
            except Exception as exc:
                print(f"open failed: {exc}")

    def copy_path(self, event=None):
        if self.current_photo:
            self.clipboard_clear()
            self.clipboard_append(self.current_photo[0])
            self.lbl_path.config(text=f"copied: {self.current_photo[0]}")


if __name__ == "__main__":
    if len(sys.argv) > 1:
        DB_PATH = sys.argv[1]
    app = PhotoApp()
    app.mainloop()