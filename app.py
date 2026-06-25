"""Spatial Transition Analyzer — 건축 동선 전환 분석기
메인 진입점. 실행: streamlit run app.py
"""
import sys
from pathlib import Path

ROOT = Path(__file__).parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import streamlit as st
from utils.sidebar import init_session, render_sidebar

st.set_page_config(
    page_title="Spatial Transition Analyzer",
    page_icon="🏛",
    layout="wide",
    initial_sidebar_state="expanded",
)

init_session()

# 사이드바: 제목 + 프로젝트/상태 정보
with st.sidebar:
    st.markdown("## 공간 전이 분석기")
    st.markdown("---")

render_sidebar()

# 한글 페이지명 내비게이션
pg = st.navigation([
    st.Page("pages/01_input.py",         title="01 입력",             icon="📋"),
    st.Page("pages/02_verify_analyze.py", title="02 검증 및 분석",    icon="🔍"),
    st.Page("pages/03_diagram_export.py", title="03 다이어그램 및 내보내기", icon="📊"),
])
pg.run()
