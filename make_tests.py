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
# and the box layout the crops rely on. Re-running the generator therefore writes
# only letters it has not written yet, and refuses to change a sheet that may
# already be in a child's hands. `--refresh` also rewrites the existing sheets, to
# carry new answers and known mistakes into their specs (page 1 comes out identical).
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
    # Tests Q, R and S: the next batch plan after N, O and P were marked.
    "g6evalexp": ("Evaluate an expression with an exponent for a given value", "6.EE.A.2.c",
                  ["5702c4ef-fbfc-533e-b5b5-a5cc126e7c3e", "ceb07b7c-b1cf-52cc-97ee-192d8a291f90"]),
    "g6distrib": ("Expand an expression with the distributive property", "6.EE.A.3",
                  ["977bc6f0-47f9-5d5f-942d-4f3477d4a2fe"]),
    "g6mean": ("Find the mean of a data set in context", "6.SP.B.5",
               ["912cf934-0cdc-5c68-ad4e-133023e02d82"]),
    # Sheets AC-AE: problem solving with heuristics. These ask the child to
    # reason about fractions rather than execute a procedure - choose the
    # operators, place the digits, equalise two amounts, estimate before
    # computing. Same standards, different demand.
    "g5fpuzzle_op": ("Choose + or - to make a fraction equation true", "5.NF.A.1",
                     ["d2565c2d-3930-54d3-864e-e532fd65cf6c",
                      "3f8f80e7-a5c3-56e5-bf2d-90c5bb5f4f08"]),
    "g5fpuzzle_digit": ("Place digits to make a fraction equation true", "5.NF.A.1",
                        ["3f8f80e7-a5c3-56e5-bf2d-90c5bb5f4f08"]),
    "g5fequal": ("Equalise two amounts by moving part of one", "5.NF.A.2",
                 ["ed662f1f-210b-5895-8841-60c021a792c2"]),
    "g5fbench": ("Use a benchmark fraction to judge whether a sum is reasonable", "5.NF.A.2",
                 ["1f6b0f81-22fb-5021-975c-b3a00269a1e9"]),
    "g6expr_id": ("Identify the expression for a phrase", "6.EE.A.2.a",
     ["115636bf-01c2-5c26-be47-a29f933a2974"]),
    "g5triclass": ("Classify triangles in a hierarchy", "5.G.B.4",
     ["8bd3a000-9afe-577e-8781-dd8b8d493289"]),
    "g5fmuleq": ("Write an equation for a fraction multiplication problem", "5.NF.B.6",
     ["ea894526-30b5-50a6-b312-6b4cfe38d624"]),
    "g6expwrite": ("Write a repeated product using an exponent", "6.EE.A.1",
     ["1f44c510-590f-575c-98ca-c19f2bbfd4c6"]),
    "g6factor": ("Factor an expression with the distributive property", "6.EE.A.3",
     ["8819fa6b-bd86-58b7-badd-df03a195db74"]),
    "g6opposite": ("Use signs for quantities in opposite directions", "6.NS.C.5",
     ["f57f8f6c-ec91-5b37-9632-fdb36c088666"]),
    "g6lcm": ("Find the least common multiple of two numbers", "6.NS.B.4",
     ["926bf4b0-e045-536b-ac02-2089d77cbf6c"]),
    "g5volspace": ("Volume as the space an object takes up", "5.MD.C.3",
     ["af5ac1f9-631b-583e-a202-f436b2c6065f"]),
    "g5exprread": ("Interpret an expression without evaluating it", "5.OA.A.2",
     ["fe00d7de-e6dc-58e5-b9ea-66e330a42eaa"]),
    "g6entity": ("View part of an expression as one quantity", "6.EE.A.2.b",
     ["1ca4a9fc-2a7b-50b8-b67a-3b850141a649"]),
    "g6equivsub": ("Use substitution to test whether expressions are equivalent", "6.EE.A.4",
     ["67cfaafc-d884-51af-b809-d3beb5308379"]),
    "g7ratmix": ("Add and subtract rational numbers", "7.NS.A.1.d",
     ["ce4afd4b-6f1d-5d6f-83df-ac9b90a40250"]),
    "g6deptable": ("Relate a table to an equation for a dependent variable", "6.EE.C.9",
     ["d29c0749-bd31-5ad3-8a3c-2a24769df8ce", "cc56ee36-cbb8-5387-b845-f41585c0660e"]),
    "g6fdivread": ("Interpret a quotient of fractions", "6.NS.A.1",
     ["63c4ca02-f441-59d8-af9b-681477d17f16"]),
    "g6ineqmath": ("Write an inequality for a mathematical condition", "6.EE.B.8",
     ["99fa4be6-09b5-5881-93be-8abcae5d7f71"]),
    "g4multi_plain": ("Solve a multi-step problem with the four operations", "4.OA.A.3",
     ["7e561083-58c0-554a-8cb0-ff5621464fad"]),
    "g5shapeattr2": ("Attributes of a category of figures apply to its subcategories", "5.G.B.3",
     ["e3e2af8b-6691-5559-b154-8d58303dde02"]),
    "g5fbetween": ("Identify the two whole numbers a fraction falls between", "5.NF.B.3",
     ["677ac9ea-e253-574e-9754-46a693260709"]),
    "g5patrel": ("Identify the relationship between corresponding terms", "5.OA.B.3",
     ["3e8126aa-6241-5782-9e20-7fa694a61e5a"]),
    "g6evalreal": ("Evaluate an expression in a real-world context", "6.EE.A.2.c",
     ["06806313-cfe4-5d7d-9646-fdcf8520cadf"]),
    "g6substineq": ("Use substitution to test an inequality", "6.EE.B.5",
     ["8fec2d18-79bd-53a4-8ef9-c4b7ee7a15d5", "a9e1847a-b8cc-5abb-9476-18e1ddb542ea"]),
    "g6gcf": ("Find the greatest common factor of two numbers", "6.NS.B.4",
              ["9bf54462-5fd0-59bf-8360-cd503e45b884"]),
    "g6signed": ("Use a negative number for a real-world quantity", "6.NS.C.5",
                 ["8119c47d-f394-50ff-b630-f4aa64763b52"]),
    "g6equiv": ("Decide whether two expressions are equivalent", "6.EE.A.4",
                ["52a53073-75a3-592d-a9cf-aba403b0d018"]),
    "g7prop_rep": ("Use a proportional relationship to find a missing value", "7.RP.A.2",
                   ["91a4d15a-cda6-510b-ba13-56d5bf536917"]),
    "g6center": ("A measure of center summarizes data with one number", "6.SP.A.3",
                 ["26d22200-e9bb-556c-81c1-c35a4c64a225"]),
    "g6ratiotable": ("Find a missing value in a ratio table", "6.RP.A.3.a",
                     ["23e8528c-1687-5088-9a16-d51bc8a145e6"]),
    "g6unitprice": ("Compare unit prices", "6.RP.A.3.b",
                    ["29e60e03-2920-51de-aff0-cb317dad7e54"]),
    # Tests T, U and V: the batch plan after Q, R and S were marked.
    "g7ratdiv": ("Divide rational numbers using properties of operations", "7.NS.A.2.c",
                 ["c48c1cff-df43-5290-8c24-3a7166311e44"]),
    "g6opp": ("The opposite of the opposite of a number is the number", "6.NS.C.6.a",
              ["a40a923f-8622-5b74-aa84-849e70cfbf65"]),
    "g6ineqpos": ("Read an inequality as positions on a number line", "6.NS.C.7.a",
                  ["e3f2391f-225c-580f-9331-7de98f609d83"]),
    "g6depvar": ("Write an equation for a dependent variable", "6.EE.C.9",
                 ["cc56ee36-cbb8-5387-b845-f41585c0660e"]),
    "g5coord_dist": ("Coordinates from distances to the two axes", "5.G.A.1",
                     ["9a9aba52-8867-53e9-b129-9bdb51a5442b", "ccfcad8c-5c0e-5b3e-8c98-78b149ecdd97"]),
    "g6subst": ("Use substitution to find which value makes an equation true", "6.EE.B.5",
                ["10b7ec1d-8484-542d-b7d8-e556ab71ceb5"]),
    "g6ineqwrite": ("Write an inequality x > c for a real-world condition", "6.EE.B.8",
                    ["56712271-b20c-563b-a20c-9535b5161e72"]),
    "g6abs": ("Absolute value as distance from 0", "6.NS.C.7.c",
              ["62c8cf40-084e-5b4c-ab3f-29f473273582"]),
    "g6convert": ("Use a ratio to convert measurement units", "6.RP.A.3.d",
                  ["18baa937-6c61-5248-93a4-1a5bfbc4e99a"]),
    "g6order": ("Order rational numbers in a real-world context", "6.NS.C.7.b",
                ["0a31d080-83c4-50e6-b6f1-b3fe448cfee9"]),
    "g6absorder": ("Tell absolute value apart from order", "6.NS.C.7.d",
                   ["f1a27da7-7faf-584a-af58-f16752145363"]),
    # Tests W, X and Y: the batch plan after T, U and V were marked.
    "g6quad4": ("Use coordinates to find a point a given distance away (same first coordinate)", "6.NS.C.8",
                ["1ba53b4c-32e9-5cd5-8ee2-6b595e72aa46"]),
    "g4multi": ("Solve a multi-step problem where a remainder must be interpreted", "4.OA.A.3",
                ["e1589f99-6dd3-56a0-b387-32ceadb75cc3", "165bed09-31f6-5e0f-be23-146fd2513912"]),
    "g7fdec": ("Convert a fraction to a decimal using long division", "7.NS.A.2.d",
               ["2ab6ac49-716f-507d-bce0-a9696013c6b2"]),
    "g6quadrant": ("Use the signs of an ordered pair to identify its quadrant", "6.NS.C.6.b",
                   ["ef1f09b2-f01e-5045-8446-28d6c9f74463"]),
    "g6numline": ("Find and position a rational number on a number line", "6.NS.C.6.c",
                  ["36d0fda5-a6ac-58c4-ba46-33343468ac4b"]),
    "g5fbench_sub": ("Use a benchmark fraction to estimate a difference", "5.NF.A.2",
                     ["109ac5cd-8a05-5f94-8bbb-001e3a91e3c8"]),
    "g7ratsub": ("Use properties of operations to subtract rational numbers", "7.NS.A.1.d",
                 ["7aa5ed91-3ba3-5eff-93af-77123a99843d"]),
    "g6speed": ("Solve a constant-speed problem with a unit rate", "6.RP.A.3.b",
                ["29e60e03-2920-51de-aff0-cb317dad7e54"]),
    "g7decrep": ("Tell whether the decimal form of a rational number ends or repeats", "7.NS.A.2.d",
                 ["0bd082cc-be74-564c-9cf4-941f5d959507"]),
    "g6reflect": ("Use the signs in ordered pairs to find a reflection across an axis", "6.NS.C.6.b",
                  ["8e0a9454-edb3-5fb9-be8a-c0f50cff2a4c"]),
    "g7addrw": ("Add and subtract rational numbers to solve a real-world money problem", "7.NS.A.3",
                ["1bff6614-a6c0-5ee1-84a5-0da4f870a38f", "39612eaf-3eed-57be-96d2-4ac4abda7d59"]),
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


# Tests Q, R and S are one batch from `skills.py --plan --sheets 3` after N, O and
# P were marked. 5.NF.A.2 has failed only on units, so it is aimed at the untested
# benchmark-estimate component instead of another addition word problem.
def test_q():
    """Batch sheet 1: volume, ratio, coordinates, a line plot, signed fractions,
    shapes, statistics, and three never-asked grade-6 standards."""
    qs = []
    v = 40 * 25 * 30                                # retest: K4 skipped a factor
    qs.append(Q("A fish tank is 40 cm long, 25 cm wide and 30 cm tall. What is its volume?",
                f"{v} cm³", [f"{v} cm³", f"{v} cm3", f"{v} cubic cm"], True,
                "40 × 25 = 1000 for the base; 1000 × 30 = 30000 cubic centimeters", "g5vol", "cm³"))
    v = F(8, 2) * 3
    qs.append(Q("A recipe uses 2 cups of flour for every 3 cups of milk. How much milk goes "
                "with 8 cups of flour?", f"{v} cups", [f"{v} cups", f"{v} cup"], True,
                "8 is 4 times 2, so the milk is 4 × 3 = 12 cups", "g6ratio", "cups"))
    qs.append(Q("A point is at (6, 2). How far is it from the x-axis?", "2", ["2", "2 units"],
                False, "The second number is the distance up from the x-axis", "g5coord_y"))
    plot = {"kind": "lineplot", "denominator": 8, "max": 1, "caption": "weight of each bag of rice (kg)",
            "values": {"1/8": 3, "1/4": 1, "1/2": 2, "3/4": 3}}
    vals = {F(k): n for k, n in plot["values"].items()}
    v = sum(k * n for k, n in vals.items())
    qs.append(Q("All the bags are put on one scale. What is the total weight?",
                f"{mixed(v)} kg", [f"{mixed(v)} kg", f"{frac(v)} kg"], True,
                "3 × 1/8 + 1/4 + 2 × 1/2 + 3 × 3/4 = 3/8 + 2/8 + 8/8 + 18/8 = 31/8 = 3 7/8 kg",
                "g5lineplot", "kg", figure=plot))
    v = F(3, 8) + F(-5, 2) + F(9, 8)                # retest: G10, I9 lost track of the negative
    assert v == -1
    qs.append(Q("Work out 3/8 + (–2 1/2) + 1 1/8", f"–{frac(-v)}", [f"–{frac(-v)}", f"-{frac(-v)}"],
                False, "Positives together: 3/8 + 1 1/8 = 1 1/2. Then 1 1/2 + (–2 1/2) = –1", "g7rat"))
    shapes = [("A", [(0.2, 0), (1, 0), (0.8, 0.6), (0, 0.6)]),             # slanted parallelogram
              ("B", [(0, 0), (1, 0), (0.55, 0.6), (0, 0.6)]),              # right trapezoid
              ("C", [(0.15, 0), (0.85, 0), (0.85, 0.7), (0.15, 0.7)]),     # square
              ("D", [(0.5, 0), (0.95, 0.45), (0.5, 0.72), (0.05, 0.45)])]  # kite
    v = ", ".join(L for L, pts in shapes if is_parallelogram(pts))
    qs.append(Q("Which of these shapes are parallelograms? Write the letters.", v, [v], False,
                "Both pairs of opposite sides parallel: the slanted parallelogram and the square. "
                "The trapezoid has only one pair", "g5shapeclass",
                figure={"kind": "shapes", "shapes": [{"label": L, "pts": pts} for L, pts in shapes]}))
    qs.append(Q("Which is a statistical question? A: How many pets does Mia have? B: How many "
                "pets do the families on our street have? C: How many legs does a spider have? "
                "Write the letter.", "B", ["B"], False,
                "Only B expects different answers from different families", "g6statq"))
    x = 4
    v = 3 * x ** 2 + 2
    qs.append(Q("Work out 3x² + 2 when x = 4", str(v), [str(v)], False,
                "Exponent first: 4² = 16. Then 3 × 16 = 48, + 2 = 50", "g6evalexp"))
    expr = ["12a + 20", "12a+20", "20 + 12a", "20+12a"]
    _expr_ok(expr, 4 * (3 * 7 + 5), a=7)
    qs.append(Q("Write 4(3a + 5) without parentheses.", expr[0], expr, False,
                "Multiply both terms by 4: 4 × 3a = 12a and 4 × 5 = 20", "g6distrib"))
    data = [2, 3, 8, 9, 13]
    v = F(sum(data), len(data))
    qs.append(Q(f"Ana scored {', '.join(map(str, data[:-1]))} and {data[-1]} points in five games. "
                "What is her mean score?", str(v), [str(v), f"{v} points"], False,
                f"Add them: {sum(data)}. Share among 5 games: {sum(data)} ÷ 5 = {v}", "g6mean"))
    return qs


def test_r():
    """Batch sheet 2: percent, multiplication, fraction sense, scaling, a fraction
    of a mixed number, expressions, unit rate, and three never-asked standards."""
    qs = []
    v = D(80) * D("0.75") * D("1.1")
    qs.append(Q("A jacket costs $80. It is 25% off, and then 10% tax is added to the sale "
                "price. What is the final cost?", usd(v), [usd(v), f"${dec(v)}"], True,
                "25% of $80 is $20, so $60. Then 10% of $60 is $6: $60 + $6 = $66.00", "pct", "$"))
    v = 658 * 347
    qs.append(Q("Work out 658 × 347", str(v), [str(v)], False,
                "658 × 300, 658 × 40, 658 × 7, then add column by column with carries", "g5mul33"))
    s = F(2, 5) + F(1, 2)
    v = "yes" if abs(s - F(3, 7)) < F(1, 10) else "no"
    qs.append(Q("Sam says 2/5 + 1/2 = 3/7. Without working it out exactly, could Sam be "
                "right? Write yes or no.", v, [v, v.capitalize()], False,
                "1/2 plus nearly another 1/2 is nearly 1, but 3/7 is less than 1/2. So no",
                "g5fbench"))
    v = "less than" if F(3, 5) < 1 else "greater than"
    qs.append(Q("Without working it out: is 3/5 × 48 greater than or less than 48?", v,
                [v, v.split()[0], f"{v} 48", "<" if v == "less than" else ">"], False,
                "3/5 is less than 1, so it makes 48 smaller", "g5scale"))
    v = F(8, 3) * F(3, 4)                           # retest: I6 read "3/4 of" as ÷ 4
    qs.append(Q("A recipe needs 2 2/3 cups of flour. Mia makes 3/4 of the recipe. How much "
                "flour does she need?", f"{mixed(v)} cups", [f"{mixed(v)} cups", f"{mixed(v)} cup"],
                True, "3/4 × 8/3 = 24/12 = 2 cups", "g5fmulword", "cups"))
    expr = ["(n – 8) ÷ 2", "(n-8)÷2", "(n – 8)/2", "(n-8)/2"]
    for e in expr:
        _expr_ok([e.replace("÷", "/")], (11 - 8) / 2, n=11)
    qs.append(Q("Write an expression for: the difference of n and 8, divided by 2.", expr[0],
                expr, False, "The difference of n and 8 is n – 8; keep it in parentheses, then ÷ 2",
                "g6expr_write"))
    v = 150 // 6
    assert v * 6 == 150
    qs.append(Q("A car goes 150 miles on 6 gallons of gas. How many miles does it go on 1 "
                "gallon?", str(v), [str(v), f"{v} miles"], False, "150 ÷ 6 = 25 miles per gallon",
                "g6unitrate"))
    from math import gcd
    v = gcd(36, 48)
    qs.append(Q("What is the greatest common factor of 36 and 48?", str(v), [str(v)], False,
                "Factors of 36: 1, 2, 3, 4, 6, 9, 12, 18, 36. 48 ÷ 12 = 4, so 12 is the greatest "
                "shared one", "g6gcf"))
    qs.append(Q("A diver is 15 m below sea level. Write her position as a number.", "–15",
                ["–15", "-15", "–15 m", "-15 m"], False,
                "Sea level is 0; below it is negative: –15", "g6signed"))
    same_value = all(2 * (x + 3) == 2 * x + 3 for x in (0, 1, 5))
    v = "yes" if same_value else "no"
    qs.append(Q("Are 2(x + 3) and 2x + 3 equivalent? Write yes or no.", v, [v, v.capitalize()],
                False, "2(x + 3) = 2x + 6, not 2x + 3. Check x = 1: 8 and 5. So no", "g6equiv"))
    return qs


def test_s():
    """Batch sheet 3: proportion, equations, signed products, powers of 10,
    patterns, spread, and three never-asked standards plus one review."""
    qs = []
    v = F(30, 4) * 10
    qs.append(Q("y is proportional to x. When x is 4, y is 30. What is y when x is 10?",
                str(v), [str(v)], False, "y is 30 ÷ 4 = 7.5 times x, so 7.5 × 10 = 75", "g7prop_rep"))
    v = (135 - 30) // 15                            # retest: K7 took off the wrong fee
    assert 30 + 15 * v == 135
    qs.append(Q("A phone plan costs $30 to join and then $15 each month. Kim has paid $135 in "
                "all. How many months has she had it?", str(v), [str(v), f"{v} months"], False,
                "30 + 15m = 135, so 15m = 105 and m = 7", "eqn"))
    v = F(-5, 8) * 4 * -6
    qs.append(Q("Work out (–5/8) × 4 × (–6)", frac(v), [frac(v)], False,
                "Two negatives make a positive. 5/8 × 4 = 5/2, × 6 = 15", "g7ratmul"))
    v = D("0.065") * 10 ** 3                        # retest: L9 moved the point two places for 10³
    qs.append(Q("Work out 0.065 × 10³", dec(v), [dec(v)], False,
                "10³ = 1000: move the point three places right", "g5pow10_mul"))
    a = [2 + 4 * k for k in range(5)]; b = [1 + 2 * k for k in range(5)]
    pair = f"({a[4]}, {b[4]})"
    qs.append(Q("Pattern A starts at 2 and adds 4. Pattern B starts at 1 and adds 2. "
                "Write the 5th pair (A, B).", pair,
                [pair, pair.replace(" ", ""), pair.strip("()"), pair.strip("()").replace(" ", "")], False,
                f"A: {', '.join(map(str, a))}. B: {', '.join(map(str, b))}. 5th terms: {pair}",
                "g5patterns"))
    plot = {"kind": "lineplot", "denominator": 1, "max": 10, "caption": "minutes to walk to school",
            "values": {"2": 1, "4": 3, "5": 4, "6": 2, "9": 1}}
    vals = [int(k) for k in plot["values"]]
    v = max(vals) - min(vals)
    qs.append(Q("What is the range of the data?", str(v), [str(v), f"{v} minutes"], False,
                "Longest 9, shortest 2: 9 – 2 = 7. The range is one number", "g6spread", figure=plot))
    qs.append(Q("Which one is a measure of center? A: range B: median C: greatest value. "
                "Write the letter.", "B", ["B"], False,
                "The median is the middle value: one number for the whole set", "g6center"))
    v = 12 // 3 * 5
    qs.append(Q("Rice to water is 3 : 5, which is the same as 6 : 10. How many cups of water "
                "go with 12 cups of rice?",
                f"{v} cups", [f"{v} cups", str(v)], False,
                "12 is 4 times 3, so the water is 4 × 5 = 20 cups", "g6ratiotable"))
    pa, pb = D("3.00") / 4, D("4.20") / 6
    v = "A" if pa < pb else "B"
    qs.append(Q("Which is the better buy? A: 4 pens for $3.00. B: 6 pens for $4.20. "
                "Write the letter.", v, [v], False,
                f"One pen: A {usd(pa)}, B {usd(pb)}. B is cheaper per pen", "g6unitprice"))
    expr = ["(20 – 4) ÷ 2", "(20-4)÷2", "(20 – 4)/2", "(20-4)/2"]
    qs.append(Q("Write an expression for: subtract 4 from 20, then divide by 2. Do not work "
                "it out.", expr[0], expr, False, "The subtraction happens first, so it goes in "
                "parentheses: (20 – 4) ÷ 2", "g5expr"))
    return qs


# Tests T, U and V are one batch from `skills.py --plan --sheets 3` after Q, R and
# S were marked. 5.MD.C.5 now has its unit right (Q1) but lost a factor, so it is
# aimed at multiplying all three edges; 7.NS.A.2.c multiplied correctly on S3, so
# it is aimed at the untested division component.
def test_t():
    """Batch sheet 1: volume, ratio, equations, signed division, scaling, three
    never-asked grade-6 standards and two reviews."""
    qs = []
    v = 60 * 40 * 35                                # retest: Q1 used 700 for 40 × 30
    qs.append(Q("A storage chest is 60 cm long, 40 cm wide and 35 cm tall. What is its volume?",
                f"{v} cm³", [f"{v} cm³", f"{v} cm3", f"{v} cubic cm"], True,
                "60 × 40 = 2400 for the base; 2400 × 35 = 84000 cubic centimeters", "g5vol", "cm³"))
    v = 15 // 3 * 4
    qs.append(Q("A paint mix uses 3 cans of blue for every 4 cans of white. How many cans of "
                "white go with 15 cans of blue?", str(v), [str(v), f"{v} cans"], False,
                "15 is 5 times 3, so the white is 5 × 4 = 20 cans", "g6ratio"))
    v = (50 - 14) // 4
    assert 14 + 4 * v == 50
    qs.append(Q("Tom has $50. He buys a book for $14 and some pens at $4 each, and spends all "
                "his money. How many pens does he buy?", str(v), [str(v), f"{v} pens"], False,
                "14 + 4p = 50, so 4p = 36 and p = 9", "eqn"))
    v = F(-12) / F(-3, 4)
    qs.append(Q("Work out (–12) ÷ (–3/4)", frac(v), [frac(v)], False,
                "Dividing by 3/4 is multiplying by 4/3: 12 × 4/3 = 16. Two negatives: positive",
                "g7ratdiv"))
    v = "greater than" if F(5, 4) > 1 else "less than"
    qs.append(Q("Without working it out: is 5/4 × 36 greater than or less than 36?", v,
                [v, v.split()[0], f"{v} 36", ">" if v == "greater than" else "<"], False,
                "5/4 is more than 1, so it makes 36 bigger", "g5scale"))
    v = -(-9)
    qs.append(Q("What is –(–9)?", str(v), [str(v)], False,
                "The opposite of –9 is 9", "g6opp"))
    v = max(-3, -8)
    qs.append(Q("–3 > –8. Which of these two numbers is further to the right on a number line?",
                f"–{-v}", [f"–{-v}", f"-{-v}"], False,
                "Greater means further right: –3 is to the right of –8", "g6ineqpos"))
    eq = ["c = 40h", "c=40h", "c = 40 × h", "c=40×h", "c = h × 40"]
    _expr_ok([e.split("=")[1] for e in eq], 40 * 3, h=3)
    qs.append(Q("A plumber charges $40 for each hour. Write an equation for the cost c of a job "
                "that takes h hours.", eq[0], eq, False,
                "The cost depends on the hours: c = 40h", "g6depvar"))
    v = D(20) - 3 * D("2.45")
    qs.append(Q("Lena has $20. She buys 3 notebooks at $2.45 each. How much change does she get?",
                usd(v), [usd(v), f"${dec(v)}"], True,
                "3 × $2.45 = $7.35; $20 – $7.35 = $12.65", "money", "$"))
    v = max(D("0.407"), D("0.47"))
    qs.append(Q("Which is greater: 0.407 or 0.47?", dec(v), [dec(v)], False,
                "0.47 is 0.470, and 470 thousandths beats 407 thousandths", "g5cmp"))
    return qs


def test_u():
    """Batch sheet 2: percent, multiplication, coordinates, signed sums, powers of
    10, three never-asked grade-6 standards and two reviews."""
    qs = []
    v = D(120) * D("1.15") * D("0.8")
    qs.append(Q("A bike costs $120. Its price goes up by 15%, and then the new price is cut "
                "by 20%. What is the final price?", usd(v), [usd(v), f"${dec(v)}"], True,
                "Up 15%: $120 + $18 = $138. Then 20% of $138 is $27.60: $138 – $27.60 = $110.40",
                "pct", "$"))
    v = 3064 * 58
    qs.append(Q("Work out 3064 × 58", str(v), [str(v)], False,
                "3064 × 50 and 3064 × 8, then add column by column with carries", "g5mul24"))
    pair = "(4, 1)"
    qs.append(Q("Point P is 4 units from the y-axis and 1 unit from the x-axis, with both "
                "coordinates positive. Write its coordinates.", pair,
                [pair, "(4,1)", "4, 1", "4,1"], False,
                "Distance from the y-axis is across (x = 4); from the x-axis is up (y = 1)",
                "g5coord_dist"))
    v = F(7, 3) + F(-14, 3) + F(1, 3)              # retest: Q5 added a positive to a negative
    assert v == -2
    qs.append(Q("Work out 2 1/3 + (–4 2/3) + 1/3", f"–{frac(-v)}", [f"–{frac(-v)}", f"-{frac(-v)}"],
                False, "Positives together: 2 1/3 + 1/3 = 2 2/3. Then 2 2/3 + (–4 2/3) = –2", "g7rat"))
    v = D("36.5") / 10 ** 2
    qs.append(Q("Work out 36.5 ÷ 10²", dec(v), [dec(v)], False,
                "10² = 100: move the point two places left", "g5pow10"))
    v = next(x for x in (4, 5, 6) if 3 * x + 4 == 19)
    qs.append(Q("Which value of x makes 3x + 4 = 19 true: 4, 5 or 6?", str(v), [str(v)], False,
                "Try each: 3 × 5 + 4 = 19", "g6subst"))
    ineq = ["h > 48", "h>48", "48 < h", "48<h"]
    qs.append(Q("To go on a ride you must be taller than 48 inches. Write an inequality for a "
                "rider's height h.", ineq[0], ineq, False,
                "Taller than 48 means more than 48, not equal to it: h > 48", "g6ineqwrite"))
    v = abs(-12)
    qs.append(Q("What is the absolute value of –12?", str(v), [str(v)], False,
                "Absolute value is the distance from 0: 12", "g6abs"))
    v = F(3, 4) * F(2, 9)
    qs.append(Q("Work out 3/4 × 2/9", frac(v), [frac(v)], False,
                "3 × 2 = 6 over 4 × 9 = 36: 6/36 = 1/6", "g5fmul"))
    qs.append(Q("A model is made of 9 unit cubes. Each cube is 1 cm³. What is the model's "
                "volume?", "9 cm³", ["9 cm³", "9 cm3", "9 cubic cm"], True,
                "9 cubes of 1 cubic centimeter each: 9 cm³", "g5volunit", "cm³"))
    return qs


def test_v():
    """Batch sheet 3: proportion, a line plot, fractions, unit rate, three
    never-asked grade-6 standards and two reviews."""
    qs = []
    v = F(21, 6) * 10                               # retest: S1 added instead of scaling
    qs.append(Q("y is proportional to x. When x is 6, y is 21. What is y when x is 10?",
                str(v), [str(v)], False, "y is 21 ÷ 6 = 3.5 times x, so 3.5 × 10 = 35", "g7prop_rep"))
    plot = {"kind": "lineplot", "denominator": 4, "max": 1, "caption": "juice in each glass (cups)",
            "values": {"1/4": 2, "1/2": 2, "3/4": 2, "1": 2}}
    vals = {F(k): n for k, n in plot["values"].items()}
    total, n = sum(k * c for k, c in vals.items()), sum(vals.values())
    v = total / n
    qs.append(Q("The juice is shared out equally. How much does each glass get?", f"{mixed(v)} cup", [f"{mixed(v)} cup", f"{mixed(v)} cups"], True,
                f"Total: 2/4 + 2/4 + 6/4 + 2 = 5 cups. 8 glasses: 5 ÷ 8 = 5/8 cup",
                "g5lineplot", "cups", figure=plot))
    v = F(3, 4) + F(2, 3)
    qs.append(Q("Kai ran 3/4 mile on Monday and 2/3 mile on Tuesday. How far did he run in all?",
                f"{mixed(v)} miles", [f"{mixed(v)} miles", f"{frac(v)} miles", f"{mixed(v)} mi"], True,
                "Twelfths: 9/12 + 8/12 = 17/12 = 1 5/12 miles", "g5fword_add", "miles"))
    v = D(3) / 12
    qs.append(Q("12 apples cost $3. What is the price of one apple?", usd(v),
                [usd(v), f"${dec(v)}", "25¢"], True, "$3 ÷ 12 = $0.25", "g6unitrate", "$"))
    v = F(2, 3) * F(9, 2)
    qs.append(Q("A garden is 4 1/2 m long. Its width is 2/3 of its length. How wide is it?",
                f"{mixed(v)} m", [f"{mixed(v)} m"], True,
                "2/3 × 9/2 = 18/6 = 3 m", "g5fmulword", "m"))
    v = F(90, 12)
    qs.append(Q("There are 12 inches in 1 foot. How many feet is 90 inches?", f"{mixed(v)} feet",
                [f"{mixed(v)} feet", f"{dec(D(v.numerator) / v.denominator)} feet", f"{mixed(v)} ft",
                 f"{frac(v)} feet", mixed(v), dec(D(v.numerator) / v.denominator)], False,
                "90 ÷ 12 = 7 r 6, and 6 inches is half a foot: 7 1/2 feet", "g6convert"))
    temps = {"Oslo": -4, "Moscow": -9}
    v = min(temps, key=temps.get)
    qs.append(Q("It is –4 °C in Oslo and –9 °C in Moscow. Which city is colder?", v, [v], False,
                "–9 is less than –4, so Moscow is colder", "g6order"))
    v = min(-40, -25)
    assert abs(v) > 25
    qs.append(Q("One account has a balance of –$40 and another has –$25. Which balance shows "
                "the bigger debt?", f"–${-v}", [f"–${-v}", f"-${-v}", f"–{-v}", f"-{-v}"], False,
                "The debt is the size of the balance: |–40| = 40 is more than 25", "g6absorder"))
    v = 2592 // 36
    assert v * 36 == 2592
    qs.append(Q("Work out 2592 ÷ 36", str(v), [str(v)], False,
                "36 × 70 = 2520; 2592 – 2520 = 72 = 36 × 2; so 72", "g5divw"))
    qs.append(Q("Every rectangle has opposite sides of equal length. Must every square have "
                "opposite sides of equal length? Write yes or no.", "yes", ["yes", "Yes"], False,
                "A square is a special rectangle, so it has everything a rectangle has",
                "g5shapeattr"))
    return qs


# Tests W, X and Y are one batch from `skills.py --plan --sheets 3` after T, U and
# V were marked. Most 5.MD.C.5, 5.NF.B.6, 7.NS.A.3 and 7.RP.A.3 failures were
# units-only, so those keep the unit in a fresh context; 5.G.A.1, 5.NF.B.5,
# 6.RP.A.1 and 6.EE.A.2.a target the observed confusions (which axis, scaling,
# order of a ratio, direction of "difference of").
def test_w():
    """Batch sheet 1: volume, ratio, coordinates, signed products, patterns,
    distribution, fraction division and powers."""
    qs = []
    v = 6 * 5 * 4
    qs.append(Q("A storage room is 6 m long, 5 m wide and 4 m tall. What is its volume?",
                f"{v} m³", [f"{v} m³", f"{v} m3", f"{v} cubic m", f"{v} cubic meters"], True,
                "6 × 5 = 30 for the floor; 30 × 4 = 120 cubic meters", "g5vol", "m³"))
    v = F(36, 4) * 11
    assert v.denominator == 1
    qs.append(Q("A machine fills 36 bottles in 4 minutes. At the same rate, how many bottles does "
                "it fill in 11 minutes?", str(v), [str(v), f"{v} bottles"], False,
                "36 ÷ 4 = 9 bottles in 1 minute; 9 × 11 = 99", "g6ratio"))
    qs.append(Q("A point is at (9, 4). How far is it from the y-axis?", "9", ["9", "9 units"],
                False, "The first number is the distance across from the y-axis", "g5coord_x"))
    v = F(-3, 4) * 8 * F(-5, 6)
    assert v == 5
    qs.append(Q("Work out (–3/4) × 8 × (–5/6)", frac(v), [frac(v)], False,
                "Two negatives make a positive. 3/4 × 8 = 6, then 6 × 5/6 = 5", "g7ratmul"))
    v = F(10, 3) * F(3, 5)
    qs.append(Q("A bag of rice weighs 3 1/3 kg. Sam uses 3/5 of it. How much rice does he use?",
                f"{mixed(v)} kg", [f"{mixed(v)} kg"], True,
                "10/3 × 3/5 = 30/15 = 2 kg", "g5fmulword", "kg"))
    a = [2 * k for k in range(5)]; b = [5 * k for k in range(5)]
    pair = f"({a[4]}, {b[4]})"
    qs.append(Q("Pattern A starts at 0 and adds 2. Pattern B starts at 0 and adds 5. "
                "The first pair is (0, 0). Write the 5th pair (A, B).", pair,
                [pair, pair.replace(" ", ""), pair.strip("()"), pair.strip("()").replace(" ", "")], False,
                f"A: {', '.join(map(str, a))}. B: {', '.join(map(str, b))}. 5th terms: {pair}",
                "g5patterns"))
    apples, pears = 8, 14
    qs.append(Q(f"A fruit bowl has {apples} apples and {pears} pears. Write the ratio of pears "
                "to apples.", f"{pears}:{apples}",
                [f"{pears}:{apples}", f"{pears} : {apples}", f"{pears} to {apples}",
                 "7:4", "7 : 4", "7 to 4"], False,
                "Pears are named first, so pears come first: 14:8, which simplifies to 7:4",
                "g6ratio_write"))
    forms = ["12b + 42", "12b+42", "42 + 12b", "42+12b"]
    _expr_ok(forms, 6 * (2 * 5 + 7), b=5)
    qs.append(Q("Write 6(2b + 7) without parentheses.", forms[0], forms, False,
                "Multiply both terms by 6: 6 × 2b = 12b and 6 × 7 = 42", "g6distrib"))
    v = F(5, 6) / F(1, 3)
    qs.append(Q("A jug holds 5/6 liter of juice. Each glass takes 1/3 liter. How many glasses "
                "can be filled?", f"{mixed(v)} glasses",
                [f"{mixed(v)} glasses", mixed(v), f"{frac(v)} glasses", frac(v), "2.5", "2.5 glasses"], False,
                "5/6 ÷ 1/3 = 5/6 × 3 = 15/6 = 2 1/2", "g6fdivword"))
    v = 6 ** 2 - 2 ** 3
    qs.append(Q("Work out 6² – 2³", str(v), [str(v)], False,
                "6² = 36 and 2³ = 8: 36 – 8 = 28", "g6exp"))
    return qs


