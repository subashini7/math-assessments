---
name: mark-paper
description: Mark a photo of a completed math practice sheet dropped in math-assessments/inbox/. Reads the answers, marks them against the spec, diagnoses the wrong ones from the child's working, and updates the per-component skill record. Use whenever a new picture is added to the inbox, or when asked to mark, grade or score a paper or test.
---

# Mark a paper from the inbox

Work in `math-assessments/`, with the project venv `.venv/bin/python` as `$V`
(create it with `python3 -m venv .venv && .venv/bin/pip install -r requirements.txt`).

No model or API key is involved. Alignment and cropping are OpenCV; marking is
arithmetic against the test spec; **you** do the reading, from the cropped images.

## 1. Prepare

```
$V prepare_inbox.py
```

It hashes each new photo, finds the orientation itself, decodes the QR and crops
every answer and working region. Already-recorded photos are skipped; `--force`
redoes one.

Two routes, and which one you get matters:

- **`answer_boxes.png` written** — the reliable route. Each answer is cropped
  away from its question. Read this.
- **`top.jpg` / `bottom.jpg` only** — the QR could not be read, so the page is
  shown as two halves. Still workable, but you are reading answers with their
  questions visible, which is the condition that produces misreadings. Be
  correspondingly careful, and say in your summary that this paper took the
  fallback route.

If it falls back, check why before accepting it: the QR may be **written over**
(the child uses that margin as scratch space) or **out of focus**. Neither is
fixable in software. If instead the page is simply upside down and has no
readable QR, add an entry to `inbox/orientation.json` keyed on any part of the
filename, then `--force`:

```json
{"Test_B": "mirror,180,ccw"}
```

Steps are comma-separated from `mirror`, `cw`, `ccw`, `180`.

## 2. Read the answers

Read `cache/prepared/<sha1>/answer_boxes.png` (or the two halves).

**Transcribe exactly what is on the page.** Do not correct, complete or tidy.
A missing decimal point, a dropped zero or a wrong unit is the information being
collected — if you normalise it away, the record is worse than useless because it
reports a clean sheet for a child who is struggling.

Before recording, **magnify anything ambiguous** rather than guessing:

```
$V -c "
import cv2
im=cv2.imread('cache/prepared/<sha1>/C5.png')
cv2.imwrite('/tmp/zoom.png', cv2.resize(im,None,fx=3,fy=3,interpolation=cv2.INTER_CUBIC))"
```

Known traps on these papers, all of which have actually occurred:

- **This child writes decimal points as commas.** `3,75` is 3.75, not 375.
  Checking the working settles it.
- `$0.9` and `$0.a` look identical in the answer box. The **working crop**
  resolves it — the child's own working ended `= 0.9`.
- A closed `0` can read as `3`. Magnify.
- A black wedge in a crop means that part of the page was never photographed.
  Say so; do not guess what was under it.

## 3. Record and mark

```
$V record_paper.py <sha1> --readings '{"C1":"18","C2":"0.4", ...}'
```

The spec supplies the correct answers, accepted forms, unit rules, standards and
known wrong answers, so marking is pure code. For a paper whose QR did not
decode, pass `--spec tests/Math_Practice_Test_<X>.json`. For letters A–J the
specs are under `tests/legacy/v<N>/`. Pick one whose questions match the photo;
the version printed in the sheet's footer says which.

Use `--unsure C7` for genuinely ambiguous handwriting. Those are held out of the
skill record until a person confirms them, rather than counted as evidence.

## 4. Diagnose what the code cannot

Anything printed as `NEEDS A DIAGNOSIS` has no stored explanation. Read its
working crop (`<id>_working.png`) and write what the page shows:

```
$V record_paper.py <sha1> --spec <spec> --diagnose '{"C1":"..."}'
```

**Check the code's diagnoses too, do not just accept them.** They are matched on
the final *value*, and the same wrong value can be reached by different routes.
On real papers the stored explanation was wrong twice in three cases:

- `6.24` was attributed to "lost a hundredth carrying"; the working showed the
  child copied `2.85` as `2.84` and then added correctly — a transcription slip.
- `12` was attributed to "worked out 4 ÷ 1/3"; the working showed `3/1 × 4/1`,
  i.e. flipping the dividend instead of the divisor.

Where the working contradicts the stored reason, overwrite it with `--diagnose`.
The diagnosis decides what gets taught next, so a plausible-but-wrong one is
worse than none.

Name the step, not the topic: "subtracted without borrowing across the zeros" is
useful; "struggles with decimals" is not.

**Do not re-run `--readings` after attaching diagnoses** unless a reading
changed — diagnoses only survive when the reading is unchanged.

## 5. Report and update the record

```
$V skills.py
```

This rewrites `cache/graph.txt`, `cache/graph.svg` and `cache/graph_by_grade.svg`.

Tell the person, in this order:

1. **The score**, and each wrong answer: what the child wrote, what was expected,
   and what the working shows went wrong.
2. **Which were not really skill failures** — a units-only slip, a copying slip,
   a blank, or a times-table error inside a correct method. These count as wrong
   in the tally but mean something different for teaching, and the distinction
   gets lost if you do not draw it.
3. **What changed in the record** — any skill that moved to weak or mastered, and
   whether a prerequisite walk was triggered.
4. Point at `cache/graph.svg` for the picture, and at the paper's review image
   `cache/reviews/Test_<X>_<sha1>.png`. That image has one row per question:
   right or wrong, reading against expected, skill and standard, the diagnosis
   and its source, and the answer-box crop when the QR route was used.
   `record_paper.py` rewrites it on every `--readings` and `--diagnose`, so
   look at it after the last diagnosis. `$V review_card.py` regenerates all of
   them.

Keep it short. Do not restate the whole record; say what moved.
