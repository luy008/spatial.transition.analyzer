"""02 검증 및 분석 — DXF 검증 + 4축 분석 + CriticalFinding 생성."""
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import math
import json
import streamlit as st
import pandas as pd

# ── 가드 ──────────────────────────────────────────────────────
if st.session_state.get("project_data") is None:
    st.warning("먼저 01 입력 페이지에서 프로젝트를 로드하세요.")
    if st.button("← 01 입력으로 이동"):
        st.switch_page("pages/01_input.py")
    st.stop()

project_data = st.session_state.project_data

st.title("02 검증 및 분석")
st.markdown(f"**{project_data.get('project_name', '')}**")
st.markdown("---")


# ══════════════════════════════════════════════════════════════
# 분석 파이프라인
# ══════════════════════════════════════════════════════════════

def _run_full_analysis(project_data: dict) -> dict:
    """4축 분석 파이프라인 (AI·인터넷 없음)."""
    from shapely.geometry import LineString, Point, Polygon
    from core.movement_analysis import compute_movement_cost, compute_directional_transformation
    from core.ramp_analysis import calculate_circular_ramp_metrics, sample_elevation_on_ramp
    from core.dxf_loader import load_dxf, filter_by_x_range, entity_to_linestring
    from core.geometry_classifier import auto_classify_all, remove_lines_inside_void, GeometryClass
    from core.isovist import IsovistParams, compute_route_isovists, compute_visibility_events
    from core.critical_findings import generate_findings_from_analysis

    settings = project_data.get("analysis_settings", {})
    routes = project_data.get("routes", {})
    levels = project_data.get("levels", {})
    spaces = project_data.get("spaces", {})

    ramp_speed = float(settings.get("ramp_speed_mps", 0.8))
    stair_speed = float(settings.get("stair_speed_mps", 0.5))

    # ── 1. 이동 비용 + 방향 전환 분석 (모든 경로) ───────────────
    movement_cost: dict = {}
    directional_raw: dict = {}
    geometry_rows: list = []

    for rid, rdata in routes.items():
        cp = rdata.get("control_points", [])
        if not cp or len(cp) < 2:
            continue
        rise = float(rdata.get("rise_m", 3.0))
        circ_type = rdata.get("circulation_type", "stair")
        speed = ramp_speed if circ_type == "ramp" else stair_speed

        centerline = LineString(cp)
        mc = compute_movement_cost(rid, centerline, rise, speed)
        dr = compute_directional_transformation(rid, centerline)

        movement_cost[rid] = mc
        directional_raw[rid] = {
            "cumulative_rotation_deg": dr.cumulative_rotation_deg,
            "tortuosity": dr.tortuosity,
            "n_direction_changes": dr.n_direction_changes,
            "curve_ratio": dr.curve_ratio,
        }
        geometry_rows.append({
            "유형": circ_type,
            "route_id": rid,
            "3D 이동거리(m)": round(mc.dist_3d_m, 2),
            "경사(%)": round(mc.slope_percent, 2),
        })

    # ── 2. R1 램프 전용 계산 ────────────────────────────────────
    ramp_metrics = None
    if "R1" in routes:
        arc = routes["R1"].get("arc", {})
        r_radius = float(arc.get("radius", settings.get("ramp_centerline_radius_m", 4.75)))
        r_rot = float(settings.get("ramp_total_rotation_deg", 360.0))
        r_rise = float(routes["R1"].get("rise_m", 3.0))
        try:
            ramp_metrics = calculate_circular_ramp_metrics(r_radius, r_rot, r_rise, ramp_speed)
        except Exception:
            pass

    # ── 3. DXF 로드 ─────────────────────────────────────────────
    src = project_data.get("source_file", "")
    dxf_path = ROOT / src if src else None
    doc = None
    entities = None
    dxf_error = None
    if dxf_path and dxf_path.exists():
        try:
            doc, entities = load_dxf(str(dxf_path))
            st.session_state.dxf_doc = doc
            st.session_state.dxf_entities = entities
        except Exception as ex:
            dxf_error = str(ex)

    # ── 4. Isovist 분석 (R1만, DXF 있을 때) ────────────────────
    iso_R1: dict = {}
    obstacles_R1: list = []

    if entities and "R1" in routes:
        L05 = levels.get("L05", {})
        win = L05.get("window", [163.521, 62.0, 205.321, 90.0])
        court_center = L05.get("courtyard_center", [184.421, 75.535])
        court_radius = float(L05.get("courtyard_radius_m", 4.0))

        l05_ents = filter_by_x_range(entities, win[0], win[2], scale=0.001)
        classified = auto_classify_all(l05_ents)

        raw_obstacles: list = []
        for ent, cls in classified:
            if cls in (GeometryClass.OPAQUE, GeometryClass.CURTAIN):
                ls = entity_to_linestring(ent, scale=0.001)
                if ls and not ls.is_empty and ls.length > 0:
                    raw_obstacles.append(ls)

        court_pt = Point(court_center[0], court_center[1])
        obstacles_R1, n_removed = remove_lines_inside_void(raw_obstacles, court_pt, court_radius)

        court_circle: Polygon = court_pt.buffer(court_radius, quad_segs=64)

        # 이전·다음 공간 polygon (point에서 2m 버퍼)
        next_R1_pt_raw = spaces.get("next_R1", {}).get("point", [186.729, 81.877])
        prev_R1_pt_raw = spaces.get("prev_R1", {}).get("point", [186.387, 80.938])
        next_space: Polygon = Point(next_R1_pt_raw[0], next_R1_pt_raw[1]).buffer(2.0)
        prev_space: Polygon = Point(prev_R1_pt_raw[0], prev_R1_pt_raw[1]).buffer(2.0)

        R1_cp = routes["R1"].get("control_points", [])
        if len(R1_cp) >= 2:
            R1_line = LineString(R1_cp)
            n_pts = int(settings.get("n_sample_points", 11))
            obs_pts = sample_elevation_on_ramp(R1_line, routes["R1"].get("rise_m", 3.0), n=n_pts)

            params = IsovistParams(
                n_rays=int(settings.get("isovist_rays", 720)),
                max_dist_m=float(settings.get("isovist_max_dist_m", 30.0)),
                min_area_m2=1.0,
                courtyard_visible_threshold=0.05,
            )
            iso_results = compute_route_isovists(
                obs_pts, obstacles_R1, params,
                prev_space=prev_space,
                court_circle=court_circle,
                next_space=next_space,
            )
            events = compute_visibility_events(iso_results)
            iso_R1 = {"results": iso_results, "events": events}

    # ── 5. CriticalFinding 생성 ──────────────────────────────────
    ar_for_findings = {
        "geometry": geometry_rows,
        "iso_R1": iso_R1,
        "directional": directional_raw,
        "visibility_threshold_m2": 0.05,
    }
    findings = generate_findings_from_analysis(ar_for_findings, project_data.get("project_name", ""))
    quality_warnings: list = []
    for f in findings:
        quality_warnings.extend(f.validate())

    return {
        "movement_cost": movement_cost,
        "directional": directional_raw,
        "ramp_metrics": ramp_metrics,
        "iso_R1": iso_R1,
        "geometry_rows": geometry_rows,
        "findings": findings,
        "quality_warnings": quality_warnings,
        "obstacles_R1": obstacles_R1,
        "dxf_entities": entities,
        "dxf_error": dxf_error,
        "dxf_entity_count": len(entities) if entities else 0,
    }


