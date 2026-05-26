import json, os, re, sys, time, urllib.request, argparse
### Dependencies
missing = []
try: import requests
except: missing.append("requests")
try:
    from reportlab.lib.pagesizes import A4
    from reportlab.lib import colors
    from reportlab.lib.units import mm
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.platypus import (Paragraph, Spacer, Table, TableStyle)
    from reportlab.lib.enums import TA_CENTER, TA_LEFT
    from reportlab.platypus import BaseDocTemplate, PageTemplate, Frame
except: missing.append("reportlab")
try: from PIL import Image as PILImage
except: missing.append("pillow")
if missing:
    print(f"[!] run: pip install {' '.join(missing)}")
    sys.exit(1)
### Configs
def parse_args():
    parser = argparse.ArgumentParser(description="BEU result fetcher")
    parser.add_argument(
        "--regset", nargs=3, metavar=("LABEL", "START", "END"),
        action="append", required=True,
        help="A registration set: LABEL START END  (repeat for multiple sets)"
    )
    parser.add_argument("--output_pdf", type=str, required=True, help="Final merged output PDF path")
    parser.add_argument("--college_name", type=str, default="", help="College name shown on topper page")
    return parser.parse_args()

args = parse_args()
OUTPUT_PDF = args.output_pdf
COLLEGE_NAME = args.college_name
YEAR = 2025
EXAM = "January/2026"
SEMESTER = "I"
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
LOGO_URL = "https://beu-bih.ac.in/assets/beu_logo.jpeg"
def ensure_logo():
    script_dir = os.path.dirname(os.path.abspath(__file__))
    logo_path = os.path.join(script_dir, "beu_logo.jpeg")
    if os.path.exists(logo_path):
        return logo_path
    print(f"[+] logo downloading from {LOGO_URL} …")
    try:
        urllib.request.urlretrieve(LOGO_URL, logo_path)
        print(f"[*] logo saved: {logo_path}")
    except Exception as e:
        print(f"[!] logo download failed: {e}")
    return logo_path if os.path.exists(logo_path) else None

def fetch_result(session, reg_no: str) -> dict:
    url = API_URL.format(year=YEAR, reg=reg_no, sem=SEMESTER, exam=EXAM)
    try:
        r = session.get(url, headers=HEADERS, timeout=20)
        if r.status_code != 200:
            return blank(reg_no, f"HTTP {r.status_code}")
        ct = r.headers.get("content-type", "")
        if "json" in ct or r.text.strip().startswith(("{", "[")):
            try:   return parse_json(r.json(), reg_no)
            except: pass
        return parse_html(r.text, reg_no)
    except requests.exceptions.Timeout:
        return blank(reg_no, "Request timed out")
    except Exception as e:
        return blank(reg_no, str(e)[:100])

def blank(reg_no, err=""):
    return {
        "reg_no": reg_no, "name": "—", "father": "—", "mother": "—",
        "college": "—", "branch": "—", "semester": "I",
        "exam_date": "January/2026", "result": "—",
        "cgpa": "—", "sgpa": "—", "remarks": "—",
        "subjects": [], "theory": [], "practical": [],
        "raw": {}, "error": err,
    }

def clean_status(raw: str) -> tuple:
    raw = raw.strip()
    if not raw or raw == "—":
        return "—", "—"
    if ":" in raw:
        word, rest = raw.split(":", 1)
        word  = word.strip().upper()
        codes = [c.strip() for c in rest.split(",") if c.strip()]
        remark = word + ":" + ",".join(codes) if codes else word
        return word, remark
    return raw.upper(), raw.upper()

def get_subj_field(d: dict, *keys) -> str:
    for k in keys:
        norm = re.sub(r"[\s_\-]", "", k.lower())
        for dk, dv in d.items():
            if re.sub(r"[\s_\-]", "", dk.lower()) == norm and dv is not None:
                return str(dv).strip()
    return "—"

def subject_row(d: dict) -> dict:
    code   = get_subj_field(d, "subject_code","subjectcode","code","sub_code")
    name   = get_subj_field(d, "subject_name","subjectname","name","sub_name","subject")
    ese    = get_subj_field(d, "ese","esemark","end_sem","endsem","ese_marks")
    ia     = get_subj_field(d, "ia","iamark","ia_marks","internal","int_marks")
    total  = get_subj_field(d, "total","totalmarks","total_marks","marks","tot")
    grade  = get_subj_field(d, "grade","lettergrade","letter_grade","grad")
    credit = get_subj_field(d, "credit","credits","creditpoint","credit_point")
    return {"code": code, "name": name, "ese": ese, "ia": ia, "total": total, "grade": grade, "credit": credit}

def is_practical_code(d: dict) -> bool:
    code = get_subj_field(d, "subject_code","subjectcode","code","sub_code").upper()
    tail = code.rstrip("P")
    return (code.endswith("P") and tail.isdigit()) or "LAB" in code

