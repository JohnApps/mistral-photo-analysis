# scan.py
# no location etc.
#
import json
import os
import sys
from datetime import datetime

from PIL import Image, ExifTags

from common import connect, existing_paths, status, Inserter

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
    dedup is done in-memory against existing rows (no PK/index needed)."""
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
                            "error": f"scan: {exc}",
                        }
                    )
                else:
                    w.add(
                        {
                            "path": dirpath,
                            "filename": name,
                            "full_path": full_path,
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


if __name__ == "__main__":
    import time

    if len(sys.argv) < 2:
        print("usage: python scan.py <folder> [folder ...]")
        sys.exit(1)
    con = connect()
    t0 = time.perf_counter()
    n = scan_disks(con, sys.argv[1:])
    secs = time.perf_counter() - t0
    rate = f" ({n / secs:.1f} img/s)" if secs > 0 and n else ""
    print(f"indexed {n} new photos; skipped existing (idempotent)")
    print(f"runtime[scan]: {secs:.1f}s for {n} photos{rate}")
    status(con)
    con.close()