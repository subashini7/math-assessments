"""Render a marked paper as one image a parent can review at a glance.

    python3 review_card.py                 # every paper in cache/papers
    python3 review_card.py <sha1> [...]    # just these

One row per question: right or wrong, what was read against what was expected,
the skill and standard it checks, and the diagnosis with where it came from.
When the paper went through the QR route the cropped answer box is shown too,
so a misreading can be caught without opening the photo.

record_paper.py calls `render` every time it writes a paper, so the card always
matches the record, including diagnoses attached afterwards.
"""
import json, sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

import prereq, skills

HERE = Path(__file__).parent
PAPERS = HERE / "cache" / "papers"
PREP = HERE / "cache" / "prepared"
OUT = HERE / "cache" / "reviews"

W = 1900
PAD = 32
COLS = {"num": 32, "status": 90, "crop": 210, "text": 470, "skill": 830, "diag": 1330}
CROP_W, CROP_H = 240, 90

INK = (31, 41, 55)
MUTED = (107, 114, 128)
LINE = (220, 224, 230)
NAVY = (31, 58, 95)
RIGHT = (22, 128, 61)
WRONG = (185, 28, 28)
HELD = (180, 120, 0)
RIGHT_BG = (240, 253, 244)
WRONG_BG = (254, 242, 242)
HELD_BG = (255, 251, 235)


def _font(size, bold=False):
    for name in (("Arial Bold.ttf" if bold else "Arial.ttf"), "Arial Unicode.ttf"):
        for d in ("/System/Library/Fonts/Supplemental", "/Library/Fonts"):
            p = Path(d) / name
            if p.exists():
                return ImageFont.truetype(str(p), size)
    return ImageFont.load_default(size)


F_TITLE, F_SUB = _font(34, True), _font(20)
F_HEAD, F_BODY, F_BOLD, F_SMALL = _font(17, True), _font(18), _font(18, True), _font(15)


def _wrap(text, font, width):
    """Wrap to a pixel width rather than a character count."""
    out = []
    for para in str(text).split("\n"):
        line = ""
        for word in para.split():
            trial = f"{line} {word}".strip()
            if font.getlength(trial) <= width or not line:
                line = trial
            else:
                out.append(line)
                line = word
        out.append(line)
    return out


def _status(q):
    if q.get("right") is True:
        return "RIGHT", RIGHT, RIGHT_BG
    if q.get("right") is False:
        return "WRONG", WRONG, WRONG_BG
    return "HELD", HELD, HELD_BG              # unsure reading, not yet confirmed


def _tally(r):
    return f"now {r['right']} right, {r['wrong']} wrong" if r else "now untested"


def _skill_lines(q, rec, comp):
    """What this question did to the skill record, in the record's own terms.

    Same rule as skills.record / skills.component_record: a held reading counts
    for nothing; otherwise the standard and EVERY component on the question get
    +1 right or +1 wrong. Totals are the record as it stands now, across all
    papers, so a reviewer sees where the skill ended up and not just the step.
    """
    width = W - COLS["skill"] - (W - COLS["diag"]) - 20
    held = (q.get("needs_review") and not q.get("confirmed")) or q.get("right") is None
    effect, colour = (("not counted (held)", HELD) if held else
                      ("+1 right", RIGHT) if q["right"] else ("+1 wrong", WRONG))
    code = q.get("standard", "")
    r = rec.get(code)
    lines = [(f"{code}   {effect}", F_BOLD, colour),
             (f"{_tally(r)} · {skills.status(r) if r else 'untested'}", F_SMALL, MUTED)]
    for cid in q.get("learning_component_ids") or []:
        name = prereq.component_name(cid) or q.get("skill", "")
        for i, part in enumerate(_wrap(name, F_SMALL, width - 16)):
            lines.append((("• " if i == 0 else "   ") + part, F_SMALL, INK))
        lines.append((f"   {effect} · {_tally(comp.get(cid))}", F_SMALL, colour))
    return lines


def _crop(sha1, qid):
    p = PREP / sha1 / f"{qid}.png"
    if not p.exists():
        return None
    im = Image.open(p).convert("RGB")
    im.thumbnail((CROP_W, CROP_H))
    return im


