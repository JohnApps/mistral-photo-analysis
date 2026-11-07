# cli.py
import argparse

from db import connect
from scan import scan_disks


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="photo-analysis",
        description="Local photo analysis pipeline: EXIF + CLIP embeddings + "
        "CLIP zero-shot tags + BLIP2 captions, stored in DuckDB.",
    )
    parser.add_argument("--db", default="photos.duckdb", help="DuckDB database file")
    sub = parser.add_subparsers(dest="command", required=True)

    p_scan = sub.add_parser("scan", help="index JPGs under one or more roots")
    p_scan.add_argument("roots", nargs="+", help="e.g. E:\\ D:\\Photos")

    p_all = sub.add_parser("all", help="scan roots, then tag + embed + caption")
    p_all.add_argument("roots", nargs="*", help="roots to scan first (optional)")

    sub.add_parser("embed", help="compute CLIP embeddings for pending photos")
    sub.add_parser("tag", help="assign zero-shot CLIP tags for pending photos")
    sub.add_parser("caption", help="generate BLIP2 captions for pending photos")
    sub.add_parser("status", help="show processing counts")

    args = parser.parse_args(argv)
    con = connect(args.db)

    if args.command == "scan":
        n = scan_disks(con, args.roots)
        print(f"indexed {n} photos")
    elif args.command == "all":
        from .caption import run_captions
        from .embed import run_embeddings
        from .tag import run_tags

        if args.roots:
            n = scan_disks(con, args.roots)
            print(f"indexed {n} photos")
        run_embeddings(con)
        run_tags(con)
        run_captions(con)
    elif args.command == "embed":
        from .embed import run_embeddings

        print(f"embedded {run_embeddings(con)} photos")
    elif args.command == "tag":
        from .tag import run_tags

        print(f"tagged {run_tags(con)} photos")
    elif args.command == "caption":
        from .caption import run_captions

        print(f"captioned {run_captions(con)} photos")

    status(con)
    con.close()


def status(con):
    row = con.execute(
        """
        SELECT
            count(*) AS total,
            count(embedding) AS with_embedding,
            count(tags) AS with_tags,
            count(caption) AS with_caption,
            count(*) FILTER (WHERE error IS NOT NULL AND error <> '') AS errors
        FROM photos
        """
    ).fetchone()
    print(
        f"total={row[0]} embedded={row[1]} tagged={row[2]} "
        f"captioned={row[3]} errors={row[4]}"
    )


if __name__ == "__main__":
    main()