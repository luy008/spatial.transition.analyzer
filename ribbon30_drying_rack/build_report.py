"""Build report.html from results.json.  Run: python3 build_report.py [--fragment out.html]"""
from __future__ import annotations

import json
import math
import sys
from pathlib import Path

HERE = Path(__file__).parent
R = json.loads((HERE / "results.json").read_text(encoding="utf-8"))
FY = R["inputs"]["fy"]
G = R["inputs"]["g"]


def f(x, d=1):
    return f"{x:,.{d}f}"


def sci(x):
    e = int(math.floor(math.log10(x)))
    sup = str(e).translate(str.maketrans("0123456789-", "⁰¹²³⁴⁵⁶⁷⁸⁹⁻"))
    return f"{x / 10**e:.1f}×10{sup}"


def chip(state, text):
    icon = {"ok": "✓", "warn": "!", "bad": "✕", "info": "i"}[state]
    return f'<span class="chip {state}"><b aria-hidden="true">{icon}</b>{text}</span>'


def util_chip(u):
    return chip("ok" if u <= 0.8 else "warn" if u <= 1.0 else "bad", f"{u:.2f}")


# ---------------- derived numbers ----------------
cases = R["rigid"]
sweep = [s for s in R["joint_sweep"] if not s.get("mechanism")]
W_rack = R["mass"]["total_kg"] * G
W_uls = 1.35 * W_rack + 1.5 * R["inputs"]["laundry_kg"] * G


def k_for_alpha(target):
    pts = sorted((s["k_Nmm_per_rad"], s["alpha_cr"]) for s in sweep)
    for (k1, a1), (k2, a2) in zip(pts, pts[1:]):
        if a1 <= target <= a2:
            t = (math.log(target) - math.log(a1)) / (math.log(a2) - math.log(a1))
            return math.exp(math.log(k1) + t * (math.log(k2) - math.log(k1)))
    return float("nan")


K_ALPHA1 = k_for_alpha(1.0)
K_ALPHA10 = k_for_alpha(10.0)


def collapse_laundry_kg(alpha_uls):
    """Laundry mass (uniform) at which the elastic critical load is reached, no imperfections."""
    return (alpha_uls * W_uls - W_rack) / G


loose = next(s for s in sweep if s["k_Nmm_per_rad"] == 1e4)
mid = next(s for s in sweep if s["k_Nmm_per_rad"] == 3e4)
rigid = sweep[0]
braced = R["braced_pinned"]

frame_uls = max(c["uls"]["frame_vm"] for c in cases.values())
rod_uls_rigid = max(c["uls"]["rod_vm"] for c in cases.values())
joint_uls = max(c["uls"]["joint_M_Nmm"] for c in cases.values())
jr = R["joint_resistance"]
rod_ss = R["rod_simply_supported"]["cases"]
w_self_sig = rod_ss["한 봉 5kg"]["sigma"] - R["fatigue"]["rod_range_rod5"]
rod_uls_pinned = 1.35 * w_self_sig + 1.5 * R["fatigue"]["rod_range_rod5"]
min_alpha_rigid = min(c["alpha_cr_uls"] for c in cases.values())
design_cap_global = min(cases[k]["laundry_design_capacity_kg"] for k in ("U", "W", "L70", "C", "HX", "HZ"))
rod_point_cap = R["rod_simply_supported"]["design_point_capacity_kg"]
fric = max(c["foot_friction_demand"] for c in cases.values())
lb = R["local_buckling"]
max_comp = max(c["uls"]["frame_comp"] for c in cases.values())
lam_lt = math.sqrt(R["ltb"]["M_el_strong"] / R["ltb"]["arc_span_1020"])
phi = 0.5 * (1 + 0.76 * (lam_lt - 0.2) + lam_lt**2)
chi_lt = min(1.0, 1 / (phi + math.sqrt(phi**2 - lam_lt**2)))
fat = R["fatigue"]
tip = R["tipping"]

# ---------------- laundry scenarios ----------------
RMC_LO, RMC_HI = 0.53, 0.72
scen = [
    ("EU 평균 1회 세탁량(2020)", 4.0, "EEA 자료의 수치(검색 결과에서 확인, 원문 접속 실패)", "중"),
    ("8~9kg 드럼 가득 (3~4인 권장 용량)", 9.0, "Bosch 구매 안내", "중"),
    ("국내 드럼 21kg의 절반", 10.5, "국내 구매 가이드(블로그)", "낮음"),
    ("국내 통돌이 18kg의 80%", 14.4, "국내 구매 가이드(블로그)", "낮음"),
    ("국내 통돌이 18kg 꽉 채움 (극단)", 18.0, "가정한 상한", "가정"),
]


# ---------------- drawings ----------------
def arc_y(x):
    return 1200 - 150 * ((x - 600) / 510) ** 2


def front_svg():
    s, ox, oy = 0.28, 40, 400

    def P(x, y):
        return f"{ox + x * s:.1f},{oy - y * s:.1f}"

    pts = [(0, 0), (0, 180), (30, 750), (90, 1050)]
    pts += [(x, arc_y(x)) for x in range(90, 1111, 30)]
    pts += [(1110, 1050), (1170, 750), (1200, 180), (1200, 0)]
    poly = " ".join(P(*p) for p in pts) + " " + P(0, 0)
    rods = "".join(f'<circle cx="{ox + x * s:.1f}" cy="{oy - arc_y(x) * s:.1f}" r="3.2" class="m-rod"/>'
                   for x in range(90, 1111, 60))
    feet = "".join(f'<rect x="{ox + x * s - 6:.1f}" y="{oy:.1f}" width="12" height="5" rx="1.5" class="m-foot"/>'
                   for x in (0, 1200))
    dims = (f'<line x1="{ox}" y1="{oy + 22}" x2="{ox + 1200 * s}" y2="{oy + 22}" class="m-dim"/>'
            f'<text x="{ox + 600 * s}" y="{oy + 36}" class="m-t" text-anchor="middle">1,200 (발 중심 간격)</text>'
            f'<line x1="{ox + 1200 * s + 26}" y1="{oy}" x2="{ox + 1200 * s + 26}" y2="{oy - 1200 * s}" class="m-dim"/>'
            f'<text x="{ox + 1200 * s + 32}" y="{oy - 600 * s}" class="m-t">1,200</text>'
            f'<text x="{ox + 600 * s}" y="{oy - 1200 * s - 12}" class="m-t" text-anchor="middle">봉 18개 · 60 간격 · 포물선 위 띠</text>'
            f'<text x="{ox + 30 * s + 10}" y="{oy - 750 * s + 4}" class="m-t">(30, 750)</text>'
            f'<text x="{ox + 10}" y="{oy - 180 * s + 4}" class="m-t">(0, 180)</text>')
    return (f'<svg viewBox="0 0 440 450" role="img" aria-label="정면도: 폭 1,200mm, 높이 1,200mm 띠형 프레임과 봉 18개">'
            f'<polygon points="{poly}" class="m-frame"/>{rods}{feet}{dims}'
            f'<text x="12" y="20" class="m-h">정면 (X–Y) · 프레임 1개</text></svg>')


