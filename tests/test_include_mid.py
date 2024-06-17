import lxml.etree as ET
import pytest

from burst2safe.burst2safe import burst2safe


@pytest.mark.integration()
def test_include_mid(tmp_path):
    safe_path = burst2safe(
        granules=['S1_088916_IW3_20240605T140826_VV_36F4-BURST'], include_mid=True, work_dir=tmp_path
    )
    products = list((safe_path / 'annotation').glob('*.xml'))
    assert len(products) == 2

    iw2_product = [p for p in products if 'iw2' in p.name][0]
    iw2_xml = ET.parse(iw2_product).getroot()

    burst_list = iw2_xml.find('.//burstList')
    assert burst_list.attrib['count'] == '0'
    assert len(burst_list) == 0

    geolocation_grid = iw2_xml.find('.//geolocationGridPointList')
    assert geolocation_grid.attrib['count'] == '0'
    assert len(geolocation_grid) == 0


@pytest.mark.integration()
def test_include_mid_ignore(tmp_path):
    safe_path = burst2safe(
        granules=['S1_088916_IW2_20240605T140825_VV_36F4-BURST'], include_mid=True, work_dir=tmp_path
    )
    products = list((safe_path / 'annotation').glob('*.xml'))
    assert len(products) == 1

    iw2_product = [p for p in products if 'iw2' in p.name][0]
    iw2_xml = ET.parse(iw2_product).getroot()

    burst_list = iw2_xml.find('.//burstList')
    assert burst_list.attrib['count'] == '1'
    assert len(burst_list) == 1

    geolocation_grid = iw2_xml.find('.//geolocationGridPointList')
    assert int(geolocation_grid.attrib['count']) > 0
    assert len(geolocation_grid) > 0
