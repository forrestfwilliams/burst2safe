from datetime import datetime
from pathlib import Path
from typing import Iterable

from shapely.geometry import MultiPoint, Polygon

from burst2safe.calibration import Calibration
from burst2safe.measurement import Measurement
from burst2safe.noise import Noise
from burst2safe.product import Product
from burst2safe.utils import BurstInfo, get_subxml_from_metadata


class Swath:
    """Class representing a single swath (and polarization) of a SAFE file."""

    def __init__(self, burst_infos: Iterable[BurstInfo], safe_path: Path, image_number: int):
        """Initialize a Swath object."""
        self.check_burst_group_validity(burst_infos)
        self.burst_infos = sorted(burst_infos, key=lambda x: x.burst_id)
        self.safe_path = safe_path
        self.image_number = image_number
        self.swath = self.burst_infos[0].swath
        self.polarization = self.burst_infos[0].polarization

        self.name = self.get_name()
        self.version = self.get_ipf_version(self.burst_infos[0].metadata_path)
        self.major_version, self.minor_version = [int(x) for x in self.version.split('.')]

        self.measurement_name = self.safe_path / 'measurement' / f'{self.name}.tiff'
        self.product_name = self.safe_path / 'annotation' / f'{self.name}.xml'
        self.noise_name = self.safe_path / 'annotation' / 'calibration' / f'noise-{self.name}.xml'
        self.calibration_name = self.safe_path / 'annotation' / 'calibration' / f'calibration-{self.name}.xml'

        # Set on write
        self.bbox = None

    @staticmethod
    def check_burst_group_validity(burst_infos: Iterable[BurstInfo]):
        """Check that the burst group is valid.

        The burst group must:
        - Not contain duplicate granules
        - Have the same absolute orbit
        - Be from the same swath
        - Have the same polarization
        - Have consecutive burst IDs

        Args:
            burst_infos: A list of BurstInfo objects
        """
        granules = [x.granule for x in burst_infos]
        duplicates = list(set([x for x in granules if granules.count(x) > 1]))
        if duplicates:
            raise ValueError(f'Found duplicate granules: {duplicates}.')

        orbits = set([x.absolute_orbit for x in burst_infos])
        if len(orbits) != 1:
            raise ValueError(f'All bursts must have the same absolute orbit. Found: {orbits}.')

        swaths = set([x.swath for x in burst_infos])
        if len(swaths) != 1:
            raise ValueError(f'All bursts must be from the same swath. Found: {swaths}.')

        polarizations = set([x.polarization for x in burst_infos])
        if len(polarizations) != 1:
            raise ValueError(f'All bursts must have the same polarization. Found: {polarizations}.')

        burst_ids = [x.burst_id for x in burst_infos]
        burst_ids.sort()
        if burst_ids != list(range(min(burst_ids), max(burst_ids) + 1)):
            raise ValueError(f'All bursts must have consecutive burst IDs. Found: {burst_ids}.')

    @staticmethod
    def get_ipf_version(metadata_path: Path) -> str:
        """Get the IPF version from the parent manifest file.

        Returns:
            The IPF version as a string
        """
        manifest = get_subxml_from_metadata(metadata_path, 'manifest')
        version_xml = [elem for elem in manifest.findall('.//{*}software') if elem.get('name') == 'Sentinel-1 IPF'][0]
        return version_xml.get('version')

    def get_name(self) -> str:
        """Get the name of the swath. Will be used to name constituent output files.

        Returns:
            The name of the swath
        """
        swath = self.swath.lower()
        pol = self.polarization.lower()
        start = datetime.strftime(min([x.start_utc for x in self.burst_infos]), '%Y%m%dt%H%M%S')
        stop = datetime.strftime(max([x.stop_utc for x in self.burst_infos]), '%Y%m%dt%H%M%S')

        safe_name = self.safe_path.name
        platfrom, _, _, _, _, _, _, orbit, data_take, _ = safe_name.lower().split('_')
        swath_name = f'{platfrom}-{swath}-slc-{pol}-{start}-{stop}-{orbit}-{data_take}-{self.image_number:03d}'
        return swath_name

    def get_bbox(self):
        """Get the bounding box of the swath using the Product GCPs.

        Returns:
            The bounding box of the swath
        """
        points = MultiPoint([(gcp.x, gcp.y) for gcp in self.product.gcps])
        min_rotated_rect = points.minimum_rotated_rectangle
        bbox = Polygon(min_rotated_rect.exterior)
        return bbox

    def assemble(self):
        """Assemble the components of the Swath."""
        self.product = Product(self.burst_infos, self.image_number)
        self.noise = Noise(self.burst_infos, self.image_number)
        self.calibration = Calibration(self.burst_infos, self.image_number)
        self.annotations = [self.product, self.noise, self.calibration]
        for component in self.annotations:
            component.assemble()

        self.measurement = Measurement(self.burst_infos, self.product.gcps, self.version, self.image_number)

    def write(self, update_info: bool = True):
        """Write the Swath componets to the SAFE directory.

        Args:
            update_info: Whether to update the bounding box of the Swath
        """
        self.measurement.write(self.measurement_name)
        self.product.update_data_stats(self.measurement.data_mean, self.measurement.data_std)
        self.product.write(self.product_name)
        self.noise.write(self.noise_name)
        self.calibration.write(self.calibration_name)
        if update_info:
            self.bbox = self.get_bbox()

    def create_manifest_components(self):
        """Create the manifest components for the Swath."""
        self.manifest_components = {
            'content_unit': [],
            'metadata_object': [],
            'data_object': [],
            'content_unit_measurement': [],
            'data_object_measurement': [],
        }
        for annotation in self.annotations:
            content, metadata, data = annotation.create_manifest_components()
            self.manifest_components['content_unit'].append(content)
            self.manifest_components['metadata_object'].append(metadata)
            self.manifest_components['data_object'].append(data)

        content, data = self.measurement.create_manifest_components()
        self.manifest_components['content_unit_measurement'].append(content)
        self.manifest_components['data_object_measurement'].append(data)
