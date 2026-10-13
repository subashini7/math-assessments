"""Generate fixed-format math practice tests (PDF) plus a matching JSON spec.

Each PDF: page 1 = 10 questions in a fixed 2x5 grid with corner markers, a QR
code identifying the test, a working area and a separate answer box per
question. Page 2 = answer key. The JSON describes questions, accepted answers,
skills and the exact answer/working regions so an app can crop and mark them.
"""
from decimal import Decimal as D
from fractions import Fraction as F
import json, sys

from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from reportlab.platypus import Paragraph, Table, TableStyle
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib import colors
from reportlab.graphics.barcode import qr
from reportlab.graphics.shapes import Drawing
from reportlab.graphics import renderPDF

# Every sheet lives once, flat in tests/, and is never overwritten with different
# printed content. Its QR payload is `mpt:test=<letter>&h=<fingerprint>`, where
# the fingerprint covers exactly what is printed on page 1 - title, question text
# and the box layout the crops rely on. Re-running the generator therefore
# refreshes answers and known mistakes in a spec (page 1 comes out identical)
# but refuses to change a sheet that may already be in a child's hands.
import hashlib, io, re, pathlib

OUT = pathlib.Path("tests")
LEGACY = OUT / "legacy"
OUT.mkdir(parents=True, exist_ok=True)


def legacy_letters():
    return {m.group(1) for f in LEGACY.rglob("Math_Practice_Test_*.json")
            if (m := re.fullmatch(r"Math_Practice_Test_(\w+)\.json", f.name))}


def fingerprint(spec):
    printed = [spec["title"]] + [[q["number"], q["text"], q["regions"]]
                                 for q in spec["questions"]]
    return hashlib.sha1(json.dumps(printed, sort_keys=True).encode()).hexdigest()[:8]

def usd(x):
    return f"${D(x).quantize(D('0.01'))}"

def dec(x):
    return format(D(x).normalize(), "f")

# Skill references (Learning Commons learning component IDs, CCSS codes)
SK = {
    "sub":  ("Subtract multi-digit decimals", "6.NS.B.3", ["a58918aa-f725-5a4c-a902-decd4a759336"]),
    "mul":  ("Multiply multi-digit decimals", "6.NS.B.3", ["e14eddf0-cf6b-5692-ab30-81f5995f4754"]),
    "add":  ("Add multi-digit decimals", "6.NS.B.3", ["d04b3e78-76db-568d-aeb2-b575eeac1664"]),
    "divw": ("Divide a decimal by a whole number", "6.NS.B.3", ["0c3f03b8-3989-5489-aa86-b9a63953e545"]),
    "whole": ("Find the whole given a part and the percent", "6.RP.A.3.c", ["e6525dd8-5e57-5c8a-abee-57f64d1c9eb4"]),
    "pct":  ("Solve multi-step percent problems", "7.RP.A.3", ["fda5f0e0-0366-5113-931b-3d9930bdfb5a"]),
    # A change-from-$10 problem multiplies, adds and subtracts, so it is evidence
    # about all three real-world components rather than one.
    "money": ("Multi-step money problem with decimals", "7.NS.A.3",
              ["29a9858d-11e0-5445-9b49-f5eb46ce5341",
               "1bff6614-a6c0-5ee1-84a5-0da4f870a38f",
               "39612eaf-3eed-57be-96d2-4ac4abda7d59"]),
    "eqn":  ("Write and solve an equation from a word problem", "7.EE.B.4",
             ["108e49e3-c3ca-58ed-a70d-95086aa90c52", "ffdefe1f-e62c-5137-89c4-ef901293bfe8"]),

    # Grade 5, one entry per major domain: OA, NBT, NF, MD, G. These are the
    # prerequisites the graph keeps surfacing as never tested, so tests C and D
    # exist to put a floor under the grade 6-7 work rather than to stretch it.
    "g5paren": ("Evaluate expressions with parentheses", "5.OA.A.1",
                ["9355ee95-a7a5-5a41-89e1-8ffaef80af0b"]),   # not nested
    "g5cmp":   ("Compare decimals to thousandths", "5.NBT.A.3",
                ["b9d27304-5ca2-57b9-968d-e5c946985513"]),
    "g5mulw":  ("Multiply multi-digit whole numbers", "5.NBT.B.5",
                ["c944c44a-afc2-5b4c-8e61-a4a8332496e0"]),
    "g5divw":  ("Divide with two-digit divisors", "5.NBT.B.6",
                ["e8d8c43a-3608-51dd-86ad-db49bcafef64",
                 "05283aa2-d294-5f59-93ee-ac361e3a10f7"]),
    "g5decadd": ("Add decimals to hundredths", "5.NBT.B.7",
                 ["425dce77-599d-5912-9e92-0802ec13cb68"]),
    "g5decsub": ("Subtract decimals to hundredths", "5.NBT.B.7",
                 ["445dd0dd-00aa-5fef-879e-58f62fd1b8db"]),
    "g5fadd":  ("Add fractions with unlike denominators", "5.NF.A.1",
                ["d022d8d2-37f6-5ce9-bb02-e000d731aba0"]),
    "g5fsub":  ("Subtract fractions with unlike denominators", "5.NF.A.1",
                ["089c550e-f3a4-5ea2-959a-34e267c3e374"]),
    "g5fmul":  ("Multiply a fraction by a fraction", "5.NF.B.4",
                ["4aeee2dd-3e67-5d7e-b843-39650a018660"]),
    "g5fdiv":  ("Divide with unit fractions", "5.NF.B.7",
                ["bfa79064-fe1e-5430-81de-c4155d27d0b4"]),
    "g5conv":  ("Convert measurement units", "5.MD.A.1",
                ["783e04ae-9b0c-5680-9b1a-7084998118c9"]),   # larger -> smaller
    "g5vol":   ("Find volume by multiplying edge lengths", "5.MD.C.5",
                ["f6cc98df-8d45-5acc-868f-9fd3fa9f58e5"]),   # real-world
    # Tests E and F: one entry per previously untested grade-5 component, so the
    # record can tell which PART of each standard the evidence covers.
    "g5paren_nest": ("Evaluate expressions with nested parentheses", "5.OA.A.1",
                     ["79506838-311e-5599-a93e-a9d03c0d80ab"]),
    "g5mul33": ("Multiply 3-digit by 3-digit whole numbers", "5.NBT.B.5",
                ["f71f6845-7313-58e0-888a-58cd23fb6266"]),
    "g5mul24": ("Multiply 2-digit by 4-digit whole numbers", "5.NBT.B.5",
                ["39c3502c-ceeb-583a-aad8-de683defa923"]),
    "g5mul34": ("Multiply 3-digit by 4-digit whole numbers", "5.NBT.B.5",
                ["39865eff-a84f-5354-b603-13ad5b99dd9f"]),
    "g5decmul": ("Multiply decimals to hundredths", "5.NBT.B.7",
                 ["486045b7-a4dd-591f-a78e-3669cc0a8352"]),
    "g5decdiv": ("Divide decimals to hundredths", "5.NBT.B.7",
                 ["90b36ead-9116-53a0-9331-c9dd7cb6b4c1"]),
    "g5mixadd": ("Add mixed numbers with unlike denominators", "5.NF.A.1",
                 ["d2565c2d-3930-54d3-864e-e532fd65cf6c"]),
    "g5mixsub": ("Subtract mixed numbers with unlike denominators", "5.NF.A.1",
                 ["3f8f80e7-a5c3-56e5-bf2d-90c5bb5f4f08"]),
    "g5conv_up": ("Convert from a smaller unit to a larger unit", "5.MD.A.1",
                  ["0c81b764-6a02-55dc-b60e-2d7d9806599a"]),
    "g5conv_multi": ("Use conversions in a multi-step problem", "5.MD.A.1",
                     ["0013fbee-3e76-500f-9978-42aa1a65f105"]),
    "g5vol_math": ("Volume in a mathematical problem", "5.MD.C.5",
                   ["96b4f4dc-dcd9-5aba-9cb0-97c1d5b77cab"]),
    "g5coord_origin": ("Identify the origin", "5.G.A.1",
                       ["7e59ad79-91b7-53a7-98ec-c85624c7fc75"]),
    "g5coord_x": ("Interpret the x-coordinate as horizontal distance", "5.G.A.1",
                  ["9a9aba52-8867-53e9-b129-9bdb51a5442b"]),
    "g5coord_y": ("Interpret the y-coordinate as vertical distance", "5.G.A.1",
                  ["ccfcad8c-5c0e-5b3e-8c98-78b149ecdd97"]),
    "g5coord_plot": ("Plot a point from an ordered pair", "5.G.A.1",
                     ["9f6772f5-1115-58c8-b53d-b5f26ccd0c9d"]),
    "g5coord": ("Name a point on the coordinate plane", "5.G.A.1",
                ["cf895e10-7702-59bb-9bc6-11e262f4c2f6",
                 "d94abe72-3f88-5c8f-9fd5-40a0bd9471ec"]),
    # Test G: from `skills.py --plan` - failures, their prerequisites, the
    # untested place-value standards, and two grade 6/7 readiness checks.
    "g5vol_add": ("Volume of two boxes joined together", "5.MD.C.5",
                  ["f6cc98df-8d45-5acc-868f-9fd3fa9f58e5"]),
    "g6div": ("Divide a 4-digit number by a 2-digit number", "6.NS.B.2",
              ["019a93e7-1877-5e9b-b4b3-476f201fccc8",
               "fa745fbb-4e7c-54e0-aa3d-a89ab5e9cbe3"]),
    "g5pv10": ("A digit is worth 10 times the place to its right", "5.NBT.A.1",
               ["ba0b5da7-336a-54af-bc1d-c4fbceb2df62"]),
    "g5pow10": ("Divide a decimal by a power of 10", "5.NBT.A.2",
                ["14c9562d-c985-5d98-8fe5-a8551e0a20ff",
                 "39c782cc-8c89-5974-98b8-a3158125e227"]),
    "g5round": ("Round a decimal to the nearest hundredth", "5.NBT.A.4",
                ["6a3040b7-8da5-55ab-8b46-29194e8d5143"]),
    "g6eqn": ("Solve x + p = q with fractions", "6.EE.B.7",
              ["1981017a-4fca-5f84-9294-9441faf647db"]),
    "g7rat": ("Add rational numbers using properties of operations", "7.NS.A.1.d",
              ["685131ac-6579-5a09-b675-995525838be5"]),
    # Test H: the next picks down the same plan, with Test G's standards set aside.
    "g5fasdiv": ("A fraction as division in a sharing problem", "5.NF.B.3",
                 ["35bc1efc-c989-50af-b620-a7bd77f2f808",
                  "26645597-c6a9-5497-b3a2-63f304ab1de1"]),
    "g5scale": ("Multiplication as scaling", "5.NF.B.5",
                ["18ed149f-cd3e-5125-a81b-506b27e3af1f"]),
    "g5fword_sub": ("Fraction subtraction word problem", "5.NF.A.2",
                    ["ed662f1f-210b-5895-8841-60c021a792c2"]),
    "g6expr": ("Write an expression with a variable for a real-world problem", "6.EE.B.6",
               ["60a51673-b0e6-57d6-840c-64a3c5b61cc0"]),
    "g6tri": ("Area of a triangle in a real-world problem", "6.G.A.1",
              ["ae975d69-8c4a-580b-aba0-7d9089b3393b"]),
    "g7ratmul": ("Multiply rational numbers using properties of operations", "7.NS.A.2.c",
                 ["54a463dd-df6b-5ace-afb5-b3b179799e8e"]),
    # Tests I and J: the plan after G and H were marked, then the next picks.
    "g5fmulword": ("Fraction times a mixed number in a real-world problem", "5.NF.B.6",
                   ["354638aa-87ee-5083-91a8-817370e282d6"]),
    "g5expr": ("Write a numerical expression with grouping symbols", "5.OA.A.2",
               ["4f28828c-0dd5-5c91-9f0c-8044d2b44890"]),
    "g6eqn_px": ("Solve px = q", "6.EE.B.7",
                 ["e50eda80-7ed8-5b93-8d57-6608093cea34"]),
    "g6ratio": ("Ratio reasoning in a real-world problem", "6.RP.A.3",
                ["5b9cd29a-a10c-5d41-af27-9d632630c4db"]),
    "g7prop": ("Recognize a proportional relationship", "7.RP.A.2",
               ["b02c3de8-7535-5bfc-8e3f-8437bc32a140"]),
    "g5pow10_mul": ("Multiply a decimal by a power of 10", "5.NBT.A.2",
                    ["14c9562d-c985-5d98-8fe5-a8551e0a20ff",
                     "53dba7fb-c548-5f5b-88cd-e657ec2114d7"]),
    "g5fword_add": ("Fraction addition word problem", "5.NF.A.2",
                    ["4b749054-84a9-5279-bb7c-9ac485005421"]),
    "g5coord_move": ("Interpret both coordinates as moves from the origin", "5.G.A.1",
                     ["cf895e10-7702-59bb-9bc6-11e262f4c2f6"]),
    # Tests K and L.
    "divd": ("Divide multi-digit decimals", "6.NS.B.3", ["3b40f296-3bd8-5986-b5a4-52cb04f8c7eb"]),
    "g6expr_var": ("Use a variable for an unknown number in an expression", "6.EE.B.6",
                   ["12b69651-752f-5e48-b838-0c669df35b64"]),
    "g6pct_of": ("Find a percent of a quantity", "6.RP.A.3.c", ["c75962da-9a8e-53a7-81cc-b46d56f5100e"]),
    "g6quad": ("Area of a quadrilateral", "6.G.A.1", ["0d09acef-0351-5d6e-8d35-ec2a950c1cf5"]),
    "g5pv10th": ("A digit is worth 1/10 of the place to its left", "5.NBT.A.1",
                 ["051034c9-6867-50df-81ba-8a5dc6629e8e"]),
    # Test M: the standards that need a picture. Each key names only the
    # components a written answer can show - reading a line plot, not making
    # one; reading a grid, not plotting on it - so the record does not claim
    # the drawing skills were tested.
    "g5volunit": ("Volume is measured in cubic units", "5.MD.C.3",
                  ["b39daa6d-6ef9-5322-9331-d38a806b52ec"]),
    "g5patterns": ("Ordered pairs from two number patterns", "5.OA.B.3",
                   ["8a9af9bf-82b8-5b6a-a19b-274dca8e60a0", "20eff432-6538-5c5a-862a-cc9e7c5275a6"]),
    "g5cubes": ("Volume by counting unit cubes", "5.MD.C.4", ["7f339f4c-abc1-50e7-a0f3-448af44eabec"]),
    "g5shapeattr": ("Attributes of a category apply to its subcategories", "5.G.B.3",
                    ["51e2d683-9271-50f3-8bab-f3d5766156fd"]),
    "g5shapeclass": ("Classify quadrilaterals by their properties", "5.G.B.4",
                     ["175a45df-f09a-50cd-b5f3-54826ac750a7"]),
    "g5lineplot": ("Use fraction operations on a line plot", "5.MD.B.2",
                   ["fcae5c49-fbc6-5f91-990b-7a786b798824"]),
    "g5gridread": ("Interpret coordinates of points in context", "5.G.A.2",
                   ["d2cd8103-3cd7-50de-bb43-390aeff1de3d"]),
    # Tests N, O and P: the never-asked grade-6 standards in the batch plan.
    "g6ratio_write": ("Write a ratio using ratio language", "6.RP.A.1",
                      ["6e6acf93-1f84-564c-8f6f-22c206e5f633", "70393172-f85d-520e-86d2-27ef4b1966d0"]),
    "g6volfrac": ("Volume of a box with a fractional edge (V = lwh)", "6.G.A.2",
                  ["319c693b-b89f-5532-8d83-d3e00a97dce3"]),
    "g6coef": ("Identify the coefficient in an expression", "6.EE.A.2.b",
               ["adfe0503-3bf5-5312-898c-aa649df77f3f"]),
    "g6exp": ("Evaluate an expression with whole-number exponents", "6.EE.A.1",
              ["fe47029d-1ca7-54ae-adb2-098430e3d2a7"]),
    "g6statq": ("Identify a statistical question", "6.SP.A.1",
                ["3fd3c652-c7ac-5615-b8b7-50ff7718d89a"]),
    "g6unitrate": ("Find a unit rate from a real-world ratio", "6.RP.A.2",
                   ["b9b94f31-b58b-5e26-9efe-680b167046ba"]),
    "g6fdivword": ("Divide a fraction by a fraction in a word problem", "6.NS.A.1",
                   ["133abb93-2720-50fc-a417-2fb6d67d32c5", "bc5dfb39-c4f5-5c20-acd5-13e303f5bace"]),
    "g6expr_write": ("Write an expression from a phrase with a letter", "6.EE.A.2.a",
                     ["16e16ca9-6704-56a1-b0f9-04d9fd582f4a"]),
    "g6spread": ("Describe the spread of a data set", "6.SP.A.2",
                 ["ee7501cd-3428-5e0b-944e-8ccaba003efd"]),
}


