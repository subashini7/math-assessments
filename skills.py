"""Accumulate a per-skill record across papers, and pick what to test next.

Reads every paper in `cache/papers/`, aggregates by CCSS standard, and plans the
next sheet from four shares: retest what went wrong (walking back to
prerequisites on repeated failure), cover standards never asked (grade 5, then
grade 6), offer higher-grade standards whose foundations are mastered, and bring
back skills already answered right on a spaced schedule.

    python3 skills.py                 # show the record and what comes next
    python3 skills.py --json          # machine-readable, for the generator
"""
import argparse, json, sys
from collections import defaultdict
from pathlib import Path

import graph as kgraph
import prereq

HERE = Path(__file__).parent
PAPERS = HERE / "cache" / "papers"

# The child works at roughly grade 6-7. Prerequisites further back than this are
# reported but not put on a test: a 10-year-old handed grade-3 work learns the
# wrong lesson about themselves.
WORKING_GRADE = 7
MAX_GRADES_BACK = 2
# ...but a fixed floor fights the whole point of walking back. If a grade-5
# standard is itself failing, its grade-4 prerequisites are exactly what needs
# testing - refusing to go there would leave the real gap unexamined. So the
# floor drops one grade below the lowest standard that is actually weak, and
# stops there.
ABSOLUTE_FLOOR = 3


def grade_floor(rec):
    weak = [prereq.grade_of(c) for c, r in rec.items()
            if status(r) == "weak" and prereq.grade_of(c) is not None]
    floor = WORKING_GRADE - MAX_GRADES_BACK
    if weak:
        floor = min(floor, min(weak) - 1)
    return max(ABSOLUTE_FLOOR, floor)


def load_papers():
    if not PAPERS.exists():
        return []
    out = []
    for f in sorted(PAPERS.glob("*.json")):
        try:
            out.append(json.loads(f.read_text()))
        except json.JSONDecodeError:
            print(f"  skipping unreadable {f.name}")
    return out


def component_record(papers):
    """Per-component tally. A standard like 6.NS.B.3 bundles four operations, so
    its headline score hides which one is actually failing."""
    by = defaultdict(lambda: {"right": 0, "wrong": 0, "standard": None,
                              "name": None, "diagnoses": []})
    for p in papers:
        for q in p.get("questions", []):
            if q.get("needs_review") and not q.get("confirmed"):
                continue
            if q.get("right") is None:
                continue
            for cid in q.get("learning_component_ids") or []:
                r = by[cid]
                r["standard"] = q.get("standard")
                r["name"] = prereq.component_name(cid) or q.get("skill")
                r["right" if q["right"] else "wrong"] += 1
                if not q["right"] and q.get("diagnosis"):
                    r["diagnoses"].append(q["diagnosis"])
    return dict(by)


def record(papers):
    """Per-standard tally. Only questions a parent confirmed, or that were read
    without conflict, count - a disputed reading is not evidence about a skill."""
    by = defaultdict(lambda: {"right": 0, "wrong": 0, "unsure": 0,
                              "diagnoses": [], "papers": [], "description": None,
                              "history": []})
    # Oldest paper first, so `history` reads in the order the child did them.
    for p in sorted(papers, key=lambda p: p.get("date") or ""):
        for q in p.get("questions", []):
            code = q.get("standard")
            if not code:
                continue
            r = by[code]
            r["description"] = r["description"] or q.get("skill")
            if p.get("paper") not in r["papers"]:
                r["papers"].append(p.get("paper"))
            if q.get("needs_review") and not q.get("confirmed"):
                r["unsure"] += 1
                continue
            if q.get("right") is True:
                r["right"] += 1
            elif q.get("right") is False:
                r["wrong"] += 1
                if q.get("diagnosis"):
                    r["diagnoses"].append(q["diagnosis"])
            if q.get("right") is not None:
                r["history"].append((p.get("date") or "", q["right"]))
    for r in by.values():
        h = r["history"]
        r["streak"] = next((i for i, (_, ok) in enumerate(reversed(h)) if not ok), len(h))
        r["last_asked"] = h[-1][0] if h else None
    return dict(by)