def test_x():
    """Batch sheet 2: percent, multiplication with a zero, scaling, signed sums,
    an expression, a shape hierarchy, centre, a negative quantity, a prism and a mean."""
    qs = []
    v = D(60) * D("1.25") * D("0.6")
    qs.append(Q("A shirt costs $60. Its price goes up by 25%, and then the new price is cut by "
                "40%. What is the final price?", usd(v), [usd(v), f"${dec(v)}"], True,
                "Up 25%: $60 + $15 = $75. Then 40% of $75 is $30: $75 – $30 = $45.00",
                "pct", "$"))
    v = 758 * 304
    qs.append(Q("Work out 758 × 304", str(v), [str(v)], False,
                "758 × 300 = 227400 and 758 × 4 = 3032; the tens row is all zeros. 227400 + 3032",
                "g5mul33"))
    v = "greater than" if F(7, 8) > 1 else "less than"
    qs.append(Q("Without working it out: is 7/8 × 120 greater than or less than 120?", v,
                [v, v.split()[0], f"{v} 120", ">" if v == "greater than" else "<"], False,
                "7/8 is less than 1, so it makes 120 smaller", "g5scale"))
    v = F(7, 10) + F(-19, 5) + F(3, 10)
    assert v == F(-14, 5)
    qs.append(Q("Work out 7/10 + (–3 4/5) + 3/10", f"–{mixed(-v)}", [f"–{mixed(-v)}", f"-{mixed(-v)}"],
                False, "Positives first: 7/10 + 3/10 = 1. Then 1 + (–3 4/5) = –2 4/5", "g7rat"))
    expr = ["4(15 – p)", "4(15-p)", "4 × (15 – p)", "4×(15-p)", "(15 – p) × 4", "(15-p)×4"]
    _expr_ok(expr, 4 * (15 - 6), p=6)
    qs.append(Q("Write an expression for: the difference of 15 and p, multiplied by 4.", expr[0], expr,
                False, "The difference of 15 and p is 15 – p, kept in parentheses, then × 4",
                "g6expr_write"))
    sq = [(0, 0), (0.6, 0), (0.6, 0.6), (0, 0.6)]
    shapes = [("A", sq),                                                 # square
              ("B", [(0, 0), (0.8, 0), (1, 0.6), (0.2, 0.6)]),           # slanted parallelogram
              ("C", [(0, 0), (1, 0), (1, 0.5), (0, 0.5)]),               # rectangle
              ("D", [(0, 0), (1, 0), (0.7, 0.6), (0.3, 0.6)])]           # trapezoid

    def is_rectangle(pts):
        s = [_vec(pts[i], pts[(i + 1) % 4]) for i in range(4)]
        return is_parallelogram(pts) and abs(s[0][0] * s[1][0] + s[0][1] * s[1][1]) < 1e-9
    v = ", ".join(L for L, pts in shapes if is_rectangle(pts))
    assert v == "A, C"
    qs.append(Q("Which of these shapes are rectangles? Write the letters.", v, [v], False,
                "A rectangle has four right angles: the wide rectangle does, and so does the "
                "square, because a square is a special rectangle", "g5shapeclass",
                figure={"kind": "shapes", "shapes": [{"label": L, "pts": pts} for L, pts in shapes]}))
    qs.append(Q("Which one is a measure of center? A: range B: minimum C: mean. Write the letter.",
                "C", ["C"], False, "The mean is one number for the middle of the data; the range "
                "measures spread and the minimum is just one end", "g6center"))
    qs.append(Q("At night the temperature is 7 degrees below zero. Write the temperature as a "
                "number.", "–7", ["–7", "-7"], False,
                "Below zero is negative: –7", "g6signed"))
    v = F(7, 2) * 2 * 4
    qs.append(Q("A box is 3 1/2 cm long, 2 cm wide and 4 cm tall. What is its volume?",
                f"{v} cm³", [f"{v} cm³", f"{v} cm3", f"{v} cubic cm"], True,
                "3 1/2 × 2 = 7 for the base; 7 × 4 = 28 cubic centimeters", "g6volfrac", "cm³"))
    data = [14, 9, 11, 16, 10]
    v = F(sum(data), len(data))
    assert v.denominator == 1
    qs.append(Q("Five friends scored 14, 9, 11, 16 and 10 points. What is the mean score?",
                str(v), [str(v), f"{v} points"], False,
                "14 + 9 + 11 + 16 + 10 = 60; 60 ÷ 5 = 12", "g6mean"))
    return qs


def test_y():
    """Batch sheet 3: proportion, a line plot, fraction subtraction, a unit rate,
    signed money, a statistical question, an exponent, four quadrants, a
    coefficient and a range."""
    qs = []
    v = F(20, 8) * 6
    assert v.denominator == 1
    qs.append(Q("y is proportional to x. When x is 8, y is 20. What is y when x is 6?",
                str(v), [str(v)], False, "y is 20 ÷ 8 = 2.5 times x, so 2.5 × 6 = 15", "g7prop_rep"))
    plot = {"kind": "lineplot", "denominator": 4, "max": 1, "caption": "length of each plank (m)",
            "values": {"1/4": 1, "1/2": 2, "3/4": 3, "1": 1}}
    vals = {F(k): n for k, n in plot["values"].items()}
    v = sum(k * n for k, n in vals.items())
    qs.append(Q("The planks are laid end to end. What is the total length?",
                f"{mixed(v)} m", [f"{mixed(v)} m", f"{frac(v)} m", f"{dec(D(v.numerator) / v.denominator)} m"], True,
                "1/4 + 2 × 1/2 + 3 × 3/4 + 1 = 1/4 + 1 + 2 1/4 + 1 = 4 1/2 m",
                "g5lineplot", "m", figure=plot))
    v = F(10, 3) - F(7, 4)
    qs.append(Q("A rope 3 1/3 m long has 1 3/4 m cut off. How much rope is left?",
                f"{mixed(v)} m", [f"{mixed(v)} m", f"{frac(v)} m"], True,
                "Twelfths: 3 4/12 – 1 9/12 = 2 16/12 – 1 9/12 = 1 7/12 m", "g5fword_sub", "m"))
    v = D(6) / 8
    qs.append(Q("8 notebooks cost $6. How much does one notebook cost?", usd(v),
                [usd(v), f"${dec(v)}", "75¢"], True, "$6 ÷ 8 = $0.75 (not 8 ÷ 6)", "g6unitrate", "$"))
    v = -18 + 50 - 47
    assert v == -15
    qs.append(Q("An account has a balance of –$18. Mia deposits $50 and then withdraws $47. "
                "What is the balance now?", f"–${-v}", [f"–${-v}", f"-${-v}", f"–{-v}", f"-{-v}"],
                False, "–18 + 50 = 32; 32 – 47 = –15, a debt of $15", "g7addrw"))
    qs.append(Q("Which is a statistical question? A: How old is Jo's cat? B: How many goals did "
                "Sam score today? C: How many goals do the players on the team score each game? "
                "Write the letter.", "C", ["C"], False,
                "Only C expects different answers from different players and games", "g6statq"))
    v = 2 * 3 ** 2 + 5
    qs.append(Q("Work out 2n² + 5 when n = 3", str(v), [str(v)], False,
                "n² = 9 first; then 2 × 9 = 18; 18 + 5 = 23", "g6evalexp"))
    ax, ay = -3, 4
    bx, by = ax, ay - 6
    pair = f"({bx}, {by})".replace("-", "–")
    forms = [pair, f"({bx}, {by})", f"({bx},{by})", f"{bx}, {by}", f"{bx},{by}"]
    qs.append(Q("Point A is at (–3, 4). Point B is 6 units directly below A. Write the "
                "coordinates of B.", pair, forms, False,
                "Directly below: same x. Going down 6 from y = 4 passes 0 and reaches –2",
                "g6quad4"))
    qs.append(Q("What is the coefficient of m in the expression 8 + 5m?", "5", ["5"], False,
                "The coefficient is the number multiplying the letter: 5", "g6coef"))
    data = [12, 7, 19, 4, 15]
    v = max(data) - min(data)
    qs.append(Q("A set of data is 12, 7, 19, 4, 15. What is the range?", str(v), [str(v)], False,
                "Greatest 19, least 4: 19 – 4 = 15", "g6spread"))
    return qs


# Tests Z, AA and AB are one batch from `skills.py --plan --sheets 3` after W, X
# and Y were marked. The plan was all failures plus four reviews. Where past
# misses were units-only (5.MD.C.5, 5.NF.A.2, 5.MD.B.2, 7.NS.A.3) the unit stays
# required in a fresh context; where they were a confusion (which axis, adding
# instead of multiplying a fraction, not distributing, counting a pattern pair,
# the order of a ratio) the question is aimed at that confusion.
def test_z():
    """Batch sheet 1: volume, ratio, coordinates, a fraction of a mixed number,
    patterns, a statistical question, a mean, a unit conversion and a ratio table."""
    qs = []
    v = 7 * 4 * 5
    qs.append(Q("A crate is 7 in long, 4 in wide and 5 in tall. What is its volume?",
                f"{v} in³", [f"{v} in³", f"{v} in3", f"{v} cubic in", f"{v} cubic inches"], True,
                "7 × 4 = 28 for the base; 28 × 5 = 140 cubic inches", "g5vol", "in³"))
    v = F(56, 7) * 12
    assert v.denominator == 1
    qs.append(Q("A printer prints 56 pages in 7 minutes. At the same rate, how many pages does "
                "it print in 12 minutes?", str(v), [str(v), f"{v} pages"], False,
                "56 ÷ 7 = 8 pages in 1 minute; 8 × 12 = 96", "g6ratio"))
    qs.append(Q("A point is at (2, 9). How far is it from the x-axis?", "9", ["9", "9 units"],
                False, "The second number is the distance up from the x-axis", "g5coord_y"))
    v = F(15, 4) * F(4, 5)
    qs.append(Q("A path is 3 3/4 km long. Ravi has walked 4/5 of it. How far has he walked?",
                f"{mixed(v)} km", [f"{mixed(v)} km"], True,
                "15/4 × 4/5 = 60/20 = 3 km", "g5fmulword", "km"))
    a = [3 * k for k in range(6)]; b = [4 * k for k in range(6)]
    pair = f"({a[5]}, {b[5]})"
    qs.append(Q("Pattern A starts at 0 and adds 3. Pattern B starts at 0 and adds 4. "
                "The first pair is (0, 0). Write the 6th pair (A, B).", pair,
                [pair, pair.replace(" ", ""), pair.strip("()"), pair.strip("()").replace(" ", "")], False,
                f"A: {', '.join(map(str, a))}. B: {', '.join(map(str, b))}. 6th terms: {pair}; "
                "(0, 0) is the 1st pair", "g5patterns"))
    red, green = 5, 8
    qs.append(Q(f"A bag has {red} red marbles and {green} green marbles. Write the ratio of green "
                "to red.", f"{green}:{red}",
                [f"{green}:{red}", f"{green} : {red}", f"{green} to {red}"], False,
                "Green is named first, so green comes first: 8:5", "g6ratio_write"))
    qs.append(Q("Which is a statistical question? A: How many pets do Ana's classmates have? "
                "B: How many pets does Ana have? C: How many days are in a week? Write the letter.",
                "A", ["A"], False,
                "Only A expects different answers from different students", "g6statq"))
    data = [12, 15, 9, 16]
    v = F(sum(data), len(data))
    assert v.denominator == 1
    qs.append(Q("The temperatures on 4 days were 12, 15, 9 and 16 degrees. What is the mean "
                "temperature?", str(v), [str(v), f"{v} degrees"], False,
                "12 + 15 + 9 + 16 = 52; 52 ÷ 4 = 13", "g6mean"))
    v = F(150, 60)
    qs.append(Q("There are 60 minutes in 1 hour. How many hours is 150 minutes?", f"{mixed(v)} hours",
                [f"{mixed(v)} hours", f"{dec(D(v.numerator) / v.denominator)} hours", f"{mixed(v)} hr",
                 f"{frac(v)} hours", mixed(v), dec(D(v.numerator) / v.denominator)], False,
                "150 ÷ 60 = 2 r 30, and 30 minutes is half an hour: 2 1/2 hours", "g6convert"))
    v = F(12, 3) * 5
    assert v.denominator == 1
    qs.append(Q("Red paint and blue paint are mixed in the ratio 3 : 5. How many cans of blue go "
                "with 12 cans of red?", str(v), [str(v), f"{v} cans"], False,
                "12 is 4 times 3, so the blue is 4 × 5 = 20 cans", "g6ratiotable"))
    return qs


def test_aa():
    """Batch sheet 2: percent, multiplication, fractions, scaling, expressions,
    centre, a negative quantity, absolute value versus order and a GCF."""
    qs = []
    v = D(50) * D("1.2") * D("0.7")
    qs.append(Q("A game costs $50. Its price goes up by 20%, and then the new price is cut by "
                "30%. What is the final price?", usd(v), [usd(v), f"${dec(v)}"], True,
                "Up 20%: $50 + $10 = $60. Then 30% of $60 is $18: $60 – $18 = $42.00",
                "pct", "$"))
    v = 2706 * 47
    qs.append(Q("Work out 2706 × 47", str(v), [str(v)], False,
                "2706 × 40 = 108240 and 2706 × 7 = 18942; the zero in the hundreds place needs "
                "care. 108240 + 18942", "g5mul24"))
    v = F(17, 6) + F(7, 4)
    qs.append(Q("Leo drank 2 5/6 cups of juice in the morning and 1 3/4 cups in the afternoon. "
                "How much did he drink in all?", f"{mixed(v)} cups", [f"{mixed(v)} cups", f"{frac(v)} cups"],
                True, "Twelfths: 2 10/12 + 1 9/12 = 3 19/12 = 4 7/12 cups", "g5fword_add", "cups"))
    v = "greater than" if F(11, 10) > 1 else "less than"
    qs.append(Q("Without working it out: is 1 1/10 × 50 greater than or less than 50?", v,
                [v, v.split()[0], f"{v} 50", ">" if v == "greater than" else "<"], False,
                "1 1/10 is more than 1, so it makes 50 bigger", "g5scale"))
    forms = ["2k – 5", "2k-5", "2 × k – 5", "2×k-5", "2k − 5"]
    _expr_ok(forms, 2 * 7 - 5, k=7)
    qs.append(Q("Write an expression for: 5 less than twice k.", forms[0], forms, False,
                "Twice k is 2k. 5 less than that is 2k – 5, not 5 – 2k", "g6expr_write"))
    forms = ["12m – 6", "12m-6", "–6 + 12m", "-6+12m"]
    _expr_ok(forms, 3 * (4 * 5 - 2), m=5)
    qs.append(Q("Write 3(4m – 2) without parentheses.", forms[0], forms, False,
                "Multiply both terms by 3: 3 × 4m = 12m and 3 × 2 = 6, so 12m – 6", "g6distrib"))
    qs.append(Q("Which is a measure of center? A: mean B: range C: largest value. Write the letter.",
                "A", ["A"], False, "The mean is one number for the middle of the data; the range "
                "measures spread and the largest value is just one end", "g6center"))
    qs.append(Q("Sam owes his friend $9. Write Sam's balance as a number.", "–$9",
                ["–$9", "-$9", "–9", "-9"], False,
                "Owing is a negative amount: –9", "g6signed"))
    qs.append(Q("Which statement is true? A: –15 > –6 B: |–15| > |–6|. Write the letter.",
                "B", ["B"], False,
                "–15 is less than –6 (it is further left), but 15 is more than 6, so the "
                "absolute value is greater", "g6absorder"))
    from math import gcd
    v = gcd(30, 45)
    qs.append(Q("What is the greatest common factor of 30 and 45?", str(v), [str(v)], False,
                "Factors of 30: 1, 2, 3, 5, 6, 10, 15, 30. 45 ÷ 15 = 3, so 15 is the greatest "
                "shared one", "g6gcf"))
    return qs


def test_ab():
    """Batch sheet 3: proportion, a line plot, signed sums, spread, a shape
    hierarchy, an exponent, an equation, unit prices and equivalence."""
    qs = []
    rows = [(1, 3), (2, 6), (4, 13)]
    v = "yes" if len({F(c, n) for n, c in rows}) == 1 else "no"
    qs.append(Q("1 book costs $3, 2 books cost $6 and 4 books cost $13. Is the cost proportional "
                "to the number of books? Write yes or no.", v, [v, v.capitalize()], False,
                "Cost of one book: $3, $3, then $3.25 - not the same, so no", "g7prop"))
    plot = {"kind": "lineplot", "denominator": 4, "max": 1, "caption": "weight of each parcel (kg)",
            "values": {"1/4": 2, "1/2": 2, "3/4": 1, "1": 3}}
    vals = {F(k): n for k, n in plot["values"].items()}
    v = sum(k * n for k, n in vals.items())
    qs.append(Q("All the parcels are put on one scale. What is the total weight?",
                f"{mixed(v)} kg", [f"{mixed(v)} kg", f"{frac(v)} kg"], True,
                "2 × 1/4 + 2 × 1/2 + 3/4 + 3 × 1 = 1/2 + 1 + 3/4 + 3 = 5 1/4 kg",
                "g5lineplot", "kg", figure=plot))
    v = F(3, 4) + F(-7, 2) + F(1, 4)
    assert v == F(-5, 2)
    qs.append(Q("Work out 3/4 + (–3 1/2) + 1/4", f"–{mixed(-v)}", [f"–{mixed(-v)}", f"-{mixed(-v)}"],
                False, "Positives first: 3/4 + 1/4 = 1. Then 1 + (–3 1/2) = –2 1/2", "g7rat"))
    v = 4 - 11
    qs.append(Q("At noon the temperature was 4 °C. By midnight it had dropped 11 °C. What was the "
                "temperature at midnight?", f"–{-v}", [f"–{-v}", f"-{-v}", f"–{-v} °C", f"-{-v} °C"],
                False, "4 – 11 = –7: dropping past 0 gives a negative", "g7addrw"))
    A_ = [10, 11, 12, 13, 14]; B_ = [2, 6, 12, 18, 22]
    v = "B" if max(B_) - min(B_) > max(A_) - min(A_) else "A"
    qs.append(Q("Data set A is 10, 11, 12, 13, 14. Data set B is 2, 6, 12, 18, 22. Which data set "
                "has the greater range? Write A or B.", v, [v], False,
                "Range of A: 14 – 10 = 4. Range of B: 22 – 2 = 20. B is more spread out", "g6spread"))
    shapes = [("A", [(0, 0), (1, 0), (1, 0.6), (0, 0.6)]),                 # rectangle
              ("B", [(0, 0), (0.8, 0), (1, 0.6), (0.2, 0.6)]),             # slanted parallelogram
              ("C", [(0, 0), (1, 0), (0.7, 0.6), (0.3, 0.6)]),             # trapezoid
              ("D", [(0.5, 0), (1, 0.35), (0.5, 0.7), (0, 0.35)])]         # rhombus
    v = ", ".join(L for L, pts in shapes if is_parallelogram(pts))
    assert v == "A, B, D"
    qs.append(Q("Which of these shapes are parallelograms? Write the letters.", v, [v], False,
                "Both pairs of opposite sides parallel: the rectangle, the slanted shape and the "
                "rhombus; the trapezoid has only one pair", "g5shapeclass",
                figure={"kind": "shapes", "shapes": [{"label": L, "pts": pts} for L, pts in shapes]}))
    v = 4 + 3 * 2 ** 2
    qs.append(Q("Work out 4 + 3m² when m = 2", str(v), [str(v)], False,
                "m² = 4 first; 3 × 4 = 12; 4 + 12 = 16", "g6evalexp"))
    eq = ["t = 15m", "t=15m", "t = 15 × m", "t=15×m", "t = m × 15"]
    _expr_ok([e.split("=")[1] for e in eq], 15 * 4, m=4)
    qs.append(Q("A gym charges $15 for each month. Write an equation for the total cost t after "
                "m months.", eq[0], eq, False,
                "The cost depends on the months: t = 15m", "g6depvar"))
    pa, pb = D(3) / 6, D(5) / 8
    v = "A" if pa < pb else "B"
    qs.append(Q("Brand A: 6 pencils cost $3. Brand B: 8 pencils cost $5. Which brand is cheaper "
                "per pencil? Write A or B.", v, [v], False,
                f"One pencil: A {usd(pa)}, B {usd(pb)}. A is cheaper per pencil", "g6unitprice"))
    same_value = all(3 * (x + 4) == 3 * x + 12 for x in (0, 1, 5))
    v = "yes" if same_value else "no"
    qs.append(Q("Are 3(x + 4) and 3x + 12 equivalent? Write yes or no.", v, [v, v.capitalize()],
                False, "3(x + 4) = 3x + 12. Check x = 1: 15 and 15. So yes", "g6equiv"))
    return qs


# Tests AF, AG and AH are one batch from `skills.py --plan --sheets 3` after AD
# and AE were marked: failures plus six reviews, and two never-asked prerequisites
# of 7.NS.A.3 (4.OA.A.3 and 7.NS.A.2.d). Fraction conversion slips (numerator
# times the wrong factor), the x-versus-y axis, "less than"/"younger than"
# direction and sign loss on negatives are aimed at directly; units-only
# failures keep the unit required in a fresh context.
def test_af():
    """Batch sheet 1: fraction subtraction, multiplication with a zero, axis
    distance, a remainder, spread, centre, GCF, absolute value, order, substitution."""
    qs = []
    v = F(5, 6) - F(1, 4)
    qs.append(Q("A board is 5/6 m long. A piece 1/4 m long is cut off. How much is left?",
                f"{mixed(v)} m", [f"{mixed(v)} m", f"{frac(v)} m"], True,
                "Twelfths: 5/6 = 10/12 and 1/4 = 3/12 (multiply top and bottom by 3). 10/12 – 3/12 = 7/12 m",
                "g5fword_sub", "m"))
    v = 607 * 245
    qs.append(Q("Work out 607 × 245", str(v), [str(v)], False,
                "607 × 200 = 121400, 607 × 40 = 24280, 607 × 5 = 3035; add them", "g5mul33"))
    qs.append(Q("A point is at (5, 11). How far is it from the x-axis?", "11", ["11", "11 units"],
                False, "The second number is the distance up from the x-axis", "g5coord_y"))
    import math
    v = math.ceil(150 / 40)
    qs.append(Q("A school needs buses for 150 students. Each bus holds 40 students. How many buses "
                "are needed?", str(v), [str(v), f"{v} buses"], False,
                "150 ÷ 40 = 3 remainder 30. The 30 left over still need a bus, so 4 buses",
                "g4multi"))
    data = [6, 14, 9, 21, 11]
    v = max(data) - min(data)
    qs.append(Q("A set of data is 6, 14, 9, 21, 11. What is the range?", str(v), [str(v)], False,
                "Greatest 21, least 6: 21 – 6 = 15", "g6spread"))
    qs.append(Q("Which one is NOT a measure of center? A: mean B: median C: range. Write the letter.",
                "C", ["C"], False, "The mean and median each give one number for the middle; "
                "the range measures spread", "g6center"))
    v = math.gcd(28, 42)
    qs.append(Q("What is the greatest common factor of 28 and 42?", str(v), [str(v)], False,
                "Factors of 28: 1, 2, 4, 7, 14, 28. 42 ÷ 14 = 3, so 14 is the greatest shared one",
                "g6gcf"))
    qs.append(Q("Which statement is true? A: –9 < –4 B: |–9| < |–4|. Write the letter.", "A", ["A"],
                False, "–9 is further left than –4, so –9 < –4; but 9 is more than 4, so |–9| is "
                "not less than |–4|", "g6absorder"))
    qs.append(Q("The temperatures in three places are –3 °C, 5 °C and –8 °C. Write them from "
                "coldest to warmest.", "–8, –3, 5",
                ["–8, –3, 5", "-8, -3, 5", "–8,–3,5", "-8,-3,5", "–8 –3 5", "-8 -3 5"], False,
                "Further left is colder: –8, then –3, then 5", "g6order"))
    v = next(x for x in (4, 5, 6) if 5 * x - 3 == 27)
    qs.append(Q("Which value of n makes 5n – 3 = 27 true: 4, 5 or 6?", str(v), [str(v)], False,
                "Try each: 5 × 6 – 3 = 27", "g6subst"))
    return qs


def test_ag():
    """Batch sheet 2: volume, a signed sum, expressions, a decimal conversion, a
    ratio, a unit price, a negative quantity, an inequality, position and a mean."""
    qs = []
    v = 50 * 30 * 20
    qs.append(Q("A fish tank is 50 cm long, 30 cm wide and 20 cm tall. What is its volume?",
                f"{v} cm³", [f"{v} cm³", f"{v} cm3", f"{v} cubic cm"], True,
                "50 × 30 = 1500 for the base; 1500 × 20 = 30000 cubic centimeters", "g5vol", "cm³"))
    v = F(5, 6) + F(-10, 3) + F(1, 6)
    assert v == F(-7, 3)
    qs.append(Q("Work out 5/6 + (–3 1/3) + 1/6", f"–{mixed(-v)}", [f"–{mixed(-v)}", f"-{mixed(-v)}"],
                False, "Positives first: 5/6 + 1/6 = 1. Then 1 + (–3 1/3) = –2 1/3", "g7rat"))
    forms = ["3w – 8", "3w-8", "3 × w – 8", "3×w-8", "3w − 8"]
    _expr_ok(forms, 3 * 5 - 8, w=5)
    qs.append(Q("Write an expression for: 8 less than 3 times w.", forms[0], forms, False,
                "3 times w is 3w. 8 less than that is 3w – 8, not 8 – 3w", "g6expr_write"))
    v = D(3) / 8
    qs.append(Q("Write 3/8 as a decimal.", dec(v), [dec(v)], False,
                "Divide 3 by 8: 8 into 3.000 gives 0.375", "g7fdec"))
    sop, alt = 9, 12
    qs.append(Q(f"A choir has {alt} altos and {sop} sopranos. Write the ratio of sopranos to altos.",
                f"{sop}:{alt}", [f"{sop}:{alt}", f"{sop} : {alt}", f"{sop} to {alt}",
                                 "3:4", "3 : 4", "3 to 4"], False,
                "Sopranos are named first, so sopranos come first: 9:12, which simplifies to 3:4",
                "g6ratio_write"))
    pa, pb = D(7) / 8, D(4) / 5
    v = "A" if pa < pb else "B"
    assert v == "B"
    qs.append(Q("Store A: 8 apples cost $7. Store B: 5 apples cost $4. Which store is cheaper per "
                "apple? Write A or B.", v, [v], False,
                f"One apple: A {usd(pa)}, B {usd(pb)}. B is cheaper, even though A's pack is bigger",
                "g6unitprice"))
    qs.append(Q("A submarine is 300 ft below sea level. Write its position as a number.", "–300",
                ["–300", "-300", "–300 ft", "-300 ft"], False,
                "Below sea level is negative: –300", "g6signed"))
    forms = ["a < 5", "a<5", "5 > a", "5>a"]
    qs.append(Q("A child rides the bus free if the child is younger than 5 years. Write an "
                "inequality for the child's age a.", forms[0], forms, False,
                "Younger than 5 means less than 5, not equal to it: a < 5", "g6ineqwrite"))
    v = min(-6, -1)
    qs.append(Q("–6 < –1. Which of these two numbers is further to the left on a number line?",
                f"–{-v}", [f"–{-v}", f"-{-v}"], False,
                "Less means further left: –6 is to the left of –1", "g6ineqpos"))
    data = [7, 10, 12, 9, 7]
    v = F(sum(data), len(data))
    assert v.denominator == 1
    qs.append(Q("The ages of five cousins are 7, 10, 12, 9 and 7. What is the mean age?",
                str(v), [str(v), f"{v} years"], False,
                "7 + 10 + 12 + 9 + 7 = 45; 45 ÷ 5 = 9", "g6mean"))
    return qs


def test_ah():
    """Batch sheet 3: percent, a line plot, a signed position, patterns, the
    distributive property, an exponent, an equation, distance from 0, opposites
    and a unit conversion."""
    qs = []
    v = D(200) * D("0.85") * D("1.1")
    qs.append(Q("A phone costs $200. It is 15% off, and then 10% tax is added to the sale price. "
                "What is the final cost?", usd(v), [usd(v), f"${dec(v)}"], True,
                "15% of $200 is $30, so $170. Then 10% of $170 is $17: $170 + $17 = $187.00",
                "pct", "$"))
    plot = {"kind": "lineplot", "denominator": 4, "max": 1, "caption": "distance each student walked (mi)",
            "values": {"1/4": 3, "1/2": 1, "3/4": 2, "1": 1}}
    vals = {F(k): n for k, n in plot["values"].items()}
    v = sum(k * n for k, n in vals.items())
    qs.append(Q("How far did the students walk in all?", f"{mixed(v)} miles",
                [f"{mixed(v)} miles", f"{frac(v)} miles", f"{mixed(v)} mi"], True,
                "3 × 1/4 + 1/2 + 2 × 3/4 + 1 = 3/4 + 1/2 + 1 1/2 + 1 = 3 3/4 miles",
                "g5lineplot", "miles", figure=plot))
    v = -15 + 40 - 30
    assert v == -5
    qs.append(Q("A hiker starts 15 m below sea level, climbs up 40 m, and then goes down 30 m. "
                "Where is the hiker now, compared with sea level?", f"–{-v} m",
                [f"–{-v} m", f"-{-v} m", f"–{-v}", f"-{-v}", f"{-v} m below", f"{-v} m below sea level"],
                False, "–15 + 40 = 25; 25 – 30 = –5, which is 5 m below sea level", "g7addrw"))
    a = [3 * k for k in range(5)]; b = [12 * k for k in range(5)]
    pair = f"({a[4]}, {b[4]})"
    qs.append(Q("Pattern A starts at 0 and adds 3. Pattern B starts at 0 and adds 12. "
                "The first pair is (0, 0). Write the 5th pair (A, B).", pair,
                [pair, pair.replace(" ", ""), pair.strip("()"), pair.strip("()").replace(" ", "")], False,
                f"A: {', '.join(map(str, a))}. B: {', '.join(map(str, b))}. 5th terms: {pair}; "
                "(0, 0) is the 1st pair", "g5patterns"))
    forms = ["15y + 20", "15y+20", "20 + 15y", "20+15y"]
    _expr_ok(forms, 5 * (3 * 4 + 4), y=4)
    qs.append(Q("Write 5(3y + 4) without parentheses.", forms[0], forms, False,
                "Multiply both terms by 5: 5 × 3y = 15y and 5 × 4 = 20", "g6distrib"))
    v = 3 * 2 ** 2 - 4
    qs.append(Q("Work out 3a² – 4 when a = 2", str(v), [str(v)], False,
                "a² = 4 first; 3 × 4 = 12; 12 – 4 = 8", "g6evalexp"))
    eq = ["d = 12t", "d=12t", "d = 12 × t", "d=12×t", "d = t × 12"]
    _expr_ok([e.split("=")[1] for e in eq], 12 * 3, t=3)
    qs.append(Q("A cyclist rides 12 miles each hour. Write an equation for the distance d after t "
                "hours.", eq[0], eq, False,
                "The distance depends on the hours: d = 12t", "g6depvar"))
    qs.append(Q("How far is –9 from 0 on a number line?", "9", ["9", "9 units"], False,
                "Distance is never negative: the absolute value of –9 is 9", "g6abs"))
    v = -7
    qs.append(Q("What is the opposite of the opposite of –7?", f"–{-v}", [f"–{-v}", f"-{-v}"], False,
                "The opposite of –7 is 7, and the opposite of 7 is –7", "g6opp"))
    v = F(14, 3)
    qs.append(Q("There are 3 feet in 1 yard. How many yards is 14 feet?", f"{mixed(v)} yards",
                [f"{mixed(v)} yards", f"{mixed(v)} yd", f"{frac(v)} yards", mixed(v), frac(v)], False,
                "14 ÷ 3 = 4 r 2, and 2 feet is 2/3 of a yard: 4 2/3 yards", "g6convert"))
    return qs


# Tests AI, AJ and AK are one batch from `skills.py --plan --sheets 3` after AG
# was marked (2/10). All failures plus six reviews. The repeated confusions are
# aimed at directly: the sign lost on a negative sum, "less than" reversed in an
# expression, the greater of two packs taken as the cheaper, which axis a
# distance is measured from, and an inequality written in words. Units-only
# failures keep the unit required in a fresh context.
def test_ai():
    """Batch sheet 1: fraction subtraction, a signed sum, an expression, a
    decimal conversion, a ratio, a GCF, an inequality, position, division, cubes."""
    qs = []
    v = F(7, 8) - F(1, 3)
    qs.append(Q("A bag holds 7/8 kg of rice. Sam uses 1/3 kg. How much rice is left?",
                f"{mixed(v)} kg", [f"{mixed(v)} kg"], True,
                "Twenty-fourths: 7/8 = 21/24 (×3) and 1/3 = 8/24 (×8). 21/24 – 8/24 = 13/24 kg",
                "g5fword_sub", "kg"))
    v = F(2, 3) + F(-9, 2) + F(1, 3)
    assert v == F(-7, 2)
    qs.append(Q("Work out 2/3 + (–4 1/2) + 1/3", f"–{mixed(-v)}", [f"–{mixed(-v)}", f"-{mixed(-v)}"],
                False, "Positives first: 2/3 + 1/3 = 1. Then 1 + (–4 1/2) = –3 1/2", "g7rat"))
    forms = ["4n – 6", "4n-6", "4 × n – 6", "4×n-6", "4n − 6"]
    _expr_ok(forms, 4 * 5 - 6, n=5)
    qs.append(Q("Write an expression for: 6 less than 4 times n.", forms[0], forms, False,
                "4 times n is 4n. 6 less than that is 4n – 6, not 6 – 4n", "g6expr_write"))
    v = D(5) / 8
    qs.append(Q("Write 5/8 as a decimal.", dec(v), [dec(v)], False,
                "Divide 5 by 8: 8 into 5.000 gives 0.625", "g7fdec"))
    spoons, forks = 9, 15
    qs.append(Q(f"A drawer has {forks} forks and {spoons} spoons. Write the ratio of spoons to forks.",
                f"{spoons}:{forks}", [f"{spoons}:{forks}", f"{spoons} : {forks}", f"{spoons} to {forks}",
                                      "3:5", "3 : 5", "3 to 5"], False,
                "Spoons are named first, so spoons come first: 9:15, which simplifies to 3:5",
                "g6ratio_write"))
    import math
    v = math.gcd(36, 54)
    qs.append(Q("What is the greatest common factor of 36 and 54?", str(v), [str(v)], False,
                "Factors of 36: 1, 2, 3, 4, 6, 9, 12, 18, 36. 54 ÷ 18 = 3, so 18 is the greatest "
                "shared one (6 and 9 are shared but smaller)", "g6gcf"))
    forms = ["a > 12", "a>12", "12 < a", "12<a"]
    qs.append(Q("To enter a contest you must be older than 12 years. Write an inequality for a "
                "person's age a.", forms[0], forms, False,
                "Older than 12 means more than 12, not equal to it: a > 12", "g6ineqwrite"))
    v = min(-8, -3)
    qs.append(Q("–8 < –3. Which of these two numbers is further to the left on a number line?",
                f"–{-v}", [f"–{-v}", f"-{-v}"], False,
                "Less means further left: –8 is to the left of –3", "g6ineqpos"))
    v = 3276 // 36
    assert v * 36 == 3276
    qs.append(Q("Work out 3276 ÷ 36", str(v), [str(v)], False,
                "36 × 90 = 3240; 3276 – 3240 = 36 = 36 × 1; so 91", "g6div"))
    l, w, h = 5, 2, 3
    v = l * w * h
    qs.append(Q("This box is full of unit cubes. How many cubes?", str(v),
                [str(v), f"{v} cubes", f"{v} unit cubes", f"{v} cubic units"], False,
                f"{l} × {w} in each layer = {l * w}, × {h} layers = {v}", "g5cubes",
                figure={"kind": "cubes", "l": l, "w": w, "h": h}))
    return qs


