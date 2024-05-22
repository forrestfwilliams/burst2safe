"""A package for converting ASF burst SLCs to the SAFE format"""

import warnings
from argparse import ArgumentParser
from concurrent.futures import ProcessPoolExecutor
from itertools import product
from multiprocessing import cpu_count
from pathlib import Path
from typing import Iterable, List, Optional

import asf_search
import numpy as np
from asf_search.Products.S1BurstProduct import S1BurstProduct
from shapely import box
from shapely.geometry import Polygon

from burst2safe.auth import get_earthdata_credentials
from burst2safe.safe import Safe
from burst2safe.utils import BurstInfo, download_url_with_retries, get_burst_infos, optional_wd


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


def add_surrounding_bursts(bursts: List[S1BurstProduct], min_bursts: int) -> List[S1BurstProduct]:
    """Add bursts to the list to ensure each swath has at least `min_bursts` bursts.
    All bursts must be from the same absolute orbit, swath, and polarization.

    Args:
        bursts: A list of S1BurstProduct objects
        min_bursts: The minimum number of bursts

    Returns:
        An extended list of S1BurstProduct objects
    """
    ids = [int(burst.properties['burst']['relativeBurstID']) for burst in bursts]
    relative_orbit, _, swath = bursts[0].properties['burst']['fullBurstID'].split('_')
    polarization = bursts[0].properties['polarization']
    absolute_orbit = int(bursts[0].properties['orbit'])

    min_id, max_id = min(ids), max(ids)
    extra = np.floor((min_bursts - (max_id - min_id + 1)) / 2).astype(int)
    min_id -= extra
    max_id += extra
    if max_id - min_id + 1 != min_bursts:
        max_id += 1

    full_burst_ids = [f'{relative_orbit}_{id}_{swath}' for id in range(min_id, max_id + 1)]
    search_results = asf_search.search(
        dataset=asf_search.constants.DATASET.SLC_BURST,
        absoluteOrbit=absolute_orbit,
        polarization=polarization,
        fullBurstID=full_burst_ids,
    )
    return search_results


def find_group(
    orbit: int, footprint: Polygon, polarizations: Iterable[str], swaths: Optional[str] = None, min_bursts: int = 1
) -> List[S1BurstProduct]:
    """Find burst groups using ASF Search.

    Args:
        orbit: The absolute orbit number of the bursts
        footprint: The bounding box of the bursts
        polarizations: List of polarizations to include
        min_bursts: The minimum number of bursts per swath (default: 1)

    Returns:
        A list of S1BurstProduct objects
    """
    bad_pols = set(polarizations) - set(['VV', 'VH', 'HV', 'HH'])
    if bad_pols:
        raise ValueError(f'Invalid polarizations: {" ".join(bad_pols)}')

    if swaths is None:
        swaths = [None]
    else:
        bad_swaths = set(swaths) - set(['IW1', 'IW2', 'IW3'])
        if bad_swaths:
            raise ValueError(f'Invalid swaths: {" ".join(bad_swaths)}')

    dataset = asf_search.constants.DATASET.SLC_BURST
    search_results = asf_search.geo_search(dataset=dataset, absoluteOrbit=orbit, intersectsWith=footprint.wkt)
    final_results = []
    for pol, swath in product(polarizations, swaths):
        sub_results = search_results
        if swath:
            sub_results = [result for result in sub_results if result.properties['swath'] == swath]
        sub_results = [result for result in sub_results if result.properties['polarization'] == pol]

        params = [f'orbit {orbit}', f'footprint {footprint}', f'polarization {pol}']
        if swath:
            params.append(f'swath {swath}')
        params = ', '.join(params)

        if not sub_results:
            raise ValueError(f'No bursts found for {params}. Bursts may not be populated yet.')

        if len(sub_results) < min_bursts:
            sub_results = add_surrounding_bursts(sub_results, min_bursts)

        if len(sub_results) < min_bursts:
            raise ValueError(f'Less than {min_bursts} bursts found for {params}. Bursts may not be populated yet.')

        final_results.extend(sub_results)
    breakpoint()
    return final_results


def find_bursts(
    granules: Optional[Iterable[str]] = None,
    orbit: Optional[int] = None,
    footprint: Optional[Polygon] = None,
    polarizations: Optional[Iterable[str]] = None,
    swaths: Optional[Iterable[str]] = None,
    min_bursts: int = 1,
) -> Path:
    """Find bursts using ASF Search.

    Args:
        granules: A list of burst granules to convert to SAFE
        orbit: The absolute orbit number of the bursts
        bbox: The bounding box of the bursts
        polarizations: List of polarizations to include
        min_bursts: The minimum number of bursts per swath (default: 1)
    """
    if granules:
        print('Using granule search...')
        results = find_granules(granules)
    elif orbit and footprint and polarizations:
        print('Using burst group search...')
        results = find_group(orbit, footprint, polarizations, swaths, min_bursts)
    else:
        raise ValueError(
            'You must provide either a list of granules or minimum set burst group parameters'
            '(Orbit, Footprint, and Polarizations).'
        )
    return results


def download_bursts(burst_infos: Iterable[BurstInfo]) -> None:
    """Download the burst data and metadata files using multiple workers.

    Args:
        burst_infos: A list of BurstInfo objects
    """
    downloads = {}
    for burst_info in burst_infos:
        downloads[burst_info.data_path] = burst_info.data_url
        downloads[burst_info.metadata_path] = burst_info.metadata_url
    download_info = [(value, key.parent, key.name) for key, value in downloads.items()]
    urls, dirs, names = zip(*download_info)

    username, password = get_earthdata_credentials()
    session = asf_search.ASFSession().auth_with_creds(username, password)
    n_workers = min(len(urls), max(cpu_count() - 2, 1))
    if n_workers == 1:
        for url, dir, name in zip(urls, dirs, names):
            download_url_with_retries(url, dir, name, session)
    else:
        with ProcessPoolExecutor(max_workers=n_workers) as executor:
            executor.map(download_url_with_retries, urls, dirs, names, [session] * len(urls))


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