def mixed(f):
    """A Fraction written the way a child would: 3 5/6 rather than 23/6."""
    f = F(f)
    if f.denominator == 1:
        return str(f.numerator)
    whole, rem = divmod(f.numerator, f.denominator)
    return f"{whole} {rem}/{f.denominator}" if whole else f"{rem}/{f.denominator}"


def frac(f):
    """A Fraction as the child would write it: 3/10, or a whole number."""
    f = F(f)
    return str(f.numerator) if f.denominator == 1 else f"{f.numerator}/{f.denominator}"

def Q(text, answer, accept, unit_required, work, skill, unit=None, figure=None):
    """`figure` is data for a small drawing in the question box (see draw_figure);
    it goes into the spec as well, so a diagnosis can refer to what was shown."""
    return dict(text=text, answer=answer, accept=accept, unit=unit,
                unit_required=unit_required, working=work, skill=skill, figure=figure)

# Geometry the figure questions compute their answers from.
def _vec(a, b):
    return (b[0] - a[0], b[1] - a[1])


def _parallel(u, v):
    return abs(u[0] * v[1] - u[1] * v[0]) < 1e-9


def is_parallelogram(pts):
    """Both pairs of opposite sides parallel."""
    s = [_vec(pts[i], pts[(i + 1) % 4]) for i in range(4)]
    return _parallel(s[0], s[2]) and _parallel(s[1], s[3])


def cubes_visible(l, w, h):
    """Cubes with at least one face showing (front, top or right) in draw_figure's view."""
    return l * w * h - (l - 1) * (w - 1) * (h - 1)



def test_a():
    qs = []
    v = D("10.4") - D("6.785")
    qs.append(Q("Work out 10.4 – 6.785", dec(v), [dec(v)], False, "10.400 – 6.785 (fill the gaps with zeros)", "sub"))
    v = D("3.6") * 7
    qs.append(Q("Work out 3.6 × 7", dec(v), [dec(v)], False, "36 × 7 = 252, one decimal place, so 25.2", "mul"))
    v = D("0.25") * D("1.6")
    qs.append(Q("Work out 0.25 × 1.6", dec(v), [dec(v), "0.40", "0.400"], False, "25 × 16 = 400, three decimal places, so 0.400 = 0.4", "mul"))
    v = D("17.25") + D("8.9") + D("0.65")
    qs.append(Q("Work out 17.25 + 8.9 + 0.65", dec(v), [dec(v), "26.80"], False, "Line up the decimal points: 17.25 + 8.90 + 0.65", "add"))
    v = D("9.36") / 4
    qs.append(Q("Work out 9.36 ÷ 4", dec(v), [dec(v)], False, "Long division: 9.36 ÷ 4, keep the point in line", "divw"))
    w = F(18) / F(30, 100); assert w.denominator == 1
    qs.append(Q("30% of a number is 18. What is the number?", str(w), [str(w)], False, "10% = 18 ÷ 3 = 6, so 100% = 60", "whole"))
    v = D(45) * D("0.8") * D("0.9")
    qs.append(Q("A game costs $45. Its price is reduced by 20%, and then the new price is reduced by a further 10%. What is the final price?",
                usd(v), [usd(v), "$32.4"], True, "$45 – 20% = $36; $36 – 10% = $32.40 (not 30% off $45, which gives $31.50)", "pct", "$"))
    v = D(10) - (4 * D("1.35") + D("0.85"))
    qs.append(Q("Mia buys 4 pens at $1.35 each and a ruler for 85¢. How much change does she get from $10?",
                usd(v), [usd(v), "375¢"], True, "4 × $1.35 = $5.40; + $0.85 = $6.25; $10 – $6.25 = $3.75", "money", "$"))
    L = next(x for x in range(1, 50) if 5 * x + 3 == 4 * (x + 3))
    qs.append(Q("Mom is 5 times as old as Leo. In 3 years' time, Mom will be 4 times as old as Leo. How old is Leo now?",
                f"{L} years", [str(L), f"{L} years", f"{L} yrs"], False, "Leo = L, Mom = 5L. 5L + 3 = 4(L + 3), so 5L + 3 = 4L + 12, so L = 9 (Mom is 45)", "eqn", "years"))
    pc = next(x for x in range(1, 120) if x + (x + 40) == 120)
    qs.append(Q("A ruler and a pencil cost $1.20 together. The ruler costs 40¢ more than the pencil. How much does the pencil cost?",
                f"{pc}¢", [f"{pc}¢", f"${D(pc)/100:.2f}"], True, "Pencil = p, ruler = p + 40. 2p + 40 = 120, so p = 40¢", "eqn", "¢"))
    return qs

def test_b():
    qs = []
    v = D("15.1") - D("7.46")
    qs.append(Q("Work out 15.1 – 7.46", dec(v), [dec(v)], False, "15.10 – 7.46 (add a zero first)", "sub"))
    v = D("0.6") * D("0.07")
    qs.append(Q("Work out 0.6 × 0.07", dec(v), [dec(v)], False, "6 × 7 = 42, three decimal places, so 0.042 (0.42 is wrong)", "mul"))
    v = D("4.75") * 8
    qs.append(Q("Work out 4.75 × 8", dec(v), [dec(v), "38.00", "38.0"], False, "475 × 8 = 3800, two decimal places, so 38.00 = 38", "mul"))
    v = D("6.08") + D("12.7") + D("3.425")
    qs.append(Q("Work out 6.08 + 12.7 + 3.425", dec(v), [dec(v)], False, "Line up the points: 6.080 + 12.700 + 3.425", "add"))
    v = D("13.5") / 6
    qs.append(Q("Work out 13.5 ÷ 6", dec(v), [dec(v)], False, "13.50 ÷ 6 = 2.25 (add a zero to keep dividing)", "divw"))
    w = F(36) / F(45, 100); assert w.denominator == 1
    qs.append(Q("36 students went on a field trip. This was 45% of the grade. How many students are in the grade?",
                f"{w} students", [str(w), f"{w} students"], False, "5% = 36 ÷ 9 = 4, so 100% = 80", "whole", "students"))
    v = D(240) * D("1.1") * D("0.75")
    qs.append(Q("A bike costs $240. The price goes up by 10%. Then the new price is reduced by 25%. What is the price now?",
                usd(v), [usd(v), "$198"], True, "$240 + 10% = $264; $264 – 25% = $198 (not –15% overall, which gives $204)", "pct", "$"))
    v = D(40) - (2 * D("8.75") + 3 * D("5.40"))
    qs.append(Q("Movie tickets cost $8.75 for an adult and $5.40 for a child. A family buys 2 adult and 3 child tickets and pays with $40. How much change do they get?",
                usd(v), [usd(v), "$6.3"], True, "2 × $8.75 = $17.50; 3 × $5.40 = $16.20; total $33.70; $40 – $33.70 = $6.30", "money", "$"))
    T = next(x for x in range(1, 30) if x + (x + 6) == 30)
    qs.append(Q("Sara is 6 years older than Tom. Their ages add up to 30. How old is Sara?",
                f"{T+6} years", [str(T + 6), f"{T+6} years", f"{T+6} yrs"], False, "Tom = t, Sara = t + 6. 2t + 6 = 30, so t = 12, so Sara is 18", "eqn", "years"))
    pc = next(x for x in range(1, 240) if x + 3 * x == 240)
    pen = D(3 * pc) / 100
    qs.append(Q("A pen costs 3 times as much as a pencil. Together they cost $2.40. How much does the pen cost?",
                usd(pen), [usd(pen), "$1.8", "180¢"], True, "Pencil = p, pen = 3p. 4p = 240¢, so p = 60¢, pen = $1.80", "eqn", "$"))
    return qs

def test_c():
    """Grade 5, set 1: OA, NBT (compare, multiply, divide, add decimals), NF, MD."""
    qs = []
    v = 2 * (9 + 4) - 5
    qs.append(Q("Work out 2 × (9 + 4) – 5", str(v), [str(v)], False,
                "Parentheses first: 9 + 4 = 13, then 2 × 13 = 26, then – 5", "g5paren"))
    qs.append(Q("Which is greater, 0.4 or 0.38?", "0.4", ["0.4", "0.40"], False,
                "0.4 is 0.40, and 40 hundredths beats 38 hundredths", "g5cmp"))
    v = 46 * 27
    qs.append(Q("Work out 46 × 27", str(v), [str(v)], False,
                "46 × 20 = 920, 46 × 7 = 322, add them", "g5mulw"))
    v = 936 // 24
    qs.append(Q("Work out 936 ÷ 24", str(v), [str(v)], False,
                "24 × 30 = 720, 216 left, 24 × 9 = 216", "g5divw"))
    v = D("3.4") + D("2.85")
    qs.append(Q("Work out 3.4 + 2.85", dec(v), [dec(v)], False,
                "Line up the points: 3.40 + 2.85", "g5decadd"))
    v = F(2, 3) + F(1, 4)
    qs.append(Q("Work out 2/3 + 1/4", frac(v), [frac(v)], False,
                "Twelfths: 8/12 + 3/12", "g5fadd"))
    v = F(2, 5) * F(3, 4)
    qs.append(Q("Work out 2/5 × 3/4", frac(v), [frac(v), "6/20"], False,
                "Multiply across: 6/20, then simplify", "g5fmul"))
    v = F(1, 3) / 4
    qs.append(Q("Work out 1/3 ÷ 4", frac(v), [frac(v)], False,
                "One third shared between 4 is a twelfth", "g5fdiv"))
    qs.append(Q("How many centimeters are there in 2.5 meters?", "250 cm",
                ["250 cm", "250cm", "250"], True, "1 m = 100 cm, so × 100", "g5conv", "cm"))
    v = 5 * 4 * 3
    qs.append(Q("A box measures 5 cm by 4 cm by 3 cm. What is its volume?", f"{v} cm³",
                [f"{v} cm³", f"{v} cm3", f"{v} cubic cm", str(v)], True,
                "Volume = length × width × height", "g5vol", "cm³"))
    return qs


def test_d():
    """Grade 5, set 2: the same domains, plus geometry (coordinates)."""
    qs = []
    v = 20 - (3 * 4) + 6
    qs.append(Q("Work out 20 – (3 × 4) + 6", str(v), [str(v)], False,
                "Parentheses first: 3 × 4 = 12, then 20 – 12 + 6", "g5paren"))
    qs.append(Q("Which is greater, 0.07 or 0.1?", "0.1", ["0.1", "0.10"], False,
                "0.1 is 10 hundredths, 0.07 is 7 hundredths", "g5cmp"))
    v = 58 * 34
    qs.append(Q("Work out 58 × 34", str(v), [str(v)], False,
                "58 × 30 = 1740, 58 × 4 = 232, add them", "g5mulw"))
    v = 4284 // 42
    qs.append(Q("Work out 4284 ÷ 42", str(v), [str(v)], False,
                "42 × 100 = 4200, 84 left, 42 × 2 = 84", "g5divw"))
    v = D("7.2") - D("3.45")
    qs.append(Q("Work out 7.2 – 3.45", dec(v), [dec(v)], False,
                "7.20 – 3.45 (add a zero first)", "g5decsub"))
    v = F(5, 6) - F(1, 4)
    qs.append(Q("Work out 5/6 – 1/4", frac(v), [frac(v)], False,
                "Twelfths: 10/12 – 3/12", "g5fsub"))
    v = F(3, 8) * F(2, 3)
    qs.append(Q("Work out 3/8 × 2/3", frac(v), [frac(v), "6/24"], False,
                "Multiply across: 6/24, then simplify", "g5fmul"))
    v = F(6) / F(1, 2)
    qs.append(Q("How many halves are there in 6? (Work out 6 ÷ 1/2)", frac(v), [frac(v)], False,
                "Each whole holds 2 halves, so 6 wholes hold 12", "g5fdiv"))
    qs.append(Q("How many meters are there in 3.5 kilometers?", "3500 m",
                ["3500 m", "3500m", "3500"], True, "1 km = 1000 m, so × 1000", "g5conv", "m"))
    qs.append(Q("Start at the origin. Move 3 to the right and 2 up. Write the coordinates of "
                "the point you land on.", "(3, 2)", ["(3, 2)", "(3,2)", "3, 2", "3,2"], False,
                "The first number is across, the second is up", "g5coord"))
    return qs