def test_aj():
    """Batch sheet 2: volume, a line plot, a signed depth, patterns, unit price,
    a negative balance, a mean, a conversion, an equation and a grid."""
    qs = []
    v = 30 * 15 * 10
    qs.append(Q("A shoe box is 30 cm long, 15 cm wide and 10 cm tall. What is its volume?",
                f"{v} cm³", [f"{v} cm³", f"{v} cm3", f"{v} cubic cm"], True,
                "30 × 15 = 450 for the base; 450 × 10 = 4500 cubic centimeters", "g5vol", "cm³"))
    plot = {"kind": "lineplot", "denominator": 4, "max": 1, "caption": "length of each rope (m)",
            "values": {"1/4": 4, "1/2": 1, "3/4": 1, "1": 1}}
    vals = {F(k): n for k, n in plot["values"].items()}
    v = sum(k * n for k, n in vals.items())
    qs.append(Q("The ropes are tied end to end. How long is the rope in all?",
                f"{mixed(v)} m", [f"{mixed(v)} m", f"{frac(v)} m"], True,
                "4 × 1/4 + 1/2 + 3/4 + 1 = 1 + 1/2 + 3/4 + 1 = 3 1/4 m", "g5lineplot", "m", figure=plot))
    v = -18 + 7 - 12
    assert v == -23
    qs.append(Q("A diver is at –18 m. She swims up 7 m and then down 12 m. What is her position now?",
                f"–{-v} m", [f"–{-v} m", f"-{-v} m", f"–{-v}", f"-{-v}"], False,
                "–18 + 7 = –11; –11 – 12 = –23", "g7addrw"))
    a = [5 * k for k in range(4)]; b = [10 * k for k in range(4)]
    pair = f"({a[3]}, {b[3]})"
    qs.append(Q("Pattern A starts at 0 and adds 5. Pattern B starts at 0 and adds 10. "
                "The first pair is (0, 0). Write the 4th pair (A, B).", pair,
                [pair, pair.replace(" ", ""), pair.strip("()"), pair.strip("()").replace(" ", "")], False,
                f"A: {', '.join(map(str, a))}. B: {', '.join(map(str, b))}. 4th terms: {pair}; "
                "(0, 0) is the 1st pair", "g5patterns"))
    pa, pb = D(2) / 4, D(6) / 10
    v = "A" if pa < pb else "B"
    assert v == "A"
    qs.append(Q("Pack A: 4 pens cost $2. Pack B: 10 pens cost $6. Which pack is cheaper per pen? "
                "Write A or B.", v, [v], False,
                f"One pen: A {usd(pa)}, B {usd(pb)}. A is cheaper per pen, though B is the bigger pack",
                "g6unitprice"))
    qs.append(Q("A bank account is overdrawn by $35. Write the balance as a number.", "–$35",
                ["–$35", "-$35", "–35", "-35"], False,
                "Overdrawn means below zero: –35", "g6signed"))
    data = [8, 13, 9, 12, 8]
    v = F(sum(data), len(data))
    assert v.denominator == 1
    qs.append(Q("A baker sold 8, 13, 9, 12 and 8 cakes on five days. What is the mean number sold "
                "per day?", str(v), [str(v), f"{v} cakes"], False,
                "8 + 13 + 9 + 12 + 8 = 50; 50 ÷ 5 = 10", "g6mean"))
    v = F(450, 100)
    qs.append(Q("There are 100 centimeters in 1 meter. How many meters is 450 centimeters?",
                f"{mixed(v)} m", [f"{mixed(v)} m", f"{dec(D(v.numerator) / v.denominator)} m",
                                  f"{frac(v)} m", mixed(v), dec(D(v.numerator) / v.denominator)], False,
                "450 ÷ 100 = 4 r 50, and 50 cm is half a meter: 4 1/2 m", "g6convert"))
    v = F(6, 5) - F(2, 5)
    qs.append(Q("Solve x + 2/5 = 1 1/5", frac(v), [frac(v), f"x = {frac(v)}", f"x={frac(v)}"], False,
                "Take 2/5 from both sides: x = 1 1/5 – 2/5 = 6/5 – 2/5 = 4/5", "g6eqn"))
    grid = {"kind": "grid", "size": 6, "points": {"A": [2, 1], "B": [4, 5], "C": [6, 2]}}
    bx, by = grid["points"]["B"]
    qs.append(Q("On this map, x is blocks east and y is blocks north. "
                "Write the coordinates of B.", f"({bx}, {by})",
                [f"({bx}, {by})", f"({bx},{by})", f"{bx}, {by}", f"{bx},{by}"], False,
                "4 east, then 5 north", "g5gridread", figure=grid))
    return qs


def test_ak():
    """Batch sheet 3: multiplication with a zero, axis distance, a multi-step
    problem, range, distributive property, an equation, opposites, absolute
    value versus order, an expression and rounding."""
    qs = []
    v = 509 * 276
    qs.append(Q("Work out 509 × 276", str(v), [str(v)], False,
                "509 × 200 = 101800, 509 × 70 = 35630, 509 × 6 = 3054; add them", "g5mul33"))
    qs.append(Q("A point is at (12, 3). How far is it from the y-axis?", "12", ["12", "12 units"],
                False, "The first number is the distance across from the y-axis", "g5coord_x"))
    v = 8 * 24 - 50
    qs.append(Q("A shop has 8 boxes with 24 pencils in each box. It sells 50 pencils. How many "
                "pencils are left?", str(v), [str(v), f"{v} pencils"], False,
                "8 × 24 = 192 pencils; 192 – 50 = 142", "g4multi"))
    data = [17, 5, 12, 23, 9]
    v = max(data) - min(data)
    qs.append(Q("A set of data is 17, 5, 12, 23, 9. What is the range?", str(v), [str(v)], False,
                "Greatest 23, least 5: 23 – 5 = 18", "g6spread"))
    forms = ["14p + 8", "14p+8", "8 + 14p", "8+14p"]
    _expr_ok(forms, 2 * (7 * 3 + 4), p=3)
    qs.append(Q("Write 2(7p + 4) without parentheses.", forms[0], forms, False,
                "Multiply both terms by 2: 2 × 7p = 14p and 2 × 4 = 8", "g6distrib"))
    eq = ["p = 14h", "p=14h", "p = 14 × h", "p=14×h", "p = h × 14"]
    _expr_ok([e.split("=")[1] for e in eq], 14 * 3, h=3)
    qs.append(Q("A worker earns $14 each hour. Write an equation for the pay p after h hours.",
                eq[0], eq, False, "The pay depends on the hours: p = 14h", "g6depvar"))
    qs.append(Q("What is the opposite of the opposite of –12?", "–12", ["–12", "-12"], False,
                "The opposite of –12 is 12, and the opposite of 12 is –12", "g6opp"))
    qs.append(Q("Which statement is true? A: –12 > –4 B: |–12| > |–4|. Write the letter.", "B", ["B"],
                False, "–12 is further left than –4, so –12 is not greater than –4; but 12 is "
                "more than 4, so |–12| > |–4|", "g6absorder"))
    forms = ["x + 8", "x+8", "8 + x", "8+x"]
    _expr_ok(forms, 5 + 8, x=5)
    qs.append(Q("Max has x marbles. He gets 8 more. Write an expression for how many he has now.",
                forms[0], forms, False, "Starting with x and getting 8 more: x + 8", "g6expr_var"))
    from decimal import ROUND_HALF_UP
    v = D("6.3547").quantize(D("0.01"), rounding=ROUND_HALF_UP)
    qs.append(Q("Round 6.3547 to the nearest hundredth.", str(v), [str(v), dec(v)], False,
                "Look at the thousandths: 4, so round down. 6.35", "g5round"))
    return qs


# Tests AL, AM and AN are one batch from `skills.py --plan --sheets 3` after AI, AJ
# and AK were marked. Only 24 distinct standards were left to ask (19 failures, 3
# reviews, and 6.NS.C.6.b/c just unlocked now that 5.G.A.1 is above the gate), so
# each sheet gets two extra questions on the weakest standards, aimed at a
# different component from the one already on the batch: a benchmark estimate,
# subtracting a negative, a missing edge of a box, a ratio, the distributive
# property and a pattern pair.
def test_al():
    """Batch sheet 1: fractions, signed numbers, a GCF, unit price, opposites,
    distance, an expression, a benchmark and subtracting a negative."""
    qs = []
    v = F(17, 4) - F(11, 6)
    qs.append(Q("A hose is 4 1/4 m long. A piece 1 5/6 m long is cut off. How much hose is left?",
                f"{mixed(v)} m", [f"{mixed(v)} m", f"{frac(v)} m"], True,
                "Twelfths: 4 3/12 = 3 15/12; 3 15/12 – 1 10/12 = 2 5/12 m", "g5fword_sub", "m"))
    v = F(3, 4) + F(-11, 2) + F(1, 4)
    assert v == F(-9, 2)
    qs.append(Q("Work out 3/4 + (–5 1/2) + 1/4", f"–{mixed(-v)}", [f"–{mixed(-v)}", f"-{mixed(-v)}"],
                False, "Positives first: 3/4 + 1/4 = 1. Then 1 + (–5 1/2) = –4 1/2", "g7rat"))
    v = -9 + 14 - 8
    qs.append(Q("At 6 a.m. the temperature was –9 °C. It rose 14 °C by noon and then fell 8 °C by "
                "night. What was the temperature at night?", f"–{-v} °C",
                [f"–{-v} °C", f"-{-v} °C", f"–{-v}", f"-{-v}", f"–{-v}°C", f"-{-v}°C"], False,
                "–9 + 14 = 5; 5 – 8 = –3", "g7addrw"))
    import math
    v = math.gcd(48, 72)
    qs.append(Q("What is the greatest common factor of 48 and 72?", str(v), [str(v)], False,
                "48 ÷ 24 = 2 and 72 ÷ 24 = 3, and nothing larger divides both. 6 and 12 are shared "
                "but smaller", "g6gcf"))
    pa, pb = D(9) / 12, D(7) / 8
    v = "A" if pa < pb else "B"
    assert v == "A"
    qs.append(Q("Brand A: 12 cans cost $9. Brand B: 8 cans cost $7. Which brand is cheaper per "
                "can? Write A or B.", v, [v], False,
                f"One can: A {usd(pa)}, B {usd(pb)}. A is cheaper per can", "g6unitprice"))
    qs.append(Q("What is the opposite of the opposite of the opposite of 6?", "–6", ["–6", "-6"], False,
                "Opposite of 6 is –6; of –6 is 6; of 6 is –6. Three flips end on –6", "g6opp"))
    ax, ay, bx, by = -4, 3, -4, -5
    assert ax == bx
    v = abs(ay - by)
    qs.append(Q("Point A is at (–4, 3) and point B is at (–4, –5). How far apart are A and B?",
                str(v), [str(v), f"{v} units"], False,
                "Same x, so go up the y-axis: from 3 down to 0 is 3, and from 0 down to –5 is 5; "
                "3 + 5 = 8", "g6quad4"))
    forms = ["(8 + 7) × 3", "(8+7)×3", "3 × (8 + 7)", "3×(8+7)", "3(8 + 7)", "3(8+7)"]
    _expr_ok(forms, 3 * (8 + 7))
    qs.append(Q("Write an expression for: add 8 and 7, then multiply by 3. (Do not work it out.)",
                forms[0], forms, False, "Adding comes first, so it goes in parentheses: (8 + 7) × 3",
                "g5expr"))
    near = min((F(0), F(1, 2), F(1)), key=lambda t: abs(F(7, 8) - F(2, 5) - t))
    assert near == F(1, 2)
    qs.append(Q("Without working it out exactly: is 7/8 – 2/5 closest to 0, 1/2 or 1?", "1/2",
                ["1/2", "one half", "half", "0.5"], False,
                "7/8 is nearly 1 and 2/5 is nearly 1/2, so the difference is nearly 1/2",
                "g5fbench_sub"))
    v = F(2, 3) - F(-7, 6)
    qs.append(Q("Work out 2/3 – (–1 1/6)", mixed(v), [mixed(v), frac(v)], False,
                "Subtracting a negative is adding: 2/3 + 1 1/6 = 4/6 + 7/6 = 11/6 = 1 5/6",
                "g7ratsub"))
    return qs


def test_am():
    """Batch sheet 2: volume, a line plot, a multi-step problem, a negative
    quantity, an equation, inequality as position, a quadrant, volume units,
    a missing edge and a ratio."""
    qs = []
    v = 10 * 8 * 3
    qs.append(Q("A classroom is 10 m long, 8 m wide and 3 m tall. What is its volume?",
                f"{v} m³", [f"{v} m³", f"{v} m3", f"{v} cubic m", f"{v} cubic meters"], True,
                "10 × 8 = 80 for the floor; 80 × 3 = 240 cubic meters", "g5vol", "m³"))
    plot = {"kind": "lineplot", "denominator": 4, "max": 1, "caption": "weight of each fruit (kg)",
            "values": {"1/4": 3, "1/2": 2, "3/4": 1, "1": 1}}
    vals = {F(k): n for k, n in plot["values"].items()}
    v = sum(k * n for k, n in vals.items())
    qs.append(Q("The fruit are all put on one scale. What is the total weight?",
                f"{mixed(v)} kg", [f"{mixed(v)} kg", f"{frac(v)} kg"], True,
                "3 × 1/4 + 2 × 1/2 + 3/4 + 1 = 3/4 + 1 + 3/4 + 1 = 3 1/2 kg", "g5lineplot", "kg",
                figure=plot))
    v = 6 * 18 - 75
    qs.append(Q("A baker makes 6 trays with 18 rolls on each tray. She sells 75 rolls. How many "
                "rolls are left?", str(v), [str(v), f"{v} rolls"], False,
                "6 × 18 = 108 rolls; 108 – 75 = 33", "g4multi"))
    qs.append(Q("A golfer is 4 strokes under par. Write her score compared with par as a number.",
                "–4", ["–4", "-4"], False, "Under par is below zero: –4", "g6signed"))
    eq = ["m = 6b", "m=6b", "m = 6 × b", "m=6×b", "m = b × 6"]
    _expr_ok([e.split("=")[1] for e in eq], 6 * 4, b=4)
    qs.append(Q("A baker packs 6 muffins in each box. Write an equation for the number of muffins "
                "m in b boxes.", eq[0], eq, False,
                "The muffins depend on the boxes: m = 6b", "g6depvar"))
    qs.append(Q("Which statement says that –2 is to the right of –7? A: –2 < –7 B: –2 > –7. "
                "Write the letter.", "B", ["B"], False,
                "To the right means greater: –2 > –7", "g6ineqpos"))
    px, py = -3, 5
    quad = 1 if px > 0 and py > 0 else 2 if px < 0 < py else 3 if px < 0 and py < 0 else 4
    qs.append(Q("In which quadrant is the point (–3, 5)? Write 1, 2, 3 or 4.", str(quad),
                [str(quad), f"quadrant {quad}", f"Quadrant {quad}"], False,
                "x is negative (left), y is positive (up): the top-left quadrant, quadrant 2",
                "g6quadrant"))
    vu = ["m³", "m3", "cubic m", "cubic meters", "cubic metres"]
    qs.append(Q("Which unit measures how much space is inside a fish tank: m, m² or m³?", "m³", vu,
                False, "Space inside is volume, and volume is measured in cubic units", "g5volunit"))
    v = 120 // (6 * 5)
    assert v * 30 == 120
    qs.append(Q("A box has a volume of 120 cm³. It is 6 cm long and 5 cm wide. How tall is it?",
                f"{v} cm", [f"{v} cm", str(v)], False,
                "Volume = length × width × height, so 120 = 30 × height and height = 4",
                "g5vol_math", "cm"))
    walk, bus = 14, 8
    qs.append(Q(f"{walk} students walk to school and {bus} ride the bus. Write the ratio of bus "
                "riders to walkers.", f"{bus}:{walk}",
                [f"{bus}:{walk}", f"{bus} : {walk}", f"{bus} to {walk}", "4:7", "4 : 7", "4 to 7"], False,
                "Bus riders are named first, so 8 comes first: 8:14, which simplifies to 4:7",
                "g6ratio_write"))
    return qs


def test_an():
    """Batch sheet 3: multiplication with a zero, an expression, a decimal, an
    inequality, a grid, absolute value, a number line, an attribute, the
    distributive property and a pattern pair."""
    qs = []
    v = 4806 * 37
    qs.append(Q("Work out 4806 × 37", str(v), [str(v)], False,
                "4806 × 30 = 144180 and 4806 × 7 = 33642; add them", "g5mul24"))
    forms = ["5q – 12", "5q-12", "5 × q – 12", "5×q-12", "5q − 12"]
    _expr_ok(forms, 5 * 4 - 12, q=4)
    qs.append(Q("Write an expression for: 12 less than the product of 5 and q.", forms[0], forms,
                False, "The product of 5 and q is 5q. 12 less than that is 5q – 12, not 12 – 5q",
                "g6expr_write"))
    v = D(7) / 16
    qs.append(Q("Write 7/16 as a decimal.", dec(v), [dec(v)], False,
                "Divide 7 by 16: 16 into 7.0000 gives 0.4375", "g7fdec"))
    forms = ["n < 8", "n<8", "8 > n", "8>n"]
    qs.append(Q("A lift can carry fewer than 8 people. Write an inequality for the number of "
                "people n.", forms[0], forms, False,
                "Fewer than 8 means less than 8, not equal to it: n < 8", "g6ineqwrite"))
    grid = {"kind": "grid", "size": 7, "points": {"A": [1, 2], "B": [3, 5], "C": [6, 2]}}
    assert grid["points"]["A"][1] == grid["points"]["C"][1]
    v = grid["points"]["C"][0] - grid["points"]["A"][0]
    qs.append(Q("On this map, x is blocks east and y is blocks north. How many blocks east of "
                "A is C?", str(v), [str(v), f"{v} blocks"], False,
                "Same y; x goes from 1 to 6: 5 blocks", "g5gridread", figure=grid))
    qs.append(Q("What is the absolute value of –35?", "35", ["35"], False,
                "Absolute value is the distance from 0: 35", "g6abs"))
    v = (-4 + 2) // 2
    qs.append(Q("Point P is exactly halfway between –4 and 2 on a number line. What number is P?",
                f"–{-v}", [f"–{-v}", f"-{-v}"], False,
                "The gap from –4 to 2 is 6; half of 6 is 3; –4 + 3 = –1", "g6numline"))
    qs.append(Q("Every rhombus has 4 equal sides. Must every square have 4 equal sides? Write yes or no.",
                "yes", ["yes", "Yes"], False,
                "A square is a special rhombus, so it has everything a rhombus has", "g5shapeattr"))
    forms = ["18k – 12", "18k-12", "–12 + 18k", "-12+18k"]
    _expr_ok(forms, 6 * (3 * 5 - 2), k=5)
    qs.append(Q("Write 6(3k – 2) without parentheses.", forms[0], forms, False,
                "Multiply both terms by 6: 6 × 3k = 18k and 6 × 2 = 12", "g6distrib"))
    a = [4 * k for k in range(6)]; b = [6 * k for k in range(6)]
    pair = f"({a[5]}, {b[5]})"
    qs.append(Q("Pattern A starts at 0 and adds 4. Pattern B starts at 0 and adds 6. "
                "The first pair is (0, 0). Write the 6th pair (A, B).", pair,
                [pair, pair.replace(" ", ""), pair.strip("()"), pair.strip("()").replace(" ", "")], False,
                f"A: {', '.join(map(str, a))}. B: {', '.join(map(str, b))}. 6th terms: {pair}; "
                "(0, 0) is the 1st pair", "g5patterns"))
    return qs


# Tests AO, AP and AQ are one batch from `skills.py --plan --sheets 3` after AL, AM
# and AN were marked. 23 distinct standards were left (19 failures, 4 reviews), so
# each sheet is topped up with extra questions on the weakest standards, aimed at
# a different component than the one already on the batch. The 4th-grade pick,
# 4.OA.A.3, is there because 7.NS.A.3 rests on it and has been missed three times;
# two of those misses were units-only or blank, so it is a check, not a diagnosis.
def test_ao():
    """Batch sheet 1: fraction subtraction, a line plot, signed temperatures, a
    GCF, unit price, a grid, a quadrant, a coefficient, an estimate, an inequality."""
    qs = []
    v = F(10, 3) - F(7, 4)
    qs.append(Q("A bowl holds 3 1/3 cups of soup. Jo eats 1 3/4 cups. How much soup is left?",
                f"{mixed(v)} cups", [f"{mixed(v)} cups", f"{frac(v)} cups", f"{mixed(v)} cup"], True,
                "Twelfths: 3 4/12 = 2 16/12; 2 16/12 – 1 9/12 = 1 7/12 cups", "g5fword_sub", "cups"))
    plot = {"kind": "lineplot", "denominator": 4, "max": 1, "caption": "length of each plank (m)",
            "values": {"1/4": 2, "1/2": 1, "3/4": 3, "1": 1}}
    vals = {F(k): n for k, n in plot["values"].items()}
    v = sum(k * n for k, n in vals.items())
    qs.append(Q("The planks are laid end to end. What is the total length?",
                f"{mixed(v)} m", [f"{mixed(v)} m", f"{frac(v)} m"], True,
                "2 × 1/4 + 1/2 + 3 × 3/4 + 1 = 1/2 + 1/2 + 2 1/4 + 1 = 4 1/4 m", "g5lineplot", "m",
                figure=plot))
    v = 3 - 11 + 6
    qs.append(Q("At 8 p.m. the temperature was 3 °C. By 6 a.m. it had fallen 11 °C, and by noon it "
                "had risen 6 °C. What was the temperature at noon?", f"–{-v} °C",
                [f"–{-v} °C", f"-{-v} °C", f"–{-v}", f"-{-v}", f"–{-v}°C", f"-{-v}°C"], False,
                "3 – 11 = –8; –8 + 6 = –2", "g7addrw"))
    import math
    v = math.gcd(54, 90)
    qs.append(Q("What is the greatest common factor of 54 and 90?", str(v), [str(v)], False,
                "54 ÷ 18 = 3 and 90 ÷ 18 = 5, and nothing larger divides both. 6 and 9 are shared "
                "but smaller", "g6gcf"))
    pa, pb = D(5) / 6, D(7) / 9
    v = "A" if pa < pb else "B"
    assert v == "B"
    qs.append(Q("Store A: 6 yogurts cost $5. Store B: 9 yogurts cost $7. Which store is cheaper per "
                "yogurt? Write A or B.", v, [v], False,
                f"One yogurt: A {usd(pa)}, B {usd(pb)}. B is cheaper per yogurt", "g6unitprice"))
    grid = {"kind": "grid", "size": 7, "points": {"A": [2, 1], "B": [2, 5], "C": [6, 3]}}
    assert grid["points"]["A"][0] == grid["points"]["B"][0]
    v = grid["points"]["B"][1] - grid["points"]["A"][1]
    qs.append(Q("On this map, x is blocks east and y is blocks north. How many blocks north of "
                "A is B?", str(v), [str(v), f"{v} blocks"], False,
                "Same x; y goes from 1 to 5: 4 blocks", "g5gridread", figure=grid))
    px, py = 4, -6
    quad = 1 if px > 0 and py > 0 else 2 if px < 0 < py else 3 if px < 0 and py < 0 else 4
    qs.append(Q("In which quadrant is the point (4, –6)? Write 1, 2, 3 or 4.", str(quad),
                [str(quad), f"quadrant {quad}", f"Quadrant {quad}"], False,
                "x is positive (right), y is negative (down): the bottom-right quadrant, quadrant 4",
                "g6quadrant"))
    qs.append(Q("What is the coefficient of y in the expression 9 + 4y?", "4", ["4"], False,
                "The coefficient is the number multiplying the letter: 4", "g6coef"))
    v = round(F(31, 8)) + round(F(11, 5))
    assert v == 6
    qs.append(Q("Estimate 3 7/8 + 2 1/5 by rounding each number to the nearest whole number.",
                str(v), [str(v)], False, "3 7/8 is nearly 4 and 2 1/5 is nearly 2: 4 + 2 = 6",
                "g5fbench"))
    forms = ["h > 120", "h>120", "120 < h", "120<h"]
    qs.append(Q("To ride the roller coaster you must be taller than 120 cm. Write an inequality "
                "for a rider's height h.", forms[0], forms, False,
                "Taller than 120 means more than 120, not equal to it: h > 120", "g6ineqwrite"))
    return qs


def test_ap():
    """Batch sheet 2: multiplication with a zero, an expression, a multi-step
    problem, an equation, opposites, position, division of fractions, powers,
    subtracting a negative and distance."""
    qs = []
    v = 7203 * 46
    qs.append(Q("Work out 7203 × 46", str(v), [str(v)], False,
                "7203 × 40 = 288120 and 7203 × 6 = 43218; add them", "g5mul24"))
    forms = ["6t – 4", "6t-4", "6 × t – 4", "6×t-4", "6t − 4"]
    _expr_ok(forms, 6 * 5 - 4, t=5)
    qs.append(Q("Write an expression for: 4 less than 6 times t.", forms[0], forms, False,
                "6 times t is 6t. 4 less than that is 6t – 4, not 4 – 6t", "g6expr_write"))
    v = 9 * 36 // 12
    assert v * 12 == 9 * 36
    qs.append(Q("A farmer has 9 crates with 36 eggs in each crate. He packs all the eggs into "
                "cartons of 12. How many cartons does he fill?", str(v), [str(v), f"{v} cartons"], False,
                "9 × 36 = 324 eggs; 324 ÷ 12 = 27", "g4multi"))
    eq = ["f = 8r", "f=8r", "f = 8 × r", "f=8×r", "f = r × 8"]
    _expr_ok([e.split("=")[1] for e in eq], 8 * 3, r=3)
    qs.append(Q("A gardener plants 8 flowers in each row. Write an equation for the number of "
                "flowers f in r rows.", eq[0], eq, False,
                "The flowers depend on the rows: f = 8r", "g6depvar"))
    qs.append(Q("What is the opposite of the opposite of the opposite of –9?", "9", ["9"], False,
                "Opposite of –9 is 9; of 9 is –9; of –9 is 9. Three flips end on 9", "g6opp"))
    qs.append(Q("Which statement says that –9 is to the left of –3? A: –9 > –3 B: –9 < –3. "
                "Write the letter.", "B", ["B"], False,
                "To the left means less: –9 < –3", "g6ineqpos"))
    v = F(9, 2) / F(2, 3)
    qs.append(Q("How many 2/3-meter pieces can be cut from a rope that is 4 1/2 meters long?",
                mixed(v), [mixed(v), f"{mixed(v)} pieces", frac(v), f"{frac(v)} pieces", "6.75"], False,
                "4 1/2 = 9/2, and 9/2 ÷ 2/3 = 9/2 × 3/2 = 27/4 = 6 3/4", "g6fdivword"))
    v = 4 ** 3 - 5 ** 2
    qs.append(Q("Work out 4³ – 5²", str(v), [str(v)], False,
                "4³ = 64 and 5² = 25: 64 – 25 = 39", "g6exp"))
    v = F(-3, 4) - F(-3, 2)
    qs.append(Q("Work out –3/4 – (–1 1/2)", frac(v), [frac(v)], False,
                "Subtracting a negative is adding: –3/4 + 1 1/2 = 3/4", "g7ratsub"))
    cx, cy, dx, dy = 2, -6, -5, -6
    assert cy == dy
    v = abs(cx - dx)
    qs.append(Q("Point C is at (2, –6) and point D is at (–5, –6). How far apart are C and D?",
                str(v), [str(v), f"{v} units"], False,
                "Same y, so go along the x-axis: from 2 to 0 is 2, and from 0 to –5 is 5; 2 + 5 = 7",
                "g6quad4"))
    return qs


def test_aq():
    """Batch sheet 3: a signed sum, a negative quantity, a decimal, an
    inequality, distance, absolute value, a prism, multiplication, speed, a plot."""
    qs = []
    v = F(3, 5) + F(-9, 2) + F(2, 5)
    assert v == F(-7, 2)
    qs.append(Q("Work out 3/5 + (–4 1/2) + 2/5", f"–{mixed(-v)}", [f"–{mixed(-v)}", f"-{mixed(-v)}"],
                False, "Positives first: 3/5 + 2/5 = 1. Then 1 + (–4 1/2) = –3 1/2", "g7rat"))
    qs.append(Q("A plane is 8000 ft above sea level and a diver is 60 ft below sea level. Write the "
                "diver's position as a number.", "–60", ["–60", "-60", "–60 ft", "-60 ft"], False,
                "Below sea level is negative: –60", "g6signed"))
    v = D(9) / 16
    qs.append(Q("Write 9/16 as a decimal.", dec(v), [dec(v)], False,
                "Divide 9 by 16: 16 into 9.0000 gives 0.5625", "g7fdec"))
    forms = ["w < 10", "w<10", "10 > w", "10>w"]
    qs.append(Q("A bridge can hold less than 10 tons. Write an inequality for the weight w in tons.",
                forms[0], forms, False,
                "Less than 10 means w is below 10, not equal to it: w < 10", "g6ineqwrite"))
    ay, by = 9, -4
    v = abs(ay - by)
    qs.append(Q("Point A is at (–2, 9) and point B is at (–2, –4). How far apart are A and B?",
                str(v), [str(v), f"{v} units"], False,
                "Same x, so go up the y-axis: from 9 down to 0 is 9, and from 0 down to –4 is 4; "
                "9 + 4 = 13", "g6quad4"))
    qs.append(Q("How far is –27 from 0 on a number line?", "27", ["27", "27 units"], False,
                "Distance is never negative: the absolute value of –27 is 27", "g6abs"))
    v = F(5, 2) * 4 * 2
    qs.append(Q("A box is 2 1/2 m long, 4 m wide and 2 m tall. What is its volume?",
                f"{v} m³", [f"{v} m³", f"{v} m3", f"{v} cubic m"], True,
                "2 1/2 × 4 = 10 for the base; 10 × 2 = 20 cubic meters", "g6volfrac", "m³"))
    v = 645 * 38
    qs.append(Q("Work out 645 × 38", str(v), [str(v)], False,
                "645 × 30 = 19350 and 645 × 8 = 5160; add them", "g5mulw"))
    v = F(180, 4) * 7
    assert v.denominator == 1
    qs.append(Q("A train travels 180 miles in 4 hours at a steady speed. How far does it travel in "
                "7 hours?", f"{v} miles", [f"{v} miles", f"{v} mi", str(v)], False,
                "180 ÷ 4 = 45 miles in 1 hour; 45 × 7 = 315", "g6speed"))
    plot = {"kind": "lineplot", "denominator": 8, "max": 1, "caption": "length of each ribbon (m)",
            "values": {"1/8": 1, "1/4": 2, "1/2": 1, "3/4": 1}}
    vals = {F(k): n for k, n in plot["values"].items()}
    v = max(vals) - min(vals)
    qs.append(Q("How much longer is the longest ribbon than the shortest?",
                f"{mixed(v)} m", [f"{mixed(v)} m", f"{frac(v)} m"], True,
                "Longest 3/4 m, shortest 1/8 m: 6/8 – 1/8 = 5/8 m", "g5lineplot", "m", figure=plot))
    return qs


# Tests AR, AS and AT are one batch from `skills.py --plan --sheets 3` after AO, AP
# and AQ were marked. 23 distinct standards were left (17 failures, 6 reviews), so
# each sheet is topped up with extra questions on the weakest standards, aimed at
# a different component or a fresh context. Repeated confusions are targeted:
# regrouping when subtracting mixed numbers, sign loss on a negative sum, the
# greatest (not just a shared) factor, the cheaper-per-item pack, dependent
# variable first in an equation, and a unit after an answer.
def test_ar():
    """Batch sheet 1: fractions, a signed sum, a negative quantity, a multi-step
    problem, an inequality, a grid, a ratio table, substitution and extras."""
    qs = []
    v = F(13, 4) - F(11, 6)
    qs.append(Q("A pitcher holds 3 1/4 liters. Ana pours out 1 5/6 liters. How much is left?",
                f"{mixed(v)} liters", [f"{mixed(v)} liters", f"{frac(v)} liters", f"{mixed(v)} L", f"{mixed(v)} l"], True,
                "Twelfths: 3 3/12 = 2 15/12; 2 15/12 – 1 10/12 = 1 5/12 liters", "g5fword_sub", "liters"))
    v = F(7, 10) + F(-23, 5) + F(3, 10)
    assert v == F(-18, 5)
    qs.append(Q("Work out 7/10 + (–4 3/5) + 3/10", f"–{mixed(-v)}", [f"–{mixed(-v)}", f"-{mixed(-v)}"],
                False, "Positives first: 7/10 + 3/10 = 1. Then 1 + (–4 3/5) = –3 3/5", "g7rat"))
    qs.append(Q("A company lost $250 this month. Write its profit as a number.", "–$250",
                ["–$250", "-$250", "–250", "-250"], False,
                "A loss is below zero: –250", "g6signed"))
    v = 7 * 24 + 36
    assert v == 204
    qs.append(Q("A school buys 7 boxes of 24 markers and then 36 single markers. How many markers "
                "is that?", str(v), [str(v), f"{v} markers"], False,
                "7 × 24 = 168; 168 + 36 = 204", "g4multi"))
    forms = ["a < 18", "a<18", "18 > a", "18>a"]
    qs.append(Q("A kids' ticket is for children younger than 18. Write an inequality for a child's "
                "age a.", forms[0], forms, False,
                "Younger than 18 means less than 18, not equal to it: a < 18", "g6ineqwrite"))
    grid = {"kind": "grid", "size": 7, "points": {"A": [5, 2], "B": [1, 6], "C": [5, 5]}}
    assert grid["points"]["A"][0] == grid["points"]["C"][0]
    v = grid["points"]["C"][1] - grid["points"]["A"][1]
    qs.append(Q("On this map, x is blocks east and y is blocks north. How many blocks north of "
                "A is C?", str(v), [str(v), f"{v} blocks"], False,
                "Same x; y goes from 2 to 5: 3 blocks", "g5gridread", figure=grid))
    v = F(35, 5) * 3
    assert v.denominator == 1
    qs.append(Q("Juice and water are mixed in the ratio 5 : 3. How many cups of water go with 35 "
                "cups of juice?", str(v), [str(v), f"{v} cups"], False,
                "35 is 7 times 5, so the water is 7 × 3 = 21 cups", "g6ratiotable"))
    v = next(x for x in (3, 4, 5) if 6 * x - 5 == 19)
    qs.append(Q("Which value of x makes 6x – 5 = 19 true: 3, 4 or 5?", str(v), [str(v)], False,
                "Try each: 6 × 4 – 5 = 19", "g6subst"))
    v = F(5, 6) - F(3, 8)
    qs.append(Q("A ribbon is 5/6 m long. A piece 3/8 m long is cut off. How much is left?",
                f"{mixed(v)} m", [f"{mixed(v)} m", f"{frac(v)} m"], True,
                "24ths: 5/6 = 20/24 (×4) and 3/8 = 9/24 (×3). 20/24 – 9/24 = 11/24 m",
                "g5fword_sub", "m"))
    v = F(1, 2) - F(-9, 4)
    qs.append(Q("Work out 1/2 – (–2 1/4)", mixed(v), [mixed(v), frac(v)], False,
                "Subtracting a negative is adding: 1/2 + 2 1/4 = 2 3/4", "g7ratsub"))
    return qs


def test_as():
    """Batch sheet 2: a line plot, expressions, equations, a decimal, opposites,
    division of fractions, equivalence and a quadrant, plus extras."""
    qs = []
    plot = {"kind": "lineplot", "denominator": 4, "max": 1, "caption": "weight of each bag (kg)",
            "values": {"1/4": 1, "1/2": 3, "3/4": 2, "1": 1}}
    vals = {F(k): n for k, n in plot["values"].items()}
    v = sum(k * n for k, n in vals.items())
    qs.append(Q("All the bags are put on one scale. What is the total weight?",
                f"{mixed(v)} kg", [f"{mixed(v)} kg", f"{frac(v)} kg"], True,
                "1/4 + 3 × 1/2 + 2 × 3/4 + 1 = 1/4 + 1 1/2 + 1 1/2 + 1 = 4 1/4 kg", "g5lineplot", "kg",
                figure=plot))
    forms = ["7c – 9", "7c-9", "7 × c – 9", "7×c-9", "7c − 9"]
    _expr_ok(forms, 7 * 5 - 9, c=5)
    qs.append(Q("Write an expression for: 9 less than 7 times c.", forms[0], forms, False,
                "7 times c is 7c. 9 less than that is 7c – 9, not 9 – 7c", "g6expr_write"))
    eq = ["c = 9n", "c=9n", "c = 9 × n", "c=9×n", "c = n × 9"]
    _expr_ok([e.split("=")[1] for e in eq], 9 * 4, n=4)
    qs.append(Q("A pack holds 9 cards. Write an equation for the number of cards c in n packs.",
                eq[0], eq, False, "The cards depend on the packs: c = 9n", "g6depvar"))
    v = D(11) / 16
    qs.append(Q("Write 11/16 as a decimal.", dec(v), [dec(v)], False,
                "Divide 11 by 16: 16 into 11.0000 gives 0.6875", "g7fdec"))
    qs.append(Q("What is the opposite of the opposite of the opposite of 15?", "–15", ["–15", "-15"], False,
                "Opposite of 15 is –15; of –15 is 15; of 15 is –15. Three flips end on –15", "g6opp"))
    v = F(15, 4) / F(3, 8)
    assert v == 10
    qs.append(Q("How many 3/8-liter cups can be filled from 3 3/4 liters of juice?", str(v),
                [str(v), f"{v} cups"], False,
                "3 3/4 = 15/4, and 15/4 ÷ 3/8 = 15/4 × 8/3 = 120/12 = 10", "g6fdivword"))
    same = all(4 * (x - 2) == 4 * x - 8 for x in (0, 1, 7))
    v = "yes" if same else "no"
    qs.append(Q("Are 4(x – 2) and 4x – 8 equivalent? Write yes or no.", v, [v, v.capitalize()], False,
                "4(x – 2) = 4x – 8. Check x = 3: 4 and 4. So yes", "g6equiv"))
    px, py = -7, -2
    quad = 1 if px > 0 and py > 0 else 2 if px < 0 < py else 3 if px < 0 and py < 0 else 4
    qs.append(Q("In which quadrant is the point (–7, –2)? Write 1, 2, 3 or 4.", str(quad),
                [str(quad), f"quadrant {quad}", f"Quadrant {quad}"], False,
                "Both coordinates are negative: left and down, quadrant 3", "g6quadrant"))
    eq = ["d = 55h", "d=55h", "d = 55 × h", "d=55×h", "d = h × 55"]
    _expr_ok([e.split("=")[1] for e in eq], 55 * 3, h=3)
    qs.append(Q("A bus travels 55 miles each hour. Write an equation for the distance d after h hours.",
                eq[0], eq, False, "The distance depends on the hours: d = 55h", "g6depvar"))
    forms = ["3(p + 6)", "3 × (p + 6)", "3(p+6)", "3×(p+6)", "(p + 6) × 3", "(p+6)×3"]
    _expr_ok(forms, 3 * (4 + 6), p=4)
    qs.append(Q("Write an expression for: 3 times the sum of p and 6.", forms[0], forms, False,
                "The sum of p and 6 is p + 6, kept in parentheses, then × 3", "g6expr_write"))
    return qs


