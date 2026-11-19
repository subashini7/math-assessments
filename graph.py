"""The knowledge graph: which pathways have been tested, and how sure we are.

Printed at the end of every `skills.py` run.

Every status here is the planner's own (`skills.status`), so the pictures say
what drives the next sheets: mastered, ok, shaky or weak. A 90% Wilson interval
over all answers is shown alongside as context - 1 out of 1 is not "100%
mastered", and the interval narrows as more questions accumulate.

Edges come from the SAP Coherence Map via `prereq.py`: an arrow means the
Coherence Map places that standard before this one.
"""
import math

import prereq

Z = 1.645          # 90% interval

STATUS = {
    "mastered": ("MASTERED", "every part asked, and right twice with no mistakes or 3 in a row on different days since the last"),
    "ok":       ("ok      ", "right so far, not yet enough to call mastered, or parts never asked"),
    "shaky":    ("shaky   ", "one mistake, not yet back to 3 in a row on different days"),
    "weak":     ("WEAK    ", "two or more mistakes, not yet back to 3 in a row on different days"),
    "untested": ("untested", "no answered questions yet"),
}


def planner_status(r):
    """The planner's status for a record with right/wrong (and streak, if any).
    Imported late: skills imports this module."""
    from skills import status
    if not r or not (r.get("right", 0) + r.get("wrong", 0)):
        return "untested"
    return status({"right": r.get("right", 0), "wrong": r.get("wrong", 0),
                   "streak_days": r.get("streak_days", 0), "unasked": r.get("unasked"),
                   "parts_failing": r.get("parts_failing")})


def to_mastered(r):
    """How many more right answers in a row would make this mastered, by the
    planner's rule: 2 with no mistakes yet, otherwise a run of 3 on different days.
    Parts never asked are a separate condition, reported on their own."""
    if planner_status(r) == "mastered":
        return 0
    if not r.get("wrong", 0):
        return max(0, 2 - r.get("right", 0))
    from skills import MASTERED_STREAK
    return max(0, MASTERED_STREAK - r.get("streak_days", 0))


def wilson(k, n, z=Z):
    """(point, low, high) for k successes in n trials. n=0 gives the full range."""
    if n == 0:
        return None, 0.0, 1.0
    p = k / n
    denom = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    half = (z / denom) * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return p, max(0.0, centre - half), min(1.0, centre + half)


def confidence_bar(n, lo, hi, width=5):
    """How tightly the interval pins the estimate down. Fills as n grows."""
    if n == 0:
        return "-" * width
    filled = width - min(width, int(round((hi - lo) / (1.0 / width))))
    return "#" * max(0, filled) + "." * (width - max(0, filled))




def build(rec, cache=None, max_depth=2):
    """Nodes for every tested standard plus the prerequisites behind them."""
    cache = cache if cache is not None else prereq.load_cache()
    nodes, edges, unknown = {}, [], []

    def node(code, tested):
        if code in nodes:
            nodes[code]["tested"] = nodes[code]["tested"] or tested
            return nodes[code]
        r = rec.get(code) or {}
        k, n = r.get("right", 0), r.get("right", 0) + r.get("wrong", 0)
        p, lo, hi = wilson(k, n)
        nodes[code] = {"code": code, "right": k, "n": n, "point": p, "lo": lo, "hi": hi,
                       "status": planner_status(r), "tested": tested, "record": r,
                       "description": prereq.describe(code, cache) or r.get("description"),
                       "unsure": r.get("unsure", 0),
                       "diagnoses": list(dict.fromkeys(r.get("diagnoses", [])))}
        return nodes[code]

    frontier = [(c, 0) for c in rec]
    for c in rec:
        node(c, True)
    seen = set(rec)
    while frontier:
        code, depth = frontier.pop(0)
        if depth >= max_depth:
            continue
        try:
            pres, _ = prereq.prerequisites(code, cache)
        except RuntimeError:
            unknown.append(code)
            continue
        if not pres and code not in rec:
            unknown.append(code)
        for p in pres:
            node(p, p in rec)
            edges.append((p, code))
            if p not in seen:
                seen.add(p)
                frontier.append((p, depth + 1))
    return nodes, edges, unknown


