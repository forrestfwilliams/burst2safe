"""A package for converting ASF burst SLCs to the SAFE format"""

import warnings
from concurrent.futures import ProcessPoolExecutor
from datetime import datetime
from itertools import product
from multiprocessing import cpu_count
from pathlib import Path
from typing import Iterable, List, Optional

import asf_search
import numpy as np
from asf_search.Products.S1BurstProduct import S1BurstProduct
from shapely.geometry import Polygon

from burst2safe.auth import get_earthdata_credentials
from burst2safe.utils import BurstInfo, download_url_with_retries


warnings.filterwarnings('ignore')


def find_granules(granules: Iterable[str]) -> List[S1BurstProduct]:
    """Find granules by name using ASF Search.

    Args:
        granules: A list of granule names

    Returns:
        A list of S1BurstProduct objects
    """
    results = asf_search.search(product_list=granules)
    found_granules = [result.properties['fileID'] for result in results]
    missing_granules = list(set(granules) - set(found_granules))
    if missing_granules:
        granule_str = ', '.joins(missing_granules)
        raise ValueError(f'Failed to find granule(s) {granule_str}. Check search parameters on Vertex.')
    return list(results)


def find_stack_orbits(rel_orbit: int, extent: Polygon, start_date: datetime, end_date: datetime) -> List[int]:
    """Find all orbits in a stack using ASF Search.

    Args:
        rel_orbit: The relative orbit number of the stack
        start_date: The start date of the stack
        end_date: The end date of the stack

    Returns:
        List of absolute orbit numbers
    """
    dataset = asf_search.constants.DATASET.SLC_BURST
    search_results = asf_search.geo_search(
        dataset=dataset,
        relativeOrbit=rel_orbit,
        intersectsWith=extent.centroid.wkt,
        start=start_date.strftime('%Y-%m-%d'),
        end=end_date.strftime('%Y-%m-%d'),
    )
    absolute_orbits = list(set([int(result.properties['orbit']) for result in search_results]))
    return absolute_orbits


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

    full_burst_ids = [f'{relative_orbit}_{id:06}_{swath}' for id in range(min_id, max_id + 1)]
    search_results = asf_search.search(
        dataset=asf_search.constants.DATASET.SLC_BURST,
        absoluteOrbit=absolute_orbit,
        polarization=polarization,
        fullBurstID=full_burst_ids,
    )
    return search_results


def find_swath_pol_group(
    search_results: List[S1BurstProduct], pol: str, swath: Optional[str], min_bursts: int
) -> List[S1BurstProduct]:
    """Find a group of bursts with the same polarization and swath.
    Add surrounding bursts if the group is too small.

    Args:
        search_results: A list of S1BurstProduct objects
        pol: The polarization to search for
        swath: The swath to search for
        min_bursts: The minimum number of bursts per swath

    Returns:
        An updated list of S1BurstProduct objects
    """
    if swath:
        search_results = [result for result in search_results if result.properties['burst']['subswath'] == swath]
    search_results = [result for result in search_results if result.properties['polarization'] == pol]

    params = [f'polarization {pol}']
    if swath:
        params.append(f'swath {swath}')
    params = ', '.join(params)

    if not search_results:
        raise ValueError(f'No bursts found for {params}. Check search parameters on Vertex.')

    if len(search_results) < min_bursts:
        search_results = add_surrounding_bursts(search_results, min_bursts)

    if len(search_results) < min_bursts:
        raise ValueError(f'Less than {min_bursts} bursts found for {params}. Check search parameters on Vertex.')

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
        sub_results = find_swath_pol_group(search_results, pol, swath, min_bursts)
        final_results.extend(sub_results)
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
