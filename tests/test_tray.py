from unittest.mock import Mock, patch

import requests

from backend import tray


@patch("backend.tray.subprocess.Popen")
@patch("backend.tray.shutil.which", return_value="C:/Edge/msedge.exe")
def test_open_jarvis_uses_edge_app_mode(
    mock_which: Mock, mock_popen: Mock
) -> None:
    tray.open_jarvis(Mock(), Mock())

    mock_popen.assert_called_once_with(
        ["C:/Edge/msedge.exe", "--app=http://127.0.0.1:8000"],
        cwd=tray.PROJECT_ROOT,
        creationflags=tray.CREATE_NO_WINDOW,
    )


@patch("backend.tray.webbrowser.open")
@patch("backend.tray.shutil.which", return_value=None)
def test_open_jarvis_falls_back_to_default_browser(
    mock_which: Mock, mock_browser: Mock
) -> None:
    tray.open_jarvis(Mock(), Mock())

    mock_browser.assert_called_once_with("http://127.0.0.1:8000")


@patch("backend.tray.requests.post")
def test_pause_and_resume_listening_update_menu_state(mock_post: Mock) -> None:
    mock_post.side_effect = [
        Mock(json=Mock(return_value={"listening": False})),
        Mock(json=Mock(return_value={"listening": True})),
    ]

    tray._listening_paused = False
    tray.toggle_listening(Mock(), Mock())
    assert tray._listening_paused
    tray.toggle_listening(Mock(), Mock())
    assert not tray._listening_paused

    assert mock_post.call_count == 2
    mock_post.assert_any_call("http://127.0.0.1:8000/api/listening", timeout=2)


@patch("backend.tray.requests.post")
def test_quit_requests_shutdown_and_stops_tray(mock_post: Mock) -> None:
    icon = Mock()

    tray.quit_jarvis(icon, Mock())

    mock_post.assert_called_once_with(
        "http://127.0.0.1:8000/api/shutdown", timeout=2
    )
    icon.stop.assert_called_once_with()


@patch("backend.tray.requests.post", side_effect=requests.ConnectionError("offline"))
def test_quit_stops_tray_even_when_server_is_unreachable(mock_post: Mock) -> None:
    icon = Mock()

    tray.quit_jarvis(icon, Mock())

    icon.stop.assert_called_once_with()
