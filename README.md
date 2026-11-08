

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

