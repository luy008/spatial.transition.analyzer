"""depthmapX CLI 어댑터 — 선택 기능. 미설치 시 앱 중단 안 함."""
from __future__ import annotations
import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Optional, Tuple, List, Dict


CANDIDATE_NAMES = ["depthmapXcli.exe", "depthmapXcli", "depthmapX.exe", "depthmapX"]
CANDIDATE_DIRS = [
    Path(__file__).parent.parent / "tools" / "depthmapX",
    Path(__file__).parent.parent / "tools",
    Path(os.environ.get("DEPTHMAPX_PATH", ".")),
]


def find_depthmapx_cli() -> Optional[Path]:
    for name in CANDIDATE_NAMES:
        found = shutil.which(name)
        if found:
            return Path(found)
    for d in CANDIDATE_DIRS:
        for name in CANDIDATE_NAMES:
            p = d / name
            if p.exists():
                return p
    return None


def get_cli_help(cli: Path) -> str:
    try:
        r = subprocess.run([str(cli), "--help"], capture_output=True, text=True, timeout=10)
        return r.stdout + r.stderr
    except Exception as e:
        return str(e)


def is_available() -> Tuple[bool, str]:
    cli = find_depthmapx_cli()
    if cli is None:
        return False, "depthmapX CLI를 찾을 수 없습니다. tools/depthmapX/ 폴더에 설치하거나 PATH에 추가하세요."
    return True, str(cli)


def run_isovist(dxf_path: str, observer_points: List[Tuple[float, float]],
                cli_path: Optional[Path] = None) -> Tuple[bool, str, Optional[List[Dict]]]:
    """depthmapX CLI로 Isovist 계산. 결과 CSV 파싱 후 반환."""
    cli = cli_path or find_depthmapx_cli()
    if cli is None:
        return False, "depthmapX를 찾을 수 없습니다.", None
    help_text = get_cli_help(cli)
    # 도움말에서 사용 가능한 명령 확인
    has_isovist = "ISOVIST" in help_text.upper()
    has_vga = "VGA" in help_text.upper()
    if not (has_isovist or has_vga):
        return False, f"이 버전의 depthmapX에서 Isovist/VGA를 지원하지 않을 수 있습니다.\n도움말:\n{help_text[:500]}", None
    # 임시 디렉토리에서 실행
    with tempfile.TemporaryDirectory() as tmpdir:
        out_file = Path(tmpdir) / "result.csv"
        cmd = [str(cli), "-f", dxf_path, "-o", str(out_file), "-m", "ISOVIST"]
        try:
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
            if r.returncode != 0:
                return False, f"depthmapX 오류:\n{r.stderr[:1000]}", None
            if out_file.exists():
                import csv
                rows = []
                with open(out_file, encoding="utf-8", errors="replace") as f:
                    for row in csv.DictReader(f):
                        rows.append(dict(row))
                return True, "완료", rows
            return False, "결과 파일이 생성되지 않았습니다.", None
        except subprocess.TimeoutExpired:
            return False, "depthmapX 실행 시간 초과 (120초).", None
        except Exception as e:
            return False, str(e), None