def render(rec, comp=None, cache=None, width=100):
    cache = cache if cache is not None else prereq.load_cache()
    nodes, edges, unknown = build(rec, cache)
    if not nodes:
        return "No standards recorded yet."

    by_child = {}
    for pre, child in edges:
        by_child.setdefault(child, []).append(pre)

    out = ["", "=" * width,
           "KNOWLEDGE GRAPH   ->  means the Coherence Map puts that skill first", "=" * width]
    tested = [c for c, nd in nodes.items() if nd["tested"]]
    out.append(f"{len(tested)} skill(s) tested, {len(nodes)} in view "
               f"(status as the planner sees it; 90% interval shown for context)")

    order = sorted(tested, key=lambda c: ({"weak": 0, "shaky": 1, "ok": 2, "untested": 3,
                                           "mastered": 4}[nodes[c]["status"]], c))
    for code in order:
        nd = nodes[code]
        out.append("")
        out.append(f"{code}  {STATUS[nd['status']][0]}  {bar(nd)}")
        if nd["description"]:
            out.append(f"    {clip(nd['description'], width - 6)}")
        for d in nd["diagnoses"][:3]:
            out.append(f"    mistake seen: {clip(d, width - 20)}")
        more = to_mastered(nd["record"])
        if more:
            then = "is also needed" if nd["record"].get("unasked") else "would make this mastered"
            out.append(f"    {more} more right in a row on different days {then}")
        for d in sorted((nd["record"].get("unasked") or {}).values()):
            out.append(f"    not mastered until asked: {clip(d, width - 31)}")
        # Which PART of the standard is weak. A standard bundles several
        # components - 6.NS.B.3 covers all four decimal operations - so the
        # headline score can say "decimals" when only subtraction is failing.
        mine = {cid: r for cid, r in (comp or {}).items() if r["standard"] == code}
        if mine:
            out.append("    inside this standard:")
            for cid, r in sorted(mine.items(), key=lambda kv: (-kv[1]["wrong"], kv[1]["name"] or "")):
                n = r["right"] + r["wrong"]
                st = planner_status(r)
                flag = "  <-- the weak part" if r["wrong"] and not r["right"] else ""
                out.append(f"      {STATUS[st][0]} {r['right']}/{n}  "
                           f"{clip(r['name'], width - 34)}{flag}")
            askable = prereq.sheet_components(code)
            untested = {c: d for c, d in prereq.components_of(code).items() if c not in mine}
            for c, d in sorted(untested.items(), key=lambda kv: (kv[0] not in askable, kv[1] or "")):
                tag = "untested 0/0" if c in askable else "not on a sheet"
                out.append(f"      {tag}  {clip(d, width - 36)}")
        for pre in sorted(by_child.get(code, [])):
            p = nodes[pre]
            tag = "tested" if p["tested"] else "NEVER TESTED"
            out.append(f"      <- {pre:<12} {STATUS[p['status']][0]} {tag:<12} "
                       f"{clip(p['description'], width - 46)}")
        if code in unknown:
            out.append(f"      <- prerequisites not cached; set LEARNING_COMMONS_API_KEY "
                       f"to look them up")

    out += ["", "-" * width,
            "mastery   n   90% interval   confidence",
            "-" * width]
    for code in sorted(nodes, key=lambda c: (-nodes[c]["n"], c)):
        nd = nodes[code]
        if nd["n"] == 0 and not nd["tested"]:
            continue
        out.append(f"{code:<12} {pct(nd['point']):>5}  {nd['n']:>2}   "
                   f"{pct(nd['lo']):>4} - {pct(nd['hi']):<5}  "
                   f"{confidence_bar(nd['n'], nd['lo'], nd['hi'])}")
    never = [c for c, nd in nodes.items() if nd["n"] == 0 and not nd["tested"]]
    if never:
        out += ["", f"Never tested ({len(never)}), reachable as prerequisites:",
                "  " + ", ".join(sorted(never))]
    if unknown:
        out += ["", "Prerequisites unknown for: " + ", ".join(sorted(set(unknown))),
                "  cached graph does not reach past these; a free "
                "LEARNING_COMMONS_API_KEY extends it."]
    out += ["", "Learning Commons knowledge graph, CC BY 4.0."]
    return "\n".join(out)


def escape(s):
    return (str(s or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))


