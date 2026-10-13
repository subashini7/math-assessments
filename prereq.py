"""Learning Commons: standard lookup and prerequisites, with a file cache.

Prerequisites come from the SAP Coherence Map, which is standard-level (not
learning-component-level), so everything here is keyed by CCSS statement code.

The REST API needs a free key in `LEARNING_COMMONS_API_KEY` (header `x-api-key`).
Without one this still works for the standards already in `cache/prereqs.json`,
which was seeded from the same graph on 2026-10-07 so the pipeline runs before
the key arrives. A lookup that misses the cache and has no key raises, rather
than guessing a progression.

Licence CC BY 4.0: show `attributionStatement` wherever this data is displayed.
"""
import json, os
from pathlib import Path

import requests

BASE = "https://api.learningcommons.org/knowledge-graph/v0"
CACHE = Path(__file__).parent / "cache" / "prereqs.json"

# Seeded 2026-10-07 from the Learning Commons knowledge graph. `prereqs` lists the
# standards the Coherence Map puts *before* each one. Sub-standards matter: a
# query for a parent like 7.EE.B.4 returns nothing and points at 7.EE.B.4.a/b.
SEED = {
    "6.NS.B.3": {
        "description": "Fluently add, subtract, multiply, and divide multi-digit decimals using the standard algorithm for each operation.",
        "grade": "6",
        "prereqs": ["6.NS.B.2", "5.NBT.B.5", "5.NBT.B.6", "5.NBT.B.7"],
    },
    "7.RP.A.3": {
        "description": "Use proportional relationships to solve multistep ratio and percent problems.",
        "grade": "7",
        "prereqs": ["7.RP.A.2", "6.RP.A.3"],
    },
    "7.NS.A.3": {
        "description": "Solve real-world and mathematical problems involving the four operations with rational numbers.",
        "grade": "7",
        "prereqs": ["4.OA.A.3", "6.NS.B.3", "7.NS.A.2.c", "7.NS.A.1.d", "7.NS.A.2.d"],
    },
    "7.EE.B.4.a": {
        "description": "Solve word problems leading to equations of the form px + q = r and p(x + q) = r.",
        "grade": "7",
        "prereqs": ["7.NS.A.3", "6.EE.B.6", "6.EE.B.7"],
    },
    "6.RP.A.3.c": {
        "description": "Find a percent of a quantity as a rate per 100; solve problems involving finding the whole given a part and the percent.",
        "grade": "6",
        "prereqs": ["6.RP.A.2"],
    },
    # Parents whose progression lives on their sub-standards. Recorded so a
    # lookup resolves instead of failing, and so the redirect is not re-learned.
    "7.EE.B.4": {"description": "Use variables to represent quantities ... construct simple equations and inequalities.",
                 "grade": "7", "prereqs": [], "substandards": ["7.EE.B.4.a", "7.EE.B.4.b"]},
    "6.RP.A.3": {"description": "Use ratio and rate reasoning to solve real-world and mathematical problems.",
                 "grade": "6", "prereqs": [],
                 "substandards": ["6.RP.A.3.a", "6.RP.A.3.b", "6.RP.A.3.c", "6.RP.A.3.d"]},
}

# Descriptions for seeded prerequisite codes, so the next test can be written
# from them without another call.
SEED_DESCRIPTIONS = {
    "6.NS.B.2": "Fluently divide multi-digit numbers using the standard algorithm.",
    "5.NBT.B.5": "Fluently multiply multi-digit whole numbers using the standard algorithm.",
    "5.NBT.B.6": "Find whole-number quotients with up to four-digit dividends and two-digit divisors.",
    "5.NBT.B.7": "Add, subtract, multiply, and divide decimals to hundredths using place value and properties of operations.",
    "7.RP.A.2": "Recognize and represent proportional relationships between quantities.",
    "4.OA.A.3": "Solve multistep word problems with the four operations, including interpreting remainders.",
    "6.EE.B.6": "Use variables to represent numbers and write expressions for a real-world problem.",
    "6.EE.B.7": "Solve problems by writing and solving equations of the form x + p = q and px = q.",
    "6.RP.A.2": "Understand the concept of a unit rate a/b associated with a ratio a:b.",
    "7.NS.A.2.c": "Apply properties of operations as strategies to multiply and divide rational numbers.",
    "7.NS.A.1.d": "Apply properties of operations as strategies to add and subtract rational numbers.",
    "7.NS.A.2.d": "Convert a rational number to a decimal using long division.",
}


def load_cache():
    if CACHE.exists():
        return json.loads(CACHE.read_text())
    data = {"standards": dict(SEED), "descriptions": dict(SEED_DESCRIPTIONS),
            "attribution": "Learning Commons knowledge graph, CC BY 4.0",
            "source": "seeded 2026-10-07 from the SAP Coherence Map"}
    save_cache(data)
    return data


