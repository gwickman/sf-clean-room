import pytest

from sf_clean_room.publish import PublishError, SENTINEL_NAME, publish


def _make_temp_tree(tmp_path):
    tdir = tmp_path / "temp_run"
    tdir.mkdir()
    (tdir / "classes").mkdir()
    (tdir / "classes" / "Foo.cls").write_text("public class Foo {}", encoding="utf-8")
    (tdir / "objects").mkdir()
    (tdir / "objects" / "Account.object").write_text("<Object/>", encoding="utf-8")
    (tdir / SENTINEL_NAME).write_text("<Package/>", encoding="utf-8")
    return tdir


def test_publish_places_sentinel_last(monkeypatch, tmp_path):
    tdir = _make_temp_tree(tmp_path)
    pdir = tmp_path / "publish"

    import sf_clean_room.publish as pub_mod

    moves: list[str] = []
    real_move = pub_mod.shutil.move

    def tracking_move(src, dst, *args, **kwargs):
        moves.append(str(dst))
        return real_move(src, dst, *args, **kwargs)

    monkeypatch.setattr(pub_mod.shutil, "move", tracking_move)

    publish(tdir, pdir)

    # Last move must be the sentinel.
    assert moves, "expected at least one move"
    assert moves[-1].endswith(SENTINEL_NAME), f"sentinel was not last: {moves}"
    # And it must exist at the publish path now.
    assert (pdir / SENTINEL_NAME).exists()
    assert (pdir / "classes" / "Foo.cls").exists()


def test_publish_clears_existing_contents(tmp_path):
    tdir = _make_temp_tree(tmp_path)
    pdir = tmp_path / "publish"
    pdir.mkdir()
    (pdir / "stale.txt").write_text("old", encoding="utf-8")
    (pdir / "olddir").mkdir()
    (pdir / "olddir" / "x.txt").write_text("old", encoding="utf-8")

    publish(tdir, pdir)

    assert not (pdir / "stale.txt").exists()
    assert not (pdir / "olddir").exists()
    assert (pdir / SENTINEL_NAME).exists()


def test_missing_sentinel_aborts_without_touching_publish_path(tmp_path):
    tdir = tmp_path / "temp_run"
    tdir.mkdir()
    (tdir / "classes").mkdir()
    (tdir / "classes" / "Foo.cls").write_text("x", encoding="utf-8")
    # NO package.xml in tdir.

    pdir = tmp_path / "publish"
    pdir.mkdir()
    (pdir / "previous.txt").write_text("keep me", encoding="utf-8")

    with pytest.raises(PublishError):
        publish(tdir, pdir)

    # Old content must still be there — publish path must not be cleared.
    assert (pdir / "previous.txt").read_text(encoding="utf-8") == "keep me"


def test_publish_path_is_created_if_missing(tmp_path):
    tdir = _make_temp_tree(tmp_path)
    pdir = tmp_path / "does" / "not" / "exist"
    publish(tdir, pdir)
    assert pdir.exists()
    assert (pdir / SENTINEL_NAME).exists()
