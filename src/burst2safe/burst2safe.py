"""A package for converting ASF burst SLCs to the SAFE format"""

import warnings
from argparse import ArgumentParser
from pathlib import Path
from typing import Iterable, Optional

import asf_search

from burst2safe.safe import Safe
from burst2safe.utils import gather_burst_infos, optional_wd


warnings.filterwarnings('ignore')


def burst2safe(granules: Iterable[str], work_dir: Optional[Path] = None) -> None:
    work_dir = optional_wd(work_dir)
    burst_infos = gather_burst_infos(granules, work_dir)
    urls = list(dict.fromkeys([x.data_url for x in burst_infos] + [x.metadata_url for x in burst_infos]))
    paths = list(dict.fromkeys([x.data_path for x in burst_infos] + [x.metadata_path for x in burst_infos]))

    # TODO: this doesn't save files to the correct filename
    # session = asf_search.ASFSession()
    # with ThreadPoolExecutor() as executor:
    #     executor.map(
    #         asf_search.download_url,
    #         urls,
    #         [x.parent for x in paths],
    #         [x.name for x in paths],
    #         repeat(session, len(urls)),
    #     )

    for url, path in zip(urls, paths):
        asf_search.download_url(url=url, path=path.parent, filename=path.name)

    [x.add_shape_info() for x in burst_infos]
    [x.add_start_stop_utc() for x in burst_infos]

    safe = Safe(burst_infos, work_dir)
    safe.create_safe()


def main() -> None:
    parser = ArgumentParser()
    parser.add_argument('granules', nargs='+', help='A list of burst granules to convert to SAFE')
    args = parser.parse_args()
    burst2safe(granules=args.granules)