def side_svg():
    s, ox, oy = 0.26, 70, 400

    def X(z):
        return ox + z * s

    def Y(y):
        return oy - y * s

    legs = ""
    for z in (0, 1000):
        legs += f'<line x1="{X(z)}" y1="{Y(0)}" x2="{X(z)}" y2="{Y(1200)}" class="m-leg"/>'
    rodline = f'<line x1="{X(0)}" y1="{Y(1150)}" x2="{X(1000)}" y2="{Y(1150)}" class="m-rodline"/>'
    brace = (f'<line x1="{X(0)}" y1="{Y(0)}" x2="{X(1000)}" y2="{Y(750)}" class="m-brace"/>'
             f'<line x1="{X(1000)}" y1="{Y(0)}" x2="{X(0)}" y2="{Y(750)}" class="m-brace"/>')
    sway = (f'<line x1="{X(0)}" y1="{Y(0)}" x2="{X(0) + 46}" y2="{Y(1200)}" class="m-sway"/>'
            f'<line x1="{X(1000)}" y1="{Y(0)}" x2="{X(1000) + 46}" y2="{Y(1200)}" class="m-sway"/>'
            f'<line x1="{X(0) + 46}" y1="{Y(1150) - 2}" x2="{X(1000) + 46}" y2="{Y(1150) - 2}" class="m-sway"/>'
            f'<path d="M{X(500) - 10},{Y(1290)} h40" class="m-arrow" marker-end="url(#ah)"/>'
            f'<text x="{X(500) + 36}" y="{Y(1290) + 4}" class="m-t">래킹(길이방향 흔들림)</text>')
    feet = "".join(f'<rect x="{X(z) - 6}" y="{Y(0)}" width="12" height="5" rx="1.5" class="m-foot"/>' for z in (0, 1000))
    dims = (f'<line x1="{X(0)}" y1="{Y(0) + 22}" x2="{X(1000)}" y2="{Y(0) + 22}" class="m-dim"/>'
            f'<text x="{X(500)}" y="{Y(0) + 36}" class="m-t" text-anchor="middle">1,000 (프레임 간격 = 봉 길이)</text>'
            f'<text x="{X(500)}" y="{Y(560)}" class="m-t" text-anchor="middle">점선: X 가새(대안 B)</text>')
    defs = '<defs><marker id="ah" viewBox="0 0 8 8" refX="7" refY="4" markerWidth="7" markerHeight="7" orient="auto"><path d="M0,0 L8,4 L0,8 z" class="m-arrowhead"/></marker></defs>'
    return (f'<svg viewBox="0 0 440 450" role="img" aria-label="측면도: 프레임 2개 간격 1,000mm, 래킹 변형과 X 가새 대안">{defs}'
            f'{brace}{sway}{legs}{rodline}{feet}{dims}'
            f'<text x="12" y="20" class="m-h">측면 (Z–Y) · 끝에서 본 모습</text></svg>')


def alpha_chart():
    W, H = 640, 330
    L, Rm, T, B = 58, 20, 20, 48
    xmin, xmax = 3, 10
    ymin, ymax = math.log10(0.03), math.log10(30)

    def px(k):
        return L + (math.log10(k) - xmin) / (xmax - xmin) * (W - L - Rm)

    def py(a):
        return T + (ymax - math.log10(a)) / (ymax - ymin) * (H - T - B)

    g = []
    # zones
    g.append(f'<rect x="{L}" y="{py(1):.1f}" width="{W - L - Rm}" height="{py(0.03) - py(1):.1f}" class="z-bad"/>')
    g.append(f'<rect x="{L}" y="{py(10):.1f}" width="{W - L - Rm}" height="{py(1) - py(10):.1f}" class="z-warn"/>')
    for a in (0.1, 1, 10):
        g.append(f'<line x1="{L}" x2="{W - Rm}" y1="{py(a):.1f}" y2="{py(a):.1f}" class="grid"/>')
        g.append(f'<text x="{L - 8}" y="{py(a) + 4:.1f}" class="tick" text-anchor="end">{a:g}</text>')
    for e in range(3, 11):
        g.append(f'<line x1="{px(10**e):.1f}" x2="{px(10**e):.1f}" y1="{T}" y2="{H - B}" class="grid"/>')
        g.append(f'<text x="{px(10**e):.1f}" y="{H - B + 18}" class="tick" text-anchor="middle">10<tspan dy="-6" font-size="9">{e}</tspan></text>')
    g.append(f'<text x="{W - Rm - 8}" y="{py(1) + 18:.1f}" class="zl" text-anchor="end">α &lt; 1 · 30kg에서 무너짐</text>')
    g.append(f'<text x="{W - Rm - 8}" y="{py(10) + 18:.1f}" class="zl" text-anchor="end">1 ≤ α &lt; 10 · 2차 효과 커짐</text>')
    g.append(f'<text x="{L + 8}" y="{py(10) - 8:.1f}" class="zl">α ≥ 10 · 충분</text>')
    pts = sorted((s["k_Nmm_per_rad"], s["alpha_cr"]) for s in sweep)
    d = " ".join(f"{'M' if i == 0 else 'L'}{px(k):.1f},{py(a):.1f}" for i, (k, a) in enumerate(pts))
    g.append(f'<path d="{d}" class="series"/>')
    for k, a in pts:
        lab = "용접(사실상 강접합)" if k >= 1e9 else f"{k:,.0f} N·mm/rad"
        g.append(f'<circle cx="{px(k):.1f}" cy="{py(a):.1f}" r="4.5" class="dot" tabindex="0" '
                 f'data-tip="{lab} → α<sub>cr</sub> = {a:.2f}"><title>{lab}: α = {a:.2f}</title></circle>')
    for k, lab in ((K_ALPHA1, "α=1"), (K_ALPHA10, "α=10")):
        g.append(f'<line x1="{px(k):.1f}" x2="{px(k):.1f}" y1="{T}" y2="{H - B}" class="mark"/>')
        g.append(f'<text x="{px(k) + 5:.1f}" y="{T + 12}" class="tick">{lab}: {sci(k)}</text>')
    g.append(f'<text x="{(L + W - Rm) / 2}" y="{H - 8}" class="axis" text-anchor="middle">봉–프레임 접합 회전강성 k (N·mm/rad, 로그)</text>')
    g.append(f'<text transform="translate(14 {(T + H - B) / 2}) rotate(-90)" class="axis" text-anchor="middle">임계하중계수 α<tspan dy="3" font-size="9">cr</tspan> (로그)</text>')
    return f'<svg viewBox="0 0 {W} {H}" id="achart" role="img" aria-label="접합 회전강성에 따른 임계하중계수 그래프">{"".join(g)}</svg>'


