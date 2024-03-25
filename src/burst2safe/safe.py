import shutil
from copy import deepcopy
from datetime import datetime
from itertools import product
from pathlib import Path
from typing import Iterable, Optional

import lxml.etree as ET

from burst2safe.calibration import Calibration
from burst2safe.measurement import Measurement
from burst2safe.noise import Noise
from burst2safe.product import Product
from burst2safe.utils import BurstInfo, get_subxml_from_metadata, optional_wd


class Swath:
    def __init__(
        self, burst_infos: Iterable[BurstInfo], safe_path: Path, image_number: int, work_dir: Optional[Path] = None
    ):
        self.check_burst_group_validity(burst_infos)
        self.burst_infos = sorted(burst_infos, key=lambda x: x.burst_id)
        self.safe_path = safe_path
        self.image_number = image_number
        self.work_dir = optional_wd(work_dir)
        self.swath = self.burst_infos[0].swath
        self.polarization = self.burst_infos[0].polarization

        self.name = self.get_name()

        self.measurement_name = self.safe_path / 'measurement' / f'{self.name}.tiff'
        self.product_name = self.safe_path / 'annotation' / f'{self.name}.xml'
        self.noise_name = self.safe_path / 'annotation' / 'calibration' / f'noise-{self.name}.xml'
        self.calibration_name = self.safe_path / 'annotation' / 'calibration' / f'calibration-{self.name}.xml'

    @staticmethod
    def check_burst_group_validity(burst_infos):
        swaths = set([x.swath for x in burst_infos])
        if len(swaths) != 1:
            raise ValueError('All bursts must be from the same swath.')

        polarizations = set([x.polarization for x in burst_infos])
        if len(polarizations) != 1:
            raise ValueError('All bursts must have the same polarization.')

    def get_name(self) -> str:
        swath = self.swath.lower()
        pol = self.polarization.lower()
        start = datetime.strftime(min([x.start_utc for x in self.burst_infos]), '%Y%m%dt%H%M%S')
        stop = datetime.strftime(max([x.stop_utc for x in self.burst_infos]), '%Y%m%dt%H%M%S')

        safe_name = self.safe_path.name
        platfrom, _, _, _, _, _, _, orbit, data_take, _ = safe_name.lower().split('_')
        swath_name = f'{platfrom}-{swath}-slc-{pol}-{start}-{stop}-{orbit}-{data_take}-{self.image_number:03d}'
        return swath_name

    def assemble(self):
        self.measurement = Measurement(self.burst_infos, self.image_number, self.work_dir)
        self.product = Product(self.burst_infos, self.image_number)
        self.noise = Noise(self.burst_infos, self.image_number)
        self.calibration = Calibration(self.burst_infos, self.image_number)
        self.annotations = [self.product, self.noise, self.calibration]
        self.components = [self.measurement, self.product, self.noise, self.calibration]

        for component in self.components:
            component.assemble()

    def write(self):
        self.measurement.write(self.measurement_name)
        self.product.write(self.product_name)
        self.noise.write(self.noise_name)
        self.calibration.write(self.calibration_name)

    def create_manifest_components(self):
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


class Safe:
    def __init__(self, burst_infos: Iterable[BurstInfo], work_dir: Optional[Path] = None):
        # TODO: Check burst group validity for multiple swaths
        self.burst_infos = burst_infos
        self.work_dir = optional_wd(work_dir)

        self.grouped_burst_infos = self.group_burst_infos(burst_infos)
        self.name = self.get_name(self.burst_infos)
        self.safe_path = self.work_dir / self.name
        self.swaths = []

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
            swath = Swath(burst_infos, self.safe_path, image_number, self.work_dir)
            swath.assemble()
            swath.write()
            self.swaths.append(swath)

    def create_manifest(self):
        manifest_name = self.safe_path / 'manifest.safe'
        manifest = Manifest(self)
        manifest.assemble()
        manifest.write(manifest_name)

    def create_safe(self):
        self.create_dir_structure()
        self.create_safe_components()
        self.create_manifest()
        return self.safe_path


class Manifest:
    def __init__(self, safe: Safe):
        self.safe = safe
        self.content_units = []
        self.metadata_objects = []
        self.data_objects = []

        for swath in self.safe.swaths:
            for annotation in swath.annotations:
                content_unit, metadata_object, date_object = annotation.create_manifest_components()
                self.content_units.append(content_unit)
                self.metadata_objects.append(metadata_object)
                self.data_objects.append(date_object)
            measurement_content, measurement_data = swath.measurement.create_manifest_components()
            self.content_units.append(measurement_content)
            self.data_objects.append(measurement_data)

        safe_ns = 'http://www.esa.int/safe/sentinel-1.0'
        self.namespaces = {
            'xsi': 'http://www.w3.org/2001/XMLSchema-instance',
            'gml': 'http://www.opengis.net/gml',
            'xfdu': 'urn:ccsds:schema:xfdu:1',
            'safe': safe_ns,
            's1': f'{safe_ns}/sentinel-1',
            's1sar': f'{safe_ns}/sentinel-1/sar',
            's1sarl1': f'{safe_ns}/sentinel-1/sar/level-1',
            's1sarl2': f'{safe_ns}/sentinel-1/sar/level-2',
            'gx': 'http://www.google.com/kml/ext/2.2',
        }
        self.version = 'esa/safe/sentinel-1.0/sentinel-1/sar/level-1/slc/standard/iwdp'

    def create_information_package_map(self):
        xdfu_ns = self.namespaces['xfdu']
        information_package_map = ET.Element(f'{{{xdfu_ns}}}informationPackageMap')
        parent_content_unit = ET.Element(
            f'{{{xdfu_ns}}}contentUnit',
            unitType='SAFE Archive Information Package',
            textInfo='Sentinel-1 IW Level-1 SLC Product',
            dmdID='acquisitionPeriod platform generalProductInformation measurementOrbitReference measurementFrameSet',
            pdiID='processing',
        )
        for content_unit in self.content_units:
            parent_content_unit.append(content_unit)

        information_package_map.append(parent_content_unit)
        self.information_package_map = information_package_map

    def create_metadata_section(self):
        metadata_section = ET.Element('metadataSection')
        for metadata_object in self.metadata_objects:
            metadata_section.append(metadata_object)

        first_manifest = get_subxml_from_metadata(self.safe.burst_infos[0].metadata_path, 'manifest')[1]
        ids_to_keep = [
            'processing',
            'platform',
            'measurementOrbitReference',
            'generalProductInformation',
            'acquisitionPeriod',
            'measurementFrameSet',
        ]
        section = 'metadataSection'
        [metadata_section.append(deepcopy(x)) for x in first_manifest.find(section) if x.get('ID') in ids_to_keep]

        self.metadata_section = metadata_section

    def create_data_object_section(self):
        self.data_object_section = ET.Element('dataObjectSection')
        for data_object in self.data_objects:
            self.data_object_section.append(data_object)

    def assemble(self):
        self.create_information_package_map()
        self.create_metadata_section()
        self.create_data_object_section()

        manifest = ET.Element('{%s}XFDU' % self.namespaces['xfdu'], nsmap=self.namespaces)
        manifest.set('version', self.version)
        manifest.append(self.information_package_map)
        manifest.append(self.metadata_section)
        manifest.append(self.data_object_section)
        manifest_tree = ET.ElementTree(manifest)

        ET.indent(manifest_tree, space='  ')
        self.xml = manifest_tree

    def write(self, out_path: Path) -> None:
        self.xml.write(out_path, pretty_print=True, xml_declaration=True, encoding='utf-8')
        self.path = out_path
