"""A package for converting ASF burst SLCs to the SAFE format"""
import hashlib
import os
import shutil
import warnings
from argparse import ArgumentParser
from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime, timedelta
from itertools import product
from pathlib import Path
from typing import Iterable, List, Optional

import asf_search
import crcmod
import lxml.etree as ET
import numpy as np
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
        annotation = get_subxml_from_burst_metadata(self.metadata_path, 'product', self.swath, self.polarization)
        start_utc_str = annotation.findall('.//burst')[self.burst_index].find('azimuthTime').text
        self.start_utc = datetime.fromisoformat(start_utc_str)
        # TODO: this is slightly wrong, but it's close enough for now
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


def create_product_name(burst_infos: Iterable[BurstInfo], unique_id: Optional[str] = None) -> str:
    """Create a product name for the SAFE file."""
    platform, beam_mode, product_type = burst_infos[0].slc_granule.split('_')[:3]
    product_info = f'1SS{burst_infos[0].polarization[0]}'
    min_date = min([x.date for x in burst_infos]).strftime('%Y%m%dT%H%M%S')
    max_date = max([x.date for x in burst_infos]).strftime('%Y%m%dT%H%M%S')
    absolute_orbit = f'{burst_infos[0].absolute_orbit:06d}'
    mission_data_take = burst_infos[0].slc_granule.split('_')[-2]
    if unique_id is None:
        unique_id = '0000'
    product_name = f'{platform}_{beam_mode}_{product_type}__{product_info}_{min_date}_{max_date}_{absolute_orbit}_{mission_data_take}_{unique_id}.SAFE'
    return product_name


def get_swath_name(product_name: str, burst_infos: Iterable[BurstInfo], image_number: int) -> str:
    """Create a measurement name for given dataset."""
    swath = burst_infos[0].swath.lower()
    pol = burst_infos[0].polarization.lower()
    start = datetime.strftime(min([x.start_utc for x in burst_infos]), '%Y%m%dt%H%M%S')
    stop = datetime.strftime(max([x.stop_utc for x in burst_infos]), '%Y%m%dt%H%M%S')

    platfrom, _, _, _, _, _, _, orbit, data_take, _ = product_name.lower().split('_')
    swath_name = f'{platfrom}-{swath}-slc-{pol}-{start}-{stop}-{orbit}-{data_take}-{image_number:03d}'
    return swath_name


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
    rfi_dir = annotations_dir / 'rfi'
    measurements_dir = safe_dir / 'measurement'

    calibration_dir.mkdir(parents=True, exist_ok=True)
    rfi_dir.mkdir(parents=True, exist_ok=True)
    measurements_dir.mkdir(parents=True, exist_ok=True)

    xsd_dir = Path(__file__).parent / 'data'
    shutil.copytree(xsd_dir, safe_dir / 'support')
    return safe_dir


def write_xml(element: ET.Element, out_path: Path) -> None:
    tree = ET.ElementTree(element)
    ET.indent(tree, space='  ')
    tree.write(out_path, pretty_print=True, xml_declaration=True, encoding='utf-8')


def prettyprint(element, **kwargs):
    xml = ET.tostring(element, pretty_print=True, **kwargs)
    print(xml.decode(), end='')


def update_ads_header(ads_header: ET.Element, start_utc: datetime, stop_utc: datetime, image_number: int) -> ET.Element:
    """Update the adsHeader element with new start and stop times and image number."""
    new_ads_header = deepcopy(ads_header)
    new_ads_header.find('startTime').text = start_utc.isoformat()
    new_ads_header.find('stopTime').text = stop_utc.isoformat()
    new_ads_header.find('imageNumber').text = f'{image_number:03d}'
    return new_ads_header


