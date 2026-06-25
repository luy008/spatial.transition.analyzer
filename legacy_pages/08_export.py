"""TAB 8 — EXPORT: SVG · PDF · PNG · CSV · JSON · ZIP."""
import sys
from pathlib import Path
ROOT = Path(__file__).parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import io
import json
import zipfile
import streamlit as st
import pandas as pd
from core.project_store import save_project
from core.diagram_renderer import render_diagram

EXPORTS = ROOT / "exports"
EXPORTS.mkdir(exist_ok=True)

st.set_page_config(page_title="Export — STA", layout="wide")
st.title("💾 08. EXPORT")

if not st.session_state.get("project"):
    st.warning("01 PROJECT에서 프로젝트를 여세요.")
    st.stop()

proj = st.session_state.project

# ── 다이어그램 출력 ───────────────────────────────────────────
st.subheader("다이어그램 생성 및 다운로드")
col1, col2, col3 = st.columns(3)

def _build_routes_data():
    import math
    from core.models import RouteType, IsovistResult
    from core.ramp_analysis import build_circular_ramp_centerline
    from shapely.geometry import Point
    rd_list = []
    geo_data = {g["경로 ID"]: g for g in st.session_state.analysis_results.get("geometry", [])}
    for r in proj.routes:
        is_ramp = r.route_type == RouteType.RAMP
        center = Point(*r.circular_center) if r.circular_center else Point(0, 0)
        cl = build_circular_ramp_centerline(center, r.circular_radius_m,
                                             r.circular_start_angle_deg, r.direction,
                                             r.circular_rotation_deg)
        pts = list(cl.coords)
        cx = float(r.circular_center[0]) if r.circular_center else 0.0
        cy = float(r.circular_center[1]) if r.circular_center else 0.0
        floor_map = {f.level_id: f for f in proj.floors}
        lvl = r.destination_level if is_ramp else r.source_level
        floor = floor_map.get(lvl)
        geo = geo_data.get(r.route_id, {})
        plan_m = float(geo.get("평면 길이(m)", 0)) or r.circular_radius_m * math.radians(r.circular_rotation_deg)
        rise_m = r.rise_m
        dist3d = float(geo.get("3D 이동거리(m)", 0)) or math.hypot(plan_m, rise_m)
        slope = float(str(geo.get("경사(%)", 0)))
        iso_raw = st.session_state.analysis_results.get(f"iso_{r.route_id}", {})
        iso_results = []
        for rd2 in iso_raw.get("results", []):
            res = IsovistResult(**{k: rd2[k] for k in rd2 if k in IsovistResult.__dataclass_fields__})
            iso_results.append(res)
        rd_list.append({
            "route_id": r.route_id, "is_ramp": is_ramp,
            "centerline_pts": pts,
            "court_center": (cx, cy),
            "court_radius": float(floor.courtyard_radius_m if floor else 4.0),
            "plan_m": plan_m, "rise_m": rise_m, "dist_3d_m": dist3d,
            "slope_percent": slope, "rotation_deg": r.circular_rotation_deg,
            "annotation": f"이동 {dist3d:.1f}m · 회전 {r.circular_rotation_deg:.0f}° · 상승 {rise_m:.1f}m\n경사 {slope:.1f}%",
            "obstacles": [],
            "iso_results": iso_results,
            "visibility_events": iso_raw.get("events", {}),
        })
    return rd_list

with col1:
    if st.button("📄 A3 PDF + PNG 생성", type="primary"):
        with st.spinner("렌더링 중..."):
            try:
                routes_data = _build_routes_data()
                out_png = str(EXPORTS / f"{proj.project_name}_A3.png")
                out_pdf = str(EXPORTS / f"{proj.project_name}_A3.pdf")
                out_svg = str(EXPORTS / f"{proj.project_name}_A3.svg")
                ok, msg = render_diagram(routes_data, proj, out_png, out_pdf, out_svg)
                if ok:
                    st.success(f"생성 완료")
                    with open(out_pdf, "rb") as f:
                        st.download_button("⬇ PDF 다운로드", data=f.read(),
                                           file_name=Path(out_pdf).name, mime="application/pdf")
                    with open(out_png, "rb") as f:
                        st.download_button("⬇ PNG 다운로드", data=f.read(),
                                           file_name=Path(out_png).name, mime="image/png")
                    if Path(out_svg).exists():
                        with open(out_svg, "rb") as f:
                            st.download_button("⬇ SVG 다운로드", data=f.read(),
                                               file_name=Path(out_svg).name, mime="image/svg+xml")
                else:
                    st.error(f"생성 실패: {msg}")
            except Exception as e:
                st.error(str(e))