def render(paper_path):
    paper = json.loads(Path(paper_path).read_text())
    sha1 = paper.get("sha1") or Path(paper_path).stem
    qs = paper.get("questions", [])
    papers = skills.load_papers()
    rec, comp = skills.record(papers), skills.component_record(papers)

    # Lay every row out first so the canvas can be sized exactly.
    rows = []
    for q in qs:
        label, colour, bg = _status(q)
        text = _wrap(q.get("text", ""), F_BODY, COLS["skill"] - COLS["text"] - 20)
        read = q.get("reading") or "(blank)"
        answer = [("Read: ", read), ("Expected: ", q.get("expected", ""))]
        skill = _skill_lines(q, rec, comp)
        if q.get("right") is True:
            diag = ["—"]
        elif q.get("diagnosis"):
            src = {"spec": "known mistake, matched by code"}.get(
                q.get("diagnosis_source"), "read from the working")
            diag = _wrap(q["diagnosis"], F_BODY, W - PAD - COLS["diag"] - 16) + [f"[{src}]"]
        else:
            diag = ["NEEDS A DIAGNOSIS"]
        crop = _crop(sha1, q.get("id", ""))
        n_lines = max(len(text) + 2, len(skill), len(diag))
        h = max(n_lines * 24 + 24, (CROP_H + 24) if crop else 0, 70)
        rows.append((q, label, colour, bg, text, answer, skill, diag, crop, h))

    right = sum(1 for q in qs if q.get("right") is True)
    held = sum(1 for q in qs if q.get("right") is None)
    head_h = 150
    H = head_h + 40 + sum(r[-1] for r in rows) + PAD

    im = Image.new("RGB", (W, H), "white")
    d = ImageDraw.Draw(im)

    title = f"Math Practice Test {paper.get('test_id', '?')}  —  {right}/{len(qs)}"
    d.text((PAD, PAD), title, font=F_TITLE, fill=NAVY)
    sub = [f"photo: {' '.join(str(paper.get('paper', '')).split())}   ·   spec: {paper.get('spec', '')}   ·   id {sha1}"]
    route = "cropped answer boxes" if any(r[8] for r in rows) else \
        "whole half-pages (QR not read) - answers read with the questions visible"
    sub.append(f"read from: {route}" + (f"   ·   {held} held for review" if held else ""))
    for i, s in enumerate(sub):
        d.text((PAD, PAD + 48 + i * 26), s, font=F_SUB, fill=MUTED)

    y = head_h
    for key, label in (("num", "Q"), ("status", ""), ("crop", "Answer box"),
                       ("text", "Question / answer"), ("skill", "Skill record: standard, then components"),
                       ("diag", "Diagnosis")):
        d.text((COLS[key], y + 10), label, font=F_HEAD, fill=MUTED)
    y += 40
    d.line((PAD, y, W - PAD, y), fill=LINE, width=2)

    for q, label, colour, bg, text, answer, skill, diag, crop, h in rows:
        d.rectangle((PAD, y + 1, W - PAD, y + h - 1), fill=bg)
        d.rectangle((PAD, y + 1, PAD + 6, y + h - 1), fill=colour)
        ty = y + 12
        d.text((COLS["num"] + 12, ty), str(q.get("number", "")), font=F_BOLD, fill=INK)
        d.text((COLS["status"], ty), label, font=F_BOLD, fill=colour)
        if crop:
            im.paste(crop, (COLS["crop"], ty))
            d.rectangle((COLS["crop"], ty, COLS["crop"] + crop.width, ty + crop.height),
                        outline=LINE)
        else:
            d.text((COLS["crop"], ty), "(no crop)", font=F_SMALL, fill=MUTED)
        for i, line in enumerate(text):
            d.text((COLS["text"], ty + i * 24), line, font=F_BODY, fill=INK)
        ay = ty + len(text) * 24 + 4
        for i, (k, v) in enumerate(answer):
            d.text((COLS["text"], ay + i * 24), k, font=F_SMALL, fill=MUTED)
            vc = colour if k.startswith("Read") else INK
            d.text((COLS["text"] + F_SMALL.getlength(k), ay + i * 24 - 2), str(v),
                   font=F_BOLD, fill=vc)
        for i, (line, font, fill) in enumerate(skill):
            d.text((COLS["skill"], ty + i * 24), line, font=font, fill=fill)
        for i, line in enumerate(diag):
            src_line = line.startswith("[") or line == "—"
            fill = MUTED if src_line else (WRONG if line == "NEEDS A DIAGNOSIS" else INK)
            d.text((COLS["diag"], ty + i * 24), line,
                   font=F_SMALL if src_line else F_BODY, fill=fill)
        y += h
        d.line((PAD, y, W - PAD, y), fill=LINE, width=1)

    OUT.mkdir(parents=True, exist_ok=True)
    dest = OUT / f"Test_{paper.get('test_id', 'X')}_{sha1}.png"
    im.save(dest)
    return dest


def main():
    ids = sys.argv[1:]
    paths = [PAPERS / f"{i}.json" for i in ids] if ids else sorted(PAPERS.glob("*.json"))
    for p in paths:
        print("wrote", render(p))


if __name__ == "__main__":
    main()
