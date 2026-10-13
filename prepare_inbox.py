"""Get images in `inbox/` ready for Claude to read. No API calls, no model.

    python3 prepare_inbox.py

For each image not already recorded: fix the orientation, and either
  - QR sheet: register it on the printed answer boxes and cut out every answer
    and working region (`align_and_crop.py`), or
  - anything else: write upright, legible halves of the page,
then print the paths to read.

Claude reads those files directly and writes the result with `record_paper.py`.
"""
import argparse, hashlib, json, subprocess, sys
from pathlib import Path

from PIL import Image, ImageOps

HERE = Path(__file__).parent
INBOX = HERE / "inbox"
PAPERS = HERE / "cache" / "papers"
PREP = HERE / "cache" / "prepared"
EXTS = (".jpg", ".jpeg", ".png", ".heic", ".webp")
# A `corrected_` copy is a second version of a paper that has already been
# worked over, so counting it as well would record the same questions twice and
# make one mistake look like a pattern. Skipped unless explicitly asked for.
SKIP_PREFIX = "corrected_"


def sha1(path):
    return hashlib.sha1(Path(path).read_bytes()).hexdigest()[:16]


def orient(path, transform=None):
    im = ImageOps.exif_transpose(Image.open(path)).convert("RGB")
    for step in [s.strip() for s in (transform or "").split(",") if s.strip()]:
        if step == "mirror":
            im = im.transpose(Image.FLIP_LEFT_RIGHT)
        elif step == "cw":
            im = im.rotate(-90, expand=True)
        elif step == "ccw":
            im = im.rotate(90, expand=True)
        elif step == "180":
            im = im.rotate(180, expand=True)
    return im


# Every way a photo can be held, cheapest first. Photo Booth mirrors, phones
# rotate, and a sheet on a desk can be any way up.
DIHEDRAL = ["", "mirror,ccw", "mirror,cw", "mirror,180", "mirror",
            "ccw", "cw", "180"]


def find_orientation(path, out, base=None):
    """Work out which transform makes this sheet register, by trying them.

    Orientation used to be recorded by hand in inbox/orientation.json, which
    meant a person had to look at every photo first. A QR sheet can settle it
    itself: only the correct orientation both decodes the code and passes
    align_and_crop's row checks. Mirroring matters - a mirrored QR is not a
    valid QR, and a marginal one will not survive it, so trying the raw image
    alone is not enough.
    """
    order = ([base] if base else []) + [d for d in DIHEDRAL if d != base]
    for t in order:
        im = orient(path, t)
        qr = read_qr(im)          # must be read per orientation: a mirrored QR
        if not qr:                # often will not decode at all
            continue
        probe = out / "_probe.jpg"
        im.save(probe, "JPEG", quality=92)
        r = subprocess.run([sys.executable, "align_and_crop.py", str(probe), str(out),
                            record_spec_dir(qr)], capture_output=True, text=True, cwd=HERE)
        probe.unlink(missing_ok=True)
        if r.returncode == 0:
            return t, qr
    return base, None


def transform_for(name, overrides):
    for key, t in (overrides or {}).items():
        if key in name:
            return t
    return None


def record_spec_dir(qr):
    """Folder holding the spec whose QR payload matches this photo."""
    import record_paper
    spec = record_paper.find_spec({"qr": qr})
    if spec is None:
        print(f"    no spec in tests/ matches {qr!r}; generate it, "
              "or pass --spec to record_paper.py later")
    return str(spec.parent) if spec else str(HERE)


def read_qr(im):
    """Payload of the sheet's QR, or None. See qr_read for why it tries hard."""
    try:
        import cv2, numpy as np, qr_read
        return qr_read.payload(cv2.cvtColor(np.array(im), cv2.COLOR_RGB2BGR))
    except Exception:
        return None