def parse_json(data, reg_no: str) -> dict:
    r = blank(reg_no)
    r["raw"] = data
    if not data:
        r["error"] = "Empty response"; return r
    if isinstance(data, list):
        data = data[0] if data else {}
    if isinstance(data, dict):
        for wrapper in ("data","result","student","response","payload","marksheet","studentdata"):
            if wrapper in data and isinstance(data[wrapper], dict):
                data = data[wrapper]; break
    if not isinstance(data, dict):
        r["error"] = f"Unexpected type: {type(data).__name__}"; return r
    flat = {}
    for k, v in data.items():
        flat[re.sub(r"[\s_\-]", "", k.lower())] = v
    def g(*keys) -> str:
        for k in keys:
            norm = re.sub(r"[\s_\-]", "", k.lower())
            if norm in flat and flat[norm] is not None:
                return str(flat[norm]).strip()
        return "—"
    r["name"] = g("name","studentname","studname","sname","candidatename","fullname")
    r["father"] = g("fathername","father_name","father","fname","fatherame")
    r["mother"] = g("mothername","mother_name","mother","mname","motherame")
    r["college"] = g("college","collegename","clg","institute","institutename")
    r["branch"] = g("branch","course","programme","dept","stream","coursename","branchname")
    r["semester"] = g("semester","sem","semno","semesternumber")
    r["exam_date"] = g("examdate","exam_date","examheld","exam_held","exammonthyear")
    r["sgpa"] = g("sgpa","semsgpa","semcgpa","semgpa")
    r["cgpa"] = g("cgpa","totalcgpa","currentcgpa","markscgpa","gpa")
    if r["cgpa"] == "—": r["cgpa"] = r["sgpa"]
    STATUS_KEYS = ("result","status","finalresult","examresult","passfail","remarks",
                   "remark","passstatus","passorfail","examstatus","overallresult",
                   "finalstatus","semresult","semstatus")
    raw_status = g(*STATUS_KEYS)
    if raw_status == "—":
        for v in data.values():
            sv = str(v).strip().upper()
            if re.search(r"\b(PASS|FAIL|PROMOTED|DETAINED)\b", sv):
                raw_status = sv; break
    r["result"], r["remarks"] = clean_status(raw_status)
    if not hasattr(parse_json, "_dumped"):
        parse_json._dumped = True
        print("\n────────────────── API JSON keys ──────────────────────────")
        for k, v in data.items():
            print(f"    {k!r:35s} [{type(v).__name__:6s}]: {str(v)[:80]}")
        print("──────────────────────────────────────────────────────────\n")
    def extract_list(key):
        norm = re.sub(r"[\s_\-]", "", key.lower())
        return flat[norm] if norm in flat and isinstance(flat[norm], list) else []
    def looks_like_subjects(lst):
        if not lst or not isinstance(lst[0], dict): return False
        ks = " ".join(lst[0].keys()).lower()
        return any(x in ks for x in ("code","subject","subj","ese","esa","grade","credit","ia","total"))
    top_theory = extract_list("theory")
    top_practical = extract_list("practical")
    raw_subs = []
    if not (top_theory or top_practical):
        for mk in ("subjects","marks","marksheet","papers","courses",
                   "subjectmarks","subjectlist","marksdetail","allmarks",
                   "resultdetail","subjectdata","markdata","resultmarks"):
            lst = extract_list(mk)
            if lst and looks_like_subjects(lst):
                raw_subs = lst; break
    if not raw_subs and not (top_theory or top_practical):
        for v in data.values():
            if isinstance(v, list) and looks_like_subjects(v):
                raw_subs = v; break
    if top_theory or top_practical:
        r["theory"] = [subject_row(s) for s in top_theory    if isinstance(s, dict)]
        r["practical"] = [subject_row(s) for s in top_practical if isinstance(s, dict)]
    elif raw_subs:
        theory_raw, practical_raw = [], []
        for s in raw_subs:
            (practical_raw if is_practical_code(s) else theory_raw).append(s)
        r["theory"] = [subject_row(s) for s in theory_raw    if isinstance(s, dict)]
        r["practical"] = [subject_row(s) for s in practical_raw if isinstance(s, dict)]
    r["subjects"] = r["theory"] + r["practical"]
    if r["name"] == "—" and not r["subjects"]:
        r["error"] = "Result not declared or registration number invalid"
    return r

def parse_html(html: str, reg_no: str) -> dict:
    r = blank(reg_no)
    if "not found" in html.lower() or "invalid" in html.lower() or len(html.strip()) < 50:
        r["error"] = "No result found"; return r
    try:
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(html, "html.parser")
        for row in soup.find_all("tr"):
            cells = [c.get_text(" ", strip=True) for c in row.find_all(["td","th"])]
            if len(cells) >= 2:
                k, v = cells[0].lower(), cells[1]
                if "name" in k and "college" not in k: r["name"] = v
                elif "father" in k: r["father"] = v
                elif "mother" in k: r["mother"] = v
                elif "college" in k or "institute" in k: r["college"] = v
                elif "branch" in k or "course" in k: r["branch"] = v
                elif "cgpa" in k: r["cgpa"] = v
                elif "sgpa" in k: r["sgpa"] = v
                elif "result" in k or "remark" in k:
                    rw, rm = clean_status(v)
                    r["result"]  = rw
                    r["remarks"] = rm
    except ImportError:
        pass
    return r

