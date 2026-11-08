# scan.py
import json
import os
import sys
from datetime import datetime

from PIL import Image, ExifTags

from common import (
    connect, existing_paths, parse_filename, status,
    Inserter, Updater, UPDATE_META_SQL,
)

JPEG_EXTS = {".jpg", ".jpeg"}


def _exif_to_json(img: Image.Image) -> str:
    try:
        raw = img.getexif()
        data = {}
        for tag_id, value in raw.items():
            tag = ExifTags.TAGS.get(tag_id, str(tag_id))
            if isinstance(value, bytes):
                value = value.decode("utf-8", errors="replace")
            data[tag] = str(value)
        return json.dumps(data)
    except Exception:
        return "{}"


def scan_disks(con, roots) -> int:
    """Index every JPG not yet in the table. full_path is the unique key;
    dedup is done in-memory against existing rows (no PK/index needed).
    Filenames like 2026-11-01-Tutsch-Fall.jpg are parsed into
    photo_date / location / subject."""
    seen = existing_paths(con)
    count = 0
    w = Inserter(con)
    for root in roots:
        for dirpath, _dirnames, filenames in os.walk(root):
            for name in filenames:
                ext = os.path.splitext(name)[1].lower()
                if ext not in JPEG_EXTS:
                    continue
                full_path = os.path.join(dirpath, name)
                if full_path in seen:
                    continue
                seen.add(full_path)
                photo_date, location, subject = parse_filename(name)
                try:
                    st = os.stat(full_path)
                    with Image.open(full_path) as img:
                        width, height = img.size
                        exif_json = _exif_to_json(img)
                except Exception as exc:
                    w.add(
                        {
                            "path": dirpath,
                            "filename": name,
                            "full_path": full_path,
                            "photo_date": photo_date,
                            "location": location,
                            "subject": subject,
                            "error": f"scan: {exc}",
                        }
                    )
                else:
                    w.add(
                        {
                            "path": dirpath,
                            "filename": name,
                            "full_path": full_path,
                            "photo_date": photo_date,
                            "location": location,
                            "subject": subject,
                            "file_size": st.st_size,
                            "mtime": datetime.fromtimestamp(st.st_mtime),
                            "width": width,
                            "height": height,
                            "exif_json": exif_json,
                        }
                    )
                count += 1
    w.flush()
    return count


def backfill_names(con) -> int:
    """Parse photo_date/location/subject for rows already in the table
    that don't have them yet (e.g. scanned with an older script version)."""
    rows = con.execute(
        "SELECT full_path, filename FROM photos WHERE photo_date IS NULL"
    ).fetchall()
    w = Updater(con, UPDATE_META_SQL)
    n = 0
    for full_path, filename in rows:
        photo_date, location, subject = parse_filename(filename)
        if photo_date is None and location is None and subject is None:
            continue
        w.add([photo_date, location, subject, full_path])
        n += 1
    w.flush()
    return n


if __name__ == "__main__":
    import time

    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    do_backfill = "--backfill" in sys.argv
    if not args and not do_backfill:
        print("usage: python scan.py <folder> [folder ...] [--backfill]")
        sys.exit(1)
    con = connect()
    if args:
        t0 = time.perf_counter()
        n = scan_disks(con, args)
        secs = time.perf_counter() - t0
        rate = f" ({n / secs:.1f} img/s)" if secs > 0 and n else ""
        print(f"indexed {n} new photos; skipped existing (idempotent)")
        print(f"runtime[scan]: {secs:.1f}s for {n} photos{rate}")
    if do_backfill:
        t0 = time.perf_counter()
        n = backfill_names(con)
        secs = time.perf_counter() - t0
        print(f"backfilled name fields for {n} photos")
        print(f"runtime[backfill]: {secs:.1f}s for {n} photos")
    status(con)
    con.close()