def clip(s, n):
    """Trim to a word boundary rather than mid-word."""
    s = str(s or "")
    if len(s) <= n:
        return s
    cut = s[:n].rsplit(" ", 1)[0]
    return (cut or s[:n]) + "..."


def pct(x):
    return "-" if x is None else f"{round(x * 100)}%"


def bar(nd):
    if nd["n"] == 0:
        return "no questions yet"
    return (f"{nd['right']}/{nd['n']} correct   "
            f"mastery {pct(nd['point'])} ({pct(nd['lo'])}-{pct(nd['hi'])})   "
            f"confidence {confidence_bar(nd['n'], nd['lo'], nd['hi'])}")


def to_dot(rec, cache=None):
    """Graphviz, for when a picture is wanted: `python3 graph.py --dot | dot -Tpng -o g.png`"""
    nodes, edges, _ = build(rec, cache)
    colour = {"mastered": "#2e7d32", "ok": "#00796b", "shaky": "#f9a825", "weak": "#c62828",
              "untested": "#9e9e9e"}
    lines = ["digraph skills {", '  rankdir=BT; node [shape=box, style="rounded,filled", '
             'fontname="Helvetica", fontsize=10, fillcolor=white];']
    for code, nd in nodes.items():
        label = f"{code}\\n{nd['right']}/{nd['n']}" if nd["n"] else f"{code}\\nuntested"
        lines.append(f'  "{code}" [label="{label}", color="{colour[nd["status"]]}", '
                     f'penwidth={3 if nd["tested"] else 1}];')
    for pre, child in edges:
        lines.append(f'  "{pre}" -> "{child}";')
    lines.append("}")
    return "\n".join(lines)


# CCSS codes start with the grade, which gives a free vertical layout: earlier
# grades at the bottom, so every prerequisite arrow points upward and the
# picture reads as a progression. Written directly rather than through Graphviz,
# which is not installed by default and is a lot to ask for one diagram.
COLOUR = {"shaky": "#b26a00", "weak": "#c62828", "untested": "#8a8a8a",
          "mastered": "#2e7d32", "ok": "#00796b"}
FILL = {"shaky": "#fff8e1", "weak": "#ffebee", "untested": "#f4f4f4",
        "mastered": "#e8f5e9", "ok": "#e0f2f1"}


def _ranks(nodes, edges):
    """Row per node: one below the deepest prerequisite that is actually drawn.

    Laying rows out by CCSS grade looks sensible but puts 8 of 16 edges flat
    along a row, where they overlap each other and hide their arrowheads behind
    the boxes - 7.NS.A.3 alone has three grade-7 prerequisites. Ranking by depth
    in the dependency chain guarantees every edge points strictly upward.
    """
    pres = {}
    for pre, child in edges:
        pres.setdefault(child, []).append(pre)
    rank, visiting = {}, set()

    def depth(code):
        if code in rank:
            return rank[code]
        if code in visiting:          # the Coherence Map should be acyclic; do not hang if not
            return 0
        visiting.add(code)
        r = 0
        for pre in pres.get(code, []):
            if pre in nodes:
                r = max(r, depth(pre) + 1)
        visiting.discard(code)
        rank[code] = r
        return r

    for code in nodes:
        depth(code)
    return rank


def _order_rows(rows, edges, passes=4):
    """Reduce crossings: repeatedly place each node near the average position of
    the nodes it connects to in the row below."""
    pos = {}
    for r in rows:
        for i, c in enumerate(rows[r]):
            pos[c] = i
    nbr = {}
    for pre, child in edges:
        nbr.setdefault(child, []).append(pre)
        nbr.setdefault(pre, []).append(child)
    for _ in range(passes):
        for r in sorted(rows):
            def key(c):
                ns = [pos[n] for n in nbr.get(c, []) if n in pos]
                return (sum(ns) / len(ns)) if ns else pos[c]
            rows[r] = sorted(rows[r], key=key)
            for i, c in enumerate(rows[r]):
                pos[c] = i
    return rows


