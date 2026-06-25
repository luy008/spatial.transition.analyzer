"""사이드바에 Analysis Mode UI가 없음을 검증하는 테스트."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pathlib import Path

ROOT = Path(__file__).parent.parent

ACTIVE_PY_DIRS = [
    ROOT / "pages",
    ROOT / "utils",
    ROOT,  # app.py
]

FORBIDDEN_LABELS = [
    "Analysis Mode",
    "Task Mode",
    "New Design Analysis",
    "과제 모드",
    "새 설계 분석",
    "새 설계 분석",
]

OBSOLETE_STATE_KEYS = [
    "analysis_mode",
    "task_mode",
]


def _collect_source_lines() -> list[tuple[str, int, str]]:
    """Return (file, lineno, line) for all active Python files."""
    hits = []
    for directory in ACTIVE_PY_DIRS:
        for py in directory.glob("*.py"):
            for lineno, text in enumerate(py.read_text(encoding="utf-8-sig").splitlines(), 1):
                hits.append((str(py.relative_to(ROOT)), lineno, text))
    return hits


def test_no_forbidden_mode_labels_in_source():
    """Active source files must not contain Analysis Mode / Task Mode labels."""
    lines = _collect_source_lines()
    violations = []
    for fpath, lineno, text in lines:
        for label in FORBIDDEN_LABELS:
            if label in text:
                violations.append(f"{fpath}:{lineno}: {text.strip()!r}")
    assert not violations, "금지 레이블 발견:\n" + "\n".join(violations)


def test_no_st_radio_in_sidebar():
    """sidebar.py must not contain any st.radio call."""
    sidebar = (ROOT / "utils" / "sidebar.py").read_text(encoding="utf-8-sig")
    assert ".radio(" not in sidebar, "sidebar.py에 st.radio() 호출이 남아 있음"


def test_obsolete_keys_popped_in_init_session():
    """init_session() must pop all obsolete mode keys."""
    sidebar_src = (ROOT / "utils" / "sidebar.py").read_text(encoding="utf-8-sig")
    for key in OBSOLETE_STATE_KEYS:
        assert f'"{key}"' in sidebar_src or f"'{key}'" in sidebar_src, (
            f"init_session()이 레거시 키 {key!r}를 pop하지 않음"
        )


def test_no_set_page_config_in_pages():
    """Page files must not call st.set_page_config (handled by app.py only)."""
    for py in (ROOT / "pages").glob("*.py"):
        src = py.read_text(encoding="utf-8-sig")
        assert "set_page_config" not in src, (
            f"{py.name}에 set_page_config 호출이 남아 있음 (app.py에서만 호출해야 함)"
        )