def test_at():
    """Batch sheet 3: multiplication with a zero, a GCF, a money problem, unit
    price, distance, a number line, order and extras."""
    qs = []
    v = 8105 * 63
    qs.append(Q("Work out 8105 × 63", str(v), [str(v)], False,
                "8105 × 60 = 486300 and 8105 × 3 = 24315; add them", "g5mul24"))
    import math
    v = math.gcd(60, 84)
    qs.append(Q("What is the greatest common factor of 60 and 84?", str(v), [str(v)], False,
                "60 ÷ 12 = 5 and 84 ÷ 12 = 7, and nothing larger divides both. 6 and 4 are shared "
                "but smaller", "g6gcf"))
    v = D(50) - 4 * D("3.75") - D("1.60")
    qs.append(Q("Dan has $50. He buys 4 books at $3.75 each and a pen for $1.60. How much money "
                "does he have left?", usd(v), [usd(v), f"${dec(v)}"], True,
                "4 × $3.75 = $15.00; $15.00 + $1.60 = $16.60; $50 – $16.60 = $33.40", "money", "$"))
    pa, pb = D(11) / 10, D(5) / 4
    v = "A" if pa < pb else "B"
    assert v == "A"
    qs.append(Q("Pack A: 10 batteries cost $11. Pack B: 4 batteries cost $5. Which pack is cheaper "
                "per battery? Write A or B.", v, [v], False,
                f"One battery: A {usd(pa)}, B {usd(pb)}. A is cheaper per battery", "g6unitprice"))
    v = abs(-8 - 5)
    qs.append(Q("Point P is at (–8, 3) and point Q is at (5, 3). How far apart are P and Q?",
                str(v), [str(v), f"{v} units"], False,
                "Same y, so go along the x-axis: from –8 to 0 is 8, and from 0 to 5 is 5; 8 + 5 = 13",
                "g6quad4"))
    v = (-9 + 3) // 2
    qs.append(Q("Point M is exactly halfway between –9 and 3 on a number line. What number is M?",
                f"–{-v}", [f"–{-v}", f"-{-v}"], False,
                "The gap from –9 to 3 is 12; half is 6; –9 + 6 = –3", "g6numline"))
    qs.append(Q("A pond is at –12 ft and a lake is at –30 ft (compared with sea level). Which is "
                "lower? Write pond or lake.", "lake", ["lake", "Lake"], False,
                "–30 is less than –12, so the lake is lower", "g6order"))
    v = F(5, 6) + F(-23, 6) + 2
    assert v == -1
    qs.append(Q("Work out 5/6 + (–3 5/6) + 2", "–1", ["–1", "-1"], False,
                "Positives first: 5/6 + 2 = 2 5/6. Then 2 5/6 + (–3 5/6) = –1", "g7rat"))
    v = F(240, 3) * 5
    assert v.denominator == 1
    qs.append(Q("A cyclist rides 240 km in 3 days at a steady rate. How far does she ride in 5 days?",
                f"{v} km", [f"{v} km", str(v)], False,
                "240 ÷ 3 = 80 km per day; 80 × 5 = 400", "g6speed"))
    qs.append(Q("A cave is 40 m below ground and a bird flies 25 m above ground. Write the cave's "
                "position as a number.", "–40", ["–40", "-40", "–40 m", "-40 m"], False,
                "Below ground is negative: –40", "g6signed"))
    return qs


# Tests AU, AV and AW are one batch from `skills.py --plan --sheets 3` after AR, AS
# and AT were marked. Only 13 standards are still asked-and-failing and nothing is
# due for review, so the 30 questions are those 13 standards two or three times
# each, every time aimed at a different component or a different confusion:
# regrouping, adding instead of taking away, flipping the divisor, a letter
# swapped in an equation, the greatest (not just a shared) factor, the
# cheaper-per-item pack, and the sign lost on a negative sum.
def test_au():
    """Batch sheet 1: fractions, expressions, unit price, opposites, a quadrant,
    a signed sum, an equation, division of fractions, a line plot and a GCF."""
    qs = []
    v = F(19, 4) - F(11, 6)
    qs.append(Q("A roll of tape is 4 3/4 m long. Kim uses 1 5/6 m. How much tape is left?",
                f"{mixed(v)} m", [f"{mixed(v)} m", f"{frac(v)} m"], True,
                "Twelfths: 4 9/12 – 1 10/12; regroup: 3 21/12 – 1 10/12 = 2 11/12 m", "g5fword_sub", "m"))
    forms = ["8k – 15", "8k-15", "8 × k – 15", "8×k-15", "8k − 15"]
    _expr_ok(forms, 8 * 5 - 15, k=5)
    qs.append(Q("Write an expression for: 15 less than 8 times k.", forms[0], forms, False,
                "8 times k is 8k. 15 less than that is 8k – 15, not 15 – 8k", "g6expr_write"))
    pa, pb = D(13) / 10, D(7) / 6
    v = "A" if pa < pb else "B"
    assert v == "B"
    qs.append(Q("Pack A: 10 stickers cost $13. Pack B: 6 stickers cost $7. Which pack is cheaper "
                "per sticker? Write A or B.", v, [v], False,
                f"One sticker: A {usd(pa)}, B {usd(pb)}. B is cheaper per sticker", "g6unitprice"))
    qs.append(Q("What is the opposite of the opposite of the opposite of –20?", "20", ["20"], False,
                "Opposite of –20 is 20; of 20 is –20; of –20 is 20. Three flips end on 20", "g6opp"))
    px, py = 8, -1
    quad = 1 if px > 0 and py > 0 else 2 if px < 0 < py else 3 if px < 0 and py < 0 else 4
    qs.append(Q("In which quadrant is the point (8, –1)? Write 1, 2, 3 or 4.", str(quad),
                [str(quad), f"quadrant {quad}", f"Quadrant {quad}"], False,
                "x is positive (right), y is negative (down): quadrant 4", "g6quadrant"))
    v = F(1, 4) + F(-17, 4) + F(3, 4)
    assert v == F(-13, 4)
    qs.append(Q("Work out 1/4 + (–4 1/4) + 3/4", f"–{mixed(-v)}", [f"–{mixed(-v)}", f"-{mixed(-v)}"],
                False, "Positives first: 1/4 + 3/4 = 1. Then 1 + (–4 1/4) = –3 1/4", "g7rat"))
    eq = ["w = 12d", "w=12d", "w = 12 × d", "w=12×d", "w = d × 12"]
    _expr_ok([e.split("=")[1] for e in eq], 12 * 3, d=3)
    qs.append(Q("A carton holds 12 eggs. Write an equation for the number of eggs w in d cartons.",
                eq[0], eq, False, "The eggs depend on the cartons: w = 12d", "g6depvar"))
    v = F(7, 2) / F(7, 8)
    assert v == 4
    qs.append(Q("How many 7/8-kg bags can be filled from 3 1/2 kg of flour?", str(v),
                [str(v), f"{v} bags"], False,
                "3 1/2 = 7/2, and 7/2 ÷ 7/8 = 7/2 × 8/7 = 4", "g6fdivword"))
    plot = {"kind": "lineplot", "denominator": 4, "max": 1, "caption": "length of each stick (m)",
            "values": {"1/4": 2, "1/2": 2, "3/4": 1, "1": 2}}
    vals = {F(k): n for k, n in plot["values"].items()}
    v = sum(k * n for k, n in vals.items())
    qs.append(Q("The sticks are laid end to end. What is the total length?",
                f"{mixed(v)} m", [f"{mixed(v)} m", f"{frac(v)} m"], True,
                "2 × 1/4 + 2 × 1/2 + 3/4 + 2 = 1/2 + 1 + 3/4 + 2 = 4 1/4 m", "g5lineplot", "m", figure=plot))
    import math
    v = math.gcd(42, 70)
    qs.append(Q("What is the greatest common factor of 42 and 70?", str(v), [str(v)], False,
                "42 ÷ 14 = 3 and 70 ÷ 14 = 5, and nothing larger divides both. 2 and 7 are shared "
                "but smaller", "g6gcf"))
    return qs


def test_av():
    """Batch sheet 2: a fraction sum, an expression, speed, opposites, a quadrant,
    a signed sum, an equation, a negative quantity, a line plot, a multi-step problem."""
    qs = []
    v = F(11, 6) + F(5, 4)
    qs.append(Q("A cat ate 1 5/6 cups of food on Monday and 1 1/4 cups on Tuesday. How much did it "
                "eat in all?", f"{mixed(v)} cups", [f"{mixed(v)} cups", f"{frac(v)} cups"], True,
                "Twelfths: 1 10/12 + 1 3/12 = 2 13/12 = 3 1/12 cups", "g5fword_add", "cups"))
    forms = ["3(x + 9)", "3 × (x + 9)", "3(x+9)", "3×(x+9)", "(x + 9) × 3", "(x+9)×3"]
    _expr_ok(forms, 3 * (4 + 9), x=4)
    qs.append(Q("Write an expression for: 3 times the sum of x and 9.", forms[0], forms, False,
                "The sum of x and 9 is x + 9, kept in parentheses, then × 3", "g6expr_write"))
    v = F(210, 6) * 9
    assert v.denominator == 1
    qs.append(Q("A car travels 210 miles in 6 hours at a steady speed. How far does it go in 9 "
                "hours?", f"{v} miles", [f"{v} miles", f"{v} mi", str(v)], False,
                "210 ÷ 6 = 35 miles in 1 hour; 35 × 9 = 315", "g6speed"))
    qs.append(Q("What is the opposite of the opposite of –31?", "–31", ["–31", "-31"], False,
                "The opposite of –31 is 31, and the opposite of 31 is –31", "g6opp"))
    px, py = -6, 9
    quad = 1 if px > 0 and py > 0 else 2 if px < 0 < py else 3 if px < 0 and py < 0 else 4
    qs.append(Q("In which quadrant is the point (–6, 9)? Write 1, 2, 3 or 4.", str(quad),
                [str(quad), f"quadrant {quad}", f"Quadrant {quad}"], False,
                "x is negative (left), y is positive (up): quadrant 2", "g6quadrant"))
    v = F(5, 6) + F(-10, 3) + F(1, 6)
    assert v == F(-7, 3)
    qs.append(Q("Work out 5/6 + (–3 1/3) + 1/6", f"–{mixed(-v)}", [f"–{mixed(-v)}", f"-{mixed(-v)}"],
                False, "Positives first: 5/6 + 1/6 = 1. Then 1 + (–3 1/3) = –2 1/3", "g7rat"))
    eq = ["s = 4c", "s=4c", "s = 4 × c", "s=4×c", "s = c × 4"]
    _expr_ok([e.split("=")[1] for e in eq], 4 * 6, c=6)
    qs.append(Q("A car has 4 seats. Write an equation for the number of seats s in c cars.",
                eq[0], eq, False, "The seats depend on the cars: s = 4c", "g6depvar"))
    qs.append(Q("A balloon is 15 m above the ground and a mole is 3 m below the ground. Write the "
                "mole's position as a number.", "–3", ["–3", "-3", "–3 m", "-3 m"], False,
                "Below ground is negative: –3", "g6signed"))
    plot = {"kind": "lineplot", "denominator": 4, "max": 1, "caption": "milk in each jug (liters)",
            "values": {"1/4": 3, "1/2": 1, "3/4": 2, "1": 1}}
    vals = {F(k): n for k, n in plot["values"].items()}
    v = sum(k * n for k, n in vals.items())
    qs.append(Q("All the milk is poured into one tank. How much milk is that in all?",
                f"{mixed(v)} liters", [f"{mixed(v)} liters", f"{frac(v)} liters", f"{mixed(v)} L"], True,
                "3 × 1/4 + 1/2 + 2 × 3/4 + 1 = 3/4 + 1/2 + 1 1/2 + 1 = 3 3/4 liters", "g5lineplot",
                "liters", figure=plot))
    v = 12 * 15 - 4 * 25
    qs.append(Q("A shop has 12 packs of 15 pens. It puts 4 packs of 25 pens on sale. How many pens "
                "are not on sale?", str(v), [str(v), f"{v} pens"], False,
                "12 × 15 = 180 pens in all; 4 × 25 = 100 on sale; 180 – 100 = 80", "g4multi"))
    return qs


def test_aw():
    """Batch sheet 3: a benchmark estimate, a negative quantity, a GCF, a multi-step
    problem, a signed difference, division, two decimal conversions, a line plot, a rate."""
    qs = []
    near = min((F(0), F(1, 2), F(1)), key=lambda t: abs(F(5, 6) + F(3, 7) - t))
    v = "greater than 1" if F(5, 6) + F(3, 7) > 1 else "less than 1"
    qs.append(Q("Without adding exactly: is 5/6 + 3/7 greater than 1 or less than 1?", v,
                [v, v.split()[0] + " " + v.split()[1], f"{v.split()[0]}"], False,
                "5/6 is nearly 1 and 3/7 is nearly 1/2, so the sum is well over 1", "g5fbench"))
    qs.append(Q("A balloon is 8 m above the ground and a fish is 6 m below the surface of a "
                "pond. Write the fish's position as a number.", "–6", ["–6", "-6", "–6 m", "-6 m"], False,
                "Below the surface is negative: –6", "g6signed"))
    import math
    v = math.gcd(66, 90)
    qs.append(Q("What is the greatest common factor of 66 and 90?", str(v), [str(v)], False,
                "66 ÷ 6 = 11 and 90 ÷ 6 = 15, and nothing larger divides both. 2 and 3 are shared "
                "but smaller", "g6gcf"))
    v = (8 * 14 + 28) // 7
    assert v * 7 == 8 * 14 + 28
    qs.append(Q("A baker makes 8 trays with 14 rolls and then 28 more rolls. She packs them into "
                "bags of 7. How many bags does she fill?", str(v), [str(v), f"{v} bags"], False,
                "8 × 14 = 112; 112 + 28 = 140; 140 ÷ 7 = 20", "g4multi"))
    v = F(2, 5) - F(-17, 10)
    qs.append(Q("Work out 2/5 – (–1 7/10)", mixed(v), [mixed(v), frac(v)], False,
                "Subtracting a negative is adding: 2/5 + 1 7/10 = 4/10 + 1 7/10 = 2 1/10", "g7ratsub"))
    v = F(13, 2) / F(13, 4)
    assert v == 2
    qs.append(Q("How many 3 1/4-m pieces can be cut from a rope 6 1/2 m long?", str(v),
                [str(v), f"{v} pieces"], False,
                "6 1/2 = 13/2 and 3 1/4 = 13/4; 13/2 ÷ 13/4 = 13/2 × 4/13 = 2", "g6fdivword"))
    v = D(13) / 16
    qs.append(Q("Write 13/16 as a decimal.", dec(v), [dec(v)], False,
                "Divide 13 by 16: 16 into 13.0000 gives 0.8125", "g7fdec"))
    qs.append(Q("Does 5/12 as a decimal end or repeat? Write end or repeat.", "repeat",
                ["repeat", "repeats", "Repeat"], False,
                "5 ÷ 12 = 0.41666…, and the 6 never stops: it repeats", "g7decrep"))
    plot = {"kind": "lineplot", "denominator": 8, "max": 1, "caption": "length of each piece (m)",
            "values": {"1/8": 2, "1/4": 1, "1/2": 2, "3/4": 1}}
    vals = {F(k): n for k, n in plot["values"].items()}
    v = sum(k * n for k, n in vals.items())
    qs.append(Q("The pieces are joined end to end. What is the total length?",
                f"{mixed(v)} m", [f"{mixed(v)} m", f"{frac(v)} m"], True,
                "2 × 1/8 + 1/4 + 2 × 1/2 + 3/4 = 1/4 + 1/4 + 1 + 3/4 = 2 1/4 m", "g5lineplot", "m",
                figure=plot))
    pa, pb = D(15) / 12, D(9) / 8
    v = "A" if pa < pb else "B"
    assert v == "B"
    qs.append(Q("Store A: 12 pencils cost $15. Store B: 8 pencils cost $9. Which store is cheaper "
                "per pencil? Write A or B.", v, [v], False,
                f"One pencil: A {usd(pa)}, B {usd(pb)}. B is cheaper per pencil", "g6unitprice"))
    return qs


# Tests AX, AY and AZ are one batch from `skills.py --plan --sheets 3` after AU, AV
# and AW were marked. The plan returned only six standards (all failures, nothing
# due for review). 24 of the 30 questions are those six, four each, every one
# aimed at a different component or confusion (regrouping, a benchmark estimate,
# "less than" direction, a line-plot sum or difference, dividing fractions, the
# dependent variable first, a quadrant and a reflection). The other six are
# confirmation questions on skills that were just promoted to mastered on thin or
# mixed records, so a lucky streak is not mistaken for mastery.
def test_ax():
    qs = []
    v = F(21, 4) - F(17, 6)
    qs.append(Q("A sack holds 5 1/4 kg of potatoes. Then 2 5/6 kg are used. How much is left?",
                f"{mixed(v)} kg", [f"{mixed(v)} kg", f"{frac(v)} kg"], True,
                "Twelfths: 5 3/12 = 4 15/12; 4 15/12 – 2 10/12 = 2 5/12 kg", "g5fword_sub", "kg"))
    v = 706 * 358
    assert v == 211800 + 35300 + 5648
    qs.append(Q("Work out 706 × 358", str(v), [str(v)], False,
                "706 × 300 = 211800, 706 × 50 = 35300, 706 × 8 = 5648; add them", "g5mul33"))
    k = 5
    opts = {"A": 6 - 3 * k, "B": 3 * k - 6, "C": 3 * (k - 6)}
    v = next(L for L, x in opts.items() if x == 3 * k - 6)
    assert v == "B" and len(set(opts.values())) == 3
    qs.append(Q("Which expression means 6 less than 3 times k? A:\u00a06\u00a0–\u00a03k  B:\u00a03k\u00a0–\u00a06  C:\u00a03(k\u00a0–\u00a06) "
                "Write A, B or C.", v, [v], False,
                "3 times k is 3k. 6 less than that takes 6 away from 3k: 3k – 6", "g6expr_id"))
    pa, pb = D(9) / 5, D(5) / 3
    v = "A" if pa < pb else "B"
    assert v == "B"
    qs.append(Q("Store A: 5 notebooks cost $9. Store B: 3 notebooks cost $5. Which store is cheaper "
                "per notebook? Write A or B.", v, [v], False,
                f"One notebook: A {usd(pa)}, B {usd(pb)}. B is cheaper per notebook", "g6unitprice"))
    pair = "(3, 5)"
    qs.append(Q("The point (3, –5) is reflected across the x-axis. Write the new point.", pair,
                [pair, "(3,5)", "3, 5", "3,5"], False,
                "Reflecting across the x-axis flips the sign of y only: (3, –5) goes to (3, 5)", "g6reflect"))
    v = 3 * (8 + 5) - 4
    qs.append(Q("Work out 3 × (8 + 5) – 4", str(v), [str(v)], False,
                "Parentheses first: 8 + 5 = 13. Then 3 × 13 = 39, – 4 = 35", "g5paren"))
    equal_sides = 3
    v = "yes" if equal_sides >= 2 else "no"
    qs.append(Q("An isosceles triangle has at least 2 equal sides. An equilateral triangle has 3 equal "
                "sides. Is every equilateral triangle also isosceles? Write yes or no.", v, [v], False,
                "3 equal sides includes at least 2 equal sides, so yes", "g5triclass"))
    total = F(7, 2) * F(9, 4)
    assert total == F(63, 8) and F(7, 2) + F(9, 4) != total and F(9, 4) / F(7, 2) != total
    v = "A"
    qs.append(Q("A jar holds 2\u00a01/4 liters. Which equation gives t, the liters in 3\u00a01/2 jars? "
                "A:\u00a0t\u00a0=\u00a03\u00a01/2\u00a0×\u00a02\u00a01/4 B:\u00a0t\u00a0=\u00a03\u00a01/2\u00a0+\u00a02\u00a01/4 C:\u00a0t\u00a0=\u00a02\u00a01/4\u00a0÷\u00a03\u00a01/2 Write A, B or C.",
                v, [v], False,
                f"Total = number of jars × liters in each: t = 3 1/2 × 2 1/4, which is {mixed(total)} liters",
                "g5fmuleq"))
    v = "5³"
    assert 5 * 5 * 5 == 5 ** 3
    qs.append(Q("Write 5 × 5 × 5 using an exponent.", v, [v, "5^3"], False,
                "5 is multiplied by itself 3 times: 5³", "g6expwrite"))
    forms = ["3(2x + 5)", "3(2x+5)", "3 × (2x + 5)", "3×(2x+5)", "(2x + 5) × 3", "(2x+5)×3"]
    _expr_ok(forms, 3 * (2 * 4 + 5), x=4)
    import math
    assert math.gcd(6, 15) == 3
    qs.append(Q("Factor 6x + 15 using the greatest common factor of 6 and 15.", forms[0], forms, False,
                "The greatest common factor is 3. 6x = 3 × 2x and 15 = 3 × 5, so 3(2x + 5)", "g6factor"))
    return qs


def test_ay():
    qs = []
    plot = {"kind": "lineplot", "denominator": 4, "max": 1, "caption": "weight of each parcel (kg)",
            "values": {"1/4": 2, "1/2": 3, "3/4": 1, "1": 1}}
    vals = {F(k): n for k, n in plot["values"].items()}
    v = sum(k * n for k, n in vals.items())
    qs.append(Q("Every parcel goes on one scale. How much do they weigh in all?",
                f"{mixed(v)} kg", [f"{mixed(v)} kg", f"{frac(v)} kg"], True,
                "2 × 1/4 + 3 × 1/2 + 3/4 + 1 = 1/2 + 1 1/2 + 3/4 + 1 = 3 3/4 kg", "g5lineplot", "kg", figure=plot))
    v = 6 * 5 * 4 + 8 * 3 * 2
    qs.append(Q("A box 6 cm by 5 cm by 4 cm sits on top of a box 8 cm by 3 cm by 2 cm. "
                "What is their total volume?", f"{v} cm³",
                [f"{v} cm³", f"{v} cm3", f"{v} cubic cm"], True,
                "120 cm³ + 48 cm³; volumes are always in cubic units", "g5vol_add", "cm³"))
    qs.append(Q("Going up 40 m is written as +40. How is going down 25 m written?", "–25",
                ["–25", "-25", "–25 m", "-25 m"], False,
                "Down is the opposite direction from up, so it takes the opposite sign: –25", "g6opposite"))
    import math
    v = math.lcm(6, 8)
    qs.append(Q("What is the least common multiple of 6 and 8?", str(v), [str(v)], False,
                "Multiples of 8: 8, 16, 24. 24 is also a multiple of 6. 48 is shared too, but larger",
                "g6lcm"))
    v = abs(3 - (-6))
    qs.append(Q("Point A is at (2, –6) and point B is at (2, 3). How far apart are A and B?",
                str(v), [str(v), f"{v} units"], False,
                "Same x, on opposite sides of the x-axis: 6 down to 0, then 3 up; 6 + 3 = 9", "g6quad4"))
    v = F(25, 6) - F(13, 8)
    assert v == F(61, 24)
    qs.append(Q("Work out 4 1/6 – 1 5/8", mixed(v), [mixed(v), frac(v)], False,
                "Twenty-fourths: 4 4/24 = 3 28/24; 3 28/24 – 1 15/24 = 2 13/24", "g5mixsub"))
    qs.append(Q("Which measures the space a box takes up: its area, its perimeter or its volume?",
                "volume", ["volume", "its volume"], False,
                "Volume measures the space inside a solid. Area and perimeter describe flat shapes",
                "g5volspace"))
    a, b, c = 3, 18, 7
    v = a * (b + c) // (b + c)
    qs.append(Q("Without working it out: 3 × (18 + 7) is how many times as large as 18 + 7?",
                str(v), [str(v), f"{v} times"], False,
                "It is 3 groups of (18 + 7), so 3 times as large, whatever the sum is", "g5exprread"))
    forms = ["a + 7", "a+7", "(a + 7)", "(a+7)", "7 + a", "7+a"]
    _expr_ok(forms, 2 + 7, a=2)
    qs.append(Q("In 3(a + 7), which part is treated as one quantity and multiplied by 3?",
                forms[0], forms, False, "The parentheses hold a + 7 together as one quantity", "g6entity"))
    n = 4
    v = "yes" if 2 * (n + 3) == 2 * n + 3 else "no"
    assert v == "no"
    qs.append(Q("Try n = 4 in 2(n + 3) and in 2n + 3. Are the two expressions equivalent? "
                "Write yes or no.", v, [v], False,
                "2(4 + 3) = 14 but 2 × 4 + 3 = 11. Different values, so not equivalent", "g6equivsub"))
    return qs


def test_az():
    qs = []
    v = F(3, 8) + F(-9, 4) - F(5, 8)
    assert v == F(-5, 2)
    qs.append(Q("Work out 3/8 + (–2 1/4) – 5/8", f"–{mixed(-v)}", [f"–{mixed(-v)}", f"-{mixed(-v)}"],
                False, "3/8 – 5/8 = –2/8 = –1/4. Then –1/4 + (–2 1/4) = –2 1/2", "g7ratmix"))
    eq = ["p = 7h", "p=7h", "p = 7 × h", "p=7×h", "p = h × 7"]
    _expr_ok([e.split("=")[1] for e in eq], 7 * 3, h=3)
    assert all(7 * h == p for h, p in ((1, 7), (2, 14), (3, 21)))
    qs.append(Q("Hours h: 1, 2, 3. Pay p: $7, $14, $21. Write an equation for the pay p after h hours.",
                eq[0], eq, False, "Each hour adds $7, and the pay depends on the hours: p = 7h", "g6deptable"))
    assert F(3, 4) / F(1, 8) == 6
    v = "A"
    qs.append(Q("Which question does 3/4 ÷ 1/8 answer? A: How many 1/8s are in 3/4? "
                "B: What is 1/8 of 3/4? Write A or B.", v, [v], False,
                "Dividing asks how many of the second fit in the first: six 1/8s are in 3/4. "
                "1/8 of 3/4 would be multiplying", "g6fdivread"))
    forms = ["y < 20", "y<20", "20 > y", "20>y"]
    qs.append(Q("Write an inequality for: the number y is less than 20.", forms[0], forms, False,
                "Less than uses <, with the letter y and no equals sign: y < 20", "g6ineqmath"))
    v = 14 * 18 - 100
    qs.append(Q("A farm packs 14 boxes with 18 apples in each box and sells 100 apples. How many "
                "apples are left?", str(v), [str(v), f"{v} apples"], False,
                "14 × 18 = 252 apples; 252 – 100 = 152", "g4multi_plain"))
    qs.append(Q("All polygons have only straight sides. A hexagon is a polygon. Does a hexagon have "
                "only straight sides? Write yes or no.", "yes", ["yes"], False,
                "What is true of every polygon is true of each kind of polygon", "g5shapeattr2"))
    lo = 17 // 5
    v = f"{lo} and {lo + 1}"
    assert lo < F(17, 5) < lo + 1
    qs.append(Q("17/5 is between which two whole numbers?", v,
                [v, f"{lo}, {lo + 1}", f"{lo},{lo + 1}", f"{lo + 1} and {lo}"], False,
                "17 ÷ 5 = 3 remainder 2, so 17/5 = 3 2/5, between 3 and 4", "g5fbetween"))
    a, b = (2, 4, 6), (8, 16, 24)
    v = b[0] // a[0]
    assert all(y == v * x for x, y in zip(a, b))
    qs.append(Q("Pattern A: 0, 2, 4, 6. Pattern B: 0, 8, 16, 24. Each term in B is how many times "
                "the matching term in A?", str(v), [str(v), f"{v} times"], False,
                "2 × 4 = 8, 4 × 4 = 16, 6 × 4 = 24, so 4 times", "g5patrel"))
    v = 3 + 2 * 8
    qs.append(Q("A taxi costs 3 + 2m dollars for m miles. How much is a ride of 8 miles?",
                f"${v}", [f"${v}", str(v), f"${v}.00"], False,
                "m = 8: 2 × 8 = 16 first, then 3 + 16 = $19", "g6evalreal"))
    x = 7
    v = "yes" if x + 5 > 11 else "no"
    qs.append(Q("Does x = 7 make x + 5 > 11 true? Write yes or no.", v, [v], False,
                "7 + 5 = 12, and 12 is greater than 11, so yes", "g6substineq"))
    return qs


# Tests BA, BB and BC are one batch from `skills.py --plan --sheets 3` after AX, AY
# and AZ were marked. The plan now names the component to aim at (a failing one,
# else one never asked), so each of the 30 questions is tagged with exactly that
# component in a new skill key (see SK.update below).
def test_ba():
    qs = []
    v = round(F(49, 8)) - round(F(23, 8))
    assert v == 3
    qs.append(Q("Estimate 6 1/8 – 2 7/8 by rounding each number to the nearest whole number.",
                str(v), [str(v)], False, "6 1/8 is nearly 6 and 2 7/8 is nearly 3: 6 – 3 = 3", "g5fbench_sub"))
    qs.append(Q("A pay table: 1 hour pays $9, 2 hours pay $18, 3 hours pay $27, 4 hours pay $36. "
                "Which equation matches, with p for pay and h for hours? A: p = h + 8  B: p = 9h  "
                "C: h = 9p. Write A, B or C.", "B", ["B"], False,
                "Each hour adds $9, so pay is 9 times the hours: p = 9h", "g6tableeq"))
    qs.append(Q("Which equation gives s, the number of 3/4-cup servings in 4 1/2 cups? A: s = 4 1/2 × 3/4  "
                "B: s = 4 1/2 ÷ 3/4  C: s = 3/4 ÷ 4 1/2. Write A, B or C.", "B", ["B"], False,
                "How many 3/4s fit in 4 1/2: divide 4 1/2 by 3/4", "g6fdiveq"))
    qs.append(Q("A triangle has sides 5 cm, 5 cm and 5 cm. Is it an isosceles triangle (at least 2 "
                "equal sides)? Write yes or no.", "yes", ["yes", "Yes"], False,
                "All three sides are equal, so at least two are: yes", "g5tri"))
    v = F(9, 4)
    qs.append(Q("9 pies are shared equally among 4 friends. How much pie does each friend get?",
                mixed(v), [mixed(v), frac(v), f"{mixed(v)} pies", "2.25"], False,
                "9 ÷ 4 = 9/4 = 2 1/4", "g5divfrac"))
    qs.append(Q("Tickets cost $6 each. Mia pays $42 in all for t tickets. Which equation fits? "
                "A: t + 6 = 42  B: 6t = 42  C: t = 42 × 6. Write A, B or C.", "B", ["B"], False,
                "Cost = price × number of tickets: 6t = 42", "g6eqrep_px"))
    v = F(7, 2) * 4
    qs.append(Q("A fish tank has a base of 3 1/2 m² and is 4 m tall. Use V = b × h to find its volume.",
                f"{v} m³", [f"{v} m³", f"{v} m3", f"{v} cubic m"], True,
                "Base area × height: 3 1/2 × 4 = 14 cubic meters", "g6volbh", "m³"))
    qs.append(Q("What is the opposite of 0?", "0", ["0", "zero"], False,
                "0 is its own opposite", "g6zeroopp"))
    v = F(12, 3)
    qs.append(Q("A car goes 12 miles in 3 hours at a steady rate. Write this as a unit rate in miles "
                "per hour.", str(v), [str(v), f"{v} miles", f"{v} mi", f"{v} miles per hour", f"{v} mph"], False,
                "12 ÷ 3 = 4 miles for each 1 hour", "g6unitrate_ab"))
    v = D(80) * D("0.35")
    qs.append(Q("What is 35% of 80?", dec(v), [dec(v)], False,
                "10% of 80 is 8, so 30% is 24 and 5% is 4: 28", "g6pct_of"))
    return qs


def test_bb():
    qs = []
    plot = {"kind": "lineplot", "denominator": 4, "max": 1, "caption": "length of each rope (m)",
            "values": {"1/4": 2, "1/2": 2, "3/4": 3, "1": 1}}
    vals = {F(k): n for k, n in plot["values"].items()}
    v = sum(k * n for k, n in vals.items() if k > F(1, 2))
    qs.append(Q("What is the total length of only the ropes that are longer than 1/2 m?",
                f"{mixed(v)} m", [f"{mixed(v)} m", f"{frac(v)} m"], True,
                "Ropes longer than 1/2 m: three of 3/4 and one of 1: 9/4 + 1 = 3 1/4 m",
                "g5lineplot", "m", figure=plot))
    qs.append(Q("Which phrase describes 4n + 3? A: 4 more than 3 times n  B: 3 more than 4 times n  "
                "C: 4 times the sum of n and 3. Write A, B or C.", "B", ["B"], False,
                "4n is 4 times n, and + 3 adds 3: 3 more than 4 times n", "g6exprphrase"))
    pair = "(4, 7)"
    qs.append(Q("The point (–4, 7) is reflected across the y-axis. Write the new point.", pair,
                [pair, "(4,7)", "4, 7", "4,7"], False,
                "Reflecting across the y-axis flips the sign of x only: (–4, 7) goes to (4, 7)",
                "g6reflect"))
    v = 5 + 4 * 6
    qs.append(Q("Renting a bike costs 5 + 4h dollars for h hours. How much does it cost for 6 hours?",
                f"${v}", [f"${v}", str(v), f"{v} dollars"], False,
                "Put h = 6: 5 + 4 × 6 = 5 + 24 = 29", "g6evalrw"))
    forms = ["m – 4", "m-4", "(m – 4)", "(m-4)", "m − 4"]
    qs.append(Q("In 6(m – 4), which part is treated as one quantity and multiplied by 6?", forms[0],
                forms, False, "The parentheses group m – 4 into one quantity", "g6oneentity"))
    qs.append(Q("Does the inequality x > 5 have exactly one solution or infinitely many solutions? "
                "Write one or infinitely many.", "infinitely many",
                ["infinitely many", "infinite", "infinitely many solutions", "Infinitely many"], False,
                "6, 7, 8, 6.5, 100 ... every number above 5 works, so there is no end", "g6inf"))
    v = D(18) / D("0.45")
    qs.append(Q("Work out 18 ÷ 0.45", dec(v), [dec(v)], False,
                "Multiply both by 100: 1800 ÷ 45 = 40", "g6divdecwhole"))
    qs.append(Q("An account balance is –$80. How many dollars does the owner owe?", "$80",
                ["$80", "80", "80 dollars"], False,
                "The amount owed is the size of the balance: |–80| = 80", "g6absreal"))
    v = F(21, 3) * 7
    qs.append(Q("The ratio of x to y is 3 : 7. If x is 21, what is y?", str(v), [str(v)], False,
                "21 is 7 times 3, so y is 7 × 7 = 49", "g6ratiomath"))
    v = D("3.4") * D("2.5")
    qs.append(Q("Work out 3.4 × 2.5", dec(v), [dec(v), "8.50"], False,
                "34 × 25 = 850, with two decimal places: 8.50 = 8.5", "g5decmul"))
    return qs


