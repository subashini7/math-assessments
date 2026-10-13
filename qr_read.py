"""Decode the sheet's QR, trying progressively harder before giving up.

Shared by `prepare_inbox.py` and `align_and_crop.py` so they cannot disagree
about whether a sheet has a readable code - they did, and the stricter one sent
a perfectly good sheet down the whole-page path.

A failed decode is expensive: the page is then read whole rather than as cropped
answer boxes, which is measurably worse. The printed QR is only 62pt, so in a
photo taken from any distance it lands on too few pixels for the detector;
upscaling alone recovers it.

Decoding is orientation-invariant - OpenCV reads a mirrored, rotated or
upside-down QR happily - so this works on the raw photo, before any rotation.

What it cannot fix, both seen on real sheets: a code the child has written over
(the margin beside it invites scratch working), and one too far out of focus to
resolve its modules.
"""
import cv2
import numpy as np


def _candidates(bgr):
    grey = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
    clahe = cv2.cvtColor(cv2.createCLAHE(3.0, (8, 8)).apply(grey), cv2.COLOR_GRAY2BGR)
    sharp = cv2.cvtColor(
        cv2.addWeighted(grey, 1.8, cv2.GaussianBlur(grey, (0, 0), 3), -0.8, 0),
        cv2.COLOR_GRAY2BGR)
    yield "as-is", bgr
    for scale in (2, 3):
        for label, src in (("plain", bgr), ("contrast", clahe), ("sharpened", sharp)):
            yield (f"{label} x{scale}",
                   cv2.resize(src, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC))


def decode(bgr, verbose=True):
    """(payload, points) in the ORIGINAL image's coordinates, or (None, None)."""
    det = cv2.QRCodeDetector()
    for label, img in _candidates(bgr):
        try:
            val, pts, _ = det.detectAndDecode(img)
        except cv2.error:
            continue
        if val and pts is not None:
            scale = img.shape[1] / float(bgr.shape[1])
            if verbose and label != "as-is":
                print(f"    QR needed {label} to decode", flush=True)
            return val, pts.reshape(-1, 2).astype(np.float32) / scale
    return None, None


def payload(bgr, verbose=True):
    return decode(bgr, verbose)[0]
