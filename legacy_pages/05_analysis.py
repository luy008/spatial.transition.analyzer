"""TAB 5 — ANALYSIS: 기하 + Isovist + 가시 이벤트 분석."""
import sys
from pathlib import Path
ROOT = Path(__file__).parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import io
import math
import streamlit as st
import pandas as pd
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from shapely.geometry import LineString, Point, Polygon

from core.models import RouteType, AnalysisSettings
from core.ramp_analysis import calculate_circular_ramp_metrics, build_circular_ramp_centerline
from core.stair_analysis import calculate_stair_metrics
from core.dxf_loader import entity_to_linestring, filter_by_x_range
from core.geometry_classifier import (auto_classify_all, GeometryClass,
                                       remove_lines_inside_void)
from core.isovist import IsovistParams, compute_route_isovists, compute_visibility_events

st.set_page_config(page_title="Analysis — STA", layout="wide")
st.title("📊 05. ANALYSIS")

if not st.session_state.get("project"):
    st.warning("01 PROJECT에서 프로젝트를 여세요.")
    st.stop()

proj = st.session_state.project
if not proj.routes:
    st.warning("04 ROUTES & SPACES에서 경로를 입력하세요.")
    st.stop()

settings = proj.analysis_settings
entities = st.session_state.get("dxf_entities", [])

# ── 분석 설정 ─────────────────────────────────────────────────
with st.expander("분석 설정", expanded=False):
    col1, col2, col3 = st.columns(3)
    with col1:
        n_samp = st.number_input("관찰점 수", value=settings.n_sample_points,
                                  min_value=3, max_value=50)
        n_rays = st.number_input("Isovist ray 수", value=settings.isovist_rays,
                                  min_value=90, max_value=2880, step=90)
    with col2:
        max_d = st.number_input("최대 가시거리 (m)", value=settings.isovist_max_dist_m)
        ramp_spd = st.number_input("램프 보행속도 (m/s)", value=settings.ramp_speed_mps,
                                    format="%.2f")
    with col3:
        stair_spd = st.number_input("계단 보행속도 (m/s)", value=settings.stair_speed_mps,
                                     format="%.2f")
        court_thresh = st.number_input("중정 가시 임계값 (m²)", value=settings.courtyard_visible_threshold,
                                        format="%.3f")

# ── 분석 실행 ─────────────────────────────────────────────────
t_geom, t_iso, t_compare = st.tabs(["A. 기하 분석", "B. Isovist 분석", "C. 비교 결과"])

with t_geom:
    st.subheader("동선 기하 분석")
    if st.button("기하 분석 실행", type="primary"):
        results = []
        for r in proj.routes:
            try:
                if r.is_circular and r.circular_center:
                    center = Point(*r.circular_center)
                    cl = build_circular_ramp_centerline(
                        center, r.circular_radius_m, r.circular_start_angle_deg,
                        r.direction, r.circular_rotation_deg)
                    if r.route_type == RouteType.RAMP:
                        m = calculate_circular_ramp_metrics(r.circular_radius_m,
                                                            r.circular_rotation_deg,
                                                            r.rise_m, ramp_spd)
                        results.append({
                            "경로 ID": r.route_id, "유형": r.route_type.value,
                            "층": f"{r.source_level}→{r.destination_level}",
                            "평면 길이(m)": round(m.horizontal_length_m, 3),
                            "3D 이동거리(m)": round(m.travel_length_3d_m, 3),
                            "상승(m)": r.rise_m, "회전각(°)": r.circular_rotation_deg,
                            "경사(%)": round(m.slope_percent, 3),
                            "경사비": f"1:{m.slope_ratio:.2f}",
                            "경사각(°)": round(m.slope_angle_deg, 3),
                            "보행시간(s)": round(m.est_time_s, 1),
                        })
                    else:
                        m = calculate_stair_metrics(r.route_id, cl, r.rise_m,
                                                    r.width_m, speed_mps=stair_spd)
                        results.append({
                            "경로 ID": r.route_id, "유형": r.route_type.value,
                            "층": f"{r.source_level}→{r.destination_level}",
                            "평면 길이(m)": round(m.plan_distance_m, 3),
                            "3D 이동거리(m)": round(m.dist_3d_m, 3),
                            "상승(m)": m.rise_m, "회전각(°)": r.circular_rotation_deg,
                            "경사(%)": round(m.slope_percent, 3),
                            "경사비": f"1:{m.plan_distance_m/m.rise_m:.2f}" if m.rise_m else "—",
                            "경사각(°)": round(m.stair_angle_deg, 3),
                            "보행시간(s)": round(m.est_time_s, 1),
                        })
            except Exception as e:
                st.error(f"{r.route_id} 계산 오류: {e}")
        if results:
            df = pd.DataFrame(results)
            st.dataframe(df, use_container_width=True)
            st.session_state.analysis_results["geometry"] = results
            csv = df.to_csv(index=False, encoding="utf-8-sig")
            st.download_button("⬇ CSV 다운로드", data=csv,
                               file_name="route_geometry.csv", mime="text/csv")

