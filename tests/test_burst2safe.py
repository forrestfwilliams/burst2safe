from pathlib import Path

from burst2safe import burst2safe


def test_optional_wd():
    wd = burst2safe.optional_wd()
    assert isinstance(wd, Path)
    assert wd == Path.cwd()

    existing_dir = 'working'
    wd = burst2safe.optional_wd(existing_dir)
    assert isinstance(wd, Path)
    assert wd == Path(existing_dir)
