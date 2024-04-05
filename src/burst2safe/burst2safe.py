"""A package for converting ASF burst SLCs to the SAFE format"""

import warnings
from argparse import ArgumentParser
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Iterable, Optional

import asf_search

from burst2safe.safe import Safe
from burst2safe.utils import get_burst_infos, optional_wd


warnings.filterwarnings('ignore')


def burst2safe(granules: Iterable[str], work_dir: Optional[Path] = None) -> Path:
    work_dir = optional_wd(work_dir)

    print(f'Gathering information for {len(granules)} burst(s)...')
    burst_infos = get_burst_infos(granules, work_dir)
    print('Check burst group validity...')
    Safe.check_group_validity(burst_infos)

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
