"""depthmapX 어댑터 — 설치 없이도 앱이 정상 작동하는지 확인."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.depthmapx_adapter import is_available, find_depthmapx_cli


def test_is_available_returns_tuple():
    result = is_available()
    assert isinstance(result, tuple)
    assert len(result) == 2
    available, msg = result
    assert isinstance(available, bool)
    assert isinstance(msg, str)


def test_find_cli_returns_none_or_path():
    cli = find_depthmapx_cli()
    assert cli is None or isinstance(cli, str)


def test_unavailable_does_not_crash():
    available, msg = is_available()
    if not available:
        assert "찾을 수 없음" in msg or "not found" in msg.lower() or len(msg) > 0