with t_iso:
    st.subheader("Isovist 분석")
    st.caption("선택된 층의 장애물을 기준으로 각 경로에서 Isovist를 계산합니다.")

    floor_map = {f.level_id: f for f in proj.floors}
    iso_route = st.selectbox("분석할 경로", [r.route_id for r in proj.routes])
    route = next((r for r in proj.routes if r.route_id == iso_route), None)

    if route and st.button("Isovist 분석 실행", type="primary", key="run_iso"):
        # 장애물 추출
        floor = floor_map.get(route.destination_level) or floor_map.get(route.source_level)
        with st.spinner("장애물 추출 + Isovist 계산 중 (1–2분 소요)..."):
            if entities and floor:
                floor_ents = filter_by_x_range(entities, floor.xmin, floor.xmax, proj.dxf_unit_scale)
                layer_rules = {l: k for k, v in proj.layer_classification.items() for l in (v or [])}
                opaque = []
                for e, cls in auto_classify_all(floor_ents, layer_rules):
                    if cls == GeometryClass.OPAQUE:
                        ls = entity_to_linestring(e, proj.dxf_unit_scale)
                        if ls and not ls.is_empty:
                            opaque.append(ls)
                # 중정 내부 벽 제거
                if floor.courtyard_center:
                    center = Point(*floor.courtyard_center)
                    opaque, removed = remove_lines_inside_void(opaque, center, floor.courtyard_radius_m)
                    if removed:
                        st.info(f"중정 내부 벽 {removed}개 제거")
            else:
                opaque = []
                st.info("도면 없음 — 장애물 없이 분석")

            # 관찰점 생성
            if route.is_circular and route.circular_center:
                center_pt = Point(*route.circular_center)
                cl = build_circular_ramp_centerline(
                    center_pt, route.circular_radius_m,
                    route.circular_start_angle_deg, route.direction, route.circular_rotation_deg)
                n = int(n_samp)
                obs_pts = [(cl.interpolate(i/(n-1), normalized=True).x,
                            cl.interpolate(i/(n-1), normalized=True).y,
                            route.rise_m * i/(n-1)) for i in range(n)]
            else:
                st.error("원형 경로가 아닙니다. 좌표를 지정하세요.")
                st.stop()

            # 공간 polygon
            court_poly = None
            if floor and floor.courtyard_center:
                cx, cy = floor.courtyard_center
                try:
                    court_poly = Point(cx, cy).buffer(floor.courtyard_radius_m, quad_segs=64)
                except Exception:
                    court_poly = Point(cx, cy).buffer(floor.courtyard_radius_m, resolution=64)

            prev_poly = next_poly = None
            for sp in proj.spaces:
                if sp.space_id == route.previous_space_id and sp.polygon_points:
                    prev_poly = Polygon(sp.polygon_points)
                if sp.space_id == route.next_space_id and sp.polygon_points:
                    next_poly = Polygon(sp.polygon_points)

            params = IsovistParams(n_rays=int(n_rays), max_dist_m=float(max_d),
                                   courtyard_visible_threshold=float(court_thresh))
            results = compute_route_isovists(obs_pts, opaque, params,
                                             prev_poly, court_poly, next_poly)
            events = compute_visibility_events(results)
            st.session_state.analysis_results[f"iso_{iso_route}"] = {
                "results": [r.__dict__ for r in results],
                "events": events
            }

        # 시각화
        fig, axes = plt.subplots(1, min(4, len(results)), figsize=(14, 5))
        if len(results) == 1:
            axes = [axes]
        idxs = np.linspace(0, len(results)-1, min(4, len(results))).astype(int)
        ramp_col = "#C0392B" if route.route_type == RouteType.RAMP else "#2980B9"
        cx2, cy2 = route.circular_center if route.circular_center else (0, 0)
        for ax, idx in zip(axes, idxs):
            res = results[idx]
            for obs in opaque[:2000]:
                try:
                    xs, ys = obs.xy
                    ax.plot([x-cx2 for x in xs], [y-cy2 for y in ys], "-", color="#999", lw=0.5)
                except Exception:
                    pass
            if res.polygon_coords:
                px = [p[0]-cx2 for p in res.polygon_coords]
                py = [p[1]-cy2 for p in res.polygon_coords]
                ax.fill(px, py, color=ramp_col, alpha=0.25)
            if floor and floor.courtyard_center:
                cx3, cy3 = floor.courtyard_center
                theta = np.linspace(0, 2*math.pi, 64)
                r3 = floor.courtyard_radius_m
                ax.fill(r3*np.cos(theta), r3*np.sin(theta), color="#EAF7F0", alpha=1.0, zorder=5)
                ax.plot(r3*np.cos(theta), r3*np.sin(theta), "-", color="#17BECF", lw=1.2, zorder=6)
            ox, oy, _ = obs_pts[idx]
            ax.plot(ox-cx2, oy-cy2, "o", color="#E67E22", ms=10)
            flags = ("이전 " if res.previous_visible else "") + \
                    ("중정 " if res.courtyard_visible else "") + \
                    ("다음" if res.next_visible else "")
            ax.set_title(f"{res.progress_percent:.0f}%\n{res.area_m2:.0f}m² {flags.strip() or '—'}",
                         fontsize=8)
            ax.set_xlim(-10, 10); ax.set_ylim(-10, 10)
            ax.set_aspect("equal"); ax.axis("off")
        fig.suptitle(f"{iso_route} Isovist 시퀀스", fontweight="bold")
        fig.tight_layout()
        buf = io.BytesIO()
        fig.savefig(buf, dpi=130, facecolor="white")
        plt.close(fig)
        st.image(buf.getvalue(), use_container_width=True)

        # 이벤트 요약
        st.write("**가시 이벤트 요약**")
        ev = events
        col1, col2, col3 = st.columns(3)
        col1.metric("중정 가시 지속", f"{ev.get('courtyard_visibility_duration_percent', 0):.1f}%")
        col2.metric("다음 공간 최초 가시", f"{ev.get('next_space_first_visible_percent', 'N/A')}%"
                    if ev.get('next_space_first_visible_percent') is not None else "미인지")
        col3.metric("이전 공간 마지막 가시", f"{ev.get('previous_space_last_visible_percent', 'N/A')}%"
                    if ev.get('previous_space_last_visible_percent') is not None else "미인지")

with t_compare:
    st.subheader("전체 동선 비교")
    geo_data = st.session_state.analysis_results.get("geometry", [])
    if geo_data:
        df = pd.DataFrame(geo_data)
        st.dataframe(df, use_container_width=True)
        # 이동거리 비교
        fig, ax = plt.subplots(figsize=(8, 4))
        rids = df["경로 ID"].tolist()
        dists = df["3D 이동거리(m)"].tolist()
        colors = ["#C0392B" if t == "ramp" else "#2980B9" for t in df["유형"].tolist()]
        ax.bar(rids, dists, color=colors)
        ax.set_ylabel("3D 이동거리 (m)")
        ax.set_title("경로별 이동거리 비교")
        ax.grid(True, alpha=0.3, axis="y")
        fig.tight_layout()
        buf = io.BytesIO()
        fig.savefig(buf, dpi=100, facecolor="white")
        plt.close(fig)
        st.image(buf.getvalue(), use_container_width=True)
    else:
        st.info("A. 기하 분석을 먼저 실행하세요.")
