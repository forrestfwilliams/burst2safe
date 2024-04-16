import os
import shutil
from datetime import datetime
from pathlib import Path
from zipfile import ZipFile

import asf_search as asf
import lxml.etree as ET
import numpy as np

from burst2safe.utils import get_burst_infos


# Commented-out versions are listed as haveing no Level-1 changes
VERSIONS = [
    ('2.36', datetime(2014, 10, 1)),
    ('2.43', datetime(2015, 3, 19)),
    ('2.45', datetime(2015, 6, 17)),
    ('2.52', datetime(2015, 7, 2)),
    ('2.53', datetime(2015, 7, 18)),  # may not need
    ('2.60', datetime(2015, 11, 20)),
    ('2.62', datetime(2016, 3, 14)),
    ('2.70', datetime(2016, 4, 13)),
    ('2.71', datetime(2016, 5, 11)),
    ('2.72', datetime(2016, 8, 23)),
    ('2.82', datetime(2017, 3, 28)),
    ('2.84', datetime(2017, 8, 22)),  # may not need
    ('2.90', datetime(2018, 3, 13)),
    ('2.91', datetime(2018, 6, 26)),
    ('3.10', datetime(2019, 6, 26)),
    ('3.20', datetime(2020, 1, 29)),
    ('3.30', datetime(2020, 6, 23)),  # may not need
    ('3.31', datetime(2020, 6, 30)),
    ('3.40', datetime(2021, 11, 4)),
    ('3.51', datetime(2022, 3, 23)),
    ('3.52', datetime(2022, 5, 12)),  # may not need
    ('3.61', datetime(2023, 3, 30)),
    ('3.71', datetime(2023, 10, 19)),
    ('Current', datetime.now()),
]


def download_slcs():
    options = {
        'intersectsWith': 'POLYGON((12.2376 41.741,12.2607 41.741,12.2607 41.7609,12.2376 41.7609,12.2376 41.741))',
        'dataset': 'SLC-BURST',
        'relativeOrbit': 117,
        'flightDirection': 'Ascending',
        'polarization': 'VV',
        'maxResults': 2000,
    }
    results = asf.search(**options)
    bursts = sorted(get_burst_infos(results, Path.cwd()), key=lambda x: x.date)
    slcs = []
    for i in range(len(VERSIONS) - 1):
        date1 = VERSIONS[i][1]
        date2 = VERSIONS[i + 1][1]
        bursts_between = [burst for burst in bursts if date1 <= burst.date < date2]
        mid_index = int(np.floor(len(bursts_between) / 2))
        mid_burst = bursts_between[mid_index]
        slc = f'{mid_burst.slc_granule}-SLC'
        slcs.append(slc)
        print(f'Found {len(bursts_between)} bursts between {date1} and {date2}. Picking SLC {slc} for download.')

    slcs = asf.granule_search(slcs)
    slcs.download('.')


def get_version(slc_path):
    slc_name = f"{slc_path.name.split('.')[0]}.SAFE"
    with ZipFile(slc_path) as z:
        manifest_str = z.read(f'{slc_name}/manifest.safe')
        manifest = ET.fromstring(manifest_str)

    version_xml = [elem for elem in manifest.findall('.//{*}software') if elem.get('name') == 'Sentinel-1 IPF'][0]
    return version_xml.get('version')


def get_versions(slc_paths):
    versions = [(slc_path.name, get_version(slc_path)) for slc_path in slc_paths]
    versions.sort(key=lambda x: x[1])


def extract_support_folder(slc_path):
    version = get_version(slc_path).replace('.', '')
    out_dir = Path(f'support_{version}')
    out_dir.mkdir(exist_ok=True)
    slc_name = f"{slc_path.name.split('.')[0]}.SAFE"
    with ZipFile(slc_path) as zip_ref:
        for file_info in zip_ref.infolist():
            if file_info.filename.startswith(f'{slc_name}/support/') and not file_info.is_dir():
                source_file = zip_ref.open(file_info)
                target_path = out_dir / Path(file_info.filename).name
                with open(target_path, 'wb') as target_file:
                    shutil.copyfileobj(source_file, target_file)


def create_diffs():
    supports = sorted(Path('.').glob('support*'))
    for i in range(len(supports) - 1):
        support1 = supports[i]
        support2 = supports[i + 1]
        diff_file = Path(f'diff_{support1.name}_{support2.name}.txt')
        diff_file.touch()
        os.system(f'git diff --no-index {support1} {support2} > {diff_file}')


if __name__ == '__main__':
    download_slcs()
    slc_paths = sorted(list(Path('.').glob('*.zip')))
    for slc_path in slc_paths:
        extract_support_folder(slc_path)
    create_diffs()