def test_bc():
    qs = []
    v = F(-9, 4) + 5 - F(7, 4)
    assert v == 1
    qs.append(Q("Work out –2 1/4 + 5 – 1 3/4", str(v), [str(v)], False,
                "Combine the fractions: –2 1/4 – 1 3/4 = –4. Then –4 + 5 = 1", "g7addsub"))
    qs.append(Q("A rope is 2 1/2 m long. Maya uses 3/5 of it. Let u be the meters she uses. Which "
                "equation fits? A: u = 3/5 + 2 1/2  B: u = 3/5 × 2 1/2  C: u = 2 1/2 ÷ 3/5. "
                "Write A, B or C.", "B", ["B"], False,
                "3/5 of the rope means 3/5 times the length", "g5fmuleq"))
    forms = ["8(2a + 3)", "8 × (2a + 3)", "8(2a+3)", "8×(2a+3)", "(2a + 3) × 8", "(2a+3)×8"]
    _expr_ok(forms, 16 * 5 + 24, a=5)
    qs.append(Q("Factor 16a + 24 using the greatest common factor of 16 and 24.", forms[0], forms, False,
                "GCF is 8: 16a = 8 × 2a and 24 = 8 × 3, so 8(2a + 3)", "g6factor"))
    qs.append(Q("A bottle is full of water. Which measures how much space the water takes up: "
                "height, surface area or volume?", "volume", ["volume", "Volume"], False,
                "Space taken up is volume", "g5volspace"))
    qs.append(Q("Does n = 5 make 3n = 18 true? Write yes or no.", "no", ["no", "No"], False,
                "3 × 5 = 15, not 18: no", "g6substeq"))
    v = 6 * 4 + 3 * 2
    qs.append(Q("An L-shape is made by joining a 6 by 4 rectangle and a 3 by 2 rectangle side by "
                "side without overlap. What is its total area?", str(v), [str(v), f"{v} square units"],
                False, "6 × 4 = 24 and 3 × 2 = 6; 24 + 6 = 30", "g6areapoly"))
    forms = ["9(2 + 3)", "9(2+3)", "9 × (2 + 3)", "9×(2+3)", "(2 + 3) × 9", "(2+3)×9"]
    assert 9 * (2 + 3) == 18 + 27
    qs.append(Q("Write 18 + 27 as a number times a sum of two numbers that have no common factor.",
                forms[0], forms, False, "GCF of 18 and 27 is 9: 18 + 27 = 9 × 2 + 9 × 3 = 9(2 + 3)",
                "g6gcfsum"))
    qs.append(Q("The ratio of cats to dogs is 2 : 3. Which ratio is equivalent: 4:5, 6:9 or 5:8? "
                "Write the ratio.", "6:9", ["6:9", "6 : 9", "6 to 9"], False,
                "Multiply both by 3: 2 : 3 = 6 : 9", "g6equivratio"))
    fa, fb = F(2, 3), F(3, 5)
    v = "A" if fa > fb else "B"
    qs.append(Q("Recipe A: 2 cups flour for 3 cups milk. Recipe B: 3 cups flour for 5 cups milk. "
                "Which recipe has more flour for each cup of milk? Write A or B.", v, [v], False,
                "Flour per cup of milk: A 2/3 = 10/15, B 3/5 = 9/15. A has more", "g6tablecmp"))
    qs.append(Q("In 7.66, the 6 in the tenths place is worth how many times the 6 in the hundredths "
                "place?", "10", ["10", "10 times", "ten"], False,
                "Each place is 10 times the place to its right", "g5pv10"))
    return qs


SK.update({
    "g6tableeq": ("Relate a table of values to an equation for the dependent variable", "6.EE.C.9",
                  ["d29c0749-bd31-5ad3-8a3c-2a24769df8ce"]),
    "g6fdiveq": ("Choose the equation for a fraction-division word problem", "6.NS.A.1",
                 ["b15981ec-6234-523c-999c-93ce61149102"]),
    "g5tri": ("Classify triangles in a hierarchy based on properties", "5.G.B.4",
              ["8bd3a000-9afe-577e-8781-dd8b8d493289"]),
    "g5divfrac": ("Whole-number division with a fraction or mixed-number answer", "5.NF.B.3",
                  ["26645597-c6a9-5497-b3a2-63f304ab1de1", "46b4aaee-e89d-53f0-abd9-12b676510c8e"]),
    "g6eqrep_px": ("Represent a real-world problem with px = q", "6.EE.B.7",
                   ["8d29194f-94ec-51fa-b0c7-fc6d99780d3b"]),
    "g6volbh": ("Volume with V = bh and a fractional edge, real-world", "6.G.A.2",
                ["0bbc7349-8768-5a94-8461-b718a4547301"]),
    "g6zeroopp": ("Zero is its own opposite", "6.NS.C.6.a", ["4c975388-0779-5402-ac2e-eda40bc3a324"]),
    "g6unitrate_ab": ("Write a ratio a:b as a unit rate a/b", "6.RP.A.2",
                      ["db4c25ad-9892-5abb-bcba-2fc9781d10f8"]),
    "g6exprphrase": ("Identify a phrase that describes a given expression", "6.EE.A.2.a",
                     ["ced6fc6b-dfd9-56c0-b8b2-7f7c72b8bfc7"]),
    "g6evalrw": ("Evaluate an expression at a value in a real-world context", "6.EE.A.2.c",
                 ["06806313-cfe4-5d7d-9646-fdcf8520cadf"]),
    "g6oneentity": ("View part of an expression as a single entity", "6.EE.A.2.b",
                    ["1ca4a9fc-2a7b-50b8-b67a-3b850141a649"]),
    "g6inf": ("Inequalities x > c have infinitely many solutions", "6.EE.B.8",
              ["94bdf387-6027-5bfe-a80f-9080e4299330"]),
    "g6divdecwhole": ("Divide a whole number by a multi-digit decimal", "6.NS.B.3",
                      ["95700724-a655-5092-ae09-41e4ed0b48c2"]),
    "g6absreal": ("Interpret absolute value as magnitude in a real-world situation", "6.NS.C.7.c",
                  ["8ef052eb-6878-5613-b9fd-3efd396d368c"]),
    "g6ratiomath": ("Solve a mathematical problem with ratio and rate reasoning", "6.RP.A.3",
                    ["c869a6c1-ffed-596f-a64f-6bffdd8faf92"]),
    "g7addsub": ("Use properties of operations to add and subtract rational numbers", "7.NS.A.1.d",
                 ["ce4afd4b-6f1d-5d6f-83df-ac9b90a40250"]),
    "g5fmuleq": ("Use an equation for a fraction-multiplication word problem", "5.NF.B.6",
                 ["ea894526-30b5-50a6-b312-6b4cfe38d624"]),
    "g6factor": ("Apply the distributive property to factor simple expressions", "6.EE.A.3",
                 ["8819fa6b-bd86-58b7-badd-df03a195db74"]),
    "g5volspace": ("Volume is the space an object takes up", "5.MD.C.3",
                   ["af5ac1f9-631b-583e-a202-f436b2c6065f"]),
    "g6substeq": ("Substitute to test a one-variable, one-step equation", "6.EE.B.5",
                  ["25259f33-13ce-5339-a53a-11e0a2ffd95f"]),
    "g6areapoly": ("Find the area of a polygon by composing rectangles", "6.G.A.1",
                   ["5a75b6d4-a3f4-5ff8-bf12-f81ff5586042"]),
    "g6gcfsum": ("Use the distributive property to write a sum as a multiple of a sum", "6.NS.B.4",
                 ["c587f727-0135-571c-8c60-7ad46e0a28c5"]),
    "g6equivratio": ("Use equivalent ratios to represent a relationship", "6.RP.A.1",
                     ["ff25751a-4675-50fe-ab86-bbaaffdda1dd"]),
    "g6tablecmp": ("Use tables of ratios to compare ratios", "6.RP.A.3.a",
                   ["05492c78-5bc3-51f2-890d-92283c0d1c00"]),
})


# Tests BD, BE and BF are one batch from `skills.py --plan --sheets 3` after BA, BB
# and BC were marked. The plan returned 22 picks (14 failures, 8 coverage) for 30
# questions, so eight extras go to the weakest standards, each on a different
# component than the plan pick. Every question is tagged with the component the plan
# named (a failing `aim at`, else one never asked).
def test_bd():
    qs = []
    plot = {"kind": "lineplot", "denominator": 4, "max": 1, "caption": "length of each rope (m)",
            "values": {"1/4": 1, "1/2": 3, "3/4": 2, "1": 2}}
    vals = {F(k): n for k, n in plot["values"].items()}
    v = sum(k * n for k, n in vals.items() if k >= F(3, 4))
    qs.append(Q("What is the total length of only the ropes that are 3/4 m or longer?",
                f"{mixed(v)} m", [f"{mixed(v)} m", f"{frac(v)} m"], True,
                "Ropes 3/4 m or longer: two of 3/4 and two of 1: 1 1/2 + 2 = 3 1/2 m",
                "g5lineplot", "m", figure=plot))
    qs.append(Q("Jan runs 3/4 of a 5 1/2 km trail. Let d be the km she runs. Which equation fits? "
                "A: d = 3/4 + 5 1/2  B: d = 3/4 × 5 1/2  C: d = 5 1/2 ÷ 3/4. Write A, B or C.",
                "B", ["B"], False, "3/4 of the trail means 3/4 times the length", "g5fmuleq"))
    qs.append(Q("The points (5, –2) and (–5, –2) are reflections of each other. Across which axis? "
                "Write x-axis or y-axis.", "y-axis", ["y-axis", "y axis", "the y-axis", "Y-axis"], False,
                "The y-coordinate stays the same and x changes sign: reflected across the y-axis",
                "g6reflect"))
    v = D(27) / D("0.45")
    qs.append(Q("Work out 27 ÷ 0.45", dec(v), [dec(v)], False,
                "Multiply both by 100: 2700 ÷ 45 = 60", "g6divdecwhole"))
    qs.append(Q("Every equilateral triangle has 3 equal sides. Does every equilateral triangle have "
                "at least 2 equal sides? Write yes or no.", "yes", ["yes", "Yes"], False,
                "3 equal sides includes at least 2 equal sides: yes", "g5tri"))
    v = 8 * 5 + 3 * 4
    qs.append(Q("A garden is made by joining an 8 m by 5 m rectangle and a 3 m by 4 m rectangle "
                "side by side. What is its area?", f"{v} m²", [f"{v} m²", f"{v} m2", f"{v} square m",
                                                             f"{v} square meters"], True,
                "8 × 5 = 40 and 3 × 4 = 12; 40 + 12 = 52 square meters", "g6areapolyrw", "m²"))
    qs.append(Q("A cyclist rides 150 miles in 3 hours. Which describes the rate? A: 50 miles for "
                "each hour  B: 50 hours for each mile. Write A or B.", "A", ["A"], False,
                "150 ÷ 3 = 50 miles in 1 hour", "g6ratelang"))
    qs.append(Q("Which single number tells how spread out a data set is: mean, median or range?",
                "range", ["range", "Range"], False,
                "The range, greatest minus least, describes the spread", "g6variation"))
    plot2 = {"kind": "lineplot", "denominator": 8, "max": 1, "caption": "length of each strip (m)",
             "values": {"1/8": 1, "1/4": 1, "1/2": 3, "7/8": 1}}
    vals2 = {F(k): n for k, n in plot2["values"].items()}
    v = max(vals2) - min(vals2)
    qs.append(Q("How much longer is the longest strip than the shortest?",
                f"{mixed(v)} m", [f"{mixed(v)} m", f"{frac(v)} m"], True,
                "Longest 7/8 m, shortest 1/8 m: 7/8 – 1/8 = 6/8 = 3/4 m", "g5lineplot", "m", figure=plot2))
    px, py = 7, -3
    quad = 1 if px > 0 and py > 0 else 2 if px < 0 < py else 3 if px < 0 and py < 0 else 4
    qs.append(Q("In which quadrant is the point (7, –3)? Write 1, 2, 3 or 4.", str(quad),
                [str(quad), f"quadrant {quad}", f"Quadrant {quad}"], False,
                "x is positive (right), y is negative (down): quadrant 4", "g6quadrant"))
    return qs


def test_be():
    qs = []
    v = -F(7, 2) + 6 - F(5, 2)
    assert v == 0
    qs.append(Q("Work out –3 1/2 + 6 – 2 1/2", str(v), [str(v)], False,
                "Combine the fractions: –3 1/2 – 2 1/2 = –6. Then –6 + 6 = 0", "g7addsub"))
    qs.append(Q("A jug holds 3 1/2 liters. Each glass takes 1/2 liter. Let g be the number of glasses. "
                "Which equation fits? A: g = 3 1/2 × 1/2  B: g = 3 1/2 ÷ 1/2  C: g = 3 1/2 + 1/2. "
                "Write A, B or C.", "B", ["B"], False,
                "How many 1/2s fit in 3 1/2: divide", "g6fdiveq"))
    forms = ["6(2x + 3)", "6 × (2x + 3)", "6(2x+3)", "6×(2x+3)", "(2x + 3) × 6", "(2x+3)×6"]
    _expr_ok(forms, 12 * 4 + 18, x=4)
    qs.append(Q("Factor 12x + 18 using the greatest common factor of 12 and 18.", forms[0], forms, False,
                "GCF is 6: 12x = 6 × 2x and 18 = 6 × 3, so 6(2x + 3)", "g6factor"))
    v = 9 + 3 * 7
    qs.append(Q("A taxi costs 9 + 3m dollars for m miles. How much is a ride of 7 miles?",
                f"${v}", [f"${v}", str(v), f"{v} dollars"], False,
                "Put m = 7: 9 + 3 × 7 = 9 + 21 = 30", "g6evalrw"))
    qs.append(Q("A box is filled with sand. Which tells how much space the sand takes up: its "
                "weight, its surface or its volume?", "volume", ["volume", "Volume"], False,
                "Space taken up is volume", "g5volspace"))
    v = F(1, 2) * F(3, 4) * 4
    qs.append(Q("A prism is 1/2 long, 3/4 wide and 4 tall. What is its volume in cubic units?",
                mixed(v), [mixed(v), frac(v), f"{mixed(v)} cubic units", f"{mixed(v)} units³"], False,
                "1/2 × 3/4 = 3/8; 3/8 × 4 = 12/8 = 1 1/2", "g6volmath"))
    qs.append(Q("There are 3 feet in 1 yard. To change 7 yards into feet, do you multiply or divide by 3? "
                "Write multiply or divide.", "multiply", ["multiply", "Multiply", "times"], False,
                "Feet are smaller than yards, so there are more of them: 7 × 3 = 21 feet",
                "g6convfactor"))
    v = F(10, 3) + F(-29, 6) + F(-5, 6)
    assert v == F(-7, 3)
    qs.append(Q("Work out 3 1/3 + (–4 5/6) + (–5/6)", f"–{mixed(-v)}", [f"–{mixed(-v)}", f"-{mixed(-v)}"],
                False, "Negatives together: –4 5/6 – 5/6 = –5 2/3. Then 3 1/3 – 5 2/3 = –2 1/3", "g7rat"))
    forms = ["7x + 5", "7x+5", "5 + 7x", "5+7x"]
    _expr_ok(forms, 3 * 2 + 5 + 4 * 2, x=2)
    qs.append(Q("Write 3x + 5 + 4x in its simplest form.", forms[0], forms, False,
                "Combine like terms: 3x + 4x = 7x, so 7x + 5", "g6combine"))
    v = F(5, 2) / F(5, 6)
    qs.append(Q("How many 5/6-m pieces can be cut from a ribbon 2 1/2 m long?", str(v),
                [str(v), f"{v} pieces"], False,
                "2 1/2 = 5/2, and 5/2 ÷ 5/6 = 5/2 × 6/5 = 3", "g6fdivword"))
    return qs


def test_bf():
    qs = []
    v = 4 * 7
    qs.append(Q("A plant's height h (cm) after w weeks: week 1 is 4, week 2 is 8, week 3 is 12. What "
                "is h at week 7?", str(v), [str(v), f"{v} cm"], False,
                "It grows 4 each week, so h = 4w: 4 × 7 = 28", "g6depmodel"))
    import math
    g = math.gcd(24, 40)
    forms = [f"{g}(3 + 5)", f"{g} × (3 + 5)", f"{g}(3+5)", f"{g}×(3+5)", "(3 + 5) × 8", "(3+5)×8"]
    assert g * (3 + 5) == 24 + 40
    qs.append(Q("Write 24 + 40 as a number times a sum of two numbers that have no common factor.",
                forms[0], forms, False, "GCF of 24 and 40 is 8: 24 + 40 = 8 × 3 + 8 × 5 = 8(3 + 5)",
                "g6gcfsum"))
    qs.append(Q("Does x < 12 have exactly one solution or infinitely many solutions? Write one or "
                "infinitely many.", "infinitely many",
                ["infinitely many", "infinite", "infinitely many solutions", "Infinitely many"], False,
                "11, 10, 0, –5, 3.5 ... every number below 12 works", "g6inf"))
    v = D(120) * D("0.15")
    qs.append(Q("What is 15% of 120?", dec(v), [dec(v)], False,
                "10% of 120 is 12 and 5% is 6: 18", "g6pct_of"))
    qs.append(Q("A bag holds 4 kg of rice. Ana has r bags and 36 kg of rice in all. Which equation "
                "fits? A: r + 4 = 36  B: 4r = 36  C: r = 36 × 4. Write A, B or C.", "B", ["B"], False,
                "Bags × 4 kg each = 36: 4r = 36", "g6eqrep_px"))
    qs.append(Q("On a number line, are 7 and –7 on the same side of 0 or on opposite sides? Write "
                "same or opposite.", "opposite", ["opposite", "opposite sides", "Opposite"], False,
                "–7 is left of 0 and 7 is right of 0: opposite sides", "g6oppsides"))
    qs.append(Q("A data set has most values low and a few very high values. Is it skewed left or "
                "skewed right? Write left or right.", "right", ["right", "skewed right", "Right"], False,
                "The long tail is on the high side, so it is skewed right", "g6skew"))
    eq = ["c = 8n", "c=8n", "c = 8 × n", "c=8×n", "c = n × 8"]
    _expr_ok([e.split("=")[1] for e in eq], 8 * 3, n=3)
    qs.append(Q("A cinema ticket costs $8. Write an equation for the cost c of n tickets.", eq[0], eq,
                False, "The cost depends on the tickets: c = 8n", "g6depvar"))
    v = math.gcd(54, 72)
    qs.append(Q("What is the greatest common factor of 54 and 72?", str(v), [str(v)], False,
                "54 ÷ 18 = 3 and 72 ÷ 18 = 4, and nothing larger divides both. 6 and 9 are shared "
                "but smaller", "g6gcf"))
    v = F(5, 6) * F(18, 5)
    qs.append(Q("A pipe is 3 3/5 m long. A piece 5/6 of its length is cut off. How long is the piece?",
                f"{mixed(v)} m", [f"{mixed(v)} m"], True,
                "5/6 × 18/5 = 90/30 = 3 m", "g5fmulword", "m"))
    return qs


SK.update({
    "g6areapolyrw": ("Find the area of a polygon by composing rectangles, real-world", "6.G.A.1",
                     ["68e69e23-c527-5dbc-b54a-7e1d0b1115fb"]),
    "g6ratelang": ("Use rate language in the context of a ratio relationship", "6.RP.A.2",
                   ["523d04e7-47d8-55c7-bc44-792f3e01bfda"]),
    "g6variation": ("The variation of a data set can be described with a single number", "6.SP.A.3",
                    ["d6f0d3bc-e9a8-5d0c-ae9e-f04c04660fad"]),
    "g6volmath": ("Volume with V = lwh and fractional edges, mathematical", "6.G.A.2",
                  ["e270cd96-fc42-5768-93ac-81c1a7e74069"]),
    "g6convfactor": ("Use ratios as conversion factors", "6.RP.A.3.d",
                     ["534e2e4c-8189-515f-9241-1b4c011556a7"]),
    "g6combine": ("Combine like terms to generate an equivalent expression", "6.EE.A.3",
                  ["e1d1c595-427d-5dcd-a1e3-8e37184e2a64"]),
    "g6depmodel": ("Model a relationship between variables to solve a real-world problem", "6.EE.C.9",
                   ["3435b2aa-520a-583e-9fbf-47110867a9de"]),
    "g6oppsides": ("Opposite signs are on opposite sides of 0 on the number line", "6.NS.C.6.a",
                   ["22156372-ad11-5837-9b62-4489288590bb"]),
    "g6skew": ("Recognize a distribution that is skewed left or right", "6.SP.A.2",
               ["24b6a84f-6d61-5663-986d-2494dcef865a"]),
})


SK.update({
    "g7ineqcon": ("Construct a simple inequality for a real-world problem", "7.EE.B.4",
                  ["7c6deb43-5973-5923-8c6e-e5d29adbaba1"]),
    "g6eqsolve_xp_rw": ("Solve a real-world problem with x + p = q", "6.EE.B.7",
                        ["cd69a8c5-90aa-5e64-9abf-112fa7051095"]),
    # Word g6distone questions as BH7 did ("one number or many numbers?"). "How many
    # numbers does the median/mean use" is ambiguous - it also reads as how many values
    # the statistic is computed from - and voided BJ6 and BM4.
    "g6distone": ("The distribution of a data set can be described with a single number", "6.SP.A.3",
                  ["f6b991bd-d534-5502-9a22-b0bc2f095797"]),
    "g6trimath": ("Find the area of a triangle, mathematical", "6.G.A.1",
                  ["c2509042-cd73-5665-88f3-317d399b8e9d"]),
    "g6commute": ("Use the commutative property to combine like terms", "6.EE.A.3",
                  ["a629106a-c48e-5417-a29e-68ab652c8c5d"]),
})


# Tests BG, BH and BI are one batch from `skills.py --plan --sheets 3` after BD, BE and
# BF were marked. The plan returned 27 picks for 30 questions, so each sheet gets one
# extra on a weak standard, on a different component than its plan pick. Two picks were
# retargeted after reading the diagnoses: 5.MD.B.2 misses are almost all units-only, so
# the line plot asks for an equal share instead of another sum; 6.G.A.1's polygon miss
# was units-only, so it aims at the never-asked triangle component, where the earlier
# miss (not halving) was a real one.
def test_bg():
    qs = []
    v = -F(11, 4) + 5 - F(5, 4)
    assert v == 1
    qs.append(Q("Work out –2 3/4 + 5 – 1 1/4", str(v), [str(v)], False,
                "Combine the fractions: –2 3/4 – 1 1/4 = –4. Then –4 + 5 = 1", "g7addsub"))
    qs.append(Q("A bag holds 4 1/2 kg of flour. Each cake uses 3/4 kg. Let c be the number of cakes. "
                "Which equation fits? A: c = 4 1/2 × 3/4  B: c = 3/4 ÷ 4 1/2  C: c = 4 1/2 ÷ 3/4. "
                "Write A, B or C.", "C", ["C"], False,
                "How many 3/4s fit in 4 1/2: divide 4 1/2 by 3/4", "g6fdiveq"))
    forms = ["5(3x + 4)", "5 × (3x + 4)", "5(3x+4)", "5×(3x+4)", "(3x + 4) × 5", "(3x+4)×5"]
    _expr_ok(forms, 15 * 2 + 20, x=2)
    qs.append(Q("Factor 15x + 20 using the greatest common factor of 15 and 20.", forms[0], forms, False,
                "GCF is 5: 15x = 5 × 3x and 20 = 5 × 4, so 5(3x + 4)", "g6factor"))
    v = D("12.05") - D("7.38")
    qs.append(Q("Work out 12.05 – 7.38", dec(v), [dec(v)], False,
                "Borrow across the 0: 12.05 – 7.38 = 4.67", "sub"))
    v = D(12) / D("0.30")
    assert v == 40
    qs.append(Q("12 is 30% of a number. What is the number?", dec(v), [dec(v)], False,
                "30% is 12, so 10% is 4 and 100% is 40", "whole"))
    qs.append(Q("Which unit could measure the volume of a box: cm, cm² or cm³?", "cm³",
                ["cm³", "cm3", "cubic cm", "cubic centimeters"], False,
                "Volume is counted in cubes: cubic centimeters, cm³", "g5volunit"))
    v = F(15, 2) * F(2, 3)
    qs.append(Q("The base of a box has an area of 7 1/2 square inches. The box is 2/3 inch tall. "
                "What is its volume in cubic inches?", mixed(v),
                [mixed(v), f"{mixed(v)} cubic inches", f"{mixed(v)} in³"], False,
                "V = bh: 15/2 × 2/3 = 30/6 = 5", "g6volbh"))
    qs.append(Q("A taxi costs $3 plus $2 per mile. Sam can spend at most $15. Which inequality fits "
                "the miles m? A: 3 + 2m ≤ 15  B: 3 + 2m ≥ 15  C: 2 + 3m ≤ 15. Write A, B or C.",
                "A", ["A"], False,
                "$3 once plus $2 for each mile, and at most $15 means ≤ 15", "g7ineqcon"))
    v = D("0.064") * 1000
    qs.append(Q("Work out 0.064 × 1000", dec(v), [dec(v)], False,
                "× 1000 moves every digit three places left: 64", "g5pow10_mul"))
    import math
    v = math.gcd(48, 72)
    qs.append(Q("What is the greatest common factor of 48 and 72?", str(v), [str(v)], False,
                "48 = 24 × 2 and 72 = 24 × 3, and 2 and 3 share nothing more", "g6gcf"))
    return qs


def test_bh():
    qs = []
    plot = {"kind": "lineplot", "denominator": 4, "max": 1, "caption": "liters of water in each beaker",
            "values": {"1/4": 2, "1/2": 2, "3/4": 2, "1": 2}}
    vals = {F(k): n for k, n in plot["values"].items()}
    total = sum(k * n for k, n in vals.items())
    v = total / sum(vals.values())
    qs.append(Q("All the water is shared out equally among the 8 beakers. How much is in each?",
                f"{frac(v)} liter", [f"{frac(v)} liter", f"{frac(v)} liters", f"{frac(v)} L"], True,
                "Total: 1/2 + 1 + 1 1/2 + 2 = 5 liters. 5 ÷ 8 = 5/8 liter each", "g5lineplot",
                "liter", figure=plot))
    import math
    g = math.gcd(36, 54)
    a, b = 36 // g, 54 // g
    assert math.gcd(a, b) == 1
    forms = [f"{g}({a} + {b})", f"{g} × ({a} + {b})", f"{g}({a}+{b})", f"{g}×({a}+{b})",
             f"({a} + {b}) × {g}", f"({a}+{b})×{g}"]
    qs.append(Q("Write 36 + 54 as a number times a sum of two numbers that have no common factor.",
                forms[0], forms, False, "GCF of 36 and 54 is 18: 36 + 54 = 18 × 2 + 18 × 3 = 18(2 + 3)",
                "g6gcfsum"))
    qs.append(Q("How many numbers make y > 4 true? Write one or infinitely many.", "infinitely many",
                ["infinitely many", "infinite", "infinitely many solutions", "Infinitely many"], False,
                "5, 4.1, 10, 1000 ... every number above 4 works", "g6inf"))
    qs.append(Q("Most test scores are high and a few are very low. Is the data skewed left or "
                "skewed right? Write left or right.", "left", ["left", "skewed left", "Left"], False,
                "The long tail is on the low side, so it is skewed left", "g6skew"))
    qs.append(Q("Is every square also a rectangle? Write yes or no.", "yes", ["yes", "Yes"], False,
                "A square has four right angles, so it is a rectangle (with equal sides too)",
                "g5shapeclass"))
    v = D("12.50") - D("4.75")
    qs.append(Q("Lia had some money. Her aunt gave her $4.75 and now she has $12.50. How much did she "
                "have at first?", usd(v), [usd(v), dec(v), f"{dec(v)} dollars"], False,
                "x + 4.75 = 12.50, so x = 12.50 – 4.75 = 7.75", "g6eqsolve_xp_rw"))
    qs.append(Q("The median of 20 heights is 142 cm. Does the median describe the data set with one "
                "number or many numbers? Write one or many.", "one", ["one", "One", "one number"], False,
                "A median is a single number that sums up the whole set", "g6distone"))
    v = 2592 // 36
    assert 36 * v == 2592
    qs.append(Q("Work out 2592 ÷ 36", str(v), [str(v)], False,
                "259 ÷ 36 = 7 r 7, bring down 2: 72 ÷ 36 = 2", "g5divw"))
    v = F(-3, 4) * F(-8, 9)
    qs.append(Q("Work out (–3/4) × (–8/9)", frac(v), [frac(v)], False,
                "Two negatives make a positive: 3/4 × 8/9 = 24/36 = 2/3", "g7ratmul"))
    v = F(9, 4) / F(3, 8)
    assert v == 6
    qs.append(Q("How many 3/8-cup scoops are in 2 1/4 cups of rice?", str(v),
                [str(v), f"{v} scoops"], False,
                "2 1/4 = 9/4, and 9/4 ÷ 3/8 = 9/4 × 8/3 = 6", "g6fdivword"))
    return qs


def test_bi():
    qs = []
    eq = ["p = 6b", "p=6b", "p = 6 × b", "p=6×b", "p = b × 6"]
    _expr_ok([e.split("=")[1] for e in eq], 6 * 5, b=5)
    qs.append(Q("Each box holds 6 pens. Write an equation for the number of pens p in b boxes.",
                eq[0], eq, False, "The pens depend on the boxes: p = 6b", "g6depvar"))
    v = F(9, 2) * F(2, 3)
    qs.append(Q("A rope is 4 1/2 m long. Lee uses 2/3 of it. How long a piece does Lee use?",
                f"{mixed(v)} m", [f"{mixed(v)} m"], True,
                "2/3 × 9/2 = 18/6 = 3 m", "g5fmulword", "m"))
    px, py = -4, -6
    quad = 1 if px > 0 and py > 0 else 2 if px < 0 < py else 3 if px < 0 and py < 0 else 4
    qs.append(Q("In which quadrant is the point (–4, –6)? Write 1, 2, 3 or 4.", str(quad),
                [str(quad), f"quadrant {quad}", f"Quadrant {quad}"], False,
                "x is negative (left), y is negative (down): quadrant 3", "g6quadrant"))
    v = 2 * 4 ** 2 + 3
    qs.append(Q("Find the value of 2x² + 3 when x = 4.", str(v), [str(v)], False,
                "Square first: 4² = 16. Then 2 × 16 + 3 = 35", "g6evalexp"))
    v = F(9, 3)
    qs.append(Q("The ratio of flour to sugar is 9 : 3. How many cups of flour are there for each cup "
                "of sugar?", str(v), [str(v), f"{v} cups"], False,
                "9 : 3 as a unit rate is 9/3 = 3 cups of flour per cup of sugar", "g6unitrate_ab"))
    v = F(14 * 9, 2)
    qs.append(Q("A triangle has a base of 14 cm and a height of 9 cm. What is its area?",
                f"{v} cm²", [f"{v} cm²", f"{v} cm2", f"{v} square cm"], True,
                "Half of base × height: 14 × 9 = 126, half is 63 cm²", "g6trimath", "cm²"))
    qs.append(Q("Which is further left on a number line: –2.5 or –1.5?", "–2.5", ["–2.5", "-2.5"], False,
                "–2.5 is further below 0, so it is further left", "g6numline"))
    v = max(D("0.407"), D("0.47"))
    qs.append(Q("Which is greater: 0.407 or 0.47?", dec(v), [dec(v)], False,
                "Compare tenths first: 4 = 4, then hundredths: 7 > 0, so 0.47", "g5cmp"))
    qs.append(Q("Which is a statistical question? A: How old is Mia?  B: How old are the students in "
                "Mia's class? Write A or B.", "B", ["B"], False,
                "B expects many different answers, so the data varies", "g6statq"))
    forms = ["6y + 8", "6y+8", "8 + 6y", "8+6y"]
    _expr_ok(forms, 5 + 2 * 3 + 3 + 4 * 3, y=3)
    qs.append(Q("Write 5 + 2y + 3 + 4y in its simplest form.", forms[0], forms, False,
                "Reorder: 2y + 4y + 5 + 3 = 6y + 8", "g6commute"))
    return qs


SK.update({
    "g6eqrep_xp_rw": ("Represent a real-world problem with x + p = q", "6.EE.B.7",
                      ["ed92d2a4-92cb-5365-8471-7494e0390c77"]),
    "g6eqsolve_px_rw": ("Solve a real-world problem with px = q", "6.EE.B.7",
                        ["fafaead4-3eb8-51f9-aac0-5bbfa4b64f3e"]),
    "g6volbh_math": ("Volume with V = bh and a fractional edge, mathematical", "6.G.A.2",
                     ["1756aedc-6f52-52e3-a1c7-d46cfbba1a88"]),
    "g6quadrw": ("Area of a quadrilateral by composing and decomposing, real-world", "6.G.A.1",
                 ["924ca975-15b2-59d6-9093-d59fbbc7bbdb"]),
})


# Tests BJ, BK and BL are one batch from `skills.py --plan --sheets 3` after BG, BH and
# BI were marked. The plan returned only 19 picks for 30 questions (every weak standard,
# two with never-asked components, one review due), so as with BG-BI the spare slots go
# to second questions on weak standards, each on a different component from that
# standard's plan pick and on a different sheet. 6.EE.B.8's recent misses were about
# "infinitely many", which BH3 then got right, so its pick goes back to writing an
# inequality with the stated variable. 6.NS.C.6.b aims at reflections, where its real
# misses are; quadrant questions have been right since AV5.
def _neg(v):
    return [f"{s}{t}" for s in ("–", "-") for t in dict.fromkeys((mixed(-v), frac(-v)))]


def test_bj():
    qs = []
    v = F(13, 4) - 5 + F(3, 2)
    assert v == F(-1, 4)
    qs.append(Q("Work out 3 1/4 – 5 + 1 1/2", f"–{mixed(-v)}", _neg(v), False,
                "Group the fractions: 3 1/4 + 1 1/2 = 4 3/4. Then 4 3/4 – 5 = –1/4", "g7addsub"))
    import math
    g = math.gcd(42, 56)
    a, b = 42 // g, 56 // g
    assert math.gcd(a, b) == 1
    forms = [f"{g}({a} + {b})", f"{g} × ({a} + {b})", f"{g}({a}+{b})", f"{g}×({a}+{b})",
             f"({a} + {b}) × {g}", f"({a}+{b})×{g}"]
    qs.append(Q("Write 42 + 56 as a number times a sum of two numbers that have no common factor.",
                forms[0], forms, False, f"GCF of 42 and 56 is {g}: 42 + 56 = {g} × {a} + {g} × {b} "
                f"= {g}({a} + {b})", "g6gcfsum"))
    forms = ["h < 140", "h<140", "140 > h", "140>h"]
    qs.append(Q("A ride is only for children shorter than 140 cm. Write an inequality for the "
                "height h of a child who may ride.", forms[0], forms, False,
                "Shorter than 140 means less than 140, not equal to it: h < 140", "g6ineqwrite"))
    qs.append(Q("Most children read 1 or 2 books a month and a few read 15 or more. Is the data "
                "skewed left or skewed right? Write left or right.", "right",
                ["right", "skewed right", "Right"], False,
                "The long tail is on the high side, so it is skewed right", "g6skew"))
    v = F(10, 4)
    qs.append(Q("Paint is mixed 10 cans of white to 4 cans of blue. How many cans of white are "
                "there for each can of blue?", mixed(v),
                [mixed(v), frac(v), dec(D(v.numerator) / v.denominator), f"{mixed(v)} cans"], False,
                "10 : 4 as a unit rate is 10/4 = 2 1/2 cans of white per can of blue", "g6unitrate_ab"))
    qs.append(Q("Ana's 12 quiz scores have a median of 7. How many numbers does the median use to "
                "describe all 12 scores?", "1", ["1", "one", "One", "1 number", "one number"], False,
                "A median is a single number that sums up the whole set", "g6distone"))
    v = D("4.50") / 3 * 7
    qs.append(Q("3 notebooks cost $4.50. At the same price, how much do 7 notebooks cost?", usd(v),
                [usd(v), dec(v), f"{dec(v)} dollars"], False,
                "One notebook: 4.50 ÷ 3 = 1.50. Seven: 7 × 1.50 = 10.50", "g7prop_rep"))
    v = F(14, 3) / F(2, 3)
    assert v == 7
    qs.append(Q("How many 2/3-cup servings are in 4 2/3 cups of soup?", str(v),
                [str(v), f"{v} servings"], False,
                "4 2/3 = 14/3, and 14/3 ÷ 2/3 = 14/3 × 3/2 = 7", "g6fdivword"))
    v = F(8 * 15, 2)
    qs.append(Q("A sail is a triangle with a base of 8 ft and a height of 15 ft. What is its area?",
                f"{v} ft²", [f"{v} ft²", f"{v} ft2", f"{v} square feet", f"{v} sq ft"], True,
                "Half of base × height: 8 × 15 = 120, half is 60 ft²", "g6tri", "ft²"))
    v = F(-3, 4) / F(1, 8)
    assert v == -6
    qs.append(Q("Work out (–3/4) ÷ (1/8)", f"–{mixed(-v)}", _neg(v), False,
                "Multiply by the flipped divisor: –3/4 × 8 = –6. One negative, so negative",
                "g7ratdiv"))
    return qs


