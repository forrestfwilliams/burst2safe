"""A package for converting ASF burst SLCs to the SAFE format"""

import warnings
from argparse import ArgumentParser
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Iterable, List, Optional

import asf_search
from asf_search.Products.S1BurstProduct import S1BurstProduct
from shapely import box
from shapely.geometry import Polygon

from burst2safe.safe import Safe
from burst2safe.utils import BurstInfo, get_burst_infos, optional_wd


warnings.filterwarnings('ignore')

DESCRIPTION = """Convert a set of ASF burst SLCs to the ESA SAFE format.
You can either provide a list of burst granules, or define a burst group by
providing the absolute orbit number, starting burst ID, ending burst ID, swaths,
and polarizations arguments.
"""


def find_granules(granules: Iterable[str]) -> List[S1BurstProduct]:
    results = asf_search.search(product_list=granules)
    found_granules = [result.properties['fileID'] for result in results]

    for granule in granules:
        if granule not in found_granules:
            raise ValueError(f'ASF Search failed to find {granule}.')
    return list(results)


def find_group(orbit: int, footprint: Polygon, polarizations: Iterable[str]) -> List[S1BurstProduct]:
    results = []
    for pol in polarizations:
        if pol not in ['VV', 'VH', 'HV', 'HH']:
            raise ValueError(f'Invalid polarization: {pol}')

        single_pol = asf_search.geo_search(
            dataset=asf_search.constants.DATASET.SLC_BURST,
            absoluteOrbit=orbit,
            intersectsWith=footprint.wkt,
            polarization=pol,
        )

        if not single_pol:
            # TODO: add Vertex link to error message?
            raise ValueError(
                f'No results found for orbit {orbit}, footprint {footprint}, and polarization {pol}. '
                'Bursts may not populated yet for this group. Check Vertex to confirm.'
            )
        results.extend(list(single_pol))
    return results


def find_bursts(
    granules: Optional[Iterable[str]] = None,
    orbit: Optional[int] = None,
    footprint: Optional[Polygon] = None,
    polarizations: Optional[Iterable[str]] = None,
) -> Path:
    """Find bursts using ASF Search.

    Args:
        granules: A list of burst granules to convert to SAFE
        orbit: The absolute orbit number of the bursts
        bbox: The bounding box of the bursts
        polarizations: List of polarizations to include
    """
    if granules:
        print('Using granule search...')
        results = find_granules(granules)
    elif orbit and footprint and polarizations:
        print('Using burst group search...')
        results = find_group(orbit, footprint, polarizations)
    else:
        raise ValueError(
            'You must provide either a list of granules or ALL burst group parameters'
            '(Orbit, Start ID, End ID, Swaths, and Polarizations.'
        )
    return results


def download_bursts(burst_infos: Iterable[BurstInfo]):
    downloads = {}
    for burst_info in burst_infos:
        downloads[burst_info.data_path] = burst_info.data_url
        downloads[burst_info.metadata_path] = burst_info.metadata_url
    download_info = [(key.parent, key.name, value) for key, value in downloads.items()]

    dirs, names, urls = zip(*download_info)
    # TODO: bug in asf_search (issue #282) requires a new session for each download
    sessions = [asf_search.ASFSession() for _ in range(len(urls))]
    with ThreadPoolExecutor() as executor:
        executor.map(asf_search.download_url, urls, dirs, names, sessions)


def burst2safe(
    granules: Optional[Iterable[str]] = None,
    orbit: Optional[int] = None,
    footprint: Optional[Polygon] = None,
    polarizations: Optional[Iterable[str]] = None,
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
        work_dir: The directory to create the SAFE in
    """
    work_dir = optional_wd(work_dir)

    products = find_bursts(granules, orbit, footprint, polarizations)
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
    parser.add_argument('granules', nargs='*', help='A list of bursts to convert to SAFE')
    parser.add_argument('--orbit', type=int, help='The absolute orbit number of the bursts')
    parser.add_argument('--bbox', type=float, nargs=4, help='Bounding box of the bursts (W S E N in lat/lon)')
    parser.add_argument('--pols', type=str, nargs='+', help='The polarizations of the bursts (i.e., VV VH)')
    parser.add_argument('--keep-files', action='store_true', default=False, help='Keep the intermediate files')
    args = parser.parse_args()

    if args.bbox:
        args.bbox = box(*args.bbox)
    if args.pols:
        args.pols = [pol.upper() for pol in args.pols]

    burst2safe(
        granules=args.granules,
        orbit=args.orbit,
        footprint=args.bbox,
        polarizations=args.pols,
        keep_files=args.keep_files,
    )
