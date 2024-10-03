"""Generate a SAFE file from local burst extractor outputs"""

import argparse
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

import numpy as np

from burst2safe import utils
from burst2safe.safe import Safe


NOMINAL_ORBITAL_DURATION = timedelta(seconds=12 * 24 * 3600 / 175)
PREAMBLE_LENGTH_IW = timedelta(seconds=2.299849)
PREAMBLE_LENGTH_EW = timedelta(seconds=2.299970)
BEAM_CYCLE_TIME_IW = timedelta(seconds=2.758273)
BEAM_CYCLE_TIME_EW = timedelta(seconds=3.038376)
MODE_TIMING = {'EW': (PREAMBLE_LENGTH_EW, BEAM_CYCLE_TIME_EW), 'IW': (PREAMBLE_LENGTH_IW, BEAM_CYCLE_TIME_IW)}


class InvalidModeNameError(Exception):
    pass


def calc_esa_burstid(
    time_since_anx: timedelta, orbit_number_start: int, preamble_len: timedelta, beam_cycle_time: timedelta
):
    """Calculates the burst ID given these parameters.

    Extracted from the opera function for the purposes of reuse IW & EW

    :param time_since_anx: time since ascending node crossing
    :param orbit_number_start:
    :param preamble_len: Preamble length
    :param beam_cycle_time: Beam cycle time
    :return:

    Args:
        time_since_anx: time since ascending node crossing
        orbit_number_start: The absolute orbit number at the start of the acquisition
        preamble_len: The preamble length
        beam_cycle_time: The beam cycle time

    Returns:
        The ESA burst ID
    """
    # Eq. 9-89: ∆tb = tb − t_anx + (r - 1)T_orb
    # tb: mid-burst sensing time (sensing_time)
    # t_anx: ascending node time (ascending_node_dt)
    # r: relative orbit number   (relative_orbit_start)
    dt_b = time_since_anx + (orbit_number_start - 1) * NOMINAL_ORBITAL_DURATION

    # Eq. 9-91 :   1 + floor((∆tb − T_pre) / T_beam )
    esa_burst_id = 1 + int(np.floor((dt_b - preamble_len) / beam_cycle_time))

    return esa_burst_id


def get_mode_timing(mode_name: str) -> tuple:
    """
    :param mode_name: Mode name (EW,IW) or subswath name (EW2 etc)
    :return: tuple (PREAMBLE_LENGTH, BEAM_CYCLE_TIME,) for passed mode
    """
    try:
        return MODE_TIMING[mode_name[:2].upper()]
    except KeyError as e:
        raise InvalidModeNameError(e)


def calc_start_subsw1(start_offsets: list, swath_num: int, sensing_time: datetime) -> datetime:
    """Calculates the start time of the #1 subswath given any subswath in a burst.

    :param start_offsets: list of start offsets, times since IW1
    :param swath_num: swath number.
    :param sensing_time:
    :return:
    """
    offset = start_offsets[swath_num - 1]
    start_subsw1 = sensing_time + timedelta(seconds=offset)
    return start_subsw1


