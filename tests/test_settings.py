import json

from localwrite.config.settings import DEFAULT_HOTKEYS, Settings, SettingsStore


def test_defaults_are_valid():
    s = Settings().validated()
    assert s.ollama_url == "http://localhost:11434"
    assert s.hotkeys == DEFAULT_HOTKEYS
    assert s.realtime_enabled is False  # advanced feature must be opt-in
    assert not hasattr(s, "history_enabled")  # history was removed entirely


def test_roundtrip(tmp_path):
    store = SettingsStore(tmp_path / "s.json")
    s = Settings(model="llama3.2:3b", temperature=0.5, popup_position="center")
    store.save(s)
    loaded = store.load()
    assert loaded.model == "llama3.2:3b"
    assert loaded.temperature == 0.5
    assert loaded.popup_position == "center"


def test_invalid_values_are_clamped():
    s = Settings(temperature=9, timeout_seconds=-4, default_mode="nope",
                 ollama_url="localhost:11434/", popup_position="moon").validated()
    assert s.temperature == 1.5
    assert s.timeout_seconds == 10
    assert s.default_mode == "grammar"
    assert Settings(default_mode="improve").validated().default_mode == "clarity"  # legacy mode mapped


def test_old_settings_file_with_removed_fields_loads(tmp_path):
    import json

    path = tmp_path / "s.json"
    path.write_text(json.dumps({"theme": "dark", "history_enabled": True, "history_limit": 5, "model": "m"}))
    s = SettingsStore(path).load()
    assert s.model == "m"
    SettingsStore(path).save(s)
    saved = json.loads(path.read_text())
    assert "theme" not in saved and "history_enabled" not in saved
    assert s.ollama_url == "http://localhost:11434"
    assert s.popup_position == "smart"


def test_unknown_keys_and_partial_hotkeys(tmp_path):
    path = tmp_path / "s.json"
    path.write_text(json.dumps({"bogus": 1, "hotkeys": {"general": "Ctrl+Shift+G", "evil": "x"}}))
    s = SettingsStore(path).load()
    assert s.hotkeys["general"] == "Ctrl+Shift+G"
    assert s.hotkeys["spelling"] == DEFAULT_HOTKEYS["spelling"]
    assert "evil" not in s.hotkeys


def test_corrupt_file_falls_back_and_backs_up(tmp_path):
    path = tmp_path / "s.json"
    path.write_text("{not json")
    s = SettingsStore(path).load()
    assert s == Settings().validated()
    assert (tmp_path / "s.json.bak").exists()


def test_is_local_server():
    assert Settings(ollama_url="http://127.0.0.1:11434").validated().is_local_server()
    assert not Settings(ollama_url="http://192.168.1.20:11434").validated().is_local_server()