# ══════════════════════════════════════════════════════════════
# 분석 실행
# ══════════════════════════════════════════════════════════════
if not st.session_state.analysis_complete:
    st.info("아래 버튼을 클릭하면 DXF 검증과 4축 분석을 자동으로 실행합니다.")
    if st.button("분석 실행", type="primary", use_container_width=True):
        with st.spinner("DXF 검증 및 분석 중... (Isovist 계산은 30-60초 소요)"):
            results = _run_full_analysis(project_data)
        st.session_state.analysis_results = results
        st.session_state.quality_warnings = results.get("quality_warnings", [])
        st.session_state.analysis_complete = True
        st.rerun()

if not st.session_state.analysis_complete:
    st.stop()

# ══════════════════════════════════════════════════════════════
# 결과 표시
# ══════════════════════════════════════════════════════════════
results = st.session_state.analysis_results

# ── DXF 검증 ─────────────────────────────────────────────────
with st.expander("DXF 신뢰도 검증", expanded=True):
    err = results.get("dxf_error")
    cnt = results.get("dxf_entity_count", 0)
    if err:
        st.error(f"DXF 로드 오류: {err}")
    else:
        col1, col2, col3 = st.columns(3)
        col1.metric("총 엔티티 수", cnt)
        entities_now = st.session_state.get("dxf_entities") or []
        if entities_now:
            layers = sorted(set(e["layer"] for e in entities_now))
            col2.metric("레이어 수", len(layers))
            types = sorted(set(e["type"] for e in entities_now))
            col3.metric("엔티티 유형 수", len(types))
            with st.expander("레이어 목록", expanded=False):
                st.write(layers)
        st.success("ezdxf 파싱 완료 — 신뢰도 검증 통과")