def write_halves(im, out, width=1500, overlap=0.06):
    """Two overlapping halves, upright and large enough to read digits.

    A whole A4 page scaled to fit one view loses the decimal points; that is
    what makes handwriting ambiguous, so split rather than shrink.
    """
    w, h = im.size
    scale = width / float(w)
    im = im.resize((width, int(h * scale)))
    w, h = im.size
    cut = int(h * (0.5 + overlap))
    parts = [("top", im.crop((0, 0, w, cut))),
             ("bottom", im.crop((0, int(h * (0.5 - overlap)), w, h)))]
    paths = []
    for name, part in parts:
        p = out / f"{name}.jpg"
        part.save(p, "JPEG", quality=92)
        paths.append(p)
    return paths


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--inbox", default=str(INBOX))
    ap.add_argument("--transform", help="orientation fix for every image, e.g. 'mirror,cw'")
    ap.add_argument("--force", action="store_true", help="re-prepare images already recorded")
    ap.add_argument("--include-corrected", action="store_true",
                    help=f"also process {SKIP_PREFIX}* images, which are skipped by default")
    ap.add_argument("--width", type=int, default=1500, help="pixel width of each half")
    args = ap.parse_args()

    inbox = Path(args.inbox)
    inbox.mkdir(parents=True, exist_ok=True)
    PAPERS.mkdir(parents=True, exist_ok=True)
    overrides = {}
    omap = inbox / "orientation.json"
    if omap.exists():
        overrides = json.loads(omap.read_text())

    images = sorted(p for p in inbox.iterdir() if p.suffix.lower() in EXTS)
    skipped = [p for p in images if p.name.startswith(SKIP_PREFIX)]
    if skipped and not args.include_corrected:
        images = [p for p in images if not p.name.startswith(SKIP_PREFIX)]
        print(f"skipping {len(skipped)} {SKIP_PREFIX}* image(s): "
              + ", ".join(p.name for p in skipped)
              + "  (--include-corrected to use them)")
    if not images:
        print(f"No images to process in {inbox}.")
        return

    todo = []
    for path in images:
        digest = sha1(path)
        if (PAPERS / f"{digest}.json").exists() and not args.force:
            print(f"- {path.name}: already recorded ({digest}.json)")
            continue
        todo.append((path, digest))
    if not todo:
        print("\nNothing new. Use --force to prepare an image again.")
        return

    print()
    for path, digest in todo:
        t = args.transform or transform_for(path.name, overrides)
        im = orient(path, t)
        out = PREP / digest
        out.mkdir(parents=True, exist_ok=True)
        # Always search: the raw photo may not decode at all, and that is
        # precisely the case where the orientation needs finding.
        found, qr = find_orientation(path, out, t)
        if qr:
            if found != t:
                print(f"    orientation {found!r} found automatically"
                      f"{' (override said ' + repr(t) + ')' if t else ''}", flush=True)
            t, im = found, orient(path, found)
        else:
            qr = read_qr(im)
        (out / "meta.json").write_text(json.dumps(
            {"source": path.name, "sha1": digest, "qr": qr, "transform": t,
             "size": list(im.size)}, indent=2))
        print(f"=== {path.name}  [{digest}]  {im.size[0]}x{im.size[1]}"
              f"{'  transform=' + t if t else ''}")

        if qr:
            print(f"    QR: {qr}")
            im.save(out / "upright.jpg", "JPEG", quality=92)
            specdir = record_spec_dir(qr)
            r = subprocess.run([sys.executable, "align_and_crop.py",
                                str(out / "upright.jpg"), str(out), specdir],
                               capture_output=True, text=True, cwd=HERE)
            if r.returncode == 0:
                print(f"    cropped by align_and_crop.py (no model involved)")
                print(f"    READ: {out/'answer_boxes.png'}   (all 10 answers)")
                print(f"    READ: {out}/<id>_working.png     (working, for wrong answers)")
            else:
                print(f"    align_and_crop failed: {(r.stderr or r.stdout).strip().splitlines()[-1:]}")
                for p in write_halves(im, out, args.width):
                    print(f"    READ: {p}")
        else:
            for p in write_halves(im, out, args.width):
                print(f"    READ: {p}")
        print(f"    then: python3 record_paper.py {digest} <<'JSON'  ...  JSON")

    print("\nIf a page is upside down or mirrored, set it in inbox/orientation.json "
          "and re-run with --force.")


if __name__ == "__main__":
    main()
