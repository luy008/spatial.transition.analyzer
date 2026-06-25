"""TAB 2 — IMPORT & CLEANUP: DXF 불러오기 · 층 범위 지정 · 레이어 필터."""
import sys
from pathlib import Path
ROOT = Path(__file__).parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import io
import streamlit as st
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from core.dxf_loader import (load_dxf, get_layer_names, get_bounds,
                              get_all_linestrings, filter_by_x_range, auto_detect_floors)
from core.models import FloorBounds

st.set_page_config(page_title="Import — STA", layout="wide")
st.title("📥 02. IMPORT & CLEANUP")

if not st.session_state.get("project"):
    st.warning("먼저 01 PROJECT에서 프로젝트를 생성하거나 여세요.")
    st.stop()

proj = st.session_state.project

# ── DXF 업로드 ────────────────────────────────────────────────
st.subheader("도면 파일 불러오기")
col1, col2 = st.columns([2, 1])
with col1:
    uploaded = st.file_uploader("DXF 파일 업로드", type=["dxf"])
    if uploaded:
        tmp = Path(ROOT) / "exports" / "_tmp_upload.dxf"
        tmp.write_bytes(uploaded.read())
        proj.source_file = str(tmp)
        st.session_state.dxf_entities = None
with col2:
    sample = Path(ROOT) / "sample_data" / "Drawing1.dxf"
    if sample.exists():
        if st.button("샘플 도면 사용 (Drawing1.dxf)"):
            proj.source_file = str(sample)
            st.session_state.dxf_entities = None
            st.success("샘플 도면 연결됨")

# ── DXF 로드 ─────────────────────────────────────────────────
if proj.source_file and Path(proj.source_file).exists():
    if st.session_state.dxf_entities is None:
        with st.spinner("DXF 파싱 중..."):
            try:
                _doc, entities = load_dxf(proj.source_file)
                st.session_state.dxf_entities = entities
                st.success(f"엔티티 {len(entities):,}개 로드 완료")
            except Exception as e:
                st.error(f"DXF 파싱 오류: {e}")
                st.stop()

entities = st.session_state.get("dxf_entities")
if entities is None:
    st.info("DXF 파일을 업로드하거나 샘플을 선택하세요.")
    st.stop()

# ── 레이어 필터 ───────────────────────────────────────────────
scale = proj.dxf_unit_scale
layers = get_layer_names(entities)
bnd = get_bounds(entities, scale)

with st.expander("레이어 표시 설정", expanded=False):
    col1, col2 = st.columns([1, 1])
    with col1:
        hide_text = st.checkbox("텍스트·주석 숨김", value=True)
        hide_dim = st.checkbox("치수선 숨김", value=True)
        hide_hatch = st.checkbox("해치 숨김", value=True)
    with col2:
        st.write(f"전체 엔티티: {len(entities):,}개 | 레이어: {len(layers)}개")
        st.write(f"도면 범위 (m): X {bnd[0]:.1f}–{bnd[2]:.1f} | Y {bnd[1]:.1f}–{bnd[3]:.1f}")

exclude_types = []
if hide_text:
    exclude_types += ["TEXT", "MTEXT", "DIMENSION"]
if hide_hatch:
    exclude_types += ["HATCH"]
vis_entities = [e for e in entities if e["type"] not in exclude_types]
if hide_dim:
    vis_entities = [e for e in vis_entities
                    if not any(kw in e["layer"] for kw in ["DIM", "dim", "Dim", "A-07"])]

# ── 전체 DXF 미리보기 ─────────────────────────────────────────
st.subheader("DXF 전체 미리보기")
if st.button("미리보기 생성", key="preview_full"):
    with st.spinner("렌더링 중..."):
        fig, ax = plt.subplots(figsize=(16, 6))
        for e in vis_entities[:8000]:
            from core.dxf_loader import entity_to_linestring
            ls = entity_to_linestring(e, scale)
            if ls and not ls.is_empty:
                try:
                    xs, ys = ls.xy
                    ax.plot(xs, ys, "-", color="#555", lw=0.4, alpha=0.7)
                except Exception:
                    pass
        ax.set_aspect("equal")
        ax.set_xlabel("x (m)"); ax.set_ylabel("y (m)")
        ax.set_title("DXF 전체 (상위 8000 엔티티)")
        ax.grid(True, alpha=0.2)
        fig.tight_layout()
        buf = io.BytesIO()
        fig.savefig(buf, dpi=100, facecolor="white")
        plt.close(fig)
        st.image(buf.getvalue(), use_container_width=True)

