import shutil
from itertools import product
from pathlib import Path
from typing import Iterable, List, Optional, Tuple

import numpy as np
from shapely.geometry import MultiPolygon, Polygon

from burst2safe.manifest import Manifest
from burst2safe.swath import Swath
from burst2safe.utils import BurstInfo, drop_duplicates, get_subxml_from_metadata, optional_wd


class Safe:
    """Class representing a SAFE file."""

    def __init__(self, burst_infos: Iterable[BurstInfo], work_dir: Optional[Path] = None):
        """Initialize a Safe object.

        Args:
            burst_infos: A list of BurstInfo objects
            work_dir: The directory to create the SAFE in
        """
        self.burst_infos = burst_infos
        self.work_dir = optional_wd(work_dir)

        self.check_group_validity(self.burst_infos)

        self.grouped_burst_infos = self.group_burst_infos(self.burst_infos)
        self.name = self.get_name(self.burst_infos)
        self.safe_path = self.work_dir / self.name
        self.swaths = []
        self.manifest = None

        self.version = self.get_ipf_version(self.burst_infos[0].metadata_path)
        self.major_version, self.minor_version = [int(x) for x in self.version.split('.')]

    @staticmethod
    def check_group_validity(burst_infos: Iterable[BurstInfo]):
        """Check that the burst group is valid.

        A valid burst group must:
        - Have the same acquisition mode
        - Be from the same absolute orbit
        - Be contiguous in time and space
        - Have the same footprint for all included polarizations

        Args:
            burst_infos: A list of BurstInfo objects
        """
        swaths = sorted(list(set([info.swath for info in burst_infos])))
        polarizations = sorted(list(set([info.polarization for info in burst_infos])))
        burst_range = {}
        for swath in swaths:
            burst_range[swath] = {}
            for pol in polarizations:
                burst_subset = [info for info in burst_infos if info.swath == swath and info.polarization == pol]
                if len(burst_subset) == 0:
                    burst_range[swath][pol] = [0, 0]
                    continue
                Swath.check_burst_group_validity(burst_subset)

                burst_ids = [info.burst_id for info in burst_subset]
                burst_range[swath][pol] = [min(burst_ids), max(burst_ids)]

            start_ids = [id_range[0] for id_range in burst_range[swath].values()]
            if len(set(start_ids)) != 1:
                raise ValueError(
                    f'Polarization groups in swath {swath} do not have same start burst id. Found {start_ids}'
                )

            end_ids = [id_range[1] for id_range in burst_range[swath].values()]
            if len(set(end_ids)) != 1:
                raise ValueError(f'Polarization groups in swath {swath} do not have same end burst id. Found {end_ids}')

        if len(swaths) == 1:
            return

        swath_combos = [[swaths[i], swaths[i + 1]] for i in range(len(swaths) - 1)]
        working_pol = polarizations[0]
        for swath1, swath2 in swath_combos:
            min_diff = burst_range[swath1][working_pol][0] - burst_range[swath2][working_pol][1]
            if np.abs(min_diff) > 1:
                raise ValueError(f'Products from swaths {swath1} and {swath2} do not overlap')
            max_diff = burst_range[swath1][working_pol][1] - burst_range[swath2][working_pol][0]
            if np.abs(max_diff) > 1:
                raise ValueError(f'Products from swaths {swath1} and {swath2} do not overlap')

    @staticmethod
    def get_name(burst_infos: Iterable[BurstInfo], unique_id: str = '0000') -> str:
        """Create a name for the SAFE file.

        Args:
            burst_infos: A list of BurstInfo objects
            unique_id: A unique identifier for the SAFE file

        Returns:
            The name of the SAFE file
        """
        platform, beam_mode, product_type = burst_infos[0].slc_granule.split('_')[:3]
        product_info = f'1SS{burst_infos[0].polarization[0]}'
        min_date = min([x.date for x in burst_infos]).strftime('%Y%m%dT%H%M%S')
        max_date = max([x.date for x in burst_infos]).strftime('%Y%m%dT%H%M%S')
        absolute_orbit = f'{burst_infos[0].absolute_orbit:06d}'
        mission_data_take = burst_infos[0].slc_granule.split('_')[-2]
        product_name = f'{platform}_{beam_mode}_{product_type}__{product_info}_{min_date}_{max_date}_{absolute_orbit}_{mission_data_take}_{unique_id}.SAFE'
        return product_name

    @staticmethod
    def group_burst_infos(burst_infos: Iterable[BurstInfo]) -> dict:
        """Group burst infos by swath and polarization.

        Args:
            burst_infos: A list of BurstInfo objects

        Returns:
            A dictionary of burst infos grouped by swath, then polarization
        """
        burst_dict = {}
        for burst_info in burst_infos:
            if burst_info.swath not in burst_dict:
                burst_dict[burst_info.swath] = {}

            if burst_info.polarization not in burst_dict[burst_info.swath]:
                burst_dict[burst_info.swath][burst_info.polarization] = []

            burst_dict[burst_info.swath][burst_info.polarization].append(burst_info)

        swaths = list(burst_dict.keys())
        polarizations = list(burst_dict[swaths[0]].keys())
        for swath, polarization in zip(swaths, polarizations):
            burst_dict[swath][polarization] = sorted(burst_dict[swath][polarization], key=lambda x: x.burst_id)

        return burst_dict

    @staticmethod
    def get_ipf_version(metadata_path: Path) -> str:
        """Get the IPF version from the parent manifest file.

        Returns:
            The IPF version as a string
        """
        manifest = get_subxml_from_metadata(metadata_path, 'manifest')
        version_xml = [elem for elem in manifest.findall('.//{*}software') if elem.get('name') == 'Sentinel-1 IPF'][0]
        return version_xml.get('version')

    def get_bbox(self):
        """Get the bounding box for the SAFE file.

        Returns:
            A Polygon object representing the bounding box
        """
        bboxs = MultiPolygon([swath.bbox for swath in self.swaths])
        min_rotated_rect = bboxs.minimum_rotated_rectangle
        bbox = Polygon(min_rotated_rect.exterior)
        return bbox

    def create_dir_structure(self) -> Path:
        """Create a directory for the SAFE file.

        Returns:
            The path to the SAFE directory
        """
        measurements_dir = self.safe_path / 'measurement'
        annotations_dir = self.safe_path / 'annotation'
        calibration_dir = annotations_dir / 'calibration'
        rfi_dir = annotations_dir / 'rfi'

        calibration_dir.mkdir(parents=True, exist_ok=True)
        measurements_dir.mkdir(parents=True, exist_ok=True)
        if self.major_version >= 3 and self.minor_version >= 40:
            rfi_dir.mkdir(parents=True, exist_ok=True)

        xsd_dir = Path(__file__).parent / 'data'
        shutil.copytree(xsd_dir, self.safe_path / 'support', dirs_exist_ok=True)

    def create_safe_components(self):
        """Create the components (data and metadata files) of the SAFE file."""
        swaths = list(self.grouped_burst_infos.keys())
        polarizations = list(self.grouped_burst_infos[swaths[0]].keys())
        for i, (swath, polarization) in enumerate(product(swaths, polarizations)):
            image_number = i + 1
            burst_infos = self.grouped_burst_infos[swath][polarization]
            swath = Swath(burst_infos, self.safe_path, self.version, image_number)
            swath.assemble()
            swath.write()
            self.swaths.append(swath)

    def compile_manifest_components(self) -> Tuple[List, List, List]:
        """Compile the manifest components for all files within the SAFE file.

        Returns:
            A list of content units, metadata objects, and data objects for the manifest file
        """
        content_units = []
        metadata_objects = []
        data_objects = []
        for swath in self.swaths:
            for annotation in swath.annotations:
                content_unit, metadata_object, date_object = annotation.create_manifest_components()
                content_units.append(content_unit)
                metadata_objects.append(metadata_object)
                data_objects.append(date_object)
            measurement_content, measurement_data = swath.measurement.create_manifest_components()
            content_units.append(measurement_content)
            data_objects.append(measurement_data)
        return content_units, metadata_objects, data_objects

    def create_manifest(self):
        """Create the manifest.safe file for the SAFE file."""
        manifest_name = self.safe_path / 'manifest.safe'
        content_units, metadata_objects, data_objects = self.compile_manifest_components()
        template_manifest = get_subxml_from_metadata(self.burst_infos[0].metadata_path, 'manifest')
        manifest = Manifest(content_units, metadata_objects, data_objects, self.get_bbox(), template_manifest)
        manifest.assemble()
        manifest.write(manifest_name)
        self.manifest = manifest

    def update_product_identifier(self):
        """Update the product identifier using the CRC of the manifest file."""
        new_new = self.get_name(self.burst_infos, unique_id=self.manifest.crc)
        new_path = self.work_dir / new_new
        if new_path.exists():
            shutil.rmtree(new_path)
        shutil.move(self.safe_path, new_path)
        self.name = new_new
        self.safe_path = new_path

    def create_safe(self):
        """Create the SAFE file."""
        self.create_dir_structure()
        self.create_safe_components()
        self.create_manifest()
        self.update_product_identifier()
        return self.safe_path

    def cleanup(self):
        to_delete = [burst_info.data_path for burst_info in self.burst_infos]
        to_delete += [burst_info.metadata_path for burst_info in self.burst_infos]
        to_delete = drop_duplicates(to_delete)
        for file in to_delete:
            file.unlink()