def save_cache(data):
    CACHE.parent.mkdir(parents=True, exist_ok=True)
    CACHE.write_text(json.dumps(data, indent=2, ensure_ascii=False))


def _get(path, **params):
    key = os.environ.get("LEARNING_COMMONS_API_KEY")
    if not key:
        return None
    r = requests.get(f"{BASE}{path}", headers={"x-api-key": key},
                     params=params, timeout=60)
    if r.status_code != 200:
        raise RuntimeError(f"Learning Commons {path} -> HTTP {r.status_code}: {r.text[:200]}")
    return r.json()


def describe(code, cache=None):
    """Human-readable text for a standard code, from cache or the API."""
    cache = cache if cache is not None else load_cache()
    if code in cache["standards"]:
        return cache["standards"][code].get("description")
    if code in cache["descriptions"]:
        return cache["descriptions"][code]
    got = _get("/standards", statementCode=code)
    if got:
        desc = (got.get("description") if isinstance(got, dict)
                else (got[0].get("description") if got else None))
        if desc:
            cache["descriptions"][code] = desc
            save_cache(cache)
            return desc
    return None


def prerequisites(code, cache=None):
    """Standards the Coherence Map places before `code`.

    Returns (codes, source) where source is "cache" or "api". Raises if the code
    is unknown and no API key is set - a guessed progression would send the next
    test after the wrong skill, which is worse than stopping.
    """
    cache = cache if cache is not None else load_cache()
    entry = cache["standards"].get(code)
    if entry is not None:
        subs = entry.get("substandards") or []
        if not entry["prereqs"] and subs:
            # The map hangs the progression off the sub-standards; union them.
            out = []
            for s in subs:
                if s in cache["standards"]:
                    out += cache["standards"][s]["prereqs"]
            return sorted(set(out)), "cache(substandards)"
        return list(entry["prereqs"]), "cache"

    if not os.environ.get("LEARNING_COMMONS_API_KEY"):
        raise RuntimeError(
            f"{code} is not in cache/prereqs.json and LEARNING_COMMONS_API_KEY is not set. "
            "Set the key, or add the standard to the cache; do not guess a progression.")

    found = _get("/standards", statementCode=code) or {}
    uuid = found.get("caseIdentifierUUID") if isinstance(found, dict) else None
    if not uuid:
        raise RuntimeError(f"Learning Commons has no standard {code}")
    prog = _get("/standards/progression", caseIdentifierUUID=uuid, direction="backward") or {}
    codes, descs = [], {}
    for s in prog.get("standards", []):
        codes.append(s["statementCode"])
        descs[s["statementCode"]] = s.get("description")
    cache["standards"][code] = {"description": found.get("description"),
                                "grade": (found.get("gradeLevels") or [None])[0],
                                "prereqs": codes}
    cache["descriptions"].update({k: v for k, v in descs.items() if v})
    save_cache(cache)
    return codes, "api"


COMPONENT_CACHE = Path(__file__).parent / "cache" / "components.json"


def load_components():
    if COMPONENT_CACHE.exists():
        return json.loads(COMPONENT_CACHE.read_text())
    return {"by_standard": {}}


def components_of(code):
    """{component_id: description} for a standard, from cache or the API.

    The Coherence Map relates standards, not components, so these carry no
    prerequisite edges. They answer a different question: which *part* of a
    standard is weak - subtraction rather than division inside 6.NS.B.3.
    """
    cache = load_components()
    if code in cache["by_standard"]:
        return cache["by_standard"][code]
    got = _get("/learning-components-for-a-standard", statementCode=code)
    if not got:
        return {}
    out = {c["identifier"]: c.get("description") for c in got.get("learning_components", [])}
    if out:
        cache["by_standard"][code] = out
        COMPONENT_CACHE.write_text(json.dumps(cache, indent=2, ensure_ascii=False))
    return out


def component_name(cid):
    for comps in load_components()["by_standard"].values():
        if cid in comps:
            return comps[cid]
    return None


def grade_of(code):
    """Leading grade number of a CCSS code, for the two-grade-level guardrail."""
    head = code.split(".")[0]
    return int(head) if head.isdigit() else None


if __name__ == "__main__":
    import sys
    cache = load_cache()
    for code in (sys.argv[1:] or ["6.NS.B.3", "7.RP.A.3", "7.EE.B.4"]):
        try:
            codes, src = prerequisites(code, cache)
        except RuntimeError as e:
            print(f"{code}: {e}")
            continue
        print(f"{code} ({describe(code, cache)})\n  via {src}")
        for c in codes:
            print(f"   <- {c}  grade {grade_of(c)}  {describe(c, cache)}")
