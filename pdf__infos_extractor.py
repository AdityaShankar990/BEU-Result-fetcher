import pdfplumber, re, os
from collections import OrderedDict

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
OUTPUT_PDF = os.path.join(BASE_DIR, "beu_reg_out.pdf")
colleges = OrderedDict()

def clean_name(x):
    x = x.upper()
    x = x.replace("&", "AND")
    x = re.sub(r'[^A-Z0-9]+', '_', x)
    x = re.sub(r'_+', '_', x)
    return x.strip('_')

with pdfplumber.open(OUTPUT_PDF) as pdf:
    for page in pdf.pages:
        tables = page.extract_tables()
        for table in tables:
            for row in table:
                if not row:
                    continue
                row = [str(x).strip() if x else "" for x in row]
                # SR | CC | BB | MM | COLLEGE | BRANCH | START | END | TOTAL
                if len(row) < 8:
                    continue
                start = row[-3]
                end   = row[-2]
                # check valid registration
                if not (start.startswith("25") and end.startswith("25")):
                    continue
                college = row[-5]
                branch  = row[-4]
                college = clean_name(college)
                branch = clean_name(branch)
                if college not in colleges:
                    colleges[college] = []
                colleges[college].append(f"{branch} {start} {end}")

for college, branches in colleges.items():
    joined = "|\\\n".join(branches)
    print(f'colleges["{college}"]="\\\\\n'
          f'{joined}"\n')