def filter_elements_by_time(
    element: ET.Element,
    min_anx: datetime,
    max_anx: datetime,
    start_line: Optional[int] = None,
    buffer: Optional[timedelta] = timedelta(seconds=3),
    line_bounds: Optional[tuple[float, float]] = None,
) -> List[ET.Element]:
    """Filter elements by azimuth time. Optionally adjust line number."""

    min_anx_bound = min_anx - buffer
    max_anx_bound = max_anx + buffer

    list_name = element.tag
    elements = element.findall('*')
    names = list(set([x.tag for x in elements]))
    if len(names) != 1:
        raise ValueError('Element must contain only one type of subelement.')

    if 'azimuthTime' in [x.tag for x in elements[0].iter()]:
        time_field = 'azimuthTime'
    elif 'time' in [x.tag for x in elements[0].iter()]:
        time_field = 'time'
    else:
        raise ValueError('No time field found in element.')

    filtered_elements = []
    for element in elements:
        azimuth_time = datetime.fromisoformat(element.find(time_field).text)
        if min_anx_bound < azimuth_time < max_anx_bound:
            filtered_elements.append(deepcopy(element))

    if start_line:
        for element in filtered_elements:
            standard_line = int(element.find('line').text)
            element.find('line').text = str(standard_line - start_line)

    new_element = ET.Element(list_name)
    for element in filtered_elements:
        if line_bounds is None:
            new_element.append(element)
        else:
            if line_bounds[0] <= int(element.find('line').text) <= line_bounds[1]:
                new_element.append(element)
    new_element.set('count', str(len(filtered_elements)))

    return new_element


def prep_info(burst_infos: Iterable[BurstInfo], data_type: str):
    metadata_paths = list(dict.fromkeys([x.metadata_path for x in burst_infos]))
    if len(metadata_paths) != 1:
        raise UserWarning('Multiple metadata files not yet supported.')

    swath, pol = burst_infos[0].swath, burst_infos[0].polarization
    start_line = burst_infos[0].burst_index * burst_infos[0].length
    min_anx = min([x.start_utc for x in burst_infos])
    max_anx = max([x.stop_utc for x in burst_infos])

    element = get_subxml_from_burst_metadata(burst_infos[0].metadata_path, data_type, swath, pol)
    return element, min_anx, max_anx, start_line


def merge_calibration(burst_infos: Iterable[BurstInfo], out_path: Path) -> None:
    """Merge calibration data into a single file."""
    calibration, min_anx, max_anx, start_line = prep_info(burst_infos, 'calibration')
    new_calibration = ET.Element('calibration')

    image_number = int(out_path.with_suffix('').name.split('-')[-1])
    ads_header = update_ads_header(calibration.find('adsHeader'), min_anx, max_anx, image_number)
    new_calibration.append(ads_header)

    calibration_information = deepcopy(calibration.find('calibrationInformation'))
    new_calibration.append(calibration_information)

    cal_vectors = calibration.find('calibrationVectorList')
    new_cal_vectors = filter_elements_by_time(cal_vectors, min_anx, max_anx, start_line)
    new_calibration.append(new_cal_vectors)

    write_xml(new_calibration, out_path)


def merge_noise(burst_infos: Iterable[BurstInfo], out_path: Path):
    """Merge noise data into a single file."""
    noise, min_anx, max_anx, start_line = prep_info(burst_infos, 'noise')
    new_noise = ET.Element('noise')

    image_number = int(out_path.with_suffix('').name.split('-')[-1])
    ads_header = update_ads_header(noise.find('adsHeader'), min_anx, max_anx, image_number)
    new_noise.append(ads_header)

    noise_rg = noise.find('noiseRangeVectorList')
    new_noise_rg = filter_elements_by_time(noise_rg, min_anx, max_anx, start_line)
    new_noise.append(new_noise_rg)

    new_noise_az = deepcopy(noise.findall('noiseAzimuthVectorList/noiseAzimuthVector'))[0]
    line_element = new_noise_az.find('line')

    lines = np.array([int(x) for x in line_element.text.split(' ')])
    lines -= start_line
    first_index = np.where(lines == lines[lines <= 0].max())[0][0]
    last_index = np.where(lines == lines[lines >= ((burst_infos[0].length * len(burst_infos)) - 1)].min())[0][0]
    last_index += 1  # add one to make it inclusive

    new_noise_az.find('lastAzimuthLine').text = str(lines[last_index - 1])

    line_element.text = ' '.join([str(x) for x in lines[first_index:last_index]])
    line_element.set('count', str(last_index - first_index))

    az_lut_element = new_noise_az.find('noiseAzimuthLut')
    az_lut_element.text = ' '.join(az_lut_element.text.split(' ')[first_index:last_index])
    az_lut_element.set('count', str(last_index - first_index))

    # TODO: will there sometime be more than one noiseAzimuthVector?
    new_noise_az_list = ET.Element('noiseAzimuthVectorList')
    new_noise_az_list.set('count', '1')
    new_noise_az_list.append(new_noise_az)

    new_noise.append(new_noise_az_list)

    write_xml(new_noise, out_path)


def create_empty_xml_list(name: str, sub_name: Optional[str] = None) -> ET.Element:
    """Create an empty XML list with a given name."""
    element = ET.Element(name)
    list_name = f'{name}List' if sub_name is None else sub_name
    list_element = ET.SubElement(element, list_name)
    list_element.set('count', '0')
    return element


