Two additions then: (1) filename parsing — since your names carry YYYY-MM-DD-location-subject, I'll extract those into dedicated columns during scan; (2) runtime tracking in every script. The "only new photos" logic is already in place, and I'll make each program report new vs. skipped explicitly. Building and testing now.





Ran a command

Fixing a bug I introduced in scan.py's \_\_main\_\_ (it would have run the scan twice), then finishing the other scripts.





Ran 2 commands

All built and verified on DuckDB 2.0.0. What's new:



Filename parsing: 2026-11-01-Tutsch-Fall.jpg → photo\_date=2026-11-01, location='Tutsch', subject='Fall' (new columns; non-matching names like IMG\_9999.jpg get NULLs and are still processed)

New-only processing: already the core design — scan inserts only new full\_paths (in-memory dedup), embed/tag/caption only touch rows where their column is still NULL; each script now says explicitly how many it processed vs. skipped

Runtime tracking: every script prints runtime\[<step>]: X.Xs for N photos (Y.Y img/s) at the end

\--backfill option in scan.py to parse the name fields for rows already in your existing DB





Migration note for your existing photos.duckdb: the new columns (photo\_date, location, subject) don't exist in your current table, and CREATE TABLE IF NOT EXISTS won't add them. Either start fresh (delete photos.duckdb, rerun scan.py — you lose nothing but scan time, since embed/tag/caption results would need redoing), or keep your existing work and run this once, then python scan.py --backfill:



python -c "import duckdb; con=duckdb.connect('photos.duckdb'); con.execute('ALTER TABLE photos ADD COLUMN photo\_date DATE'); con.execute('ALTER TABLE photos ADD COLUMN location VARCHAR'); con.execute('ALTER TABLE photos ADD COLUMN subject VARCHAR'); con.close()"

python scan.py --backfill



Now you can query by parsed names, e.g. all Woodpecker photos: SELECT full\_path FROM photos WHERE subject = 'Woodpecker', or everything from Tutsch in 2026: WHERE location = 'Tutsch' AND year(photo\_date) = 2026. Verified in the sandbox: parsing (including bad dates and non-matching names), idempotent rescan (0 new), embed re-run (0 processed), all on DuckDB 2.0.0.













Behavior of similar:



python similar.py "O:\\Bilder\\1-D7100\\\_JDA9525.jpg" — works regardless of how the path is cased or slashed in the DB; prints the resolved stored path plus the top-N similar photos with captions

python similar.py "d7100" — no exact match, so it lists up to 20 paths containing that text so you can pick one

Unknown text → NOT IN TABLE with the hint to scan first

Photo without embedding → NO EMBEDDING YET with the hint to run embed.py

The target itself appears at the top with score 1.0000 — that's your confirmation the lookup worked

One caveat: if the same filename exists in several folders, an exact full path is still required — but the fuzzy listing shows you the stored spellings to copy.



Photo Viewer
Layout (matching your spec):

Top bar: the full\_path of the selected photo — left-click opens it in the Windows default viewer (os.startfile, i.e. the Photos app), right-click copies it to the clipboard, and there's a Copy path button too
Left sidebar: search panel + folder list (folder names with photo counts)
Main pane: the selected photo, scaled to fit, redrawn on window resize
Info pane (below main): caption (from BLIP2) and date taken (from EXIF DateTimeOriginal, falling back to file mtime)
Bottom ribbon: scrollable thumbnails (mouse wheel scrolls horizontally), loaded asynchronously 5 ms apart so the UI never freezes — same technique as your old script's V10


Behavior:

Clicking a folder loads its thumbnails (up to 500, RIBBON\_LIMIT)
Search (Enter or button) matches full\_path ILIKE, caption ILIKE (NULL captions are naturally excluded), and tags ILIKE (via array\_to\_string); the ribbon shows matches and the folder list narrows to folders containing them; Esc or Clear search resets
Thumbnails of photos on unplugged disks are silently skipped (the os.path.exists check)
The DB is opened read-only, so the viewer can run alongside the pipeline without lock conflicts
Run it with:

python photo\_viewer.py

