from copy import deepcopy

from burst2safe import local2safe


def test_burst_from_local(burst_info1, burst_info2):
    burst_info1_copy = deepcopy(burst_info1)
    burst_info1_copy.granule = ''
    burst_info1_local = local2safe.burst_info_from_local(
        burst_info1.data_path,
        burst_info1.metadata_path,
        burst_info1.slc_granule,
        burst_info1.swath,
        burst_info1.polarization,
        burst_info1.burst_index,
    )
    assert burst_info1_local == burst_info1_copy

    burst_info2_copy = deepcopy(burst_info2)
    burst_info2_copy.granule = ''
    burst_info2_local = local2safe.burst_info_from_local(
        burst_info2.data_path,
        burst_info2.metadata_path,
        burst_info2.slc_granule,
        burst_info2.swath,
        burst_info2.polarization,
        burst_info2.burst_index,
    )
    assert burst_info2_local == burst_info2_copy
