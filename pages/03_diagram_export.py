"""03 다이어그램 및 내보내기 — A3 다이어그램 생성 + SVG/PDF/PNG/ZIP 내보내기."""
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import io
import json
import zipfile
import datetime
import streamlit as st

# ── 가드 ──────────────────────────────────────────────────────
if not st.session_state.get("analysis_complete"):
    st.warning("먼저 02 검증 및 분석 페이지에서 분석을 완료하세요.")
    if st.button("← 02 검증 및 분석으로 이동"):
        st.switch_page("pages/02_verify_analyze.py")
    st.stop()

project_data = st.session_state.project_data
results = st.session_state.analysis_results

st.title("03 다이어그램 및 내보내기")
st.markdown(f"**{project_data.get('project_name', '')}**")
st.markdown("---")

EXPORTS = ROOT / "exports"
EXPORTS.mkdir(exist_ok=True)

ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
OUT_PNG = str(EXPORTS / "diagram.png")
OUT_PDF = str(EXPORTS / "diagram.pdf")
OUT_SVG = str(EXPORTS / "diagram.svg")


# ══════════════════════════════════════════════════════════════
# 다이어그램 렌더링 함수
# ══════════════════════════════════════════════════════════════

def _build_routes_data(project_data: dict, results: dict) -> list:
    """render_diagram용 routes_data 조립."""
    routes = project_data.get("routes", {})
    levels = project_data.get("levels", {})
    mc_map = results.get("movement_cost", {})
    dr_map = results.get("directional", {})
    iso_R1 = results.get("iso_R1", {})
    obstacles_R1 = results.get("obstacles_R1", [])

    route_order = ["S1", "S2", "S3", "R1"]
    routes_data = []

    for rid in route_order:
        rdata = routes.get(rid)
        if not rdata:
            continue

        circ_type = rdata.get("circulation_type", "stair")
        cp = rdata.get("control_points", [])
        rise = float(rdata.get("rise_m", 3.0))

        # 중정 중심: 해당 층 level에서
        src_lv = rdata.get("source_level", "L01")
        lv_info = levels.get(src_lv, {})
        court_center = tuple(lv_info.get("courtyard_center", [0.0, 0.0]))
        court_radius = float(lv_info.get("courtyard_radius_m", 4.0))

        mc = mc_map.get(rid)
        plan_m = mc.plan_distance_m if mc else (len(cp) * 0.5)
        dist_3d_m = mc.dist_3d_m if mc else rise
        slope_pct = mc.slope_percent if mc else 0.0

        dr = dr_map.get(rid, {})
        rot_deg = dr.get("cumulative_rotation_deg", 360.0 if circ_type == "ramp" else 90.0)

        iso_res = []
        vis_events = {}
        obstacles = []
        if rid == "R1":
            iso_res = iso_R1.get("results", [])
            vis_events = iso_R1.get("events", {})
            obstacles = obstacles_R1

        rm = results.get("ramp_metrics")
        if rid == "R1" and rm:
            annotation = rm.annotation()
        elif mc:
            slope_ratio_str = f"1:{mc.slope_ratio:.0f}" if mc.slope_ratio > 0 else ""
            annotation = (
                f"이동 {dist_3d_m:.1f}m · 상승 {rise:.1f}m\n"
                f"경사 {slope_pct:.1f}% {slope_ratio_str}"
            )
        else:
            annotation = ""

        routes_data.append({
            "route_id": rid,
            "centerline_pts": [tuple(p) for p in cp],
            "court_center": court_center,
            "court_radius": court_radius,
            "is_ramp": circ_type == "ramp",
            "obstacles": obstacles,
            "iso_results": iso_res,
            "plan_m": plan_m,
            "rise_m": rise,
            "dist_3d_m": dist_3d_m,
            "rotation_deg": rot_deg,
            "slope_percent": slope_pct,
            "visibility_events": vis_events,
            "annotation": annotation,
        })

    return routes_data


def _build_project_obj(project_data: dict):
    """render_diagram용 ProjectData 객체 생성."""
    from core.models import ProjectData, DiagramSettings
    p = ProjectData(
        project_name=project_data.get("project_name", ""),
        title_en=project_data.get("title_en", ""),
        title_ko=project_data.get("title_ko", ""),
        design_question=project_data.get("design_question", ""),
    )
    p.diagram_settings = DiagramSettings(
        title_en=p.title_en,
        title_ko=p.title_ko,
        design_question=p.design_question,
        show_annotations=True,
        show_section=True,
        show_critical_reading=True,
        show_method_limit=True,
    )
    return p


# ── 다이어그램 생성 버튼 ───────────────────────────────────────
diagram_generated = st.session_state.get("diagram_paths", {}).get("png") is not None
if Path(OUT_PNG).exists():
    diagram_generated = True