def test_bk():
    qs = []
    plot = {"kind": "lineplot", "denominator": 8, "max": 1, "caption": "length of each ribbon (m)",
            "values": {"1/8": 2, "3/8": 1, "5/8": 3, "7/8": 2}}
    vals = {F(k): n for k, n in plot["values"].items()}
    v = sum(k * n for k, n in vals.items() if k > F(1, 2))
    qs.append(Q("What is the total length of only the ribbons longer than 1/2 m?",
                f"{mixed(v)} m", [f"{mixed(v)} m", f"{mixed(v)}m", f"{frac(v)} m"], True,
                "Longer than 1/2 m: three of 5/8 and two of 7/8: 15/8 + 14/8 = 29/8 = 3 5/8 m",
                "g5lineplot", "m", figure=plot))
    v = F(27, 4) * F(2, 3)
    qs.append(Q("A tank holds 6 3/4 liters. 2/3 of it is used. How many liters are used?",
                f"{mixed(v)} L", [f"{mixed(v)} L", f"{mixed(v)} liters", f"{mixed(v)} liter",
                                  f"{frac(v)} L", f"{frac(v)} liters"], True,
                "6 3/4 = 27/4, and 2/3 × 27/4 = 54/12 = 4 1/2 liters", "g5fmulword", "L"))
    qs.append(Q("The point (–6, 2) is reflected across the x-axis. Write the new point.", "(–6, –2)",
                ["(–6, –2)", "(-6, -2)", "(-6,-2)", "(–6,–2)", "-6, -2", "-6,-2"], False,
                "Reflecting across the x-axis flips the sign of y only: (–6, 2) goes to (–6, –2)",
                "g6reflect"))
    v = D(18) / D("0.24")
    assert v == 75
    qs.append(Q("Work out 18 ÷ 0.24", dec(v), [dec(v)], False,
                "Multiply both by 100: 1800 ÷ 24 = 75", "g6divdecwhole"))
    v = 25 + 40 * 3
    qs.append(Q("A plumber charges 25 + 40h dollars for h hours. How much is it for 3 hours?",
                f"${v}", [f"${v}", str(v), f"{v} dollars"], False,
                "Put h = 3: 25 + 40 × 3 = 25 + 120 = 145", "g6evalrw"))
    qs.append(Q("Jo has some stickers. After getting 15 more she has 42. Which equation fits? "
                "A: 15s = 42  B: s + 15 = 42  C: s – 15 = 42. Write A, B or C.", "B", ["B"], False,
                "Some stickers plus 15 more makes 42: s + 15 = 42", "g6eqrep_xp_rw"))
    import math
    v = math.gcd(36, 60)
    qs.append(Q("What is the greatest common factor of 36 and 60?", str(v), [str(v)], False,
                "36 = 12 × 3 and 60 = 12 × 5, and 3 and 5 share nothing more", "g6gcf"))
    qs.append(Q("Which one number tells the typical value of a data set? A: the range  "
                "B: the median  C: how many values there are. Write A, B or C.", "B", ["B"], False,
                "The median is a measure of center: one number for a typical value", "g6center"))
    v = F(21, 4) * F(8, 3)
    assert v == 14
    qs.append(Q("A prism has a base area of 5 1/4 cm² and a height of 2 2/3 cm. What is its volume?",
                str(v), [str(v), f"{v} cm³", f"{v} cm3", f"{v} cubic cm"], False,
                "V = bh: 21/4 × 8/3 = 168/12 = 14 cm³", "g6volbh_math"))
    v = -F(11, 8) - F(21, 8)
    assert v == -4
    qs.append(Q("Work out –1 3/8 – 2 5/8", f"–{mixed(-v)}", _neg(v), False,
                "Both go down: –1 3/8 – 2 5/8 = –(1 3/8 + 2 5/8) = –4", "g7ratsub"))
    return qs


def test_bl():
    qs = []
    # \u00a0 keeps each mixed number and each option on one line: "1" at a line end and
    # "1/2" on the next reads as two numbers.
    qs.append(Q("5\u00a01/4 m of ribbon is cut into 3/4 m pieces. Which gives the number of pieces? "
                "A:\u00a05\u00a01/4\u00a0×\u00a03/4  B:\u00a05\u00a01/4\u00a0÷\u00a03/4  "
                "C:\u00a03/4\u00a0÷\u00a05\u00a01/4", "B", ["B"], False,
                "How many 3/4s fit in 5 1/4: divide 5 1/4 by 3/4", "g6fdiveq"))
    forms = ["6(3y + 4)", "6 × (3y + 4)", "6(3y+4)", "6×(3y+4)", "(3y + 4) × 6", "(3y+4)×6"]
    _expr_ok(forms, 18 * 2 + 24, y=2)
    qs.append(Q("Factor 18y + 24 using the greatest common factor of 18 and 24.", forms[0], forms,
                False, "GCF is 6: 18y = 6 × 3y and 24 = 6 × 4, so 6(3y + 4)", "g6factor"))
    v = F(-2, 5) * F(-15, 4)
    assert v == F(3, 2)
    qs.append(Q("Work out (–2/5) × (–15/4)", mixed(v), [mixed(v), frac(v), "1.5"], False,
                "Two negatives make a positive: 2/5 × 15/4 = 30/20 = 1 1/2", "g7ratmul"))
    v = F(10 + 6, 2) * 4
    assert v == 6 * 4 + F(4 * 4, 2)
    qs.append(Q("A patio is a trapezoid. Its parallel sides are 10 m and 6 m, and they are 4 m "
                "apart. What is its area?", f"{v} m²",
                [f"{v} m²", f"{v} m2", f"{v} square meters", f"{v} sq m"], True,
                "Rectangle 6 × 4 = 24, plus two triangles that make 4 × 4 ÷ 2 = 8: 32 m²",
                "g6quadrw", "m²"))
    v = D(260) * D("0.15")
    qs.append(Q("Find 15% of 260.", dec(v), [dec(v)], False,
                "10% is 26 and 5% is 13, so 15% is 39", "g6pct_of"))
    v = F(9, 2) * F(8, 3)
    assert v == 12
    qs.append(Q("A fish tank has a base area of 4 1/2 square feet and is 2 2/3 feet tall. What is "
                "its volume in cubic feet?", str(v),
                [str(v), f"{v} ft³", f"{v} ft3", f"{v} cubic feet"], False,
                "V = bh: 9/2 × 8/3 = 72/6 = 12", "g6volbh"))
    v = F(162, 6)
    assert v == 27
    qs.append(Q("A car goes 162 miles on 6 gallons of gas. How many miles is that per gallon?", str(v),
                [str(v), f"{v} miles", f"{v} miles per gallon", f"{v} mpg"], False,
                "Miles per gallon: 162 ÷ 6 = 27", "g6unitrate"))
    v = D("4.20") / D("0.35")
    assert v == 12
    qs.append(Q("Pencils cost $0.35 each. Mia spent $4.20 on pencils. How many did she buy?", dec(v),
                [dec(v), f"{dec(v)} pencils"], False,
                "0.35p = 4.20, so p = 4.20 ÷ 0.35 = 420 ÷ 35 = 12", "g6eqsolve_px_rw"))
    qs.append(Q("Sam fills 3\u00a01/3 jars with 1\u00a01/2 cups each. Which gives the cups used? "
                "A:\u00a01\u00a01/2\u00a0÷\u00a03\u00a01/3  B:\u00a03\u00a01/3\u00a0×\u00a01\u00a01/2  "
                "C:\u00a03\u00a01/3\u00a0÷\u00a01\u00a01/2", "B", ["B"],
                False, "3 1/3 jars of 1 1/2 cups each is 3 1/3 times 1 1/2", "g5fmuleq"))
    v = 3 * 3 ** 2 - 5
    qs.append(Q("Find the value of 3a² – 5 when a = 3.", str(v), [str(v)], False,
                "Square first: 3² = 9. Then 3 × 9 – 5 = 22", "g6evalexp"))
    return qs


SK.update({
    "g7ratio_multi": ("Solve a multi-step ratio problem", "7.RP.A.3",
                      ["da9fc2c7-7cf2-52ef-bd89-1f1c625401e6"]),
    "g6eqrep_px_math": ("Represent a mathematical problem with px = q", "6.EE.B.7",
                        ["e54e642e-caef-5e93-956e-a382564f8e4f"]),
    "g6volboth_rw": ("Volume with V = lwh and V = bh and fractional edges, real-world", "6.G.A.2",
                     ["f873f320-ef6b-55f6-ab04-ce9b8dc30224"]),
})


def _nb(s):
    """Non-breaking spaces inside an answer option, so '2 1/4' never splits across lines."""
    return s.replace(" ", " ")