# ── 층 범위 지정 ─────────────────────────────────────────────
st.subheader("층별 범위 지정")
st.caption("각 층의 X 범위를 입력하세요. 자동 감지 값을 수정할 수 있습니다.")

if st.button("자동 감지", key="auto_detect"):
    auto = auto_detect_floors(entities, scale, n_floors=6)
    proj.floors = [FloorBounds(
        level_id=f["level_id"], label=f.get("label", f["level_id"]),
        xmin=f["xmin"], ymin=bnd[1], xmax=f["xmax"], ymax=bnd[3]
    ) for f in auto]
    st.success(f"{len(proj.floors)}개 층 자동 감지")

n_floors = st.number_input("층 수", min_value=1, max_value=20, value=max(len(proj.floors), 5))

floor_configs = []
cols = st.columns(min(int(n_floors), 6))
for i in range(int(n_floors)):
    with cols[i % len(cols)]:
        existing = proj.floors[i] if i < len(proj.floors) else None
        lid = st.text_input(f"층 ID", value=existing.level_id if existing else f"L{i+1:02d}",
                             key=f"lid_{i}")
        label = st.text_input(f"레이블", value=existing.label if existing else f"Level {i+1:02d}",
                              key=f"llbl_{i}")
        xmin_v = float(existing.xmin if existing else bnd[0] + i * (bnd[2]-bnd[0])/n_floors)
        xmax_v = float(existing.xmax if existing else bnd[0] + (i+1) * (bnd[2]-bnd[0])/n_floors)
        xmin = st.number_input(f"X 최소 (m)", value=xmin_v, key=f"xmin_{i}", format="%.2f")
        xmax = st.number_input(f"X 최대 (m)", value=xmax_v, key=f"xmax_{i}", format="%.2f")
        cx_v = float(existing.courtyard_center[0] if (existing and existing.courtyard_center) else (xmin+xmax)/2)
        cy_v = float(existing.courtyard_center[1] if (existing and existing.courtyard_center) else (bnd[1]+bnd[3])/2)
        cx = st.number_input(f"중정 X (m)", value=cx_v, key=f"cx_{i}", format="%.3f")
        cy = st.number_input(f"중정 Y (m)", value=cy_v, key=f"cy_{i}", format="%.3f")
        cr = st.number_input(f"중정 반지름 (m)", value=float(existing.courtyard_radius_m if existing else 4.0),
                             key=f"cr_{i}", format="%.2f")
        floor_configs.append(FloorBounds(level_id=lid, label=label,
                                         xmin=xmin, ymin=bnd[1], xmax=xmax, ymax=bnd[3],
                                         courtyard_center=(cx, cy), courtyard_radius_m=cr))

if st.button("층 설정 저장", type="primary"):
    proj.floors = floor_configs
    st.success(f"{len(proj.floors)}개 층 저장 완료")

# ── 층별 미리보기 ─────────────────────────────────────────────
if proj.floors:
    st.subheader("층별 미리보기")
    sel_floor = st.selectbox("층 선택", [f.label for f in proj.floors])
    floor = next((f for f in proj.floors if f.label == sel_floor), None)
    if floor and st.button("층 미리보기 생성", key="preview_floor"):
        with st.spinner("렌더링 중..."):
            floor_ents = filter_by_x_range(vis_entities, floor.xmin, floor.xmax, scale)
            fig, ax = plt.subplots(figsize=(8, 8))
            for e in floor_ents[:5000]:
                from core.dxf_loader import entity_to_linestring
                ls = entity_to_linestring(e, scale)
                if ls and not ls.is_empty:
                    try:
                        xs, ys = ls.xy
                        ax.plot(xs, ys, "-", color="#555", lw=0.6)
                    except Exception:
                        pass
            if floor.courtyard_center:
                import math
                theta = np.linspace(0, 2*math.pi, 64)
                cx, cy = floor.courtyard_center
                r = floor.courtyard_radius_m
                ax.plot(cx + r*np.cos(theta), cy + r*np.sin(theta),
                        ":", color="#17BECF", lw=2, label="중정 경계")
                ax.plot(cx, cy, "+", color="#17BECF", ms=12)
                ax.legend()
            ax.set_aspect("equal")
            ax.set_title(f"{floor.label} 평면")
            ax.grid(True, alpha=0.2)
            fig.tight_layout()
            buf = io.BytesIO()
            fig.savefig(buf, dpi=120, facecolor="white")
            plt.close(fig)
            st.image(buf.getvalue(), use_container_width=True)