def _parts(code, comp, components):
    """(name, right, asked, streak_days) per part of a standard, failing parts first.
    asked == -1 marks a part only a drawing or an explanation can show."""
    mine = {cid: r for cid, r in (comp or {}).items() if r["standard"] == code}
    rowset = [(r["name"], r["right"], r["right"] + r["wrong"], r.get("streak_days", 0))
              for r in mine.values()]
    askable = prereq.sheet_components(code)
    for cid, desc in components.items():
        if cid not in mine:
            rowset.append((desc, 0, 0 if cid in askable else -1, 0))
    return sorted(rowset, key=lambda z: (z[2] <= 0, -(z[2] - z[1]), z[0] or ""))


def _distinct_labels(names):
    """Sibling parts often open with the same words ("Explain patterns in the ...",
    "Find quotients with ..."), so clipped to fit a card they read identically.
    Drop the opening words a part shares with any sibling, keeping what differs."""
    words = [str(n or "").split() for n in names]
    out = []
    for i, w in enumerate(words):
        shared = 0
        for j, v in enumerate(words):
            if i != j:
                k = 0
                while k < min(len(w), len(v)) and w[k].lower() == v[k].lower():
                    k += 1
                shared = max(shared, k)
        # Only when it leaves something to read; a one-word tail says too little.
        out.append("…" + " ".join(w[shared:]) if shared >= 2 and len(w) - shared >= 2
                   else " ".join(w))
    return out


def _part_lines(out, x, y, w, rows, label_chars=30):
    """One line per part: status dot, name, score. 14 px each, starting at y."""
    labels = _distinct_labels([r[0] for r in rows])
    for j, ((_, k, n, days), name) in enumerate(zip(rows, labels)):
        ty = y + j * 14
        # n == -1: a part only a drawing or an explanation can show; never asked
        # on a sheet by design, so grey and labelled as such, not "untested".
        st = planner_status({"right": k, "wrong": max(n, 0) - k, "streak_days": days})
        out.append(f'<circle cx="{x + 13:.0f}" cy="{ty + 5:.0f}" r="3.6" '
                   f'fill="{COLOUR[st]}"/>')
        tail = f"{k}/{n}" if n > 0 else ("untested" if n == 0 else "not on sheet")
        out.append(f'<text x="{x + 22:.0f}" y="{ty + 9:.0f}" font-size="9.5" '
                   f'fill="#3c4043">{escape(clip(name, label_chars - (6 if n < 0 else 0)))}</text>')
        out.append(f'<text x="{x + w - 7:.0f}" y="{ty + 9:.0f}" text-anchor="end" '
                   f'font-size="9" fill="{COLOUR[st]}">{tail}</text>')