def calculate_burstid_opera(
    sensing_time: datetime,
    anx_time: datetime,
    orbit_number_start: int,
    orbit_number_stop: int,
    subswath: str,
) -> tuple:
    """Calculate the unique burst ID of a burst. And return the
    correct orbit number.

    Accounts for equator crossing frames, where the current track number of
    a burst may change mid-frame. Uses the ESA convention defined in the
    Sentinel-1 Level 1 Detailed Algorithm Definition.

    Note:
    The `orbit_number_start` and `orbit_number_stop` parameters are used to determine if the
    scene crosses the equator. They are the same if the frame does not cross
    the equator.

    References:
    ESA Sentinel-1 Level 1 Detailed Algorithm Definition
    https://sentinels.copernicus.eu/documents/247904/1877131/S1-TN-MDA-52-7445_Sentinel-1+Level+1+Detailed+Algorithm+Definition_v2-4.pdf/83624863-6429-cfb8-2371-5c5ca82907b8

    Stolen from https://github.com/opera-adt/s1-reader/blob/main/src/s1reader/s1_burst_id.py

    Args:
        sensing_time: Iso date of sensing time of the first input line of this burst [UTC]
        anx_time: Time of the ascending node prior to the start of the scene.
        orbit_number_start: Relative orbit number at the start of the acquisition, from 1-175.
        orbit_number_stop: Relative orbit number at the end of the acquisition.
        subswath: Name of the subswath of the burst (not case sensitive).

    Returns:
        The burst ID and the correct orbit number
    """
    mode = subswath[0:2].upper()
    swath_num = int(subswath[-1])
    pream, beamtime = get_mode_timing(mode)

    # Since we only have access to the current subswath, we need to use the
    # burst-to-burst times to figure out
    #   1. if IW1 crossed the equator, and
    #   2. The mid-burst sensing time for IW2
    # IW1 -> IW2 takes ~0.83220 seconds
    # IW2 -> IW3 takes ~1.07803 seconds
    # IW3 -> IW1 takes ~0.84803 seconds
    # EW1 -> EW2 ~0.6826778977095476
    # EW2 -> EW3 ~0.558731729405626
    # EW3 -> EW4 ~0.6123389197595133
    # EW4 -> EW5 ~0.5653802400407812
    # EW5 -> EW1 ~0.619247213084539

    burst_times = {'IW': [0.832, 1.078, 0.848], 'EW': [0.683, 0.559, 0.612, 0.565, 0.619]}

    if mode == 'IW':
        iw1_start_offsets = [0, -burst_times[mode][0], -burst_times[mode][0] - burst_times[mode][1]]

        start_iw1 = calc_start_subsw1(iw1_start_offsets, swath_num, sensing_time)

        # Middle of IW2 is the middle of the entire burst:
        start_iw1_to_mid_iw2 = burst_times[mode][0] + burst_times[mode][1] / 2
        mid_iw2 = start_iw1 + timedelta(seconds=start_iw1_to_mid_iw2)

        has_anx_crossing = (orbit_number_stop == orbit_number_start + 1) or (
            orbit_number_stop == 1 and orbit_number_start == 175
        )

        time_since_anx_iw1 = start_iw1 - anx_time
        time_since_anx = mid_iw2 - anx_time

        if (time_since_anx_iw1 - NOMINAL_ORBITAL_DURATION).total_seconds() < 0:
            # Less than a full orbit has passed
            orbit_number = orbit_number_start
        else:
            orbit_number = orbit_number_stop
            # Additional check for scenes which have a given ascending node
            # that's more than 1 orbit in the past
            if not has_anx_crossing:
                time_since_anx = time_since_anx - NOMINAL_ORBITAL_DURATION

        esa_burst_id = calc_esa_burstid(time_since_anx, orbit_number_start, pream, beamtime)

    elif mode == 'EW':
        # EWs are always high-latitude and don't cross equator. We can always
        # use start orbit.
        orbit_number = orbit_number_start

        ew1_start_offsets = [
            0,
            -burst_times[mode][0],
            -burst_times[mode][0] - burst_times[mode][1],
            -burst_times[mode][0] - burst_times[mode][1] - burst_times[mode][2],
            -burst_times[mode][0] - burst_times[mode][1] - burst_times[mode][2] - burst_times[mode][3],
        ]

        start_ew1 = calc_start_subsw1(ew1_start_offsets, swath_num, sensing_time)

        # Middle of EW3 is the middle of the entire burst:
        start_ew1_to_mid_ew3 = burst_times[mode][0] + burst_times[mode][1] + burst_times[mode][2] / 2
        mid_ew3 = start_ew1 + timedelta(seconds=start_ew1_to_mid_ew3)

        time_since_anx = mid_ew3 - anx_time

        esa_burst_id = calc_esa_burstid(time_since_anx, orbit_number_start, pream, beamtime)

    return esa_burst_id, orbit_number