# ---------------- tables ----------------
def case_rows():
    rows = []
    for key, c in cases.items():
        s, u = c["service"], c["uls"]
        rows.append(
            f"<tr><td>{c['label']}</td><td class=n>{f(s['frame_disp_mm'], 3)}</td><td class=n>{f(s['rod_sag_mm'], 2)}</td>"
            f"<td class=n>{f(s['frame_sigma'])}</td><td class=n>{f(s['rod_sigma'])}</td>"
            f"<td class=n>{f(u['frame_vm'])}</td><td class=n>{f(u['rod_vm'])}</td>"
            f"<td class=n>{f(u['joint_M_Nmm'] / 1000, 2)}</td><td class=n>{f(c['alpha_cr_uls'])}</td></tr>")
    return "".join(rows)


def sweep_rows():
    rows = []
    for s in sweep:
        k = s["k_Nmm_per_rad"]
        a = s["alpha_cr"]
        st = "ok" if a >= 10 else "warn" if a >= 1 else "bad"
        lab = "강접합(용접)" if k >= 1e9 else f"{k:,.0f}"
        rows.append(f"<tr><td class=n>{lab}</td><td class=n>{chip(st, f'{a:.2f}')}</td>"
                    f"<td class=n>{f(collapse_laundry_kg(a), 0) if collapse_laundry_kg(a) > 0 else '빈 상태도 불안정'}</td>"
                    f"<td class=n>{f(s['sway_z_per_15N_mm'], 1)}</td><td class=n>{f(s['rod_sag_rod5_mm'], 2)}</td>"
                    f"<td class=n>{f(s['rod_vm_rod5'])}</td></tr>")
    return "".join(rows)


def scen_rows():
    out = []
    for label, dry, src, conf in scen:
        lo, hi = dry * (1 + RMC_LO), dry * (1 + RMC_HI)
        st = "ok" if hi <= 30 else "warn"
        out.append(f"<tr><td>{label}</td><td class=n>{f(dry)}</td><td class=n>{f(lo)} ~ {f(hi)}</td>"
                   f"<td>{chip(st, f'{hi / 30 * 100:.0f}%')}</td><td>{src}</td><td>{conf}</td></tr>")
    return "".join(out)


def tip_rows():
    out = []
    for t in tip:
        wind = f"{t['v_wind_tip_ms']:.0f} / {t['v_wind_slide_mu03_ms']:.0f}" if "v_wind_tip_ms" in t else "–"
        first = "미끄러짐" if t["H_slide_mu03_N"] < t["H_tip_N"] else "넘어짐"
        out.append(f"<tr><td>{t['case']}</td><td class=n>{f(t['H_tip_N'])}</td><td class=n>{f(t['H_slide_mu03_N'])}</td>"
                   f"<td class=n>{f(t['H_slide_mu05_N'])}</td><td>{first}</td><td class=n>{wind}</td></tr>")
    return "".join(out)


check_rows = [
    ("프레임 강도 (설계하중, 최악 경우)", f"{f(frame_uls)} MPa", f"{FY:g} MPa", frame_uls / FY, "모서리 편중 + 1.35G + 1.5Q"),
    ("봉 강도 · 강접합 (설계하중)", f"{f(rod_uls_rigid)} MPa", f"{FY:g} MPa", rod_uls_rigid / FY, "가운데 봉 5kg 집중"),
    ("봉 강도 · 핀접합 (설계하중)", f"{f(rod_uls_pinned)} MPa", f"{FY:g} MPa", rod_uls_pinned / FY, "단순지지, 봉 하나 중앙 5kg"),
    ("봉–프레임 접합 모멘트 (참고식)", f"{f(joint_uls / 1000, 2)} N·m", f"{f(jr['M_op_Nmm'] / 1000, 1)} N·m", joint_uls / jr["M_op_Nmm"], "EN 1993-1-8 표 7.14 형식, 두께 1mm는 적용범위 밖"),
    ("전체 좌굴 (강접합)", f"α = {f(min_alpha_rigid)}", "α ≥ 10", 10 / min_alpha_rigid, "1차 모드 = 길이방향 래킹"),
    ("벽 국부좌굴 (압축 40mm 벽)", f"{f(max_comp)} MPa", f"σcr ≈ {f(lb['sigma_cr_web_compression'], 0)} MPa", max_comp / lb["sigma_cr_web_compression"], f"단면 등급: 압축 {lb['class_web_compression']}등급, 휨 {lb['class_web_bending']}등급"),
    ("횡비틀림좌굴 (상부 띠 1,020mm)", f"λ̄LT = {lam_lt:.2f}", f"χLT ≈ {chi_lt:.2f}", frame_uls / (FY * chi_lt), "폐단면이라 영향 작음"),
    ("피로 · 봉 (15년 · 하루 2회)", f"{f(fat['rod_range_rod5'])} MPa", f"{f(fat['allowable'], 0)} MPa", fat["rod_range_rod5"] / fat["allowable"], f"상세등급 36(최저 수준) 가정, {fat['cycles']:,}회"),
    ("구멍 응력집중 · 프레임 (Kt = 3)", f"{f(3 * max(c['service']['frame_sigma'] for c in cases.values()))} MPa", f"{FY:g} MPa", 3 * max(c['service']['frame_sigma'] for c in cases.values()) / FY, "사용하중, 어디에 구멍이 있어도"),
    ("구멍 응력집중 · 봉 중앙 (Kt = 3)", f"{f(3 * rod_ss['한 봉 5kg']['sigma'])} MPa", f"{FY:g} MPa", 3 * rod_ss['한 봉 5kg']['sigma'] / FY, "봉 중앙에는 구멍 금지"),
    ("가새 압축 (대안 B)", f"{f(braced['uls_brace_max_N'])} N", f"{f(braced['brace_euler_N'], 0)} N", braced["uls_brace_max_N"] / braced["brace_euler_N"], "탄성 좌굴하중 대비, 핀 단부"),
]