### LAYOUT
PW, PH = A4
LM = RM = 18 * mm
TM = BM = 15 * mm
USABLE_W = PW - LM - RM
COL_BLACK = colors.black
COL_WHITE = colors.HexColor("#F8F9FA")
COL_SECT_BG = colors.HexColor("#6c757d")
COL_RED_EXAM = colors.HexColor("#ff5370")
COL_PASS = colors.HexColor("#006400")
COL_FAIL_REM = colors.HexColor("#ff5370")
COL_INFO_HDR = colors.HexColor("#6c757d")
COL_INFO_FAIL = colors.HexColor("#ffe0e0")
COL_INFO_PASS = colors.HexColor("#e8f5e9")
COL_PASS_TEXT = colors.HexColor("#006400")
COL_FAIL_TEXT = colors.HexColor("#ff5370")
COL_GOLD = colors.HexColor("#FFD700")
COL_GOLD_DARK = colors.HexColor("#B8860B")
COL_GOLD_LITE = colors.HexColor("#FFF8DC")
COL_SILVER = colors.HexColor("#C0C0C0")
COL_BRONZE = colors.HexColor("#CD7F32")
COL_TROPHY_BG = colors.HexColor("#1a1a2e")
COL_HEADER_BG = colors.HexColor("#2c3e50")
COL_OVERALL_BG= colors.HexColor("#FFF8DC")
COL_BRANCH_HDR= colors.HexColor("#34495e")
COL_RANK1_BG = colors.HexColor("#FFF9E3")
COL_RANK2_BG = colors.HexColor("#F5F5F5")
COL_RANK3_BG = colors.HexColor("#FFF0E8")

def clean_gpa(raw) -> str:
    if raw is None:
        return "—"
    s = str(raw).strip()
    if s.startswith("["):
        try:
            import ast
            lst = ast.literal_eval(s)
            if isinstance(lst, (list, tuple)):
                for v in lst:
                    sv = str(v).strip()
                    if sv and sv not in ("-", "—", "None", "null", ""):
                        return sv
        except Exception:
            m = re.search(r"\d+\.?\d*", s)
            return m.group(0) if m else "—"
    return s if s else "—"

def parse_cgpa_float(r: dict) -> float:
    sgpa = clean_gpa(r.get("sgpa"))
    cgpa = clean_gpa(r.get("cgpa"))
    for val in (cgpa, sgpa):
        val = val.rstrip("*").strip()
        try:
            f = float(val)
            if f > 0:
                return f
        except Exception:
            pass
    return 0.0