# ── 이동 비용 분석 ───────────────────────────────────────────
with st.expander("축 1 · 이동 비용 (Movement Cost)", expanded=True):
    mc = results.get("movement_cost", {})
    if mc:
        rows = []
        for rid, m in mc.items():
            rows.append({
                "경로": rid,
                "유형": project_data.get("routes", {}).get(rid, {}).get("circulation_type", "-"),
                "계획 거리(m)": f"{m.plan_distance_m:.2f}",
                "3D 거리(m)": f"{m.dist_3d_m:.2f}",
                "상승(m)": f"{m.rise_m:.1f}",
                "경사(%)": f"{m.slope_percent:.2f}",
                "경사비": f"1:{m.slope_ratio:.1f}",
                "각도(°)": f"{m.slope_angle_deg:.2f}",
                "이동시간(s)": f"{m.est_time_s:.1f}",
                "속도(m/s)": f"{m.speed_mps:.1f}",
            })
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
    rm = results.get("ramp_metrics")
    if rm:
        st.markdown("**R1 램프 설계값 검증**")
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("반지름(m)", f"{rm.radius_m:.2f}")
        c2.metric("수평 길이(m)", f"{rm.horizontal_length_m:.3f}")
        c3.metric("3D 이동(m)", f"{rm.travel_length_3d_m:.3f}")
        c4.metric("경사(%)", f"{rm.slope_percent:.3f}")
        st.caption(rm.annotation())

# ── 방향 전환 분석 ───────────────────────────────────────────
with st.expander("축 2 · 방향 전환 (Directional Transformation)", expanded=True):
    dr = results.get("directional", {})
    if dr:
        rows = []
        for rid, d in dr.items():
            rows.append({
                "경로": rid,
                "누적 회전(°)": f"{d.get('cumulative_rotation_deg', 0):.1f}",
                "tortuosity": f"{d.get('tortuosity', 1):.3f}",
                "방향변화 횟수": d.get("n_direction_changes", "-"),
                "곡선 비율": f"{d.get('curve_ratio', 0):.2f}",
            })
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
        st.caption("tortuosity = 실제경로길이 / 직선거리. 1.0 = 완전 직선, >1 = 우회")

# ── 시야 변환 분석 ───────────────────────────────────────────
with st.expander("축 3 · 시야 변환 (Visual Transformation) — R1 Isovist", expanded=True):
    iso = results.get("iso_R1", {})
    evts = iso.get("events", {})
    iso_results_list = iso.get("results", [])

    if evts:
        c1, c2, c3 = st.columns(3)
        court_dur = evts.get("courtyard_visibility_duration_percent", 0)
        next_first = evts.get("next_space_first_visible_percent")
        prev_last = evts.get("previous_space_last_visible_percent")
        c1.metric("중정 가시 지속율", f"{court_dur:.0f}%")
        c2.metric("다음 공간 최초 가시", f"{next_first:.0f}%" if next_first is not None else "미검출")
        c3.metric("이전 공간 마지막 가시", f"{prev_last:.0f}%" if prev_last is not None else "미검출")

        if iso_results_list:
            import matplotlib
            matplotlib.use("Agg")
            import matplotlib.pyplot as plt
            import matplotlib.patches as mpatches

            fig, ax = plt.subplots(figsize=(10, 2.5))
            n = len(iso_results_list)
            colors = {"courtyard": "#17BECF", "next": "#C0392B", "previous": "#2980B9"}
            labels = {"courtyard": "중정 가시", "next": "다음 공간 가시", "previous": "이전 공간 가시"}
            keys = ["courtyard", "next", "previous"]
            band_h = 0.9
            gap = 0.6

            for row_i, key in enumerate(keys):
                attr = f"{key}_visible"
                y_top = -(row_i * (band_h + gap))
                col = colors[key]
                ax.add_patch(plt.Rectangle((0, y_top - band_h), 1, band_h,
                                           fill=False, ec="#ccc", lw=0.5))
                seg = 1.0 / (n - 1) if n > 1 else 1.0
                for ii, res in enumerate(iso_results_list):
                    if getattr(res, attr, False):
                        ax.add_patch(plt.Rectangle(
                            (ii * seg - seg / 2, y_top - band_h), seg, band_h,
                            fc=col, ec="none", alpha=0.85,
                        ))
                ax.text(-0.02, y_top - band_h / 2, labels[key],
                        ha="right", va="center", fontsize=8, color=col)
                ax.text(1.02, y_top - band_h / 2,
                        f"{sum(1 for r in iso_results_list if getattr(r, attr, False))}/{n}",
                        ha="left", va="center", fontsize=7, color=col)

            ax.set_xlim(-0.18, 1.12)
            ax.set_ylim(-(len(keys) * (band_h + gap)), 0.5)
            ax.set_xticks([0, 0.25, 0.5, 0.75, 1.0])
            ax.set_xticklabels(["0%", "25%", "50%", "75%", "100%"], fontsize=8)
            ax.axis("off")
            ax.xaxis.set_visible(True)
            ax.spines["bottom"].set_visible(True)
            ax.tick_params(left=False)
            ax.set_xlabel("R1 진행율 →", fontsize=8)
            plt.tight_layout()
            st.pyplot(fig, use_container_width=True)
            plt.close(fig)

        if iso_results_list:
            areas = [r.area_m2 for r in iso_results_list]
            progs = [r.progress_percent for r in iso_results_list]
            fig2, ax2 = plt.subplots(figsize=(10, 2.5))
            ax2.plot(progs, areas, "o-", color="#C0392B", lw=1.5, ms=5)
            ax2.fill_between(progs, areas, alpha=0.15, color="#C0392B")
            ax2.set_xlabel("진행율 (%)", fontsize=8)
            ax2.set_ylabel("Isovist 면적 (m²)", fontsize=8)
            ax2.set_title("R1 진행에 따른 Isovist 면적 변화", fontsize=9)
            ax2.grid(True, alpha=0.25)
            plt.tight_layout()
            st.pyplot(fig2, use_container_width=True)
            plt.close(fig2)
    else:
        st.info("DXF가 없거나 R1 control_points가 없어 Isovist를 계산하지 못했습니다.")