MASTERED_STREAK = 3


def status(r):
    if r["right"] + r["wrong"] == 0:
        return "untested"
    # Three right in a row since the last mistake counts as mastered too, so one
    # old slip does not hold a skill - and everything gated on it - back forever.
    if (r["wrong"] == 0 and r["right"] >= 2) or r.get("streak", 0) >= MASTERED_STREAK:
        return "mastered"
    if r["wrong"] >= 2:
        return "weak"
    if r["wrong"] >= 1:
        return "shaky"
    return "ok"


def pick_next(rec, cache=None, n_target=8, n_confidence=2, comp=None):
    """What the next test should cover, and why."""
    cache = cache if cache is not None else prereq.load_cache()
    picks, seen = [], set()

    def weak_parts(code):
        """The components of `code` that are actually failing, so the next test
        targets the operation that is wrong rather than the whole standard."""
        return sorted((r["name"], cid) for cid, r in (comp or {}).items()
                      if r["standard"] == code and r["wrong"] and not r["right"])

    def add(code, why, source):
        if code in seen:
            return
        g = prereq.grade_of(code)
        if g is not None and g < WORKING_GRADE - MAX_GRADES_BACK:
            picks.append({"standard": code, "why": why, "source": source,
                          "skipped": f"grade {g} is more than {MAX_GRADES_BACK} levels back"})
            seen.add(code)
            return
        seen.add(code)
        parts = weak_parts(code)
        picks.append({"standard": code, "why": why, "source": source,
                      "description": prereq.describe(code, cache),
                      "target_components": [{"id": cid, "name": name} for name, cid in parts],
                      "focus": (f"weight this toward {', '.join(n for n, _ in parts)}"
                                if parts else None)})

    weak = [(c, r) for c, r in rec.items() if status(r) == "weak"]
    shaky = [(c, r) for c, r in rec.items() if status(r) == "shaky"]

    # Repeated failure first, and with it the prerequisites it may rest on.
    for code, r in sorted(weak, key=lambda kv: -kv[1]["wrong"]):
        add(code, f"wrong {r['wrong']} times", "failed")
        try:
            pres, _ = prereq.prerequisites(code, cache)
        except RuntimeError as e:
            picks.append({"standard": None, "why": str(e), "source": "prerequisite-lookup-failed"})
            continue
        for pcode in pres:
            pr = rec.get(pcode)
            if pr is None:
                add(pcode, f"never tested, and {code} has failed {r['wrong']} times", "prerequisite")
            elif status(pr) in ("weak", "shaky"):
                add(pcode, f"also shaky, and {code} depends on it", "prerequisite")

    for code, r in shaky:
        add(code, f"wrong {r['wrong']} of {r['right'] + r['wrong']}", "shaky")

    for code, r in rec.items():
        if status(r) == "untested":
            add(code, "seen on a paper but never answered", "untested")

    confidence = [c for c, r in rec.items() if status(r) == "mastered"][:n_confidence]
    testable = [p for p in picks if not p.get("skipped")]
    return {"test": testable[:n_target],
            "confidence": [{"standard": c, "why": "mastered; included so the test is not all weaknesses",
                            "source": "mastered"} for c in confidence],
            "skipped": [p for p in picks if p.get("skipped")]}


SYLLABUS = HERE / "cache" / "syllabus.json"


def coverage(rec, grade="5"):
    """What fraction of a whole grade has been tested at all.

    The graph is built from evidence, so a standard nobody has been asked about
    is simply absent from it - indistinguishable from one that does not exist.
    This reads the roster instead, so the gaps are visible.
    """
    import json as _json
    if not SYLLABUS.exists():
        return None
    roster = _json.loads(SYLLABUS.read_text())["grades"].get(grade, {})
    rows = []
    for code, desc in sorted(roster.items()):
        r = rec.get(code)
        n = (r["right"] + r["wrong"]) if r else 0
        rows.append({"standard": code, "domain": code.split(".")[1],
                     "description": desc, "n": n,
                     "status": status(r) if r else "never asked"})
    return rows


