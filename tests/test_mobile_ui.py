"""Static mobile UI integrity checks; no browser/network access required."""
from pathlib import Path
import re
import shutil
import subprocess
from tempfile import TemporaryDirectory
import pytest

SITE = Path(__file__).resolve().parents[1] / "site" / "index.html"


def test_mobile_ui_controls_exist():
    html = SITE.read_text(encoding="utf-8")
    for item in ["backtestTimePicker", "backtestPeriods", "stockOverlay", "stockGraph",
                 "stockShortcuts", "toggleBot", "renderStock", "regionChips"]:
        assert item in html, f"missing UI: {item}"
    assert "localStorage" in html  # client-only tracking toggles
    assert "actions/workflows/bot-control.yml" in html  # path to authenticated cloud pause


def test_onsite_javascript_parses_under_node():
    node = shutil.which("node")
    if not node:
        pytest.skip("Node.js is not installed on this machine")
    html=SITE.read_text(encoding="utf-8")
    scripts=re.findall(r"<script[^>]*>(.*?)</script>", html, flags=re.S)
    assert len(scripts)==1
    with TemporaryDirectory() as root:
        p=Path(root)/"app.js"
        p.write_text(scripts[0],encoding="utf-8")
        result=subprocess.run([node,"--check",str(p)],capture_output=True,text=True)
        assert result.returncode==0, result.stderr
