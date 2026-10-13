"""Record what Claude read off a prepared paper. No model, no API.

    python3 record_paper.py <sha1> --readings '{"A1": "4.415", "A2": "25.2", ...}'

For a QR sheet the spec supplies everything else: the correct answer, the
accepted forms, the unit rule, the standard, the learning components, and the
known wrong answers. So marking is pure code (`mark.py`), and the only thing
coming from a reader is the transcription.

Diagnoses for wrong answers are attached the same way once the working crops
have been read:

    python3 record_paper.py <sha1> --diagnose '{"A9": "No working shown; likely a guess"}'

Anything the spec can already explain is filled in automatically from
`common_wrong_answers`, so only the genuinely new mistakes need a reader.
"""
import argparse, json, sys
from pathlib import Path

import mark as marker

HERE = Path(__file__).parent
PAPERS = HERE / "cache" / "papers"
PREP = HERE / "cache" / "prepared"


TESTS = HERE / "tests"


def find_spec(meta, override=None):
    """The spec whose `qr_payload` is exactly what the photo's QR says.

    Current sheets sit flat in tests/ with `&h=<fingerprint>` payloads; older
    ones keep their `&v=<N>` payloads under tests/legacy/. Matching the whole
    payload rather than the letter matters because the same letter exists in
    several legacy folders, and the box layout (which the crops rely on)
    differs between them.
    """
    if override:
        return Path(override)
    qr = (meta or {}).get("qr") or ""
    if not qr:
        return None
    specs = sorted(TESTS.rglob("Math_Practice_Test_*.json"))
    hits = [f for f in specs if json.loads(f.read_text()).get("qr_payload") == qr]
    if len(hits) > 1:
        raise SystemExit(f"{len(hits)} specs claim the payload {qr!r}: "
                         + ", ".join(str(h) for h in hits))
    if not hits and "test=" in qr:
        # Some printed &v= sheets were generated into folders that were later
        # deleted. Say which specs exist for the letter rather than just failing.
        letter = qr.split("test=")[1].split("&")[0]
        same = [str(f) for f in specs if f.name == f"Math_Practice_Test_{letter}.json"]
        if same:
            print(f"    no spec has payload {qr!r}; Test {letter} exists as: {', '.join(same)}"
                  "\n    check the questions match the photo, then pass one with --spec")
    return hits[0] if hits else None


