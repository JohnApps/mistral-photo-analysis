# similar.py
# take care of mixed case path and file names
#
import sys

import duckdb

# Normalized comparison: case-insensitive AND slash-insensitive
MATCH_SQL = """
lower(replace(full_path, '\\', '/')) = lower(replace(?, '\\', '/'))
"""


def main():
    if len(sys.argv) < 2:
        print('usage: python similar.py "<full_path or partial path>" [n]')
        print('example: python similar.py "O:\\Bilder\\1-D7100\\_JDA9525.jpg" 30')
        sys.exit(1)

    target = sys.argv[1]
    n = int(sys.argv[2]) if len(sys.argv) > 2 else 30
    con = duckdb.connect("photos.duckdb", read_only=True)

    # 1. Resolve the target: case- and slash-insensitive match on full_path.
    hits = con.execute(
        "select full_path, embedding is not null from photos where " + MATCH_SQL,
        [target],
    ).fetchall()
    if not hits:
        # substring match to help the user find the right spelling
        fuzzy = con.execute(
            "select full_path from photos where contains("
            "lower(replace(full_path, '\\', '/')), "
            "lower(replace(?, '\\', '/'))) limit 20",
            [target],
        ).fetchall()
        if fuzzy:
            print("No exact match, but these paths contain that text:")
            for (p,) in fuzzy:
                print("  ", p)
            print("-> retry with one of the paths above (case does not matter)")
        else:
            print(f"NOT IN TABLE: {target}")
            print("-> run: python scan.py <folder containing the photo>")
        sys.exit(1)
    if len(hits) > 1:
        print("Multiple photos match that path:")
        for p, _ in hits:
            print("  ", p)
        sys.exit(1)

    exact_path, has_embedding = hits[0]
    if not has_embedding:
        print(f"NO EMBEDDING YET: {exact_path}")
        print("-> run: python embed.py")
        sys.exit(1)

    # 2. Find the most similar photos.
    rows = con.execute(
        """
        select full_path, caption,
               array_cosine_similarity(embedding,
                 (select embedding from photos where """ + MATCH_SQL + """)) as score
        from photos
        where embedding is not null
        order by score desc nulls last
        limit ?
        """,
        [target, n],
    ).fetchall()

    print(f"target: {exact_path}")
    print(f"most similar {len(rows)} photos (score 1.0 = identical):")
    for full_path, caption, score in rows:
        print(f"{score:.4f}  {full_path}  | {caption or ''}")


if __name__ == "__main__":
    main()