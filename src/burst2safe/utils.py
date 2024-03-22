import warnings
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Iterable, List, Optional

import asf_search
import crcmod
import lxml.etree as ET
from osgeo import gdal


gdal.UseExceptions()
warnings.filterwarnings('ignore')


@dataclass
class BurstInfo:
    """Dataclass for storing burst information."""

    granule: str
    slc_granule: str
    swath: str
    polarization: str
    burst_id: int
    burst_index: int
    direction: str
    absolute_orbit: int
    date: datetime
    data_url: Path
    data_path: Path
    metadata_url: Path
    metadata_path: Path
    start_utc: datetime = None
    stop_utc: datetime = None
    length: int = None
    width: int = None

    def add_shape_info(self):
        """Add shape information to the BurstInfo object."""
        info = gdal.Info(str(self.data_path), format='json')
        self.width, self.length = info['size']

    def add_start_stop_utc(self):
        """Add start and stop UTC to burst info.
        There is spatial overlap between bursts, so burst start/stop times will overlap as well.
        """
        annotation = get_subxml_from_metadata(self.metadata_path, 'product', self.swath, self.polarization)
        start_utc_str = annotation.findall('.//burst')[self.burst_index].find('azimuthTime').text
        self.start_utc = datetime.fromisoformat(start_utc_str)
        # TODO: this is slightly wrong, but it's close enough for now
        azimuth_time_interval = float(annotation.find('.//azimuthTimeInterval').text)
        self.stop_utc = self.start_utc + (self.length * timedelta(seconds=azimuth_time_interval))


def get_burst_info(granule: str, work_dir: Path) -> BurstInfo:
    results = asf_search.search(product_list=[granule])
    if len(results) == 0:
        raise ValueError(f'ASF Search failed to find {granule}.')
    if len(results) > 1:
        raise ValueError(f'ASF Search found multiple results for {granule}.')
    result = results[0]

    burst_granule = result.properties['fileID']
    slc_granule = result.umm['InputGranules'][0].split('-')[0]
    swath = result.properties['burst']['subswath'].upper()
    polarization = result.properties['polarization'].upper()
    burst_id = int(result.properties['burst']['relativeBurstID'])
    burst_index = int(result.properties['burst']['burstIndex'])
    direction = result.properties['flightDirection'].upper()
    absolute_orbit = int(result.properties['orbit'])
    date_format = '%Y%m%dT%H%M%S'
    burst_time_str = burst_granule.split('_')[3]
    burst_time = datetime.strptime(burst_time_str, date_format)
    data_url = result.properties['url']
    data_path = work_dir / f'{burst_granule}.tiff'
    metadata_url = result.properties['additionalUrls'][0]
    metadata_path = work_dir / f'{slc_granule}_{polarization}.xml'

    burst_info = BurstInfo(
        burst_granule,
        slc_granule,
        swath,
        polarization,
        burst_id,
        burst_index,
        direction,
        absolute_orbit,
        burst_time,
        data_url,
        data_path,
        metadata_url,
        metadata_path,
    )
    return burst_info


def gather_burst_infos(granules: Iterable[str], work_dir: Path) -> List[BurstInfo]:
    """Get burst information from ASF Search.

    Args:
        granules: The burst granules to get information for.
        save_dir: The directory to save the data to.
    Returns:
        A list of BurstInfo objects.
    """
    work_dir = optional_wd(work_dir)
    burst_info_list = []
    for granule in granules:
        burst_info = get_burst_info(granule, work_dir)
        burst_info_list.append(burst_info)

    return burst_info_list


def sort_burst_infos(burst_info_list):
    burst_infos = {}
    for burst_info in burst_info_list:
        if burst_info.swath not in burst_infos:
            burst_infos[burst_info.swath] = {}

        if burst_info.polarization not in burst_infos[burst_info.swath]:
            burst_infos[burst_info.swath][burst_info.polarization] = []

        burst_infos[burst_info.swath][burst_info.polarization].append(burst_info)

    swaths = list(burst_infos.keys())
    polarizations = list(burst_infos[swaths[0]].keys())
    for swath, polarization in zip(swaths, polarizations):
        burst_infos[swath][polarization] = sorted(burst_infos[swath][polarization], key=lambda x: x.burst_id)

    return burst_infos


def optional_wd(wd: Optional[Path | str] = None) -> None:
    """Return the working directory as a Path object"""
    if wd is None:
        wd = Path.cwd()
    return Path(wd)


def calculate_crc16(file_path: Path):
    """Calculate the CRC16 checksum for a file."""
    with open(file_path, 'rb') as f:
        data = f.read()

    # TODO: this doesn't match the ESA checksum
    crc16 = crcmod.predefined.mkPredefinedCrcFun('crc-16')
    crc16_value = crc16(data)
    crc16_hex = hex(crc16_value)[2:].zfill(4).upper()
    return crc16_hex


def get_subxml_from_metadata(metadata_path: str, xml_type: str, subswath: str = None, polarization: str = None):
    """Extract child xml info from ASF combined metadata file.

    Args:
        metadata_path: Path to metadata file
        xml_typ: Desired type of metadata to obtain (product, noise, calibration, or rfi)
        subswath: Desired subswath to obtain data for
        polarization: Desired polarization to obtain data for

    Returns:
        lxml Element for desired metadata
    """
    with open(metadata_path, 'r') as metadata_file:
        metadata = ET.parse(metadata_file).getroot()

    if xml_type == 'manifest':
        name = 'manifest.safe'
        desired_metadata = metadata.find('manifest/{urn:ccsds:schema:xfdu:1}XFDU')
        return name, desired_metadata

    possible_types = ['product', 'noise', 'calibration', 'rfi']
    if xml_type not in possible_types:
        raise ValueError(f'Metadata type {xml_type} not one of {" ".join(possible_types)}')

    if subswath is None or polarization is None:
        raise ValueError('subswath and polarization must be provided for non-manifest files')

    correct_type = [x for x in metadata.find('metadata').iterchildren() if x.tag == xml_type]
    correct_swath = [x for x in correct_type if x.find('swath').text == subswath]
    correct_pol = [x for x in correct_swath if x.find('polarisation').text == polarization]

    if not correct_pol:
        desired_metadata = None
    else:
        desired_metadata = correct_pol[0].find('content')

    return desired_metadata


def flatten(list_of_lists: List[List]):
    return [item for sublist in list_of_lists for item in sublist]


def drop_duplicates(input_list: List):
    return list(dict.fromkeys(input_list))
