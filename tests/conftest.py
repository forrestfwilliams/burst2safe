from datetime import datetime
from pathlib import Path

import asf_search
import pytest

from burst2safe.utils import BurstInfo


TEST_DIR = Path(__file__).parent


def pytest_configure(config):
    config.addinivalue_line('filterwarnings', 'ignore::RuntimeWarning')


@pytest.fixture
def test_data_dir():
    return TEST_DIR / 'test_data'


# @pytest.fixture
# def test_data_xml(test_data_dir):
#     return test_data_dir / 'S1A_IW_SLC__1SDV_20200604T022251_20200604T022318_032861_03CE65_7C85_VV.xml'


@pytest.fixture
def test_data1_xml(test_data_dir):
    return test_data_dir / 'S1A_IW_SLC__1SDV_20240408T015045_20240408T015113_053336_06778C_CB5D_VV.xml'


@pytest.fixture
def test_data2_xml(test_data_dir):
    return test_data_dir / 'S1A_IW_SLC__1SDV_20240408T015111_20240408T015138_053336_06778C_CA9A_VV.xml'


@pytest.fixture
def xsd_dir():
    xsd_dir = Path(__file__).parent.parent / 'src' / 'burst2safe' / 'data' / 'support_340'
    return xsd_dir


@pytest.fixture
def search_result1():
    product = asf_search.ASFProduct()
    product.umm = {'InputGranules': ['S1A_IW_SLC__1SDV_20200604T022251_20200604T022318_032861_03CE65_7C85']}
    product.properties.update(
        {
            'fileID': 'S1_136231_IW2_20200604T022312_VV_7C85-BURST',
            'flightDirection': 'ascending',
            'polarization': 'vv',
            'orbit': 123,
            'url': 'https://example.com/foo.zip',
            'additionalUrls': ['https://example.com/foo.xml'],
            'burst': {
                'subswath': 'IW2',
                'relativeBurstID': 123456,
                'burstIndex': 7,
            },
        }
    )
    # If an ASFSearchResults object is needed, uncomment the following lines:
    # results = asf_search.ASFSearchResults([product])
    # results.searchComplete = True
    return product


@pytest.fixture
def burst_info1(test_data1_xml):
    burst_info = BurstInfo(
        granule='S1_135526_IW2_20240408T015108_VV_CB5D-BURST',
        slc_granule='S1A_IW_SLC__1SDV_20240408T015045_20240408T015113_053336_06778C_CB5D',
        swath='IW2',
        polarization='VV',
        burst_id=135526,
        burst_index=8,
        direction='ASCENDING',
        absolute_orbit=53336,
        date=datetime(2024, 4, 8, 1, 51, 8),
        data_url='https://sentinel1-burst.asf.alaska.edu/S1A_IW_SLC__1SDV_20240408T015045_20240408T015113_053336_06778C_CB5D/IW2/VV/8.tiff',
        data_path=Path(''),
        metadata_url='https://sentinel1-burst.asf.alaska.edu/S1A_IW_SLC__1SDV_20240408T015045_20240408T015113_053336_06778C_CB5D/IW2/VV/8.xml',
        metadata_path=test_data1_xml,
        start_utc=datetime(2024, 4, 8, 1, 51, 8, 355601),
        stop_utc=datetime(2024, 4, 8, 1, 51, 11, 453324),
        length=1508,
        width=25470,
    )
    return burst_info


@pytest.fixture
def burst_info2(test_data2_xml):
    burst_info = BurstInfo(
        granule='S1_135527_IW2_20240408T015111_VV_CA9A-BURST',
        slc_granule='S1A_IW_SLC__1SDV_20240408T015111_20240408T015138_053336_06778C_CA9A',
        swath='IW2',
        polarization='VV',
        burst_id=135527,
        burst_index=0,
        direction='ASCENDING',
        absolute_orbit=53336,
        date=datetime(2024, 4, 8, 1, 51, 11),
        data_url='https://sentinel1-burst.asf.alaska.edu/S1A_IW_SLC__1SDV_20240408T015111_20240408T015138_053336_06778C_CA9A/IW2/VV/0.tiff',
        data_path=Path(''),
        metadata_url='https://sentinel1-burst.asf.alaska.edu/S1A_IW_SLC__1SDV_20240408T015111_20240408T015138_053336_06778C_CA9A/IW2/VV/0.xml',
        metadata_path=test_data2_xml,
        start_utc=datetime(2024, 4, 8, 1, 51, 11, 107991),
        stop_utc=datetime(2024, 4, 8, 1, 51, 14, 205714),
        length=1508,
        width=25470,
    )
    return burst_info


@pytest.fixture
def burst_infos(burst_info1, burst_info2):
    return [burst_info1, burst_info2]