def merge_product(burst_infos: Iterable[BurstInfo], out_path: Path):
    """Merge annotation data into a single file."""
    annotation, min_anx, max_anx, start_line = prep_info(burst_infos, 'product')
    new_annotation = ET.Element('product')

    image_number = int(out_path.with_suffix('').name.split('-')[-1])
    ads_header = update_ads_header(annotation.find('adsHeader'), min_anx, max_anx, image_number)
    new_annotation.append(ads_header)

    quality = deepcopy(annotation.find('qualityInformation'))
    new_annotation.append(quality)

    xml_lists = {}
    for list_name in ['orbitList', 'attitudeList', 'noiseList', 'terrainHeightList', 'azimuthFmRateList']:
        if list_name == 'orbitList':
            buffer = 30
        else:
            buffer = 5

        xml_list = annotation.find(f'generalAnnotation/{list_name}')
        new_xml_list = filter_elements_by_time(xml_list, min_anx, max_anx, buffer=timedelta(seconds=buffer))
        xml_lists[list_name] = new_xml_list

    new_general = ET.Element('generalAnnotation')
    new_general.append(deepcopy(annotation.find('generalAnnotation/productInformation')))
    new_general.append(deepcopy(annotation.find('generalAnnotation/downlinkInformationList')))
    new_general.append(xml_lists['orbitList'])
    new_general.append(xml_lists['attitudeList'])
    new_general.append(deepcopy(annotation.find('generalAnnotation/rawDataAnalysisList')))
    new_general.append(deepcopy(annotation.find('generalAnnotation/replicaInformationList')))
    new_general.append(xml_lists['noiseList'])
    new_general.append(xml_lists['terrainHeightList'])
    new_general.append(xml_lists['azimuthFmRateList'])
    new_annotation.append(new_general)

    new_image_info = ET.Element('imageInformation')
    start_time = ET.SubElement(new_image_info, 'productFirstLineUtcTime')
    start_time.text = min_anx.isoformat()
    stop_time = ET.SubElement(new_image_info, 'productLastLineUtcTime')
    stop_time.text = max_anx.isoformat()
    new_image_info.append(deepcopy(annotation.find('imageAnnotation/imageInformation/ascendingNodeTime')))
    new_image_info.append(deepcopy(annotation.find('imageAnnotation/imageInformation/anchorTime')))
    composition = ET.SubElement(new_image_info, 'productComposition')
    composition.text = 'Assembled'
    slice_number = ET.SubElement(new_image_info, 'sliceNumber')
    slice_number.text = '0'
    slice_list = ET.SubElement(new_image_info, 'sliceList')
    slice_list.set('count', '0')
    copy_list = [
        'slantRangeTime',
        'pixelValue',
        'outputPixels',
        'rangePixelSpacing',
        'azimuthPixelSpacing',
        'azimuthTimeInterval',
        'azimuthFrequency',
        'numberOfSamples',
    ]
    for element_name in copy_list:
        new_image_info.append(deepcopy(annotation.find(f'imageAnnotation/imageInformation/{element_name}')))

    n_lines = ET.SubElement(new_image_info, 'numberOfLines')
    n_lines.text = str(burst_infos[0].length * len(burst_infos))

    copy_list = ['zeroDopMinusAcqTime', 'incidenceAngleMidSwath', 'imageStatistics']
    for element_name in copy_list:
        new_image_info.append(deepcopy(annotation.find(f'imageAnnotation/imageInformation/{element_name}')))

    # TODO: recalculate imageStatistics

    new_image = ET.Element('imageAnnotation')
    new_image.append(new_image_info)
    new_image.append(deepcopy(annotation.find('imageAnnotation/processingInformation')))

    new_annotation.append(new_image)

    dop_centroid_list = annotation.find('dopplerCentroid/dcEstimateList')
    new_dop_centroid_list = filter_elements_by_time(dop_centroid_list, min_anx, max_anx)
    new_dop_centroid = ET.Element('dopplerCentroid')
    new_dop_centroid.append(new_dop_centroid_list)
    new_annotation.append(new_dop_centroid)

    antenna_list = annotation.find('antennaPattern/antennaPatternList')
    new_antenna_list = filter_elements_by_time(antenna_list, min_anx, max_anx)
    new_antenna = ET.Element('antennaPattern')
    new_antenna.append(new_antenna_list)
    new_annotation.append(new_antenna)

    swath_timing = annotation.find('swathTiming')
    bursts = swath_timing.find('burstList')
    new_bursts = filter_elements_by_time(bursts, min_anx, max_anx, buffer=timedelta(seconds=0.5))
    new_swath_timing = ET.Element('swathTiming')
    new_swath_timing.append(deepcopy(swath_timing.find('linesPerBurst')))
    new_swath_timing.append(deepcopy(swath_timing.find('samplesPerBurst')))
    new_swath_timing.append(new_bursts)
    new_annotation.append(new_swath_timing)

    gcp_list = annotation.find('geolocationGrid/geolocationGridPointList')
    new_gcp_list = filter_elements_by_time(
        gcp_list, min_anx, max_anx, start_line, line_bounds=[0, burst_infos[0].length * len(burst_infos)]
    )
    new_gcp = ET.Element('geolocationGrid')
    new_gcp.append(new_gcp_list)
    new_annotation.append(new_gcp)

    # Both of these fields are not used for SLCs, only GRDs
    new_annotation.append(create_empty_xml_list('coordinateConversion'))
    new_annotation.append(create_empty_xml_list('swathMerging', 'swathMergeList'))

    write_xml(new_annotation, out_path)