def write_card(dest):
    """Refresh the review images; the record itself never depends on them.

    Every card is redrawn, not just this paper's: the cards show each skill's
    running total, so a new paper changes the totals printed on the old ones.
    """
    try:
        import review_card
    except ImportError as e:
        print(f"(no review image: {e}; run with the venv that has Pillow)")
        return
    for p in sorted(PAPERS.glob("*.json")):
        out = review_card.render(p)
        if p == dest:
            print(f"review image -> {out}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("sha1", help="the id prepare_inbox.py printed for the image")
    ap.add_argument("--readings", help='JSON {"A1": "...", ...}; omit to read stdin')
    ap.add_argument("--diagnose", help='JSON {"A9": "why it went wrong"}')
    ap.add_argument("--unsure", nargs="*", default=[],
                    help="question ids whose handwriting is genuinely ambiguous; "
                         "these are held out of the skill record until confirmed")
    ap.add_argument("--spec", help="spec JSON (default: from the QR payload)")
    ap.add_argument("--note")
    args = ap.parse_args()

    meta_path = PREP / args.sha1 / "meta.json"
    meta = json.loads(meta_path.read_text()) if meta_path.exists() else {}
    dest = PAPERS / f"{args.sha1}.json"
    paper = json.loads(dest.read_text()) if dest.exists() else {}

    spec_path = find_spec(meta, args.spec)
    if spec_path is None:
        sys.exit("No spec for this paper. Pass --spec, or record a non-QR paper with "
                 "--readings plus explicit question text (not supported yet).")
    spec = json.loads(spec_path.read_text())

    # --- diagnoses only: attach to an existing record and stop -------------
    if args.diagnose and not args.readings:
        if not paper:
            sys.exit(f"No record at {dest} yet; record the readings first.")
        given = json.loads(args.diagnose)
        for q in paper["questions"]:
            if q["id"] in given:
                q["diagnosis"] = given[q["id"]]
                q["diagnosis_source"] = "read from the working crop"
        dest.write_text(json.dumps(paper, indent=2, ensure_ascii=False))
        print(f"attached {len(given)} diagnosis(es) -> {dest}")
        write_card(dest)
        return

    raw = args.readings or sys.stdin.read()
    readings = json.loads(raw)
    ids = [q["id"] for q in spec["questions"]]
    missing = [i for i in ids if i not in readings]
    if missing:
        print(f"warning: no reading given for {', '.join(missing)} (recorded as blank)")
    readings = {i: (readings.get(i) or "") for i in ids}

    rows = {r["id"]: r for r in marker.mark(spec, readings)}
    given_diag = json.loads(args.diagnose) if args.diagnose else {}
    # Re-recording the same readings must not throw away diagnoses that were
    # read off the working crops; they cost a person's attention. Carried over
    # only where the reading is unchanged, since a new reading may mean a
    # different mistake.
    kept = {q["id"]: q.get("diagnosis") for q in paper.get("questions", [])
            if q.get("diagnosis") and q.get("diagnosis_source") != "spec"
            and str(q.get("reading")) == str(readings.get(q["id"]))}

    questions = []
    for q in spec["questions"]:
        r = rows[q["id"]]
        unsure = q["id"] in args.unsure
        diag = None
        if not r["right"]:
            if r["diagnosis"] and r["diagnosis"] != marker.NEEDS_MODEL:
                diag = r["diagnosis"]            # the spec already knew this mistake
            else:
                diag = given_diag.get(q["id"]) or kept.get(q["id"])
        questions.append({
            "id": q["id"], "number": q["number"], "text": q["text"],
            "standard": q["standard"], "skill": q["skill"],
            "learning_component_ids": q["learning_component_ids"],
            "reading": r["reading"], "expected": q["answer"],
            "right": None if unsure else r["right"],
            "diagnosis": diag,
            "diagnosis_source": ("spec" if diag and diag == r["diagnosis"]
                                 else ("read from the working crop" if diag else None)),
            # A reader transcribed this from a crop, so it is confirmed unless
            # the handwriting was called out as ambiguous.
            "needs_review": unsure,
            "confirmed": not unsure,
        })

    # When the paper was done, so the planner can space out review. The camera
    # app stamps it into the file name (Test_K_h…_20261012-183000.jpg);
    # otherwise the day it is marked. Kept if already set (re-recording).
    if not paper.get("date"):
        import datetime, re
        m = re.search(r"_(\d{4})(\d{2})(\d{2})-\d{6}", meta.get("source") or "")
        paper["date"] = f"{m[1]}-{m[2]}-{m[3]}" if m else datetime.date.today().isoformat()
        paper["date_source"] = "photo filename" if m else "day it was marked"
    paper.update({
        "paper": meta.get("source") or spec["title"], "sha1": args.sha1,
        "spec": spec_path.name, "test_id": spec["test_id"], "route": "qr-crops",
        "read_by": "claude (crops from align_and_crop.py)", "questions": questions,
    })
    if args.note:
        paper["note"] = args.note
    PAPERS.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(paper, indent=2, ensure_ascii=False))

    right = sum(1 for q in questions if q["right"] is True)
    wrong = [q for q in questions if q["right"] is False]
    print(f"{spec['title']}: {right}/{len(questions)} correct -> {dest}")
    for q in wrong:
        src = {"spec": "code", None: "NEEDS A DIAGNOSIS"}.get(q["diagnosis_source"], "read")
        print(f"  {q['id']} read {q['reading']!r}, expected {q['expected']!r}  [{src}]"
              f"{'  ' + q['diagnosis'] if q['diagnosis'] else ''}")
    need = [q["id"] for q in wrong if not q["diagnosis"]]
    if need:
        print(f"\nRead the working crops for {', '.join(need)} in cache/prepared/{args.sha1}/, then:")
        print(f"  python3 record_paper.py {args.sha1} --diagnose '{{\"{need[0]}\": \"...\"}}'")
    if args.unsure:
        print(f"\nheld out of the skill record as ambiguous: {', '.join(args.unsure)}")
    write_card(dest)


if __name__ == "__main__":
    main()