def to_svg(rec, comp=None, cache=None, box=(206, 48), gap=(26, 86), pad=28):
    nodes, edges, unknown = build(rec, cache)
    # Components of each tested standard, so the picture shows which PART is
    # weak rather than only the standard's headline score.
    parts = {}
    for code, nd in nodes.items():
        if not nd["tested"]:
            continue
        rowset = _parts(code, comp, prereq.components_of(code))
        if rowset:
            parts[code] = rowset
    if not nodes:
        return '<svg xmlns="http://www.w3.org/2000/svg" width="200" height="40"></svg>'
    bw, bh = box
    unknown_set = set(unknown)
    rank = _ranks(nodes, edges)
    rows = {}
    for code in nodes:
        rows.setdefault(rank[code], []).append(code)
    for r in rows:
        rows[r] = sorted(rows[r])
    rows = _order_rows(rows, edges)

    order = sorted(rows, reverse=True)           # deepest dependents at the top
    pos = {}
    width = pad * 2 + max(len(v) for v in rows.values()) * (bw + gap[0]) - gap[0]
    def node_h(code):
        return bh + (14 * len(parts[code]) + 8 if code in parts else 0)

    row_h = {rk: max(node_h(c) for c in rows[rk]) for rk in rows}
    y = pad
    for rk in order:
        codes = rows[rk]
        span = len(codes) * (bw + gap[0]) - gap[0]
        x0 = (width - span) / 2
        for i, code in enumerate(codes):
            pos[code] = (x0 + i * (bw + gap[0]), y)
        y += row_h[rk] + gap[1]
    height = y - gap[1] + pad + 26

    out = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{width:.0f}" height="{height:.0f}" '
           f'viewBox="0 0 {width:.0f} {height:.0f}" font-family="Helvetica,Arial,sans-serif">',
           '<defs><marker id="a" markerWidth="9" markerHeight="7" refX="8" refY="3.5" '
           'orient="auto"><polygon points="0 0, 9 3.5, 0 7" fill="#9aa0a6"/></marker></defs>',
           f'<rect width="{width:.0f}" height="{height:.0f}" fill="#ffffff"/>']
    for pre, child in edges:
        if pre not in pos or child not in pos:
            continue
        x1, y1 = pos[pre][0] + bw / 2, pos[pre][1]
        x2, y2 = pos[child][0] + bw / 2, pos[child][1] + node_h(child)
        out.append(f'<path d="M{x1:.0f},{y1:.0f} C{x1:.0f},{(y1 + y2) / 2:.0f} '
                   f'{x2:.0f},{(y1 + y2) / 2:.0f} {x2:.0f},{y2:.0f}" fill="none" '
                   f'stroke="#9aa0a6" stroke-width="1.2" marker-end="url(#a)"/>')
    for code, (x, y) in pos.items():
        nd = nodes[code]
        c, f = COLOUR[nd["status"]], FILL[nd["status"]]
        sw = 2.6 if nd["tested"] else 1.0
        dash = '' if nd["tested"] else ' stroke-dasharray="4 3"'
        out.append(f'<rect x="{x:.0f}" y="{y:.0f}" width="{bw}" height="{node_h(code):.0f}" '
                   f'rx="7" fill="{f}" stroke="{c}" stroke-width="{sw}"{dash}/>')
        score = (f'{nd["right"]}/{nd["n"]}  {pct(nd["point"])} '
                 f'({pct(nd["lo"])}-{pct(nd["hi"])})' if nd["n"] else "never tested")
        g = prereq.grade_of(code)
        out.append(f'<text x="{x + bw / 2:.0f}" y="{y + 19:.0f}" text-anchor="middle" '
                   f'font-size="13" font-weight="600" fill="#202124">{code}</text>')
        out.append(f'<text x="{x + bw / 2:.0f}" y="{y + 35:.0f}" text-anchor="middle" '
                   f'font-size="10.5" fill="{c}">{score}</text>')
        if g is not None:
            out.append(f'<text x="{x + 7:.0f}" y="{y + 13:.0f}" font-size="9" '
                       f'fill="#9aa0a6">G{g}</text>')
        # A node with no arrows beneath it is not necessarily a foundation - it
        # may just be where the cached map runs out. Say which, or the picture
        # claims the child's weaknesses bottom out here when they may not.
        # One line per component: the part of the standard, and how it scored.
        _part_lines(out, x, y + bh + 4, bw, parts.get(code, []))
        if code in unknown_set:
            cx = x + bw / 2
            yb = y + node_h(code)
            out.append(f'<path d="M{cx:.0f},{yb:.0f} v14" stroke="#bdbdbd" '
                       f'stroke-width="1.2" stroke-dasharray="3 3"/>')
            out.append(f'<text x="{cx:.0f}" y="{yb + 25:.0f}" text-anchor="middle" '
                       f'font-size="9.5" fill="#9aa0a6">prereqs not looked up</text>')
    legend = "  ".join(f"{k}" for k in ("mastered", "ok", "shaky", "weak", "untested"))
    out.append(f'<text x="{pad}" y="{height - 10:.0f}" font-size="11" fill="#5f6368">'
               f'every arrow runs from a prerequisite up to what it supports; rows are '
               f'dependency depth, not grade (G = grade); solid border = tested; '
               f'a dashed stub means the chain continues but has not been looked up; '
               f'dots inside a box are the components of that standard '
               f'&#160;|&#160; {legend}</text>')
    out.append("</svg>")
    return "\n".join(out)


if __name__ == "__main__":
    import sys
    import skills
    rec = skills.record(skills.load_papers())
    if "--dot" in sys.argv:
        print(to_dot(rec))
    elif "--svg" in sys.argv:
        print(to_svg(rec))
    else:
        print(render(rec))


# ---------------------------------------------------------------------------
# A second view: everything laid out by grade, with no edges.
#
# The dependency graph has to be wide, because a row holds every standard at the
# same depth and the arrows need room. That makes it awkward to take in at a
# glance. This one drops the edges entirely and arranges standards by grade and
# domain, which fits a screen and answers a different question: how much of each
# grade has been covered, and how is it going.

