Two additions then: (1) filename parsing — since your names carry YYYY-MM-DD-location-subject, I'll extract those into dedicated columns during scan; (2) runtime tracking in every script. The "only new photos" logic is already in place, and I'll make each program report new vs. skipped explicitly. Building and testing now.





**Ran a command**

Fixing a bug I introduced in scan.py's \_\_main\_\_ (it would have run the scan twice), then finishing the other scripts.





**Ran 2 commands**

All built and verified on DuckDB 2.0.0. What's new:



Filename parsing: 2026-11-01-Tutsch-Fall.jpg → photo\_date=2026-11-01, location='Tutsch', subject='Fall' (new columns; non-matching names like IMG\_9999.jpg get NULLs and are still processed)

New-only processing: already the core design — scan inserts only new full\_paths (in-memory dedup), embed/tag/caption only touch rows where their column is still NULL; each script now says explicitly how many it processed vs. skipped

Runtime tracking: every script prints runtime\[<step>]: X.Xs for N photos (Y.Y img/s) at the end

\--backfill option in scan.py to parse the name fields for rows already in your existing DB





Migration note for your existing photos.duckdb: the new columns (photo\_date, location, subject) don't exist in your current table, and CREATE TABLE IF NOT EXISTS won't add them. Either start fresh (delete photos.duckdb, rerun scan.py — you lose nothing but scan time, since embed/tag/caption results would need redoing), or keep your existing work and run this once, then python scan.py --backfill:



python -c "import duckdb; con=duckdb.connect('photos.duckdb'); con.execute('ALTER TABLE photos ADD COLUMN photo\_date DATE'); con.execute('ALTER TABLE photos ADD COLUMN location VARCHAR'); con.execute('ALTER TABLE photos ADD COLUMN subject VARCHAR'); con.close()"

python scan.py --backfill



Now you can query by parsed names, e.g. all Woodpecker photos: SELECT full\_path FROM photos WHERE subject = 'Woodpecker', or everything from Tutsch in 2026: WHERE location = 'Tutsch' AND year(photo\_date) = 2026. Verified in the sandbox: parsing (including bad dates and non-matching names), idempotent rescan (0 new), embed re-run (0 processed), all on DuckDB 2.0.0.







**Behavior of similar:**



python similar.py "O:\\Bilder\\1-D7100\\\_JDA9525.jpg" — works regardless of how the path is cased or slashed in the DB; prints the resolved stored path plus the top-N similar photos with captions

python similar.py "d7100" — no exact match, so it lists up to 20 paths containing that text so you can pick one

Unknown text → NOT IN TABLE with the hint to scan first

Photo without embedding → NO EMBEDDING YET with the hint to run embed.py

The target itself appears at the top with score 1.0000 — that's your confirmation the lookup worked

One caveat: if the same filename exists in several folders, an exact full path is still required — but the fuzzy listing shows you the stored spellings to copy.





**Photo Viewer**
Layout (matching your spec):

Top bar: the full\_path of the selected photo — left-click opens it in the Windows default viewer (os.startfile, i.e. the Photos app), right-click copies it to the clipboard, and there's a Copy path button too
Left sidebar: search panel + folder list (folder names with photo counts)
Main pane: the selected photo, scaled to fit, redrawn on window resize
Info pane (below main): caption (from BLIP2) and date taken (from EXIF DateTimeOriginal, falling back to file mtime)
Bottom ribbon: scrollable thumbnails (mouse wheel scrolls horizontally), loaded asynchronously 5 ms apart so the UI never freezes — same technique as your old script's V10



**Behavior**:

Clicking a folder loads its thumbnails (up to 500, RIBBON\_LIMIT)
Search (Enter or button) matches full\_path ILIKE, caption ILIKE (NULL captions are naturally excluded), and tags ILIKE (via array\_to\_string); the ribbon shows matches and the folder list narrows to folders containing them; Esc or Clear search resets
Thumbnails of photos on unplugged disks are silently skipped (the os.path.exists check)
The DB is opened read-only, so the viewer can run alongside the pipeline without lock conflicts
Run it with:

python photo\_viewer.py





**What changed:**



