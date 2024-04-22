import shutil
from pathlib import Path

import asf_search
import pytest

from burst2safe.safe import Safe
from burst2safe.utils import get_burst_infos
from helpers import create_test_geotiff, validate_xml


BURSTS = [
    ('2.36', 'S1_249405_IW2_20150117T170523_VV_AE35-BURST'),
    ('2.45', 'S1_249405_IW2_20150622T170528_VV_EFBC-BURST'),
    ('2.60', 'S1_249405_IW2_20160124T170529_VV_7CC5-BURST'),
    ('2.90', 'S1_249405_IW2_20180507T170501_VV_6B12-BURST'),
    ('3.40', 'S1_249405_IW2_20211223T170608_VV_B8E2-BURST'),
    ('3.71', 'S1_249405_IW2_20240130T170617_VV_9A35-BURST'),
]


@pytest.mark.integration()
@pytest.mark.parametrize('version,burst', BURSTS)
def test_versions(version, burst, tmp_path):
    products = asf_search.granule_search([burst])
    burst_infos = get_burst_infos(products, tmp_path)

    ipf_dir = Path(__file__).parent / 'test_data' / 'ipf'
    shutil.copy(ipf_dir / burst_infos[0].metadata_path.name, burst_infos[0].metadata_path)

    [info.add_shape_info() for info in burst_infos]
    [info.add_start_stop_utc() for info in burst_infos]

    create_test_geotiff(burst_infos[0].data_path, 'cfloat', shape=(burst_infos[0].length, burst_infos[0].width, 1))
    safe = Safe(burst_infos, tmp_path)
    safe.create_safe()

    # TODO: switch XSD dir to the one in the safe
    xsd_dir = Path(__file__).parent.parent / 'src' / 'burst2safe' / 'data' / f'support_{version.replace(".", "")}'
    for swath in safe.swaths:
        validate_xml(swath.product.path, xsd_dir / 's1-level-1-product.xsd')
        validate_xml(swath.noise.path, xsd_dir / 's1-level-1-noise.xsd')
        validate_xml(swath.calibration.path, xsd_dir / 's1-level-1-calibration.xsd')
        if swath.has_rfi:
            validate_xml(swath.rfi.path, xsd_dir / 's1-level-1-rfi.xsd')