def make_styles():
    b = getSampleStyleSheet()
    def S(name, **kw):
        kw.setdefault("parent", b["Normal"])
        return ParagraphStyle(name, **kw)
    return {
        "uni_name":         S("uni_name",   fontSize=16, fontName="Helvetica-Bold",   alignment=TA_CENTER, textColor=COL_BLACK,    leading=20, spaceAfter=0),
        "exam_title":       S("exam_title", fontSize=11, fontName="Helvetica-Bold",   alignment=TA_CENTER, textColor=COL_RED_EXAM, leading=15, spaceBefore=2),
        "lbl":              S("lbl",        fontSize=9,  fontName="Helvetica-Bold",   textColor=COL_BLACK),
        "val":              S("val",        fontSize=9,  fontName="Helvetica",        textColor=COL_BLACK),
        "sect":             S("sect",       fontSize=9,  fontName="Helvetica-Bold",   alignment=TA_LEFT,   textColor=COL_WHITE),
        "th":               S("th",         fontSize=9,  fontName="Helvetica-Bold",   alignment=TA_CENTER, textColor=COL_WHITE),
        "tdc":              S("tdc",        fontSize=9,  fontName="Helvetica",        alignment=TA_CENTER, textColor=COL_BLACK),
        "tdl":              S("tdl",        fontSize=9,  fontName="Helvetica",        alignment=TA_LEFT,   textColor=COL_BLACK),
        "rem_lbl":          S("rem_lbl",    fontSize=9,  fontName="Helvetica-Bold",   textColor=COL_BLACK),
        "rem_pass":         S("rem_pass",   fontSize=9,  fontName="Helvetica-Bold",   textColor=COL_PASS),
        "rem_fail":         S("rem_fail",   fontSize=9,  fontName="Helvetica-Bold",   textColor=COL_FAIL_REM),
        "info_title":       S("info_title", fontSize=14, fontName="Helvetica-Bold",   alignment=TA_CENTER, textColor=COL_BLACK,    leading=18, spaceAfter=0),
        "info_sub":         S("info_sub",   fontSize=10, fontName="Helvetica-Bold",   alignment=TA_CENTER, textColor=COL_RED_EXAM, leading=14, spaceBefore=2),
        "info_hdr":         S("info_hdr",   fontSize=9,  fontName="Helvetica-Bold",   alignment=TA_CENTER, textColor=COL_WHITE),
        "info_td":          S("info_td",    fontSize=9,  fontName="Helvetica",        alignment=TA_CENTER, textColor=COL_BLACK),
        "info_tdl":         S("info_tdl",   fontSize=9,  fontName="Helvetica",        alignment=TA_LEFT,   textColor=COL_BLACK),
        "info_pass":        S("info_pass",  fontSize=9,  fontName="Helvetica-Bold",   alignment=TA_CENTER, textColor=COL_PASS_TEXT),
        "info_fail":        S("info_fail",  fontSize=9,  fontName="Helvetica-Bold",   alignment=TA_CENTER, textColor=COL_FAIL_TEXT),
        "info_dash":        S("info_dash",  fontSize=9,  fontName="Helvetica",        alignment=TA_CENTER, textColor=colors.HexColor("#555555")),
        "top_heading":      S("top_heading",      fontSize=18, fontName="Helvetica-Bold",   alignment=TA_CENTER, textColor=COL_BLACK,      leading=22, spaceBefore=4, spaceAfter=2),
        "top_sub":          S("top_sub",          fontSize=11, fontName="Helvetica-Bold",   alignment=TA_CENTER, textColor=COL_RED_EXAM,   leading=14, spaceBefore=2, spaceAfter=6),
        "top_section_hdr":  S("top_section_hdr",  fontSize=11, fontName="Helvetica-Bold",   alignment=TA_CENTER, textColor=COL_WHITE,      leading=14),
        "top_overall_lbl":  S("top_overall_lbl",  fontSize=9,  fontName="Helvetica-Bold",   alignment=TA_CENTER, textColor=COL_GOLD_DARK),
        "top_overall_name": S("top_overall_name", fontSize=11, fontName="Helvetica-Bold",   alignment=TA_CENTER, textColor=COL_BLACK,      leading=14),
        "top_overall_val":  S("top_overall_val",  fontSize=10, fontName="Helvetica-Bold",   alignment=TA_CENTER, textColor=COL_GOLD_DARK),
        "top_overall_meta": S("top_overall_meta", fontSize=9,  fontName="Helvetica",        alignment=TA_CENTER, textColor=colors.HexColor("#555555")),
        "top_th":           S("top_th",           fontSize=9,  fontName="Helvetica-Bold",   alignment=TA_CENTER, textColor=COL_WHITE),
        "top_td_c":         S("top_td_c",         fontSize=9,  fontName="Helvetica",        alignment=TA_CENTER, textColor=COL_BLACK),
        "top_td_l":         S("top_td_l",         fontSize=9,  fontName="Helvetica",        alignment=TA_LEFT,   textColor=COL_BLACK),
        "top_cgpa":         S("top_cgpa",         fontSize=10, fontName="Helvetica-Bold",   alignment=TA_CENTER, textColor=COL_GOLD_DARK),
        "top_rank1":        S("top_rank1",         fontSize=10, fontName="Helvetica-Bold",   alignment=TA_CENTER, textColor=COL_BLACK),
        "top_rank2":        S("top_rank2",         fontSize=10, fontName="Helvetica-Bold",   alignment=TA_CENTER, textColor=COL_BLACK),
        "top_rank3":        S("top_rank3",         fontSize=10, fontName="Helvetica-Bold",   alignment=TA_CENTER, textColor=COL_BLACK),
        "top_medal":        S("top_medal",         fontSize=14, fontName="Helvetica-Bold",   alignment=TA_CENTER, textColor=COL_BLACK),
        "lbl_white":        S("lbl_white",         fontSize=9,  fontName="Helvetica-Bold",   textColor=colors.white),
    }

def header_table(logo_path: str, ST: dict) -> Table:
    logo_cell = ""
    if logo_path and os.path.exists(logo_path):
        try:
            from reportlab.platypus import Image
            logo_cell = Image(logo_path, width=30*mm, height=30*mm)
        except Exception:
            pass
    title_para = Paragraph("BIHAR ENGINEERING UNIVERSITY, PATNA", ST["uni_name"])
    sub_para   = Paragraph("B.Tech. 1st Semester Examination, 2026", ST["exam_title"])
    inner = Table([[title_para], [sub_para]], colWidths=[USABLE_W - 34*mm])
    inner.setStyle(TableStyle([
        ("ALIGN",         (0,0),(-1,-1), "CENTER"),
        ("VALIGN",        (0,0),(-1,-1), "MIDDLE"),
        ("TOPPADDING",    (0,0),(-1,-1), 0),
        ("BOTTOMPADDING", (0,0),(-1,-1), 0),
    ]))
    t = Table([[logo_cell, inner]], colWidths=[34*mm, USABLE_W - 34*mm])
    t.setStyle(TableStyle([
        ("VALIGN",        (0,0),(-1,-1), "MIDDLE"),
        ("ALIGN",         (0,0),(0,0),   "CENTER"),
        ("TOPPADDING",    (0,0),(-1,-1), 4),
        ("BOTTOMPADDING", (0,0),(-1,-1), 4),
        ("LEFTPADDING",   (0,0),(-1,-1), 0),
        ("RIGHTPADDING",  (0,0),(-1,-1), 0),
    ]))
    return t

