---
name: new-assessment
description: Generate the next printable math practice test for math-assessments, mixing untested foundations, skills the child has got wrong, and a few harder ones whose prerequisites are now mastered. Use when asked to create, generate or make a new test, assessment, practice sheet or paper.
---

# Generate the next assessment

Work in `math-assessments/`, with the project venv `.venv/bin/python` as `$V`
(create it with `python3 -m venv .venv && .venv/bin/pip install -r requirements.txt`).

## 1. Ask the record what to cover

```
$V skills.py --plan                # one sheet
$V skills.py --plan --sheets 3     # a batch of 2 or 3 sheets
```

When asked for more than one sheet, plan them as **one batch** with
`--sheets N`, not as separate runs: a separate run sees the same marked record
and returns the same plan. The batch is planned as N × 10 picks with the quota
scaled, so no standard appears twice in it, then dealt across the sheets so each
gets its share of failures, coverage and readiness. Write each sheet's questions
from its own section of the output, one new letter per sheet.

This weighs four things, with a quota so none crowds the others out:

- **failure** (4 of 10) — wrong before. A standard wrong twice also pulls in what it rests on.
- **coverage** (3 of 10) — in the grade roster, never asked. Grade 5 first, so gaps are found before they are inherited; grade 6 once grade 5 runs short, rotating through the domains. A grade-6 standard whose known grade-5 foundations are not mastered is held back here too.
- **readiness** (1 of 10) — a never-asked grade 6/7 standard whose grade-5 foundations are mastered.
- **review** (2 of 10) — spaced repetition. A skill whose last answer was right comes back once its gap is up: 2 days after one right answer in a row, then 7, 21 and 60 days. Most overdue first. Ask it fresh (new numbers, same skill), not as a copy of the last question.

Unused slots in one bucket go to the others. Mastered means right at least twice
with no mistakes, or **three right in a row since the last mistake** - so one old
slip no longer holds a skill, and everything gated on it, back for good.
Planning uses each paper's `date` (set by `record_paper.py` from the camera
app's file name, or the marking day).

It also prints what is **held back** and why. Honour that: a standard whose
foundations are still shaky measures the foundation, not the new skill.

`$V skills.py --coverage 5` shows how much of a grade has been touched at all.

Do not override the plan silently. If you depart from it, say so and why.

**Check *why* a standard is weak before aiming questions at it.** A standard can
be weak on failures that are not about the mathematics. `5.MD.C.5` reached 0/3
with the volume arithmetic correct every time and only the units missing — a
test of volume computation would measure something already demonstrated three
times. Read the diagnoses in `cache/papers/*.json`, and if the failures are
units-only, a copying slip or a blank, target the actual gap instead and say so.

## 2. Write the questions

The generator is **not** automatic — it has no templates, only hand-written
question instances. You write them. For each pick from the plan, add a `Q(...)`
to a new `test_x()` function in `make_tests.py`.

Rules that the build enforces or that experience has imposed:

- **Compute every answer in code**, never type it: `v = 46 * 27` then `str(v)`.
  The build asserts the answers, so a hand-arithmetic slip cannot ship.
- **Give each question a skill key** in `SK` carrying the CCSS code and the
  Learning Commons component UUIDs. Aim at the *component* the plan names, not
  just the standard — `6.NS.B.3` bundles four operations, and testing division
  when subtraction is the weak one wastes the question.
  `cache/components.json` holds the components for every grade 5–7 roster
  standard. Look them up there first. Only a standard new to the syllabus needs
  the Learning Commons connector; add what it returns to the cache.
- **Only list wrong answers you can derive.** A guessed one attaches a confident
  explanation to something the child never did. Leaving the slot empty is fine —
  the question then asks for a reading of the working, which is more reliable.
  Prefer this child's *observed* mistakes, which are in `cache/papers/*.json`.
- The build refuses if a "wrong" answer collides with an accepted one. It has
  already caught a real error this way.

**Picture questions.** `Q(..., figure={...})` draws a small figure at the top
right of the question box: `cubes` (a stack of unit cubes, l × w × h), `shapes`
(up to four labelled polygons), `lineplot` (x marks over a fraction number line)
or `grid` (a first-quadrant grid with labelled points). The answer box stays
where it always is, so the photo pipeline is unchanged. Compute the answer from
the figure's own data (`is_parallelogram`, `cubes_visible`), never from looking
at the drawing. "Write the letters" answers are marked as a set, so "C, A" and
"A and C" both match "A, C". Keep picture-question text short: the text column
is narrow and long wording runs into the Answer label. Check the preview.

Picture questions take a **written** answer: they test reading a line plot or a
grid, not making one. Give such a question only the components a written answer
can show, so the record does not claim the drawing skill was tested.

Standards whose only meaningful question needs a drawn answer (drawing polygons
on a grid, nets, displaying data in plots) are flagged `needs_diagram` in
`cache/syllabus.json` and excluded from coverage. Do not word around them.

## 3. Generate

```
$V make_tests.py            # writes tests/Math_Practice_Test_<X>.pdf/.json
```

Give each new sheet the **next unused letter**. Each sheet is written once, flat
in `tests/`, with the QR payload `mpt:test=<X>&h=<fingerprint>`. The
fingerprint covers what page 1 prints (title, question text, box layout), so:

- Re-running is safe. A sheet whose page 1 is unchanged is rewritten in place
  ("refreshed"), so new component ids or newly observed wrong answers reach
  its spec without invalidating the printed copy. Nothing to delete by hand.
- If a question's wording or the layout would change, the build refuses and
  writes nothing. The sheet may already be printed: put the new questions
  under a new letter instead of editing the old one.
- Letters in `tests/legacy/` (A–J, from the earlier per-run folders with
  `&v=<N>` payloads) are never regenerated. Their specs stay there so those
  QR codes still resolve, with the box layout they were printed with.

Render a preview and look at it:
`pdftoppm -png -r 110 tests/Math_Practice_Test_<X>.pdf cache/previews/Test_<X>`

Check page 1 (the questions) and page 2 (the answer key, which also names the
skill and CCSS code per question).

## 4. Report

Say which standard and component each question targets and why it is there —
failure, coverage or readiness. Name anything from the plan you could **not**
cover and the reason. Give the paths to the PDF and the preview.
