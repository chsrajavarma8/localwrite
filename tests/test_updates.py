from localwrite.core import ollama_updates as u


def test_version_compare():
    assert u.is_newer("0.40.17", "0.40.15")
    assert u.is_newer("v1.0", "0.99.9")
    assert not u.is_newer("0.40.15", "0.40.15")
    assert not u.is_newer("0.40", "0.40.0")
    assert not u.is_newer("garbage", "0.1")


def test_local_log_detection(tmp_path):
    (tmp_path / "app.log").write_text(
        'msg="New update available at https://github.com/ollama/ollama/releases/download/v0.40.17/OllamaSetup.exe"\n')
    (tmp_path / "app-1.log").write_text(
        'msg="New update available at https://github.com/ollama/ollama/releases/download/v0.40.10/OllamaSetup.exe"\n')
    assert u.latest_from_local_logs(tmp_path) == "0.40.17"
    info = u.check_for_update("0.40.15", online=False, log_dir=tmp_path)
    assert info == u.UpdateInfo("0.40.15", "0.40.17", "local")
    assert u.check_for_update("0.40.17", online=False, log_dir=tmp_path) is None


def test_online_check_is_opt_in(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(u, "latest_from_github", lambda timeout=5.0: calls.append(1) or "9.9.9")
    assert u.check_for_update("0.40.15", online=False, log_dir=tmp_path) is None
    assert calls == []  # no network access unless the user opted in
    info = u.check_for_update("0.40.15", online=True, log_dir=tmp_path)
    assert info.latest == "9.9.9" and info.source == "online"


def test_missing_ollama_folder_is_fine(tmp_path):
    assert u.latest_from_local_logs(tmp_path / "nope") is None