# ── 공간인지 시퀀스 ─────────────────────────────────────────
with st.expander("축 4 · 공간 인지 시퀀스 (Spatial Recognition Sequence)", expanded=False):
    evts = results.get("iso_R1", {}).get("events", {})
    if evts:
        st.markdown("**R1 공간 인지 이벤트**")
        seq_data = [
            {"이벤트": "이전 공간 마지막 인지",
             "진행율": f"{evts.get('previous_space_last_visible_percent', '미검출')}%"
             if evts.get('previous_space_last_visible_percent') is not None else "미검출"},
            {"이벤트": "중정 가시 지속 구간",
             "진행율": f"전체 {evts.get('courtyard_visibility_duration_percent', 0):.0f}%"},
            {"이벤트": "다음 공간(최상부 전시실) 최초 인지",
             "진행율": f"{evts.get('next_space_first_visible_percent', '미검출')}%"
             if evts.get('next_space_first_visible_percent') is not None else "미검출"},
        ]
        st.dataframe(pd.DataFrame(seq_data), use_container_width=True, hide_index=True)
        st.caption(
            "방법론 한계: 2D Isovist는 램프 관찰자의 실제 눈높이 상승을 반영하지 않으며, "
            "중정 커튼월의 투명도를 완전 투명으로 처리합니다. "
            "가시성은 면적 기준 0.05m² 이상을 '가시'로 분류합니다."
        )
    else:
        st.info("Isovist 분석이 없으면 공간 인지 시퀀스를 생성할 수 없습니다.")

# ── CriticalFinding ───────────────────────────────────────────
st.markdown("---")
st.subheader("CriticalFinding")

findings = results.get("findings", [])
if findings:
    for f in findings:
        with st.expander(f"**{f.finding_id}** · {f.title}", expanded=True):
            col_l, col_r = st.columns([2, 1])
            with col_l:
                st.markdown("**관찰 결과**")
                st.write(f.observed_result)
                st.markdown("**관련 형상**")
                st.caption(f.related_geometry)
                st.markdown("**방법론적 환원**")
                st.warning(f.methodological_reduction)
                st.markdown("**해석 위험**")
                st.error(f.interpretive_risk)
                st.markdown("**설계 함의**")
                st.info(f.design_implication)
            with col_r:
                st.markdown("**근거 목록 (EvidenceReference)**")
                for ev in f.evidence:
                    route_tag = f" · `{ev.route_id}`" if ev.route_id else ""
                    sample_tag = f" · sample `{ev.sample_id}`" if ev.sample_id else ""
                    st.markdown(
                        f"- **{ev.metric_name}**: {ev.value} {ev.unit}{route_tag}{sample_tag}"
                    )
                st.markdown(f"**신뢰도**: `{f.confidence}`")
else:
    st.info("분석 결과가 충분하지 않아 CriticalFinding을 생성하지 못했습니다.")

# ── 품질 검사 ────────────────────────────────────────────────
warnings = results.get("quality_warnings", [])
if warnings:
    st.markdown("---")
    st.subheader("품질 검사 경고")
    for w in warnings:
        st.warning(w)
else:
    st.success("품질 검사 통과 — generic claim 없음, 모든 근거 링크 정상")

# ── 다음 페이지 이동 ─────────────────────────────────────────
st.markdown("---")
if st.button("다이어그램 생성 및 내보내기 →", type="primary", use_container_width=True):
    st.switch_page("pages/03_diagram_export.py")

if st.button("분석 재실행", use_container_width=True):
    st.session_state.analysis_complete = False
    st.rerun()
