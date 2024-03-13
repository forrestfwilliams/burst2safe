"""A package for converting ASF burst SLCs to the SAFE format"""
from argparse import ArgumentParser
from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime, timedelta
from itertools import product
from pathlib import Path
from typing import Iterable, List, Optional

import asf_search
import lxml.etree as ET
from osgeo import gdal


gdal.UseExceptions()


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
        annotation = get_subxml_from_burst_metadata(self.metadata_path, 'product', self.swath, self.polarization)
        start_utc_str = annotation.findall('.//burst')[self.burst_index].find('azimuthTime').text
        self.start_utc = datetime.fromisoformat(start_utc_str)
        azimuth_time_interval = float(annotation.find('.//azimuthTimeInterval').text)
        self.stop_utc = self.start_utc + (self.length * timedelta(seconds=azimuth_time_interval))


def optional_wd(wd: Optional[Path | str] = None) -> None:
    """Return the working directory as a Path object"""
    if wd is None:
        wd = Path.cwd()
    return Path(wd)


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


def create_product_name(burst_infos: Iterable[BurstInfo]) -> str:
    """Create a product name for the SAFE file."""
    platform, beam_mode, product_type = burst_infos[0].slc_granule.split('_')[:3]
    product_info = f'1SS{burst_infos[0].polarization[0]}'
    min_date = min([x.date for x in burst_infos]).strftime('%Y%m%dT%H%M%S')
    max_date = max([x.date for x in burst_infos]).strftime('%Y%m%dT%H%M%S')
    absolute_orbit = f'{burst_infos[0].absolute_orbit:06d}'
    mission_data_take = burst_infos[0].slc_granule.split('_')[-2]
    dummy_unique_id = '0000'
    product_name = f'{platform}_{beam_mode}_{product_type}__{product_info}_{min_date}_{max_date}_{absolute_orbit}_{mission_data_take}_{dummy_unique_id}.SAFE'
    return product_name


def get_measurement_name(product_name: str, swath: str, pol: str, image_number: int) -> str:
    """Create a measurement name for given dataset."""
    platfrom, _, _, _, _, start, stop, orbit, data_take, _ = product_name.lower().split('_')
    product_name = (
        f'{platfrom}-{swath.lower()}-slc-{pol.lower()}-{start}-{stop}-{orbit}-{data_take}-{image_number:03d}.tiff'
    )
    return product_name


def get_subxml_from_burst_metadata(metadata_path: str, xml_type: str, subswath: str = None, polarization: str = None):
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
        name = 'manifest.xml'
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


def bursts_to_tiff(burst_infos: Iterable[BurstInfo], out_path: Path, work_dir: Path):
    """Write concatenated bursts to VRT file."""
    swaths = set([x.swath for x in burst_infos])
    if len(swaths) != 1:
        raise ValueError('All bursts must be from the same swath.')
    swath = list(swaths)[0]
    vrt_path = work_dir / f'{swath}.vrt'

    burst_length = burst_infos[0].length
    burst_width = burst_infos[0].width
    total_width = burst_width
    total_length = burst_length * len(burst_infos)

    vrt_dataset = ET.Element('VRTDataset', rasterXSize=str(total_width), rasterYSize=str(total_length))
    vrt_raster_band = ET.SubElement(vrt_dataset, 'VRTRasterBand', dataType='CInt16', band='1')
    no_data_value = ET.SubElement(vrt_raster_band, 'NoDataValue')
    no_data_value.text = '0.0'
    for i, burst_info in enumerate(burst_infos):
        simple_source = ET.SubElement(vrt_raster_band, 'SimpleSource')
        source_filename = ET.SubElement(simple_source, 'SourceFilename', relativeToVRT='1')
        source_filename.text = burst_info.data_path.name
        source_band = ET.SubElement(simple_source, 'SourceBand')
        source_band.text = '1'
        ET.SubElement(
            simple_source,
            'SourceProperties',
            RasterXSize=str(burst_width),
            RasterYSize=str(burst_length),
            DataType='CInt16',
        )
        ET.SubElement(
            simple_source, 'SrcRect', xOff=str(0), yOff=str(0), xSize=str(burst_width), ySize=str(burst_length)
        )
        ET.SubElement(
            simple_source,
            'DstRect',
            xOff=str(0),
            yOff=str(burst_length * i),
            xSize=str(burst_width),
            ySize=str(burst_length),
        )
    tree = ET.ElementTree(vrt_dataset)
    tree.write(vrt_path, pretty_print=True, xml_declaration=False, encoding='utf-8')
    # TODO add geotiff metadata
    gdal.Translate(str(out_path), str(vrt_path), format='GTiff')


def create_safe_directory(product_name: str, work_dir: Path) -> Path:
    """Create a directory for the SAFE file."""
    safe_dir = work_dir / product_name
    annotations_dir = safe_dir / 'annotation'
    calibration_dir = annotations_dir / 'calibration'
    noise_dir = annotations_dir / 'noise'
    rfi_dir = annotations_dir / 'rfi'
    measurements_dir = safe_dir / 'measurement'

    calibration_dir.mkdir(parents=True, exist_ok=True)
    noise_dir.mkdir(parents=True, exist_ok=True)
    rfi_dir.mkdir(parents=True, exist_ok=True)
    measurements_dir.mkdir(parents=True, exist_ok=True)
    return safe_dir