No more dead space — the right side now uses pack instead of a vertical PanedWindow: the main photo expands to take all leftover space, while the info panel and ribbon are fixed-height (pack\_propagate(False)), so the ribbon is exactly as tall as its thumbnails.

Bigger fonts — caption/date: Segoe UI 13; folder list and sidebar: Segoe UI 11.

I/O optimization — the big one. The repeated disk reads weren't the folder list (that's one aggregate query over the DB, no photo-disk I/O); they were the thumbnail decoding: every click on an O:\\bilder\\1-D7100 folder re-opened and re-decoded up to 500 full-size JPEGs from the USB3 disk. Now:

On-disk thumbnail cache in H:\\mistral-photo-analysis\\.thumbcache — each photo is decoded once, the 110 px thumbnail saved as a small JPEG, and every later visit reads only the tiny cached file (measured: 20 ms → 0.4 ms per thumbnail, \~50× less work, and no more full-res reads from the O: disk at all after first view).

JPEG draft() mode — the decoder downscales while reading, so even the first visit reads less data.

In-memory folder cache — the folder list is queried once and reused; searches filter the cached list instead of re-aggregating.

Note: the first time you open each folder it still reads the originals once (unavoidable — that's when the cache fills). After that, folder browsing is nearly instant. The cache grows to roughly 3–8 KB × 11,364 photos ≈ 50–90 MB — negligible, and you can delete .thumbcache anytime to rebuild it.



Three conditions, joined with OR, so a photo matches if any one of them is true:

full\_path ILIKE ? — case-insensitive match anywhere in the complete path, e.g. O:\\Bilder\\1-D7100\\2022-04-23-Canobio\_JDA9525.jpg. This covers folder names and filenames, so %tutsch% finds photos in a ...-Tutsch folder, and %JDA9525% finds that Nikon filename wherever it lives.

caption ILIKE ? — matches the BLIP2-generated text description. Since NULL captions never satisfy ILIKE, photos without captions are simply skipped by this condition (they can still match via path or tags). So bird finds a photo captioned "a bird sitting on a branch" even if "bird" appears nowhere in its filename.

array\_to\_string(tags, ' ') ILIKE ? — the tags column is a list (\['bird', 'animal']), which can't be compared directly with ILIKE. array\_to\_string flattens it to a single string ('bird animal'), which is then matched. So animal finds every photo tagged animal.

What happens with the results:



The matching photos (up to RIBBON\_LIMIT = 500) go into the bottom thumbnail ribbon — you click a thumbnail to view it in the main pane with its caption and date.
The left folder list narrows to only the folders containing matches, keeping each folder's total photo count — so you can see where the hits live and click into a folder for its remaining photos.
The label above the folder list shows how many photos matched (and warns if you hit the 500 cap, in which case a more specific term will help).
Resetting: press Esc in the search box or click Clear search — the folder list returns to all folders and the ribbon keeps showing the last results until you click a folder.

Two things to keep in mind:

It's an OR search, not AND — there's no way to combine terms (e.g. "tutsch AND bird") in the current version. If you want that, I can extend it with support for multiple words (all must match) or explicit field prefixes like caption:bird.
The search runs entirely in DuckDB against the database — no photo files are opened. Disk I/O only starts afterwards, when the ribbon loads thumbnails (from the cache if you've viewed them before).







**Search syntax (labelled in the sidebar):**



You type Meaning 

Path: tutsch 2025

full\_path ILIKE '%tutsch%' AND full\_path ILIKE '%2025%' → your 1408 rows

Caption: woman baby

both words must appear in the caption → your 22 rows

Caption: woman|baby

either word appears (OR)

Caption: woman|dog baby

(woman OR dog) AND baby — OR binds tighter than space-AND within a group

Path: tutsch and Caption: woman

both fields must match (fields are ANDed)

Tags: bird

matches the tag list (flattened to a string)

Any empty field is ignored. Press Enter in any field to run, Esc or Clear search to reset. The logic is unit-tested against DuckDB 2.0.0 (AND within field, OR via |, cross-field AND, tag matching).



One caveat: | is a plain separator, not a full expression language — you can't write a | b AND c and expect the AND to distribute across the OR; each |-separated group is evaluated independently and OR'ed. If you ever need real boolean logic (parentheses, mixed precedence), tell me and I'll wire in a proper expression parser.