def test_e():
    """Grade 5, set 3: the untested components, plus a retest of each mistake."""
    qs = []
    v = 3 * (2 + (8 - 5))
    qs.append(Q("Work out 3 × [2 + (8 – 5)]", str(v), [str(v)], False,
                "Innermost first: 8 – 5 = 3, then 2 + 3 = 5, then 3 × 5", "g5paren_nest"))
    v = 214 * 132
    qs.append(Q("Work out 214 × 132", str(v), [str(v)], False,
                "214 × 100, 214 × 30, 214 × 2, then add", "g5mul33"))
    v = D("0.6") * D("0.45")
    qs.append(Q("Work out 0.6 × 0.45", dec(v), [dec(v), "0.270"], False,
                "6 × 45 = 270, three decimal places, so 0.270 = 0.27", "g5decmul"))
    v = D("8.3") - D("4.67")                       # retest: Test A subtraction error
    qs.append(Q("Work out 8.3 – 4.67", dec(v), [dec(v)], False,
                "8.30 – 4.67 (add a zero, then borrow)", "g5decsub"))
    v = F(3, 2) + F(7, 3)
    qs.append(Q("Work out 1 1/2 + 2 1/3", mixed(v), [mixed(v), frac(v)], False,
                "Sixths: 1 3/6 + 2 2/6", "g5mixadd"))
    v = F(1, 5) / 3                                # retest: Test C flipped the wrong fraction
    qs.append(Q("Work out 1/5 ÷ 3", frac(v), [frac(v)], False,
                "One fifth shared between 3 is a fifteenth", "g5fdiv"))
    v = D("450") / 100
    qs.append(Q("How many meters are there in 450 centimeters?", f"{dec(v)} m",
                [f"{dec(v)} m", f"{dec(v)}m", dec(v)], True,
                "100 cm = 1 m, so divide by 100", "g5conv_up", "m"))
    v = 6 * 3 * 2                                  # retest: Test C volume units
    qs.append(Q("A cuboid measures 6 cm by 3 cm by 2 cm. What is its volume?", f"{v} cm³",
                [f"{v} cm³", f"{v} cm3", f"{v} cubic cm"], True,
                "Volume = 6 × 3 × 2, and three lengths multiplied give cubic units",
                "g5vol_math", "cm³"))
    qs.append(Q("Start at the origin. Move 4 to the right and stay on the x-axis. "
                "Write the coordinates of the point.", "(4, 0)",
                ["(4, 0)", "(4,0)", "4, 0", "4,0"], False,
                "4 across, 0 up", "g5coord_x"))
    qs.append(Q("What are the coordinates of the origin?", "(0, 0)",
                ["(0, 0)", "(0,0)", "0, 0", "0,0"], False,
                "Where the two axes cross", "g5coord_origin"))
    return qs


def test_f():
    """Grade 5, set 4: the rest of the untested components."""
    qs = []
    v = 4 * (7 + 2) - 10                           # retest: Test C times-table slip
    qs.append(Q("Work out 4 × (7 + 2) – 10", str(v), [str(v)], False,
                "Parentheses first: 7 + 2 = 9, then 4 × 9 = 36, then – 10", "g5paren"))
    v = 36 * 1245
    qs.append(Q("Work out 36 × 1245", str(v), [str(v)], False,
                "1245 × 30, 1245 × 6, then add", "g5mul24"))
    v = 123 * 2045
    qs.append(Q("Work out 123 × 2045", str(v), [str(v)], False,
                "2045 × 100, 2045 × 20, 2045 × 3, then add", "g5mul34"))
    v = D("0.84") / D("0.4")
    qs.append(Q("Work out 0.84 ÷ 0.4", dec(v), [dec(v), "2.10"], False,
                "Make the divisor whole: 8.4 ÷ 4 = 2.1", "g5decdiv"))
    v = F(13, 4) - F(5, 3)
    qs.append(Q("Work out 3 1/4 – 1 2/3", mixed(v), [mixed(v), frac(v)], False,
                "Twelfths: 3 3/12 – 1 8/12, borrow one whole", "g5mixsub"))
    v = 250 - 3 * 40
    qs.append(Q("A rope is 2.5 meters long. Three pieces of 40 cm each are cut off. "
                "How many centimeters are left?", f"{v} cm", [f"{v} cm", f"{v}cm", str(v)],
                True, "2.5 m = 250 cm; 3 × 40 = 120; 250 – 120", "g5conv_multi", "cm"))
    qs.append(Q("A point has coordinates (0, 5). How far up from the origin is it?", "5",
                ["5", "5 units"], False, "The second number is the distance up", "g5coord_y"))
    qs.append(Q("Which point is 2 to the right of the origin and 7 up? "
                "Write its coordinates.", "(2, 7)", ["(2, 7)", "(2,7)", "2, 7", "2,7"], False,
                "Across first, then up", "g5coord_plot"))
    v = 10 * 5 * 4                                 # retest: volume units again
    qs.append(Q("A tank measures 10 cm by 5 cm by 4 cm. What volume of water fills it?",
                f"{v} cm³", [f"{v} cm³", f"{v} cm3", f"{v} cubic cm"], True,
                "10 × 5 × 4, in cubic centimeters", "g5vol"))
    qs.append(Q("A point is 6 along the x-axis and 3 along the y-axis. "
                "Write its coordinates.", "(6, 3)",
                ["(6, 3)", "(6,3)", "6, 3", "6,3"], False,
                "x first, then y", "g5coord"))
    return qs


def test_g():
    """Mixed: retests of the confirmed failures and their prerequisites, the
    never-asked place-value standards, and two grade 6/7 readiness checks."""
    qs = []
    v = D("20.3") - D("8.47")                      # retest: Test A borrowing error
    qs.append(Q("Work out 20.3 – 8.47", dec(v), [dec(v)], False,
                "20.30 – 8.47: add a zero, then borrow across it", "sub"))
    v = 9246 // 23
    assert 23 * v == 9246
    qs.append(Q("Work out 9246 ÷ 23", str(v), [str(v)], False,
                "92 ÷ 23 = 4, bring down 4: 4 ÷ 23 = 0, bring down 6: 46 ÷ 23 = 2", "g6div"))
    v = 326 * 147                                  # retest: Test E adding the partial products
    qs.append(Q("Work out 326 × 147", str(v), [str(v)], False,
                "326 × 100, 326 × 40, 326 × 7, then add carefully", "g5mul33"))
    v = D("4.7") + D("3.68")
    qs.append(Q("Work out 4.7 + 3.68", dec(v), [dec(v)], False,
                "Line up the points: 4.70 + 3.68", "g5decadd"))
    qs.append(Q("In 5.55, the 5 in the tenths place is worth how many times "
                "the 5 in the hundredths place?", "10", ["10", "10 times"], False,
                "0.5 ÷ 0.05 = 10: each place is worth 10 times the place to its right", "g5pv10"))
    v = D("63.8") / 10 ** 2
    qs.append(Q("Work out 63.8 ÷ 10²", dec(v), [dec(v)], False,
                "10² = 100, so the decimal point moves two places to the left", "g5pow10"))
    v = D("7.396").quantize(D("0.01"))
    qs.append(Q("Round 7.396 to the nearest hundredth.", str(v), [str(v), dec(v)], False,
                "The thousandths digit is 6, so 7.39 rounds up to 7.40", "g5round"))
    # Volume has been right three times with the units missing, so this one is
    # about writing cm³ - the addition of two boxes is the only new part.
    v = 5 * 4 * 2 + 3 * 3 * 2
    qs.append(Q("A box 5 cm by 4 cm by 2 cm sits on top of a box 3 cm by 3 cm by 2 cm. "
                "What is their total volume?", f"{v} cm³",
                [f"{v} cm³", f"{v} cm3", f"{v} cubic cm"], True,
                "40 cm³ + 18 cm³; volumes are always in cubic units", "g5vol_add", "cm³"))
    v = F(19, 3) - F(11, 4)
    qs.append(Q("x + 2 3/4 = 6 1/3. What is x?", mixed(v), [mixed(v), frac(v)], False,
                "x = 6 1/3 – 2 3/4 = 6 4/12 – 2 9/12 = 3 7/12", "g6eqn"))
    v = F(3, 8) + F(-5, 2) + F(5, 8)
    assert v < 0
    neg = [f"{s}{t}" for s in ("-", "–") for t in (mixed(-v), frac(-v))]
    qs.append(Q("Work out 3/8 + (–2 1/2) + 5/8", f"–{mixed(-v)}", neg, False,
                "Group 3/8 + 5/8 = 1 first, then 1 + (–2 1/2)", "g7rat"))
    return qs


def test_h():
    """The next picks down the plan: the failures Test G did not reach, the
    untested fraction standards, and two more grade 6/7 readiness checks."""
    qs = []
    v = F(3, 5)
    qs.append(Q("5 friends share 3 pizzas equally. What fraction of a pizza does each "
                "friend get?", frac(v), [frac(v), f"{frac(v)} pizza", f"{frac(v)} of a pizza"],
                False, "3 ÷ 5 = 3/5", "g5fasdiv"))
    qs.append(Q("Without working it out: is 3/4 × 250 greater than, less than, or "
                "equal to 250?", "less than",
                ["less than", "less", "less than 250", "<"], False,
                "3/4 is less than 1, so it shrinks 250", "g5scale"))
    v = F(9, 4) - F(5, 3)
    qs.append(Q("Sam ran 2 1/4 miles on Monday and 1 2/3 miles on Tuesday. "
                "How much farther did he run on Monday?", f"{mixed(v)} mile",
                [f"{mixed(v)} mile", f"{mixed(v)} miles", f"{mixed(v)} mi"], True,
                "Twelfths: 2 3/12 – 1 8/12, borrow one whole: 1 15/12 – 1 8/12",
                "g5fword_sub", "miles"))
    v = F(1, 2) / 3                                # retest: Test C flipped the wrong fraction
    qs.append(Q("Half a pizza is shared equally among 3 friends. What fraction of the "
                "whole pizza does each friend get?", frac(v),
                [frac(v), f"{frac(v)} pizza", f"{frac(v)} of the pizza"], False,
                "1/2 ÷ 3 = 1/6", "g5fdiv"))
    v = D(15) / D("0.25")                          # retest: Test B left this blank
    qs.append(Q("A jar has 15 red marbles. That is 25% of all the marbles. "
                "How many marbles are in the jar?", dec(v), [dec(v), f"{dec(v)} marbles"],
                False, "25% is 1/4, so the whole is 4 × 15", "whole"))
    v = D(80) * D("0.75") * D("0.9")               # retest: Test A two-step discount
    qs.append(Q("A jacket costs $80. Its price is reduced by 25%, and then the new price "
                "is reduced by a further 10%. What is the final price?", usd(v),
                [usd(v), f"${dec(v)}"], True,
                "25% off: $80 – $20 = $60. Then 10% of $60 is $6: $60 – $6 = $54",
                "pct", "$"))
    expr = ["7p + 45", "7p+45", "45 + 7p", "45+7p", "7 × p + 45", "7×p+45", "p × 7 + 45"]
    for e in expr:                                 # every accepted form must mean 7p + 45
        assert eval(re.sub(r"(\d)p", r"\1*p", e.replace("×", "*")), {"p": 3}) == 7 * 3 + 45, e
    qs.append(Q("Pencils cost p cents each. Write an expression for the cost, in cents, "
                "of 7 pencils and a 45¢ eraser.", expr[0], expr, False,
                "7 pencils cost 7 × p = 7p cents; add 45 for the eraser", "g6expr"))
    m = (3 * 6 - 6) // (4 - 3)                     # 4m + 6 = 3(m + 6)
    assert 4 * m + 6 == 3 * (m + 6)
    qs.append(Q("Dad is 4 times as old as Mia. In 6 years he will be 3 times as old as Mia. "
                "How old is Mia now?", f"{m} years", [str(m), f"{m} years", f"{m} yrs"], False,
                "Mia = m, Dad = 4m. Then 4m + 6 = 3(m + 6), so 4m + 6 = 3m + 18 and m = 12",
                "eqn"))
    v = F(9 * 6, 2)
    qs.append(Q("A triangular flag has a base of 9 cm and a height of 6 cm. "
                "What is its area?", f"{v} cm²", [f"{v} cm²", f"{v} cm2", f"{v} sq cm"], True,
                "Half of base × height: (9 × 6) ÷ 2 = 27, in square centimeters",
                "g6tri", "cm²"))
    v = F(-6) * F(2, 3) * F(-1, 4)
    qs.append(Q("Work out (–6) × 2/3 × (–1/4)", frac(v), [frac(v)], False,
                "Two negatives give a positive. 6 × 2/3 = 4, then 4 × 1/4 = 1", "g7ratmul"))
    return qs


def _expr_ok(forms, value, **names):
    """Every accepted way of writing an expression must evaluate to `value`.
    Variables are passed by name, e.g. _expr_ok(forms, 2 * 7 - 4, m=7)."""
    for e in forms:
        py = e.replace("×", "*").replace("–", "-").replace("−", "-")
        py = re.sub(r"(\d)([a-z(])", r"\1*\2", py)
        assert eval(py, {}, names) == value, e


def test_i():
    """The plan after Tests G and H: the decimal failures and the carries inside
    them, the two never-asked grade-5 standards, and a percent retest."""
    qs = []
    v = F(120, 6 * 5)
    qs.append(Q("A box has a volume of 120 cm³. It is 6 cm long and 5 cm wide. "
                "How tall is it?", f"{v} cm", [f"{v} cm", f"{v}cm"], True,
                "6 × 5 = 30 cm² for the base; 120 ÷ 30 = 4 cm", "g5vol_math", "cm"))
    v = D("40.2") - D("17.65")
    qs.append(Q("Work out 40.2 – 17.65", dec(v), [dec(v)], False,
                "40.20 – 17.65: add a zero, then borrow across it", "sub"))
    v = 7854 // 34
    assert 34 * v == 7854
    qs.append(Q("Work out 7854 ÷ 34", str(v), [str(v)], False,
                "78 ÷ 34 = 2 r 10, bring down 5: 105 ÷ 34 = 3 r 3, bring down 4: 34 ÷ 34 = 1",
                "g6div"))
    # Tests E and G both went wrong ADDING the partial products, not making them,
    # so this one has carries in nearly every column of the addition.
    v = 487 * 256
    qs.append(Q("Work out 487 × 256", str(v), [str(v)], False,
                "487 × 200, 487 × 50, 487 × 6, then add column by column with carries",
                "g5mul33"))
    v = D("5.67") + D("2.85")                      # carries out of both columns, as on Test G
    qs.append(Q("Work out 5.67 + 2.85", dec(v), [dec(v)], False,
                "7 + 5 = 12, carry 1; 6 + 8 + 1 = 15, carry 1; 5 + 2 + 1 = 8", "g5decadd"))
    v = F(3, 4) * F(5, 2)
    qs.append(Q("A recipe needs 2 1/2 cups of flour. Maya makes 3/4 of the recipe. "
                "How many cups of flour does she need?", f"{mixed(v)} cups",
                [f"{mixed(v)} cups", f"{mixed(v)} cup", f"{frac(v)} cups"], True,
                "3/4 × 5/2 = 15/8 = 1 7/8 cups", "g5fmulword", "cups"))
    expr = ["4 × (9 + 6)", "4×(9+6)", "(9 + 6) × 4", "(9+6)×4", "4(9 + 6)", "4(9+6)"]
    _expr_ok(expr, 4 * (9 + 6))
    qs.append(Q("Write an expression for: add 9 and 6, then multiply by 4. "
                "Do not work it out.", expr[0], expr, False,
                "The adding happens first, so it goes in parentheses", "g5expr"))
    v = D("14.4") / 6
    qs.append(Q("6n = 14.4. What is n?", dec(v), [dec(v), f"n = {dec(v)}", f"n={dec(v)}"],
                False, "Divide both sides by 6: 14.4 ÷ 6 = 2.4", "g6eqn_px"))
    v = F(2, 5) + F(-16, 5) + F(3, 5)               # retest: Test G moved away from zero
    assert v < 0
    neg = [f"{s}{t}" for s in ("-", "–") for t in (mixed(-v), frac(-v))]
    qs.append(Q("Work out 2/5 + (–3 1/5) + 3/5", f"–{mixed(-v)}", neg, False,
                "Group 2/5 + 3/5 = 1 first, then 1 + (–3 1/5) = –2 1/5", "g7rat"))
    v = D(150) * D("1.2") * D("0.8")               # retest: Test A wrong, Test H blank
    qs.append(Q("A bike costs $150. Its price goes up by 20%, and then the new price "
                "goes down by 20%. What is the final price?", usd(v), [usd(v), f"${dec(v)}"],
                True, "Up 20%: $150 + $30 = $180. Down 20% of $180 = $36: $180 – $36 = $144",
                "pct", "$"))
    return qs


