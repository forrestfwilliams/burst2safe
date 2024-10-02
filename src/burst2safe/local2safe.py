"""Generate a SAFE file from local burst extractor outputs"""

from pathlib import Path
from typing import Optional


from burst2safe import utils
from burst2safe.safe import Safe


def burst_from_local(xml_path: Path, swath: str, burst_index: int) -> utils.BurstInfo:
    """Create a BurstInfo object from a local copy of the burst extractor output

    args:
        xml_path: The path to the XML file
        swath: The name of the swath
        burst_index: The index of the burst within the swath
    """
    polarization = xml_path.name.split('_')[-1].split('.')[0]
    product = utils.get_subxml_from_metadata(xml_path, 'product', swath, polarization)
    return None


def local2safe(
    tiff_path: Path, xml_path: Path, burst_index: int, all_anns: bool = False, work_dir: Optional[Path] = None
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

    burst_infos = list(burst_from_local(tiff_path, xml_path, burst_index))
    print(f'Found {len(burst_infos)} burst(s).')

    print('Check burst group validity...')
    Safe.check_group_validity(burst_infos)

    print('Creating SAFE...')
    [info.add_shape_info() for info in burst_infos]
    [info.add_start_stop_utc() for info in burst_infos]

    safe = Safe(burst_infos, all_anns, work_dir)
    safe_path = safe.create_safe()
    print('SAFE created!')

    return safe_path