def burst_from_local(
    tiff_path: Path, xml_path: Path, slc_name: str, swath: str, polarization: str, burst_index: int
) -> utils.BurstInfo:
    """Create a BurstInfo object from a local copy of the burst extractor output

    args:
        xml_path: The path to the XML file
        swath: The name of the swath
        burst_index: The index of the burst within the swath
    """
    polarization = xml_path.name.split('_')[-1].split('.')[0]
    manifest = utils.get_subxml_from_metadata(xml_path, 'manifest', swath, polarization)
    xml_orbit_path = './/{*}metadataObject[@ID="measurementOrbitReference"]/metadataWrap/xmlData/{*}orbitReference'
    meta_orbit = manifest.find(xml_orbit_path)
    abs_orbit_start, abs_orbit_stop = [int(x.text) for x in meta_orbit.findall('{*}orbitNumber')]
    rel_orbit_start, rel_orbit_stop = [int(x.text) for x in meta_orbit.findall('{*}relativeOrbitNumber')]
    direction = meta_orbit.find('{*}extension/{*}orbitProperties/{*}pass').text.upper()
    # anx_time = datetime.fromisoformat(meta_orbit.find('{*}extension/{*}orbitProperties/{*}ascendingNodeTime').text)

    info = utils.BurstInfo(
        granule='',
        slc_granule=slc_name,
        swath=swath,
        polarization=polarization,
        # FIXME: burst_id is not correct
        burst_id=burst_index,
        burst_index=burst_index,
        direction=direction,
        absolute_orbit=abs_orbit_start,
        relative_orbit=rel_orbit_start,
        date=None,
        data_url='',
        data_path=tiff_path,
        metadata_url='',
        metadata_path=xml_path,
    )
    info.add_shape_info()
    info.add_start_stop_utc()
    info.date = info.start_utc

    # doesn't work
    # burst_id, orbit_number = calculate_burstid_opera(info.start_utc, anx_time, rel_orbit_start, rel_orbit_stop, swath)
    # info.absolute_orbit = orbit_number
    # info.burst_id = burst_id
    return info


def local2safe(
    tiff_path: Path,
    xml_path: Path,
    slc_name: str,
    swath: str,
    polarization: str,
    burst_index: int,
    all_anns: bool = False,
    work_dir: Optional[Path] = None,
) -> Path:
    """Convert a burst granule to the ESA SAFE format using local files

    Args:
        tiff_path: The path to the TIFF file
        xml_path: The path to the XML file
        burst_index: The index of the burst within the swath
        work_dir: The directory to store temporary files

    Returns:
        The path to the created SAFE
    """
    work_dir = utils.optional_wd(work_dir)

    valid_swaths = ['IW1', 'IW2', 'IW3', 'EW1', 'EW2', 'EW3', 'EW4', 'EW5']
    swath = swath.upper()
    if swath not in valid_swaths:
        raise ValueError(f'Invalid swath: {swath}')

    valid_pols = ['VV', 'VH', 'HV', 'HH']
    polarization = polarization.upper()
    if polarization not in valid_pols:
        raise ValueError(f'Invalid polarization: {polarization}')

    burst_infos = [burst_from_local(tiff_path, xml_path, slc_name, swath, polarization, burst_index)]
    print(f'Found {len(burst_infos)} burst(s).')

    # print('Check burst group validity...')
    # Safe.check_group_validity(burst_infos)
    print('Creating SAFE...')

    safe = Safe(burst_infos, all_anns, work_dir)
    safe_path = safe.create_safe()
    print('SAFE created!')

    return safe_path


def main():
    """Entrypoint for the local2safe script
    Example:

    local2safe S1_136231_IW2_20200604T022312_VV_7C85-BURST.tiff S1A_IW_SLC__1SDV_20200604T022251_20200604T022318_032861_03CE65_7C85_VV.xml \
    --slc_name S1A_IW_SLC__1SDV_20200604T022251_20200604T022318_032861_03CE65_7C85 --swath IW2 --polarization VV --burst_index 3
    """
    parser = argparse.ArgumentParser(description='Generate a SAFE file from local burst extractor outputs')
    parser.add_argument('tiff_path', type=Path, help='Path to the burst TIFF file')
    parser.add_argument('xml_path', type=Path, help='Path to the burst XML file')
    parser.add_argument('--slc_name', type=str, help='The name of the SLC granule')
    parser.add_argument('--swath', type=str, help='The name of the swath')
    parser.add_argument('--polarization', type=str, help='The polarization of the burst')
    parser.add_argument('--burst_index', type=int, help='The index of the burst within the swath')
    parser.add_argument('--all_anns', action='store_true', help='Include all annotations')
    parser.add_argument('--work_dir', type=Path, help='The directory to store temporary files')
    args = parser.parse_args()

    local2safe(
        args.tiff_path,
        args.xml_path,
        args.slc_name,
        args.swath,
        args.polarization,
        args.burst_index,
        args.all_anns,
        args.work_dir,
    )