def test_j():
    """The next picks down the ranking, chosen by what the diagnoses show is
    still a real gap rather than a slip that has since been answered correctly."""
    qs = []
    v = F(3, 2) * 8
    qs.append(Q("A recipe uses 3 cups of flour for every 2 cups of milk. How much flour "
                "goes with 8 cups of milk?", f"{v} cups", [f"{v} cups", f"{v} cup"], True,
                "8 is 4 lots of 2, so 4 lots of 3 = 12 cups", "g6ratio", "cups"))
    rows = [(2, 3), (4, 6), (6, 10)]
    v = "yes" if len({F(c, n) for n, c in rows}) == 1 else "no"
    qs.append(Q("2 pens cost $3, 4 pens cost $6, and 6 pens cost $10. Is the cost "
                "proportional to the number of pens? Write yes or no.", v,
                [v, v.capitalize()], False,
                "Price per pen: $1.50, $1.50, then $1.67 - not the same, so not proportional",
                "g7prop"))
    v = F(17 - 3, 2)                               # 3 + 2m = 17
    qs.append(Q("A taxi charges $3 plus $2 for each mile. A ride costs $17. "
                "How many miles was the ride?", f"{v} miles",
                [f"{v} miles", f"{v} mi"], True,
                "3 + 2m = 17, so 2m = 14 and m = 7", "eqn", "miles"))
    v = F(8 * 5, 2)                                # retest: Test H forgot to halve, wrong units
    qs.append(Q("A triangular garden bed has a base of 8 m and a height of 5 m. "
                "What is its area?", f"{v} m²", [f"{v} m²", f"{v} m2", f"{v} sq m"], True,
                "Half of base × height: (8 × 5) ÷ 2 = 20, in square meters", "g6tri", "m²"))
    v = D("4.6") * 10 ** 3                         # retest: Test G wrote 10² as 10000
    qs.append(Q("Work out 4.6 × 10³", dec(v), [dec(v)], False,
                "10³ = 10 × 10 × 10 = 1000, so the decimal point moves three places right",
                "g5pow10_mul"))
    qs.append(Q("Without working it out: is 5/6 × 72 greater than or less than 72?",
                "less than", ["less than", "less", "less than 72", "<"], False,
                "5/6 is less than 1, so it shrinks 72", "g5scale"))
    qs.append(Q("The 7 in 0.7 is worth how many times the 7 in 0.07?", "10",
                ["10", "10 times"], False,
                "0.7 ÷ 0.07 = 10: one place to the left is worth 10 times as much", "g5pv10"))
    v = F(-8) * F(3, 4) * F(-1, 2)
    qs.append(Q("Work out (–8) × 3/4 × (–1/2)", frac(v), [frac(v)], False,
                "Two negatives give a positive. 8 × 1/2 = 4, then 4 × 3/4 = 3", "g7ratmul"))
    v = F(7, 4) + F(7, 3)
    qs.append(Q("A ribbon 1 3/4 m long is joined to one 2 1/3 m long. "
                "What is the total length?", f"{mixed(v)} m",
                [f"{mixed(v)} m", f"{mixed(v)}m", f"{frac(v)} m"], True,
                "Twelfths: 1 9/12 + 2 4/12 = 3 13/12 = 4 1/12 m", "g5fword_add", "m"))
    qs.append(Q("Start at the origin. Move 5 to the right and 3 up. "
                "Write the coordinates of the point.", "(5, 3)",
                ["(5, 3)", "(5,3)", "5, 3", "5,3"], False,
                "Across 5 first, then up 3", "g5coord_move"))
    return qs


def test_k():
    """Retests from the plan after Tests I and J, with signed numbers in place
    of the two readiness picks the planner offered (both already mastered)."""
    qs = []
    v = D(60) * D("1.1") * D("0.75")              # retest: two-step percent, $ required
    qs.append(Q("A jacket costs $60. Its price goes up by 10%, and then the new price "
                "is reduced by 25%. What is the final price?", usd(v), [usd(v), f"${dec(v)}"],
                True, "Up 10%: $60 + $6 = $66. Then 25% of $66 is $16.50: $66 – $16.50 = $49.50",
                "pct", "$"))
    rows = [(2, 6), (5, 15), (8, 24)]
    v = "yes" if len({F(y, x) for x, y in rows}) == 1 else "no"
    qs.append(Q("x is 2, 5 and 8. y is 6, 15 and 24. Is y proportional to x? "
                "Write yes or no.", v, [v, v.capitalize()], False,
                "y ÷ x is 3 every time, so yes", "g7prop"))
    v = F(150, 3) * 5
    qs.append(Q("A car travels 150 miles in 3 hours. At the same speed, how far does it "
                "travel in 5 hours?", f"{v} miles", [f"{v} miles", f"{v} mi"], True,
                "150 ÷ 3 = 50 miles each hour; 50 × 5 = 250 miles", "g6ratio", "miles"))
    v = 40 * 25 * 30
    qs.append(Q("A fish tank is 40 cm long, 25 cm wide and 30 cm tall. "
                "What is its volume?", f"{v} cm³", [f"{v} cm³", f"{v} cm3", f"{v} cubic cm"],
                True, "40 × 25 = 1000, × 30 = 30000 cubic centimeters", "g5vol", "cm³"))
    v = 608 * 347
    qs.append(Q("Work out 608 × 347", str(v), [str(v)], False,
                "608 × 300, 608 × 40, 608 × 7, then add column by column", "g5mul33"))
    v = D("7.56") / D("0.36")
    qs.append(Q("Work out 7.56 ÷ 0.36", dec(v), [dec(v)], False,
                "Multiply both by 100: 756 ÷ 36 = 21", "divd"))
    v = (110 - 20) // 15
    assert 20 + 15 * v == 110
    qs.append(Q("A club costs $20 to join and then $15 a month. Sam has paid $110 in all. "
                "For how many months has he been a member?", str(v),
                [str(v), f"{v} months", f"{v} month"], False,
                "20 + 15m = 110, so 15m = 90 and m = 6", "eqn"))
    v = D("9.05") - D("3.68")
    qs.append(Q("Work out 9.05 – 3.68", dec(v), [dec(v)], False,
                "9.05 – 3.68: borrow in the hundredths and again in the tenths", "g5decsub"))
    v = F(-9, 2) + F(11, 4)                        # retest: G10, I9 sign handling
    assert v < 0
    neg = [f"{sg}{t}" for sg in ("-", "–") for t in (mixed(-v), frac(-v))]
    qs.append(Q("Work out –4 1/2 + 2 3/4", f"–{mixed(-v)}", neg, False,
                "The negative part is bigger, so the answer is negative: 4 2/4 – 2 3/4 = 1 3/4",
                "g7rat"))
    v = F(-3) * F(-2, 3) * 5                       # retest: J8 kept the minus sign
    qs.append(Q("Work out (–3) × (–2/3) × 5", frac(v), [frac(v)], False,
                "Two negatives make a positive. 3 × 2/3 = 2, then 2 × 5 = 10", "g7ratmul"))
    return qs


def test_l():
    """The next picks down the ranking: the fraction work, area, place value and
    powers of ten, each aimed at the part the diagnoses show is still open."""
    qs = []
    expr = ["2m – 4", "2m-4", "2m - 4", "2 × m – 4", "2×m-4", "m × 2 – 4"]
    _expr_ok(expr, 2 * 7 - 4, m=7)
    qs.append(Q("Mia has m marbles. Leo has 4 fewer than twice as many as Mia. "
                "Write an expression for Leo's marbles.", expr[0], expr, False,
                "Twice as many is 2m; 4 fewer takes 4 away: 2m – 4", "g6expr_var"))
    v = F(13, 4) - F(5, 3)
    qs.append(Q("A bag has 3 1/4 kg of rice. 1 2/3 kg is used. How much rice is left?",
                f"{mixed(v)} kg", [f"{mixed(v)} kg", f"{frac(v)} kg"], True,
                "Twelfths: 3 3/12 – 1 8/12; borrow one whole: 2 15/12 – 1 8/12 = 1 7/12 kg",
                "g5fword_sub", "kg"))
    v = D(80) * D("0.35")
    qs.append(Q("What is 35% of 80?", dec(v), [dec(v)], False,
                "10% of 80 is 8, so 30% is 24; 5% is 4; 24 + 4 = 28", "g6pct_of"))
    v = F(3, 5) * F(10, 3)                         # retest: I6 read "3/4 of" as divide by 4
    qs.append(Q("A rope is 3 1/3 m long. Ella uses 3/5 of it. How long is the piece "
                "she uses?", f"{mixed(v)} m", [f"{mixed(v)} m", f"{mixed(v)}m"], True,
                "3/5 × 10/3 = 30/15 = 2 m", "g5fmulword", "m"))
    v = 5 / F(1, 4)
    qs.append(Q("How many 1/4-cup scoops are there in 5 cups of flour?", str(v),
                [str(v), f"{v} scoops"], False, "Each cup holds 4 quarter-cups: 5 × 4 = 20",
                "g5fdiv"))
    qs.append(Q("A point is at (7, 2). How far is it from the x-axis?", "2",
                ["2", "2 units"], False, "The second number is the distance up from the x-axis",
                "g5coord_y"))
    qs.append(Q("Without working it out: is 1 1/2 × 64 greater than or less than 64?",
                "greater than", ["greater than", "greater", "greater than 64", ">"], False,
                "1 1/2 is more than 1, so it makes 64 bigger", "g5scale"))
    v = 9 * 4
    qs.append(Q("A parallelogram has a base of 9 m and a height of 4 m. What is its area?",
                f"{v} m²", [f"{v} m²", f"{v} m2", f"{v} sq m"], True,
                "Base × height = 36 square meters - no halving: it is two triangles, not one",
                "g6quad", "m²"))
    v = D("52.7") / 10 ** 3                        # retest: G6 (10² as 10000, reversed division)
    qs.append(Q("Work out 52.7 ÷ 10³", dec(v), [dec(v)], False,
                "10³ = 1000, so the decimal point moves three places left", "g5pow10"))
    qs.append(Q("The 3 in 0.03 is what fraction of the 3 in 0.3?", "1/10",
                ["1/10", "0.1", "one tenth"], False,
                "0.03 is one tenth of 0.3: each place is 1/10 of the place to its left", "g5pv10th"))
    return qs


def test_m():
    """The standards that need a picture or a concept rather than a computation.
    Every answer that depends on a figure is computed from the figure's data."""
    qs = []
    vol_units = ["cm³", "cm3", "cubic cm", "cubic centimeters", "cubic centimetres"]
    qs.append(Q("Which unit measures the space inside a box: cm, cm² or cm³?", "cm³", vol_units,
                False, "Space inside is volume, and volume is measured in cubic units", "g5volunit"))
    a = [0 + 3 * k for k in range(4)]; b = [0 + 6 * k for k in range(4)]
    pair = f"({a[3]}, {b[3]})"
    qs.append(Q("Pattern A starts at 0 and adds 3. Pattern B starts at 0 and adds 6. "
                "The first pair is (0, 0). Write the 4th pair (A, B).", pair,
                [pair, pair.replace(" ", ""), pair.strip("()"), pair.strip("()").replace(" ", "")], False,
                f"A: {', '.join(map(str, a))}. B: {', '.join(map(str, b))}. 4th terms: {pair}",
                "g5patterns"))
    for l, w, h in ((4, 3, 2), (3, 2, 3)):
        v = l * w * h
        qs.append(Q("This box is full of unit cubes. How many cubes?", str(v),
                    [str(v), f"{v} cubes", f"{v} unit cubes", f"{v} cubic units"], False,
                    f"{l} × {w} in each layer = {l * w}, × {h} layers = {v}", "g5cubes",
                    figure={"kind": "cubes", "l": l, "w": w, "h": h}))
    # Which must have four right angles: the shapes that are rectangles.
    right_angles = {"square": True, "rhombus": False, "rectangle": True, "parallelogram": False}
    names = ["square", "rhombus", "rectangle", "parallelogram"]
    v = ", ".join(L for L, n in zip("ABCD", names) if right_angles[n])
    qs.append(Q("Every rectangle has four right angles. Which of these must have four right "
                "angles? A square, B rhombus, C rectangle, D parallelogram. Write the letters.",
                v, [v], False,
                "A square is a special rectangle, so it has four right angles too", "g5shapeattr"))
    shapes = [("A", [(0, 0), (1, 0), (1, 0.6), (0, 0.6)]),                 # rectangle
              ("B", [(0, 0), (1, 0), (0.75, 0.6), (0.25, 0.6)]),           # trapezoid
              ("C", [(0.5, 0), (1, 0.35), (0.5, 0.7), (0, 0.35)]),         # rhombus
              ("D", [(0.5, 0), (0.95, 0.52), (0.5, 0.72), (0.05, 0.52)])]  # kite: short top, long bottom
    v = ", ".join(L for L, pts in shapes if is_parallelogram(pts))
    qs.append(Q("Which of these shapes are parallelograms? Write the letters.", v, [v], False,
                "A parallelogram has both pairs of opposite sides parallel: the rectangle and the "
                "rhombus do; the trapezoid has one pair, the kite none", "g5shapeclass",
                figure={"kind": "shapes", "shapes": [{"label": L, "pts": pts} for L, pts in shapes]}))
    plot = {"kind": "lineplot", "denominator": 4, "max": 1, "caption": "cups of juice in each glass",
            "values": {"1/4": 2, "1/2": 3, "3/4": 1, "1": 2}}
    vals = {F(k): n for k, n in plot["values"].items()}
    v = sum(k * n for k, n in vals.items())
    qs.append(Q("The line plot shows the juice in each glass. How much juice is there "
                "in all?", f"{mixed(v)} cups", [f"{mixed(v)} cups", f"{frac(v)} cups"], True,
                "2 × 1/4 + 3 × 1/2 + 1 × 3/4 + 2 × 1 = 1/2 + 1 1/2 + 3/4 + 2 = 4 3/4 cups",
                "g5lineplot", "cups", figure=plot))
    v = max(vals) - min(vals)
    qs.append(Q("How much more juice is in the fullest glass than in the emptiest?",
                f"{mixed(v)} cup", [f"{mixed(v)} cup", f"{mixed(v)} cups"], True,
                "1 – 1/4 = 3/4 cup", "g5lineplot", "cups", figure=plot))
    grid = {"kind": "grid", "size": 6, "points": {"A": [1, 1], "B": [5, 3], "C": [1, 5]}}
    bx, by = grid["points"]["B"]
    qs.append(Q("On this map, x is blocks east and y is blocks north. "
                "Write the coordinates of B.", f"({bx}, {by})",
                [f"({bx}, {by})", f"({bx},{by})", f"{bx}, {by}", f"{bx},{by}"], False,
                "5 east, then 3 north", "g5gridread", figure=grid))
    v = grid["points"]["C"][1] - grid["points"]["A"][1]
    assert grid["points"]["C"][0] == grid["points"]["A"][0]
    qs.append(Q("How many blocks north of point A is point C?", str(v),
                [str(v), f"{v} blocks"], False, "Same x; y goes from 1 to 5: 4 blocks", "g5gridread",
                figure=grid))
    return qs


