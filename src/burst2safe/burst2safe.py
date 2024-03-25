"""A package for converting ASF burst SLCs to the SAFE format"""

import warnings
from argparse import ArgumentParser
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Iterable, Optional

import asf_search

from burst2safe.safe import Safe
from burst2safe.utils import gather_burst_infos, optional_wd


warnings.filterwarnings('ignore')


def burst2safe(granules: Iterable[str], work_dir: Optional[Path] = None) -> Path:
    work_dir = optional_wd(work_dir)
    burst_infos = gather_burst_infos(granules, work_dir)
    urls = list(dict.fromkeys([x.data_url for x in burst_infos] + [x.metadata_url for x in burst_infos]))
    paths = list(dict.fromkeys([x.data_path for x in burst_infos] + [x.metadata_path for x in burst_infos]))

    dirs = [x.parent for x in paths]
    names = [x.name for x in paths]
    # TODO: bug in asf_search (issue #282), creates a need for multiple sessions
    sessions = [asf_search.ASFSession() for _ in range(len(urls))]
    with ThreadPoolExecutor() as executor:
        executor.map(asf_search.download_url, urls, dirs, names, sessions)

    [info.add_shape_info() for info in burst_infos]
    [info.add_start_stop_utc() for info in burst_infos]

    safe = Safe(burst_infos, work_dir)
    safe_path = safe.create_safe()
    return safe_path


def main() -> None:
    parser = ArgumentParser()
    parser.add_argument('granules', nargs='+', help='A list of burst granules to convert to SAFE')
    args = parser.parse_args()
    burst2safe(granules=args.granules)
