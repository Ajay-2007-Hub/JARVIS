from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_register_script_uses_project_relative_paths_and_limited_task() -> None:
    script = (PROJECT_ROOT / "scripts" / "register_autostart.ps1").read_text(
        encoding="utf-8"
    )

    assert "Join-Path $PSScriptRoot '..'" in script
    assert "Join-Path $ProjectRoot '.venv\\Scripts\\pythonw.exe'" in script
    assert "Join-Path $ProjectRoot 'scripts\\launcher.py'" in script
    assert "-LogonType Interactive" in script
    assert "-RunLevel Limited" in script
    assert "$Trigger.Delay = 'PT30S'" in script
    assert "-RestartCount 3" in script
    assert "-ExecutionTimeLimit ([TimeSpan]::Zero)" in script
    assert "-AllowStartIfOnBatteries" in script
    assert "-DontStopIfGoingOnBatteries" in script


def test_unregister_script_handles_missing_task_without_error() -> None:
    script = (PROJECT_ROOT / "scripts" / "unregister_autostart.ps1").read_text(
        encoding="utf-8"
    )

    assert "-ErrorAction SilentlyContinue" in script
    assert "if ($null -ne $Task)" in script


def test_status_script_reports_enabled_and_last_result() -> None:
    script = (PROJECT_ROOT / "scripts" / "status_autostart.ps1").read_text(
        encoding="utf-8"
    )

    assert "enabled=false" in script
    assert "enabled=true" in script
    assert "last_run_result={0}" in script
