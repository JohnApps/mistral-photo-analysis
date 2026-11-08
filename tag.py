# tag.py
# batch images
#
import time

import open_clip
import torch
from PIL import Image
from tqdm import tqdm

from common import (
    connect, pending_photos, status,
    Updater, UPDATE_TAGS_SQL, UPDATE_ERROR_SQL,
)
from embed import EMBED_MODEL, EMBED_PRETRAINED, MODEL_BATCH, THREADS, load_model

CANDIDATE_TAGS = [
    "people", "face", "child", "group photo", "pet", "dog", "cat",
    "bird", "animal", "landscape", "mountain", "beach", "ocean", "lake",
    "forest", "flower", "plant", "food", "meal", "restaurant", "drink",
    "building", "city", "street", "car", "vehicle", "bicycle", "train",
    "airplane", "boat", "sunset", "sunrise", "night", "snow", "rain",
    "waterfall", "bridge", "portrait", "wedding", "party", "birthday",
    "concert", "sport", "swimming", "hiking", "document", "screenshot",
    "meme", "art", "drawing", "text", "map", "indoor", "outdoor",
]

THRESHOLD = 0.22


def run(con, model, preprocess, text_emb) -> int:
    done = 0
    w_tags = Updater(con, UPDATE_TAGS_SQL)
    w_err = Updater(con, UPDATE_ERROR_SQL)
    pbar = tqdm(desc="tagging", unit="img")
    while True:
        rows = pending_photos(con, "tags", MODEL_BATCH)
        if not rows:
            break
        tensors, results = [], []
        for (full_path,) in rows:
            try:
                with Image.open(full_path).convert("RGB") as img:
                    tensors.append(preprocess(img))
                results.append((full_path, None))
            except Exception as exc:
                results.append((full_path, f"tags: {exc}"))
        all_tags = []
        if tensors:
            with torch.no_grad():
                img_emb = model.encode_image(torch.stack(tensors))
                img_emb = img_emb / img_emb.norm(dim=-1, keepdim=True)
                scores = img_emb @ text_emb.T
            for s in scores:
                hits = s > THRESHOLD
                tags = [CANDIDATE_TAGS[i] for i in hits.nonzero().flatten().tolist()]
                if not tags:
                    tags = [CANDIDATE_TAGS[int(s.argmax())]]
                all_tags.append(tags)
        k = 0
        for full_path, err in results:
            if err is None:
                w_tags.add([all_tags[k], f"{EMBED_MODEL}/{EMBED_PRETRAINED}", full_path])
                k += 1
            else:
                w_err.add([err, full_path])
            done += 1
            pbar.update(1)
        w_tags.flush()
        w_err.flush()
    pbar.close()
    return done


if __name__ == "__main__":
    con = connect()
    model, preprocess = load_model()
    tokenizer = open_clip.get_tokenizer(EMBED_MODEL)
    with torch.no_grad():
        text = tokenizer(CANDIDATE_TAGS)
        text_emb = model.encode_text(text)
        text_emb = text_emb / text_emb.norm(dim=-1, keepdim=True)
    t0 = time.perf_counter()
    n = run(con, model, preprocess, text_emb)
    secs = time.perf_counter() - t0
    rate = f" ({n / secs:.1f} img/s)" if secs > 0 and n else ""
    print(f"tagged {n} new photos; skipped already-tagged")
    print(f"runtime[tag]: {secs:.1f}s for {n} photos{rate}")
    status(con)
    con.close()