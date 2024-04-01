"""A package for converting ASF burst SLCs to the SAFE format"""

import warnings
from argparse import ArgumentParser
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Iterable, Optional

import asf_search
import numpy as np

from burst2safe.safe import Safe, Swath
from burst2safe.utils import BurstInfo, get_burst_infos, optional_wd


warnings.filterwarnings('ignore')


def check_group_validity(burst_infos: Iterable[BurstInfo]):
    swaths = sorted(list(set([info.swath for info in burst_infos])))
    polarizations = sorted(list(set([info.polarization for info in burst_infos])))
    burst_range = {}
    for swath in swaths:
        burst_range[swath] = {}
        for pol in polarizations:
            burst_subset = [info for info in burst_infos if info.swath == swath and info.polarization == pol]
            if len(burst_subset) == 0:
                burst_range[swath][pol] = [0, 0]
                continue
            Swath.check_burst_group_validity(burst_subset)

            burst_ids = [info.burst_id for info in burst_subset]
            burst_range[swath][pol] = [min(burst_ids), max(burst_ids)]

        start_ids = [id_range[0] for id_range in burst_range[swath].values()]
        if len(set(start_ids)) != 1:
            raise ValueError(f'Polarization groups in swath {swath} do not have same start burst id. Found {start_ids}')

        end_ids = [id_range[1] for id_range in burst_range[swath].values()]
        if len(set(end_ids)) != 1:
            raise ValueError(f'Polarization groups in swath {swath} do not have same end burst id. Found {end_ids}')

    if len(swaths) == 1:
        return

    pols = [f'({", ".join(sorted(keys))})' for keys in burst_range.values()]
    if len(set(pols)) != 1:
        raise ValueError(f'Swaths do not have same polarization groups. Found {pols}')

    swath_combos = [[swaths[i], swaths[i + 1]] for i in range(len(swaths) - 1)]
    working_pol = polarizations[0]
    for swath1, swath2 in swath_combos:
        min_diff = burst_range[swath1][working_pol][0] - burst_range[swath2][working_pol][1]
        if np.abs(min_diff) > 1:
            raise ValueError(f'Products from swaths {swath1} and {swath2} do not overlap')
        max_diff = burst_range[swath1][working_pol][1] - burst_range[swath2][working_pol][0]
        if np.abs(max_diff) > 1:
            raise ValueError(f'Products from swaths {swath1} and {swath2} do not overlap')


def burst2safe(granules: Iterable[str], work_dir: Optional[Path] = None) -> Path:
    work_dir = optional_wd(work_dir)

    print(f'Gathering information for {len(granules)} burst(s)...')
    burst_infos = get_burst_infos(granules, work_dir)
    print('Check burst group validity...')
    check_group_validity(burst_infos)

    downloads = {}
    for burst_info in burst_infos:
        downloads[burst_info.data_path] = burst_info.data_url
        downloads[burst_info.metadata_path] = burst_info.metadata_url
    download_info = [(key.parent, key.name, value) for key, value in downloads.items()]

    print('Downloading data...')
    dirs, names, urls = zip(*download_info)
    # TODO: bug in asf_search (issue #282) requires a new session for each download
    sessions = [asf_search.ASFSession() for _ in range(len(urls))]
    with ThreadPoolExecutor() as executor:
        executor.map(asf_search.download_url, urls, dirs, names, sessions)
    print('Download complete.')

    print('Creating SAFE...')
    [info.add_shape_info() for info in burst_infos]
    [info.add_start_stop_utc() for info in burst_infos]

    safe = Safe(burst_infos, work_dir)
    safe_path = safe.create_safe()
    print('SAFE created!')

    return safe_path


def main() -> None:
    parser = ArgumentParser()
    parser.add_argument('granules', nargs='+', help='A list of burst granules to convert to SAFE')
    args = parser.parse_args()
    burst2safe(granules=args.granules)
