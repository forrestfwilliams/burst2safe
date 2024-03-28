from copy import deepcopy
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch

import lxml.etree as ET

from burst2safe import utils
from helpers import create_test_geotiff


def test_add_shape_info(tmp_path, burst_info1):
    tmp_tiff = tmp_path / 'tmp.tiff'
    create_test_geotiff(tmp_tiff, dtype='float', shape=(10, 10, 1))
    tmp_burst = deepcopy(burst_info1)
    tmp_burst.data_path = tmp_tiff
    tmp_burst.add_shape_info()
    assert tmp_burst.length == 10
    assert tmp_burst.width == 10


def test_add_start_stop_utc(burst_info1):
    test_elem = ET.Element('product')
    az_time_interval = ET.SubElement(test_elem, 'azimuthTimeInterval')
    az_time_interval.text = '0.01'
    start = datetime.fromisoformat('2020-01-01T00:00:00')
    for i in range(9):
        burst_elem = ET.SubElement(test_elem, 'burst')
        az_time = ET.SubElement(burst_elem, 'azimuthTime')
        burst_time = (start + timedelta(seconds=i * 5)).isoformat()
        az_time.text = burst_time

    with patch('burst2safe.utils.get_subxml_from_metadata', return_value=test_elem):
        tmp_burst = deepcopy(burst_info1)
        tmp_burst.burst_index = 2
        tmp_burst.length = 10
        tmp_burst.add_start_stop_utc()
        assert tmp_burst.start_utc == datetime.fromisoformat('2020-01-01T00:00:10')
        assert tmp_burst.stop_utc == datetime.fromisoformat('2020-01-01T00:00:10.09')


def test_optional_wd():
    wd = utils.optional_wd()
    assert isinstance(wd, Path)
    assert wd == Path.cwd()

    existing_dir = 'working'
    wd = utils.optional_wd(existing_dir)
    assert isinstance(wd, Path)
    assert wd == Path(existing_dir)
