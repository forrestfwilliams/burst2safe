import shutil
from itertools import product
from pathlib import Path
from typing import Iterable, Optional

import numpy as np
from shapely.geometry import MultiPolygon, Polygon

from burst2safe.manifest import Manifest
from burst2safe.swath import Swath
from burst2safe.utils import BurstInfo, get_subxml_from_metadata, optional_wd


class Safe:
    def __init__(self, burst_infos: Iterable[BurstInfo], work_dir: Optional[Path] = None):
        self.burst_infos = burst_infos
        self.work_dir = optional_wd(work_dir)

        self.check_group_validity(self.burst_infos)

        self.grouped_burst_infos = self.group_burst_infos(self.burst_infos)
        self.name = self.get_name(self.burst_infos)
        self.safe_path = self.work_dir / self.name
        self.swaths = []

    @staticmethod
    def check_group_validity(burst_infos: Iterable[BurstInfo]):
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
        
        # Don't think I need this check
        # pols = [f'({", ".join(sorted(keys))})' for keys in burst_range.values()]
        # if len(set(pols)) != 1:
        #     raise ValueError(f'Swaths do not have same polarization groups. Found {pols}')

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
        """Create a product name for the SAFE file."""
        platform, beam_mode, product_type = burst_infos[0].slc_granule.split('_')[:3]
        product_info = f'1SS{burst_infos[0].polarization[0]}'
        min_date = min([x.date for x in burst_infos]).strftime('%Y%m%dT%H%M%S')
        max_date = max([x.date for x in burst_infos]).strftime('%Y%m%dT%H%M%S')
        absolute_orbit = f'{burst_infos[0].absolute_orbit:06d}'
        mission_data_take = burst_infos[0].slc_granule.split('_')[-2]
        product_name = f'{platform}_{beam_mode}_{product_type}__{product_info}_{min_date}_{max_date}_{absolute_orbit}_{mission_data_take}_{unique_id}.SAFE'
        return product_name

    @staticmethod
    def group_burst_infos(burst_info_list):
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

    def get_bbox(self):
        bboxs = MultiPolygon([swath.bbox for swath in self.swaths])
        min_rotated_rect = bboxs.minimum_rotated_rectangle
        bbox = Polygon(min_rotated_rect.exterior)
        return bbox

    def create_dir_structure(self) -> Path:
        """Create a directory for the SAFE file."""
        measurements_dir = self.safe_path / 'measurement'
        annotations_dir = self.safe_path / 'annotation'
        calibration_dir = annotations_dir / 'calibration'

        calibration_dir.mkdir(parents=True, exist_ok=True)
        measurements_dir.mkdir(parents=True, exist_ok=True)

        xsd_dir = Path(__file__).parent / 'data'
        shutil.copytree(xsd_dir, self.safe_path / 'support', dirs_exist_ok=True)

    def create_safe_components(self):
        swaths = list(self.grouped_burst_infos.keys())
        polarizations = list(self.grouped_burst_infos[swaths[0]].keys())
        for i, (swath, polarization) in enumerate(product(swaths, polarizations)):
            image_number = i + 1
            burst_infos = self.grouped_burst_infos[swath][polarization]
            swath = Swath(burst_infos, self.safe_path, image_number)
            swath.assemble()
            swath.write()
            self.swaths.append(swath)

    def compile_manifest_components(self):
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
        manifest_name = self.safe_path / 'manifest.safe'
        content_units, metadata_objects, data_objects = self.compile_manifest_components()
        template_manifest = get_subxml_from_metadata(self.burst_infos[0].metadata_path, 'manifest')
        manifest = Manifest(content_units, metadata_objects, data_objects, self.get_bbox(), template_manifest)
        manifest.assemble()
        manifest.write(manifest_name)

    def create_safe(self):
        self.create_dir_structure()
        self.create_safe_components()
        self.create_manifest()
        return self.safe_path
