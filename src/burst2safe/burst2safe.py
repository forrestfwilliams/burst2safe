"""A package for converting ASF burst SLCs to the SAFE format"""

from argparse import ArgumentParser
from pathlib import Path
from typing import Iterable, Optional

from shapely import box
from shapely.geometry import Polygon

from burst2safe.safe import Safe
from burst2safe.search import download_bursts, find_bursts
from burst2safe.utils import get_burst_infos, optional_wd


DESCRIPTION = """Convert a set of ASF burst SLCs to the ESA SAFE format.
You can either provide a list of burst granules, or define a burst group by
providing the absolute orbit number, starting burst ID, ending burst ID, swaths,
and polarizations arguments.
"""


def burst2safe(
    granules: Optional[Iterable[str]] = None,
    orbit: Optional[int] = None,
    footprint: Optional[Polygon] = None,
    polarizations: Optional[Iterable[str]] = None,
    swaths: Optional[Iterable[str]] = None,
    min_bursts: int = 1,
    keep_files: bool = False,
    work_dir: Optional[Path] = None,
) -> Path:
    """Convert a set of burst granules to the ESA SAFE format.

    To be eligible for conversions, all burst granules must:
    - Have the same acquisition mode
    - Be from the same absolute orbit
    - Be contiguous in time and space
    - Have the same footprint for all included polarizations

    Args:
        granules: A list of burst granules to convert to SAFE
        orbit: The absolute orbit number of the bursts
        footprint: The bounding box of the bursts
        polarizations: List of polarizations to include
        min_bursts: The minimum number of bursts per swath (default: 1)
        work_dir: The directory to create the SAFE in (default: current directory)
    """
    work_dir = optional_wd(work_dir)

    products = find_bursts(granules, orbit, footprint, polarizations, swaths, min_bursts)
    burst_infos = get_burst_infos(products, work_dir)
    print(f'Found {len(burst_infos)} burst(s).')

    print('Check burst group validity...')
    Safe.check_group_validity(burst_infos)

    print('Downloading data...')
    download_bursts(burst_infos)
    print('Download complete.')

    print('Creating SAFE...')
    [info.add_shape_info() for info in burst_infos]
    [info.add_start_stop_utc() for info in burst_infos]

    safe = Safe(burst_infos, work_dir)
    safe_path = safe.create_safe()
    print('SAFE created!')

    if not keep_files:
        safe.cleanup()

    return safe_path


def main() -> None:
    parser = ArgumentParser(description=DESCRIPTION)
    parser.add_argument('granules', nargs='*', help='List of bursts to convert to SAFE')
    parser.add_argument('--orbit', type=int, help='Absolute orbit number of the bursts')
    parser.add_argument('--bbox', type=float, nargs=4, help='Bounding box of the bursts (W S E N in lat/lon)')
    parser.add_argument('--pols', type=str, nargs='+', help='Plarizations of the bursts (i.e., VV VH)')
    parser.add_argument('--swaths', type=str, nargs='+', help='Swaths of the bursts (i.e., IW1 IW2 IW3)')
    parser.add_argument('--min-bursts', type=int, default=1, help='Minimum # of bursts per swath/polarization.')
    parser.add_argument('--output-dir', type=str, default=None, help='Output directory to save to')
    parser.add_argument('--keep-files', action='store_true', default=False, help='Keep the intermediate files')
    args = parser.parse_args()

    if args.bbox:
        args.bbox = box(*args.bbox)
    if args.pols:
        args.pols = [pol.upper() for pol in args.pols]
    if args.swaths:
        args.swaths = [swath.upper() for swath in args.swaths]

    burst2safe(
        granules=args.granules,
        orbit=args.orbit,
        footprint=args.bbox,
        polarizations=args.pols,
        min_bursts=args.min_bursts,
        swaths=args.swaths,
        keep_files=args.keep_files,
        work_dir=args.output_dir,
    )
