"""TAB 7 — DIAGRAM COMPOSER: 다이어그램 편집·미리보기."""
import sys
from pathlib import Path
ROOT = Path(__file__).parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import io
import math
import streamlit as st
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from core.models import RouteType, DiagramSettings
from core.ramp_analysis import calculate_circular_ramp_metrics, build_circular_ramp_centerline
from core.stair_analysis import calculate_stair_metrics
from core.diagram_renderer import render_diagram, get_common_panel_extent, setup_korean_font
from shapely.geometry import LineString, Point

EXPORTS = ROOT / "exports"
EXPORTS.mkdir(exist_ok=True)

st.set_page_config(page_title="Diagram — STA", layout="wide")
st.title("🎨 07. DIAGRAM COMPOSER")

if not st.session_state.get("project"):
    st.warning("01 PROJECT에서 프로젝트를 여세요.")
    st.stop()

proj = st.session_state.project
if not proj.routes:
    st.warning("04 ROUTES & SPACES에서 경로를 입력하세요.")
    st.stop()

ds = proj.diagram_settings

# ── 다이어그램 설정 ───────────────────────────────────────────
with st.expander("다이어그램 설정", expanded=True):
    col1, col2 = st.columns(2)
    with col1:
        ds.title_en = st.text_input("영문 제목", value=ds.title_en or proj.title_en)
        ds.title_ko = st.text_input("한글 제목", value=ds.title_ko or proj.title_ko)
        ds.design_question = st.text_area("설계 질문", value=ds.design_question or proj.design_question, height=80)
        template = st.selectbox("다이어그램 템플릿",
                                ["sequence_focus", "equal_panels", "vertical_section", "minimal_academic"],
                                index=["sequence_focus", "equal_panels", "vertical_section", "minimal_academic"].index(ds.template))
        ds.template = template
    with col2:
        ds.stair_color = st.color_picker("계단 색상", value=ds.stair_color or "#2980B9")
        ds.ramp_color = st.color_picker("램프 색상", value=ds.ramp_color or "#C0392B")
        ds.court_color = st.color_picker("중정 색상", value=ds.court_color or "#17BECF")
        ds.show_annotations = st.checkbox("수치 주석 표시", value=ds.show_annotations)
        ds.show_section = st.checkbox("수직 분석 단면 표시", value=ds.show_section)
        ds.show_critical_reading = st.checkbox("Critical Reading 표시", value=ds.show_critical_reading)
        ds.show_method_limit = st.checkbox("Methodological Limit 표시", value=ds.show_method_limit)
    col3, col4 = st.columns(2)
    with col3:
        same_size = st.checkbox("모든 패널 크기 동일", value=(ds.panel_size_mode == "equal"))
        ds.panel_size_mode = "equal" if same_size else "auto"
    with col4:
        same_scale = st.checkbox("모든 패널 축척 동일", value=(ds.panel_scale_mode == "equal"))
        ds.panel_scale_mode = "equal" if same_scale else "auto"

st.markdown("---")