# Tests N, O and P are one batch from `skills.py --plan --sheets 3`. Several
# "failures" on it were units-only (5.MD.C.5, 5.NF.A.2, 5.MD.B.2, 6.RP.A.3), so
# those questions keep the unit required in a fresh context rather than drilling
# arithmetic that was already right.
def test_n():
    """Batch sheet 1: volume, ratio, decimals, fractions, signed numbers, and
    three never-asked grade-6 standards."""
    qs = []
    v = 12 * 5 * 8                                  # K4 skipped a factor and wrote m³
    qs.append(Q("A storage box is 12 in long, 5 in wide and 8 in tall. What is its volume?",
                f"{v} in³", [f"{v} in³", f"{v} in3", f"{v} cubic inches", f"{v} cubic in"], True,
                "12 × 5 = 60, × 8 = 480 cubic inches", "g5vol", "in³"))
    v = 45 // 3 * 8
    qs.append(Q("A printer prints 45 pages in 3 minutes. At the same rate, how many pages "
                "does it print in 8 minutes?", f"{v} pages", [f"{v} pages"], True,
                "45 ÷ 3 = 15 pages a minute; 15 × 8 = 120 pages", "g6ratio", "pages"))
    v = D("6.48") + D("2.97")                       # carries out of both columns, as on Test G
    qs.append(Q("Work out 6.48 + 2.97", dec(v), [dec(v)], False,
                "8 + 7 = 15, carry 1; 4 + 9 + 1 = 14, carry 1; 6 + 2 + 1 = 9", "g5decadd"))
    v = F(5, 3) + F(11, 4)
    qs.append(Q("Jo walked 1 2/3 miles in the morning and 2 3/4 miles in the afternoon. "
                "How far did she walk in all?", f"{mixed(v)} miles",
                [f"{mixed(v)} miles", f"{frac(v)} miles", f"{mixed(v)} mi"], True,
                "Twelfths: 1 8/12 + 2 9/12 = 3 17/12 = 4 5/12 miles", "g5fword_add", "miles"))
    v = F(5, 6) + F(-10, 3) + F(1, 6)               # retest: G10, I9 three-term sums
    assert v < 0
    neg = [f"{sg}{t}" for sg in ("-", "–") for t in (mixed(-v), frac(-v))]
    qs.append(Q("Work out 5/6 + (–3 1/3) + 1/6", f"–{mixed(-v)}", neg, False,
                "Put the positives together: 5/6 + 1/6 = 1. Then 1 + (–3 1/3) = –2 1/3", "g7rat"))
    v = 6 * (15 - 7) + 4
    qs.append(Q("Work out 6 × (15 – 7) + 4", str(v), [str(v)], False,
                "Parentheses first: 15 – 7 = 8. Then 6 × 8 = 48, + 4 = 52", "g5paren"))
    v = F(2, 3) * F(21, 4)                          # retest: I6 read "3/4 of" as divide by 4
    qs.append(Q("A trail is 5 1/4 km long. Ben has walked 2/3 of it. How far has he walked?",
                f"{mixed(v)} km", [f"{mixed(v)} km", f"{frac(v)} km", f"{dec(D(v.numerator) / v.denominator)} km"], True,
                "2/3 × 21/4 = 42/12 = 3 1/2 km", "g5fmulword", "km"))
    g, b = 12, 15
    r = [f"{b}:{g}", f"{b} : {g}", f"{b} to {g}"]
    s = [x.replace(str(b), str(b // 3)).replace(str(g), str(g // 3)) for x in r]
    qs.append(Q(f"A class has {g} girls and {b} boys. Write the ratio of boys to girls.",
                r[0], r + s + [f"{b}/{g}", f"{b // 3}/{g // 3}"], False, "Boys first: 15 to 12, which is the same as 5 to 4",
                "g6ratio_write"))
    v = 4 * 3 * F(5, 2)
    qs.append(Q("A box is 4 cm long, 3 cm wide and 2 1/2 cm tall. What is its volume?",
                f"{v} cm³", [f"{v} cm³", f"{v} cm3", f"{v} cubic cm"], True,
                "4 × 3 = 12 for the base; 12 × 2 1/2 = 24 + 6 = 30 cubic centimeters",
                "g6volfrac", "cm³"))
    qs.append(Q("In the expression 5x + 9, what is the coefficient of x?", "5", ["5"], False,
                "The coefficient is the number multiplying the letter: 5", "g6coef"))
    return qs


def test_o():
    """Batch sheet 2: percent, equations, coordinates, signs, a line plot, area,
    and four never-asked grade-6 standards plus one review."""
    qs = []
    v = D(50) * D("0.8") * D("1.1")
    qs.append(Q("A lamp costs $50. Its price goes down by 20%, and then the new price goes "
                "up by 10%. What is the final price?", usd(v), [usd(v), f"${dec(v)}"], True,
                "Down 20%: $50 – $10 = $40. Then 10% of $40 is $4: $40 + $4 = $44.00", "pct", "$"))
    v = (108 - 24) // 12                            # retest: K7 never set up fee + rate
    assert 24 + 12 * v == 108
    qs.append(Q("A gym costs $24 to join and then $12 for each class. Ana has paid $108 in "
                "all. How many classes has she taken?", str(v),
                [str(v), f"{v} classes", f"{v} class"], False,
                "24 + 12c = 108, so 12c = 84 and c = 7", "eqn"))
    qs.append(Q("A point is at (3, 8). How far is it from the y-axis?", "3", ["3", "3 units"],
                False, "The first number is the distance across from the y-axis", "g5coord_x"))
    v = F(-5, 6) * -3 * -2
    qs.append(Q("Work out (–5/6) × (–3) × (–2)", f"–{frac(-v)}", [f"–{frac(-v)}", f"-{frac(-v)}"],
                False, "Three negatives: two make a positive, the third makes it negative. "
                "5/6 × 3 = 5/2, × 2 = 5, so –5", "g7ratmul"))
    plot = {"kind": "lineplot", "denominator": 8, "max": 1, "caption": "length of each ribbon (m)",
            "values": {"1/8": 2, "3/8": 1, "1/2": 3, "3/4": 2}}
    vals = {F(k): n for k, n in plot["values"].items()}
    v = sum(k * n for k, n in vals.items())
    qs.append(Q("The ribbons are joined end to end. What is the total length?",
                f"{mixed(v)} m", [f"{mixed(v)} m", f"{frac(v)} m"], True,
                "2 × 1/8 + 3/8 + 3 × 1/2 + 2 × 3/4 = 2/8 + 3/8 + 1 1/2 + 1 1/2 = 3 5/8 m",
                "g5lineplot", "m", figure=plot))
    v = F(7 * 10, 2)
    qs.append(Q("A triangular sail has a base of 7 ft and a height of 10 ft. What is its area?",
                f"{v} ft²", [f"{v} ft²", f"{v} ft2", f"{v} sq ft", f"{v} square feet"], True,
                "7 × 10 = 70, halved = 35 square feet", "g6tri", "ft²"))
    v = 2 ** 3 + 3 ** 2
    qs.append(Q("Work out 2³ + 3²", str(v), [str(v)], False, "2³ = 2 × 2 × 2 = 8; 3² = 3 × 3 = 9; "
                "8 + 9 = 17", "g6exp"))
    qs.append(Q("Which is a statistical question? A: How tall is Sam? B: How tall are the "
                "students in Sam's class? C: How many days are in May? Write the letter.",
                "B", ["B"], False, "Only B expects different answers from different students",
                "g6statq"))
    v = D(10) / 4
    qs.append(Q("4 notebooks cost $10. How much does one notebook cost?", usd(v),
                [usd(v), f"${dec(v)}"], True, "$10 ÷ 4 = $2.50", "g6unitrate", "$"))
    v = F(7, 4)
    qs.append(Q("A 7 m rope is cut into 4 equal pieces. How long is each piece?",
                f"{mixed(v)} m", [f"{mixed(v)} m", f"{frac(v)} m", f"{dec(D(v.numerator) / v.denominator)} m"], True,
                "7 ÷ 4 = 7/4 = 1 3/4 m", "g5fasdiv", "m"))
    return qs


def test_p():
    """Batch sheet 3: proportion, multiplication, scaling, place value, percent,
    and three never-asked grade-6 standards plus one review."""
    qs = []
    rows = [(3, 12), (5, 20), (8, 30)]
    v = "yes" if len({F(c, n) for n, c in rows}) == 1 else "no"
    qs.append(Q("3 tickets cost $12, 5 tickets cost $20 and 8 tickets cost $30. Is the cost "
                "proportional to the number of tickets? Write yes or no.", v, [v, v.capitalize()],
                False, "Cost of one ticket: $4, $4, then $3.75 - not the same, so no", "g7prop"))
    v = 739 * 486
    qs.append(Q("Work out 739 × 486", str(v), [str(v)], False,
                "739 × 400, 739 × 80, 739 × 6, then add column by column with carries", "g5mul33"))
    qs.append(Q("Without working it out: is 45 × 1 1/3 greater than or less than 45?",
                "greater than", ["greater than", "greater", "greater than 45", ">"], False,
                "1 1/3 is more than 1, so it makes 45 bigger", "g5scale"))
    v = D("8.4") / 10 ** 3                          # retest: L9 moved the point two places
    qs.append(Q("Work out 8.4 ÷ 10³", dec(v), [dec(v)], False,
                "10³ = 1000: move the point three places left, filling with zeros", "g5pow10"))
    v = F(24) / F(40, 100)
    qs.append(Q("24 students walk to school. That is 40% of the class. How many students are "
                "in the class?", str(v), [str(v), f"{v} students"], False,
                "10% is 24 ÷ 4 = 6, so 100% is 60", "whole"))
    qs.append(Q("In 4.44, the 4 in the ones place is worth how many times the 4 in the tenths "
                "place?", "10", ["10", "10 times", "ten"], False,
                "Each place is 10 times the place to its right", "g5pv10"))
    v = F(9, 4) / F(3, 8)
    qs.append(Q("How many 3/8-cup servings are in 2 1/4 cups of yogurt?", str(v),
                [str(v), f"{v} servings"], False,
                "2 1/4 = 18/8, and 18/8 ÷ 3/8 = 18 ÷ 3 = 6", "g6fdivword"))
    expr = ["3(12 – y)", "3(12-y)", "3 × (12 – y)", "3×(12-y)", "(12 – y) × 3", "(12-y)×3"]
    _expr_ok(expr, 3 * (12 - 5), y=5)
    qs.append(Q("Write an expression for: 3 times the difference of 12 and y.", expr[0], expr,
                False, "The difference of 12 and y is 12 – y; keep it in parentheses, then × 3",
                "g6expr_write"))
    plot = {"kind": "lineplot", "denominator": 1, "max": 6, "caption": "books read by each student",
            "values": {"1": 1, "2": 2, "3": 4, "4": 2, "5": 1}}
    vals = [int(k) for k in plot["values"]]
    v = max(vals) - min(vals)
    qs.append(Q("What is the range of the data?", str(v), [str(v), f"{v} books"], False,
                "Most books 5, fewest 1: 5 – 1 = 4", "g6spread", figure=plot))
    from decimal import ROUND_HALF_UP
    v = D("8.2961").quantize(D("0.01"), rounding=ROUND_HALF_UP)
    qs.append(Q("Round 8.2961 to the nearest hundredth.", str(v), [str(v), dec(v)], False,
                "Look at the thousandths: 6, so round up. 8.29 -> 8.30", "g5round"))
    return qs


def colswap(a, b, places=2):
    """Subtract by taking the smaller digit from the larger in each column."""
    fa, fb = (f"{D(x):.{places}f}".replace(".", "") for x in (a, b))
    fb = fb.zfill(len(fa))
    s = "".join(str(abs(int(x) - int(y))) for x, y in zip(fa, fb))
    return dec(D(int(s)).scaleb(-places))


def nocarry(a, b, places=2):
    """Add column by column, writing each column's last digit and never carrying."""
    fa, fb = (f"{D(x):.{places}f}".replace(".", "") for x in (a, b))
    n = max(len(fa), len(fb))
    s = "".join(str((int(x) + int(y)) % 10) for x, y in zip(fa.zfill(n), fb.zfill(n)))
    return dec(D(int(s)).scaleb(-places))


A, B, C, Dd, E, Ff, G, Hh, I, J, K, Ll, M = (test_a(), test_b(), test_c(), test_d(), test_e(), test_f(),
                                             test_g(), test_h(), test_i(), test_j(), test_k(), test_l(),
                                             test_m())
N, O, P = test_n(), test_o(), test_p()

# Predictable wrong answers -> diagnosis (computed, so code can diagnose without AI)
WRONG = {
    "A": {
        1: {dec(D("10.4") - D("6.785") + 1): "Borrowing error across the added zeros",
            "4.385": "Subtracted the smaller digit from the larger in each column instead of borrowing",
            "4.415": "Did 7 − 3 in the tenths column instead of borrowing (observed 2026-10-06)"},
        2: {dec(D("3.6") * 7 * 10): "Dropped the decimal point", dec(D("3.6") * 7 / 10): "Too many decimal places"},
        3: {dec(D("0.25") * D("1.6") * 10): "Too few decimal places", dec(D("0.25") * D("1.6") / 10): "Too many decimal places"},
        4: {dec(D("17.25") + D("0.89") + D("0.65")): "Misaligned 8.9 as 0.89"},
        5: {dec(D("9.36") / 4 * 10): "Misplaced the decimal point"},
        6: {dec(D(18) * D("0.3")): "Found 30% of 18 instead of the whole", dec(D(18) * D("1.3")): "Added 30% instead of finding the whole"},
        7: {usd(D(45) * D("0.7")): "Took 30% off in one step instead of 20% then 10%",
            usd(D(45) * D("0.8")): "Applied only the first discount",
            usd(D(45) * D("0.2") + D(45) * D("0.1")): "Gave the discount amount, not the final price",
            usd(D(45) * D("0.2") * D("0.1")): "Took 10% of the $9 discount instead of the new price; never subtracted (observed 2026-10-06)"},
        8: {usd(D(10) - (D("1.35") + D("0.85"))): "Forgot to multiply the pens by 4",
            usd(4 * D("1.35") + D("0.85")): "Gave the total cost, not the change"},
        9: {"45": "Gave Mom's age instead of Leo's", "45 years": "Gave Mom's age instead of Leo's"},
        10: {"80¢": "Gave the ruler's price", "60¢": "Split $1.20 in half without the 40¢ difference"},
    },
    "B": {
        1: {dec(D("15.1") - D("7.46") + 1): "Borrowing error across the added zero"},
        2: {dec(D("0.6") * D("0.07") * 10): "Too few decimal places", dec(D("0.6") * D("0.07") * 100): "Too few decimal places"},
        3: {dec(D("4.75") * 8 * 100): "Dropped the decimal point"},
        4: {dec(D("6.08") + D("1.27") + D("3.425")): "Misaligned 12.7 as 1.27"},
        5: {dec(D("13.5") / 6 * 10): "Misplaced the decimal point", "2.2": "Stopped dividing too early (remainder dropped)"},
        6: {dec(D(36) * D("0.45")): "Found 45% of 36 instead of the whole",
            f"{dec(D(36) * D('0.45'))} students": "Found 45% of 36 instead of the whole"},
        7: {usd(D(240) * D("0.85")): "Combined +10% and –25% into –15%",
            usd(D(240) * D("0.75")): "Ignored the 10% increase",
            usd(D(240) * D("1.1")): "Applied only the increase"},
        8: {usd(D(40) - (D("8.75") + D("5.40"))): "Forgot to multiply the tickets",
            usd(2 * D("8.75") + 3 * D("5.40")): "Gave the total cost, not the change"},
        9: {"12": "Gave Tom's age instead of Sara's", "12 years": "Gave Tom's age instead of Sara's",
            "15": "Split 30 in half without the 6-year difference", "15 years": "Split 30 in half without the 6-year difference"},
        10: {"$0.60": "Gave the pencil's price", "60¢": "Gave the pencil's price", "$0.80": "Divided $2.40 by 3 instead of 4"},
    },
    # Only mistakes that can be justified from the arithmetic are listed. The
    # rest are left for a reader to diagnose from the working and added once
    # confirmed - a guessed wrong answer would attach a confident explanation to
    # something the child never did.
    "C": {
        1: {"17": "Multiplied before the parentheses: 2 × 9 = 18, + 4, – 5"},
        2: {"0.38": "Took the longer decimal to be the larger one"},
        5: {"6.24": "Lost a hundredth carrying", "3.74": "Subtracted instead of adding"},
        6: {"3/7": "Added the numerators and the denominators"},
        7: {"11/20": "Added instead of multiplying"},
        8: {"4/3": "Multiplied by 4 instead of dividing", "12": "Worked out 4 ÷ 1/3 instead"},
        9: {"25 cm": "Multiplied by 10 instead of 100", "0.025 cm": "Divided by 100 instead of multiplying"},
        10: {"12 cm³": "Added the edges instead of multiplying them"},
    },
    "D": {
        1: {"74": "Worked left to right instead of doing the parentheses first"},
        2: {"0.07": "Took the longer decimal to be the larger one"},
        5: {"4.25": "Subtracted the smaller digit from the larger in each column instead of borrowing",
            "3.85": "Borrowing error across the added zero"},
        6: {"4/2": "Subtracted the numerators and the denominators", "2": "Subtracted the numerators and the denominators"},
        7: {"25/24": "Added instead of multiplying"},
        8: {"3": "Halved 6 instead of dividing by a half"},
        9: {"350 m": "Multiplied by 100 instead of 1000", "35 m": "Multiplied by 10 instead of 1000"},
        10: {"(2, 3)": "Gave the coordinates the wrong way round (up before across)",
             "(0, 2)": "Kept the origin's x-coordinate and applied only the vertical move (observed 2026-10-07)"},
    },
    "E": {
        1: {"9": "Worked left to right, ignoring the brackets: 3 × 2 = 6, + 8, – 5"},
        3: {"2.7": "One decimal place too few", "0.027": "One decimal place too many"},
        4: {"4.37": "Subtracted the smaller digit from the larger in each column instead of borrowing"},
        6: {"15": "Flipped the dividend and multiplied, as on Test C",
            "5/3": "Flipped the dividend instead of the divisor"},
        7: {"45000": "Multiplied by 100 instead of dividing", "45": "Divided by 10 instead of 100"},
        8: {"11 cm³": "Added the edges instead of multiplying them",
            "36 cm": "Correct number, but a volume needs cubic units"},
        9: {"(0, 4)": "Kept the origin's x-coordinate, as on Test D"},
    },
    "F": {
        1: {"20": "Worked left to right, ignoring the parentheses: 4 × 7 = 28, + 2, – 10"},
        4: {"0.21": "Decimal point one place out", "21": "Lost the decimal point entirely"},
        6: {"130 m": "Correct number, but the answer is in centimeters",
            "210 cm": "Subtracted only one 40 cm piece instead of three"},
        9: {"19 cm³": "Added the edges instead of multiplying them",
            "200 cm": "Correct number, but a volume needs cubic units"},
        10: {"(3, 6)": "Gave the coordinates the wrong way round"},
    },
    "G": {
        1: {colswap("20.3", "8.47"): "Subtracted the smaller digit from the larger in each column instead of borrowing, as on Test A"},
        2: {"42": "Left out the 0 in the quotient when 4 ÷ 23 did not go"},
        4: {dec(D("0.47") + D("3.68")): "Lined up the last digits instead of the decimal points"},
        5: {"1/10": "Gave the relationship the wrong way round",
            "0.1": "Gave the relationship the wrong way round"},
        6: {dec(D("63.8") / 10): "Moved the point one place: read 10² as 10",
            dec(D("63.8") / 20): "Read 10² as 10 × 2",
            dec(D("63.8") * 100): "Multiplied by 100 instead of dividing"},
        7: {"7.39": "Cut off the last digit instead of rounding up",
            "7.3": "Cut off at the tenths instead of rounding to the hundredths"},
        8: {"58 cm": "Correct number, but a volume needs cubic units, as on Tests C and F",
            "58": "Correct number, but no units, as on Test E"},
        9: {mixed(F(19, 3) + F(11, 4)): "Added 2 3/4 instead of subtracting it"},
        10: {"1 1/2": "Dropped the minus sign", "3 1/2": "Treated –2 1/2 as +2 1/2"},
    },
    "H": {
        1: {"5/3": "Divided 5 by 3 instead of 3 by 5",
            "1 2/3": "Divided 5 by 3 instead of 3 by 5"},
        2: {"greater than": "Assumed multiplying always makes a number bigger",
            "greater": "Assumed multiplying always makes a number bigger"},
        3: {f"{mixed(F(9, 4) + F(5, 3))} miles": "Added the distances instead of subtracting",
            f"{mixed(1 + (F(2, 3) - F(1, 4)))} miles":
                "Subtracted the smaller fraction from the larger (2/3 – 1/4) instead of borrowing",
            f"{mixed(F(9, 4) - F(5, 3))}": "Correct number, but no units"},
        4: {str(2 * 3): "Flipped the dividend and multiplied, as on Test C (2/1 × 3)",
            mixed(F(1, 2) * 3): "Multiplied by 3 instead of dividing"},
        5: {dec(D(15) * D("0.25")): "Found 25% of 15 instead of the whole",
            dec(D(15) * D("1.25")): "Added 25% to 15 instead of finding the whole"},
        6: {usd(D(80) * D("0.65")): "Took 35% off in one step instead of 25% then 10%",
            usd(D(80) * D("0.75")): "Applied only the first discount",
            usd(D(80) * D("0.25") * D("0.1")): "Took 10% of the $20 discount instead of the new price, as on Test A",
            usd(D(80) * D("0.25") + D(60) * D("0.1")): "Gave the total discount, not the final price",
            "54": "Correct number, but no $ sign"},
        8: {"48": "Gave Dad's age instead of Mia's", "48 years": "Gave Dad's age instead of Mia's"},
        9: {"54 cm²": "Forgot to halve base × height",
            "27 cm": "Correct number, but an area needs square units",
            "27": "Correct number, but no units"},
        10: {"-1": "Sign error: two negatives multiply to a positive",
             "–1": "Sign error: two negatives multiply to a positive"},
    },
}
WRONG["I"] = {
    1: {"4 cm³": "Right number, but a height is a length: cm, not cm³",
        "4": "Correct number, but no units",
        "3600 cm": "Multiplied all three numbers instead of dividing"},
    2: {colswap("40.2", "17.65"): "Subtracted the smaller digit from the larger in each column instead of borrowing"},
    5: {nocarry("5.67", "2.85"): "Lined up correctly but never carried",
        dec(D("5.67") + D("2.85") - 1): "Dropped the carry into the ones, as on Test G"},
    6: {f"{mixed(F(3, 2) + F(1, 2))} cups": "Multiplied only the 2 by 3/4 and kept the 1/2",
        mixed(F(15, 8)): "Correct number, but no units"},
    7: {"9 + 6 × 4": "Left out the parentheses, so the multiplying happens first",
        "4 × 9 + 6": "Multiplied before adding"},
    8: {dec(D("14.4") * 6): "Multiplied by 6 instead of dividing",
        dec(D("14.4") - 6): "Subtracted 6 instead of dividing"},
    9: {mixed(F(11, 5)): "Dropped the minus sign",
        f"–{mixed(F(16, 5) + 1)}": "Added the positive parts to the size of the negative number, as on Test G",
        f"-{mixed(F(16, 5) + 1)}": "Added the positive parts to the size of the negative number, as on Test G"},
    10: {usd(150): "Assumed up 20% then down 20% cancel out",
         usd(D(150) * D("1.2")): "Applied only the increase",
         usd(D(150) * D("0.8")): "Applied only the decrease",
         usd(D(30) * D("0.2")): "Took 20% of the $30 increase instead of the new price, as on Test A",
         "144": "Correct number, but no $ sign"},
}
WRONG["J"] = {
    1: {"9 cups": "Added 6 to both (2 -> 8, so 3 -> 9) instead of multiplying by 4",
        f"{mixed(F(2, 3) * 8)} cups": "Turned the ratio upside down: 2/3 of 8",
        "12": "Correct number, but no units"},
    2: {"yes": "Saw both amounts going up and called it proportional without checking the unit price",
        "Yes": "Saw both amounts going up and called it proportional without checking the unit price"},
    3: {f"{dec(D(17) / 2)} miles": "Forgot to take off the $3 fee first",
        f"{(17 + 3) // 2} miles": "Added the $3 fee instead of taking it off",
        "7": "Correct number, but no units"},
    4: {"40 m²": "Forgot to halve base × height, as on Test H",
        "20 m": "Correct number, but an area needs square units",
        "20": "Correct number, but no units"},
    5: {dec(D("4.6") * 10): "Moved the point one place: read 10³ as 10",
        dec(D("4.6") * 100): "Moved the point two places",
        dec(D("4.6") * 30): "Read 10³ as 10 × 3"},
    6: {"greater than": "Assumed multiplying always makes a number bigger, as on Test H",
        "greater": "Assumed multiplying always makes a number bigger, as on Test H"},
    7: {"1/10": "Gave the relationship the wrong way round", "0.1": "Gave the relationship the wrong way round"},
    8: {"-3": "Sign error: two negatives multiply to a positive",
        "–3": "Sign error: two negatives multiply to a positive"},
    9: {f"{mixed(1 + 2 + F(3 + 1, 4 + 3))} m": "Added the numerators and the denominators: 3/4 + 1/3 = 4/7",
        mixed(F(7, 4) + F(7, 3)): "Correct number, but no units"},
    10: {"(3, 5)": "Gave the coordinates the wrong way round (up before across)",
         "(0, 3)": "Kept the origin's x-coordinate and applied only the vertical move, as on Test D"},
}
WRONG["K"] = {
    1: {usd(D(60) * D("0.85")): "Combined +10% and –25% into –15%",
        usd(D(60) * D("0.75")): "Applied only the decrease",
        usd(D(60) * D("1.1")): "Applied only the increase",
        usd(D(6) * D("0.25")): "Took 25% of the $6 increase instead of the new price, as on Test A",
        "49.50": "Correct number, but no $ sign", "49.5": "Correct number, but no $ sign"},
    2: {"no": "Said not proportional, though y ÷ x is 3 every time",
        "No": "Said not proportional, though y ÷ x is 3 every time"},
    3: {"250": "Correct number, but no units",
        f"{150 // 3} miles": "Found the speed (miles in one hour), not the distance in 5 hours",
        f"{150 * 3 // 5} miles": "Turned the rate upside down: 150 × 3 ÷ 5"},
    4: {"30000 cm": "Correct number, but a volume needs cubic units",
        "30000": "Correct number, but no units",
        "95 cm³": "Added the edges instead of multiplying them"},
    6: {dec(D("7.56") / D("0.36") / 10): "Decimal point one place out",
        dec(D("7.56") / D("0.36") / 100): "Decimal point two places out"},
    7: {str(110 // 15): "Divided the total by 15 without taking off the $20 first",
        str((110 + 20) // 15): "Added the $20 instead of taking it off"},
    8: {colswap("9.05", "3.68"): "Subtracted the smaller digit from the larger in each column instead of borrowing"},
    9: {mixed(F(7, 4)): "Dropped the minus sign",
        f"–{mixed(F(9, 2) + F(11, 4))}": "Added the sizes and kept the minus sign, moving away from zero (as on Tests G and I)",
        f"-{mixed(F(9, 2) + F(11, 4))}": "Added the sizes and kept the minus sign, moving away from zero (as on Tests G and I)"},
    10: {"-10": "Kept a minus sign: two negatives make a positive (as on Test J)",
         "–10": "Kept a minus sign: two negatives make a positive (as on Test J)"},
}
WRONG["L"] = {
    1: {"4 – 2m": "Wrote the subtraction the wrong way round", "4-2m": "Wrote the subtraction the wrong way round",
        "2m + 4": "Added 4 instead of taking it away"},
    2: {f"{mixed(2 + (F(2, 3) - F(1, 4)))} kg": "Subtracted the smaller fraction from the larger (2/3 – 1/4) instead of borrowing",
        f"{mixed(F(13, 4) + F(5, 3))} kg": "Added instead of subtracting",
        mixed(F(13, 4) - F(5, 3)): "Correct number, but no units"},
    3: {dec(D(80) * D("0.65")): "Found the part that is left (65%), not 35%",
        dec(D(80) / D("0.35")): "Divided by 35% instead of multiplying"},
    4: {f"{mixed(F(10, 3) / 5)} m": "Found 1/5 of the rope instead of 3/5 (as on Test I, divided instead of taking the fraction)",
        f"{mixed(F(10, 3) - F(3, 5))} m": "Subtracted 3/5 instead of finding 3/5 of the rope",
        "2": "Correct number, but no units"},
    5: {mixed(F(5, 4)): "Multiplied by 1/4 instead of dividing",
        "1/20": "Flipped the dividend instead of the divisor, as on Test C"},
    6: {"7": "Gave the x-coordinate, the distance across, not up"},
    7: {"less than": "Thought multiplying by a fraction always makes a number smaller",
        "less": "Thought multiplying by a fraction always makes a number smaller"},
    8: {"18 m²": "Halved base × height as for a triangle; a parallelogram is not halved",
        "36 m": "Correct number, but an area needs square units",
        "36": "Correct number, but no units"},
    9: {dec(D("52.7") / 100): "Moved the point two places: read 10³ as 100",
        dec(D("52.7") / 10): "Moved the point one place",
        dec(D("52.7") * 1000): "Multiplied by 1000 instead of dividing"},
    10: {"10": "Gave the relationship the wrong way round", "10 times": "Gave the relationship the wrong way round"},
}
WRONG["M"] = {
    1: {"cm²": "Picked square units, which measure a flat area", "cm": "Picked a length unit"},
    2: {"(18, 9)": "Wrote the pair the wrong way round (B before A)",
        "(12, 24)": "Took the 5th terms: counted from 3 and 6 instead of from 0",
        "(9, 12)": "Added 3 to B instead of 6"},
    3: {str(cubes_visible(4, 3, 2)): "Counted only the cubes that can be seen",
        str(4 + 3 + 2): "Added the edges instead of multiplying"},
    4: {str(cubes_visible(3, 2, 3)): "Counted only the cubes that can be seen",
        str(3 + 2 + 3): "Added the edges instead of multiplying"},
    5: {"A": "Missed that a square is a rectangle", "C": "Missed that a square has four right angles too",
        "A, B, C, D": "Thought every four-sided shape has right angles"},
    6: {"A": "Missed the rhombus: it is a parallelogram with equal sides",
        "A, B, C": "Counted the trapezoid, which has only one pair of parallel sides",
        "A, C, D": "Counted the kite, which has no parallel sides"},
    7: {"8 cups": "Counted the glasses (the x marks) instead of adding the amounts", "8": "Counted the glasses",
        f"{mixed(F(1, 4) + F(1, 2) + F(3, 4) + 1)} cups": "Added each amount once, ignoring how many x marks it has",
        mixed(F(19, 4)): "Correct number, but no units"},
    8: {"1 cup": "Gave the fullest glass, not the difference", "1/4 cup": "Gave the emptiest glass, not the difference",
        "3/4": "Correct number, but no units"},
    9: {"(3, 5)": "Gave the coordinates the wrong way round (north before east)"},
    10: {"5": "Gave C's y-coordinate, not the distance from A", "6": "Counted grid lines, not spaces"},
}
WRONG["N"] = {
    1: {"480 in": "Correct number, but a volume needs cubic units", "480": "Correct number, but no units",
        f"{12 * 8} in³": "Multiplied only two of the edges, as on Test K",
        f"{12 + 5 + 8} in³": "Added the edges instead of multiplying them"},
    2: {f"{45 // 3} pages": "Found the rate (pages in one minute), not the pages in 8 minutes",
        "120": "Correct number, but no units"},
    3: {nocarry("6.48", "2.97"): "Lined up correctly but never carried",
        dec(D("6.48") + D("2.97") - 1): "Dropped the carry into the ones, as on Test G"},
    4: {f"{mixed(1 + 2 + F(2 + 3, 3 + 4))} miles": "Added the numerators and the denominators: 2/3 + 3/4 = 5/7",
        mixed(F(5, 3) + F(11, 4)): "Correct number, but no units"},
    5: {mixed(F(7, 3)): "Dropped the minus sign",
        f"–{mixed(F(10, 3) + 1)}": "Added the sizes and kept the minus sign, moving away from zero (as on Tests G and I)",
        f"-{mixed(F(10, 3) + 1)}": "Added the sizes and kept the minus sign, moving away from zero (as on Tests G and I)"},
    6: {str(6 * 15 - 7 + 4): "Ignored the parentheses and multiplied first"},
    7: {f"{mixed(F(21, 4) / 3)} km": "Found 1/3 of the trail instead of 2/3 (as on Test I, divided instead of taking the fraction)",
        f"{mixed(F(21, 4) - F(2, 3))} km": "Subtracted 2/3 instead of finding 2/3 of the trail",
        "3 1/2": "Correct number, but no units"},
    8: {"12:15": "Wrote girls to boys: the order is the other way round",
        "4:5": "Wrote girls to boys: the order is the other way round",
        "12 to 15": "Wrote girls to boys: the order is the other way round"},
    9: {"30 cm": "Correct number, but a volume needs cubic units", "30": "Correct number, but no units",
        f"{mixed(4 + 3 + F(5, 2))} cm³": "Added the edges instead of multiplying them"},
    10: {"9": "Gave the constant term, not the number multiplying x", "5x": "Gave the whole term, not its coefficient"},
}
WRONG["O"] = {
    1: {usd(D(50) * D("0.9")): "Combined –20% and +10% into –10%",
        usd(D(50) * D("0.8")): "Applied only the decrease",
        usd(D(50) * D("1.1")): "Applied only the increase",
        "44": "Correct number, but no $ sign", "44.00": "Correct number, but no $ sign"},
    2: {str(108 // 12): "Divided the total by 12 without taking off the $24 first"},
    3: {"11": "Added the two coordinates, as on Test L", "8": "Gave the y-coordinate, the distance up, not across"},
    4: {"5": "Treated three negatives like two: the answer stays negative"},
    5: {"8 m": "Counted the ribbons (the x marks) instead of adding the lengths", "8": "Counted the ribbons",
        f"{mixed(F(1, 8) + F(3, 8) + F(1, 2) + F(3, 4))} m": "Added each length once, ignoring how many x marks it has",
        mixed(F(29, 8)): "Correct number, but no units"},
    6: {"70 ft²": "Forgot to halve base × height, as on Test H",
        "35 ft": "Correct number, but an area needs square units", "35": "Correct number, but no units"},
    7: {str(2 * 3 + 3 * 2): "Multiplied the base by the exponent: 2 × 3 + 3 × 2"},
    8: {"A": "Picked a question with one answer", "C": "Picked a question with one answer"},
    9: {usd(D(4) / 10): "Divided the wrong way round: 4 ÷ 10", "2.50": "Correct number, but no $ sign",
        "2.5": "Correct number, but no $ sign"},
    10: {"4/7 m": "Divided 4 by 7 instead of 7 by 4", "1 3/4": "Correct number, but no units"},
}
WRONG["P"] = {
    1: {"yes": "Saw both amounts going up and called it proportional without checking each ticket's price, as on Test J",
        "Yes": "Saw both amounts going up and called it proportional without checking each ticket's price, as on Test J"},
    3: {"less than": "Thought multiplying by a fraction always makes a number smaller, as on Test L",
        "less": "Thought multiplying by a fraction always makes a number smaller, as on Test L"},
    4: {dec(D("8.4") / 100): "Moved the point two places, as on Test L",
        dec(D("8.4") / 10): "Moved the point one place",
        dec(D("8.4") * 1000): "Multiplied by 1000 instead of dividing"},
    5: {dec(D(24) * D("0.4")): "Found 40% of 24 instead of the whole",
        dec(D(24) * D("1.4")): "Added 40% to 24 instead of finding the whole"},
    6: {"1/10": "Gave the relationship the wrong way round", "0.1": "Gave the relationship the wrong way round"},
    7: {frac(F(9, 4) * F(3, 8)): "Multiplied instead of dividing",
        "1/6": "Divided 3/8 by 2 1/4 instead of 2 1/4 by 3/8"},
    8: {"3 × 12 – y": "Left out the parentheses, so only 12 is multiplied by 3",
        "3(y – 12)": "Wrote the difference the wrong way round"},
    9: {"5": "Gave the largest value, not the range", "10": "Counted the students instead"},
    10: {"8.29": "Cut off the last digits instead of rounding up"},
}
TESTS = (("A", A), ("B", B), ("C", C), ("D", Dd), ("E", E), ("F", Ff), ("G", G), ("H", Hh),
         ("I", I), ("J", J), ("K", K), ("L", Ll), ("M", M), ("N", N), ("O", O), ("P", P))

for code, qs in TESTS:
    for i, q in enumerate(qs):
        cw = WRONG[code].get(i + 1, {})
        assert not (set(cw) & set(q["accept"])), (code, i + 1)
        q["common_wrong_answers"] = cw
assert [q["answer"] for q in A] == ["3.615", "25.2", "0.4", "26.8", "2.34", "60", "$32.40", "$3.75", "9 years", "40¢"]
assert [q["answer"] for q in B] == ["7.64", "0.042", "38", "22.205", "2.25", "80 students", "$198.00", "$6.30", "18 years", "$1.80"]
assert [q["answer"] for q in C] == ["21", "0.4", "1242", "39", "6.25", "11/12", "3/10", "1/12", "250 cm", "60 cm³"], [q["answer"] for q in C]
assert [q["answer"] for q in Dd] == ["14", "0.1", "1972", "102", "3.75", "7/12", "1/4", "12", "3500 m", "(3, 2)"], [q["answer"] for q in Dd]
# Every grade-5 domain has to be represented across the two new tests.
_domains = {SK[q["skill"]][1].split(".")[1] for q in C + Dd}
assert _domains == {"OA", "NBT", "NF", "MD", "G"}, _domains
assert [q["answer"] for q in E] == ["15", "28248", "0.27", "3.63", "3 5/6", "1/15",
                                    "4.5 m", "36 cm³", "(4, 0)", "(0, 0)"], [q["answer"] for q in E]
assert [q["answer"] for q in Ff] == ["26", "44820", "251535", "2.1", "1 7/12", "130 cm",
                                     "5", "(2, 7)", "200 cm³", "(6, 3)"], [q["answer"] for q in Ff]
assert [q["answer"] for q in G] == ["11.83", "402", "47922", "8.38", "10", "0.638", "7.40",
                                    "58 cm³", "3 7/12", "–1 1/2"], [q["answer"] for q in G]
assert [q["answer"] for q in Hh] == ["3/5", "less than", "7/12 mile", "1/6", "60", "$54.00",
                                     "7p + 45", "12 years", "27 cm²", "1"], [q["answer"] for q in Hh]
assert [q["answer"] for q in I] == ["4 cm", "22.55", "231", "124672", "8.52", "1 7/8 cups",
                                    "4 × (9 + 6)", "2.4", "–2 1/5", "$144.00"], [q["answer"] for q in I]
assert [q["answer"] for q in J] == ["12 cups", "no", "7 miles", "20 m²", "4600", "less than",
                                    "10", "3", "4 1/12 m", "(5, 3)"], [q["answer"] for q in J]
assert [q["answer"] for q in K] == ["$49.50", "yes", "250 miles", "30000 cm³", "210976", "21",
                                    "6", "5.37", "–1 3/4", "10"], [q["answer"] for q in K]
assert [q["answer"] for q in Ll] == ["2m – 4", "1 7/12 kg", "28", "2 m", "20", "2", "greater than",
                                     "36 m²", "0.0527", "1/10"], [q["answer"] for q in Ll]
assert [q["answer"] for q in M] == ["cm³", "(9, 18)", "24", "18", "A, C", "A, C", "4 3/4 cups",
                                    "3/4 cup", "(5, 3)", "4"], [q["answer"] for q in M]
assert [q["answer"] for q in N] == ["480 in³", "120 pages", "9.45", "4 5/12 miles", "–2 1/3", "52",
                                    "3 1/2 km", "15:12", "30 cm³", "5"], [q["answer"] for q in N]
assert [q["answer"] for q in O] == ["$44.00", "7", "3", "–5", "3 5/8 m", "35 ft²", "17", "B",
                                    "$2.50", "1 3/4 m"], [q["answer"] for q in O]
assert [q["answer"] for q in P] == ["no", "359154", "greater than", "0.0084", "60", "10", "6",
                                    "3(12 – y)", "4", "8.30"], [q["answer"] for q in P]
assert cubes_visible(4, 3, 2) == 18 and cubes_visible(3, 2, 3) == 14
# Tests E and F exist to close gaps, so every question must target a component
# that the record shows as untested or as a confirmed mistake.
_targets = {cid for q in E + Ff for cid in SK[q["skill"]][2]}
assert len(_targets) >= 15, len(_targets)

# ---------------- Layout ----------------
W, H = A4
M = 40
NAVY = colors.HexColor("#1F3A5F")
GREY = colors.HexColor("#6B7280")
LINE = colors.HexColor("#C9CED6")
FAINT = colors.HexColor("#9CA3AF")

qstyle = ParagraphStyle("q", fontName="Helvetica", fontSize=11, leading=14.5)
small = ParagraphStyle("s", fontName="Helvetica", fontSize=9.5, leading=12.5)
cell = ParagraphStyle("c", fontName="Helvetica", fontSize=10, leading=13)
cellb = ParagraphStyle("cb", fontName="Helvetica-Bold", fontSize=10, leading=13)

MK = 16          # corner marker size (pt)
MK_INSET = 18    # distance from page edge
# Marker centres; the JSON regions are normalised to the rectangle between them
MX0, MX1 = MK_INSET + MK / 2, W - MK_INSET - MK / 2
MY0, MY1 = MK_INSET + MK / 2, H - MK_INSET - MK / 2   # PDF coords (origin bottom-left)

def norm(x, y, w, h):
    """PDF rect -> [x, y, w, h] as fractions of the marker rectangle, origin top-left."""
    sx, sy = MX1 - MX0, MY1 - MY0
    return [round((x - MX0) / sx, 4), round((MY1 - (y + h)) / sy, 4), round(w / sx, 4), round(h / sy, 4)]

def corner_markers(c):
    c.setFillColor(colors.black)
    for cx, cy in ((MX0, MY0), (MX1, MY0), (MX0, MY1), (MX1, MY1)):
        c.rect(cx - MK / 2, cy - MK / 2, MK, MK, stroke=0, fill=1)

def qr_code(c, payload, x, y, size):
    w = qr.QrCodeWidget(payload, barLevel="M")
    b = w.getBounds()
    d = Drawing(size, size, transform=[size / (b[2] - b[0]), 0, 0, size / (b[3] - b[1]), 0, 0])
    d.add(w)
    renderPDF.draw(d, c, x, y)

# ---------------- Figures ----------------
# Small drawings inside a question box, top right. Every answer that depends on
# a figure is computed from the same data the figure is drawn from.
FIG_W, FIG_H = 112, 74


def draw_figure(c, fig, fx, fy, fw, fh):
    kind = fig["kind"]
    c.saveState()
    c.setLineWidth(0.7); c.setStrokeColor(colors.black)
    if kind == "cubes":
        l, w, h = fig["l"], fig["w"], fig["h"]
        dx, dy = 0.45, 0.35                                   # depth, in cube sizes
        s = min(fw / (l + dx * w), fh / (h + dy * w))
        ox = fx + (fw - s * (l + dx * w)) / 2
        oy = fy + (fh - s * (h + dy * w)) / 2
        # Painter's order: back rows first, bottom up, left to right, so nearer
        # cubes cover the hidden edges of the ones behind.
        for y in reversed(range(w)):
            for z in range(h):
                for x in range(l):
                    bx, by = ox + x * s + y * dx * s, oy + z * s + y * dy * s
                    def poly(pts, grey):
                        c.setFillColor(colors.Color(grey, grey, grey))
                        path = c.beginPath(); path.moveTo(*pts[0])
                        for pt in pts[1:]: path.lineTo(*pt)
                        path.close(); c.drawPath(path, stroke=1, fill=1)
                    poly([(bx, by), (bx + s, by), (bx + s, by + s), (bx, by + s)], 0.93)
                    poly([(bx, by + s), (bx + s, by + s), (bx + s + dx * s, by + s + dy * s),
                          (bx + dx * s, by + s + dy * s)], 0.99)
                    poly([(bx + s, by), (bx + s + dx * s, by + dy * s),
                          (bx + s + dx * s, by + s + dy * s), (bx + s, by + s)], 0.80)
    elif kind == "shapes":
        cw, ch = fw / 2, fh / 2
        for i, shp in enumerate(fig["shapes"]):
            cx, cy = fx + (i % 2) * cw, fy + fh - (i // 2 + 1) * ch
            sc = min(cw - 14, ch - 6)
            pts = [(cx + 12 + px * sc, cy + 3 + py * sc) for px, py in shp["pts"]]
            path = c.beginPath(); path.moveTo(*pts[0])
            for pt in pts[1:]: path.lineTo(*pt)
            path.close(); c.setFillColor(colors.HexColor("#E8EDF4")); c.drawPath(path, stroke=1, fill=1)
            c.setFillColor(colors.black); c.setFont("Helvetica-Bold", 9)
            c.drawString(cx + 2, cy + ch / 2 - 3, shp["label"])
    elif kind == "lineplot":
        d, top = fig["denominator"], F(fig["max"])
        ticks = int(top * d)
        x0, x1, base = fx + 8, fx + fw - 8, fy + 14
        c.line(x0, base, x1, base)
        c.setFont("Helvetica", 6.5); c.setFillColor(colors.black)
        for t in range(ticks + 1):
            tx = x0 + (x1 - x0) * t / ticks
            c.line(tx, base - 3, tx, base + 3)
            c.drawCentredString(tx, base - 10, frac(F(t, d)) if t else "0")
        c.setFont("Helvetica-Bold", 8)
        for val, n in fig["values"].items():
            tx = x0 + (x1 - x0) * float(F(val) / top)
            for k in range(n):
                c.drawCentredString(tx, base + 6 + k * 8, "x")
        c.setFont("Helvetica", 6.5)
        c.drawCentredString((x0 + x1) / 2, fy + fh - 6, fig["caption"])
    elif kind == "grid":
        n = fig["size"]
        cell = min((fw - 14) / n, (fh - 12) / n)
        gx, gy = fx + 12, fy + 9
        c.setStrokeColor(colors.HexColor("#B0B6BE")); c.setLineWidth(0.4)
        for k in range(n + 1):
            c.line(gx + k * cell, gy, gx + k * cell, gy + n * cell)
            c.line(gx, gy + k * cell, gx + n * cell, gy + k * cell)
        c.setStrokeColor(colors.black); c.setLineWidth(0.9)
        c.line(gx, gy, gx + n * cell, gy); c.line(gx, gy, gx, gy + n * cell)
        c.setFont("Helvetica", 6); c.setFillColor(colors.black)
        for k in range(n + 1):
            c.drawCentredString(gx + k * cell, gy - 7, str(k))
            c.drawRightString(gx - 2, gy + k * cell - 2, str(k))
        for label, (px, py) in fig["points"].items():
            c.circle(gx + px * cell, gy + py * cell, 1.8, stroke=0, fill=1)
            c.setFont("Helvetica-Bold", 7.5)
            c.drawString(gx + px * cell + 2.5, gy + py * cell + 2.5, label)
    else:
        raise ValueError(f"unknown figure kind {kind!r}")
    c.restoreState()


def questions_page(c, code, qs, spec):
    # The four corner markers are no longer printed. Registration is done on the
    # ten answer boxes (align_and_crop.py), which survives a cut-off edge; the
    # markers were only ever used by the earlier corner-based alignment and were
    # unreadable on a casually framed photo anyway. The marker RECTANGLE stays as
    # the coordinate frame the spec's regions are normalised to - that is a
    # convention, not something that has to be drawn.
    payload = spec["qr_payload"]
    # 62pt put the code at 10% of page width, which in a photo taken at any
    # angle or distance drops below the ~3px-per-module the detector needs: one
    # sheet decoded at 85px, two failed at roughly 50-65px and had to be read
    # as whole pages instead. 90pt gives about 45% more linear resolution for
    # the same framing, at no cost but a little margin.
    qsize = 90
    qr_code(c, payload, W - M - qsize + 4, H - M - qsize + 8, qsize)
    c.setFillColor(NAVY)
    c.setFont("Helvetica-Bold", 20)
    c.drawString(M, H - M - 14, f"Math Practice Test {code}")
    c.setFillColor(GREY)
    c.setFont("Helvetica", 10.5)
    # The rule stops short of the QR instead of running under it: a line across
    # the code is exactly the kind of interference that stops it decoding, and a
    # failed decode drops the sheet onto the less reliable whole-page path.
    c.setStrokeColor(NAVY); c.setLineWidth(1.2)
    c.line(M, H - M - 74, W - M - qsize - 12, H - M - 74)

    # The grid has to start below the QR, not beside it: at 90pt the code
    # reaches down to H - M - 82, and the old top of H - M - 68 ran the first
    # right-hand box underneath it.
    top, bottom = H - M - 86, M + 14
    rows, cols, gap = 5, 2, 10
    bw = (W - 2 * M - gap) / cols
    bh = (top - bottom - gap * (rows - 1)) / rows
    ans_w, ans_h = bw * 0.52, 30
    for i, q in enumerate(qs):
        r, col = divmod(i, cols)
        x = M + col * (bw + gap)
        y = top - r * (bh + gap) - bh
        c.setStrokeColor(LINE); c.setLineWidth(0.8)
        c.roundRect(x, y, bw, bh, 6, stroke=1, fill=0)
        c.setFillColor(NAVY)
        c.circle(x + 16, y + bh - 16, 10, stroke=0, fill=1)
        c.setFillColor(colors.white); c.setFont("Helvetica-Bold", 10.5)
        c.drawCentredString(x + 16, y + bh - 19.6, str(i + 1))
        p = Paragraph(q["text"], qstyle)
        fig = q.get("figure")
        _, ph = p.wrap(bw - 44 - ((FIG_W + 6) if fig else 0), bh)
        p.drawOn(c, x + 32, y + bh - 9 - ph)
        if fig:
            # Top right, clear of the answer box below it, so the regions the
            # photo is aligned on are exactly where they always are.
            draw_figure(c, fig, x + bw - FIG_W - 8, y + bh - 8 - FIG_H, FIG_W, FIG_H)
        # answer box (bottom-right), kept separate from working area
        ax, ay = x + bw - ans_w - 8, y + 8
        c.setStrokeColor(colors.black); c.setLineWidth(1.1)
        c.rect(ax, ay, ans_w, ans_h, stroke=1, fill=0)
        c.setFillColor(GREY); c.setFont("Helvetica", 9)
        c.drawRightString(ax - 6, ay + ans_h / 2 - 3, "Answer")
        # working area = space between question text and answer box
        wy0 = ay + ans_h + 6
        wy1 = y + bh - 12 - ph
        c.setFillColor(FAINT); c.setFont("Helvetica-Oblique", 8)
        c.drawString(x + 10, wy1 - 10, "Working")
        spec["questions"][i]["regions"] = {
            "question_box": norm(x, y, bw, bh),
            "working": norm(x + 4, y + 4, bw - 8, wy1 - y - 4),
            "answer": norm(ax, ay, ans_w, ans_h),
        }
    c.setFillColor(GREY); c.setFont("Helvetica", 8.5)
    c.drawRightString(W - M, M - 2, f"Test {code} · {spec['fingerprint']}  ·  Answer key on page 2")

def answers_page(c, code, qs, spec):
    c.setFillColor(NAVY); c.setFont("Helvetica-Bold", 20)
    c.drawString(M, H - M - 14, f"Answer Key: Math Practice Test {code}")
    c.setFillColor(GREY); c.setFont("Helvetica", 10.5)
    c.drawString(M, H - M - 32, "Answers involving money or ages should include units ($, ¢, years). Working shows one way to solve each.")
    c.setStrokeColor(NAVY); c.setLineWidth(1.2)
    c.line(M, H - M - 42, W - M, H - M - 42)
    data = [[Paragraph(h, cellb) for h in ("Q", "Answer", "Working", "Skill checked")]]
    for i, q in enumerate(qs):
        name, std, _ = SK[q["skill"]]
        data.append([Paragraph(str(i + 1), cell), Paragraph(f"<b>{q['answer']}</b>", cell),
                     Paragraph(q["working"], small), Paragraph(f"{name} ({std})", small)])
    avail = W - 2 * M
    t = Table(data, colWidths=[24, 78, avail - 24 - 78 - 140, 140])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#E8EDF4")),
        ("LINEBELOW", (0, 0), (-1, -1), 0.5, LINE),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 7), ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
        ("LEFTPADDING", (0, 0), (-1, -1), 5),
    ]))
    _, th = t.wrap(avail, H)
    t.drawOn(c, M, H - M - 58 - th)
    c.setFillColor(GREY); c.setFont("Helvetica", 8.5)
    c.drawRightString(W - M, M - 2, f"Test {code} · {spec['fingerprint']}  ·  Answer key")

def build_spec(code, qs):
    spec = {
        "test_id": code, "fingerprint": None, "qr_payload": None,
        "title": f"Math Practice Test {code}", "page_size": "A4",
        # California adopted CCSS for mathematics; at every standard used here the
        # California framework carries the identical code and identical text, and
        # differs only in its CASE identifier. Checked against both jurisdictions
        # in the Learning Commons knowledge graph, 2026-10-07.
        "standards_jurisdiction": "California / CCSS (identical codes and text at these standards)",
        "regions_note": "Regions are [x, y, width, height] as fractions of the rectangle between the centres of the four corner markers, origin top-left. Warp the photo so the markers map to that rectangle, then crop. The working region is everything below the question text, so it also contains the answer box.",
        "questions": [],
    }
    for i, q in enumerate(qs):
        name, std, lcs = SK[q["skill"]]
        spec["questions"].append({
            "id": f"{code}{i+1}", "number": i + 1, "text": q["text"],
            "answer": q["answer"], "accept": q["accept"],
            "unit": q["unit"], "unit_required": q["unit_required"],
            "skill": name, "standard": std, "learning_component_ids": lcs,
            "common_wrong_answers": q["common_wrong_answers"],
            **({"figure": q["figure"]} if q.get("figure") else {}),
        })
    # The regions only exist once the page is laid out, and the fingerprint
    # covers them, so lay it out once on a throwaway canvas first. Nothing on
    # the layout depends on the payload, so the second pass places every box
    # identically.
    spec["qr_payload"] = spec["fingerprint"] = "-"
    questions_page(canvas.Canvas(io.BytesIO(), pagesize=A4), code, qs, spec)
    spec["fingerprint"] = fingerprint(spec)
    spec["qr_payload"] = f"mpt:test={code}&h={spec['fingerprint']}"
    return spec


# Decide everything before writing anything, so one refused letter leaves
# tests/ exactly as it was.
legacy = legacy_letters()
plan, refused = [], []
for code, qs in TESTS:
    if code in legacy:
        continue                                   # printed under the old &v= scheme
    spec = build_spec(code, qs)
    path = OUT / f"Math_Practice_Test_{code}.json"
    old = json.loads(path.read_text()).get("fingerprint") if path.exists() else None
    if old and old != spec["fingerprint"]:
        refused.append(f"  Test {code}: page 1 would change ({old} -> {spec['fingerprint']}). "
                       "It may already be printed - put the new questions under a new letter.")
        continue
    plan.append((code, qs, spec, "refreshed" if old else "new"))
if refused:
    sys.exit("Refusing to overwrite a sheet whose printed content changed:\n" + "\n".join(refused))

for code, qs, spec, what in plan:
    pdf = OUT / f"Math_Practice_Test_{code}.pdf"
    c = canvas.Canvas(str(pdf), pagesize=A4)
    c.setTitle(f"Math Practice Test {code}")
    questions_page(c, code, qs, spec)
    c.showPage()
    answers_page(c, code, qs, spec)
    c.showPage()
    c.save()
    (OUT / f"Math_Practice_Test_{code}.json").write_text(
        json.dumps(spec, indent=2, ensure_ascii=False))
    print(f"{what:<9} {pdf}  ({spec['qr_payload']})")
skipped = sorted(code for code, _ in TESTS if code in legacy)
if skipped:
    print(f"untouched (printed under the old scheme, specs in {LEGACY}): {', '.join(skipped)}")
