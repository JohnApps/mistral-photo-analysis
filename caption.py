# caption.py
import time

import torch
from PIL import Image
from tqdm import tqdm
from transformers import Blip2Processor, Blip2ForConditionalGeneration

from common import (
    connect, pending_photos, status,
    Updater, UPDATE_CAPTION_SQL, UPDATE_ERROR_SQL,
)
from embed import THREADS

CAPTION_MODEL = "Salesforce/blip2-opt-2.7b"
MODEL_BATCH = 4  # BLIP2 is heavy; keep small on CPU


def run(con, processor, model) -> int:
    done = 0
    w_cap = Updater(con, UPDATE_CAPTION_SQL)
    w_err = Updater(con, UPDATE_ERROR_SQL)
    pbar = tqdm(desc="captioning", unit="img")
    while True:
        rows = pending_photos(con, "caption", MODEL_BATCH)
        if not rows:
            break
        images, results = [], []
        for (full_path,) in rows:
            try:
                images.append(Image.open(full_path).convert("RGB"))
                results.append((full_path, None))
            except Exception as exc:
                results.append((full_path, f"caption: {exc}"))
        captions = []
        if images:
            inputs = processor(images=images, return_tensors="pt", padding=True)
            with torch.no_grad():
                out = model.generate(**inputs, max_new_tokens=40)
            captions = processor.batch_decode(out, skip_special_tokens=True)
        k = 0
        for full_path, err in results:
            if err is None:
                w_cap.add([captions[k].strip(), CAPTION_MODEL, full_path])
                k += 1
            else:
                w_err.add([err, full_path])
            done += 1
            pbar.update(1)
        for img in images:
            img.close()
        w_cap.flush()
        w_err.flush()
    pbar.close()
    return done


if __name__ == "__main__":
    torch.set_num_threads(THREADS)
    con = connect()
    processor = Blip2Processor.from_pretrained(CAPTION_MODEL)
    model = Blip2ForConditionalGeneration.from_pretrained(
        CAPTION_MODEL, torch_dtype=torch.float32
    )
    model.eval()
    t0 = time.perf_counter()
    n = run(con, processor, model)
    secs = time.perf_counter() - t0
    rate = f" ({n / secs:.1f} img/s)" if secs > 0 and n else ""
    print(f"captioned {n} new photos; skipped already-captioned")
    print(f"runtime[caption]: {secs:.1f}s for {n} photos{rate}")
    status(con)
    con.close()