# ── 경로 데이터 수집 ──────────────────────────────────────────
def build_routes_data():
    """각 경로의 분석 데이터를 render_diagram 포맷으로 변환."""
    rd_list = []
    geo_data = {g["경로 ID"]: g for g in st.session_state.analysis_results.get("geometry", [])}
    for r in proj.routes:
        is_ramp = r.route_type == RouteType.RAMP
        center = Point(*r.circular_center) if r.circular_center else Point(0, 0)
        cl = build_circular_ramp_centerline(center, r.circular_radius_m,
                                             r.circular_start_angle_deg, r.direction,
                                             r.circular_rotation_deg)
        pts = list(cl.coords)
        floor_map = {f.level_id: f for f in proj.floors}
        lvl = r.destination_level if is_ramp else r.source_level
        floor = floor_map.get(lvl)
        cx = float(r.circular_center[0]) if r.circular_center else 0.0
        cy = float(r.circular_center[1]) if r.circular_center else 0.0
        # 기하 메트릭
        geo = geo_data.get(r.route_id, {})
        plan_m = float(geo.get("평면 길이(m)", 0)) or (r.circular_radius_m * math.radians(r.circular_rotation_deg))
        rise_m = r.rise_m
        dist3d = float(geo.get("3D 이동거리(m)", 0)) or math.hypot(plan_m, rise_m)
        slope = float(str(geo.get("경사(%)", 0)).replace("%", ""))
        rot = r.circular_rotation_deg
        ann = (f"이동 {dist3d:.1f}m · 회전 {rot:.0f}° · 상승 {rise_m:.1f}m\n"
               f"경사 {slope:.1f}% (1:{plan_m/rise_m:.1f})" if rise_m else "")
        # Isovist
        iso_key = f"iso_{r.route_id}"
        iso_raw = st.session_state.analysis_results.get(iso_key, {})
        from core.models import IsovistResult
        iso_results = []
        for rd2 in iso_raw.get("results", []):
            res = IsovistResult(**{k: rd2[k] for k in rd2 if k in IsovistResult.__dataclass_fields__})
            iso_results.append(res)
        ev = iso_raw.get("events", {})
        # 장애물 (DXF 없으면 빈 목록)
        obstacles = []
        if st.session_state.get("dxf_entities") and floor:
            from core.dxf_loader import entity_to_linestring, filter_by_x_range
            from core.geometry_classifier import auto_classify_all, GeometryClass, remove_lines_inside_void
            ents = filter_by_x_range(st.session_state.dxf_entities, floor.xmin, floor.xmax, proj.dxf_unit_scale)
            layer_rules = {l: k for k, v in proj.layer_classification.items() for l in (v or [])}
            for e, cls in auto_classify_all(ents, layer_rules):
                if cls == GeometryClass.OPAQUE:
                    ls = entity_to_linestring(e, proj.dxf_unit_scale)
                    if ls and not ls.is_empty:
                        obstacles.append(ls)
            if floor.courtyard_center:
                cp = Point(*floor.courtyard_center)
                obstacles, _ = remove_lines_inside_void(obstacles, cp, floor.courtyard_radius_m)
        rd_list.append({
            "route_id": r.route_id, "is_ramp": is_ramp,
            "centerline_pts": pts,
            "court_center": (cx, cy),
            "court_radius": float(floor.courtyard_radius_m if floor else 4.0),
            "plan_m": plan_m, "rise_m": rise_m, "dist_3d_m": dist3d,
            "slope_percent": slope, "rotation_deg": rot,
            "annotation": ann,
            "obstacles": obstacles[:3000],
            "iso_results": iso_results,
            "visibility_events": ev,
        })
    return rd_list

# ── 미리보기 ─────────────────────────────────────────────────
if st.button("🖼 다이어그램 미리보기 생성", type="primary"):
    with st.spinner("렌더링 중..."):
        try:
            routes_data = build_routes_data()
            out_png = str(EXPORTS / "preview_diagram.png")
            out_pdf = str(EXPORTS / "preview_diagram.pdf")
            ok, msg = render_diagram(routes_data, proj, out_png, out_pdf)
            if ok:
                st.image(out_png, use_container_width=True)
                st.success("다이어그램 생성 완료")
            else:
                st.error(f"렌더링 오류: {msg}")
        except Exception as e:
            st.error(f"예외 발생: {e}")
            import traceback
            st.code(traceback.format_exc())

# ── 검증 ────────────────────────────────────────────────────
st.markdown("---")
st.subheader("다이어그램 검증")
if st.button("패널 동일 축척 검증"):
    if ds.panel_size_mode == "equal" and ds.panel_scale_mode == "equal":
        st.success("✅ 동일 크기·동일 축척 모드 활성화. render_diagram이 공통 extent를 적용합니다.")
    else:
        st.warning("동일 축척 미적용. 위 설정에서 '모든 패널 축척 동일'을 체크하세요.")
