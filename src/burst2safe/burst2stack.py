"""A tool for converting stacks of ASF burst SLCs to stacks of SAFEs"""

from argparse import ArgumentParser
from datetime import datetime
from pathlib import Path
from typing import Iterable, Optional

from shapely.geometry import Polygon

from burst2safe import utils
from burst2safe.burst2safe import burst2safe
from burst2safe.search import find_stack_orbits


DESCRIPTION = """Convert a stack of ASF burst SLCs to a stack of ESA SAFEs.
This will produce a SAFE for each absolute orbit in the stack. You can
define a stack by specifying a relaitve orbit number, start/end dates,
an extent, and polarization(s).
"""


def burst2stack(
    rel_orbit: Optional[int] = None,
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
    extent: Optional[Polygon] = None,
    polarizations: Optional[Iterable[str]] = None,
    swaths: Optional[Iterable[str]] = None,
    min_bursts: int = 1,
    include_mid: bool = False,
    keep_files: bool = False,
    work_dir: Optional[Path] = None,
) -> Path:
    """Convert a stack of burst granules to a stack of ESA SAFEs.
    Wraps the burst2safe function to handle multiple dates.

    Args:
        rel_orbit: The relative orbit number of the bursts
        start_date: The start date of the bursts
        end_date: The end date of the bursts
        extent: The bounding box of the bursts
        swaths: List of swaths to include
        polarizations: List of polarizations to include
        min_bursts: The minimum number of bursts per swath (default: 1)
        include_mid: Include mid-swath annotation file (for s1-reader compatibility)
        keep_files: Keep the intermediate files
        work_dir: The directory to create the SAFE in (default: current directory)
    """
    absolute_orbits = find_stack_orbits(rel_orbit, extent, start_date, end_date)
    print(f'Creating SAFEs for {len(absolute_orbits)} time periods...')
    for orbit in absolute_orbits:
        print()
        burst2safe(
            granules=None,
            orbit=orbit,
            extent=extent,
            polarizations=polarizations,
            swaths=swaths,
            min_bursts=min_bursts,
            include_mid=include_mid,
            keep_files=keep_files,
            work_dir=work_dir,
        )


def main() -> None:
    parser = ArgumentParser(description=DESCRIPTION)
    parser.add_argument('--rel-orbit', type=int, help='Relative orbit number of the bursts')
    parser.add_argument('--start-date', type=str, help='Start date of the bursts (YYYY-MM-DD)')
    parser.add_argument('--end-date', type=str, help='End date of the bursts (YYYY-MM-DD)')
    parser.add_argument(
        '--extent',
        type=str,
        nargs='+',
        help='Bounds (W S E N in lat/lon) or geometry file describing spatial extent',
    )
    parser.add_argument('--pols', type=str, nargs='+', help='Plarizations of the bursts (i.e., VV VH)')
    parser.add_argument('--swaths', type=str, nargs='+', help='Swaths of the bursts (i.e., IW1 IW2 IW3)')
    parser.add_argument('--min-bursts', type=int, default=1, help='Minimum # of bursts per swath/polarization.')
    parser.add_argument(
        '--include-mid',
        action='store_true',
        default=False,
        help='Include mid-swath annotation file (for s1-reader compatibility).',
    )
    parser.add_argument('--output-dir', type=str, default=None, help='Output directory to save to')
    parser.add_argument('--keep-files', action='store_true', default=False, help='Keep the intermediate files')

    args = utils.reparse_args(parser.parse_args(), tool='burst2stack')

    burst2stack(
        rel_orbit=args.rel_orbit,
        start_date=args.start_date,
        end_date=args.end_date,
        extent=args.extent,
        polarizations=args.pols,
        min_bursts=args.min_bursts,
        include_mid=args.include_mid,
        swaths=args.swaths,
        keep_files=args.keep_files,
        work_dir=args.output_dir,
    )