if not diagram_generated:
    if st.button("A3 다이어그램 생성", type="primary", use_container_width=True):
        with st.spinner("A3 다이어그램 렌더링 중..."):
            from core.architectural_diagram_renderer import render_architectural_diagram
            ok, msg = render_architectural_diagram(
                project_data, results, OUT_PNG, OUT_PDF, OUT_SVG
            )
        if ok or Path(OUT_PNG).exists():
            st.session_state.diagram_paths = {
                "png": OUT_PNG, "pdf": OUT_PDF, "svg": OUT_SVG
            }
            st.success("다이어그램 생성 완료")
            st.rerun()
        else:
            st.error(f"다이어그램 생성 실패: {msg}")
else:
    # ── 다이어그램 미리보기 ────────────────────────────────────
    st.subheader("A3 다이어그램 미리보기")
    png_path = Path(OUT_PNG)
    if png_path.exists():
        st.image(str(png_path), use_container_width=True)
    else:
        st.warning("PNG 파일을 찾을 수 없습니다.")

    # ── 다운로드 버튼 ─────────────────────────────────────────
    st.markdown("---")
    st.subheader("다운로드")
    col1, col2, col3 = st.columns(3)

    with col1:
        if Path(OUT_PNG).exists():
            with open(OUT_PNG, "rb") as f:
                st.download_button(
                    "PNG 다운로드",
                    data=f,
                    file_name=f"spatial_transition_diagram_{ts}.png",
                    mime="image/png",
                    use_container_width=True,
                )
    with col2:
        if Path(OUT_PDF).exists():
            with open(OUT_PDF, "rb") as f:
                st.download_button(
                    "PDF 다운로드",
                    data=f,
                    file_name=f"spatial_transition_diagram_{ts}.pdf",
                    mime="application/pdf",
                    use_container_width=True,
                )
    with col3:
        if Path(OUT_SVG).exists():
            with open(OUT_SVG, "rb") as f:
                st.download_button(
                    "SVG 다운로드",
                    data=f,
                    file_name=f"spatial_transition_diagram_{ts}.svg",
                    mime="image/svg+xml",
                    use_container_width=True,
                )

    # ── JSON 내보내기 ─────────────────────────────────────────
    st.markdown("---")
    st.subheader("분석 데이터 내보내기")

    col_a, col_b = st.columns(2)

    with col_a:
        # evidence_register.json
        findings = results.get("findings", [])
        ev_register = []
        for f in findings:
            for ev in f.evidence:
                ev_register.append({
                    "finding_id": f.finding_id,
                    "metric_name": ev.metric_name,
                    "value": ev.value,
                    "unit": ev.unit,
                    "route_id": ev.route_id,
                    "sample_id": ev.sample_id,
                    "progress_percent": ev.progress_percent,
                    "geometry_ids": ev.geometry_ids,
                })
        ev_json = json.dumps(ev_register, ensure_ascii=False, indent=2)
        st.download_button(
            "evidence_register.json 다운로드",
            data=ev_json.encode("utf-8"),
            file_name="evidence_register.json",
            mime="application/json",
            use_container_width=True,
        )

    with col_b:
        # critical_findings.json
        cf_list = []
        for f in findings:
            cf_list.append({
                "finding_id": f.finding_id,
                "title": f.title,
                "observed_result": f.observed_result,
                "related_geometry": f.related_geometry,
                "methodological_reduction": f.methodological_reduction,
                "interpretive_risk": f.interpretive_risk,
                "design_implication": f.design_implication,
                "confidence": f.confidence,
                "evidence_count": len(f.evidence),
            })
        cf_json = json.dumps(cf_list, ensure_ascii=False, indent=2)
        st.download_button(
            "critical_findings.json 다운로드",
            data=cf_json.encode("utf-8"),
            file_name="critical_findings.json",
            mime="application/json",
            use_container_width=True,
        )

    # ── ZIP 패키지 ───────────────────────────────────────────
    st.markdown("---")
    st.subheader("분석 코드 패키지 (ZIP)")

    method_limits = [
        {
            "id": "ML-01",
            "type": "courtyard_visibility_overestimate",
            "description": "2D Isovist는 중정 커튼월을 완전 투명한 경계로 처리하므로 "
                           "중정 가시성을 실제보다 과대평가할 수 있다.",
        },
        {
            "id": "ML-02",
            "type": "binary_visibility_limit",
            "description": "가시성을 0.05m² 이상/미만으로 이진 분류하며, "
                           "가시 강도(partial/glimpse)를 구분하지 않는다.",
        },
        {
            "id": "ML-03",
            "type": "destination_space_delay",
            "description": "다음 공간(최상부 전시실) 경계가 point buffer로 근사되어 "
                           "실제 개구부 위치와 오차가 있을 수 있다.",
        },
        {
            "id": "ML-04",
            "type": "stair_ramp_comparison_confound",
            "description": "계단과 램프의 이동속도를 각각 0.5m/s, 0.8m/s로 고정하며 "
                           "관람자 나이·피로·혼잡을 반영하지 않는다.",
        },
        {
            "id": "ML-05",
            "type": "travel_time_fatigue",
            "description": "2D 평면의 누적 회전각은 이동 방향의 수평 변화만 포착하며 "
                           "3m 상승에 따른 수직 방향 변화와 신체 피로는 포함하지 않는다.",
        },
    ]

    def _build_zip() -> bytes:
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
            # PNG
            if Path(OUT_PNG).exists():
                zf.write(OUT_PNG, "diagram.png")
            if Path(OUT_PDF).exists():
                zf.write(OUT_PDF, "diagram.pdf")
            if Path(OUT_SVG).exists():
                zf.write(OUT_SVG, "diagram.svg")
            # JSON 파일들
            zf.writestr("evidence_register.json", ev_json)
            zf.writestr("critical_findings.json", cf_json)
            zf.writestr(
                "methodological_limits.json",
                json.dumps(method_limits, ensure_ascii=False, indent=2),
            )
            # 이동 비용 분석 결과
            mc_export = {}
            for rid, mc in results.get("movement_cost", {}).items():
                mc_export[rid] = {
                    "plan_distance_m": mc.plan_distance_m,
                    "dist_3d_m": mc.dist_3d_m,
                    "rise_m": mc.rise_m,
                    "slope_percent": mc.slope_percent,
                    "slope_ratio": mc.slope_ratio,
                    "slope_angle_deg": mc.slope_angle_deg,
                    "est_time_s": mc.est_time_s,
                    "speed_mps": mc.speed_mps,
                }
            # 방향 전환 결과
            dr_export = results.get("directional", {})
            # Isovist 이벤트
            iso_events = results.get("iso_R1", {}).get("events", {})
            analysis_export = {
                "movement_cost": mc_export,
                "directional": dr_export,
                "isovist_events_R1": iso_events,
                "quality_warnings": results.get("quality_warnings", []),
            }
            zf.writestr(
                "analysis_results.json",
                json.dumps(analysis_export, ensure_ascii=False, indent=2),
            )
            # README
            readme = (
                f"# Spatial Transition Analysis Package\n"
                f"## {project_data.get('project_name', '')}\n\n"
                f"생성일시: {datetime.datetime.now().isoformat()}\n\n"
                f"### 파일 목록\n"
                f"- diagram.png/pdf/svg : A3 다이어그램\n"
                f"- evidence_register.json : 근거 등록부\n"
                f"- critical_findings.json : 비판적 발견 목록\n"
                f"- methodological_limits.json : 방법론 한계 5항목\n"
                f"- analysis_results.json : 전체 분석 수치\n\n"
                f"### 방법론 요약\n"
                f"AI API 없음 · 인터넷 연결 불필요 · 모든 계산 로컬 수행\n"
            )
            zf.writestr("README.md", readme)
        buf.seek(0)
        return buf.getvalue()

    zip_bytes = _build_zip()
    st.download_button(
        "analysis_code_package.zip 다운로드",
        data=zip_bytes,
        file_name=f"analysis_code_package_{ts}.zip",
        mime="application/zip",
        use_container_width=True,
    )

    # ── CriticalFinding 요약 ──────────────────────────────────
    st.markdown("---")
    st.subheader("CriticalFinding 요약")
    for f in findings:
        color = "#C0392B" if f.confidence == "high" else "#F39C12"
        st.markdown(
            f"**{f.finding_id}** · {f.title} &nbsp; "
            f"<span style='color:{color}'>신뢰도: {f.confidence}</span>",
            unsafe_allow_html=True,
        )
        st.caption(f.observed_result[:200])

    # ── 방법론 한계 ──────────────────────────────────────────
    st.markdown("---")
    st.subheader("방법론적 한계 (5항목)")
    for ml in method_limits:
        st.markdown(f"**{ml['id']}** — {ml['description']}")

    # ── 다이어그램 재생성 ─────────────────────────────────────
    st.markdown("---")
    if st.button("다이어그램 재생성", use_container_width=True):
        # 기존 파일 삭제 후 재생성
        for p in (OUT_PNG, OUT_PDF, OUT_SVG):
            try:
                Path(p).unlink(missing_ok=True)
            except Exception:
                pass
        st.session_state.diagram_paths = {}
        st.rerun()
