"""A package for converting ASF burst SLCs to the SAFE format"""
from argparse import ArgumentParser
from dataclasses import dataclass
from datetime import datetime
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
    burst_number: int
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


def optional_wd(wd: Optional[Path | str]) -> None:
    """Return the working directory as a Path object"""
    if wd is None:
        wd = Path.cwd()
    return Path(wd)


def get_burst_info(granules: Iterable[str], work_dir: Path) -> List[BurstInfo]:
    """Get burst information from ASF Search.

    Args:
        granules: The burst granules to get information for.
        save_dir: The directory to save the data to.
    Returns:
        A list of BurstInfo objects.
    """
    work_dir = optional_wd(work_dir)
    burst_infos = []
    for granule in granules:
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
        burst_number = int(result.properties['burst']['burstIndex'])
        direction = result.properties['flightDirection'].upper()
        absolute_orbit = int(result.properties['orbit'])
        date_format = '%Y%m%dT%H%M%S'
        burst_time_str = burst_granule.split('_')[3]
        burst_time = datetime.strptime(burst_time_str, date_format)
        data_url = result.properties['url']
        data_path = work_dir / f'{burst_granule}.tiff'
        metadata_url = result.properties['additionalUrls'][0]
        metadata_path = work_dir / f'{burst_granule}.xml'

        burst_info = BurstInfo(
            burst_granule,
            slc_granule,
            swath,
            polarization,
            burst_number,
            direction,
            absolute_orbit,
            burst_time,
            data_url,
            data_path,
            metadata_url,
            metadata_path,
        )

        burst_infos.append(burst_info)
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
    product_name = f'{platfrom}-{swath.lower()}-slc-{pol.lower()}-{start}-{stop}-{orbit}-{data_take}-{image_number:03d}.tiff'
    return product_name


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
    gdal.Translate(str(out_path), str(vrt_path), format='GTiff')


def create_safe_directory(product_name: str, work_dir: Path) -> Path:
    """Create a directory for the SAFE file."""
    safe_dir = work_dir / product_name
    annotations_dir = safe_dir / 'annotation'
    measurements_dir = safe_dir / 'measurement'
    annotations_dir.mkdir(parents=True, exist_ok=True)
    measurements_dir.mkdir(parents=True, exist_ok=True)
    return safe_dir


def burst2safe(granules: Iterable[str], work_dir: Optional[Path] = None) -> None:
    work_dir = optional_wd(work_dir)
    burst_infos = get_burst_info(granules, work_dir)
    urls = [x.data_url for x in burst_infos] + [x.metadata_url for x in burst_infos]
    paths = [x.data_path for x in burst_infos] + [x.metadata_path for x in burst_infos]
    for url, path in zip(urls, paths):
        asf_search.download_url(url=url, path=path.parent, filename=path.name)
    product_name = create_product_name(burst_infos)
    safe_dir = create_safe_directory(product_name, work_dir)
    [x.add_shape_info() for x in burst_infos]
    measurement_name = get_measurement_name(product_name, burst_infos[0].swath, burst_infos[0].polarization, 1)
    bursts_to_tiff(burst_infos, safe_dir / 'measurement' / measurement_name, work_dir)


def main() -> None:
    parser = ArgumentParser()
    parser.add_argument('granules', nargs='+', help='A list of burst granules to convert to SAFE')
    args = parser.parse_args()
    burst2safe(granules=args.granules)
