from localwrite.core.diff import change_count, compute_diff, render_inline, render_side


def test_diff_basic():
    ops = compute_diff("I has a apple", "I have an apple")
    assert change_count(ops) == 1  # 'has a' -> 'have an' merged into one edit
    orig = render_side(ops, "original")
    corr = render_side(ops, "corrected")
    assert "line-through" in orig and "has a" in orig
    assert "have an" in corr
    assert "apple" in render_inline(ops)


def test_diff_identical_and_escaping():
    ops = compute_diff("<b>same</b>", "<b>same</b>")
    assert change_count(ops) == 0
    assert "&lt;b&gt;" in render_side(ops, "corrected")


def test_diff_newlines_render_as_breaks():
    ops = compute_diff("a\nb", "a\nc")
    assert "<br>" in render_side(ops, "corrected")


def test_no_history_module_exists():
    import importlib.util

    assert importlib.util.find_spec("localwrite.core.history") is None


def test_legacy_history_files_are_purged(tmp_path, monkeypatch):
    from localwrite import paths

    monkeypatch.setenv("LOCALWRITE_HOME", str(tmp_path))
    for name in ("history.db", "history.db-wal", "history.db-shm"):
        (tmp_path / name).write_bytes(b"old text")
    assert paths.purge_legacy_history() == 3
    assert not list(tmp_path.glob("history.db*"))