def _roster(cache_dir=None):
    import json
    p = (cache_dir or HERE_CACHE) / "syllabus.json"
    if not p.exists():
        return {}, {}
    d = json.loads(p.read_text())
    return d.get("grades", {}), d.get("needs_diagram", {})


HERE_CACHE = __import__("pathlib").Path(__file__).parent / "cache"

# Plain-English names for the cards, so the chart can be read without knowing
# the codes. Anything missing falls back to the standard's own wording.
TOPIC = {
    "5.G.A.1": "Coordinate plane: plotting points",
    "5.G.A.2": "Graphing real-world points",
    "5.G.B.3": "Shape categories and properties",
    "5.G.B.4": "Classifying 2-D shapes",
    "5.MD.A.1": "Converting measurement units",
    "5.MD.C.3": "What volume means",
    "5.MD.B.2": "Line plots with fractions",
    "5.MD.C.4": "Volume by counting cubes",
    "5.MD.C.5": "Volume: length × width × height",
    "5.NBT.A.1": "Place value: ×10 and ÷10",
    "5.NBT.A.2": "Powers of 10, moving the point",
    "5.NBT.A.3": "Reading and comparing decimals",
    "5.NBT.A.4": "Rounding decimals",
    "5.NBT.B.5": "Multi-digit multiplication",
    "5.NBT.B.6": "Long division, 2-digit divisor",
    "5.NBT.B.7": "Decimals: + − × ÷ to hundredths",
    "5.NF.A.1": "Adding and subtracting fractions",
    "5.NF.A.2": "Fraction word problems (+ −)",
    "5.NF.B.3": "A fraction as division (sharing)",
    "5.NF.B.4": "Multiplying fractions",
    "5.NF.B.5": "Multiplying as scaling",
    "5.NF.B.6": "Fraction × word problems",
    "5.NF.B.7": "Dividing with unit fractions",
    "5.OA.A.1": "Order of operations, brackets",
    "5.OA.A.2": "Writing number expressions",
    "5.OA.B.3": "Number patterns and graphs",
    "6.RP.A.1": "What a ratio is",
    "6.RP.A.3.a": "Tables of equivalent ratios",
    "6.RP.A.3.b": "Unit price and speed",
    "6.RP.A.3.d": "Converting units with ratios",
    "6.NS.B.4": "GCF, LCM and factoring sums",
    "6.NS.C.5": "Positive and negative in real life",
    "6.NS.C.6.a": "Opposites on the number line",
    "6.NS.C.7.a": "Inequalities on a number line",
    "6.NS.C.7.b": "Ordering negatives in context",
    "6.NS.C.7.c": "Absolute value as distance",
    "6.NS.C.7.d": "Absolute value vs. order",
    "6.NS.C.8": "Four-quadrant grid and distances",
    "6.EE.A.1": "Exponents",
    "6.EE.A.2.a": "Writing expressions with letters",
    "6.EE.A.2.b": "Naming parts: term, factor, coefficient",
    "6.EE.A.2.c": "Substituting into formulas",
    "6.EE.A.3": "Equivalent expressions (distributing)",
    "6.EE.A.4": "Spotting equivalent expressions",
    "6.EE.B.5": "Checking solutions by substituting",
    "6.EE.B.8": "Inequalities like x > c",
    "6.EE.C.9": "Two variables: tables, graphs, rules",
    "6.G.A.2": "Volume with fractional edges",
    "6.G.A.3": "Polygons on a coordinate grid",
    "6.G.A.4": "Nets and surface area",
    "6.SP.A.1": "Statistical questions",
    "6.SP.A.2": "Center, spread and shape of data",
    "6.SP.A.3": "Mean/median vs. spread",
    "6.SP.B.4": "Dot plots, histograms, box plots",
    "6.SP.B.5": "Summarizing data in context",
    "6.EE.B.6": "Expressions with variables",
    "6.EE.B.7": "One-step equations",
    "6.G.A.1": "Area of triangles and quadrilaterals",
    "6.NS.A.1": "Dividing fractions by fractions",
    "6.NS.B.2": "Long division, multi-digit",
    "6.NS.B.3": "Decimal arithmetic",
    "6.NS.C.6.b": "Quadrants and signs of points",
    "6.NS.C.6.c": "Negatives on a number line",
    "6.RP.A.2": "Unit rates",
    "6.RP.A.3": "Ratio and rate problems",
    "6.RP.A.3.c": "Percent: part and whole",
    "7.EE.B.4": "Writing and solving equations",
    "7.NS.A.1.d": "Adding and subtracting negatives",
    "7.NS.A.2.c": "Multiplying negatives",
    "7.NS.A.2.d": "Fractions to decimals",
    "7.NS.A.3": "Word problems, all four operations",
    "7.RP.A.2": "Proportional relationships",
    "7.RP.A.3": "Multi-step percent problems",
    "7.SP.B.3": "Comparing two data sets",
}
DOMAIN = {
    "OA": "Operations and algebraic thinking", "NBT": "Place value and base ten",
    "NF": "Fractions", "MD": "Measurement and data", "G": "Geometry",
    "NS": "The number system", "RP": "Ratios and proportions",
    "EE": "Expressions and equations", "SP": "Statistics and probability",
}


