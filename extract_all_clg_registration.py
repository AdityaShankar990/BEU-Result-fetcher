import re, sys, time, threading, os
### Dependencies
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
missing = []
try: import requests
except: missing.append("requests")
try:
    from reportlab.lib.pagesizes import A4
    from reportlab.lib import colors
    from reportlab.lib.units import mm
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.platypus import (SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable)
    from reportlab.lib.enums import TA_CENTER
except: missing.append("reportlab")
if missing:
    print(f"[!] pip install {' '.join(missing)}")
    sys.exit(1)
### Configs
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
OUTPUT_PDF = os.path.join(BASE_DIR, "beu_reg_out.pdf")
YEAR = 2025
EXAM = "January/2026"
SEMESTER = "I"
ROLL_START = 1
ROLL_MAX_PROBE = 300
WORKERS = 100
BSEARCH_WORKERS = 8
DELAY = 0.03
API_URL = (
    "https://beu-bih.ac.in/backend/v1/result/get-result"
    "?year={year}&redg_no={reg}&semester={sem}&exam_held={exam}"
)
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/plain, */*",
    "Referer": "https://beu-bih.ac.in/",
    "Origin": "https://beu-bih.ac.in",
}
COLLEGE_RANGE = range(1, 100)
BRANCH_CODES = list(range(1, 100))
MIDDLE_RANGE = range(0, 100)

def make_reg(cc: str, bb: str, mm: str, roll: int) -> str:
    return f"{YEAR % 100:02d}{cc}{bb}{mm}{roll:03d}"

def api_url(reg):
    return API_URL.format(year=YEAR, reg=reg, sem=SEMESTER, exam=EXAM)

def flat_keys(d):
    return {re.sub(r"[\s_\-]", "", k.lower()): v for k, v in d.items()}

def grab(flat, *keys):
    for k in keys:
        nk = re.sub(r"[\s_\-]", "", k.lower())
        if nk in flat and flat[nk] is not None:
            v = str(flat[nk]).strip()
            if v: return v
    return ""

def fetch_one(session, reg: str):
    try:
        r = session.get(api_url(reg), headers=HEADERS, timeout=15)
        if r.status_code != 200:
            return False, "", "", "", "", f"HTTP {r.status_code}"
        try: data = r.json()
        except: return False, "", "", "", "", "bad JSON"
        if isinstance(data, list):
            data = data[0] if data else {}
        if isinstance(data, dict):
            for w in ("data","result","student","response","payload"):
                if w in data and isinstance(data[w], dict):
                    data = data[w]; break
        if not isinstance(data, dict) or not data:
            return False, "", "", "", "", "empty"
        fl = flat_keys(data)
        name = grab(fl, "name","studentname","studname","candidatename","fullname")
        college = grab(fl, "college","collegename","institute","institutename","instname")
        branch = grab(fl, "branch","course","programme","dept","coursename","branchname")
        cgpa = grab(fl, "cgpa","sgpa","gpa","semsgpa","semcgpa")
        raw_st = grab(fl, "result","status","finalresult","examresult","passfail", "passstatus","overallresult","finalstatus","semresult")
        if not raw_st:
            for v in data.values():
                sv = str(v).strip().upper()
                if re.search(r"\b(PASS|FAIL|PROMOTED|DETAINED)\b", sv):
                    raw_st = sv; break
        valid = bool(name or re.search(r"PASS|FAIL|PROMOTED|DETAINED", raw_st, re.I))
        return valid, name, college, branch, cgpa, raw_st
    except Exception as e:
        return False, "", "", "", "", str(e)[:60]

def build_candidates():
    candidates = []
    for cc in COLLEGE_RANGE:
        for bb in BRANCH_CODES:
            for mm in MIDDLE_RANGE:
                candidates.append((f"{cc:02d}", f"{bb:02d}", f"{mm:02d}"))
    return candidates

_print_lock = threading.Lock()
def sweep(candidates):
    found = []
    seen_mm = set()
    session_pool = [requests.Session() for _ in range(WORKERS)]
    def probe(args):
        idx, (cc, bb, mm) = args
        sess = session_pool[idx % WORKERS]
        reg  = make_reg(cc, bb, mm, ROLL_START)
        time.sleep(DELAY * (idx % WORKERS) * 0.05)
        ok, name, college, branch, cgpa, status = fetch_one(sess, reg)
        return cc, bb, mm, ok, name, college, branch, cgpa, status
    total = len(candidates)
    print(f"[Phase 1] Sweeping {total:,} permutations  "
          f"(CC×BB×MM = {len(list(COLLEGE_RANGE))}×{len(BRANCH_CODES)}×{len(list(MIDDLE_RANGE))})")
    print(f"          MIDDLE range: {MIDDLE_RANGE.start}–{MIDDLE_RANGE.stop-1}  "
          f"| Workers: {WORKERS}\n")

    with ThreadPoolExecutor(max_workers=WORKERS) as ex:
        futures = {ex.submit(probe, (i, c)): c for i, c in enumerate(candidates)}
        done = 0
        for fut in as_completed(futures):
            done += 1
            cc, bb, mm, ok, name, college, branch, cgpa, status = fut.result()
            if ok:
                entry = {
                    "cc": cc, "bb": bb, "mm": mm,
                    "code":    f"{cc}{bb}{mm}",
                    "college": college or "—",
                    "branch":  branch  or "—",
                    "name":    name    or "—",
                    "cgpa":    cgpa    or "—",
                    "status":  status  or "—",
                    "start":   make_reg(cc, bb, mm, ROLL_START),
                    "end":     make_reg(cc, bb, mm, ROLL_START),
                    "count":   1,
                }
                found.append(entry)
                seen_mm.add(mm)
                with _print_lock:
                    print(f"  CC={cc} BB={bb} MM={mm}  reg={entry['start']}"
                          f"  │  {college or '?':30s}  │  {branch or '?'}")
            if done % 500 == 0:
                pct = done / total * 100
                with _print_lock:
                    print(f"  … {done:,}/{total:,} ({pct:.1f}%)  "
                          f"hits: {len(found)}  unique MM found: {sorted(seen_mm)}")
    found.sort(key=lambda x: (x["cc"], x["bb"], x["mm"]))
    print(f"\n[Phase 1 done]  {len(found)} valid series | "
          f"Unique MM codes: {sorted(seen_mm)}\n")
    return found, sorted(seen_mm)

def binary_search_end(session, cc, bb, mm, lo=1, hi=ROLL_MAX_PROBE) -> int:
    while hi < 9999:
        ok, *_ = fetch_one(session, make_reg(cc, bb, mm, hi))
        if ok: hi = min(hi * 2, 9999)
        else:  break
    best = lo
    while lo <= hi:
        mid = (lo + hi) // 2
        ok, *_ = fetch_one(session, make_reg(cc, bb, mm, mid))
        if ok: best = mid; lo = mid + 1
        else:  hi   = mid - 1
        time.sleep(0.08)
    return best

def find_ends(entries):
    print(f"[Phase 2] Binary-searching end rolls for {len(entries)} series …\n")
    sessions = [requests.Session() for _ in range(BSEARCH_WORKERS)]
    def do_search(args):
        i, e = args
        sess = sessions[i % BSEARCH_WORKERS]
        end_roll = binary_search_end(sess, e["cc"], e["bb"], e["mm"])
        return e["code"], end_roll
    with ThreadPoolExecutor(max_workers=BSEARCH_WORKERS) as ex:
        futures = {ex.submit(do_search, (i, e)): e["code"] for i, e in enumerate(entries)}
        for fut in as_completed(futures):
            code, end_roll = fut.result()
            for e in entries:
                if e["code"] == code:
                    e["end"]   = make_reg(e["cc"], e["bb"], e["mm"], end_roll)
                    e["count"] = end_roll
                    with _print_lock:
                        print(f"  {code}  last roll={end_roll:03d}  ({e['end']})"
                              f"  │  {e['branch']:20s}  │  {e['college']}")
    print()
    return entries

PRIMARY = colors.HexColor("#1a3c6e")
SECND = colors.HexColor("#2e7bcf")
LTBG = colors.HexColor("#eef4fb")
def build_pdf(entries, seen_mm, path):
    bs = getSampleStyleSheet()
    W, _ = A4;  M = 14*mm
    ST = {
        "title": ParagraphStyle("t", parent=bs["Title"],  fontSize=15, textColor=PRIMARY, alignment=TA_CENTER, fontName="Helvetica-Bold", spaceAfter=3),
        "sub":   ParagraphStyle("s", parent=bs["Normal"], fontSize=8.5, textColor=colors.HexColor("#555"), alignment=TA_CENTER, spaceAfter=6),
        "cell":  ParagraphStyle("c", parent=bs["Normal"], fontSize=7.5),
        "mono":  ParagraphStyle("m", parent=bs["Normal"], fontSize=7, fontName="Courier", spaceAfter=2),
        "hdr":   ParagraphStyle("h", parent=bs["Normal"], fontSize=9, fontName="Helvetica-Bold", textColor=PRIMARY, spaceAfter=4),
    }
    doc = SimpleDocTemplate(path, pagesize=A4, leftMargin=M, rightMargin=M, topMargin=M, bottomMargin=M)
    story = [
        Paragraph("BEU Bihar — Full Permutation Discovery Report", ST["title"]),
        Paragraph(
            f"Format: 25·CC·BB·MM·RRR  │  "
            f"CC range: {COLLEGE_RANGE.start}–{COLLEGE_RANGE.stop-1}  │  "
            f"MM range: {MIDDLE_RANGE.start}–{MIDDLE_RANGE.stop-1}  │  "
            f"Generated: {datetime.now().strftime('%d %b %Y %H:%M')}",
            ST["sub"]),
        Paragraph(
            f"Total valid series: {len(entries)}  │  "
            f"Valid MM codes found: {seen_mm if seen_mm else 'none'}",
            ST["sub"]),
        HRFlowable(width="100%", thickness=3, color=PRIMARY, spaceAfter=8),
    ]
    if not entries:
        story.append(Paragraph("No valid series found. Try widening MIDDLE_RANGE to range(0,100).", ST["cell"]))
    else:
        from itertools import groupby
        entries_by_mm = sorted(entries, key=lambda x: (x["mm"], x["cc"], x["bb"]))
        cw  = W - 2*M
        col_w = [cw*.04, cw*.05, cw*.05, cw*.05, cw*.26, cw*.18, cw*.13, cw*.13, cw*.09]
        hdr_row = [["#", "CC", "BB", "MM", "College", "Branch", "Start Reg", "End Reg", "~Students"]]
        rows = []
        for i, e in enumerate(entries_by_mm, 1):
            rows.append([
                str(i), e["cc"], e["bb"], e["mm"],
                Paragraph(e["college"], ST["cell"]),
                Paragraph(e["branch"],  ST["cell"]),
                e["start"], e["end"], str(e["count"]),
            ])
        tbl = Table(hdr_row + rows, colWidths=col_w, repeatRows=1)
        tbl.setStyle(TableStyle([
            ("BACKGROUND",    (0,0),(-1,0),  PRIMARY),
            ("TEXTCOLOR",     (0,0),(-1,0),  colors.white),
            ("FONTNAME",      (0,0),(-1,0),  "Helvetica-Bold"),
            ("ROWBACKGROUNDS",(0,1),(-1,-1), [colors.white, LTBG]),
            ("GRID",          (0,0),(-1,-1), 0.35, colors.lightgrey),
            ("FONTSIZE",      (0,0),(-1,-1), 7.5),
            ("ALIGN",         (0,0),(-1,-1), "CENTER"),
            ("ALIGN",         (4,1),(5,-1),  "LEFT"),
            ("PADDING",       (0,0),(-1,-1), 3),
            ("VALIGN",        (0,0),(-1,-1), "MIDDLE"),
        ]))
        story.append(tbl)
        story.append(Spacer(1, 12))
        story.append(Paragraph("Quick reference (copy into result fetcher):", ST["hdr"]))
        for e in entries:
            story.append(Paragraph(
                f"START_REG = {e['start']}    END_REG = {e['end']}"
                f"    # CC={e['cc']} BB={e['bb']} MM={e['mm']}"
                f" | {e['branch']} @ {e['college']}",
                ST["mono"]))

    doc.build(story)
    print(f"\n[+] PDF saved → {path}")

def main():
    candidates = build_candidates()
    total_comb = len(candidates)
    est_mins = total_comb / WORKERS / (1/DELAY) / 60
    print(f"[+] Total permutations : {total_comb:,}")
    print(f"[+] Estimated time     : ~{est_mins:.1f} min at {WORKERS} workers\n")
    print("[+] Tip: If MM=58 is the only hit after this run, the 58 is universal.")
    print("[+] If new MM values appear, re-run with MIDDLE_RANGE = range(0,100)\n")
    valid, seen_mm = sweep(candidates)
    if not valid:
        print("[-] No hits found.")
        print("[-] Try setting MIDDLE_RANGE = range(0, 100) for full brute-force.")
        build_pdf([], [], OUTPUT_PDF)
        return
    valid = find_ends(valid)
    print("\n" + "="*80)
    print(f"[+] {'CC':4} {'BB':4} {'MM':4}  {'BRANCH':22}  {'START':14}  {'END':14}  N")
    print("="*80)
    for e in valid:
        print(f"[+] {e['cc']:4} {e['bb']:4} {e['mm']:4}  "
              f"[+] {e['branch']:22}  {e['start']:14}  {e['end']:14}  {e['count']}")
    print(f"\n[+] Unique MM (middle) codes found: {seen_mm}")
    build_pdf(valid, seen_mm, OUTPUT_PDF)

if __name__ == "__main__":
    main()