# embed.py
# Changed run to batch images
import numpy as np
import open_clip
import torch
from PIL import Image
from tqdm import tqdm

from common import (
    connect, pending_photos, split_path, status,
    Updater, UPDATE_EMBED_SQL, UPDATE_ERROR_SQL,
)

EMBED_MODEL = "ViT-B-32-quickgelu"
EMBED_PRETRAINED = "openai"
MODEL_BATCH = 32   # images per forward pass
THREADS = 8        # physical cores


def load_model():
    torch.set_num_threads(THREADS)
    model, _, preprocess = open_clip.create_model_and_transforms(
        EMBED_MODEL, pretrained=EMBED_PRETRAINED
    )
    model.eval()
    return model, preprocess


def run(con, model, preprocess) -> int:
    done = 0
    w_emb = Updater(con, UPDATE_EMBED_SQL)
    w_err = Updater(con, UPDATE_ERROR_SQL)
    pbar = tqdm(desc="embedding", unit="img")
    while True:
        rows = pending_photos(con, "embedding", MODEL_BATCH)
        if not rows:
            break
        tensors, results = [], []
        for (full_path,) in rows:
            try:
                with Image.open(full_path).convert("RGB") as img:
                    tensors.append(preprocess(img))
                results.append((full_path, None))
            except Exception as exc:
                results.append((full_path, f"embed: {exc}"))
        embs = None
        if tensors:
            with torch.no_grad():
                embs = model.encode_image(torch.stack(tensors))
            embs = (embs / embs.norm(dim=-1, keepdim=True)).float().numpy()
        k = 0
        for full_path, err in results:
            if err is None:
                w_emb.add([embs[k].tolist(), f"{EMBED_MODEL}/{EMBED_PRETRAINED}", full_path])
                k += 1
            else:
                w_err.add([err, full_path])
            done += 1
            pbar.update(1)
        w_emb.flush()
        w_err.flush()
    pbar.close()
    return done


if __name__ == "__main__":
    con = connect()
    model, preprocess = load_model()
    print(f"embedded {run(con, model, preprocess)} photos")
    status(con)
    con.close()