def load_syllabus():
    import json as _json
    return _json.loads(SYLLABUS.read_text()) if SYLLABUS.exists() else None


# A sheet entirely of failures re-tests known gaps and discovers nothing; one
# entirely of new material never closes a gap. Quotas keep all three reasons on
# every sheet, with the balance tilted toward what is already known to be wrong.
QUOTA = {"failure": 4, "coverage": 3, "readiness": 1, "review": 2}

# Spaced review: after 1, 2, 3, 4+ right answers in a row, a skill comes back
# this many days after it was last asked. Children forget without repetition;
# the gap widens as the run of right answers grows.
REVIEW_AFTER_DAYS = (2, 7, 21, 60)


def plan_tests(rec, comp=None, base_grade="5", n=10, quota=None, coverage_grades=("5", "6"),
               today=None):
    """What the next sheet should ask, weighing all three reasons at once.

    FAILURE   something is known to be wrong - retest it, and if it has failed
              twice, test what it rests on.
    COVERAGE  a standard in the grade roster that has never been asked about.
              Work bottom-up: grade 5 first, so gaps are found before they are
              inherited.
    READINESS a higher-grade standard whose grade-5 foundations are mastered.
              Testing one whose foundations are still shaky measures the
              foundation, not the new skill, so it is held back and the reason
              recorded.

    Returns the picks in priority order plus the blocked list, because "why is
    this NOT on the test" is as useful to a parent as what is.
    """
    syl = load_syllabus()
    if not syl:
        return None
    quota = dict(quota or QUOTA)
    used = {k: 0 for k in quota}
    roster = syl["grades"]
    unlocks = syl.get("unlocks", {})
    no_sheet = syl.get("needs_diagram", {})
    picks, seen, blocked = [], set(), []

    def mastered(code):
        r = rec.get(code)
        return bool(r) and status(r) == "mastered"

    def add(code, why, source, grade):
        bucket = "failure" if source.startswith("failure") else source
        if code in seen or len(picks) >= n or used.get(bucket, 0) >= quota.get(bucket, n):
            return
        seen.add(code)
        used[bucket] = used.get(bucket, 0) + 1
        parts = sorted((cid, r["name"]) for cid, r in (comp or {}).items()
                       if r["standard"] == code and r["wrong"] and not r["right"])
        picks.append({"standard": code, "grade": grade, "reason": source, "why": why,
                      "description": (roster.get(grade) or {}).get(code)
                                     or prereq.describe(code),
                      "focus": [name for _, name in parts] or None})

    def coverage_candidates():
        """(code, grade) never asked and askable on a sheet, lowest grade first.
        Above the base grade a standard whose known grade-5 foundations are not
        mastered is skipped: coverage must not bypass the readiness gate."""
        for g in coverage_grades:
            # Rotate through the domains (EE, G, NS, RP, SP, ...) instead of
            # taking codes alphabetically, so one sheet does not ask three
            # expressions questions in a row while the other domains wait.
            by_domain = {}
            for code in sorted(roster.get(g) or {}):
                by_domain.setdefault(code.split(".")[1], []).append(code)
            order = [c for tier in __import__("itertools").zip_longest(*by_domain.values())
                     for c in tier if c]
            for code in order:
                if code in rec or code in no_sheet:
                    continue
                if g != base_grade:
                    foundations = [l for l, hs in unlocks.items() if code in hs]
                    if any(not mastered(f) for f in foundations):
                        continue
                yield code, g

    def due_for_review():
        import datetime
        day = today or datetime.date.today()
        due = []
        for code, r in rec.items():
            streak, last = r.get("streak", 0), r.get("last_asked")
            if not streak or not last or code in no_sheet:
                continue
            gap = REVIEW_AFTER_DAYS[min(streak, len(REVIEW_AFTER_DAYS)) - 1]
            days = (day - datetime.date.fromisoformat(last)).days
            if days >= gap:
                due.append((days / gap, code,
                            f"right {streak} in a row, last asked {days} days ago (due after {gap})"))
        return [(code, why) for _, code, why in sorted(due, reverse=True)]

    # 1. FAILURE, worst first.
    for code, r in sorted(rec.items(), key=lambda kv: -kv[1]["wrong"]):
        st = status(r)
        if st not in ("weak", "shaky"):
            continue
        g = str(prereq.grade_of(code) or "")
        add(code, f"wrong {r['wrong']} of {r['right'] + r['wrong']}", "failure", g)
        if st == "weak":
            try:
                for p in prereq.prerequisites(code)[0]:
                    if not mastered(p):
                        add(p, f"{code} has failed twice and rests on this", "failure-prereq",
                            str(prereq.grade_of(p) or ""))
            except RuntimeError:
                pass

    # 2. COVERAGE of the base grade, before anything above it.
    # Grade by grade: a grade-6 gap is only reached once grade 5 runs short of
    # untested standards, so gaps are still found before they are inherited.
    for code, g in coverage_candidates():
        add(code, f"in the grade {g} roster, never asked", "coverage", g)

    # 3. READINESS: higher grades, gated on their grade-5 foundations.
    for lower, higher in sorted(unlocks.items()):
        for code in higher:
            g = str(prereq.grade_of(code) or "")
            # Readiness is for first asks. Anything already answered comes back
            # through failure (if last wrong) or review (on its schedule).
            if g == base_grade or code in seen or code in no_sheet or code in rec:
                continue
            foundations = sorted(l for l, hs in unlocks.items() if code in hs)
            unmet = [f for f in foundations if not mastered(f)]
            if unmet:
                blocked.append({"standard": code, "grade": g,
                                "waiting_on": unmet,
                                "description": (roster.get(g) or {}).get(code)})
            else:
                add(code, "foundations mastered: " + ", ".join(foundations), "readiness", g)
    # 4. REVIEW: skills last answered right, brought back once their gap is up,
    #    most overdue first. Failures above already cover anything last wrong.
    for code, why in due_for_review():
        add(code, why, "review", str(prereq.grade_of(code) or ""))
    # one entry per blocked standard, listing everything it waits on
    # If a bucket could not fill its share (say nothing is ready yet), let the
    # others use the remainder instead of printing a short sheet.
    if len(picks) < n:
        for k in quota:
            quota[k] = n
        for code, r in sorted(rec.items(), key=lambda kv: -kv[1]["wrong"]):
            if status(r) in ("weak", "shaky"):
                add(code, f"wrong {r['wrong']} of {r['right'] + r['wrong']}", "failure",
                    str(prereq.grade_of(code) or ""))
        for code, g in coverage_candidates():
            add(code, f"in the grade {g} roster, never asked", "coverage", g)
        for code, why in due_for_review():
            add(code, why, "review", str(prereq.grade_of(code) or ""))

    seen_b = {}
    for b in blocked:
        seen_b.setdefault(b["standard"], b)
    off_sheet = [{"standard": c, "why": w} for c, w in sorted(no_sheet.items())
                 if c not in rec and c.split(".")[0] in coverage_grades]
    return {"picks": picks, "blocked": sorted(seen_b.values(), key=lambda b: b["standard"]),
            "mix": used, "off_sheet": off_sheet}


