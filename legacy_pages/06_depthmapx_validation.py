"""TAB 6 — DEPTHMAPX: 선택적 교차 검증 (미설치 시 앱 중단 안 함)."""
import sys
from pathlib import Path
ROOT = Path(__file__).parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import streamlit as st
from core.depthmapx_adapter import is_available, find_depthmapx_cli, get_cli_help

st.set_page_config(page_title="depthmapX — STA", layout="wide")
st.title("🔧 06. DEPTHMAPX VALIDATION (선택)")

available, msg = is_available()

if not available:
    st.warning(f"""
**depthmapX CLI가 설치되지 않았습니다.**

현재 앱의 자체 Isovist 분석은 계속 정상 사용할 수 있습니다.

depthmapX를 사용하려면:
1. [depthmapX GitHub](https://github.com/SpaceGroupUCL/depthmapX) 에서 다운로드
2. 실행파일(`depthmapXcli.exe`)을 다음 경로에 배치:
   - `{ROOT}/tools/depthmapX/depthmapXcli.exe`
   - 또는 시스템 PATH에 추가
3. 이 페이지를 새로 고침하면 자동 인식됩니다.
""")
    st.info("🔬 자체 Isovist 분석은 05 ANALYSIS 탭에서 사용하세요.")
    st.stop()

st.success(f"depthmapX 감지됨: `{msg}`")
cli = find_depthmapx_cli()
help_text = get_cli_help(cli) if cli else ""
with st.expander("CLI 도움말"):
    st.code(help_text[:2000])

st.subheader("depthmapX Isovist 교차 검증")
if not st.session_state.get("project"):
    st.warning("01 PROJECT에서 프로젝트를 여세요.")
    st.stop()

proj = st.session_state.project
if not proj.source_file or not Path(proj.source_file).exists():
    st.warning("도면 파일이 없습니다.")
    st.stop()

from core.depthmapx_adapter import run_isovist
from core.ramp_analysis import build_circular_ramp_centerline
from shapely.geometry import Point

route_id = st.selectbox("검증할 경로", [r.route_id for r in proj.routes] or ["없음"])
route = next((r for r in proj.routes if r.route_id == route_id), None)

if route and st.button("depthmapX 교차 검증 실행"):
    obs_pts = []
    if route.is_circular and route.circular_center:
        cl = build_circular_ramp_centerline(
            Point(*route.circular_center), route.circular_radius_m,
            route.circular_start_angle_deg, route.direction, route.circular_rotation_deg)
        n = 5
        obs_pts = [(cl.interpolate(i/(n-1), normalized=True).x,
                    cl.interpolate(i/(n-1), normalized=True).y) for i in range(n)]
    with st.spinner("depthmapX 실행 중 (최대 2분)..."):
        ok, msg2, rows = run_isovist(proj.source_file, obs_pts, cli)
    if ok:
        import pandas as pd
        st.success("검증 완료")
        if rows:
            st.dataframe(pd.DataFrame(rows[:20]))
        # 자체 분석과 비교
        iso_key = f"iso_{route_id}"
        self_data = st.session_state.analysis_results.get(iso_key, {})
        if self_data:
            st.info("자체 분석 결과와 비교하려면 면적 값을 확인하세요. "
                    "depthmapX 결과를 절대적 정답으로 취급하지 마세요 — "
                    "벽·커튼월·개구부 분류 차이에 따라 수치가 달라질 수 있습니다.")
        else:
            st.info("05 ANALYSIS에서 먼저 자체 Isovist 분석을 실행하면 비교 가능합니다.")
    else:
        st.error(f"depthmapX 실패: {msg2}")
