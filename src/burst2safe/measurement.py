import hashlib
from datetime import datetime
from pathlib import Path
from typing import Iterable

import lxml.etree as ET
import numpy as np
from osgeo import gdal, osr

from burst2safe.product import Product
from burst2safe.utils import BurstInfo, get_subxml_from_metadata


class Measurement:
    def __init__(self, burst_infos: Iterable[BurstInfo], product_obj: Product, image_number: int):
        self.burst_infos = burst_infos
        self.product = product_obj
        self.image_number = image_number
        self.swath = burst_infos[0].swath
        self.burst_length = burst_infos[0].length
        self.burst_width = burst_infos[0].width
        self.total_width = self.burst_width
        self.total_length = self.burst_length * len(burst_infos)
        self.data_mean = None
        self.data_std = None

    def get_data(self, band: int = 1) -> np.ndarray:
        data = np.zeros((self.total_length, self.total_width), dtype=np.complex64)
        for i, burst_info in enumerate(self.burst_infos):
            ds = gdal.Open(str(burst_info.data_path))
            data[i * self.burst_length : (i + 1) * self.burst_length, :] = ds.GetRasterBand(band).ReadAsArray()
            ds = None
        return data

    def add_metadata(self, ds):
        gcps = self.product.gcps
        gdal_gcps = [gdal.GCP(gcp.x, gcp.y, gcp.z, gcp.pixel, gcp.line) for gcp in gcps]
        srs = osr.SpatialReference()
        srs.ImportFromEPSG(4326)

        manifest = get_subxml_from_metadata(self.burst_infos[0].metadata_path, 'manifest')[1]
        software = 'Sentinel-1 IPF'
        version_xml = [elem for elem in manifest.findall('.//{*}software') if elem.get('name') == software][0]
        software_version = f'{software} {version_xml.get("version")}'

        ds.SetGCPs(gdal_gcps, srs.ExportToWkt())
        ds.SetMetadataItem('TIFFTAG_DATETIME', datetime.strftime(datetime.now(), '%Y:%m:%d %H:%M:%S'))
        # TODO make sure A/B is being set correctly.
        ds.SetMetadataItem('TIFFTAG_IMAGEDESCRIPTION', 'Sentinel-1A IW SLC L1')
        ds.SetMetadataItem('TIFFTAG_IMAGEDESCRIPTION', 'Sentinel-1A IW SLC L1')
        ds.SetMetadataItem('TIFFTAG_SOFTWARE', software_version)

    def create_geotiff(self, out_path: Path, update_info=True):
        mem_drv = gdal.GetDriverByName('MEM')
        mem_ds = mem_drv.Create('', self.total_width, self.total_length, 1, gdal.GDT_CInt16)
        data = self.get_data()
        band = mem_ds.GetRasterBand(1)
        band.WriteArray(data)
        band.SetNoDataValue(0)
        self.add_metadata(mem_ds)
        gdal.Translate(str(out_path), mem_ds, format='GTiff')
        mem_ds = None
        self.path = out_path
        if update_info:
            self.data_mean = np.mean(data[data != 0])
            self.data_std = np.std(data[data != 0])
            with open(self.path, 'rb') as f:
                file_bytes = f.read()
                self.size_bytes = len(file_bytes)
                self.md5 = hashlib.md5(file_bytes).hexdigest()

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

    def write(self, out_path):
        self.create_geotiff(out_path)
