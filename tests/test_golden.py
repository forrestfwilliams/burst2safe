import filecmp
from pathlib import Path
from unittest.mock import patch
from zipfile import ZipFile

import pytest
import requests
from shapely import box

from burst2safe.burst2safe import burst2safe


def bit_for_bit(reference: Path, secondary: Path):
    filecmp.clear_cache()
    return filecmp.cmp(reference, secondary, shallow=False)


def prep_golden_safe(tmp_path: Path):
    golden_url = 'https://ffwilliams2-shenanigans.s3.us-west-2.amazonaws.com/burst2safe/S1A_IW_SLC__1SSV_20240103T015108_20240103T015112_051936_064669_51EE.zip'

    golden_dir = tmp_path / 'golden'
    golden_dir.mkdir(exist_ok=True)

    golden_zip = golden_dir / Path(golden_url).name
    with requests.get(golden_url, stream=True) as r:
        r.raise_for_status()
        with open(golden_zip, 'wb') as f:
            for chunk in r.iter_content(chunk_size=2**22):
                f.write(chunk)

    with ZipFile(golden_zip, 'r') as z:
        z.extractall(golden_dir)

    golden_safe = golden_zip.with_suffix('.SAFE')
    return golden_safe


@pytest.mark.golden()
def test_golden():
    work_path = Path.cwd()
    safe_name = 'S1A_IW_SLC__1SSV_20240103T015108_20240103T015112_051936_064669_51EE.SAFE'
    golden_safe = (work_path / 'golden' / safe_name).resolve()
    new_safe = (work_path / safe_name).resolve()

    prep_golden_safe(work_path)

    with patch('burst2safe.measurement.Measurement.get_time_tag') as mock_get_time_tag:
        mock_get_time_tag.return_value = '2024:01:01 00:00:00'
        burst2safe(
            granules=[],
            orbit=51936,
            footprint=box(*[-117.3, 35.5, -117.2, 35.6]),
            polarizations=['VV', 'VH'],
            keep_files=True,
            work_dir=work_path,
        )

    golden_files = sorted([x.resolve() for x in golden_safe.rglob('*')])
    new_files = sorted([x.resolve() for x in new_safe.rglob('*')])

    golden_set = set([f.relative_to(golden_safe) for f in golden_files])
    new_set = set([f.relative_to(new_safe) for f in new_files])

    only_in_golden = [str(x) for x in golden_set - new_set]
    assert not only_in_golden

    only_in_new = [str(x) for x in new_set - golden_set]
    assert not only_in_new

    differing_files = []
    for golden_file, new_file in zip(golden_files, new_files):
        if golden_file.is_dir():
            continue

        if not bit_for_bit(golden_file, new_file):
            differing_files.append(new_file.relative_to(new_safe))
    differing_files = [str(x) for x in differing_files]
    assert not differing_files
