"""TAB 4 — ROUTES & SPACES: 계단·램프·공간 입력."""
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

from core.models import RouteSpec, RouteType, SpaceSpec
from core.ramp_analysis import calculate_circular_ramp_metrics, build_circular_ramp_centerline
from core.stair_analysis import calculate_stair_metrics
from shapely.geometry import LineString, Point

st.set_page_config(page_title="Routes — STA", layout="wide")
st.title("🛤 04. ROUTES & SPACES")

if not st.session_state.get("project"):
    st.warning("01 PROJECT에서 프로젝트를 여세요.")
    st.stop()

proj = st.session_state.project
t_route, t_space, t_preview = st.tabs(["동선 편집", "공간 편집", "미리보기"])

# ──────────────────────────────────────────────────────────────
with t_route:
    st.subheader("동선 경로 편집")

    # 기존 경로 목록
    if proj.routes:
        st.write(f"**현재 경로 {len(proj.routes)}개:**")
        for i, r in enumerate(proj.routes):
            col1, col2, col3 = st.columns([3, 2, 1])
            with col1:
                st.write(f"**{r.route_id}** ({r.route_type.value}) "
                         f"{r.source_level} → {r.destination_level}")
            with col2:
                st.caption(f"상승 {r.rise_m}m | {'원형' if r.is_circular else '다각형'} | "
                           f"{'CW' if r.direction=='cw' else 'CCW'}")
            with col3:
                if st.button("삭제", key=f"del_r_{i}"):
                    proj.routes.pop(i)
                    st.rerun()

    st.markdown("---")
    st.write("**새 경로 추가**")

    rtype = st.selectbox("동선 유형", [e.value for e in RouteType])
    col1, col2 = st.columns(2)
    with col1:
        rid = st.text_input("경로 ID", value=f"Route_{len(proj.routes)+1}")
        src_lvl_opts = [f.level_id for f in proj.floors] or ["L01", "L02", "L03", "L04", "L05"]
        src_lvl = st.selectbox("출발 층", src_lvl_opts, key="src")
        dst_lvl = st.selectbox("도착 층", src_lvl_opts, index=min(1, len(src_lvl_opts)-1), key="dst")
    with col2:
        rise_m = st.number_input("상승 높이 (m)", value=3.0, min_value=0.1, format="%.2f")
        width_m = st.number_input("폭 (m)", value=1.5, min_value=0.1, format="%.2f")
        court_rel = st.checkbox("중정 관련 동선", value=True)

    # 원형 경로 설정
    is_circular = st.checkbox("원형 경로 (계단·램프)", value=True)
    if is_circular:
        st.write("**원형 경로 파라미터**")
        # 기본 중정 중심 (선택된 층)
        floor_map = {f.level_id: f for f in proj.floors}
        src_floor = floor_map.get(src_lvl)
        default_cx = float(src_floor.courtyard_center[0]) if src_floor and src_floor.courtyard_center else 0.0
        default_cy = float(src_floor.courtyard_center[1]) if src_floor and src_floor.courtyard_center else 0.0
        col1, col2, col3 = st.columns(3)
        with col1:
            circ_cx = st.number_input("중심 X (m)", value=default_cx, format="%.3f")
            circ_cy = st.number_input("중심 Y (m)", value=default_cy, format="%.3f")
            circ_r = st.number_input("중심선 반지름 (m)", value=4.75, format="%.3f")
        with col2:
            circ_start = st.number_input("시작각 (°)", value=70.0, format="%.1f")
            circ_rot = st.number_input("회전각 (°)", value=360.0 if rtype == "ramp" else 121.0, format="%.1f")
            direction = st.selectbox("방향", ["ccw", "cw"])
        with col3:
            # 미리 계산
            if rtype == "ramp":
                try:
                    m = calculate_circular_ramp_metrics(circ_r, circ_rot, rise_m)
                    st.metric("평면 길이", f"{m.horizontal_length_m:.2f} m")
                    st.metric("3D 이동거리", f"{m.travel_length_3d_m:.2f} m")
                    st.metric("경사율", f"{m.slope_percent:.2f} %")
                    st.metric("경사비", f"1:{m.slope_ratio:.2f}")
                except Exception as e:
                    st.error(str(e))
    else:
        circ_cx = circ_cy = circ_r = circ_start = circ_rot = 0.0
        direction = "ccw"

    prev_sp = st.text_input("이전 공간 ID (선택)", value=f"prev_{rid}")
    next_sp = st.text_input("다음 공간 ID (선택)", value=f"next_{rid}")

    if st.button("✅ 경로 추가", type="primary"):
        new_route = RouteSpec(
            route_id=rid, route_type=RouteType(rtype),
            source_level=src_lvl, destination_level=dst_lvl,
            rise_m=rise_m, width_m=width_m,
            is_circular=is_circular,
            circular_center=(circ_cx, circ_cy) if is_circular else None,
            circular_radius_m=circ_r if is_circular else 4.75,
            circular_rotation_deg=circ_rot if is_circular else 360.0,
            circular_start_angle_deg=circ_start if is_circular else 0.0,
            direction=direction,
            courtyard_related=court_rel,
            previous_space_id=prev_sp or None,
            next_space_id=next_sp or None)
        proj.routes.append(new_route)
        st.success(f"'{rid}' 경로 추가 완료")
        st.rerun()