def calculate_crc16(file_path: Path):
    """Calculate the CRC16 checksum for a file."""
    with open(file_path, 'rb') as f:
        data = f.read()

    # TODO: this doesn't match the ESA checksum
    crc16 = crcmod.predefined.mkPredefinedCrcFun('crc-16')
    crc16_value = crc16(data)
    crc16_hex = hex(crc16_value)[2:].zfill(4).upper()
    return crc16_hex


def create_manifest_components(item_path: Path, item_type: str):
    """Create the components of the manifest file."""
    if item_type in ['product', 'noise', 'calibration', 'rfi']:
        unit_type = 'Metadata Unit'
        mime_type = 'text/xml'
        create_metadata_element = True
    elif item_type == 'measurement':
        unit_type = 'Measurement Data Unit'
        mime_type = 'application/octet-stream'
        create_metadata_element = False
    else:
        raise ValueError(f'Item type {item_type} not recognized.')

    schema = '{urn:ccsds:schema:xfdu:1}'
    rep_id = f's1Level1{item_type.capitalize()}Schema'
    simple_name = item_path.with_suffix('').name.replace('-', '')
    if item_type == 'product':
        simple_name = f'product{simple_name}'

    content_unit = ET.Element(f'{schema}contentUnit')
    content_unit.set('unitType', unit_type)
    content_unit.set('repID', rep_id)
    ET.SubElement(content_unit, 'dataObjectPointer', dataObjectID=simple_name)

    if create_metadata_element:
        metadata_object = ET.Element('metadataObject')
        metadata_object.set('ID', f'{simple_name}Annotation')
        metadata_object.set('classification', 'DESCRIPTION')
        metadata_object.set('category', 'DMD')
        ET.SubElement(metadata_object, 'dataObjectPointer', dataObjectID=simple_name)
    else:
        metadata_object = None

    with open(item_path, 'rb') as f:
        item_bytes = f.read()
        item_length = len(item_bytes)
        item_md5 = hashlib.md5(item_bytes).hexdigest()

    safe_index = [i for i, x in enumerate(item_path.parts) if 'SAFE' in x][-1]
    safe_path = Path(*item_path.parts[: safe_index + 1])
    relative_path = item_path.relative_to(safe_path)

    data_object = ET.Element('dataObject')
    data_object.set('ID', simple_name)
    data_object.set('repID', rep_id)
    byte_stream = ET.SubElement(data_object, 'byteStream')
    byte_stream.set('mimeType', mime_type)
    byte_stream.set('size', str(item_length))
    file_location = ET.SubElement(byte_stream, 'fileLocation')
    file_location.set('locatorType', 'URL')
    file_location.set('href', f'./{relative_path}')
    checksum = ET.SubElement(byte_stream, 'checksum')
    checksum.set('checksumName', 'MD5')
    checksum.text = item_md5

    return content_unit, metadata_object, data_object


