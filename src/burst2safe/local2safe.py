"""Generate a SAFE file from local burst extractor outputs"""

import argparse
from datetime import datetime
from pathlib import Path
from typing import Optional

from burst2safe import utils
from burst2safe.burst_id import calculate_burstid_opera
from burst2safe.safe import Safe


def burst_from_local(
    tiff_path: Path, xml_path: Path, slc_name: str, swath: str, polarization: str, burst_index: int
) -> utils.BurstInfo:
    """Create a BurstInfo object from a local copy of the burst extractor output

    args:
        xml_path: The path to the XML file
        swath: The name of the swath
        burst_index: The index of the burst within the swath
    """
    extractor_url = 'https://sentinel1-burst.asf.alaska.edu'
    burst_url_base = f'{extractor_url}/{slc_name}/{swath}/{polarization}/{burst_index}'
    data_url = f'{burst_url_base}.tiff'
    metadata_url = f'{burst_url_base}.xml'

    manifest = utils.get_subxml_from_metadata(xml_path, 'manifest', swath, polarization)
    xml_orbit_path = './/{*}metadataObject[@ID="measurementOrbitReference"]/metadataWrap/xmlData/{*}orbitReference'
    meta_orbit = manifest.find(xml_orbit_path)
    abs_orbit_start, abs_orbit_stop = [int(x.text) for x in meta_orbit.findall('{*}orbitNumber')]
    rel_orbit_start, rel_orbit_stop = [int(x.text) for x in meta_orbit.findall('{*}relativeOrbitNumber')]
    direction = meta_orbit.find('{*}extension/{*}orbitProperties/{*}pass').text.upper()

    product = utils.get_subxml_from_metadata(xml_path, 'product', swath, polarization)
    sensing_time_str = product.findall('swathTiming/burstList/burst')[burst_index].find('sensingTime').text
    anx_time_str = meta_orbit.find('{*}extension/{*}orbitProperties/{*}ascendingNodeTime').text
    burst_id, rel_orbit = calculate_burstid_opera(
        sensing_time_str, anx_time_str, rel_orbit_start, rel_orbit_stop, swath
    )
    info = utils.BurstInfo(
        granule='',
        slc_granule=slc_name,
        swath=swath,
        polarization=polarization,
        burst_id=burst_id,
        burst_index=burst_index,
        direction=direction,
        absolute_orbit=abs_orbit_start,
        relative_orbit=rel_orbit_start,
        date=None,
        data_url=data_url,
        data_path=tiff_path,
        metadata_url=metadata_url,
        metadata_path=xml_path,
    )
    info.add_shape_info()
    info.add_start_stop_utc()
    date_format = '%Y%m%dT%H%M%S'
    info.date = datetime.strptime(datetime.strftime(info.start_utc, date_format), date_format)
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
