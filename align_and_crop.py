"""Fixed-format sheet reader: QR -> test spec; answer boxes -> page homography; crop answers.
Uses the 10 printed answer boxes as alignment targets. Orientation and mirroring come
from where the QR sits (top-right)."""
import cv2, json, numpy as np, sys
img = cv2.imread(sys.argv[1]); out = sys.argv[2]; specdir = sys.argv[3]
PW, PH = 595.28, 841.89
MX0, MY0, MW, MH = 26, 26, PW - 52, PH - 52

import qr_read
val, qpts = qr_read.decode(img)
# Manual fallback for a QR that is printed but unreadable (steep angle, written
# over): the caller names the spec and says where the QR sits in this image, as
# fractions "x,y" of width and height. Position is all the QR contributes to
# geometry - which way is up, and which column is right.
#   python3 align_and_crop.py <img> <out> <specdir> <spec.json> <x,y>
manual = len(sys.argv) > 5
if val:
    qc = qpts.mean(0)
    spec = json.load(open(f"{specdir}/Math_Practice_Test_{val.split('test=')[1].split('&')[0]}.json"))
    print("QR:", val)
elif manual:
    fx, fy = (float(v) for v in sys.argv[5].split(","))
    qc = np.array([fx * img.shape[1], fy * img.shape[0]], dtype=np.float32)
    spec = json.load(open(sys.argv[4]))
    print(f"QR not decoded; using {sys.argv[4]} with the QR stated at ({fx}, {fy})")
else:
    sys.exit("QR not found -> ask for retake")

# Detect answer boxes (thick-bordered rectangles, aspect ~2-7)
g = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
th = cv2.adaptiveThreshold(g, 255, cv2.ADAPTIVE_THRESH_MEAN_C, cv2.THRESH_BINARY_INV, 31, 15)
cnts, _ = cv2.findContours(th, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)
area_img = g.size
cand = []
for c in cnts:
    a = cv2.contourArea(c)
    if not (0.0008 * area_img < a < 0.03 * area_img): continue
    ap = cv2.approxPolyDP(c, 0.03 * cv2.arcLength(c, True), True)
    if len(ap) != 4 or not cv2.isContourConvex(ap): continue
    (w, h) = cv2.minAreaRect(ap)[1]
    if 2.2 < max(w, h) / max(1, min(w, h)) < 7:
        cand.append((ap.reshape(-1, 2).astype(np.float32), a))
boxes = []
for q, a in sorted(cand, key=lambda t: -t[1]):            # keep outer contour per box
    if all(np.linalg.norm(q.mean(0) - b.mean(0)) > 30 for b in boxes): boxes.append(q)
C = np.array([b.mean(0) for b in boxes])
# Keep the dominant similar-size group (drop stray rectangles)
areas = np.array([cv2.contourArea(b) for b in boxes]); med = np.median(areas)
keep = [i for i in range(len(boxes)) if 0.5 * med < areas[i] < 2.5 * med]
boxes = [boxes[i] for i in keep]; C = C[keep]

# Axes from the boxes themselves. Every answer box is a wide rectangle printed
# horizontally, so their long edges give the page's horizontal direction even
# when only a few boxes are found. (The spread of the box centres, used before,
# is skewed by an uneven set: six boxes under a shadow put it 30 degrees off,
# the QR then sat almost level with the middle, and the columns were swapped -
# every answer filed under the other column's question, with no error.)
def _long_edge_angle(b):
    e = max((b[(k + 1) % 4] - b[k] for k in range(4)), key=np.linalg.norm)
    return np.arctan2(e[1], e[0])
ang = np.array([_long_edge_angle(b) for b in boxes])
th = 0.5 * np.arctan2(np.sin(2 * ang).mean(), np.cos(2 * ang).mean())   # edges have no sign
h_ax = np.array([np.cos(th), np.sin(th)]); v_ax = np.array([-h_ax[1], h_ax[0]])
mu = C.mean(0)
up = v_ax * np.sign(np.dot(qc - mu, v_ax))                       # toward the QR = page top

# Columns: split the box centres along the horizontal at the widest gap. The
# two columns sit about two box-widths apart; boxes within one barely differ.
bw_px = float(np.median([max(np.linalg.norm(b[(k + 1) % 4] - b[k]) for k in range(4)) for b in boxes]))
x = (C - mu) @ h_ax
order_x = np.argsort(x); gaps = np.diff(x[order_x])
if len(gaps) == 0 or gaps.max() < bw_px:
    sys.exit("answer boxes found in one column only -> ask for retake")
k = int(np.argmax(gaps))
lo, hi = order_x[:k + 1], order_x[k + 1:]
mid = (x[lo].mean() + x[hi].mean()) / 2
# The QR sits above the right column, so it lies clearly on the right half.
# If it does not, the frame is unreliable and a swap would be silent.
qx = float((qc - mu) @ h_ax) - mid
if abs(qx) < 0.25 * (x[hi].mean() - x[lo].mean()):
    sys.exit("cannot tell which column is right from the QR position -> ask for retake")