# ──────────────────────────────────────────────────────────────
with t_space:
    st.subheader("공간 영역 편집")
    st.caption("이전 공간, 중정, 다음 공간을 polygon으로 지정합니다.")

    if proj.spaces:
        for i, sp in enumerate(proj.spaces):
            col1, col2 = st.columns([4, 1])
            with col1:
                st.write(f"**{sp.space_id}** — {sp.label} "
                         f"({'중정' if sp.is_courtyard else '일반'}) "
                         f"[{len(sp.polygon_points)}점]")
            with col2:
                if st.button("삭제", key=f"del_sp_{i}"):
                    proj.spaces.pop(i)
                    st.rerun()

    st.markdown("---")
    st.write("**새 공간 추가**")
    sp_id = st.text_input("공간 ID", value=f"space_{len(proj.spaces)+1}")
    sp_label = st.text_input("레이블", value="이전 공간")
    is_court = st.checkbox("중정으로 표시", value=False)
    sp_lvl = st.selectbox("해당 층", [f.level_id for f in proj.floors] or ["L01"])

    st.info("좌표를 직접 입력하세요. (도면의 x, y 값, m 단위)")
    pts_text = st.text_area("polygon 좌표 (x,y 한 줄씩)", value="", height=100,
                             placeholder="예:\n184.0, 71.0\n189.0, 71.0\n189.0, 80.0\n184.0, 80.0")
    if st.button("공간 추가"):
        pts = []
        for line in pts_text.strip().split("\n"):
            try:
                x, y = line.split(",")
                pts.append((float(x.strip()), float(y.strip())))
            except Exception:
                pass
        if pts:
            proj.spaces.append(SpaceSpec(space_id=sp_id, label=sp_label,
                                         polygon_points=pts, is_courtyard=is_court, level_id=sp_lvl))
            st.success(f"'{sp_id}' 추가 완료 ({len(pts)}점)")
            st.rerun()
        else:
            st.error("유효한 좌표가 없습니다.")

# ──────────────────────────────────────────────────────────────
with t_preview:
    st.subheader("동선 미리보기")
    if not proj.routes:
        st.info("경로가 없습니다.")
    else:
        sel_ids = st.multiselect("표시할 경로", [r.route_id for r in proj.routes],
                                  default=[r.route_id for r in proj.routes])
        if st.button("미리보기 생성"):
            fig, ax = plt.subplots(figsize=(10, 10))
            extent = 10.0
            colors = {"stair": "#2980B9", "ramp": "#C0392B", "corridor": "#888"}
            for r in proj.routes:
                if r.route_id not in sel_ids:
                    continue
                col = colors.get(r.route_type.value, "#888")
                if r.is_circular and r.circular_center:
                    cx, cy = r.circular_center
                    cl = build_circular_ramp_centerline(
                        Point(cx, cy), r.circular_radius_m,
                        r.circular_start_angle_deg, r.direction, r.circular_rotation_deg)
                    xs = [p[0]-cx for p in cl.coords]
                    ys = [p[1]-cy for p in cl.coords]
                    extent = max(extent, max(abs(x) for x in xs+[0]) + 2)
                    ax.plot(xs, ys, "-", color=col, lw=2.5 if r.route_type==RouteType.RAMP else 1.8,
                            label=r.route_id)
                    ax.plot(xs[0], ys[0], "o", color=col, ms=8)
                    ax.plot(xs[-1], ys[-1], "s", color=col, ms=8)
                elif r.control_points:
                    cx = sum(p[0] for p in r.control_points) / len(r.control_points)
                    cy = sum(p[1] for p in r.control_points) / len(r.control_points)
                    xs = [p[0]-cx for p in r.control_points]
                    ys = [p[1]-cy for p in r.control_points]
                    ax.plot(xs, ys, "-", color=col, lw=1.5, label=r.route_id)

            # 중정 원 (참조)
            theta = np.linspace(0, 2*math.pi, 64)
            for r in proj.routes:
                if r.is_circular and r.circular_center and r.route_id in sel_ids:
                    ax.plot(4.0 * np.cos(theta), 4.0 * np.sin(theta),
                            ":", color="#17BECF", lw=1.5)
                    ax.plot(0, 0, "+", color="#17BECF", ms=14)
                    break
            ax.set_xlim(-extent, extent)
            ax.set_ylim(-extent, extent)
            ax.set_aspect("equal")
            ax.legend(fontsize=9)
            ax.set_title("동선 미리보기 (중정 중심 정렬)", fontsize=11)
            ax.grid(True, alpha=0.25)
            fig.tight_layout()
            buf = io.BytesIO()
            fig.savefig(buf, dpi=130, facecolor="white")
            plt.close(fig)
            st.image(buf.getvalue(), use_container_width=True)

if st.button("💾 경로·공간 저장", type="primary", key="save_routes"):
    from core.project_store import save_project
    p = save_project(proj)
    st.success(f"저장 완료: {p}")
