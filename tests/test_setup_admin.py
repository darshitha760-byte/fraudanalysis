import subprocess
import sys
from pathlib import Path


def test_setup_admin_script_can_be_invoked_directly():
    project_root = Path(__file__).resolve().parents[1]
    script_path = project_root / "scripts" / "setup_admin.py"

    result = subprocess.run(
        [sys.executable, str(script_path), "--help"],
        cwd=project_root,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert "Create Admin User" in result.stdout