def write_xml(element: ET.Element, out_path: Path) -> None:
    tree = ET.ElementTree(element)
    ET.indent(tree, space='  ')
    tree.write(out_path, pretty_print=True, xml_declaration=True, encoding='utf-8')


def update_ads_header(ads_header: ET.Element, start_utc: datetime, stop_utc: datetime, image_number: int) -> ET.Element:
    """Update the adsHeader element with new start and stop times and image number."""
    new_ads_header = deepcopy(ads_header)
    new_ads_header.find('startTime').text = start_utc.isoformat()
    new_ads_header.find('stopTime').text = stop_utc.isoformat()
    new_ads_header.find('imageNumber').text = f'{image_number:03d}'
    return new_ads_header


def filter_elements_by_az_time(
    element: ET.Element,
    min_anx: datetime,
    max_anx: datetime,
    buffer: Optional[timedelta] = timedelta(seconds=3),
    start_line: Optional[int] = None,
) -> List[ET.Element]:
    """Filter elements by azimuth time. Optionally adjust line number."""

    min_anx_bound = min_anx - timedelta(seconds=3)
    max_anx_bound = max_anx + timedelta(seconds=3)

    list_name = element.tag
    elements = element.findall('*')
    names = list(set([x.tag for x in elements]))
    if len(names) != 1:
        raise ValueError('Element must contain only one type of subelement.')

    filtered_elements = []
    for element in elements:
        azimuth_time = datetime.fromisoformat(element.find('azimuthTime').text)
        if min_anx_bound < azimuth_time < max_anx_bound:
            filtered_elements.append(deepcopy(element))

    if start_line:
        for element in filtered_elements:
            element.find('line').text = str(int(element.find('line').text) - start_line)

    new_element = ET.Element(list_name)
    for element in filtered_elements:
        new_element.append(element)
    new_element.set('count', str(len(filtered_elements)))

    return new_element


def merge_calibration(burst_infos: Iterable[BurstInfo], image_number: int, safe_dir: Path) -> None:
    """Merge calibration data into a single file."""
    metadata_paths = list(dict.fromkeys([x.metadata_path for x in burst_infos]))
    if len(metadata_paths) != 1:
        raise UserWarning('Multiple metadata files not yet supported.')

    swath, pol = burst_infos[0].swath, burst_infos[0].polarization
    start_line = burst_infos[0].burst_index * burst_infos[0].length
    min_anx = min([x.start_utc for x in burst_infos])
    max_anx = max([x.stop_utc for x in burst_infos])

    new_calibration = ET.Element('calibration')
    calibration = get_subxml_from_burst_metadata(burst_infos[0].metadata_path, 'calibration', swath, pol)

    ads_header = update_ads_header(calibration.find('adsHeader'), min_anx, max_anx, image_number)
    new_calibration.append(ads_header)

    calibration_information = deepcopy(calibration.find('calibrationInformation'))
    new_calibration.append(calibration_information)

    cal_vectors = calibration.find('calibrationVectorList')
    new_cal_vectors = filter_elements_by_az_time(cal_vectors, min_anx, max_anx, start_line)
    new_calibration.append(new_cal_vectors)

    new_calibration_path = safe_dir / 'annotation' / 'calibration' / f'{swath}_{pol}_{image_number:03d}.xml'
    write_xml(new_calibration, new_calibration_path)


def burst2safe(granules: Iterable[str], work_dir: Optional[Path] = None) -> None:
    work_dir = optional_wd(work_dir)
    burst_infos = gather_burst_infos(granules, work_dir)
    urls = list(dict.fromkeys([x.data_url for x in burst_infos] + [x.metadata_url for x in burst_infos]))
    paths = list(dict.fromkeys([x.data_path for x in burst_infos] + [x.metadata_path for x in burst_infos]))
    for url, path in zip(urls, paths):
        asf_search.download_url(url=url, path=path.parent, filename=path.name)

    [x.add_shape_info() for x in burst_infos]
    [x.add_start_stop_utc() for x in burst_infos]

    product_name = create_product_name(burst_infos)
    safe_dir = create_safe_directory(product_name, work_dir)

    burst_infos = sort_burst_infos(burst_infos)
    swaths = list(burst_infos.keys())
    polarizations = list(burst_infos[swaths[0]].keys())
    for i, (swath, polarization) in enumerate(product(swaths, polarizations)):
        image_number = i + 1
        burst_infos = burst_infos[swath][polarization]
        measurement_name = get_measurement_name(product_name, burst_infos[0].swath, burst_infos[0].polarization, 1)
        bursts_to_tiff(burst_infos, safe_dir / 'measurement' / measurement_name, work_dir)
        merge_calibration(burst_infos, image_number, safe_dir)


def main() -> None:
    parser = ArgumentParser()
    parser.add_argument('granules', nargs='+', help='A list of burst granules to convert to SAFE')
    args = parser.parse_args()
    burst2safe(granules=args.granules)
