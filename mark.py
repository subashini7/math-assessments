import json, re, sys
from decimal import Decimal
from fractions import Fraction
# Units the child might write. Longest patterns first, so "cm3" is not read as
# "cm": a volume answer given in cm is a real mistake, not a missing unit, and
# the two have to be told apart. Matched against the answer with spaces removed.
UNITS = [
    (r"(cm3|cm\^?3|cm³|cubiccm|cubiccentimet(er|re)s?)", "cm³"),
    (r"(m3|m\^?3|m³|cubicm|cubicmet(er|re)s?)", "m³"),
    (r"(cm2|cm\^?2|cm²|sqcm|squarecm|squarecentimet(er|re)s?)", "cm²"),
    (r"(m2|m\^?2|m²|sqm|squarem|squaremet(er|re)s?)", "m²"),
    (r"(centimet(er|re)s?|cm)", "cm"),
    (r"(kilomet(er|re)s?|km)", "km"),
    (r"(millilit(er|re)s?|ml)", "ml"),
    (r"(kilograms?|kg)", "kg"),
    (r"(grams?|g)\b", "g"),
    (r"(miles?|mi)", "miles"),
    (r"(met(er|re)s?|m)\b", "m"),
    (r"(minutes?|mins?)", "min"),
    (r"(hours?|hrs?)", "hr"),
    (r"(cups?)", "cups"),
    (r"y(ea)?rs?", "years"),
]
# Spelling variants a spec may use for the same unit.
UNIT_ALIASES = {"mile": "miles", "cup": "cups", "cm3": "cm³", "m2": "m²", "cm2": "cm²"}

_NUM = r"\d+(?:[.,]\d+)?|[.,]\d+"


def _clean(s):
    s = str(s).strip().lower()
    s = s.replace("–", "-").replace("−", "-").replace("—", "-")
    return re.sub(r"\s+", " ", s)


def _strip_unit(s):
    """(rest, unit). Money symbols anywhere; other units only at the end."""
    if "$" in s:
        return s.replace("$", "").strip(), "$"
    if "¢" in s:
        return s.replace("¢", "").strip(), "¢"
    if re.search(r"\dc$", s):
        return s[:-1].strip(), "¢"
    flat = s.replace(" ", "")
    for pat, name in UNITS:
        m = re.search(pat + r"$", flat)
        if m and m.start() > 0 and re.search(r"[\d)]$", flat[:m.start()]):
            # Remove the same number of non-space characters from the spaced
            # string, so "4 1/12 m" keeps its space and stays a mixed number.
            n = len(flat) - m.start(); i = len(s)
            while n:
                i -= 1
                if s[i] != " ": n -= 1
            return s[:i].strip(), name
    return s, None


def _number(s):
    """Exact value of an integer, decimal (point or comma), fraction or mixed number."""
    s = s.strip()
    neg = s.startswith("-")
    if neg: s = s[1:].strip()
    f = lambda t: Fraction(Decimal(t.replace(",", ".")))
    m = re.fullmatch(rf"({_NUM})", s)
    if m: v = f(m[1])
    elif (m := re.fullmatch(r"(\d+)\s*/\s*(\d+)", s)) and int(m[2]):
        v = Fraction(int(m[1]), int(m[2]))
    elif (m := re.fullmatch(r"(\d+)\s+(\d+)\s*/\s*(\d+)", s)) and int(m[3]):
        v = int(m[1]) + Fraction(int(m[2]), int(m[3]))
    else:
        return None
    return -v if neg else v


def _pair(s):
    m = re.fullmatch(r"\(?\s*(-?\s*[\d.]+)\s*,\s*(-?\s*[\d.]+)\s*\)?", s)
    if not m: return None
    a, b = _number(m[1].replace(" ", "")), _number(m[2].replace(" ", ""))
    return None if a is None or b is None else (a, b)


def parse(s, pair=False):
    """(key, unit). The key is ("num", Fraction), ("pair", (x, y)) or ("text", str).

    `pair` says the expected answer is a coordinate pair; only then is "5,3"
    two numbers. Otherwise a comma between digits is a decimal point - this
    child writes 3,75 for 3.75.
    """
    s = _clean(s)
    rest, unit = _strip_unit(s)
    if pair and (v := _pair(rest)) is not None:
        return ("pair", v), unit
    if (v := _number(rest)) is not None:
        return ("num", v), unit
    # Words and expressions: compare the writing, ignoring spaces and the
    # different ways of writing a times sign. The unit stays in the text.
    return ("text", re.sub(r"\s+", "", s).replace("×", "*").replace("·", "*")), None


def _is_pair(a):
    return bool(re.fullmatch(r"\s*\(.*,.*\)\s*", str(a)))


_LETTER_LIST = re.compile(r"\s*[A-H](\s*(,|and|&)?\s*[A-H])*\s*")