def build_topper_page(all_results_by_branch: dict, college_name: str, ST: dict, logo_path: str) -> list:
    el = []
    el.append(header_table(logo_path, ST))
    el.append(Spacer(1, 4*mm))
    el.append(Spacer(1, 2*mm))
    all_results_flat = []
    for branch, results in all_results_by_branch.items():
        for r in results:
            if any(x in r.get("result","").upper() for x in ("PASS","PROMOTED")):
                r["_branch_key"] = branch
                all_results_flat.append(r)
    def top_n(lst, n=3):
        valid = [(parse_cgpa_float(r), r) for r in lst if parse_cgpa_float(r) > 0]
        valid.sort(key=lambda x: x[0], reverse=True)
        return valid[:n]
    overall_top3 = top_n(all_results_flat, 3)
    medals   = ["1st", "2nd", "3rd"]
    bg_cols  = [COL_RANK1_BG, COL_RANK2_BG, COL_RANK3_BG]
    txt_stys = ["top_rank1", "top_rank2", "top_rank3"]
    if overall_top3:
        overall_bar = Table(
            [[Paragraph("OVERALL COLLEGE TOPPERS", ST["top_section_hdr"])]],
            colWidths=[USABLE_W]
        )
        overall_bar.setStyle(TableStyle([
            ("BACKGROUND",    (0,0),(-1,-1), COL_INFO_HDR),
            ("BOX",           (0,0),(-1,-1), 0.8, COL_BLACK),
            ("TOPPADDING",    (0,0),(-1,-1), 6),
            ("BOTTOMPADDING", (0,0),(-1,-1), 6),
            ("LEFTPADDING",   (0,0),(-1,-1), 10),
            ("RIGHTPADDING",  (0,0),(-1,-1), 10),
        ]))
        el.append(overall_bar)
        el.append(Spacer(1, 3*mm))
        cw = [USABLE_W * p for p in [0.08, 0.10, 0.25, 0.15, 0.30, 0.12]]
        hdr = [
            Paragraph("Rank",       ST["top_th"]),
            Paragraph("Reg No",     ST["top_th"]),
            Paragraph("Name",       ST["top_th"]),
            Paragraph("Branch",     ST["top_th"]),
            Paragraph("College",    ST["top_th"]),
            Paragraph("CGPA",       ST["top_th"]),
        ]
        rows = [hdr]
        row_styles = []
        for idx, (cgpa_val, r) in enumerate(overall_top3):
            cgpa_str = f"{cgpa_val:.2f}"
            branch   = r.get("branch","—")
            college  = r.get("college","—")
            if college == "—": college = college_name
            row = [
                Paragraph(medals[idx],        ST[txt_stys[idx]]),
                Paragraph(r["reg_no"],         ST["top_td_c"]),
                Paragraph(r.get("name","—"),  ST["top_td_l"]),
                Paragraph(branch,              ST["top_td_l"]),
                Paragraph(college,             ST["top_td_l"]),
                Paragraph(cgpa_str,            ST[txt_stys[idx]]),
            ]
            rows.append(row)
            row_styles.append(("BACKGROUND", (0, idx+1), (-1, idx+1), bg_cols[idx]))
        base_ts = [
            ("BACKGROUND",    (0,0),(-1,0),  COL_INFO_HDR),
            ("BACKGROUND",    (0,1),(-1,-1), colors.white),
            ("BOX",           (0,0),(-1,-1), 0.8, COL_BLACK),
            ("INNERGRID",     (0,0),(-1,-1), 0.4, colors.HexColor("#aaaaaa")),
            ("VALIGN",        (0,0),(-1,-1), "MIDDLE"),
            ("TOPPADDING",    (0,0),(-1,-1), 6),
            ("BOTTOMPADDING", (0,0),(-1,-1), 6),
            ("LEFTPADDING",   (0,0),(-1,-1), 5),
            ("RIGHTPADDING",  (0,0),(-1,-1), 5),
        ]
        t = Table(rows, colWidths=cw, repeatRows=1)
        t.setStyle(TableStyle(base_ts))
        el.append(t)
        el.append(Spacer(1, 6*mm))
    branch_bar = Table(
        [[Paragraph("BRANCH-WISE TOPPERS", ST["top_section_hdr"])]],
        colWidths=[USABLE_W]
    )
    branch_bar.setStyle(TableStyle([
        ("BACKGROUND",    (0,0),(-1,-1), COL_INFO_HDR),
        ("BOX",           (0,0),(-1,-1), 0.8, COL_BLACK),
        ("TOPPADDING",    (0,0),(-1,-1), 6),
        ("BOTTOMPADDING", (0,0),(-1,-1), 6),
        ("LEFTPADDING",   (0,0),(-1,-1), 10),
        ("RIGHTPADDING",  (0,0),(-1,-1), 10),
    ]))
    el.append(branch_bar)
    el.append(Spacer(1, 3*mm))
    cw2 = [USABLE_W * p for p in [0.07, 0.14, 0.26, 0.37, 0.16]]
    hdr2 = [
        Paragraph("Rank",   ST["top_th"]),
        Paragraph("Reg No", ST["top_th"]),
        Paragraph("Name",   ST["top_th"]),
        Paragraph("Branch", ST["top_th"]),
        Paragraph("CGPA",   ST["top_th"]),
    ]
    for branch, results in sorted(all_results_by_branch.items()):
        passing = [r for r in results if any(x in r.get("result","").upper() for x in ("PASS","PROMOTED"))]
        top3 = top_n(passing, 3)
        if not top3:
            continue
        branch_sub = Table(
            [[Paragraph(branch, ST["lbl_white"])]],
            colWidths=[USABLE_W]
        )
        branch_sub.setStyle(TableStyle([
            ("BACKGROUND",    (0,0),(-1,-1), COL_INFO_HDR),
            ("BOX",           (0,0),(-1,-1), 0.5, COL_BLACK),
            ("TOPPADDING",    (0,0),(-1,-1), 5),
            ("BOTTOMPADDING", (0,0),(-1,-1), 5),
            ("LEFTPADDING",   (0,0),(-1,-1), 8),
            ("RIGHTPADDING",  (0,0),(-1,-1), 8),
        ]))
        el.append(branch_sub)
        rows2 = [hdr2]
        row_styles2 = []
        for idx, (cgpa_val, r) in enumerate(top3):
            cgpa_str = f"{cgpa_val:.2f}"
            row = [
                Paragraph(medals[idx],       ST[txt_stys[idx]]),
                Paragraph(r["reg_no"],        ST["top_td_c"]),
                Paragraph(r.get("name","—"), ST["top_td_l"]),
                Paragraph(r.get("branch","—"), ST["top_td_l"]),
                Paragraph(cgpa_str,           ST[txt_stys[idx]]),
            ]
            rows2.append(row)
            row_styles2.append(("BACKGROUND", (0, idx+1), (-1, idx+1), bg_cols[idx]))
        base_ts2 = [
            ("BACKGROUND",    (0,0),(-1,0),  COL_INFO_HDR),
            ("BACKGROUND",    (0,1),(-1,-1), colors.white),
            ("BOX",           (0,0),(-1,-1), 0.8, COL_BLACK),
            ("INNERGRID",     (0,0),(-1,-1), 0.4, colors.HexColor("#aaaaaa")),
            ("VALIGN",        (0,0),(-1,-1), "MIDDLE"),
            ("TOPPADDING",    (0,0),(-1,-1), 5),
            ("BOTTOMPADDING", (0,0),(-1,-1), 5),
            ("LEFTPADDING",   (0,0),(-1,-1), 5),
            ("RIGHTPADDING",  (0,0),(-1,-1), 5),
        ]
        t2 = Table(rows2, colWidths=cw2, repeatRows=1)
        t2.setStyle(TableStyle(base_ts2))
        el.append(t2)
        el.append(Spacer(1, 3*mm))
    return el

