import hashlib
from pathlib import Path
from typing import Iterable

import lxml.etree as ET
from osgeo import gdal

from burst2safe.utils import BurstInfo


class Measurement:
    def __init__(self, burst_infos: Iterable[BurstInfo], image_number: int, work_dir: Path):
        self.burst_infos = burst_infos
        self.image_number = image_number
        self.work_dir = work_dir

        self.swath = burst_infos[0].swath
        self.vrt_path = work_dir / f'{self.swath}.vrt'

        self.burst_length = burst_infos[0].length
        self.burst_width = burst_infos[0].width
        self.total_width = self.burst_width
        self.total_length = self.burst_length * len(burst_infos)

    def create_vrt(self):
        vrt_dataset = ET.Element('VRTDataset', rasterXSize=str(self.total_width), rasterYSize=str(self.total_length))
        vrt_raster_band = ET.SubElement(vrt_dataset, 'VRTRasterBand', dataType='CInt16', band='1')
        no_data_value = ET.SubElement(vrt_raster_band, 'NoDataValue')
        no_data_value.text = '0.0'
        for i, burst_info in enumerate(self.burst_infos):
            simple_source = ET.SubElement(vrt_raster_band, 'SimpleSource')
            source_filename = ET.SubElement(simple_source, 'SourceFilename', relativeToVRT='1')
            source_filename.text = burst_info.data_path.name
            source_band = ET.SubElement(simple_source, 'SourceBand')
            source_band.text = '1'
            ET.SubElement(
                simple_source,
                'SourceProperties',
                RasterXSize=str(self.burst_width),
                RasterYSize=str(self.burst_length),
                DataType='CInt16',
            )
            ET.SubElement(
                simple_source,
                'SrcRect',
                xOff=str(0),
                yOff=str(0),
                xSize=str(self.burst_width),
                ySize=str(self.burst_length),
            )
            ET.SubElement(
                simple_source,
                'DstRect',
                xOff=str(0),
                yOff=str(self.burst_length * i),
                xSize=str(self.burst_width),
                ySize=str(self.burst_length),
            )
        tree = ET.ElementTree(vrt_dataset)
        tree.write(self.vrt_path, pretty_print=True, xml_declaration=False, encoding='utf-8')

    def create_geotiff(self, out_path: Path, update_info=True):
        gdal.Translate(str(out_path), str(self.vrt_path), format='GTiff')
        if update_info:
            self.path = out_path
            with open(self.path, 'rb') as f:
                file_bytes = f.read()
                self.size_bytes = len(file_bytes)
                self.md5 = hashlib.md5(file_bytes).hexdigest()

    # TODO add geotiff metadata
    # def add_metadata(self):

    def create_manifest_components(self):
        unit_type = 'Measurement Data Unit'
        mime_type = 'application/octet-stream'

        schema = '{urn:ccsds:schema:xfdu:1}'
        rep_id = 's1Level1MeasurementSchema'
        simple_name = self.path.with_suffix('').name.replace('-', '')

        content_unit = ET.Element(f'{schema}contentUnit')
        content_unit.set('unitType', unit_type)
        content_unit.set('repID', rep_id)
        ET.SubElement(content_unit, 'dataObjectPointer', dataObjectID=simple_name)

        safe_index = [i for i, x in enumerate(self.path.parts) if 'SAFE' in x][-1]
        safe_path = Path(*self.path.parts[: safe_index + 1])
        relative_path = self.path.relative_to(safe_path)

        data_object = ET.Element('dataObject')
        data_object.set('ID', simple_name)
        data_object.set('repID', rep_id)
        byte_stream = ET.SubElement(data_object, 'byteStream')
        byte_stream.set('mimeType', mime_type)
        byte_stream.set('size', str(self.size_bytes))
        file_location = ET.SubElement(byte_stream, 'fileLocation')
        file_location.set('locatorType', 'URL')
        file_location.set('href', f'./{relative_path}')
        checksum = ET.SubElement(byte_stream, 'checksum')
        checksum.set('checksumName', 'MD5')
        checksum.text = self.md5

        return content_unit, data_object

    def assemble(self):
        self.create_vrt()

    def write(self, out_path):
        self.create_geotiff(out_path)
