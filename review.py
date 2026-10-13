"""Confirm the readings the pipeline is not sure about.

Whole-page reading gets roughly 1 in 5 answers wrong, in both directions, at
high stated confidence. Disputed readings are therefore held out
of the skill record until a person says what the page actually says. This is
that step, in the terminal until there is a web page.

    python3 review.py            # walk the disputed questions
    python3 review.py --all      # walk every question, not just disputed ones
    python3 review.py --list     # just show what is pending

Enter = accept the shown reading, or type the correct one. `s` skips, `q` quits.
"""
import argparse, json
from pathlib import Path

PAPERS = Path(__file__).parent / "cache" / "papers"


def pending(paper, every=False):
    return [q for q in paper.get("questions", [])
            if (every or q.get("needs_review")) and not q.get("confirmed")]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--list", action="store_true")
    args = ap.parse_args()

    files = sorted(PAPERS.glob("*.json"))
    if not files:
        print(f"Nothing in {PAPERS}. Run prepare_inbox.py first.")
        return

    total = 0
    for f in files:
        paper = json.loads(f.read_text())
        todo = pending(paper, args.all)
        total += len(todo)
        if args.list:
            if todo:
                print(f"{paper.get('paper')}: {len(todo)} to confirm")
            continue
        if not todo:
            continue
        print(f"\n=== {paper.get('paper')} ({paper.get('route')}) ===")
        changed = False
        for q in todo:
            print(f"\nQ{q['number']}: {q.get('text')}")
            print(f"  first pass : {q.get('reading')!r}")
            if q.get("reading_second_pass") is not None:
                print(f"  second pass: {q.get('reading_second_pass')!r}")
            if q.get("review_reason"):
                print(f"  flagged because {q['review_reason']}")
            if q.get("expected") is not None:
                print(f"  correct answer: {q.get('expected')!r}")
            try:
                got = input("  what does the page actually say? [Enter=first pass] ").strip()
            except EOFError:
                print("\n(not a terminal; use --list)")
                return
            if got.lower() == "q":
                break
            if got.lower() == "s":
                continue
            if got:
                q["reading"] = got
                # The mark was computed from a reading that has just changed, so
                # it is no longer evidence; drop it rather than leave it stale.
                q["right"] = None
                q["expected_stale"] = True
            q["confirmed"] = True
            q["needs_review"] = False
            changed = True
        if changed:
            f.write_text(json.dumps(paper, indent=2, ensure_ascii=False))
            print(f"\n  saved {f.name}")

    if args.list:
        print(f"\n{total} question(s) awaiting confirmation.")
    elif total == 0:
        print("Nothing to confirm.")
    print("\nIf you corrected any reading, re-mark it before trusting the record:")
    print("  python3 mark.py <spec>.json '<readings json>'   (QR sheets)")


if __name__ == "__main__":
    main()