def build_topper_pdf(all_results_by_branch: dict, college_name: str, path: str, logo_path: str):
    ST = make_styles()
    frame = Frame(LM, BM, USABLE_W, PH - TM - BM, id="main")
    doc = BaseDocTemplate(
        path, pagesize=A4,
        leftMargin=LM, rightMargin=RM,
        topMargin=TM,  bottomMargin=BM,
    )
    def on_page(canvas, doc):
        canvas.saveState()
        canvas.setStrokeColor(colors.HexColor("#333333"))
        canvas.setLineWidth(0.8)
        canvas.rect(LM - 4, BM - 4, USABLE_W + 8, PH - TM - BM + 8)
        canvas.restoreState()
    doc.addPageTemplates([PageTemplate(id="main", frames=[frame], onPage=on_page)])
    story = build_topper_page(all_results_by_branch, college_name, ST, logo_path)
    doc.build(story)
    print(f"[*] topper pdf saved: {path}")

def build_info_page(results: list, ST: dict, logo_path: str) -> list:
    el = []
    el.append(header_table(logo_path, ST))
    el.append(Spacer(1, 3*mm))
    cw_num = USABLE_W * 0.05
    cw_reg = USABLE_W * 0.16
    cw_name = USABLE_W * 0.22
    cw_branch = USABLE_W * 0.35
    cw_gpa = USABLE_W * 0.12
    cw_status = USABLE_W * 0.10
    cws = [cw_num, cw_reg, cw_name, cw_branch, cw_gpa, cw_status]
    hdr = [
        Paragraph("#",          ST["info_hdr"]),
        Paragraph("Reg No",     ST["info_hdr"]),
        Paragraph("Name",       ST["info_hdr"]),
        Paragraph("Branch",     ST["info_hdr"]),
        Paragraph("SGPA/CGPA",  ST["info_hdr"]),
        Paragraph("Status",     ST["info_hdr"]),
    ]
    rows = [hdr]
    row_styles = []
    for idx, r in enumerate(results, start=1):
        result_raw = r.get("result", "—").strip().upper()
        is_pass  = any(x in result_raw for x in ("PASS", "PROMOTED"))
        is_fail  = any(x in result_raw for x in ("FAIL", "DETAINED"))
        has_error = bool(r.get("error"))
        sgpa = clean_gpa(r.get("sgpa"))
        cgpa = clean_gpa(r.get("cgpa"))
        gpa_display = sgpa if sgpa != "—" else cgpa
        if gpa_display != "—" and not gpa_display.endswith("*") and (cgpa != "—"):
            gpa_display = cgpa + "*"
        if has_error:
            status_para = Paragraph("N/A", ST["info_dash"])
        elif is_pass:
            status_para = Paragraph("PASS", ST["info_pass"])
        elif is_fail:
            status_para = Paragraph("FAIL", ST["info_fail"])
        else:
            status_para = Paragraph(result_raw or "—", ST["info_td"])
        branch = r.get("branch", "—")
        name = r.get("name",   "—")
        row = [
            Paragraph(str(idx),   ST["info_td"]),
            Paragraph(r["reg_no"], ST["info_td"]),
            Paragraph(name,        ST["info_tdl"]),
            Paragraph(branch,      ST["info_tdl"]),
            Paragraph(gpa_display, ST["info_td"]),
            status_para,
        ]
        rows.append(row)
        data_row_idx = idx
        if has_error:
            row_styles.append(("BACKGROUND", (0, data_row_idx), (-1, data_row_idx), colors.HexColor("#fffde7")))
        elif is_fail:
            row_styles.append(("BACKGROUND", (0, data_row_idx), (-1, data_row_idx), COL_INFO_FAIL))
        elif is_pass:
            row_styles.append(("BACKGROUND", (0, data_row_idx), (-1, data_row_idx), COL_INFO_PASS))
    t = Table(rows, colWidths=cws, repeatRows=1)
    base_style = [
        ("BACKGROUND",    (0,0),(-1,0),  COL_INFO_HDR),
        ("BOX",           (0,0),(-1,-1), 0.8, COL_BLACK),
        ("INNERGRID",     (0,0),(-1,-1), 0.4, colors.HexColor("#aaaaaa")),
        ("VALIGN",        (0,0),(-1,-1), "MIDDLE"),
        ("TOPPADDING",    (0,0),(-1,-1), 5),
        ("BOTTOMPADDING", (0,0),(-1,-1), 5),
        ("LEFTPADDING",   (0,0),(-1,-1), 5),
        ("RIGHTPADDING",  (0,0),(-1,-1), 5),
    ]
    t.setStyle(TableStyle(base_style + row_styles))
    el.append(t)
    total  = len(results)
    passed = sum(1 for r in results if any(x in r.get("result","").upper() for x in ("PASS","PROMOTED")))
    failed = sum(1 for r in results if any(x in r.get("result","").upper() for x in ("FAIL","DETAINED")))
    no_res = sum(1 for r in results if r.get("error"))
    cgpa_vals = [parse_cgpa_float(r) for r in results if any(x in r.get("result","").upper() for x in ("PASS","PROMOTED"))]
    highest_cgpa = max(cgpa_vals) if cgpa_vals else 0.0
    el.append(Spacer(1, 5*mm))
    stats_data = [[
        Paragraph(f"<b>Total Students:</b> {total}",                              ST["lbl"]),
        Paragraph(f"<b>Passed:</b> <font color='#006400'>{passed}</font>",        ST["lbl"]),
        Paragraph(f"<b>Failed:</b> <font color='#cc0000'>{failed}</font>",        ST["lbl"]),
        Paragraph(f"<b>No Result:</b> {no_res}",                                  ST["lbl"]),
        Paragraph(f"<b>Highest CGPA:</b> <font color='#7B5C00'>{highest_cgpa:.2f}</font>", ST["lbl"]),
    ]]
    stats_t = Table(stats_data, colWidths=[USABLE_W/5]*5)
    stats_t.setStyle(TableStyle([
        ("BOX",           (0,0),(-1,-1), 0.5, COL_BLACK),
        ("INNERGRID",     (0,0),(-1,-1), 0.5, COL_BLACK),
        ("BACKGROUND",    (0,0),(-1,-1), colors.HexColor("#f5f5f5")),
        ("TOPPADDING",    (0,0),(-1,-1), 6),
        ("BOTTOMPADDING", (0,0),(-1,-1), 6),
        ("LEFTPADDING",   (0,0),(-1,-1), 8),
        ("RIGHTPADDING",  (0,0),(-1,-1), 8),
        ("ALIGN",         (0,0),(-1,-1), "CENTER"),
    ]))
    el.append(stats_t)
    return el

