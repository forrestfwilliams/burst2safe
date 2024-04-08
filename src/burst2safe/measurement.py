import hashlib
from datetime import datetime
from pathlib import Path
from typing import Iterable, Tuple

import numpy as np
from osgeo import gdal, osr

from burst2safe.base import create_content_unit, create_data_object
from burst2safe.product import GeoPoint
from burst2safe.utils import BurstInfo, get_subxml_from_metadata


class Measurement:
    """Class representing a measurement GeoTIFF."""

    def __init__(self, burst_infos: Iterable[BurstInfo], gcps: Iterable[GeoPoint], image_number: int):
        """Initialize a Measurement object.

        Args:
            burst_infos: A list of BurstInfo objects
            gcps: A list of GeoPoint objects
            image_number: The image number of the measurement
        """
        self.burst_infos = burst_infos
        self.gcps = gcps
        self.image_number = image_number

        self.swath = self.burst_infos[0].swath
        self.burst_length = self.burst_infos[0].length
        self.burst_width = self.burst_infos[0].width
        self.total_width = self.burst_width
        self.total_length = self.burst_length * len(self.burst_infos)
        self.data_mean = None
        self.data_std = None
        self.size_bytes = None
        self.md5 = None

    def get_data(self, band: int = 1) -> np.ndarray:
        """Get the data from the measurement from ASF burst GeoTIFFs.

        Args:
            band: The GeoTIFF band to read

        Returns:
            The data from burst GeoTIFFs as a numpy array
        """
        data = np.zeros((self.total_length, self.total_width), dtype=np.complex64)
        for i, burst_info in enumerate(self.burst_infos):
            ds = gdal.Open(str(burst_info.data_path))
            data[i * self.burst_length : (i + 1) * self.burst_length, :] = ds.GetRasterBand(band).ReadAsArray()
            ds = None
        return data

    @staticmethod
    def get_ipf_version(metadata_path: Path) -> str:
        """Get the IPF version from the parent manifest file.

        Returns:
            The IPF version as a string
        """
        manifest = get_subxml_from_metadata(metadata_path, 'manifest')
        version_xml = [elem for elem in manifest.findall('.//{*}software') if elem.get('name') == 'Sentinel-1 IPF'][0]
        return version_xml.get('version')

    def add_metadata(self, dataset: gdal.Dataset):
        """Add metadata to an existing GDAL dataset.

        Args:
            dataset: The GDAL dataset to add metadata to
        """
        gdal_gcps = [gdal.GCP(gcp.x, gcp.y, gcp.z, gcp.pixel, gcp.line) for gcp in self.gcps]
        srs = osr.SpatialReference()
        srs.ImportFromEPSG(4326)
        dataset.SetGCPs(gdal_gcps, srs.ExportToWkt())

        dataset.SetMetadataItem('TIFFTAG_DATETIME', datetime.strftime(datetime.now(), '%Y:%m:%d %H:%M:%S'))
        # TODO make sure A/B is being set correctly.
        dataset.SetMetadataItem('TIFFTAG_IMAGEDESCRIPTION', 'Sentinel-1A IW SLC L1')

        version = self.get_ipf_version(self.burst_infos[0].metadata_path)
        software_version = f'Sentinel-1 IPF {version}'
        dataset.SetMetadataItem('TIFFTAG_SOFTWARE', software_version)

    def create_geotiff(self, out_path: Path, update_info=True):
        """Create a GeoTIFF of SLC data from the constituent burst SLC GeoTIFFs.
        Optionally update Measurment metadata.

        Args:
            out_path: The path to write the SLC GeoTIFF to
            update_info: Whether to update the Measurement metadata
        """
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

    def create_manifest_components(self) -> Tuple:
        """Create the components of the SAFE manifest for the measurement file.

        Returns:
            A tuple of the content unit and data object for the measurement file
        """
        simple_name = self.path.with_suffix('').name.replace('-', '')
        rep_id = 's1Level1MeasurementSchema'
        unit_type = 'Measurement Data Unit'
        mime_type = 'application/octet-stream'

        safe_index = [i for i, x in enumerate(self.path.parts) if 'SAFE' in x][-1]
        safe_path = Path(*self.path.parts[: safe_index + 1])
        relative_path = self.path.relative_to(safe_path)

        content_unit = create_content_unit(simple_name, rep_id, unit_type)
        data_object = create_data_object(simple_name, relative_path, rep_id, mime_type, self.size_bytes, self.md5)
        return content_unit, data_object

    def write(self, out_path):
        """Write the measurement GeoTIFF to a file."""
        self.create_geotiff(out_path)