def check_table():
    out = []
    for name, demand, cap, u, note in check_rows:
        out.append(f"<tr><td>{name}</td><td class=n>{demand}</td><td class=n>{cap}</td><td>{util_chip(u)}</td><td>{note}</td></tr>")
    return "".join(out)


CSS = """
:root{
  /* layout: one reading column, calc-sheet tables, verdict first */
  --bg:#eef1f4; --surface:#ffffff; --ink:#16202a; --ink-2:#465462; --muted:#6f7c89; --line:#d3dae1;
  --accent:#1d5d8c; --accent-wash:#e3edf5;
  --ok:#23704a; --ok-wash:#e2f1e8; --warn:#8a5a00; --warn-wash:#fbefd6; --bad:#a3271f; --bad-wash:#f8e1df;
  --display:"IBM Plex Sans KR","Apple SD Gothic Neo","Malgun Gothic",sans-serif;
  --mono:"IBM Plex Mono",ui-monospace,Menlo,Consolas,monospace;
}
@media (prefers-color-scheme:dark){:root:not([data-theme="light"]){
  --bg:#0e141a; --surface:#151d25; --ink:#e3e9ef; --ink-2:#a9b5c1; --muted:#7e8b98; --line:#2a3541;
  --accent:#73b2e0; --accent-wash:#1a2a38;
  --ok:#62c993; --ok-wash:#173327; --warn:#e3a944; --warn-wash:#3a2c12; --bad:#f2837a; --bad-wash:#3d1c1a; color-scheme:dark}}
:root[data-theme="dark"]{
  --bg:#0e141a; --surface:#151d25; --ink:#e3e9ef; --ink-2:#a9b5c1; --muted:#7e8b98; --line:#2a3541;
  --accent:#73b2e0; --accent-wash:#1a2a38;
  --ok:#62c993; --ok-wash:#173327; --warn:#e3a944; --warn-wash:#3a2c12; --bad:#f2837a; --bad-wash:#3d1c1a; color-scheme:dark}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--ink);font:15px/1.75 var(--display);padding-inline:16px}
main{max-width:900px;margin:0 auto;padding-block:40px 64px;display:grid;gap:12px}
h1{font-size:clamp(26px,4.4vw,38px);line-height:1.25;margin:4px 0 6px;text-wrap:balance;font-weight:700;letter-spacing:-.01em}
h2{font-size:21px;margin:34px 0 4px;text-wrap:balance;font-weight:700}
h3{font-size:16px;margin:18px 0 0}
p{margin:0;max-width:68ch}
.eyebrow{font:500 12px/1 var(--mono);letter-spacing:.14em;text-transform:uppercase;color:var(--accent)}
.lede{color:var(--ink-2);font-size:16px}
.verdict{background:var(--surface);border:1px solid var(--line);border-left:5px solid var(--warn);border-radius:6px;padding:20px 22px;display:grid;gap:12px}
.verdict h2{margin:0;font-size:20px}
.verdict ol{margin:0;padding-left:22px;display:grid;gap:6px}
.figs{display:grid;grid-template-columns:repeat(auto-fit,minmax(190px,1fr));gap:10px}
.fig{background:var(--surface);border:1px solid var(--line);border-radius:6px;padding:14px 16px;display:grid;gap:2px;min-width:0}
.fig .v{font:600 26px/1.2 var(--display);font-variant-numeric:tabular-nums}
.fig .l{font-size:13px;color:var(--ink-2)}
.fig .s{font-size:12px;color:var(--muted)}
.tw{overflow-x:auto;background:var(--surface);border:1px solid var(--line);border-radius:6px}
table{border-collapse:collapse;width:100%;font-size:13px;min-width:560px}
th,td{text-align:left;padding:8px 10px;border-bottom:1px solid var(--line);vertical-align:top}
th{font-weight:600;color:var(--ink-2);background:var(--accent-wash);font-size:12px}
tr:last-child td{border-bottom:0}
td.n{font-family:var(--mono);font-variant-numeric:tabular-nums;white-space:nowrap}
.chip{display:inline-flex;align-items:center;gap:5px;font:500 12px/1 var(--mono);padding:4px 7px;border-radius:999px;white-space:nowrap}
.chip b{font-family:var(--display)}
.chip.ok{background:var(--ok-wash);color:var(--ok)} .chip.warn{background:var(--warn-wash);color:var(--warn)}
.chip.bad{background:var(--bad-wash);color:var(--bad)} .chip.info{background:var(--accent-wash);color:var(--accent)}
.note{font-size:13px;color:var(--ink-2);max-width:72ch}
.callout{background:var(--accent-wash);border-radius:6px;padding:14px 16px;display:grid;gap:6px}
.drawings{display:grid;grid-template-columns:repeat(auto-fit,minmax(280px,1fr));gap:10px}
.drawings svg,.chartbox svg{width:100%;height:auto;display:block}
.drawings figure,.chartbox{margin:0;background:var(--surface);border:1px solid var(--line);border-radius:6px;padding:10px;min-width:0;position:relative}
.m-frame{fill:none;stroke:var(--ink);stroke-width:5;stroke-linejoin:round}
.m-leg{stroke:var(--ink);stroke-width:5;stroke-linecap:round}
.m-rodline{stroke:var(--accent);stroke-width:3}
.m-rod{fill:var(--accent);stroke:var(--surface);stroke-width:2}
.m-foot{fill:var(--muted)}
.m-dim{stroke:var(--muted);stroke-width:1}
.m-brace{stroke:var(--ok);stroke-width:2;stroke-dasharray:6 4}
.m-sway{stroke:var(--bad);stroke-width:1.5;stroke-dasharray:3 3;fill:none}
.m-arrow{stroke:var(--bad);stroke-width:1.5;fill:none}
.m-arrowhead{fill:var(--bad)}
.m-t{font:11px var(--display);fill:var(--ink-2)}
.m-h{font:600 12px var(--display);fill:var(--ink)}
.grid{stroke:var(--line);stroke-width:1}
.tick{font:11px var(--mono);fill:var(--muted)}
.axis{font:12px var(--display);fill:var(--ink-2)}
.zl{font:12px var(--display);fill:var(--ink-2)}
.z-bad{fill:var(--bad-wash)} .z-warn{fill:var(--warn-wash)}
.series{fill:none;stroke:var(--accent);stroke-width:2;stroke-linejoin:round;stroke-linecap:round}
.dot{fill:var(--accent);stroke:var(--surface);stroke-width:2;cursor:pointer}
.dot:hover,.dot:focus{r:6.5;outline:none}
.mark{stroke:var(--ink-2);stroke-width:1}
#tip{position:absolute;pointer-events:none;background:var(--ink);color:var(--surface);font:12px/1.3 var(--mono);padding:6px 8px;border-radius:4px;white-space:nowrap}
ul.plain{margin:0;padding-left:20px;display:grid;gap:4px;max-width:72ch}
code{font-family:var(--mono);font-size:.92em;background:var(--accent-wash);padding:1px 5px;border-radius:3px}
a{color:var(--accent)}
small,.muted{color:var(--muted)}
@media (prefers-reduced-motion:reduce){*{transition:none!important}}
"""