def section_bar(title: str, ST: dict) -> Table:
    t = Table([[Paragraph(title, ST["sect"])]], colWidths=[USABLE_W])
    t.setStyle(TableStyle([
        ("BACKGROUND",    (0,0),(-1,-1), COL_SECT_BG),
        ("TEXTCOLOR",     (0,0),(-1,-1), COL_WHITE),
        ("BOX",           (0,0),(-1,-1), 0.5, COL_BLACK),
        ("TOPPADDING",    (0,0),(-1,-1), 6),
        ("BOTTOMPADDING", (0,0),(-1,-1), 6),
        ("LEFTPADDING",   (0,0),(-1,-1), 8),
        ("RIGHTPADDING",  (0,0),(-1,-1), 8),
        ("VALIGN",        (0,0),(-1,-1), "MIDDLE"),
    ]))
    return t

def build_pdf(results: list, path: str, logo_path: str):
    ST = make_styles()
    frame = Frame(LM, BM, USABLE_W, PH - TM - BM, id="main")
    doc = BaseDocTemplate(
        path, pagesize=A4,
        leftMargin=LM, rightMargin=RM,
        topMargin=TM,  bottomMargin=BM,
    )
    def on_page(canvas, doc):
        canvas.saveState()
        canvas.setStrokeColor(colors.HexColor("#333333"))
        canvas.setLineWidth(0.8)
        canvas.rect(LM - 4, BM - 4, USABLE_W + 8, PH - TM - BM + 8)
        canvas.setFont("Helvetica-Bold", 52)
        canvas.setFillColor(colors.HexColor("#ff5370"))
        canvas.setFillAlpha(0.06)
        canvas.translate(PW/2, PH/2)
        canvas.rotate(35)
        canvas.restoreState()
    doc.addPageTemplates([PageTemplate(id="main", frames=[frame], onPage=on_page)])
    story = []
    story.extend(build_info_page(results, ST, logo_path))
    doc.build(story)
    print(f"\n[*] pdf saved: {path}")

