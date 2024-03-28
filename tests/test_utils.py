from pathlib import Path

from burst2safe import utils


def test_optional_wd():
    wd = utils.optional_wd()
    assert isinstance(wd, Path)
    assert wd == Path.cwd()

    existing_dir = 'working'
    wd = utils.optional_wd(existing_dir)
    assert isinstance(wd, Path)
    assert wd == Path(existing_dir)
