"""Check the graph against its sources, rather than taking it on trust.

    python3 verify_graph.py                 # print every claim and where to check it
    LEARNING_COMMONS_API_KEY=... python3 verify_graph.py --refetch

The prerequisite edges in `cache/prereqs.json` were seeded from the
Learning Commons knowledge graph, so transcription error is a real risk — a
wrong edge would send the next test after a skill the child does not need.
`--refetch` re-queries every cached standard and reports any difference; it
exits non-zero if anything disagrees, so it can be run as a check.

Without a key it prints each claim in a form that can be checked by hand against
the public sources, which is slower but needs nothing installed.
"""
import argparse, json, sys
from pathlib import Path

import prereq

CACHE = Path(__file__).parent / "cache" / "prereqs.json"

SOURCES = """Where to check each kind of claim:

  Standard code and its text
    CCSS is a public framework; the codes are not invented here.
    https://www.corestandards.org/Math/   (navigate by grade, e.g. 6.NS.B.3)

  Prerequisite arrows
    These come from the SAP Coherence Map, which is browsable for free:
    https://achievethecore.org/coherence-map/
    Pick the grade, click the standard, and its prerequisites are shown.
    An arrow here should appear there; if it does not, the cache is wrong.

  Learning component ids (the UUIDs in each test spec)
    ANet learning components, served by Learning Commons. Not used by the graph
    yet - the Coherence Map relates standards, not components.

Learning Commons data is CC BY 4.0."""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--refetch", action="store_true",
                    help="re-query Learning Commons and diff against the cache")
    args = ap.parse_args()

    cache = json.loads(CACHE.read_text())
    standards, descriptions = cache["standards"], cache["descriptions"]

    print(f"cache: {CACHE}")
    print(f"  {len(standards)} standard(s) with prerequisites, "
          f"{len(descriptions)} description(s)")
    print(f"  seeded: {cache.get('source')}")
    print(f"  descriptions: {cache.get('description_source', 'unrecorded')}\n")

    print("Every prerequisite claim in the graph:\n")
    total = 0
    for code in sorted(standards):
        entry = standards[code]
        pres = entry.get("prereqs") or []
        subs = entry.get("substandards") or []
        if subs and not pres:
            print(f"  {code}: no direct prerequisites; the map hangs them off "
                  f"{', '.join(subs)}")
            continue
        for p in pres:
            total += 1
            print(f"  {p:<12} -> {code}")
    print(f"\n  {total} edge(s) to verify.\n")

    if not args.refetch:
        print(SOURCES)
        print("\nTo check automatically instead, get a free key at "
              "https://platform.learningcommons.org and run:")
        print("  LEARNING_COMMONS_API_KEY=... python3 verify_graph.py --refetch")
        return

    import os
    if not os.environ.get("LEARNING_COMMONS_API_KEY"):
        sys.exit("--refetch needs LEARNING_COMMONS_API_KEY in the environment.")

    print("Re-fetching from Learning Commons...\n")
    problems = []
    fresh = {"standards": {}, "descriptions": {}}
    for code in sorted(standards):
        if standards[code].get("substandards") and not standards[code].get("prereqs"):
            continue
        try:
            got, _ = prereq.prerequisites(code, fresh)
        except RuntimeError as e:
            problems.append(f"{code}: could not re-fetch ({e})")
            continue
        cached = sorted(standards[code].get("prereqs") or [])
        if sorted(got) != cached:
            problems.append(f"{code}: cache says {cached}, Learning Commons says {sorted(got)}")
            print(f"  MISMATCH {code}")
        else:
            print(f"  ok       {code}  ({len(cached)} prerequisite(s))")

    for code, text in sorted(descriptions.items()):
        live = prereq.describe(code, fresh)
        if live and live.strip() != text.strip():
            problems.append(f"{code}: description differs from Learning Commons")

    print()
    if problems:
        print(f"{len(problems)} problem(s):")
        for p in problems:
            print(f"  - {p}")
        print("\nThe cache is wrong where it disagrees. Correct cache/prereqs.json, "
              "or delete it and let prereq.py rebuild from the API.")
        sys.exit(1)
    print("Everything in the cache matches Learning Commons.")


if __name__ == "__main__":
    main()
