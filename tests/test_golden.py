import filecmp
import shutil
import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest
from shapely import box

from burst2safe.burst2safe import burst2safe


def bit_for_bit(reference: Path, secondary: Path):
    filecmp.clear_cache()
    return filecmp.cmp(reference, secondary, shallow=False)


@pytest.mark.golden()
def test_burst2safe():
    branch = subprocess.check_output(['git', 'rev-parse', '--abbrev-ref', 'HEAD']).strip().decode('utf-8')
    work_path = Path.cwd() / branch
    work_path.mkdir(exist_ok=True)
    with patch('burst2safe.measurement.Measurement.get_time_tag') as mock_get_time_tag:
        mock_get_time_tag.return_value = '2024:01:01 00:00:00'
        burst2safe(
            granules=[],
            orbit=51936,
            extent=box(*[-117.3, 35.5, -117.2, 35.6]),
            polarizations=['VV', 'VH'],
            keep_files=False,
            work_dir=work_path,
        )
    shutil.make_archive(work_path, 'tar', work_path)


@pytest.mark.golden()
def test_golden():
    main_branch = 'main'
    develop_branch = 'develop'
    
    work_path = Path.cwd()
    tars = [work_path / f'{main_branch}.tar', work_path / f'{develop_branch}.tar']
    for tar in tars:
        extract_dir = tar.with_suffix('')
        extract_dir.mkdir(exist_ok=True)
        shutil.unpack_archive(tar, extract_dir)

    main_safe = list((work_path / main_branch).glob('*.SAFE'))[0]
    develop_safe = list((work_path / develop_branch).glob('*.SAFE'))[0]
    assert main_safe.name == develop_safe.name

    main_files = sorted([x.resolve() for x in main_safe.rglob('*')])
    develop_files = sorted([x.resolve() for x in develop_safe.rglob('*')])

    main_set = set([f.relative_to(main_safe) for f in main_files])
    develop_set = set([f.relative_to(develop_safe) for f in develop_files])
    
    only_in_main = [str(x) for x in main_set - develop_set]
    assert not only_in_main

    only_in_develop = [str(x) for x in develop_set - main_set]
    assert not only_in_develop

    differing_files = []
    for main_file, develop_file in zip(main_files, develop_files):
        if main_file.is_dir():
            continue

        if not bit_for_bit(main_file, develop_file):
            differing_files.append(develop_file.relative_to(develop_safe))

    differing_files = [str(x) for x in differing_files]
    assert not differing_files
