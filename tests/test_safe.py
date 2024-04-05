from collections import namedtuple

import pytest
from shapely.geometry import Polygon

from burst2safe.safe import Safe


class TestSafe:
    def test_init(self, burst_infos, tmp_path):
        safe = Safe(burst_infos, work_dir=tmp_path)
        assert safe.burst_infos == burst_infos
        assert safe.work_dir == tmp_path
        assert safe.swaths == []

    def test_check_group_validity(self):
        BurstStub = namedtuple('BurstStub', ['granule', 'absolute_orbit', 'swath', 'polarization', 'burst_id'])
        burst1 = BurstStub(granule='S1A_20210101_1_VV', absolute_orbit=1, swath='IW1', polarization='VV', burst_id=1)
        burst3 = BurstStub(granule='S1A_20210101_1_VH', absolute_orbit=1, swath='IW1', polarization='VH', burst_id=1)
        burst5 = BurstStub(granule='S1A_20210101_2_VV', absolute_orbit=1, swath='IW1', polarization='VV', burst_id=2)
        burst6 = BurstStub(granule='S1A_20210101_2_VH', absolute_orbit=1, swath='IW1', polarization='VH', burst_id=2)

        burst2 = BurstStub(granule='S1A_20210101_1_VV', absolute_orbit=1, swath='IW2', polarization='VV', burst_id=1)
        burst4 = BurstStub(granule='S1A_20210101_1_VH', absolute_orbit=1, swath='IW2', polarization='VH', burst_id=1)

        Safe.check_group_validity([burst1, burst2, burst3, burst4])

        burst_start = BurstStub(
            granule='S1A_IW_SLC_20210101_0_VH', absolute_orbit=1, swath='IW1', polarization='VH', burst_id=0
        )
        different_polarization_starts = [burst_start, burst1, burst3, burst5, burst6]
        with pytest.raises(ValueError, match='Polarization groups in swath .* start burst id.*'):
            Safe.check_group_validity(different_polarization_starts)

        burst_end = BurstStub(
            granule='S1A_IW_SLC_20210101_3_VH', absolute_orbit=1, swath='IW1', polarization='VH', burst_id=3
        )
        different_polarization_ends = [burst1, burst3, burst5, burst6, burst_end]
        with pytest.raises(ValueError, match='Polarization groups in swath .* end burst id.*'):
            Safe.check_group_validity(different_polarization_ends)

        swath_nonoverlap = [burst1, BurstStub(*burst2._replace(burst_id=3))]
        with pytest.raises(ValueError, match='Products from swaths IW1 and IW2 do not overlap'):
            Safe.check_group_validity(swath_nonoverlap)

    def test_get_name(self, burst_infos, tmp_path):
        safe = Safe(burst_infos, work_dir=tmp_path)
        golden_name = 'S1A_IW_SLC__1SSV_20200604T022312_20200604T022315_032861_03CE65_0000.SAFE'
        assert safe.get_name(safe.burst_infos) == golden_name

    def test_group_burst_infos(self):
        BurstStub = namedtuple('BurstStub', ['swath', 'polarization', 'burst_id'])
        burst1 = BurstStub(swath='IW1', polarization='VV', burst_id=1)
        burst2 = BurstStub(swath='IW1', polarization='VH', burst_id=1)
        burst3 = BurstStub(swath='IW1', polarization='VV', burst_id=2)
        burst4 = BurstStub(swath='IW1', polarization='VH', burst_id=2)
        burst5 = BurstStub(swath='IW2', polarization='VV', burst_id=1)
        burst6 = BurstStub(swath='IW2', polarization='VH', burst_id=1)
        burst7 = BurstStub(swath='IW2', polarization='VV', burst_id=2)
        burst8 = BurstStub(swath='IW2', polarization='VH', burst_id=2)

        burst_info_stubs = [burst1, burst2, burst3, burst4, burst5, burst6, burst7, burst8]
        grouped = Safe.group_burst_infos(burst_info_stubs)
        assert grouped['IW1']['VV'] == [burst1, burst3]
        assert grouped['IW1']['VH'] == [burst2, burst4]
        assert grouped['IW2']['VV'] == [burst5, burst7]
        assert grouped['IW2']['VH'] == [burst6, burst8]

    def test_get_bbox(self, burst_infos, tmp_path):
        safe = Safe(burst_infos, work_dir=tmp_path)

        polygon1 = Polygon([(1, 1), (1, 2), (2, 2), (2, 1), (1, 1)])
        polygon2 = Polygon([(2, 2), (2, 3), (3, 3), (3, 2), (2, 2)])
        polygon_merged = Polygon([(1, 1), (1, 3), (3, 3), (3, 1), (1, 1)])

        SwathStub = namedtuple('SwathStub', ['bbox'])
        safe.swaths = [SwathStub(polygon1), SwathStub(polygon2)]
        bbox = safe.get_bbox()
        assert bbox == polygon_merged

    def test_create_dir_structure(self, burst_infos, tmp_path):
        safe = Safe(burst_infos, work_dir=tmp_path)
        safe.create_dir_structure()
        assert safe.safe_path == tmp_path / safe.get_name(safe.burst_infos)
        assert (safe.safe_path / 'measurement').exists()
        assert (safe.safe_path / 'annotation').exists()
        assert (safe.safe_path / 'annotation' / 'calibration').exists()
        assert (safe.safe_path / 'support').exists()
        assert len(list((safe.safe_path / 'support').glob('*'))) == 5