# Skew questions. BF7, BH4, BJ4 and BN3 were words only ("most values low and a few very
# high") with two choices, which had three faults: a guess was right half the time, so
# BN3 being right said little; every miss got the same diagnosis whatever its cause; and
# the child first had to turn "low values" into "the left of a number line" before she
# could look for a tail. These show a dot plot on a whole-number line and offer three
# answers. The answer is computed from the plotted data: mean right of the median means
# the tail is on the right.
def _skew_answer(values):
    data = sorted(int(k) for k, n in values.items() for _ in range(n))
    n = len(data)
    mean, med = F(sum(data), n), F(data[(n - 1) // 2] + data[n // 2], 2)
    counts = {int(k): c for k, c in values.items()}
    lo, hi = min(counts), max(counts)
    if all(counts.get(lo + hi - k, 0) == c for k, c in counts.items()):
        return "symmetric"
    mode = max(counts, key=counts.get)
    side = "right" if mean > med else "left"
    # A clear skew: the peak sits on the opposite half from the tail.
    assert mean != med and ((mode < (lo + hi) / 2) if side == "right" else (mode > (lo + hi) / 2)), values
    return side


def _skew_q(values, top, caption):
    ans = _skew_answer(values)
    forms = {"right": ["right", "skewed right", "Right"], "left": ["left", "skewed left", "Left"],
             "symmetric": ["symmetric", "Symmetric", "symmetrical"]}[ans]
    work = {"right": "The long tail stretches out to the right (high values), so it is skewed right",
            "left": "The long tail stretches out to the left (low values), so it is skewed left",
            "symmetric": "Both sides are mirror images, so it is symmetric"}[ans]
    return Q("Is this plot skewed left, skewed right or symmetric?", forms[0], forms, False,
             work, "g6skew",
             figure={"kind": "lineplot", "denominator": 1, "max": top, "caption": caption,
                     "values": {str(k): n for k, n in values.items()}})


def _skew_wrong(ans):
    """The other two answers, each with the one route that reaches it."""
    if ans == "symmetric":
        return {s: "Saw a tail in a plot whose two sides are mirror images" for s in ("left", "right")}
    bunch = "left" if ans == "right" else "right"
    return {bunch: "Named the skew after the side where the data bunches, not the side the tail "
                   "points to, as on BF7, BH4 and BJ4",
            "symmetric": "Did not see the tail: called a lopsided plot symmetric"}


SK.update({
    "g6volboth_math": ("Volume with V = lwh and V = bh and fractional edges, mathematical", "6.G.A.2",
                       ["2a84aba3-bc85-5130-b97c-7002f6d4e147"]),
    "g6eqrep_xp_math": ("Represent a mathematical problem with x + p = q", "6.EE.B.7",
                        ["099ceccb-4732-56c0-bdb1-61f9c6fcbd65"]),
})


# Tests BP, BQ and BR are one batch from `skills.py --plan --sheets 3`, re-run after the
# mastery rule changed: a standard is no longer mastered while one of its parts is still
# failing by the same three-days rule (5.NBT.B.5 had been green with 3-digit x 3-digit at
# one right since its last miss). That made 12 standards weak again, so the plan is 22
# failures, 2 coverage and 6 reviews, with no spare slots. Each failure aims at a part the
# plan names as failing. Departures, from reading the diagnoses:
# - 5.NF.A.2 and 5.MD.C.5: the recent misses are units only, with the arithmetic right,
#   so both questions require the unit - the unit is the gap being measured.
# - 5.NBT.B.5: the misses are copying and adding slips inside a correct method; it gets a
#   3-digit x 3-digit product, the part that has not recovered.
# - 6.SP.A.2 uses the dot-plot skew question; 6.G.A.2 and 6.EE.B.7 take their never-asked
#   parts (the coverage reason) rather than the failing ones.
# - Left out, because the plan is full: 6.RP.A.2, 6.SP.A.3, 4.OA.A.3, 5.G.B.4, 5.MD.C.3,
#   5.NBT.A.2 and 5.NBT.B.7, all weak.
def test_bp():
    qs = []
    v = F(11, 4) + F(11, 6)
    assert v == F(55, 12)
    qs.append(Q("Mia walked 2 3/4 km in the morning and 1 5/6 km in the afternoon. How far "
                "did she walk in all?", f"{mixed(v)} km", [f"{mixed(v)} km", f"{mixed(v)}km",
                                                          f"{frac(v)} km"], True,
                "Common denominator 12: 2 9/12 + 1 10/12 = 3 19/12 = 4 7/12 km", "g5fword_add", "km"))
    v = 734 * 268
    qs.append(Q("Work out 734 × 268", str(v), [str(v), f"{v:,}"], False,
                "734 × 8 = 5872, 734 × 60 = 44040, 734 × 200 = 146800; add: 196712", "g5mul33"))
    qs.append(Q("How many 2/3-cup scoops are in 5 1/3 cups of rice? Which gives the answer? "
                f"{_nb('A: 2/3 ÷ 5 1/3')}  {_nb('B: 5 1/3 × 2/3')}  {_nb('C: 5 1/3 ÷ 2/3')}",
                "C", ["C"], False, "How many 2/3s fit in 5 1/3: divide 5 1/3 by 2/3", "g6fdiveq"))
    mango = F(30 * 3, 2 + 3)
    assert mango == 18
    qs.append(Q("A fruit mix has 2 cups of apple for every 3 cups of mango. There are 30 cups in all. "
                "How many cups are mango?", str(mango), [str(mango), f"{mango} cups"], False,
                "2 + 3 = 5 cups in each batch, 30 ÷ 5 = 6 batches, 6 × 3 = 18 mango", "g7ratio_multi"))
    v = F(-2, 3) / F(-4, 9)
    assert v == F(3, 2)
    qs.append(Q("Work out (–2/3) ÷ (–4/9)", mixed(v), [mixed(v), frac(v), "1.5"], False,
                "Multiply by the flipped divisor: 2/3 × 9/4 = 18/12 = 1 1/2. Two negatives, so positive",
                "g7ratdiv"))
    qs.append(Q("A freezer is set to 15 degrees below zero. Write its temperature as a number.", "–15",
                ["–15", "-15", "–15 degrees", "-15 degrees", "–15°", "-15°"], False,
                "Zero degrees is 0 and below it is negative: –15", "g6signed"))
    pt = (7, 4)
    qs.append(Q(f"A point is at ({pt[0]}, {pt[1]}). How far is it from the y-axis?", str(pt[0]),
                [str(pt[0]), f"{pt[0]} units"], False,
                "Distance from the y-axis is how far across: the x-coordinate, 7", "g5coord_x"))
    v = D(30) - 4 * D("3.85")
    assert v == D("14.60")
    qs.append(Q("Sam has $30. He buys 4 books at $3.85 each. How much change does he get?", usd(v),
                [usd(v), "$14.6"], True, "4 × $3.85 = $15.40; $30 – $15.40 = $14.60", "money", "$"))
    data = [14, 9, 17, 12]
    v = F(sum(data), len(data))
    assert v == 13
    qs.append(Q("Four plants are 14, 9, 17 and 12 cm tall. What is their mean height?", str(v),
                [str(v), f"{v} cm"], False, f"Add them: {sum(data)}. Share among 4: {sum(data)} ÷ 4 = {v}",
                "g6mean"))
    forms = ["5t + 3", "5t+3", "3 + 5t", "3+5t", "5 × t + 3", "5×t+3"]
    _expr_ok(forms, 5 * 4 + 3, t=4)
    qs.append(Q("Tickets cost t dollars each. Write an expression for the cost of 5 tickets and a "
                "$3 booking fee.", forms[0], forms, False,
                "5 tickets cost 5 × t = 5t dollars; add 3 for the fee", "g6expr"))
    return qs


def test_bq():
    qs = []
    v = -F(21, 8) - F(27, 8)
    assert v == -6
    qs.append(Q("Work out –2 5/8 – 3 3/8", f"–{mixed(-v)}", _neg(v), False,
                "Both go down: –2 5/8 – 3 3/8 = –(2 5/8 + 3 3/8) = –6", "g7ratsub"))
    v = 12 * 5 * 4
    qs.append(Q("A box is 12 cm long, 5 cm wide and 4 cm tall. What is its volume?", f"{v} cm³",
                [f"{v} cm³", f"{v} cm3", f"{v} cubic cm", f"{v} cubic centimeters"], True,
                "12 × 5 = 60 cm² for the base; 60 × 4 = 240 cm³", "g5vol_math", "cm³"))
    forms = ["7(3y + 4)", "7 × (3y + 4)", "7(3y+4)", "7×(3y+4)", "(3y + 4) × 7", "(3y+4)×7"]
    _expr_ok(forms, 21 * 2 + 28, y=2)
    qs.append(Q("Factor 21y + 28 using the greatest common factor of 21 and 28.", forms[0], forms,
                False, "GCF is 7: 21y = 7 × 3y and 28 = 7 × 4, so 7(3y + 4)", "g6factor"))
    forms = ["w < 23", "w<23", "23 > w", "23>w"]
    qs.append(Q("A suitcase can be checked in only if it weighs less than 23 kg. Write an inequality "
                "for the weight w of a suitcase that can be checked in.", forms[0], forms, False,
                "Less than 23, not equal to it: w < 23", "g6ineqwrite"))
    forms = ["2m – 5", "2m - 5", "2m–5", "2m-5", "2 × m – 5", "2×m–5"]
    _expr_ok(forms, 2 * 6 - 5, m=6)
    qs.append(Q("Write an expression for: 5 less than 2 times m.", forms[0], forms, False,
                "2 times m is 2m; 5 less than that takes 5 away: 2m – 5", "g6expr_write"))
    qs.append(Q("The point (6, –3) is reflected across the y-axis. Write the new point.", "(–6, –3)",
                ["(–6, –3)", "(-6, -3)", "(-6,-3)", "(–6,–3)", "-6, -3", "-6,-3"], False,
                "Reflecting across the y-axis flips the sign of x only: (6, –3) goes to (–6, –3)",
                "g6reflect"))
    v = 5 + 2 * 3 ** 2
    qs.append(Q("Find the value of 5 + 2k² when k = 3.", str(v), [str(v)], False,
                "Square first: 3² = 9. Then 5 + 2 × 9 = 23", "g6evalexp"))
    qs.append(Q(f"A number n plus 2.5 is 9. Which equation fits? {_nb('A: 2.5n = 9')}  "
                f"{_nb('B: n – 2.5 = 9')}  {_nb('C: n + 2.5 = 9')}. Write A, B or C.", "C", ["C"], False,
                "n plus 2.5 is n + 2.5, and it equals 9: n + 2.5 = 9", "g6eqrep_xp_math"))
    qs.append(Q(f"Which statement is true? {_nb('A: |–3| > |–10|')}  {_nb('B: –3 > –10')}. "
                "Write the letter.", "B", ["B"],
                False, "–3 is further right than –10, so –3 > –10; but 3 is less than 10, so "
                "|–3| > |–10| is false", "g6absorder"))
    v = D("4.6952").quantize(D("0.01"))
    qs.append(Q("Round 4.6952 to the nearest hundredth.", str(v), [str(v), dec(v)], False,
                "The thousandths digit is 5, so 4.69 rounds up to 4.70", "g5round"))
    return qs


def test_br():
    qs = []
    import math
    g = math.gcd(48, 72)
    a, b = 48 // g, 72 // g
    assert math.gcd(a, b) == 1
    forms = [f"{g}({a} + {b})", f"{g} × ({a} + {b})", f"{g}({a}+{b})", f"{g}×({a}+{b})",
             f"({a} + {b}) × {g}", f"({a}+{b})×{g}"]
    qs.append(Q("Write 48 + 72 as a number times a sum of two numbers that have no common factor.",
                forms[0], forms, False, f"GCF of 48 and 72 is {g}: 48 + 72 = {g} × {a} + {g} × {b} "
                f"= {g}({a} + {b})", "g6gcfsum"))
    v = F(9, 2) * F(2, 3)
    assert v == 3
    qs.append(Q("A jug holds 4 1/2 cups of juice. Sam drinks 2/3 of it. How many cups does he "
                "drink?", f"{v} cups", [f"{v} cups", f"{v} cup"], True,
                "4 1/2 = 9/2, and 2/3 × 9/2 = 18/6 = 3 cups", "g5fmulword", "cups"))
    forms = ["a = 6b", "a=6b", "a = 6 × b", "a=6×b", "6b = a", "6b=a"]
    qs.append(Q("Each bag holds 6 apples. Write an equation for the number of apples a in b bags.",
                forms[0], forms, False, "Apples depend on bags: 6 in each bag, so a = 6b", "g6depvar"))
    v = F(14 + 10, 2) * 6
    assert v == 10 * 6 + 2 * F(2 * 6, 2)
    qs.append(Q("A table top is a trapezoid. Its parallel sides are 14 ft and 10 ft, and the height "
                "between them is 6 ft. What is its area?", f"{v} ft²",
                [f"{v} ft²", f"{v} ft2", f"{v} square feet", f"{v} sq ft"], True,
                "Rectangle 10 × 6 = 60, plus two triangles 2 × 6 ÷ 2 = 6 each: 72 ft²", "g6quadrw", "ft²"))
    qs.append(_skew_q({2: 3, 3: 5, 4: 4, 5: 2, 6: 1, 8: 1, 10: 1}, 10, "minutes to walk to school"))
    v = F(27) / F(30, 100)
    assert v == 90
    qs.append(Q("30% of a number is 27. What is the number?", str(v), [str(v)], False,
                "10% is 27 ÷ 3 = 9, so 100% is 90", "whole"))
    v = D(21) / D("0.35")
    assert v == 60
    qs.append(Q("Work out 21 ÷ 0.35", dec(v), [dec(v)], False,
                "Multiply both by 100: 2100 ÷ 35 = 60", "g6divdecwhole"))
    base = F(5, 2) * 4
    v = base * F(8, 5)
    assert v == 16
    qs.append(Q("A prism is 2 1/2 cm long, 4 cm wide and 1 3/5 cm tall. Use the area of "
                "its base to find its volume.", str(v),
                [str(v), f"{v} cm³", f"{v} cm3", f"{v} cubic cm"], False,
                "Base: 2 1/2 × 4 = 10 cm². V = bh: 10 × 1 3/5 = 16 cm³", "g6volboth_math"))
    v = 6552 // 26
    assert v * 26 == 6552
    qs.append(Q("Work out 6552 ÷ 26", str(v), [str(v)], False,
                "65 ÷ 26 = 2 r 13, bring down 5: 135 ÷ 26 = 5 r 5, bring down 2: 52 ÷ 26 = 2", "g6div"))
    l, w, h = 5, 2, 4
    v = l * w * h
    qs.append(Q("This box is full of unit cubes. How many cubes?", str(v),
                [str(v), f"{v} cubes", f"{v} unit cubes", f"{v} cubic units"], False,
                f"{l} × {w} in each layer = {l * w}, × {h} layers = {v}", "g5cubes",
                figure={"kind": "cubes", "l": l, "w": w, "h": h}))
    return qs


# Tests BM, BN and BO are one batch from `skills.py --plan --sheets 3` after BJ, BK and
# BL were marked. The plan returned 16 picks for 30 questions (13 failures, 2 coverage,
# 1 review), so as with BJ-BL each of the 14 weak standards gets a second question on a
# different component, on a different sheet from its plan pick. Departures from the plan,
# from reading the diagnoses:
# - 5.NF.B.6's recent misses are a units-only slip (BK2), a copying slip (BI2) and a
#   wrong operation choice (BL9); only the last is a gap, so its pick is the equation.
# - 6.EE.B.8's misses are wording (BF3) and the wrong letter (BJ3), not the inequality;
#   both its questions name the variable and still test the direction.
# - 6.G.A.2's misses are two blanks and halving a correct 14 (BK9), so its pick stays on
#   V = bh with a given base area; the never-asked lwh-and-bh real-world part is BN10.
#   The lwh-and-bh mathematical component (2a84aba3) is left for the next batch.
# - 6.EE.B.7 had two never-asked parts; this batch covers px = q (mathematical) only.
def test_bm():
    qs = []
    v = -F(19, 6) - F(11, 6)
    assert v == -5
    qs.append(Q("Work out –3 1/6 – 1 5/6", f"–{mixed(-v)}", _neg(v), False,
                "Both go down: –3 1/6 – 1 5/6 = –(3 1/6 + 1 5/6) = –5", "g7ratsub"))
    v = F(15, 4) / F(5, 8)
    assert v == 6
    qs.append(Q("A 3 3/4 m rope is cut into 5/8 m pieces. How many pieces are there?", str(v),
                [str(v), f"{v} pieces"], False,
                "3 3/4 = 15/4, and 15/4 ÷ 5/8 = 15/4 × 8/5 = 6", "g6fdivword"))
    v = F(-5, 6) / F(-1, 3)
    assert v == F(5, 2)
    qs.append(Q("Work out (–5/6) ÷ (–1/3)", mixed(v), [mixed(v), frac(v), dec(D(5) / 2)], False,
                "Multiply by the flipped divisor: 5/6 × 3 = 5/2 = 2 1/2. Two negatives, so positive",
                "g7ratdiv"))
    qs.append(Q("Leo's 30 jump distances have a mean of 2 m. How many numbers does the mean use "
                "to sum up all 30 jumps?", "1", ["1", "one", "One", "1 number", "one number"], False,
                "A mean is a single number that sums up the whole set", "g6distone"))
    v = F(14, 4)
    qs.append(Q("A recipe uses 14 cups of flour for 4 cups of sugar. How many cups of flour is that "
                "for each cup of sugar?", mixed(v),
                [mixed(v), frac(v), dec(D(14) / 4), f"{mixed(v)} cups"], False,
                "14 : 4 as a unit rate is 14/4 = 3 1/2 cups of flour per cup of sugar", "g6unitrate_ab"))
    red = F(40 * 3, 3 + 5)
    assert red == 15
    qs.append(Q("Paint is mixed 3 cans of red to 5 cans of white. Ben uses 40 cans in all. How many "
                "cans are red?", str(red), [str(red), f"{red} cans"], False,
                "3 + 5 = 8 cans in each batch, 40 ÷ 8 = 5 batches, 5 × 3 = 15 red", "g7ratio_multi"))
    import math
    v = 9 * 12 // math.gcd(9, 12)
    qs.append(Q("What is the least common multiple of 9 and 12?", str(v), [str(v)], False,
                "Multiples of 12: 12, 24, 36. 36 is the first that 9 also divides", "g6lcm"))
    forms = ["8x + 20", "8x+20", "20 + 8x", "20+8x"]
    _expr_ok(forms, 4 * (2 * 3 + 5), x=3)
    qs.append(Q("Expand 4(2x + 5).", forms[0], forms, False,
                "Multiply both terms by 4: 4 × 2x = 8x and 4 × 5 = 20", "g6distrib"))
    v = F(16 * 11, 2)
    qs.append(Q("A triangle has a base of 16 cm and a height of 11 cm. What is its area?",
                f"{v} cm²", [f"{v} cm²", f"{v} cm2", f"{v} square cm", f"{v} sq cm"], True,
                "Half of base × height: 16 × 11 = 176, half is 88 cm²", "g6trimath", "cm²"))
    v = F(26) / F(40, 100)
    assert v == 65
    qs.append(Q("40% of a number is 26. What is the number?", str(v), [str(v)], False,
                "10% is 26 ÷ 4 = 6.5, so 100% is 65", "whole"))
    return qs


def test_bn():
    qs = []
    import math
    g = math.gcd(36, 84)
    a, b = 36 // g, 84 // g
    assert math.gcd(a, b) == 1
    forms = [f"{g}({a} + {b})", f"{g} × ({a} + {b})", f"{g}({a}+{b})", f"{g}×({a}+{b})",
             f"({a} + {b}) × {g}", f"({a}+{b})×{g}"]
    qs.append(Q("Write 36 + 84 as a number times a sum of two numbers that have no common factor.",
                forms[0], forms, False, f"GCF of 36 and 84 is {g}: 36 + 84 = {g} × {a} + {g} × {b} "
                f"= {g}({a} + {b})", "g6gcfsum"))
    forms = ["5(4x + 7)", "5 × (4x + 7)", "5(4x+7)", "5×(4x+7)", "(4x + 7) × 5", "(4x+7)×5"]
    _expr_ok(forms, 20 * 2 + 35, x=2)
    qs.append(Q("Factor 20x + 35 using the greatest common factor of 20 and 35.", forms[0], forms,
                False, "GCF is 5: 20x = 5 × 4x and 35 = 5 × 7, so 5(4x + 7)", "g6factor"))
    qs.append(Q("Most test scores were high, 85 to 100, and a few were very low, near 40. Is the "
                "data skewed left or skewed right? Write left or right.", "left",
                ["left", "skewed left", "Left"], False,
                "The long tail is on the low side, so it is skewed left", "g6skew"))
    v = 2 * 4 ** 2 + 7
    qs.append(Q("Find the value of 2m² + 7 when m = 4.", str(v), [str(v)], False,
                "Square first: 4² = 16. Then 2 × 16 + 7 = 39", "g6evalexp"))
    qs.append(Q("A number n times 7 is 63. Which equation fits? A: n + 7 = 63  B: 7n = 63  "
                "C: n = 7 × 63. Write A, B or C.", "B", ["B"], False,
                "n times 7 is 7n, and it equals 63: 7n = 63", "g6eqrep_px_math"))
    v = -F(13, 3) + 9 + -F(8, 3)
    assert v == 2
    qs.append(Q("Work out –4 1/3 + 9 + (–2 2/3)", str(v), [str(v)], False,
                "Group the negatives: –4 1/3 + (–2 2/3) = –7. Then –7 + 9 = 2", "g7rat"))
    qs.append(Q("Which one number describes the middle of a data set? A: the median  B: the range  "
                "C: the largest value. Write A, B or C.", "A", ["A"], False,
                "The median is a measure of center", "g6center"))
    v = F(15, 2) * F(2, 5)
    assert v == 3
    qs.append(Q("A fence is 7 1/2 m long. Tom paints 2/5 of it. How many meters does he paint?",
                f"{v} m", [f"{v} m", f"{v}m", f"{v} meters"], True,
                "7 1/2 = 15/2, and 2/5 × 15/2 = 30/10 = 3 m", "g5fmulword", "m"))
    forms = ["t < 2 1/2", "t<2 1/2", "t < 5/2", "t<5/2", "t < 2.5", "t<2.5",
             "2 1/2 > t", "5/2 > t", "2.5 > t"]
    qs.append(Q("Write an inequality that says the number t is less than 2 1/2.", forms[0], forms,
                False, "Less than 2 1/2, not equal to it: t < 2 1/2", "g6ineqmath"))
    v = F(7, 2) * 2 * F(3, 2)
    qs.append(Q("A box is 3 1/2 in long, 2 in wide and 1 1/2 in tall. What is its volume "
                "in cubic inches?", mixed(v),
                [mixed(v), frac(v), dec(D(21) / 2), f"{mixed(v)} in³", f"{mixed(v)} in3",
                 f"{mixed(v)} cubic inches"], False,
                "Base 3 1/2 × 2 = 7 in². Then V = bh: 7 × 1 1/2 = 10 1/2 in³", "g6volboth_rw"))
    return qs


def test_bo():
    qs = []
    qs.append(Q("Each bag holds 2 1/4 kg of rice. Ana fills 2 2/3 bags. Which gives the "
                f"rice used? {_nb('A: 2 2/3 × 2 1/4')}  {_nb('B: 2 1/4 ÷ 2 2/3')}  "
                f"{_nb('C: 2 2/3 ÷ 2 1/4')}", "A", ["A"], False,
                "2 2/3 bags of 2 1/4 kg each is 2 2/3 times 2 1/4", "g5fmuleq"))
    forms = ["L < 450", "L<450", "450 > L", "450>L"]
    qs.append(Q("A lift can only carry loads lighter than 450 kg. Write an inequality for the load L "
                "that the lift may carry.", forms[0], forms, False,
                "Lighter than 450 means less than 450, not equal to it: L < 450", "g6ineqwrite"))
    v = F(12 + 8, 2) * 5
    assert v == 50
    qs.append(Q("A garden is a trapezoid. Its parallel sides are 12 m and 8 m, and the height "
                "between them is 5 m. What is its area?", f"{v} m²",
                [f"{v} m²", f"{v} m2", f"{v} square meters", f"{v} sq m"], True,
                "Average the parallel sides: (12 + 8) ÷ 2 = 10. Then 10 × 5 = 50 m²", "g6quadrw", "m²"))
    v = D(180) * D("0.35")
    assert v == 63
    qs.append(Q("Find 35% of 180.", dec(v), [dec(v)], False,
                "10% is 18, so 30% is 54, and 5% is 9: 54 + 9 = 63", "g6pct_of"))
    v = F(27, 4) * F(8, 3)
    assert v == 18
    qs.append(Q("A prism has a base area of 6 3/4 in² and a height of 2 2/3 in. What is its "
                "volume?", str(v), [str(v), f"{v} in³", f"{v} in3", f"{v} cubic inches"], False,
                "V = bh: 27/4 × 8/3 = 216/12 = 18 in³", "g6volbh_math"))
    qs.append(Q("How many 3/8 kg bags can be filled from 4 1/2 kg of flour? Which gives the "
                f"answer? {_nb('A: 4 1/2 ÷ 3/8')}  {_nb('B: 3/8 ÷ 4 1/2')}  {_nb('C: 4 1/2 × 3/8')}",
                "A", ["A"], False, "How many 3/8s fit in 4 1/2: divide 4 1/2 by 3/8", "g6fdiveq"))
    v = F(-3, 4) * F(-8, 3)
    assert v == 2
    qs.append(Q("Work out (–3/4) × (–2 2/3)", str(v), [str(v)], False,
                "Two negatives make a positive: 3/4 × 8/3 = 24/12 = 2", "g7ratmul"))
    v = F(96, 8)
    assert v == 12
    qs.append(Q("A printer prints 96 pages in 8 minutes. How many pages is that per minute?", str(v),
                [str(v), f"{v} pages", f"{v} pages per minute"], False,
                "Pages per minute: 96 ÷ 8 = 12", "g6unitrate"))
    ages = [9, 11, 12, 12, 14, 17]
    v = max(ages) - min(ages)
    qs.append(Q("The ages in a club are 9, 11, 12, 12, 14 and 17. What is the range of the ages?",
                str(v), [str(v), f"{v} years"], False,
                "Range is largest minus smallest: 17 – 9 = 8", "g6spread"))
    v = 15 + 8 * 5
    qs.append(Q("A gym charges 15 + 8w dollars for w weeks. How much is it for 5 weeks?", f"${v}",
                [f"${v}", str(v), f"{v} dollars"], False,
                "Put w = 5: 15 + 8 × 5 = 15 + 40 = 55", "g6evalrw"))
    return qs


# Tests BS, BT and BU are one batch from `skills.py --plan --sheets 3` after BP, BQ and
# BR were marked: 25 failures and 4 reviews, so 29 picks with one spare slot. The spare
# goes to a second expression question (6.EE.A.2.a): writing a number where the letter
# belongs has now happened on AI3, AS10 and BQ5. Departures, from the diagnoses:
# - 5.NF.A.2 and 5.MD.C.5: the misses are still units only (BP1, BQ2), so both keep a
#   required unit; the arithmetic has been right every time.
# - 5.NBT.B.7: the misses were a copying slip and a dropped carry; the question needs a carry.
# - 5.G.B.4: the miss is that an equilateral triangle is also isosceles (AX7).
# - Multiple-choice answers avoid slot A where the trap would sit there: on S7 and BK8 a
#   default guess of A was the wrong answer.
def test_bs():
    qs = []
    v = F(16, 3) - F(11, 4)
    assert v == F(31, 12)
    qs.append(Q("A tank has 5 1/3 liters of water. 2 3/4 liters leak out. How much water is "
                "left?", f"{mixed(v)} L", [f"{mixed(v)} L", f"{mixed(v)} liters", f"{frac(v)} L"],
                True, "Common denominator 12: 5 4/12 – 2 9/12 = 4 16/12 – 2 9/12 = 2 7/12 L",
                "g5fword_sub", "L"))
    import math
    v = math.gcd(72, 96)
    assert v == 24
    qs.append(Q("What is the greatest common factor of 72 and 96?", str(v), [str(v)], False,
                "72 = 24 × 3 and 96 = 24 × 4, and 3 and 4 share nothing more", "g6gcf"))
    qs.append(Q("Each jar holds 3/4 cup of jam. Lena fills 2 2/3 jars. Which gives the jam used? "
                f"{_nb('A: 2 2/3 ÷ 3/4')}  {_nb('B: 2 2/3 × 3/4')}  {_nb('C: 3/4 ÷ 2 2/3')}", "B", ["B"],
                False, "2 2/3 jars of 3/4 cup each is 2 2/3 times 3/4", "g5fmuleq"))
    v = F(16 + 10, 2) * 4
    assert v == 52
    qs.append(Q("A patio is a trapezoid. Its parallel sides are 16 m and 10 m, and the height between "
                "them is 4 m. What is its area?", f"{v} m²",
                [f"{v} m²", f"{v} m2", f"{v} square meters", f"{v} sq m"], True,
                "Rectangle 10 × 4 = 40, plus two triangles 3 × 4 ÷ 2 = 6 each: 52 m²", "g6quadrw", "m²"))
    qs.append(Q("In which quadrant is the point (–4, –7)? Write 1, 2, 3 or 4.", "3", ["3"], False,
                "x negative (left) and y negative (down): quadrant 3", "g6quadrant"))
    v = 3 * 5 ** 2 - 4
    qs.append(Q("Find the value of 3n² – 4 when n = 5.", str(v), [str(v)], False,
                "Square first: 5² = 25. Then 3 × 25 – 4 = 71", "g6evalexp"))
    v = F(15, 4) * F(8, 5)
    assert v == 6
    qs.append(Q("A fish tank has a base area of 3 3/4 square feet and is 1 3/5 feet tall. What "
                "is its volume in cubic feet?", str(v), [str(v), f"{v} ft³", f"{v} ft3", f"{v} cubic feet"],
                False, "V = bh: 15/4 × 8/5 = 120/20 = 6", "g6volbh"))
    qs.append(Q("Triangle T has 3 equal sides. Which names fit it? A: equilateral only  B: isosceles "
                "only  C: both equilateral and isosceles. Write A, B or C.", "C", ["C"], False,
                "Isosceles means at least 2 equal sides, so 3 equal sides counts too: both", "g5tri"))
    qs.append(Q("Two boxes take up exactly the same amount of space. Which must be the same for both? "
                "A: perimeter  B: volume  C: height. Write A, B or C.", "B", ["B"], False,
                "Volume is the space an object takes up", "g5volspace"))
    v = D(340) * D("0.15")
    assert v == 51
    qs.append(Q("Find 15% of 340.", dec(v), [dec(v)], False,
                "10% is 34 and 5% is 17: 34 + 17 = 51", "g6pct_of"))
    return qs


def test_bt():
    qs = []
    v = -F(23, 4) + 9 + -F(9, 4)
    assert v == 1
    qs.append(Q("Work out –5 3/4 + 9 + (–2 1/4)", str(v), [str(v)], False,
                "Group the negatives: –5 3/4 + (–2 1/4) = –8. Then –8 + 9 = 1", "g7rat"))
    blue = F(56 * 4, 3 + 4)
    assert blue == 32
    qs.append(Q("A bead kit has 3 red beads for every 4 blue beads. There are 56 beads in all. How "
                "many are blue?", str(blue), [str(blue), f"{blue} beads", f"{blue} blue"], False,
                "3 + 4 = 7 beads in each group, 56 ÷ 7 = 8 groups, 8 × 4 = 32 blue", "g7ratio_multi"))
    forms = ["8(3x + 5)", "8 × (3x + 5)", "8(3x+5)", "8×(3x+5)", "(3x + 5) × 8", "(3x+5)×8"]
    _expr_ok(forms, 24 * 2 + 40, x=2)
    qs.append(Q("Factor 24x + 40 using the greatest common factor of 24 and 40.", forms[0], forms,
                False, "GCF is 8: 24x = 8 × 3x and 40 = 8 × 5, so 8(3x + 5)", "g6factor"))
    forms = ["4p + 7", "4p+7", "7 + 4p", "7+4p", "4 × p + 7", "4×p+7"]
    _expr_ok(forms, 4 * 3 + 7, p=3)
    qs.append(Q("Write an expression for: 7 more than 4 times p.", forms[0], forms, False,
                "4 times p is 4p; 7 more than that adds 7: 4p + 7", "g6expr_write"))
    qs.append(_skew_q({1: 1, 3: 1, 5: 2, 6: 3, 7: 4, 8: 5, 9: 3}, 10, "goals scored"))
    v = D(80) - 6 * D("12.75")
    assert v == D("3.50")
    qs.append(Q("A phone plan costs $12.75 a month. Lily pays for 6 months with $80. How much change "
                "does she get?", usd(v), [usd(v), "$3.5"], True,
                "6 × $12.75 = $76.50; $80 – $76.50 = $3.50", "money", "$"))
    v = D("6.85") + D("3.7")
    qs.append(Q("Work out 6.85 + 3.7", dec(v), [dec(v)], False,
                "Line up the points: 6.85 + 3.70 = 10.55", "g5decadd"))
    v = -(-158 // 24)
    assert v == 7
    qs.append(Q("158 students go on a trip. Each bus holds 24 students. How many buses are needed?",
                str(v), [str(v), f"{v} buses"], False,
                "158 ÷ 24 = 6 r 14. The 14 left over still need a bus, so 7 buses", "g4multi"))
    qs.append(Q("The median of 40 test scores is 81. Does the median describe the data set with one "
                "number or many numbers? Write one or many.", "one", ["one", "One", "1"], False,
                "A median is a single number that sums up the whole set", "g6distone"))
    qs.append(Q("–2 > –9. Which of these two numbers is further to the right on a number line?", "–2",
                ["–2", "-2"], False, "Greater means further right: –2 is to the right of –9",
                "g6ineqpos"))
    return qs


def test_bu():
    qs = []
    v = 15 * 6 * 3
    qs.append(Q("A box is 15 cm long, 6 cm wide and 3 cm tall. What is its volume?", f"{v} cm³",
                [f"{v} cm³", f"{v} cm3", f"{v} cubic cm", f"{v} cubic centimeters"], True,
                "15 × 6 = 90 cm² for the base; 90 × 3 = 270 cm³", "g5vol_math", "cm³"))
    v = 856 * 347
    qs.append(Q("Work out 856 × 347", str(v), [str(v), f"{v:,}"], False,
                "856 × 7 = 5992, 856 × 40 = 34240, 856 × 300 = 256800; add: 297032", "g5mul33"))
    forms = ["p = 8b", "p=8b", "p = 8 × b", "p=8×b", "8b = p", "8b=p"]
    qs.append(Q("Boxes b: 1, 2, 3. Pens p: 8, 16, 24. Write an equation for the number of pens p in "
                "b boxes.", forms[0], forms, False,
                "Each box adds 8 pens, and the pens depend on the boxes: p = 8b", "g6tableeq"))
    forms = ["infinitely many", "Infinitely many", "infinite", "infinitely many numbers", "infinitely"]
    qs.append(Q("How many numbers make x > 9 true? Write one, none or infinitely many.", forms[0], forms,
                False, "9.1, 10, 100 and every number above 9 work: infinitely many", "g6inf"))
    pt = (3, 10)
    qs.append(Q(f"A point is at ({pt[0]}, {pt[1]}). How far is it from the y-axis?", str(pt[0]),
                [str(pt[0]), f"{pt[0]} units"], False,
                "Distance from the y-axis is how far across: the x-coordinate, 3", "g5coord_x"))
    v = F(10, 4)
    qs.append(Q("A recipe uses 10 cups of water for 4 cups of rice. How many cups of water is that for "
                "each cup of rice?", mixed(v), [mixed(v), frac(v), "2.5", f"{mixed(v)} cups"], False,
                "10 : 4 as a unit rate is 10/4 = 2 1/2 cups of water per cup of rice", "g6unitrate_ab"))
    v = D("47.3") / 1000
    qs.append(Q("Work out 47.3 ÷ 10³", dec(v), [dec(v)], False,
                "10³ = 1000, so the point moves three places left: 0.0473", "g5pow10"))
    qs.append(Q("Pens cost $3 each. Sam spends $27 on p pens. Which equation fits? "
                f"{_nb('A: p + 3 = 27')}  {_nb('B: 27p = 3')}  {_nb('C: 3p = 27')}. Write A, B or C.",
                "C", ["C"], False, "p pens at $3 each cost 3p, and that is 27: 3p = 27", "g6eqrep_px"))
    v = F(-5, 8) * F(-12, 5)
    assert v == F(3, 2)
    qs.append(Q("Work out (–5/8) × (–2 2/5)", mixed(v), [mixed(v), frac(v), "1.5"], False,
                "Two negatives make a positive: 5/8 × 12/5 = 60/40 = 1 1/2", "g7ratmul"))
    forms = ["6k – 2", "6k - 2", "6k–2", "6k-2", "6 × k – 2", "6×k–2"]
    _expr_ok(forms, 6 * 5 - 2, k=5)
    qs.append(Q("Write an expression for: 2 less than 6 times k.", forms[0], forms, False,
                "6 times k is 6k; 2 less than that takes 2 away: 6k – 2", "g6expr_write"))
    return qs


# Tests BV, BW and BX are one batch from `skills.py --plan --sheets 3` after BS, BT and
# BU were marked: 21 failures, no reviews due and no coverage left, so 9 spare slots.
# The spares go to second questions on the real misses of the last batch and the
# standards still failing most: a ratio part (BT2), percent of / whole (BS10, BM10),
# subtracting rationals (BK10, BM1), a 3-digit row slip (BU2), the trapezoid (BL4, BO3,
# BR4), letters in an equation (BU3), an expression with brackets, an inequality, and
# cubic units (BS7, BU1, BM9: an area or length unit on a volume, three times).
# Departures, from the diagnoses:
# - 5.MD.C.5 and 6.G.A.2: the misses are units only, so both require a cubic unit.
# - 6.G.A.1: the triangle miss was cm³ for an area, so the unit is required.
# - 7.RP.A.3: every miss gave the other part of the ratio, so one sheet asks for the
#   first-named part and the other for the second.
def test_bv():
    qs = []
    v = F(19, 8) + F(11, 6)
    assert v == F(101, 24)
    qs.append(Q("Mia walks 2 3/8 km to the park, then 1 5/6 km to the shop. How far does she walk "
                "in all?", f"{mixed(v)} km", [f"{mixed(v)} km", f"{mixed(v)}km", f"{frac(v)} km"],
                True, "Common denominator 24: 2 9/24 + 1 20/24 = 3 29/24 = 4 5/24 km",
                "g5fword_add", "km"))
    boys = F(36 * 5, 5 + 4)
    assert boys == 20
    qs.append(Q("A club has 5 boys for every 4 girls. There are 36 children in all. How many are "
                "boys?", str(boys), [str(boys), f"{boys} boys"], False,
                "5 + 4 = 9 in each group, 36 ÷ 9 = 4 groups, 4 × 5 = 20 boys", "g7ratio_multi"))
    forms = ["d = 12h", "d=12h", "d = 12 × h", "d=12×h", "12h = d", "12h=d"]
    qs.append(Q("Hours h: 1, 2, 3. Pay d: 12, 24, 36 dollars. Write an equation for the pay d "
                "after h hours.", forms[0], forms, False,
                "Each hour adds $12, and the pay depends on the hours: d = 12h", "g6tableeq"))
    v = F(12 * 15, 2)
    assert v == 90
    qs.append(Q("A triangle has a base of 12 cm and a height of 15 cm. What is its area?",
                f"{v} cm²", [f"{v} cm²", f"{v} cm2", f"{v} square cm", f"{v} sq cm"], True,
                "Half of base × height: 12 × 15 = 180, half is 90 cm²", "g6trimath", "cm²"))
    v = F(-4, 5) / F(2, 15)
    assert v == -6
    qs.append(Q("Work out (–4/5) ÷ (2/15)", f"–{-v}", [f"–{-v}", f"-{-v}"], False,
                "Multiply by the flipped divisor: 4/5 × 15/2 = 60/10 = 6. One negative, so –6",
                "g7ratdiv"))
    grid = {"kind": "grid", "size": 7, "points": {"P": [5, 2], "Q": [2, 6]}}
    px, py = grid["points"]["P"]
    qs.append(Q("Write the coordinates of point P.", f"({px}, {py})",
                [f"({px}, {py})", f"({px},{py})", f"{px}, {py}", f"{px},{py}"], False,
                "Across 5 first, then up 2: (5, 2)", "g5coord", figure=grid))
    qs.append(Q("A bottle and a mug take up exactly the same amount of space. Which is the same for "
                "both: area, perimeter or volume? Write the word.", "volume",
                ["volume", "Volume"], False, "The space an object takes up is its volume",
                "g5volspace"))
    v = F(28) / F(35, 100)
    assert v == 80
    qs.append(Q("28 is 35% of a number. What is the number?", str(v), [str(v)], False,
                "35% is 28, so 5% is 4 and 100% is 80", "whole"))
    forms = ["L < 600", "L<600", "600 > L", "600>L"]
    qs.append(Q("A lift can only carry a load that is less than 600 kg. Write an inequality for the "
                "load L the lift can carry.", forms[0], forms, False,
                "Less than 600, not equal to it: L < 600", "g6ineqwrite"))
    v = 748 * 569
    qs.append(Q("Work out 748 × 569", str(v), [str(v), f"{v:,}"], False,
                "748 × 9 = 6732, 748 × 60 = 44880, 748 × 500 = 374000; add: 425612", "g5mul33"))
    return qs


def test_bw():
    qs = []
    v = -F(10, 3) + 10 + -F(8, 3)
    assert v == 4
    qs.append(Q("Work out –3 1/3 + 10 + (–2 2/3)", str(v), [str(v)], False,
                "Group the negatives: –3 1/3 + (–2 2/3) = –6. Then –6 + 10 = 4", "g7rat"))
    v = 3407 * 46
    qs.append(Q("Work out 3407 × 46", str(v), [str(v), f"{v:,}"], False,
                "3407 × 6 = 20442, 3407 × 40 = 136280; add: 156722", "g5mul24"))
    v = F(21, 4) * F(2, 3)
    assert v == F(7, 2)
    qs.append(Q("A rope is 5 1/4 m long. Ana uses 2/3 of it. How many meters does she use?",
                f"{mixed(v)} m", [f"{mixed(v)} m", f"{mixed(v)}m", f"{frac(v)} m", "3.5 m"], True,
                "5 1/4 = 21/4, and 2/3 × 21/4 = 42/12 = 3 1/2 m", "g5fmulword", "m"))
    forms = ["5w – 8", "5w - 8", "5w–8", "5w-8", "5 × w – 8", "5×w–8"]
    _expr_ok(forms, 5 * 4 - 8, w=4)
    qs.append(Q("Write an expression for: 8 less than 5 times w.", forms[0], forms, False,
                "5 times w is 5w; 8 less than that takes 8 away: 5w – 8", "g6expr_write"))
    qs.append(Q("The point (4, –7) is reflected across the x-axis. Write the new point.", "(4, 7)",
                ["(4, 7)", "(4,7)", "4, 7", "4,7"], False,
                "Reflecting across the x-axis flips the sign of y only: (4, –7) goes to (4, 7)",
                "g6reflect"))
    v = F(9, 2) * F(8, 3)
    assert v == 12
    qs.append(Q("A prism has a base area of 4 1/2 cm² and a height of 2 2/3 cm. What is its "
                "volume?", f"{v} cm³", [f"{v} cm³", f"{v} cm3", f"{v} cubic cm"], True,
                "V = bh: 9/2 × 8/3 = 72/6 = 12 cm³", "g6volbh_math", "cm³"))
    qs.append(Q("The mean height of 25 plants is 14 cm. Does the mean describe the data set with one "
                "number or many numbers? Write one or many.", "one", ["one", "One", "1"], False,
                "A mean is a single number that sums up the whole set", "g6distone"))
    yellow = F(45 * 2, 2 + 7)
    assert yellow == 10
    qs.append(Q("A paint mix uses 2 cans of yellow for every 7 cans of blue. There are 45 cans in "
                "all. How many are yellow?", str(yellow), [str(yellow), f"{yellow} cans"], False,
                "2 + 7 = 9 cans in each batch, 45 ÷ 9 = 5 batches, 5 × 2 = 10 yellow", "g7ratio_multi"))
    v = F(20 + 12, 2) * 5
    assert v == 12 * 5 + 2 * F(4 * 5, 2)
    qs.append(Q("A garden is a trapezoid. Its parallel sides are 20 m and 12 m, and the height "
                "between them is 5 m. What is its area?", f"{v} m²",
                [f"{v} m²", f"{v} m2", f"{v} square meters", f"{v} sq m"], True,
                "Rectangle 12 × 5 = 60, plus two triangles 4 × 5 ÷ 2 = 10 each: 80 m²", "g6quadrw", "m²"))
    forms = ["c = 9t", "c=9t", "c = 9 × t", "c=9×t", "9t = c", "9t=c"]
    qs.append(Q("Each ticket costs $9. Write an equation for the total cost c of t tickets.",
                forms[0], forms, False, "Cost depends on tickets: $9 for each, so c = 9t", "g6depvar"))
    return qs


def test_bx():
    qs = []
    v = 7 ** 3
    qs.append(Q("A cube has edges of 7 m. What is its volume?", f"{v} m³",
                [f"{v} m³", f"{v} m3", f"{v} cubic m", f"{v} cubic meters"], True,
                "7 × 7 = 49 m² for the base; 49 × 7 = 343 m³", "g5vol_math", "m³"))
    import math
    g = math.gcd(36, 60)
    a, b = 36 // g, 60 // g
    assert g == 12 and math.gcd(a, b) == 1
    forms = [f"{g}({a} + {b})", f"{g} × ({a} + {b})", f"{g}({a}+{b})", f"{g}×({a}+{b})",
             f"({a} + {b}) × {g}", f"({a}+{b})×{g}"]
    qs.append(Q("Write 36 + 60 as a number times a sum of two numbers that have no common factor.",
                forms[0], forms, False, f"GCF of 36 and 60 is {g}: 36 + 60 = {g} × {a} + {g} × {b} "
                f"= {g}({a} + {b})", "g6gcfsum"))
    forms = ["5(3y + 7)", "5 × (3y + 7)", "5(3y+7)", "5×(3y+7)", "(3y + 7) × 5", "(3y+7)×5"]
    _expr_ok(forms, 15 * 2 + 35, y=2)
    qs.append(Q("Factor 15y + 35 using the greatest common factor of 15 and 35.", forms[0], forms,
                False, "GCF is 5: 15y = 5 × 3y and 35 = 5 × 7, so 5(3y + 7)", "g6factor"))
    forms = ["k > –4", "k > -4", "k>-4", "k>–4", "–4 < k", "-4 < k", "-4<k"]
    qs.append(Q("Write an inequality that says the number k is greater than –4.", forms[0], forms,
                False, "Greater than –4, not equal to it: k > –4", "g6ineqmath"))
    v = D(180) * D("0.45")
    assert v == 81
    qs.append(Q("Find 45% of 180.", dec(v), [dec(v)], False,
                "10% is 18, so 40% is 72; 5% is 9: 72 + 9 = 81", "g6pct_of"))
    v = F(12, 8)
    qs.append(Q("A recipe uses 12 cups of flour for 8 cups of sugar. How many cups of flour is that "
                "for each cup of sugar?", mixed(v), [mixed(v), frac(v), "1.5", f"{mixed(v)} cups"],
                False, "12 : 8 as a unit rate is 12/8 = 1 1/2 cups of flour per cup of sugar",
                "g6unitrate_ab"))
    qs.append(Q("Each box holds 6 eggs. Ana has 42 eggs in x boxes. Which equation fits? "
                f"{_nb('A: x + 6 = 42')}  {_nb('B: 6x = 42')}  {_nb('C: 42x = 6')}. Write A, B or C.",
                "B", ["B"], False, "x boxes of 6 eggs is 6x, and that is 42: 6x = 42", "g6eqrep_px"))
    v = -F(13, 8) - F(27, 8)
    assert v == -5
    qs.append(Q("Work out –1 5/8 – 3 3/8", f"–{-v}", [f"–{-v}", f"-{-v}"], False,
                "Both go down: –1 5/8 – 3 3/8 = –(1 5/8 + 3 3/8) = –5", "g7ratsub"))
    forms = ["3(n + 9)", "3(n+9)", "3 × (n + 9)", "3×(n+9)", "(n + 9) × 3", "(n+9)×3",
             "3n + 27", "3n+27"]
    _expr_ok(forms, 3 * (4 + 9), n=4)
    qs.append(Q("Write an expression for: 3 times the sum of n and 9.", forms[0], forms, False,
                "The sum of n and 9 is n + 9; 3 times all of it needs brackets: 3(n + 9)",
                "g6expr_write"))
    qs.append(Q("Which unit could measure the volume of a fish tank: m, m² or m³?", "m³",
                ["m³", "m3", "cubic m", "cubic meters"], False,
                "Volume is counted in cubes: cubic meters, m³", "g5volunit"))
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



def _ops_unique(v1, v2, v3, want):
    """The one +/- pair that makes the equation true - and assert it is the only
    one, so the puzzle has a single answer a child can be marked against."""
    from itertools import product as _product
    hits = []
    for ops in _product("+-", repeat=2):
        tot = v1
        for op, v in zip(ops, (v2, v3)):
            tot = tot + v if op == "+" else tot - v
        if tot == want:
            hits.append(" ".join(ops))
    assert len(hits) == 1, (v1, v2, v3, want, hits)
    return hits[0]


def _digits_unique(target, digits=(1, 2, 3, 4, 5, 6)):
    """The one way to place the digits in  a b/c - d e/f = target.

    Brute-forced rather than trusted: a second solution would make the question
    unmarkable, and that is not visible by eye.
    """
    from itertools import permutations as _perms
    hits = [s for s in _perms(digits)
            if s[1] < s[2] and s[4] < s[5]
            and (s[0] + F(s[1], s[2])) - (s[3] + F(s[4], s[5])) == target]
    assert len(hits) == 1, (target, hits)
    s = hits[0]
    return f"{s[0]} {s[1]}/{s[2]} - {s[3]} {s[4]}/{s[5]}"


def _ops_q(v1, v2, v3, want, skill="g5fpuzzle_op"):
    ans = _ops_unique(v1, v2, v3, want)
    # Underscores, not a box glyph: the PDF font has no ☐ and substitutes a
    # solid black square, which reads like a redaction rather than a blank.
    text = (f"Write + or – in each blank so the equation is true:   "
            f"{mixed(v1)} ___ {mixed(v2)} ___ {mixed(v3)} = {mixed(want)}.   "
            f"Write the two signs in order.")
    acc = [ans, ans.replace(" ", ""), ans.replace("-", "−"), ans.replace(" ", ",")]
    return Q(text, ans, acc, False,
             f"Try the pairs: only {ans} gives {mixed(want)}", skill)


def _digit_q(target, skill="g5fpuzzle_digit"):
    ans = _digits_unique(target)
    text = ("Use each of the digits 1 to 6 exactly once to fill the blanks:   "
            f"__ __/__  –  __ __/__  =  {mixed(target)}.   "
            "Write the completed subtraction.")
    acc = [ans, ans.replace(" ", ""), ans.replace("-", "−")]
    return Q(text, ans, acc, False,
             f"Only one arrangement works: {ans}", skill)


def _equal_q(a, b, unit, skill="g5fequal"):
    """Pour from the fuller container so both hold the same."""
    move, end = (a - b) / 2, (a + b) / 2
    text = (f"One bottle holds {mixed(a)} {unit} of water and another holds {mixed(b)} {unit}. "
            f"How much must be poured from the first into the second so that both hold "
            f"the same amount?")
    ans = f"{mixed(move)} {unit}"
    return Q(text, ans, [ans, f"{frac(move)} {unit}"], True,
             f"The difference is {mixed(a - b)}; half of it moves across, so each ends with "
             f"{mixed(end)} {unit}", skill, unit)


def _estimate_q(a, b, op, skill="g5fbench"):
    """Round each mixed number to the nearest whole, then combine."""
    est = round(a) + round(b) if op == "+" else round(a) - round(b)
    exact = a + b if op == "+" else a - b
    text = (f"Without working it out exactly, estimate {mixed(a)} {op} {mixed(b)} "
            f"by rounding each number to the nearest whole number.")
    ans = str(est)
    return Q(text, ans, [ans, f"about {est}", f"≈ {est}", f"~{est}", f"≈{est}"], False,
             f"{mixed(a)} rounds to {round(a)} and {mixed(b)} rounds to {round(b)}, "
             f"so about {est} (exactly {mixed(exact)})", skill)


def test_ac():
    """Fractions 1 of 3: heuristics (choose the operators, place the digits,
    equalise, estimate) alongside the four operations on fractions."""
    qs = [
        _ops_q(F(7, 2), F(2, 3), F(1, 6), F(4)),
        _digit_q(F(19, 12)),
        _equal_q(F(9, 4), F(5, 4), "cups"),
        _estimate_q(F(29, 6), F(23, 8), "+"),
    ]
    v = F(11, 4) + F(11, 6)
    qs.append(Q("Work out 2 3/4 + 1 5/6", mixed(v), [mixed(v), frac(v)], False,
                "Twelfths: 2 9/12 + 1 10/12 = 3 19/12 = 4 7/12", "g5mixadd"))
    v = F(21, 4) - F(8, 3)
    qs.append(Q("Work out 5 1/4 – 2 2/3", mixed(v), [mixed(v), frac(v)], False,
                "Twelfths: 5 3/12 – 2 8/12, borrow one whole", "g5mixsub"))
    v = F(3, 5) * F(5, 9)
    qs.append(Q("Work out 3/5 × 5/9", frac(v), [frac(v), "15/45"], False,
                "Multiply across: 15/45, then simplify", "g5fmul"))
    v = F(1, 4) / 5
    qs.append(Q("Work out 1/4 ÷ 5", frac(v), [frac(v)], False,
                "A quarter shared between 5 is a twentieth", "g5fdiv"))
    qs.append(Q("Without multiplying, is 7/8 × 12 greater than 12, less than 12, or equal "
                "to 12?", "less than 12", ["less than 12", "less", "smaller", "less than"],
                False, "7/8 is less than 1, so the product is smaller than 12", "g5scale"))
    v = F(2, 3) * F(9, 2)
    qs.append(Q("A recipe needs 4 1/2 cups of flour. How much is 2/3 of that?",
                f"{mixed(v)} cups", [f"{mixed(v)} cups", f"{frac(v)} cups"], True,
                "2/3 × 9/2 = 18/6 = 3 cups", "g5fmulword", "cups"))
    return qs


def test_ad():
    """Fractions 2 of 3."""
    qs = [
        _ops_q(F(9, 2), F(5, 8), F(7, 8), F(3)),
        _digit_q(F(13, 4)),
        _equal_q(F(3, 2), F(3, 4), "liter"),
        _estimate_q(F(39, 8), F(11, 10), "-"),
    ]
    v = F(7, 4)
    qs.append(Q("Seven oranges are shared equally between 4 children. How much does each "
                "child get?", mixed(v), [mixed(v), frac(v)], False,
                "7 ÷ 4 = 7/4 = 1 3/4 of an orange each", "g5fasdiv"))
    v = F(3, 8) + F(5, 12)
    qs.append(Q("Work out 3/8 + 5/12", frac(v), [frac(v)], False,
                "Twenty-fourths: 9/24 + 10/24", "g5fadd"))
    v = F(7, 9) - F(1, 6)
    qs.append(Q("Work out 7/9 – 1/6", frac(v), [frac(v)], False,
                "Eighteenths: 14/18 – 3/18", "g5fsub"))
    v = F(5, 6) - F(3, 8)
    qs.append(Q("A ribbon is 5/6 of a meter long. A piece 3/8 of a meter is cut off. "
                "How much is left?", f"{frac(v)} m", [f"{frac(v)} m", frac(v)], True,
                "Twenty-fourths: 20/24 – 9/24 = 11/24 m", "g5fword_sub", "m"))
    qs.append(Q("Without multiplying, is 5/4 × 20 greater than 20, less than 20, or equal "
                "to 20?", "greater than 20", ["greater than 20", "greater", "more", "bigger",
                                              "greater than"], False,
                "5/4 is more than 1, so the product is larger than 20", "g5scale"))
    v = F(6) / F(1, 3)
    qs.append(Q("How many thirds are there in 6? (Work out 6 ÷ 1/3)", frac(v), [frac(v)], False,
                "Each whole holds 3 thirds, so 6 wholes hold 18", "g5fdiv"))
    return qs


def test_ae():
    """Fractions 3 of 3."""
    qs = [
        _ops_q(F(5, 2), F(1, 3), F(5, 6), F(3)),
        _digit_q(F(19, 6)),
        _equal_q(F(7, 8), F(3, 8), "kg"),
        _estimate_q(F(31, 6), F(29, 10), "+"),
    ]
    v = F(7, 3) + F(7, 4)
    qs.append(Q("A jug holds 2 1/3 liters and a bottle holds 1 3/4 liters. How much do they "
                "hold altogether?", f"{mixed(v)} liters",
                [f"{mixed(v)} liters", f"{frac(v)} liters", f"{mixed(v)} l"], True,
                "Twelfths: 2 4/12 + 1 9/12 = 3 13/12 = 4 1/12 liters", "g5fword_add", "l"))
    v = F(3, 2) * F(2, 3)
    qs.append(Q("Work out 1 1/2 × 2/3", frac(v), [frac(v), "1"], False,
                "3/2 × 2/3 = 6/6 = 1", "g5fmulword"))
    v = F(1, 6) / 4
    qs.append(Q("Work out 1/6 ÷ 4", frac(v), [frac(v)], False,
                "A sixth shared between 4 is a twenty-fourth", "g5fdiv"))
    qs.append(Q("Without adding exactly, is 5/8 + 2/5 greater than 1 or less than 1?",
                "greater than 1", ["greater than 1", "greater", "more than 1", "more",
                                   "bigger", "greater than"], False,
                "5/8 is more than a half and 2/5 is nearly a half, so the sum passes 1",
                "g5fbench"))
    v = F(5, 8)
    qs.append(Q("Five pizzas are shared equally between 8 friends. How much pizza does each "
                "friend get?", frac(v), [frac(v)], False,
                "5 ÷ 8 = 5/8 of a pizza each", "g5fasdiv"))
    v = F(3, 4) * F(2, 3)
    qs.append(Q("A path is 3/4 of a mile long. Maya walks 2/3 of the way along it. "
                "How far does she walk?", f"{frac(v)} miles",
                [f"{frac(v)} miles", f"{frac(v)} mile"], True,
                "2/3 × 3/4 = 6/12 = 1/2 of a mile", "g5fmulword", "miles"))
    return qs

A, B, C, Dd, E, Ff, G, Hh, I, J, K, Ll, M = (test_a(), test_b(), test_c(), test_d(), test_e(), test_f(),
                                             test_g(), test_h(), test_i(), test_j(), test_k(), test_l(),
                                             test_m())
N, O, P = test_n(), test_o(), test_p()
Qq, R, S = test_q(), test_r(), test_s()
T, U, V = test_t(), test_u(), test_v()
Wq, Xq, Yq = test_w(), test_x(), test_y()
Zq, AAq, ABq = test_z(), test_aa(), test_ab()
AFq, AGq, AHq = test_af(), test_ag(), test_ah()
AIq, AJq, AKq = test_ai(), test_aj(), test_ak()
ALq, AMq, ANq = test_al(), test_am(), test_an()
AOq, APq, AQq = test_ao(), test_ap(), test_aq()
ARq, ASq, ATq = test_ar(), test_as(), test_at()
AUq, AVq, AWq = test_au(), test_av(), test_aw()
AXq, AYq, AZq = test_ax(), test_ay(), test_az()
BAq, BBq, BCq = test_ba(), test_bb(), test_bc()
BDq, BEq, BFq = test_bd(), test_be(), test_bf()
BGq, BHq, BIq = test_bg(), test_bh(), test_bi()
BJq, BKq, BLq = test_bj(), test_bk(), test_bl()
BMq, BNq, BOq = test_bm(), test_bn(), test_bo()
BPq, BQq, BRq = test_bp(), test_bq(), test_br()
BSq, BTq, BUq = test_bs(), test_bt(), test_bu()
BVq, BWq, BXq = test_bv(), test_bw(), test_bx()
ACq, ADq, AEq = test_ac(), test_ad(), test_ae()

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
WRONG["Q"] = {
    1: {f"{40 * 25} cm³": "Multiplied only two of the edges, as on Test K",
        f"{40 + 25 + 30} cm³": "Added the edges instead of multiplying them",
        f"{40 * 25 * 30} cm": "Correct number, but a volume needs cubic units",
        str(40 * 25 * 30): "Correct number, but no units"},
    2: {"9 cups": "Added instead of scaling: flour went up by 6, so added 6 to the milk",
        f"{mixed(F(8 * 2, 3))} cups": "Used the ratio upside down: 8 × 2/3",
        "12": "Correct number, but no units"},
    3: {"6": "Gave the x-coordinate, the distance across, not up", "8": "Added the two coordinates, as on Test L"},
    4: {"9 kg": "Counted the bags (the x marks) instead of adding the weights", "9": "Counted the bags",
        f"{mixed(F(1, 8) + F(1, 4) + F(1, 2) + F(3, 4))} kg": "Added each weight once, ignoring how many x marks it has",
        mixed(F(31, 8)): "Correct number, but no units"},
    5: {"1": "Dropped the minus sign",
        "–4": "Added the sizes and kept the minus sign, moving away from zero (as on Tests G and I)",
        "-4": "Added the sizes and kept the minus sign, moving away from zero (as on Tests G and I)"},
    6: {"A, B, C": "Counted the trapezoid, which has only one pair of parallel sides, as on Test M",
        "C": "Counted only the shape with right angles; a parallelogram need not have them"},
    7: {"A": "Picked a question with one answer", "C": "Picked a question with one answer"},
    8: {str((3 * 4) ** 2 + 2): "Squared 3x instead of only x", str(3 * 4 * 2 + 2): "Multiplied by 2 instead of squaring"},
    9: {"12a + 5": "Multiplied only the first term by 4", "12a+5": "Multiplied only the first term by 4"},
    10: {"8": "Gave the median (the middle value), not the mean", "35": "Added the scores but did not divide by 5",
         "11": "Gave the range, not the mean"},
}
WRONG["R"] = {
    1: {usd(D(80) * D("0.85")): "Combined –25% and +10% into –15%",
        usd(D(80) * D("0.75")): "Applied only the discount",
        usd(D(80) * D("0.75") + 8): "Added 10% of the original price instead of the sale price",
        "66": "Correct number, but no $ sign", "66.00": "Correct number, but no $ sign"},
    3: {"yes": "Accepted adding the tops and the bottoms (2 + 1 over 5 + 2) without checking its size",
        "Yes": "Accepted adding the tops and the bottoms (2 + 1 over 5 + 2) without checking its size"},
    4: {"greater than": "Thought multiplying always makes a number bigger", "greater": "Thought multiplying always makes a number bigger"},
    5: {f"{mixed(F(8, 3) / 4)} cups": "Read '3/4 of' as dividing by 4, as on Test I",
        f"{mixed(F(8, 3) - F(3, 4))} cups": "Subtracted 3/4 instead of finding 3/4 of it",
        "2": "Correct number, but no units"},
    6: {"n – 8 ÷ 2": "Left out the parentheses, so only 8 is divided by 2",
        "n-8÷2": "Left out the parentheses, so only 8 is divided by 2",
        "(n ÷ 8) ÷ 2": "Read 'difference' as division, as on Test P",
        "(8 – n) ÷ 2": "Wrote the difference the wrong way round"},
    7: {dec(D(6) / 150): "Divided the wrong way round: 6 ÷ 150, as on Test O"},
    8: {"144": "Gave the least common multiple, not the greatest common factor",
        "6": "Found a common factor, but not the greatest", "4": "Found a common factor, but not the greatest"},
    9: {"15": "Dropped the minus sign: below sea level is negative"},
    10: {"yes": "Multiplied only the x by 2, not the 3 as well", "Yes": "Multiplied only the x by 2, not the 3 as well"},
}
WRONG["S"] = {
    1: {"36": "Added 6 to y because x went up by 6, instead of multiplying"},
    2: {str((135 - 15) // 30): "Took off the monthly fee and divided by the joining fee, as on Test K",
        str(135 // 15): "Divided the total by 15 without taking off the $30 first"},
    3: {"–15": "Kept a minus sign: two negatives make a positive, as on Test J",
        "-15": "Kept a minus sign: two negatives make a positive, as on Test J"},
    4: {dec(D("0.065") * 100): "Moved the point two places, as on Test L",
        dec(D("0.065") * 10): "Moved the point one place",
        dec(D("0.065") / 1000): "Divided by 1000 instead of multiplying"},
    5: {"18": "Wrote only Pattern A's term, not the pair", "(9, 18)": "Wrote the pair the wrong way round (B, A)",
        "(14, 7)": "Gave the 4th pair, not the 5th"},
    6: {"2-9": "Wrote the smallest and largest as an interval, not their difference, as on Test P",
        "2 – 9": "Wrote the smallest and largest as an interval, not their difference, as on Test P",
        "2 to 9": "Wrote the smallest and largest as an interval, not their difference, as on Test P",
        "9": "Gave the largest value, not the range"},
    7: {"A": "Picked the range, which measures spread, not center", "C": "Picked a single value, not a summary"},
    8: {"16 cups": "Added instead of scaling: rice went up by 6, so added 6 to the water", "16": "Added instead of scaling"},
    9: {"A": "Picked the lower total price instead of comparing the price of one pen"},
    10: {"8": "Worked it out instead of writing the expression",
         "20 – 4 ÷ 2": "Left out the parentheses, so the division would happen first",
         "20-4÷2": "Left out the parentheses, so the division would happen first"},
}
WRONG["T"] = {
    1: {f"{60 * 40} cm³": "Multiplied only two of the edges, as on Test K",
        f"{60 + 40 + 35} cm³": "Added the edges instead of multiplying them",
        f"{60 * 40 * 35} cm": "Correct number, but a volume needs cubic units",
        str(60 * 40 * 35): "Correct number, but no units"},
    2: {"16": "Added instead of scaling: blue went up by 12, so added 12 to the white",
        "16 cans": "Added instead of scaling: blue went up by 12, so added 12 to the white",
        mixed(F(15 * 3, 4)): "Used the ratio upside down: 15 × 3/4"},
    3: {dec(D(50) / 4): "Divided the total by 4 without taking off the $14 first",
        str((50 + 14) // 4): "Added the $14 instead of taking it off"},
    4: {"–16": "Kept a minus sign: two negatives make a positive",
        "-16": "Kept a minus sign: two negatives make a positive",
        "9": "Multiplied by 3/4 instead of dividing", "–9": "Multiplied by 3/4 and kept a minus sign",
        "-9": "Multiplied by 3/4 and kept a minus sign"},
    5: {"less than": "Thought multiplying by a fraction always makes a number smaller, as on Test L",
        "less": "Thought multiplying by a fraction always makes a number smaller, as on Test L"},
    6: {"–9": "Kept one minus sign: the opposite of –9 is 9", "-9": "Kept one minus sign: the opposite of –9 is 9"},
    7: {"–8": "Took the bigger-looking number as further right", "-8": "Took the bigger-looking number as further right"},
    8: {"h = 40c": "Wrote the equation the wrong way round: the cost depends on the hours",
        "c = 40 + h": "Added the hours instead of multiplying"},
    9: {usd(D(20) - D("2.45")): "Took off the price of one notebook, not three",
        usd(3 * D("2.45")): "Found the cost, not the change",
        "12.65": "Correct number, but no $ sign"},
    10: {"0.407": "Took the longer decimal as the larger one"},
}
WRONG["U"] = {
    1: {usd(D(120) * D("0.95")): "Combined +15% and –20% into –5%",
        usd(D(120) * D("0.8")): "Applied only the decrease", usd(D(120) * D("1.15")): "Applied only the increase",
        "110.40": "Correct number, but no $ sign", "110.4": "Correct number, but no $ sign"},
    3: {"(1, 4)": "Wrote the distances the wrong way round: from the y-axis is x", "(1,4)": "Wrote the distances the wrong way round"},
    4: {"2": "Dropped the minus sign", "–7 1/3": "Added the sizes and kept the minus sign, as on Tests G and I",
        "-7 1/3": "Added the sizes and kept the minus sign, as on Tests G and I"},
    5: {dec(D("36.5") / 10): "Moved the point one place", dec(D("36.5") / 1000): "Moved the point three places",
        dec(D("36.5") * 100): "Multiplied by 100 instead of dividing"},
    6: {"4": "Picked a value that does not make it true: 3 × 4 + 4 = 16",
        "6": "Picked a value that does not make it true: 3 × 6 + 4 = 22"},
    7: {"h < 48": "Wrote the inequality the wrong way round", "h ≥ 48": "Included 48, but the rule says taller than"},
    8: {"–12": "Kept the sign: absolute value is a distance, never negative",
        "-12": "Kept the sign: absolute value is a distance, never negative"},
    9: {frac(F(3 + 2, 4 + 9)): "Added the numerators and the denominators",
        frac(F(3, 4) * F(9, 2)): "Flipped the second fraction, as if dividing"},
    10: {"9": "Correct number, but no units", "9 cm": "Correct number, but a volume needs cubic units"},
}
WRONG["V"] = {
    1: {"25": "Added 4 to y because x went up by 4, instead of multiplying, as on Test S"},
    2: {"5 cups": "Found the total but did not share it among the glasses",
        "8": "Counted the glasses", mixed(F(5, 8)): "Correct number, but no units"},
    3: {f"{frac(F(3 + 2, 4 + 3))} miles": "Added the numerators and the denominators: 3/4 + 2/3 = 5/7",
        mixed(F(17, 12)): "Correct number, but no units"},
    4: {usd(D(12) / 3): "Divided the wrong way round: 12 ÷ 3, as on Test O",
        "0.25": "Correct number, but no $ sign"},
    5: {f"{mixed(F(9, 2) / F(2, 3))} m": "Divided by 2/3 instead of finding 2/3 of the length",
        f"{mixed(F(9, 2) / 3)} m": "Found 1/3 of the length instead of 2/3",
        "3": "Correct number, but no units"},
    6: {"1080 feet": "Multiplied by 12 instead of dividing", "1080": "Multiplied by 12 instead of dividing"},
    7: {"Oslo": "Took the bigger-looking number as colder"},
    8: {"–$25": "Took the greater balance as the bigger debt", "-$25": "Took the greater balance as the bigger debt",
        "–25": "Took the greater balance as the bigger debt", "-25": "Took the greater balance as the bigger debt"},
    10: {"no": "Did not apply the rectangle's attributes to the square", "No": "Did not apply the rectangle's attributes to the square"},
}
WRONG["W"] = {4: {"–5": "Right size, wrong sign: carried a minus through instead of applying that two negative factors make a positive",
                   "-5": "Right size, wrong sign: carried a minus through instead of applying that two negative factors make a positive"}}
WRONG["X"] = {}
WRONG["BD"] = {}
WRONG["BE"] = {}
WRONG["BF"] = {}
WRONG["BG"] = {
    1: {"2": "Combined the whole numbers only and dropped the fractions (–2 + 5 – 1), as on BE1"},
    2: {"A": "Multiplied for a how-many-groups problem instead of dividing, as on BE2 and BE10",
        "B": "Divided the wrong way round: the size of a cake by the flour in the bag"},
    3: {"95": "Substituted the GCF 5 for x and worked out 15(5) + 20 instead of factoring, as on BE3"},
    4: {colswap("12.05", "7.38"): "Took the smaller digit from the larger in each column instead of borrowing"},
    5: {"3.6": "Found 30% of 12 instead of the number that 12 is 30% of"},
    6: {"cm²": "Gave a unit of area, not volume", "cm": "Gave a unit of length, not volume"},
    8: {"B": "Reversed the direction: at most means ≤, not ≥",
        "C": "Swapped the fixed charge and the charge per mile"},
    9: {"6.4": "Moved the decimal point one place instead of three"},
}
WRONG["BH"] = {
    1: {"5 liters": "Found the total but did not share it among the 8 beakers",
        "5 liter": "Found the total but did not share it among the 8 beakers"},
    2: {"90": "Added 36 + 54 instead of factoring out the common factor, as on BF2",
        "6(6 + 9)": "Factored out a common factor but not the greatest; 6 and 9 still share 3",
        "9(4 + 6)": "Factored out a common factor but not the greatest; 4 and 6 still share 2"},
    3: {"one": "Thought only one number makes y > 4 true"},
    4: {"right": "Named the skew after where the data bunches, not the side of the tail, as on BF7"},
    5: {"no": "Treated square and rectangle as separate kinds instead of a square being a special rectangle"},
    6: {"$17.25": "Added 4.75 to 12.50 instead of subtracting", "17.25": "Added 4.75 to 12.50 instead of subtracting"},
    9: {"–2/3": "Two negatives multiply to a positive; kept a minus sign",
        "-2/3": "Two negatives multiply to a positive; kept a minus sign"},
    10: {"27/32": "Multiplied 9/4 × 3/8 instead of dividing, as on BE10"},
}
WRONG["BI"] = {
    1: {"b = 6p": "Letters swapped: the boxes made the subject, the same swap as on earlier sheets",
        "b=6p": "Letters swapped: the boxes made the subject, the same swap as on earlier sheets"},
    2: {"1 1/2 m": "Found 1/3 of the rope instead of 2/3",
        "5 1/6 m": "Added 2/3 to the length instead of multiplying"},
    4: {"67": "Squared 2x instead of only x: (2 × 4)² + 3"},
    5: {"1/3": "Turned the ratio upside down: sugar per cup of flour"},
    6: {"126 cm²": "Multiplied base × height and did not halve it"},
    8: {"0.407": "Took the number with more digits as the larger"},
    10: {"14y": "Added the numbers and the y terms together as if they were all like terms"},
}
_SIGN = "Right size, wrong sign"
WRONG["BJ"] = {
    1: {"1/4": f"{_SIGN}: lost the minus when 4 3/4 – 5 went below zero, as on AZ1",
        "–1": "Combined the whole numbers only (3 – 5 + 1) and dropped the fractions, as on BE1",
        "-1": "Combined the whole numbers only (3 – 5 + 1) and dropped the fractions, as on BE1"},
    2: {"98": "Added 42 + 56 instead of factoring out the common factor, as on BF2",
        "7(6 + 8)": "Factored out a common factor but not the greatest; 6 and 8 still share 2",
        "2(21 + 28)": "Factored out a common factor but not the greatest; 21 and 28 still share 7"},
    3: {"h > 140": "Reversed the direction: shorter than means less than",
        "h>140": "Reversed the direction: shorter than means less than",
        "h ≤ 140": "Included 140: shorter than means less than, not equal to it"},
    4: {"left": "Named the skew after where the data bunches, not the side of the tail, as on BF7 and BH4"},
    5: {"2/5": "Turned the ratio upside down: blue per can of white, as on BA9",
        "0.4": "Turned the ratio upside down: blue per can of white, as on BA9",
        "10": "Gave the first number of the ratio instead of dividing it by the second, as on BI5"},
    # 6: no stored wrong answers. "How many numbers does the median use" also reads as
    # "how many values it is computed from" (2 for 12 scores, the 6th and 7th), so the
    # question is ambiguous and was voided in the record. Ask it as BH7 did instead:
    # "Does the median describe the data set with one number or many numbers?"
    7: {"$8.50": "Added the change in notebooks (4) to the price instead of scaling, as on S1",
        "8.50": "Added the change in notebooks (4) to the price instead of scaling, as on S1"},
    8: {"28/9": "Multiplied 14/3 × 2/3 instead of dividing, as on BE10",
        "3 1/9": "Multiplied 14/3 × 2/3 instead of dividing, as on BE10"},
    9: {"120 ft²": "Multiplied base × height and did not halve it, as on BI6"},
    10: {"6": f"{_SIGN}: a negative divided by a positive is negative",
         "–3/32": "Multiplied by 1/8 instead of dividing by it",
         "-3/32": "Multiplied by 1/8 instead of dividing by it"},
}
WRONG["BK"] = {
    1: {"4 1/4 m": "Added every ribbon, not only those longer than 1/2 m"},
    2: {"2 1/4 L": "Found 1/3 of the tank instead of 2/3"},
    3: {"(2, –6)": "Swapped the two numbers, as on AX5", "(2, -6)": "Swapped the two numbers, as on AX5",
        "(6, 2)": "Reflected across the y-axis instead: flipped x, not y",
        "(6,2)": "Reflected across the y-axis instead: flipped x, not y"},
    4: {"7.5": "Moved the decimal point one place instead of two"},
    5: {"$195": "Added 25 + 40 first and then multiplied by 3, instead of multiplying first",
        "195": "Added 25 + 40 first and then multiplied by 3, instead of multiplying first"},
    6: {"A": "Wrote a multiplication equation for an add-on situation",
        "C": "Subtracted where stickers were added"},
    7: {"180": "Found the least common multiple instead of the greatest common factor"},
    # 8: voided in the record. "Typical value" is not a term the child has been taught, and
    # "which one number" fits all three options (the range is one number too). Word it as
    # BN7 did ("describes the middle"). Range sat in slot A on both misses (S7, BK8); keep
    # it out of A so a default guess of A cannot score or fail the question.
    10: {"1 1/4": "Subtracted the sizes (2 5/8 – 1 3/8) and dropped the sign",
         "4": f"{_SIGN}: both numbers go below zero, so the total is negative"},
}
WRONG["BL"] = {
    1: {"A": "Multiplied for a how-many-pieces problem instead of dividing, as on BE2, BG2",
        "C": "Divided the wrong way round: the piece by the whole ribbon"},
    2: {"6": "Wrote the GCF only, not the factored expression, as on AX10 and BC3",
        "132": "Substituted the GCF 6 for y and worked out 18(6) + 24 instead of factoring, as on BE3 and BG3",
        "3(6y + 8)": "Factored out a common factor but not the greatest; 6 and 8 still share 2",
        "2(9y + 12)": "Factored out a common factor but not the greatest; 9 and 12 still share 3"},
    3: {"–1 1/2": f"{_SIGN}: two negatives multiply to a positive, as on BH9",
        "-1 1/2": f"{_SIGN}: two negatives multiply to a positive, as on BH9",
        "–3/2": f"{_SIGN}: two negatives multiply to a positive, as on BH9",
        "-3/2": f"{_SIGN}: two negatives multiply to a positive, as on BH9"},
    4: {"64 m²": "Multiplied the sum of the parallel sides by the distance and did not halve it"},
    7: {"1/27": "Divided the wrong way round: gallons per mile, as on O9"},
    8: {"1.47": "Multiplied 4.20 × 0.35 instead of dividing",
        "$1.47": "Multiplied 4.20 × 0.35 instead of dividing"},
    9: {"A": "Divided where the problem is a multiplication, as on AX8",
        "C": "Divided where the problem is a multiplication, as on AX8"},
    10: {"76": "Squared 3a instead of only a: (3 × 3)² – 5"},
}
_TAKE = "Subtracted the smaller size from the larger and put a minus in front, instead of adding two negatives, as on BK10"
_HALF = "Halved the volume as if it were a triangle or pyramid, as on BK9"
WRONG["BM"] = {
    1: {f"–{mixed(F(19, 6) - F(11, 6))}": _TAKE, f"-{mixed(F(19, 6) - F(11, 6))}": _TAKE},
    2: {mixed(F(15, 4) * F(5, 8)): "Multiplied instead of dividing for a how-many-pieces problem, as on BE10"},
    3: {s: f"{_SIGN}: two negatives divide to a positive"
        for s in ("–2 1/2", "-2 1/2", "–5/2", "-5/2", "-2.5", "–2.5")},
    # 4: no stored wrong answers - same ambiguity as BJ6, and worse: a mean is computed
    # from all 30 values, so "30" is a defensible reading. Voided in the record.
    5: {"2/7": "Turned the ratio upside down: sugar per cup of flour, as on BA9",
        "14": "Gave the flour figure straight from the ratio instead of dividing, as on BI5",
        "14 cups": "Gave the flour figure straight from the ratio instead of dividing, as on BI5"},
    6: {"25": "Gave the white cans, not the red",
        "24": "Treated the 5 white cans as the whole: 40 ÷ 5 × 3"},
    7: {"108": "Multiplied the numbers: a common multiple, but not the least, as on AY4",
        "3": "Gave the greatest common factor, not the least common multiple, as on AY4"},
    8: {"8x + 5": "Multiplied the first term only, not the 5", "8x+5": "Multiplied the first term only, not the 5"},
    9: {"176 cm²": "Multiplied base × height and did not halve it, as on BI6"},
    10: {dec(D(26) * D("0.4")): "Found 40% of 26 instead of the whole"},
}
WRONG["BP"] = {
    1: {f"{2 + 1} {3 + 5}/{4 + 6} km":"Added the tops and added the bottoms: 2 3/4 + 1 5/6 as 3 8/10"},
    3: {"B": "Multiplied for a how-many-groups problem instead of dividing, as on BE2 and BG2",
        "A": "Divided the wrong way round: the scoop by the whole amount"},
    4: {"12": "Gave the apple cups, not the mango", "45": "Treated the 2 apple cups as the whole: 30 ÷ 2 × 3"},
    5: {s: f"{_SIGN}: two negatives divide to a positive" for s in ("–1 1/2", "-1 1/2", "–3/2", "-3/2")},
    6: {"15": "Dropped the sign: below zero is negative",
        "15 degrees": "Dropped the sign: below zero is negative"},
    7: {"4": "Gave the y-coordinate as the distance from the y-axis, as on O3 and W3",
        "11": "Added the two coordinates, as on L6"},
    8: {usd(4 * D("3.85")): "Gave the total cost, not the change",
        usd(D(30) - D("3.85")): "Took off one book only: did not multiply by 4"},
    10: {"5(t + 3)": "Added the fee to every ticket instead of once", "5(t+3)": "Added the fee to every ticket instead of once"},
}
WRONG["BQ"] = {
    1: {f"–{mixed(F(27, 8) - F(21, 8))}": _TAKE, f"-{mixed(F(27, 8) - F(21, 8))}": _TAKE,
        mixed(F(27, 8) - F(21, 8)): "Subtracted the smaller size from the larger and dropped the "
                                    "minus, instead of adding two negatives, as on BM1"},
    2: {f"{12 * 5 * 4} cm²": "Used square units for a volume"},
    3: {"7": "Wrote the GCF only, not the factored expression, as on BC3",
        "7(3 + 4)": "Dropped the variable y from the factored term, as on BL2",
        "7(3+4)": "Dropped the variable y from the factored term, as on BL2",
        str(21 * 7 + 28): "Substituted the GCF 7 for y and worked out 21(7) + 28 instead of factoring, as on BE3 and BG3"},
    4: {"w > 23": "Inequality sign the wrong way round", "w>23": "Inequality sign the wrong way round"},
    5: {s: "Built it in the order the words are spoken, 5 first, as on AG3" for s in ("5 – 2m", "5 - 2m", "5–2m", "5-2m")},
    6: {s: "Reflected across the x-axis instead of the y-axis" for s in ("(6, 3)", "(6,3)", "6, 3", "6,3")},
    7: {str((2 * 3) ** 2 + 5): "Squared 2k instead of only k: (2 × 3)² + 5"},
    8: {"A": "Chose a times equation where the problem says plus, as on BA6",
        "B": "Subtracted where the problem adds"},
    10: {"4.69": "Cut off after the hundredths instead of rounding up"},
}
WRONG["BR"] = {
    1: {"120": "Added 48 + 72 instead of factoring out the common factor, as on BF2",
        "24": "Wrote the GCF only, not the expression",
        **{f"{c}({48 // c} + {72 // c})": "Factored out a common factor but not the greatest"
           for c in (2, 3, 4, 6, 8, 12)}},
    2: {f"{mixed(F(9, 2) * F(1, 3))} cups": "Found 1/3 of the jug (the part left) instead of 2/3"},
    3: {s: "Letters swapped: the bags made the subject, as on AU7 and AV7" for s in ("b = 6a", "b=6a")},
    4: {f"{(14 + 10) * 6} ft²": "Multiplied the sum of the parallel sides by the height and did not halve it",
        f"{10 * 6 + 2 * (14 - 10) * 6} ft²": "Used the whole 4 ft difference on both sides as rectangles, as on BO3"},
    5: _skew_wrong(BRq[4]["answer"]),
    6: {dec(D(27) * D("0.3")): "Found 30% of 27 instead of the whole, as on BM10"},
    7: {"6": "Moved the decimal point in 0.35 one place but not in 21: worked out 21 ÷ 3.5"},
    8: {"8": _HALF, "10": "Gave the base area, not the volume"},
    10: {str(cubes_visible(5, 2, 4)): "Counted only the cubes that show, not the hidden ones"},
}
WRONG["BV"] = {
    2: {"16": "Gave the girls, not the boys: the other part of the ratio, as on BM6 and BT2",
        "4": "Wrote the number of groups instead of finishing, as on BP4"},
    3: {s: "Letters swapped: the hours made the subject, as on BU3" for s in ("h = 12d", "h=12d")},
    4: {"180 cm²": "Multiplied base by height and did not halve it"},
    5: {"6": f"{_SIGN}: a negative divided by a positive is negative",
        "–1/6": "Flipped the first fraction instead of the divisor: 5/4 × 2/15",
        "-1/6": "Flipped the first fraction instead of the divisor: 5/4 × 2/15"},
    6: {s: "Wrote the coordinates in the wrong order: up first, then across" for s in ("(2, 5)", "(2,5)", "2, 5", "2,5")},
    7: {"perimeter": "Chose perimeter for the space an object takes up, as on AY7 and BS9",
        "area": "Chose area for the space an object takes up"},
    8: {dec(D(28) * D("0.35")): "Worked out 35% of 28 instead of finding the whole that 28 is 35% of, as on BM10"},
}
WRONG["BW"] = {
    4: {s: "Built it in the order the words are spoken, 8 first, as on AG3" for s in ("8 – 5w", "8 - 5w", "8-5w")},
    5: {s: "Flipped the sign of x instead of y: that is a reflection across the y-axis"
        for s in ("(–4, –7)", "(-4, -7)", "(-4,-7)", "-4, -7")},
    8: {"35": "Gave the blue cans, not the yellow: the other part of the ratio, as on BT2",
        "5": "Wrote the number of batches instead of finishing, as on BP4"},
    9: {"160 m²": "Multiplied the sum of the parallel sides by the height and did not halve it"},
    10: {s: "Letters swapped: the tickets made the subject, as on BU3" for s in ("t = 9c", "t=9c")},
}
WRONG["BX"] = {
    2: {f"6({36 // 6} + {60 // 6})": "Took out a common factor but not the greatest",
        f"6({36 // 6}+{60 // 6})": "Took out a common factor but not the greatest"},
    3: {s: "Dropped the variable y from the factored term, as on BL2" for s in ("5(3 + 7)", "5(3+7)")},
    5: {dec(D(45) * 9 / 100): "Cancelled 180 down to 9 but kept the 100 below: the factor came off the "
        "top only, as on BS10"},
    6: {"2/3": "Turned the ratio upside down: sugar per cup of flour, as on BA9",
        "12": "Gave the flour figure straight from the ratio instead of dividing, as on BI5"},
    7: {"A": "Chose an addition equation where each box holds the same, as on BA6"},
    8: {"1 3/4": "Took the smaller number from the larger and dropped the sign, as on BK10 and BM1",
        "–1 3/4": "Took the smaller number from the larger and put a minus in front, as on BK10 and BM1",
        "-1 3/4": "Took the smaller number from the larger and put a minus in front, as on BK10 and BM1"},
    9: {s: "Multiplied only n by 3, not the whole sum" for s in ("3n + 9", "3n+9")},
    10: {"m²": "Chose a square unit, which measures area", "m": "Chose a length unit"},
}
WRONG["BS"] = {
    1: {f"{5 - 2} {(F(3, 4) - F(1, 3)).numerator}/{(F(3, 4) - F(1, 3)).denominator} L":
        "Took the smaller fraction from the larger (3/4 – 1/3) instead of regrouping, as on AY6"},
    2: {"12": "Missed one common factor of 2, as on BF9 where only some matching factors were circled"},
    3: {"A": "Divided where the problem is a multiplication, as on BL9",
        "C": "Divided where the problem is a multiplication, as on BL9"},
    4: {f"{(16 + 10) * 4} m²": "Multiplied the sum of the parallel sides by the height and did not halve it",
        f"{10 * 4 + 2 * (16 - 10) * 4} m²": "Used the whole 6 m difference on both sides as rectangles, as on BO3"},
    6: {str((3 * 5) ** 2 - 4): "Squared 3n instead of only n: (3 × 5)² – 4"},
    7: {"3": _HALF},
    8: {"A": "Did not see that 3 equal sides also counts as isosceles (at least 2), as on AX7"},
    9: {"A": "Chose perimeter for the space a box takes up, as on AY7"},
    10: {dec(D(68) * 3 / 20): "Cancelled a 5 from 340 and again from 15/100: the same factor twice, as on BL5"},
}
WRONG["BT"] = {
    1: {str(-5 + 9 - 2): "Combined the whole numbers and dropped the fractions, as on BE1"},
    2: {"24": "Gave the red beads, not the blue",
        "4": "Wrote a number from the ratio instead of finishing, as on BP4"},
    3: {"8": "Wrote the GCF only, not the factored expression, as on BC3",
        "8(3 + 5)": "Dropped the variable x from the factored term, as on BL2",
        "8(3+5)": "Dropped the variable x from the factored term, as on BL2",
        str(24 * 8 + 40): "Substituted the GCF 8 for x and worked out 24(8) + 40 instead of factoring, as on BE3 and BG3",
        "4(6x + 10)": "Factored out a common factor but not the greatest",
        "2(12x + 20)": "Factored out a common factor but not the greatest"},
    4: {"4(p + 7)": "Added 7 before multiplying by 4", "4(p+7)": "Added 7 before multiplying by 4"},
    5: _skew_wrong(BTq[4]["answer"]),
    6: {usd(6 * D("12.75")): "Gave the total cost, not the change"},
    7: {dec(D("6.85") + D("0.37")): "Lined up the last digits instead of the decimal points",
        dec(D("6.85") + D("3.7") - 1): "Dropped the carry into the ones, as on G4"},
    8: {"6": "Dropped the remainder: the 14 students left over still need a bus",
        "6 r 14": "Gave the division, not the number of buses", "6r14": "Gave the division, not the number of buses"},
    9: {"many": "Thought a summary needs as many numbers as there are values, as on BH7"},
    10: {"–9": "Picked the number further left, as on AG9", "-9": "Picked the number further left, as on AG9"},
}
WRONG["BU"] = {
    1: {f"{15 * 6 * 3} cm²": "Used square units for a volume"},
    3: {s: "Letters swapped: the boxes made the subject, as on AU7 and AV7" for s in ("b = 8p", "b=8p")},
    4: {"one": "Thought only one number solves an inequality"},
    5: {"10": "Gave the y-coordinate as the distance from the y-axis, as on O3 and W3",
        "13": "Added the two coordinates, as on L6"},
    6: {"2/5": "Turned the ratio upside down: rice per cup of water, as on BA9",
        "10": "Gave the water figure straight from the ratio instead of dividing, as on BI5"},
    7: {dec(D("47.3") / 100): "Moved the point two places instead of three, as on L9",
        dec(D("47.3") * 1000): "Multiplied by 1000 instead of dividing"},
    8: {"A": "Chose an addition equation where each pen costs the same, as on BA6"},
    9: {"–1 1/2": f"{_SIGN}: two negatives multiply to a positive, as on BH9",
        "-1 1/2": f"{_SIGN}: two negatives multiply to a positive, as on BH9"},
    10: {s: "Built it in the order the words are spoken, 2 first, as on AG3" for s in ("2 – 6k", "2 - 6k", "2-6k")},
}
WRONG["BN"] = {
    1: {"120": "Added 36 + 84 instead of factoring out the common factor, as on BF2",
        "12": "Wrote the GCF only, not the expression",
        **{f"{c}({36 // c} + {84 // c})": "Factored out a common factor but not the greatest"
           for c in (2, 3, 4, 6)}},
    2: {"5": "Wrote the GCF only, not the factored expression, as on BC3",
        "5(4 + 7)": "Dropped the variable x from the factored term, as on BL2",
        "5(4+7)": "Dropped the variable x from the factored term, as on BL2",
        str(20 * 5 + 35): "Substituted the GCF 5 for x and worked out 20(5) + 35 instead of factoring, as on BE3 and BG3"},
    3: {"right": "Named the skew after where the data bunches, not the side of the tail, as on BF7, BH4 and BJ4",
        "Right": "Named the skew after where the data bunches, not the side of the tail, as on BF7, BH4 and BJ4"},
    4: {str((2 * 4) ** 2 + 7): "Squared 2m instead of only m: (2 × 4)² + 7"},
    5: {"A": "Chose an addition equation where the problem says times, as on BA6"},
    6: {str(-4 + 9 - 2): "Combined the whole numbers and dropped the fractions, as on BE1"},
    7: {"B": "Chose the measure of spread, not of center, as on BK8"},
    8: {f"{mixed(F(15, 2) * F(3, 5))} m": "Found the part not painted (3/5) instead of 2/5"},
    9: {"t > 2 1/2": "Inequality sign the wrong way round", "t>2 1/2": "Inequality sign the wrong way round"},
    10: {mixed(F(21, 4)): _HALF, str(F(7, 2) + 2 + F(3, 2)): "Added the three edges instead of multiplying"},
}
WRONG["BO"] = {
    1: {"B": "Divided where the problem is a multiplication, as on BL9",
        "C": "Divided where the problem is a multiplication, as on BL9"},
    2: {"L > 450": "Inequality sign the wrong way round", "L>450": "Inequality sign the wrong way round"},
    3: {f"{(12 + 8) * 5} m²": "Multiplied the sum of the parallel sides by the height and did not halve it"},
    4: {dec(D(36) * 7 / 20): "Cancelled a 5 from 180 and again from 35/100: the same factor twice, as on BL5",
        mixed(F(36 * 7, 20)): "Cancelled a 5 from 180 and again from 35/100: the same factor twice, as on BL5"},
    5: {"9": _HALF},
    6: {"C": "Multiplied for a how-many-groups problem instead of dividing, as on BE2 and BG2",
        "B": "Divided the wrong way round: the bag by the whole flour"},
    7: {"–2": f"{_SIGN}: two negatives multiply to a positive, as on BH9",
        "-2": f"{_SIGN}: two negatives multiply to a positive, as on BH9"},
    8: {"1/12": "Divided the wrong way round: minutes per page, as on BA9"},
    10: {f"${(15 + 8) * 5}": "Added 15 + 8 before multiplying by 5", str((15 + 8) * 5): "Added 15 + 8 before multiplying by 5"},
}
WRONG["BA"] = {}
WRONG["BB"] = {}
WRONG["BC"] = {}
WRONG["AX"] = {
    3: {"A": "Wrote it in the order the words are spoken, 6 first, as on Test AA"},
    4: {"A": "Compared pack size or total price, not the cost of one"},
    5: {"(–3, –5)": "Reflected across the y-axis: flipped x instead of y"},
    6: {"25": "Multiplied only the 8 by 3: ignored the parentheses"},
    8: {"B": "Added the jars and the liters instead of multiplying, as when '3/5 of it' was read as adding"},
    9: {"125": "Worked out the value instead of writing it with an exponent",
        "15": "Multiplied 5 by 3, reading the count as a factor"},
}
WRONG["AY"] = {
    3: {"25": "Dropped the minus sign"},
    4: {"48": "Multiplied the numbers: a common multiple, but not the least",
        "2": "Gave the greatest common factor, not the least common multiple"},
    5: {"3": "Subtracted 6 – 3 as if both points were on the same side of the x-axis"},
    6: {"3 11/24": "Took the smaller fraction from the larger instead of regrouping"},
    10: {"yes": "Treated 2(n + 3) as 2n + 3: did not multiply the 3 by 2"},
}
WRONG["AZ"] = {
    2: {"h = 7p": "Letters swapped: the hours made the subject, same swap as on earlier sheets"},
    3: {"B": "Read the division as multiplication"},
    9: {"$40": "Added 3 + 2 first, then multiplied by 8", "40": "Added 3 + 2 first, then multiplied by 8"},
}
WRONG["AU"] = {}
WRONG["AV"] = {}
WRONG["AW"] = {}
WRONG["AR"] = {}
WRONG["AS"] = {}
WRONG["AT"] = {}
WRONG["AO"] = {}
WRONG["AP"] = {}
WRONG["AQ"] = {}
WRONG["AL"] = {}
WRONG["AM"] = {}
WRONG["AN"] = {}
WRONG["AI"] = {}
WRONG["AJ"] = {}
WRONG["AK"] = {}
WRONG["AF"] = {}
WRONG["AG"] = {}
WRONG["AH"] = {6: {"32": "Squared 3a instead of only a: (3 × 2)² – 4"}}
WRONG["Z"] = {}
WRONG["AA"] = {}
WRONG["AB"] = {7: {"40": "Squared 3m instead of only m: (3 × 2)² + 4"}}
WRONG["Y"] = {7: {"41": "Squared 2n instead of only n: (2 × 3)² + 5"}}

# Sheets AC-AE. The heuristic questions have very specific likely errors:
# adding everything rather than testing the signs, and - the big one on
# equalising - pouring the whole difference across instead of half of it,
# which overshoots and swaps which container is fuller.
WRONG["AC"] = {
    1: {"+ +": "Added both without testing the signs",
        "++": "Added both without testing the signs"},
    3: {f"{mixed(F(9, 4) - F(5, 4))} cups": "Poured the whole difference across, which overfills the second cup"},
    4: {"7": "Rounded both numbers down instead of to the nearest whole",
        mixed(F(29, 6) + F(23, 8)): "Worked it out exactly instead of estimating"},
    6: {mixed(F(3) + abs(F(1, 4) - F(2, 3))): "Took the smaller fraction from the larger instead of borrowing a whole"},
    9: {"greater than 12": "Thought multiplying always makes a number bigger",
        "greater": "Thought multiplying always makes a number bigger",
        "equal to 12": "Treated 7/8 as if it were 1"},
}
WRONG["AD"] = {
    1: {"+ +": "Added both without testing the signs",
        "++": "Added both without testing the signs"},
    3: {f"{frac(F(3, 2) - F(3, 4))} liter": "Poured the whole difference across, which overfills the second bottle"},
    4: {"3": "Rounded both numbers down instead of to the nearest whole"},
    8: {f"{frac(F(5, 6) + F(3, 8))} m": "Added the two lengths instead of subtracting"},
    9: {"less than 20": "Thought a fraction in front always makes a number smaller",
        "less": "Thought a fraction in front always makes a number smaller"},
}
WRONG["AE"] = {
    1: {"+ +": "Added both without testing the signs",
        "++": "Added both without testing the signs"},
    3: {f"{frac(F(7, 8) - F(3, 8))} kg": "Poured the whole difference across, which overfills the second bottle"},
    4: {"7": "Rounded both numbers down instead of to the nearest whole"},
    8: {"less than 1": "Judged 2/5 as small without noticing it is nearly a half",
        "less": "Judged 2/5 as small without noticing it is nearly a half"},
}

TESTS = (("A", A), ("B", B), ("C", C), ("D", Dd), ("E", E), ("F", Ff), ("G", G), ("H", Hh),
         ("I", I), ("J", J), ("K", K), ("L", Ll), ("M", M), ("N", N), ("O", O), ("P", P),
         ("Q", Qq), ("R", R), ("S", S), ("T", T), ("U", U), ("V", V), ("W", Wq), ("X", Xq), ("Y", Yq),
         ("Z", Zq), ("AA", AAq), ("AB", ABq),
         ("AC", ACq), ("AD", ADq), ("AE", AEq),
         ("AF", AFq), ("AG", AGq), ("AH", AHq),
         ("AI", AIq), ("AJ", AJq), ("AK", AKq),
         ("AL", ALq), ("AM", AMq), ("AN", ANq),
         ("AO", AOq), ("AP", APq), ("AQ", AQq),
         ("AR", ARq), ("AS", ASq), ("AT", ATq),
         ("AU", AUq), ("AV", AVq), ("AW", AWq),
         ("AX", AXq), ("AY", AYq), ("AZ", AZq),
         ("BA", BAq), ("BB", BBq), ("BC", BCq),
         ("BD", BDq), ("BE", BEq), ("BF", BFq),
         ("BG", BGq), ("BH", BHq), ("BI", BIq),
         ("BJ", BJq), ("BK", BKq), ("BL", BLq),
         ("BM", BMq), ("BN", BNq), ("BO", BOq),
         ("BP", BPq), ("BQ", BQq), ("BR", BRq),
         ("BS", BSq), ("BT", BTq), ("BU", BUq),
         ("BV", BVq), ("BW", BWq), ("BX", BXq))

for code, qs in TESTS:
    for i, q in enumerate(qs):
        cw = WRONG[code].get(i + 1, {})
        assert not (set(cw) & set(q["accept"])), (code, i + 1)
        q["common_wrong_answers"] = cw
    # The sheet is a 2x5 grid. Nine questions leaves a blank cell, and nothing
    # noticed when it happened.
    assert len(qs) == 10, f"Test {code} has {len(qs)} questions, the sheet holds 10"
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
assert [q["answer"] for q in Qq] == ["30000 cm³", "12 cups", "2", "3 7/8 kg", "–1", "A, C", "B",
                                     "50", "12a + 20", "7"], [q["answer"] for q in Qq]
assert [q["answer"] for q in R] == ["$66.00", "228326", "no", "less than", "2 cups", "(n – 8) ÷ 2",
                                    "25", "12", "–15", "no"], [q["answer"] for q in R]
assert [q["answer"] for q in S] == ["75", "7", "15", "65", "(18, 9)", "7", "B", "20 cups", "B",
                                    "(20 – 4) ÷ 2"], [q["answer"] for q in S]
assert [q["answer"] for q in T] == ["84000 cm³", "20", "9", "16", "greater than", "9", "–3",
                                    "c = 40h", "$12.65", "0.47"], [q["answer"] for q in T]
assert [q["answer"] for q in U] == ["$110.40", "177712", "(4, 1)", "–2", "0.365", "5", "h > 48",
                                    "12", "1/6", "9 cm³"], [q["answer"] for q in U]
assert [q["answer"] for q in V] == ["35", "5/8 cup", "1 5/12 miles", "$0.25", "3 m", "7 1/2 feet",
                                    "Moscow", "–$40", "72", "yes"], [q["answer"] for q in V]
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
REFRESH = "--refresh" in sys.argv[1:]
legacy = legacy_letters()
plan, refused, stale = [], [], []
for code, qs in TESTS:
    if code in legacy:
        continue                                   # printed under the old &v= scheme
    spec = build_spec(code, qs)
    path = OUT / f"Math_Practice_Test_{code}.json"
    saved = json.loads(path.read_text()) if path.exists() else {}
    old = saved.get("fingerprint")
    if old and old != spec["fingerprint"]:
        refused.append(f"  Test {code}: page 1 would change ({old} -> {spec['fingerprint']}). "
                       "It may already be printed - put the new questions under a new letter.")
        continue
    if old and not REFRESH and path.with_suffix(".pdf").exists():
        if saved != json.loads(json.dumps(spec)):   # as it reads back from disk
            stale.append(code)
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
if not plan:
    print("nothing new to write")
if stale:
    print(f"specs behind make_tests.py (run with --refresh to update): {', '.join(stale)}")
skipped = sorted(code for code, _ in TESTS if code in legacy)
if skipped:
    print(f"untouched (printed under the old scheme, specs in {LEGACY}): {', '.join(skipped)}")