def fetch_set(session, label, start, end):
    reg_numbers = [str(n) for n in range(int(start), int(end) + 1)]
    print(f"\n{'='*60}")
    print(f"[+] Set: {label}  |  {reg_numbers[0]}: {reg_numbers[-1]}  ({len(reg_numbers)} regs)")
    print(f"{'='*60}")
    if not getattr(fetch_set, "_inspected", False):
        fetch_set._inspected = True
        url0 = API_URL.format(year=YEAR, reg=reg_numbers[0], sem=SEMESTER, exam=EXAM)
        try:
            r0 = session.get(url0, headers=HEADERS, timeout=20)
            print(f"  HTTP: {r0.status_code}  |  Content-Type: {r0.headers.get('content-type','?')}")
            try:
                j = r0.json()
                print(f"[-] full JSON (first 3000 chars):")
                print(json.dumps(j, indent=2, ensure_ascii=False)[:3000])
            except Exception:
                print(f"[-] raw (first 500 chars): {r0.text[:500]}")
        except Exception as e:
            print(f"[!] {e}")
    all_results = []
    ok = fail = err = 0
    for i, reg in enumerate(reg_numbers, 1):
        print(f" [{i:02d}/{len(reg_numbers)}] {reg} … ", end="", flush=True)
        result = fetch_result(session, reg)
        all_results.append(result)
        st = result.get("result", "—")
        if result.get("error"):
            print(f"[!]  {result['error']}")
            err += 1
        elif any(x in st.upper() for x in ("PASS", "PROMOTED")):
            print(f"PASS  |  {result['name']}  |  CGPA: {result.get('cgpa','—')}")
            ok += 1
        elif any(x in st.upper() for x in ("FAIL", "DETAINED")):
            print(f"FAIL  |  {result['name']}  |  {result.get('remarks','—')}")
            fail += 1
        else:
            print(f"?  {result['name']}  |  {st}")
        time.sleep(0.3)
    print(f"\n{'─'*60}")
    print(f"[+] passed: {ok}  |  failed: {fail}  |  no result: {err}")
    print(f"{'─'*60}")
    return all_results

def merge_pdfs(pdf_paths: list, output_path: str):
    try:
        from pypdf import PdfWriter, PdfReader
        print("[+] Using pypdf")
    except ImportError:
        from PyPDF2 import PdfWriter, PdfReader
        print("[+] Using PyPDF2")
    writer = PdfWriter()
    total = 0
    for pdf in pdf_paths:
        if os.path.exists(pdf):
            reader = PdfReader(pdf)
            for page in reader.pages:
                writer.add_page(page)
                total += 1
            print(f"[+] Added {len(reader.pages)} pages from: {os.path.basename(pdf)}")
        else:
            print(f"[!] Not found, skipping: {pdf}")
    if total == 0:
        print("[!] No pages collected — aborting merge.")
        return False
    with open(output_path, "wb") as f:
        writer.write(f)
    print(f"\n[*] Merged PDF saved ({total} pages): {output_path}")
    for pdf in pdf_paths:
        if os.path.exists(pdf) and os.path.abspath(pdf) != os.path.abspath(output_path):
            os.remove(pdf)
            print(f"[-] Deleted temp: {os.path.basename(pdf)}")
    return True

def main():
    logo_path = ensure_logo()
    session = requests.Session()
    out_dir = os.path.dirname(os.path.abspath(OUTPUT_PDF))
    base_name = os.path.splitext(os.path.basename(OUTPUT_PDF))[0]
    set_pdfs = []
    all_results_by_label = {}
    for label, start, end in args.regset:
        safe_label = re.sub(r"[^A-Za-z0-9_\-]", "_", label)
        set_pdf = os.path.join(out_dir, f"{base_name}__{safe_label}.pdf")
        results = fetch_set(session, label, start, end)
        all_results_by_label[label.replace("_", " ")] = [
            {k: v for k, v in r.items() if k != "raw"} for r in results
        ]
        print(f"\n[+] Generating PDF for set '{label}': {set_pdf}")
        build_pdf(results, set_pdf, logo_path)
        set_pdfs.append(set_pdf)
    topper_pdf = os.path.join(out_dir, f"{base_name}__TOPPERS.pdf")
    college = COLLEGE_NAME or base_name.replace("_", " ")
    if all_results_by_label:
        print(f"\n[+] Generating topper page: {topper_pdf}")
        build_topper_pdf(all_results_by_label, college_name=college, path=topper_pdf, logo_path=logo_path)
    else:
        print("[!] No result data — skipping topper page.")
        topper_pdf = None
    merge_order = []
    if topper_pdf and os.path.exists(topper_pdf):
        merge_order.append(topper_pdf)
    merge_order.extend(set_pdfs)
    print(f"\n[+] merging {len(merge_order)} PDFs: {OUTPUT_PDF}")
    merge_pdfs(merge_order, OUTPUT_PDF)
    print(f"\n[+] output: {OUTPUT_PDF}")

if __name__ == "__main__":
    main()