def _topic_lines(code, roster, width_chars=30, max_lines=2):
    """The card's topic text, wrapped to fit."""
    text = TOPIC.get(code)
    if not text:
        text = next((g[code] for g in roster.values() if code in g), None) or prereq.describe(code) or ""
    words, lines, line = text.split(), [], ""
    for w in words:
        if len(line) + len(w) + 1 > width_chars and line:
            lines.append(line); line = w
        else:
            line = f"{line} {w}".strip()
    lines.append(line)
    if len(lines) > max_lines:
        lines = lines[:max_lines]; lines[-1] = lines[-1][:width_chars - 1].rstrip() + "…"
    return lines


def to_svg_by_grade(rec, comp=None, cache=None, cols=5, card=(200, 78), gap=12, pad=24):
    """Standards grouped by grade then domain, coloured by status. No edges."""
    roster, no_sheet = _roster()
    cw, ch = card

    # Everything worth showing: tested, plus the whole roster so gaps are visible.
    known = {}
    for code, r in rec.items():
        known[code] = r
    for g, codes in roster.items():
        for code in codes:
            known.setdefault(code, None)

    by_grade = {}
    for code in known:
        g = prereq.grade_of(code)
        by_grade.setdefault(g if g is not None else 99, []).append(code)

    def domain(c):
        parts = c.split(".")
        return parts[1] if len(parts) > 1 else ""

    # The parts of each standard, as in graph.svg, so a green card cannot hide a red
    # part. Cached components only: the roster standards never asked would otherwise
    # each cost an API call.
    cached = prereq.load_components()["by_standard"]

    def compact(rows, limit=8):
        # 4.OA.A.3 has 18 parts, most near-duplicates never asked; past `limit`, keep
        # the asked parts by name and fold the rest into one line per kind.
        if len(rows) <= limit:
            return rows
        un = sum(1 for z in rows if z[2] == 0)
        no = sum(1 for z in rows if z[2] < 0)
        return ([z for z in rows if z[2] > 0]
                + ([(f"+{un} more parts", 0, 0, 0)] if un else [])
                + ([(f"+{no} more parts", 0, -1, 0)] if no else []))

    parts = {code: compact(_parts(code, comp, cached.get(code) or {})) for code in known}
    PART_TOP = 58                                  # below the code and two topic lines

    def card_h(code):
        return ch + (14 * len(parts[code]) + 2 if parts[code] else 0)

    width = pad * 2 + cols * (cw + gap) - gap
    y = pad
    blocks = []
    for g in sorted(by_grade):
        codes = sorted(by_grade[g], key=lambda c: (domain(c), c))
        blocks.append(("grade", g, y, len(codes)))
        y += 30
        # keep each domain starting on its own row, so the eye can group them;
        # a row is as tall as its tallest card, which grows with its parts
        rows = []
        for code in codes:
            d = domain(code)
            if not rows or rows[-1][0] != d or len(rows[-1][1]) >= cols:
                rows.append((d, []))
            rows[-1][1].append(code)
        last_domain = None
        for d, row in rows:
            if d != last_domain:
                blocks.append(("domain", d, y, None))
                y += 20
                last_domain = d
            rh = max(card_h(c) for c in row)
            for i, code in enumerate(row):
                blocks.append(("card", code, (pad + i * (cw + gap), y), rh))
            y += rh + gap
        y += 14
    height = y + pad

    out = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height:.0f}" '
           f'viewBox="0 0 {width} {height:.0f}" font-family="Helvetica,Arial,sans-serif">',
           f'<rect width="{width}" height="{height:.0f}" fill="#ffffff"/>']
    for kind, a, b, c in blocks:
        if kind == "grade":
            tested = sum(1 for code in by_grade[a] if code in rec)
            label = f"Grade {a}" if a != 99 else "Other"
            out.append(f'<text x="{pad}" y="{b + 20:.0f}" font-size="15" font-weight="700" '
                       f'fill="#202124">{label}</text>')
            out.append(f'<text x="{pad + 78}" y="{b + 20:.0f}" font-size="11.5" fill="#80868b">'
                       f'{tested} of {c} tested</text>')
            out.append(f'<line x1="{pad}" y1="{b + 27:.0f}" x2="{width - pad}" y2="{b + 27:.0f}" '
                       f'stroke="#e0e0e0"/>')
            continue
        if kind == "domain":
            name = DOMAIN.get(a, "")
            out.append(f'<text x="{pad}" y="{b + 13:.0f}" font-size="11.5" font-weight="600" '
                       f'fill="#5f6368">{escape(a)}{" · " + escape(name) if name else ""}</text>')
            continue
        code, (x, yy), ch = a, b, c
        r = rec.get(code)
        k = r["right"] if r else 0
        n = (r["right"] + r["wrong"]) if r else 0
        # The planner's own status, so the chart says what drives the next
        # sheets: mastered / ok / shaky / weak, with recent answers counting
        # (three right in a row on different days since the last mistake is mastered,
        # once every part of the standard has been asked).
        st = planner_status(r)
        col, fill = COLOUR[st], FILL[st]
        dash = "" if r else ' stroke-dasharray="4 3"'
        out.append(f'<rect x="{x}" y="{yy:.0f}" width="{cw}" height="{ch}" rx="7" '
                   f'fill="{fill}" stroke="{col}" stroke-width="{2.4 if r else 1}"{dash}/>')
        out.append(f'<text x="{x + 10}" y="{yy + 21:.0f}" font-size="12.5" font-weight="600" '
                   f'fill="#202124">{escape(code)}</text>')
        for i, line in enumerate(_topic_lines(code, roster)):
            out.append(f'<text x="{x + 10}" y="{yy + 37 + i * 13:.0f}" font-size="10.5" '
                       f'fill="#3c4043">{escape(line)}</text>')
        if parts[code]:
            out.append(f'<line x1="{x + 8}" y1="{yy + PART_TOP - 5:.0f}" x2="{x + cw - 8}" '
                       f'y2="{yy + PART_TOP - 5:.0f}" stroke="{col}" stroke-opacity="0.25"/>')
            _part_lines(out, x - 3, yy + PART_TOP, cw - 3, parts[code], label_chars=28)
        if n:
            _, lo, hi = wilson(k, n)
            out.append(f'<text x="{x + cw - 10}" y="{yy + 21:.0f}" text-anchor="end" '
                       f'font-size="11" fill="{col}">{k}/{n}</text>')
            streak = r.get("streak", 0)
            run = f" · {streak} in a row" if streak >= 2 else ""
            out.append(f'<text x="{x + 10}" y="{yy + ch - 9:.0f}" font-size="10" fill="{col}">'
                       f'{st}{run}</text>')
            out.append(f'<text x="{x + cw - 10}" y="{yy + ch - 9:.0f}" text-anchor="end" '
                       f'font-size="8.5" fill="#9aa0a6">{pct(lo)}-{pct(hi)}</text>')
        else:
            tag = "no sheet format" if code in no_sheet else "never asked"
            out.append(f'<text x="{x + 10}" y="{yy + ch - 9:.0f}" font-size="10" fill="#9aa0a6">'
                       f'{tag}</text>')
    out.append(f'<text x="{pad}" y="{height - 8:.0f}" font-size="11" fill="#5f6368">'
               f'status is the planner\'s: mastered = every part asked, and right twice with no mistakes or 3 in a row on different days since the last; '
               f'ok = right so far; shaky = one mistake; weak = two or more. Grey % = 90% range over all answers.'
               f'</text>')
    out.append("</svg>")
    return "\n".join(out)