def deal(picks, sheets):
    """Spread one batch's picks across `sheets` sheets of 10.

    The batch is planned as a whole (so no standard is asked twice in it), then
    dealt bucket by bucket - failures, then coverage, then readiness - each pick
    to the sheet with the fewest so far. Every sheet gets its share of each
    reason, instead of sheet 1 taking all the failures.
    """
    out = [[] for _ in range(sheets)]
    order = {"failure": 0, "coverage": 1, "readiness": 2, "review": 3}
    groups = {}
    for pk in picks:
        bucket = "failure" if pk["reason"].startswith("failure") else pk["reason"]
        groups.setdefault(bucket, []).append(pk)
    for bucket in sorted(groups, key=lambda b: order.get(b, 9)):
        for pk in groups[bucket]:
            min(out, key=len).append(pk)
    return out


def expand_cache(rec):
    """Pull prerequisites for the weak standards that are currently leaves.

    A standard the child keeps failing is exactly the one whose foundations are
    worth drawing, and those are the nodes sitting at the bottom of the graph
    with nothing beneath them. Weak first, then shaky.
    """
    import os
    cache = prereq.load_cache()
    frontier = [(status(r), c) for c, r in rec.items()
                if status(r) in ("weak", "shaky") and c not in cache["standards"]]
    frontier.sort(key=lambda z: (z[0] != "weak", z[1]))
    if not frontier:
        print("Nothing to expand: every weak or shaky standard already has prerequisites cached.\n")
        return
    have_key = bool(os.environ.get("LEARNING_COMMONS_API_KEY"))
    print(f"Expanding the graph beneath {len(frontier)} standard(s) with no prerequisites yet:")
    for st, code in frontier:
        if not have_key:
            print(f"  {st:<6} {code:<12} would fetch (set LEARNING_COMMONS_API_KEY)")
            continue
        try:
            got, src = prereq.prerequisites(code, cache)
            print(f"  {st:<6} {code:<12} +{len(got)} prerequisite(s) via {src}: {', '.join(got) or '(none)'}")
        except RuntimeError as e:
            print(f"  {st:<6} {code:<12} failed: {e}")
    if not have_key:
        print("\nNo key set, so nothing was fetched. Free key: https://platform.learningcommons.org")
    print()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--target", type=int, default=8, help="skills to put on the next test")
    ap.add_argument("--no-graph", action="store_true", help="skip the knowledge graph")
    ap.add_argument("--dot", action="store_true", help="emit the graph as Graphviz and exit")
    ap.add_argument("--sheets", type=int, default=1, choices=(1, 2, 3),
                    help="with --plan: plan a batch of this many sheets and deal it across them")
    ap.add_argument("--plan", action="store_true",
                    help="what the next sheet should ask, weighing failure, coverage and readiness")
    ap.add_argument("--coverage", metavar="GRADE", nargs="?", const="5",
                    help="show how much of a whole grade has been tested (default 5)")
    ap.add_argument("--expand", action="store_true",
                    help="fetch and cache prerequisites for weak standards that have none, so "
                         "the graph can keep going down to the basics (needs "
                         "LEARNING_COMMONS_API_KEY)")
    args = ap.parse_args()

    papers = load_papers()
    rec = record(papers)
    comp = component_record(papers)
    if args.dot:
        print(kgraph.to_dot(rec))
        return
    if args.plan:
        comp = component_record(papers)
        k = args.sheets
        quota = {b: q * k for b, q in QUOTA.items()}
        out = plan_tests(rec, comp, n=10 * k, quota=quota)
        if out is None:
            sys.exit("No cache/syllabus.json.")
        head = "NEXT SHEET — 10 questions" if k == 1 else f"NEXT {k} SHEETS — {10 * k} questions, no standard repeated"
        print(head + "\n")
        print(f"mix: {out['mix']}  (quota {quota})\n")
        for si, sheet in enumerate(deal(out["picks"], k), 1):
            if k > 1:
                print(f"--- sheet {si} ---")
            for i, p in enumerate(sheet, 1):
                print(f"{i:>2}. {p['standard']:<12} G{p['grade']}  [{p['reason']}]  {p['why']}")
                if p.get("description"):
                    print(f"    {p['description'][:92]}")
                if p.get("focus"):
                    print(f"    aim at: {', '.join(p['focus'])}")
            if k > 1:
                print()
        if out.get("off_sheet"):
            print(f"\nIn the roster but not testable on a ten-box sheet ({len(out['off_sheet'])}):")
            for o in out["off_sheet"]:
                print(f"  {o['standard']:<12} {o['why']}")
        if out["blocked"]:
            print(f"\nHeld back until their foundations are mastered ({len(out['blocked'])}):")
            for b in out["blocked"]:
                print(f"  {b['standard']:<12} G{b['grade']}  waiting on {', '.join(b['waiting_on'])}")
        return
    if args.coverage:
        rows = coverage(rec, args.coverage)
        if rows is None:
            sys.exit("No cache/syllabus.json; nothing to compare against.")
        done = [r for r in rows if r["n"]]
        print(f"GRADE {args.coverage} COVERAGE: {len(done)} of {len(rows)} standards tested\n")
        last = None
        for r in rows:
            if r["domain"] != last:
                last = r["domain"]
                print(f"  {last}")
            mark = f"{r['status']:<11} n={r['n']}" if r["n"] else "never asked"
            print(f"    {r['standard']:<11} {mark:<22} {r['description'][:62]}")
        miss = [r["standard"] for r in rows if not r["n"]]
        print(f"\n{len(miss)} never asked: {', '.join(miss)}")
        return
    if args.expand:
        expand_cache(rec)
    plan = pick_next(rec, n_target=args.target, comp=comp)

    if args.json:
        print(json.dumps({"record": rec, "components": comp, "next": plan},
                         indent=2, ensure_ascii=False))
        return

    print(f"{len(papers)} paper(s) in cache/papers/\n")
    if not rec:
        print("No questions with a standard yet. Drop images in inbox/ and run prepare_inbox.py.")
        return
    print(f"{'standard':<14} {'status':<9} {'right':>5} {'wrong':>5} {'unsure':>6}  skill")
    for code in sorted(rec, key=lambda c: (status(rec[c]) != "weak", c)):
        r = rec[code]
        print(f"{code:<14} {status(r):<9} {r['right']:>5} {r['wrong']:>5} {r['unsure']:>6}  "
              f"{(r['description'] or '')[:42]}")
        for d in dict.fromkeys(r["diagnoses"]):
            print(f"{'':<14}   - {d[:90]}")

    print("\nNext test should cover:")
    for p in plan["test"]:
        # A failed prerequisite lookup is recorded as a pick with no standard,
        # so that the reason is not silently dropped; print it as a note.
        if not p.get("standard"):
            print(f"  (note) [{p['source']}] {p['why']}")
            continue
        print(f"  {p['standard']:<14} [{p['source']}] {p['why']}")
        if p.get("description"):
            print(f"  {'':<14}   {p['description'][:88]}")
        if p.get("focus"):
            print(f"  {'':<14}   {p['focus']}")
    for p in plan["confidence"]:
        print(f"  {p['standard']:<14} [{p['source']}] {p['why']}")
    for p in plan["skipped"]:
        print(f"  (skipped {p['standard']}: {p['skipped']})")

    if not args.no_graph:
        text = kgraph.render(rec, comp)
        print(text)
        # Keep the latest graph on disk, so it can be looked at without re-running
        # and so two runs can be compared as the record grows.
        out = HERE / "cache"
        out.mkdir(parents=True, exist_ok=True)
        (out / "graph.txt").write_text(text)
        (out / "graph.svg").write_text(kgraph.to_svg(rec, comp))
        (out / "graph_by_grade.svg").write_text(kgraph.to_svg_by_grade(rec, comp))
        print(f"\nSaved: {out/'graph.txt'}   the text above"
              f"\n       {out/'graph.svg'}   dependency view, wide"
              f"\n       {out/'graph_by_grade.svg'}   by grade, no edges - fits a screen")


if __name__ == "__main__":
    main()