def create_manifest(template_manifset: ET.Element, assets: dict, out_path: Path) -> None:
    """Create a manifest file for the SAFE product."""

    schema = '{urn:ccsds:schema:xfdu:1}'
    manifest = deepcopy(template_manifset)
    sets = {
        f'informationPackageMap/{schema}contentUnit': 'content_unit',
        'metadataSection': 'metadata_object',
        'dataObjectSection': 'data_object',
    }
    metadata_ids_keep = [
        'processing',
        'platform',
        'measurementOrbitReference',
        'generalProductInformation',
        'acquisitionPeriod',
        'measurementFrameSet',
    ]
    copied_metadata = [deepcopy(x) for x in manifest.find('metadataSection') if x.get('ID') in metadata_ids_keep]

    for element_name, asset_type in sets.items():
        element = manifest.find(element_name)
        for child in element:
            element.remove(child)

        for item in assets[asset_type]:
            element.append(item)

    content_section = manifest.find(f'informationPackageMap/{schema}contentUnit')
    for item in assets['content_unit_measurement']:
        content_section.append(item)

    metadata_section = manifest.find('metadataSection')
    for item in copied_metadata:
        metadata_section.append(item)

    data_section = manifest.find('dataObjectSection')
    for item in assets['data_object_measurement']:
        data_section.append(item)

    write_xml(manifest, out_path)


def burst2safe(granules: Iterable[str], work_dir: Optional[Path] = None) -> None:
    work_dir = optional_wd(work_dir)
    burst_infos = gather_burst_infos(granules, work_dir)
    urls = list(dict.fromkeys([x.data_url for x in burst_infos] + [x.metadata_url for x in burst_infos]))
    paths = list(dict.fromkeys([x.data_path for x in burst_infos] + [x.metadata_path for x in burst_infos]))
    for url, path in zip(urls, paths):
        asf_search.download_url(url=url, path=path.parent, filename=path.name)

    [x.add_shape_info() for x in burst_infos]
    [x.add_start_stop_utc() for x in burst_infos]
    breakpoint()

    safe_name = create_product_name(burst_infos)
    safe_dir = create_safe_directory(safe_name, work_dir)

    burst_infos = sort_burst_infos(burst_infos)
    swaths = list(burst_infos.keys())
    polarizations = list(burst_infos[swaths[0]].keys())
    manifest_data = {
        'content_unit': [],
        'metadata_object': [],
        'data_object': [],
        'content_unit_measurement': [],
        'data_object_measurement': [],
    }
    for i, (swath, polarization) in enumerate(product(swaths, polarizations)):
        image_number = i + 1
        burst_infos = burst_infos[swath][polarization]
        swath_name = get_swath_name(safe_name, burst_infos, image_number)

        measurement_name = safe_dir / 'measurement' / f'{swath_name}.tiff'
        bursts_to_tiff(burst_infos, measurement_name, work_dir)
        content, _, data = create_manifest_components(measurement_name, 'measurement')
        manifest_data['content_unit_measurement'].append(content)
        manifest_data['data_object_measurement'].append(data)

        product_name = safe_dir / 'annotation' / f'{swath_name}.xml'
        merge_product(burst_infos, product_name)
        content, metadata, data = create_manifest_components(product_name, 'product')
        manifest_data['content_unit'].append(content)
        manifest_data['metadata_object'].append(metadata)
        manifest_data['data_object'].append(data)

        noise_name = safe_dir / 'annotation' / 'calibration' / f'noise-{swath_name}.xml'
        merge_noise(burst_infos, noise_name)
        content, metadata, data = create_manifest_components(noise_name, 'noise')
        manifest_data['content_unit'].append(content)
        manifest_data['metadata_object'].append(metadata)
        manifest_data['data_object'].append(data)

        calibration_name = safe_dir / 'annotation' / 'calibration' / f'calibration-{swath_name}.xml'
        merge_calibration(burst_infos, calibration_name)
        content, metadata, data = create_manifest_components(calibration_name, 'calibration')
        manifest_data['content_unit'].append(content)
        manifest_data['metadata_object'].append(metadata)
        manifest_data['data_object'].append(data)

    manifest_name = safe_dir / 'manifest.safe'
    template_manifest = get_subxml_from_burst_metadata(burst_infos[0].metadata_path, 'manifest')[1]
    create_manifest(template_manifest, manifest_data, manifest_name)

    # crc16 = calculate_crc16(manifest_name)
    # new_safe_name = safe_name.replace('0000', crc16)
    # if Path(new_safe_name).exists():
    #     shutil.rmtree(new_safe_name)
    # os.rename(safe_name, new_safe_name)


def main() -> None:
    parser = ArgumentParser()
    parser.add_argument('granules', nargs='+', help='A list of burst granules to convert to SAFE')
    args = parser.parse_args()
    burst2safe(granules=args.granules)