with col2:
    st.write("**분석 CSV 다운로드**")
    geo_data = st.session_state.analysis_results.get("geometry", [])
    if geo_data:
        df = pd.DataFrame(geo_data)
        csv = df.to_csv(index=False, encoding="utf-8-sig")
        st.download_button("⬇ 기하 분석 CSV", data=csv,
                           file_name="route_geometry.csv", mime="text/csv")
    # Isovist CSV 합치기
    all_iso = []
    for r in proj.routes:
        iso_raw = st.session_state.analysis_results.get(f"iso_{r.route_id}", {})
        for res in iso_raw.get("results", []):
            row = {"route_id": r.route_id}
            row.update(res)
            all_iso.append(row)
    if all_iso:
        df_iso = pd.DataFrame(all_iso)
        csv_iso = df_iso.to_csv(index=False, encoding="utf-8-sig")
        st.download_button("⬇ Isovist CSV", data=csv_iso,
                           file_name="isovist_results.csv", mime="text/csv")

with col3:
    if st.button("💾 프로젝트 JSON 저장"):
        path = save_project(proj)
        st.success(f"저장: {path}")
        with open(path, encoding="utf-8") as f:
            data = f.read()
        st.download_button("⬇ 프로젝트 JSON", data=data,
                           file_name=f"{proj.project_name}.json", mime="application/json")

# ── ZIP 패키지 ────────────────────────────────────────────────
st.markdown("---")
st.subheader("ZIP 프로젝트 패키지")
if st.button("📦 ZIP 패키지 만들기"):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        # 프로젝트 JSON
        proj_json = json.dumps(proj.to_dict(), ensure_ascii=False, indent=2)
        zf.writestr(f"{proj.project_name}/project.json", proj_json)
        # 분석 결과
        if st.session_state.analysis_results:
            zf.writestr(f"{proj.project_name}/analysis_results.json",
                        json.dumps(st.session_state.analysis_results, ensure_ascii=False, indent=2,
                                   default=str))
        # 생성된 파일
        for fpath in EXPORTS.glob("*.png"):
            zf.write(fpath, f"{proj.project_name}/{fpath.name}")
        for fpath in EXPORTS.glob("*.pdf"):
            zf.write(fpath, f"{proj.project_name}/{fpath.name}")
        for fpath in EXPORTS.glob("*.svg"):
            zf.write(fpath, f"{proj.project_name}/{fpath.name}")
        # README
        readme = (f"# {proj.project_name}\n\n"
                  f"**{proj.title_en}**\n\n"
                  f"{proj.design_question}\n\n"
                  f"## 재현 방법\n"
                  f"1. `streamlit run app.py` 실행\n"
                  f"2. 01 PROJECT에서 `project.json` 열기\n"
                  f"3. 05 ANALYSIS에서 재분석 실행\n")
        zf.writestr(f"{proj.project_name}/README.md", readme)
    buf.seek(0)
    st.download_button("⬇ ZIP 다운로드",
                       data=buf.getvalue(),
                       file_name=f"{proj.project_name}.zip",
                       mime="application/zip")

# ── Markdown 해설 초안 ────────────────────────────────────────
st.markdown("---")
st.subheader("비판적 해설 Markdown")
if proj.routes:
    import math as _math
    ramp_routes = [r for r in proj.routes if r.route_type == RouteType.RAMP]
    stair_routes = [r for r in proj.routes if r.route_type != RouteType.RAMP]
    geo_data = {g["경로 ID"]: g for g in st.session_state.analysis_results.get("geometry", [])}
    md_lines = [f"# {proj.title_en}\n", f"## {proj.title_ko}\n",
                f"\n> {proj.design_question}\n"]
    md_lines.append("\n## 동선 기하 분석\n")
    for r in proj.routes:
        g = geo_data.get(r.route_id, {})
        md_lines.append(f"- **{r.route_id}** ({r.route_type.value}): "
                        f"3D {g.get('3D 이동거리(m)', '—')}m · "
                        f"경사 {g.get('경사(%)', '—')}% · "
                        f"상승 {r.rise_m}m\n")
    md_lines.append("\n## Isovist 분석\n")
    for r in proj.routes:
        iso = st.session_state.analysis_results.get(f"iso_{r.route_id}", {})
        ev = iso.get("events", {})
        court = ev.get("courtyard_visibility_duration_percent")
        nxt = ev.get("next_space_first_visible_percent")
        md_lines.append(f"- **{r.route_id}**: 중정 가시 {court:.0f}%"
                        f", 다음공간 최초인지 {nxt:.0f}%\n"
                        if (court is not None and nxt is not None) else
                        f"- **{r.route_id}**: Isovist 미실행\n")
    md_content = "".join(md_lines)
    st.text_area("해설 초안", value=md_content, height=300)
    st.download_button("⬇ Markdown 다운로드", data=md_content,
                       file_name="critical_commentary.md", mime="text/markdown")

from core.models import RouteType