def _letters(s):
    """The set of shape labels in "A, C", "C and A" or "AC"; None if not letters."""
    t = re.sub(r"\bAND\b|&|,|\s", "", str(s).upper())
    return frozenset(t) if t and re.fullmatch(r"[A-H]+", t) else None


def _expr_values(s):
    """(variable, values at a few points) for an expression in one letter such as
    "2m – 4", "L = (2m) - 4" or "7p+45"; None for anything else."""
    t = _clean(s).replace("×", "*").replace("·", "*")
    t = re.sub(r"^[a-z]\s*=\s*", "", t)                 # "L = ..." names the answer
    if not re.fullmatch(r"[0-9a-z+\-*/(). ]+", t) or re.search(r"[a-z]{2,}", t):
        return None
    names = set(re.findall(r"[a-z]", t))
    if len(names) != 1:
        return None
    t = re.sub(r"(\d|\))\s*(?=[a-z(])", r"\1*", t)      # 2m -> 2*m, 2(m) -> 2*(m)
    t = re.sub(r"([a-z])\s*(?=[\d(])", r"\1*", t)       # m2 -> m*2
    try:
        code = compile(t, "<answer>", "eval")
        var = names.pop()
        return var, tuple(eval(code, {"__builtins__": {}}, {var: Fraction(v)}) for v in (2, 3, 7))
    except Exception:
        return None


def same(a, b, units=True):
    """Is reading `a` the same answer as `b` (an accepted or known-wrong form)?

    With units=False only the quantity is compared, so the unit check in judge()
    can say exactly what was wrong with the unit.
    """
    if re.search(r"[a-z]", str(b)) and re.search(r"[+\-−–×*(=]", str(b)):
        # An expression with a variable: equivalent if it gives the same value
        # for several values of the variable, however it is written. Only when
        # the expected answer has a variable - "4 × (9 + 6), do not work it out"
        # must stay a comparison of the writing, or 60 would count as right.
        ea, eb = _expr_values(a), _expr_values(b)
        if ea and eb:
            return ea == eb
    if _LETTER_LIST.fullmatch(str(b)):
        # "Which shapes ...? Write the letters": order and separators do not matter.
        return _letters(a) is not None and _letters(a) == _letters(b)
    pair = _is_pair(b)
    (ka, ua), (kb, ub) = parse(a, pair), parse(b, pair)
    if ka[0] != kb[0]: return False
    va, vb = ka[1], kb[1]
    if ka[0] == "num" and ua in ("$", "¢") and ub in ("$", "¢"):
        # Convert cents only when both sides are money: "20c" for 20 scoops is
        # a stray letter, not 20 cents.
        if ua == "¢": va, ua = va / 100, "$"
        if ub == "¢": vb, ub = vb / 100, "$"
    return va == vb and (not units or ua == ub or ua is None or ub is None)


NEEDS_MODEL = "-> send working to model"


def judge(q, r):
    """Mark one answer. `diag` is NEEDS_MODEL when the code cannot explain it."""
    ok = any(same(r, a, units=False) for a in q["accept"])
    got_unit = parse(r)[1]
    want_unit = (q.get("unit") or "").strip() or None
    want_unit = UNIT_ALIASES.get(want_unit, want_unit)
    if want_unit is None:
        # Older specs leave `unit` empty; the expected answer itself says it.
        want_unit = parse(q["answer"], _is_pair(q["answer"]))[1]
    unit_ok = True
    unit_note = None
    if q["unit_required"]:
        if got_unit is None:
            unit_ok, unit_note = False, "Correct number but no units written"
        elif want_unit and got_unit != want_unit and not (want_unit, got_unit) in (("$", "¢"), ("¢", "$")):
            # Writing cm where cm³ is wanted is a different mistake from writing
            # nothing: the child measured the wrong kind of quantity.
            unit_ok = False
            unit_note = f"Gave the answer in {got_unit} where it should be {want_unit}"
    diag = None
    if not ok:
        diag = next((d for w, d in q["common_wrong_answers"].items() if same(r, w)), None) or NEEDS_MODEL
    elif not unit_ok:
        diag = unit_note
    return bool(ok and unit_ok), diag


def mark(spec, readings):
    out = []
    for q in spec["questions"]:
        r = readings[q["id"]]
        right, diag = judge(q, r)
        out.append({"id": q["id"], "reading": r, "expected": q["answer"],
                    "right": right, "diagnosis": diag})
    return out


if __name__ == "__main__":
    spec = json.load(open(sys.argv[1])); readings = json.loads(sys.argv[2])
    rows = mark(spec, readings)
    for row in rows:
        print(f"{row['id']:>3}  read {row['reading']:>8}  expected {row['expected']:>8}  "
              f"{'✓' if row['right'] else '✗'}  {row['diagnosis'] or ''}")
    print("score", sum(r["right"] for r in rows), "/", len(rows))