right = h_ax * np.sign(qx)
pu, pr = (C - mu) @ up, (C - mu) @ right
col = np.zeros(len(C), int); col[hi if qx > 0 else lo] = 1      # 1 = right column
print(f"boxes found: {len(boxes)}  (left col {sum(col==0)}, right col {sum(col==1)})")
# A stated QR position is only approximate, and with a box missing the rows are
# anchored on it - so a slightly wrong position could file every answer one row
# off without any error. Full columns need no anchor; insist on them.
if manual and not val and not (sum(col == 0) == 5 and sum(col == 1) == 5):
    sys.exit("QR not decoded: the manual fallback needs all ten answer boxes -> ask for retake")
# Row pitch, measured across both columns and robust to gaps in either.
Y = [spec["questions"][r * 2]["regions"]["answer"][1]
     + spec["questions"][r * 2]["regions"]["answer"][3] / 2 for r in range(5)]
SPN = float(np.median(np.diff(Y)))                               # row pitch, normalised
YQR = 0.0468                                                     # QR centre y, same frame
steps_all = []
for ci in (0, 1):
    idx = np.where(col == ci)[0]
    if len(idx) >= 2: steps_all += list(-np.diff(pu[idx[np.argsort(-pu[idx])]]))
if not steps_all: sys.exit("too few answer boxes to find the row pitch -> ask for retake")
sp0 = np.median(steps_all)
mult = np.round(np.array(steps_all) / sp0); mult[mult == 0] = 1
sp = float(np.median(np.array(steps_all) / mult))                # one row, in pixels

# Anchor rows on the QR, not on the topmost box found. If the top box of a column
# is missed, "first box = row 0" shifts every crop in that column by one row and
# silently files each answer under the wrong question.
puq = float((qc - mu) @ up)
src, dst = [], []
for ci in (0, 1):
    idx = np.where(col == ci)[0]
    if len(idx) < 2: continue
    order = idx[np.argsort(-pu[idx])]                            # top to bottom
    if len(order) == 5:
        # A full column needs no anchor: five boxes top-to-bottom are rows 0-4.
        # The QR formula assumes a uniform row pitch, which a steeply angled
        # photo breaks - near rows are taller than far ones, so the median pitch
        # mis-rounds the top row and two boxes collide. Seen on a real sheet.
        rows = np.arange(5)
    else:
        rows = np.round((puq - pu[order]) / sp - (Y[0] - YQR) / SPN).astype(int)
    if len(set(rows)) != len(rows) or rows.min() < 0 or rows.max() > 4:
        sys.exit(f"column {ci}: rows {list(rows)} are not a sane 0-4 -> ask for retake")
    for i, r in zip(order, rows):
        q = spec["questions"][r * 2 + ci] if r * 2 + ci < 10 else None
        if q is None: continue
        x, y, w, h = q["regions"]["answer"]
        page = np.float32([[x, y], [x + w, y], [x + w, y + h], [x, y + h]])
        page = page * [MW, MH] + [MX0, MY0]
        b = boxes[i]; d = b - b.mean(0)
        u, r_ = d @ up, d @ right
        tl = b[np.argmax(u - r_)]; tr = b[np.argmax(u + r_)]; br = b[np.argmax(-u + r_)]; bl = b[np.argmax(-u - r_)]
        src += list(page); dst += [tl, tr, br, bl]
Hm, inl = cv2.findHomography(np.float32(src), np.float32(dst), cv2.RANSAC, 10)
print("alignment points:", len(src), "inliers:", int(inl.sum()))
S = 2.0
warp = cv2.warpPerspective(img, Hm @ np.diag([1 / S, 1 / S, 1]), (int(PW * S), int(PH * S)), flags=cv2.WARP_INVERSE_MAP)
cv2.imwrite(f"{out}/straightened.jpg", warp)
def cut(region, pad=8):
    x, y, w, h = region
    X, Y, Wd, Hd = (MX0 + x * MW) * S, (MY0 + y * MH) * S, w * MW * S, h * MH * S
    return warp[max(0, int(Y) - pad):int(Y + Hd) + pad, max(0, int(X) - pad):int(X + Wd) + pad]

crops = []
for q in spec["questions"]:
    c = cut(q["regions"]["answer"])
    cv2.imwrite(f"{out}/{q['id']}.png", c); crops.append(c)
    # The working is what the diagnosis step reads, so crop it in the same pass.
    cv2.imwrite(f"{out}/{q['id']}_working.png", cut(q["regions"]["working"], pad=4))
hm = max(c.shape[0] for c in crops); wm = max(c.shape[1] for c in crops)
sheet = np.full(((hm + 26) * 5, (wm + 10) * 2, 3), 255, np.uint8)
for i, c in enumerate(crops):
    r, k = divmod(i, 2); y0 = r * (hm + 26) + 20; x0 = k * (wm + 10)
    sheet[y0:y0 + c.shape[0], x0:x0 + c.shape[1]] = c
    cv2.putText(sheet, spec["questions"][i]["id"], (x0 + 2, y0 - 5), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 255), 1)
cv2.imwrite(f"{out}/answer_boxes.png", sheet)