TIP_JS = """
<script>
(function(){var box=document.querySelector('.chartbox');if(!box)return;var tip=document.getElementById('tip');
function show(e){var t=e.target;if(!t.dataset||!t.dataset.tip)return;tip.innerHTML=t.dataset.tip;tip.hidden=false;
var b=box.getBoundingClientRect(),r=t.getBoundingClientRect();var x=r.left-b.left+r.width/2,y=r.top-b.top-8;
tip.style.left=Math.max(4,Math.min(x-tip.offsetWidth/2,b.width-tip.offsetWidth-4))+'px';tip.style.top=(y-tip.offsetHeight)+'px';}
function hide(){tip.hidden=true;}
box.addEventListener('mouseover',show);box.addEventListener('focusin',show);box.addEventListener('mouseout',hide);box.addEventListener('focusout',hide);})();
</script>"""


def body():
    u = cases["U"]["service"]
    return f"""
<main>
<p class="eyebrow">RIBBON / 30 · 2차 구조 검토</p>
<h1>30kg은 버틴다. 다만 접합이 단단해야 한다.</h1>
<p class="lede">1차 보고서(GPT)의 형상과 단면을 그대로 3D 골조로 다시 만들었습니다. 빠져 있던 검토 항목, 즉 3D 비틀림·횡변형, 전체 좌굴, 접합부, 국부좌굴, 미끄러짐, 피로, 응력집중을 계산했습니다. 4인 가정 젖은 빨래 무게의 근거도 찾았습니다.</p>

<section class="verdict" aria-labelledby="v">
  <h2 id="v">판정: 조건부 적합</h2>
  <p>계산한 모든 하중 경우에서 부재 응력은 항복강도의 {max(frame_uls, rod_uls_rigid, rod_uls_pinned) / FY * 100:.0f}% 이하입니다(설계하중 = 1.35×자중 + 1.5×빨래). 30kg 목표는 현실적인 4인 가정 1회 빨래량(약 6~25kg)을 덮습니다. 아래 두 조건이 충족될 때만 이 판정이 성립합니다.</p>
  <ol>
    <li><b>봉–프레임 접합이 휘어지지 않을 만큼 단단해야 합니다.</b> 회전강성이 접합 1곳당 약 {sci(K_ALPHA10)} N·mm/rad 이상이어야 하고(용접이면 충족), 유격이 없어야 합니다. 핀처럼 돌아가는 접합이면 길이방향으로 접히듯 무너지는 <b>메커니즘</b>이 됩니다.</li>
    <li><b>또는 양쪽 끝 다리에 X 가새를 답니다(대안 B).</b> 이렇게 하면 접합이 핀이어도 α<sub>cr</sub> = {braced['alpha_cr']:.0f}로 안정합니다. 무게는 {braced['added_mass_kg']:.2f}kg 늘고, 가새 가운데를 핀으로 하면 가위식으로 접을 수 있습니다.</li>
  </ol>
  <p class="note">실물 시험은 하지 않았습니다. 바닥 마찰, 실제 접합 강성, 용접 품질은 측정이 필요합니다. 마지막 절에 시험 절차를 제안했습니다.</p>
</section>

<div class="figs">
  <div class="fig"><span class="l">최대 응력 이용률 (설계하중)</span><span class="v">{max(frame_uls, rod_uls_rigid, rod_uls_pinned) / FY:.2f}</span><span class="s">봉, 핀접합, 한 봉 5kg 집중</span></div>
  <div class="fig"><span class="l">전체 좌굴 계수 α<sub>cr</sub></span><span class="v">{min_alpha_rigid:.1f}</span><span class="s">강접합 · 기준 ≥ 10</span></div>
  <div class="fig"><span class="l">핀접합 시 길이방향</span><span class="v">메커니즘</span><span class="s">최소 고유값 ≈ 0, 가새 필요</span></div>
  <div class="fig"><span class="l">빈 건조대를 넘기는 힘</span><span class="v">{tip[0]['H_tip_N']:.0f} N</span><span class="s">꼭대기 길이방향 · 약 {tip[0]['H_tip_N'] / G:.1f}kgf</span></div>
</div>

<h2>1. 4인 가정 젖은 빨래는 얼마나 무거운가</h2>
<p>세탁기 용량은 <b>마른 빨래</b> 기준입니다. 탈수 후 남는 물은 EU 에너지 라벨의 탈수 등급(잔류수분율 = 물 질량 ÷ 마른 빨래 질량)으로 범위를 잡았습니다. B등급 상한은 54% 미만, D등급 상한은 72% 미만입니다. 여기서는 53%~72%를 썼습니다.</p>
<div class="tw"><table>
<tr><th>시나리오</th><th>마른 빨래 kg</th><th>젖은 빨래 kg</th><th>30kg 대비</th><th>근거</th><th>신뢰도</th></tr>
{scen_rows()}
</table></div>
<p class="note">국내 세탁기 권장 용량은 공식 통계가 아니라 구매 가이드 수준의 자료입니다. 국내 세탁기의 실제 잔류수분율 측정 자료는 찾지 못했습니다. 통돌이를 18kg까지 꽉 채운 극단적인 경우에만 젖은 빨래가 30kg을 조금 넘을 수 있습니다(최대 약 31kg). 이 경우도 설계하중 계수 1.5로 덮입니다(45kg 상당).</p>

<h2>2. 해석 모델</h2>
<div class="drawings"><figure>{front_svg()}</figure><figure>{side_svg()}</figure></div>
<ul class="plain note">
<li>형상은 1차 보고서 도면 좌표에서 복원했습니다. 발 (0,0)·(1200,0), 다리 꺾임점 (0,180)·(30,750)·(90,1050), 상부는 꼭대기 1,200mm인 포물선입니다. 강재 중량 {R['mass']['total_kg']:.2f}kg으로 1차 보고서의 14.65kg과 일치합니다.</li>
<li>3D 보 요소(절점당 6자유도), 하중 경우 {len(cases)}개. 프레임 RHS 40×20×1(40mm가 프레임 평면 안), 봉 CHS 16×1, E = 200GPa, f<sub>y</sub> = 235MPa.</li>
<li>바닥: 4개 발이 수직으로 받치고 마찰로 수평 고정, 회전 자유. 필요한 마찰계수는 최대 {fric:.2f}입니다. 마찰이 부족해 발이 미끄러져도 변위가 {R['feet_sliding_sensitivity']['frame_disp_mm']:.1f}mm로 커질 뿐 응력은 {R['feet_sliding_sensitivity']['frame_sigma']:.1f}MPa 수준입니다.</li>
<li>봉–프레임 접합은 회전 스프링으로 모델링해 강성을 바꿔 가며 계산했습니다(강접합 = 10<sup>10</sup> N·mm/rad).</li>
<li>엔진 검증: 외팔보, 비틀림, 양단고정보, 단순보, 오일러 좌굴 2종 등 이론해와 비교한 단위시험 10개를 통과했습니다.</li>
</ul>

<h2>3. 1차 보고서 숫자 교차검증</h2>
<div class="tw"><table>
<tr><th>항목</th><th>1차(GPT, 2D)</th><th>이번(3D)</th><th>판단</th></tr>
<tr><td>강재 중량</td><td class=n>14.65 kg</td><td class=n>{R['mass']['total_kg']:.2f} kg</td><td>{chip('ok', '일치')}</td></tr>
<tr><td>30kg 균등, 프레임 변위</td><td class=n>0.257 mm</td><td class=n>{u['frame_disp_mm']:.3f} mm</td><td>{chip('ok', '일치')}</td></tr>
<tr><td>30kg 폭 한쪽, 프레임 변위</td><td class=n>0.329 mm</td><td class=n>{cases['W']['service']['frame_disp_mm']:.3f} mm</td><td>{chip('ok', '일치')}</td></tr>
<tr><td>30kg 균등, 프레임 응력</td><td class=n>10.13 MPa</td><td class=n>{u['frame_sigma']:.2f} MPa</td><td>{chip('warn', '1차가 과소')} 봉 끝 모멘트로 인한 비틀림·약축 휨은 2D에 없습니다</td></tr>
<tr><td>봉 1개 중앙 5kg (단순지지)</td><td class=n>4.014 mm · 76.39 MPa</td><td class=n>{rod_ss['한 봉 5kg']['sag_mm']:.3f} mm · {rod_ss['한 봉 5kg']['sigma']:.2f} MPa</td><td>{chip('ok', '일치')}</td></tr>
<tr><td>빈 건조대 전도 수평력</td><td class=n>59.9 N</td><td class=n>{tip[0]['H_tip_N']:.1f} N</td><td>{chip('ok', '일치')}</td></tr>
<tr><td>길이방향 안정성(래킹)</td><td>검토 안 됨</td><td>접합 강성에 전적으로 의존</td><td>{chip('bad', '새로 발견')}</td></tr>
</table></div>

<h2>4. 30kg 하중 경우별 결과 (강접합)</h2>
<p class="note">사용하중 = 자중 + 빨래 30kg(+수평 15N). 설계하중 = 1.35×자중 + 1.5×(빨래 + 수평력). 응력은 von Mises 기준이며 단위는 MPa입니다.</p>
<div class="tw"><table>
<tr><th>하중 경우</th><th>프레임 변위 mm</th><th>봉 처짐 mm</th><th>프레임 σ (사용)</th><th>봉 σ (사용)</th><th>프레임 (설계)</th><th>봉 (설계)</th><th>접합 M N·m (설계)</th><th>α<sub>cr</sub></th></tr>
{case_rows()}
</table></div>
<p class="note">1차 보고서 기준(변위 4mm, 봉 처짐 5mm, 응력 117.5MPa)을 모든 경우가 만족합니다. 길이방향 수평 15N에서 꼭대기 흔들림은 {cases['HZ']['service']['lateral_mm']['z']:.2f}mm입니다.</p>

<h2>5. 핵심 발견: 길이방향 안정성은 접합이 결정한다</h2>
<p>두 프레임은 바닥에서 한 줄로 늘어선 발 위에 서 있습니다. 그래서 각 프레임은 그 줄을 축으로 앞뒤로 기울 수 있습니다. 둘을 잇는 것은 봉 18개뿐이고, 기울어짐을 막는 힘은 봉 끝 접합의 휨 저항에서만 나옵니다. 모든 하중 경우에서 1차 좌굴 모드가 이 길이방향 래킹입니다.</p>
<div class="chartbox">{alpha_chart()}<div id="tip" hidden></div></div>
<div class="tw"><table>
<tr><th>접합 회전강성 k (N·mm/rad)</th><th>α<sub>cr</sub> (설계하중)</th><th>탄성 좌굴에 이르는 빨래 kg (이론, 결함 없음)</th><th>꼭대기 흔들림 mm / 15N</th><th>봉 처짐 mm (5kg)</th><th>봉 σ MPa (5kg)</th></tr>
{sweep_rows()}
<tr><td>핀(회전 자유)</td><td>{chip('bad', '0 · 메커니즘')}</td><td class=n>빈 상태도 불안정</td><td class=n>∞</td><td class=n>4.02</td><td class=n>76.4</td></tr>
<tr><td>핀 + 측면 X 가새 (대안 B)</td><td>{chip('ok', f"{braced['alpha_cr']:.1f}")}</td><td class=n>{collapse_laundry_kg(braced['alpha_cr']):,.0f}</td><td class=n>{braced['sway_z_per_15N_mm']:.2f}</td><td class=n>{braced['rod_sag_rod5_mm']:.2f}</td><td class=n>{rod_ss['한 봉 5kg']['sigma']:.1f}</td></tr>
</table></div>
<div class="callout">
<p><b>접합 요구조건.</b> 설계하중에서 α<sub>cr</sub> ≥ 10이 되려면 k ≥ 약 {sci(K_ALPHA10)} N·mm/rad가 필요합니다(계산점 사이 로그 보간). 접합 1곳이 1° 돌 때 약 {K_ALPHA10 * math.pi / 180 / 1000:.1f} N·m를 버티는 수준입니다. k가 약 {sci(K_ALPHA1)} 아래로 내려가면 30kg을 걸기 전에 이론적으로 무너집니다.</p>
<p>예를 들어 끼움식 플라스틱 클립처럼 헐거운 접합(k ≈ 10⁴)이면 빨래 약 {collapse_laundry_kg(loose['alpha_cr']):.0f}kg에서 무너지는 것으로 계산됩니다. 실제로는 초기 기울어짐과 유격 때문에 이보다 일찍 무너집니다.</p>
</div>

<h2>6. 남은 항목 검토</h2>
<div class="tw"><table>
<tr><th>항목</th><th>작용</th><th>저항 / 기준</th><th>이용률</th><th>비고</th></tr>
{check_table()}
</table></div>
<ul class="plain note">
<li>두께 1mm 관은 EN 1993-1-8 중공단면 접합식의 적용범위(벽 두께 2.5mm 이상)를 벗어납니다. 접합 저항 13.5N·m는 참고값이며, 접합 모멘트 시험으로 확인해야 합니다.</li>
<li>1mm 벽 용접은 녹아내림과 변형 위험이 있어 TIG·레이저 같은 정밀 용접이나 기계식 접합이 필요합니다. 용접 품질 자체는 계산으로 확인할 수 없습니다.</li>
<li>피로는 하중 반복이 15년간 약 1.1만 회로 적어서 지배하지 않습니다. 응력 범위가 허용치의 절반 이하입니다.</li>
<li>봉 중앙부는 휨이 가장 큰 곳이라 구멍(Kt≈3)을 뚫으면 사용하중에서 국부적으로 항복 가까이(약 229MPa) 갑니다. 구멍은 봉 끝 근처에만 둡니다.</li>
</ul>

<h2>7. 넘어짐과 미끄러짐</h2>
<p>봉이 모두 발 사이(폭 90~1,110mm, 길이 0~1,000mm)에 있습니다. 그래서 빨래나 손으로 누르는 <b>수직</b> 힘으로는 넘어지지 않습니다. 위험한 것은 수평으로 미는 힘입니다.</p>
<div class="tw"><table>
<tr><th>경우 (꼭대기 1.2m에서 수평력)</th><th>넘어짐 N</th><th>미끄러짐 N (μ=0.3)</th><th>미끄러짐 N (μ=0.5)</th><th>μ=0.3에서 먼저</th><th>바람 m/s 넘어짐 / 미끄러짐</th></tr>
{tip_rows()}
</table></div>
<p class="note">강체·접합 변형 무시. 바람은 실외 사용을 가정한 대략값입니다. 젖은 빨래의 바람받이 면적 1m², 힘계수 1.2, 합력 높이 0.9m로 가정했습니다. 빈 건조대는 약 60N(6kgf)의 수평력으로 넘어지므로 아이가 당기거나 매달리는 상황은 위험합니다. 바닥이 미끄러우면(μ≈0.3) 넘어지기 전에 미끄러지고, 고무발처럼 마찰이 크면(μ≈0.5) 빈 건조대는 미끄러지기 전에 넘어집니다.</p>

<h2>8. 얼마까지 버티나</h2>
<ul class="plain">
<li><b>건조대 전체:</b> 설계하중 기준 약 <b>{design_cap_global:,.0f}kg</b>까지 응력·2차 효과 검토를 통과합니다(강접합, 가장 불리한 모서리 편중 배치). 이 값은 계산상 용량이며 정격으로 쓰면 안 됩니다.</li>
<li><b>봉 1개:</b> 중앙 집중하중으로 약 <b>{rod_point_cap:.1f}kg</b>(설계, 핀접합 가정), 처음 항복은 약 {R['rod_simply_supported']['first_yield_point_kg']:.1f}kg입니다. 사용 안내는 봉당 5kg 이하를 권합니다.</li>
<li>실질적인 한계는 재료가 아니라 <b>접합 강성·유격</b>과 <b>넘어짐</b>입니다.</li>
</ul>

<h2>9. 접이식으로 만든다면</h2>
<p>1차 보고서의 형상은 고정식(연속 강접합)입니다. 접이 구조 도면이 없으므로 특정 경첩이나 잠금장치를 검증할 수는 없습니다. 대신 어떤 접이 구조든 만족해야 할 조건을 이 해석에서 뽑았습니다.</p>
<ul class="plain">
<li>봉을 접는 구조(봉 끝이 돌아감): 봉 끝 접합이 핀이 되므로 <b>측면 X 가새가 필수</b>입니다. 가새 가운데를 핀으로 하면 가위처럼 접힙니다. 펼친 상태 잠금은 가새 길이를 고정하는 방식(스톱 또는 잠금 핀)으로 합니다.</li>
<li>가새 없이 접합 잠금만으로 버티려면: 잠금 상태 회전강성 ≥ {sci(K_ALPHA10)} N·mm/rad, 모멘트 저항 ≥ {joint_uls / 1000:.1f} N·m(설계)가 필요하고 유격이 거의 없어야 합니다.</li>
<li>가새 부재력은 설계하중에서 {braced['uls_brace_max_N']:.0f}N 정도로 작습니다. 이 값은 16×1 관 가새로 계산한 것입니다. 인장만 받는 와이어로 바꾸면 다시 계산해야 합니다.</li>
</ul>

<h2>10. 계산으로 확인할 수 없어 시험이 필요한 것</h2>
<ul class="plain">
<li><b>접합 회전강성 시험:</b> 프레임 조각에 봉을 붙이고 끝에 하중을 걸어 모멘트–회전을 측정합니다. k ≥ {sci(K_ALPHA10)} N·mm/rad와 유격 여부를 확인합니다.</li>
<li><b>정적 하중 시험(제안):</b> 45kg(30kg × 1.5)을 균등·모서리 편중으로 걸어 둔 뒤, 하중을 뺐을 때 영구 변형이 없는지 봅니다. 봉 1개에는 중앙 10kg을 겁니다.</li>
<li><b>흔들림 시험:</b> 30kg을 건 상태에서 꼭대기를 길이방향으로 15N 밀었을 때 흔들림이 4mm 이하인지 봅니다(강접합 계산값 {cases['HZ']['service']['lateral_mm']['z']:.1f}mm).</li>
<li><b>안정성 시험:</b> 실제 바닥(타일·마루)에서 넘어짐/미끄러짐 시작 힘을 재서 위 표와 비교합니다.</li>
<li>이 시험 절차는 제 제안입니다. 건조대에 적용되는 공인 시험 규격은 확인하지 못했습니다.</li>
</ul>

<h2>가정과 한계</h2>
<ul class="plain note">
<li>선형 탄성 1차 해석과 선형 좌굴 해석입니다. 큰 하중에서의 용량은 1/(1−1/α) 증폭으로 2차 효과를 근사했습니다.</li>
<li>모서리가 각진 단면 성질을 썼습니다(실제 둥근 모서리보다 단면이 약간 큼). 접합부·잠금부·고무발 질량은 제외했습니다.</li>
<li>하중계수 1.35/1.5는 EN 1990 건축 구조용 값을 설계 가정으로 빌려 쓴 것입니다. 가정용품 인증 기준이 아닙니다.</li>
<li>빨래는 봉 길이를 따라 고르게 분포한다고 보았고, 봉 하나 경우만 중앙 집중으로 계산했습니다.</li>
</ul>

<h2>재현 방법과 출처</h2>
<p class="note"><code>ribbon30_drying_rack/</code> 폴더에서 <code>python3 -m unittest test_fem3d</code>(엔진 검증) → <code>python3 rack_model.py</code>(results.json 생성) → <code>python3 build_report.py</code>(이 보고서)를 차례로 실행합니다. numpy·scipy가 필요합니다.</p>
<ul class="plain note">
<li><a href="https://en.wikipedia.org/wiki/European_Union_energy_label">EU 에너지 라벨: 세탁기 탈수 효율 등급(잔류수분율 구간)</a> · 2차 자료이므로 원 규정(EU 1061/2010) 확인을 권합니다.</li>
<li><a href="https://www.eea.europa.eu/en/circularity/sectoral-modules/product-lifespans/evolution-in-the-average-number-of-washing-cycles-per-washing-machine-in-eu-intensity-of-use">EEA: EU 세탁기 1회 평균 세탁량 3.1kg(1995) → 4kg(2020)</a> · 검색 요약으로 확인했고 원문 페이지는 접속이 막혀 열지 못했습니다.</li>
<li><a href="https://www.consumer.org.nz/articles/what-size-washing-machine-do-you-really-need">Consumer NZ: 가정 세탁 1회 평균 약 3.4kg</a> · 검색 요약으로 확인.</li>
<li><a href="https://www.bosch-home.com/qa/en/products/washers-dryers/washing-machines/buying-guide">Bosch 구매 안내: 3~4인 가정 8~9kg</a> · 1차 보고서 인용.</li>
<li><a href="https://choicemon.com/washing-machine-capacity/">국내 세탁기 용량 가이드(4인: 통돌이 15~18kg, 드럼 19~21kg)</a> · 비공식 자료.</li>
<li>강구조 판단 기준: EN 1993-1-1(단면 등급, 좌굴), EN 1993-1-8 표 7.14(중공단면 접합, 참고), EN 1993-1-9(피로 상세등급). 조항 번호와 계수는 기억에 의존한 부분이 있으니 원문으로 확인하십시오.</li>
</ul>
<p class="note"><small>예비 구조 검토이며 제품 인증이 아닙니다. 계산: 3D 보 FEM, {len(R['joint_sweep'])}개 접합 강성 조건, {len(cases)}개 하중 경우.</small></p>
</main>
"""


def head():
    return ('<title>RIBBON/30 안전성 검토</title>'
            '<link rel="preconnect" href="https://fonts.googleapis.com">'
            '<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>'
            '<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500&family=IBM+Plex+Sans+KR:wght@400;500;600;700&display=swap">'
            f"<style>{CSS}</style>")


if __name__ == "__main__":
    full = ('<!doctype html><html lang="ko"><head><meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width,initial-scale=1">'
            f"{head()}</head><body>{body()}{TIP_JS}</body></html>")
    (HERE / "report.html").write_text(full, encoding="utf-8")
    if "--fragment" in sys.argv:
        out = Path(sys.argv[sys.argv.index("--fragment") + 1])
        out.write_text(head() + body() + TIP_JS, encoding="utf-8")
    print("report.html written")
