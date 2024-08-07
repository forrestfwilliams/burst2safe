from copy import deepcopy
from pathlib import Path
from typing import List

import lxml.etree as ET
import numpy as np
from shapely.geometry import Polygon

from burst2safe.utils import calculate_crc16


SAFE_NS = 'http://www.esa.int/safe/sentinel-1.0'
NAMESPACES = {
    'xsi': 'http://www.w3.org/2001/XMLSchema-instance',
    'gml': 'http://www.opengis.net/gml',
    'xfdu': 'urn:ccsds:schema:xfdu:1',
    'safe': SAFE_NS,
    's1': f'{SAFE_NS}/sentinel-1',
    's1sar': f'{SAFE_NS}/sentinel-1/sar',
    's1sarl1': f'{SAFE_NS}/sentinel-1/sar/level-1',
    's1sarl2': f'{SAFE_NS}/sentinel-1/sar/level-2',
    'gx': 'http://www.google.com/kml/ext/2.2',
}


def get_footprint_string(bbox: Polygon, x_first=True) -> str:
    """Get a string representation of the footprint of the product.

    Args:
        bbox: The bounding box of the product
        x_first: Whether to put the x coordinate first or second

    Returns:
        A string representation of the product footprint
    """
    coords = [(np.round(y, 6), np.round(x, 6)) for x, y in bbox.exterior.coords]
    # TODO: order assumes descending
    coords = [coords[2], coords[3], coords[0], coords[1]]
    if x_first:
        coords_str = ' '.join([f'{x},{y}' for x, y in coords])
    else:
        coords_str = ' '.join([f'{y},{x}' for x, y in coords])
    return coords_str


class Manifest:
    """Class representing a SAFE manifest."""

    def __init__(
        self,
        content_units: List[ET.Element],
        metadata_objects: List[ET.Element],
        data_objects: List[ET.Element],
        bbox: Polygon,
        template_manifest: ET.Element,
    ):
        """Initialize a Manifest object.

        Args:
            content_units: A list of contentUnit elements
            metadata_objects: A list of metadataObject elements
            data_objects: A list of dataObject elements
            bbox: The bounding box of the product
            template_manifest: The template manifest to generate unalterd metadata from
        """
        self.content_units = content_units
        self.metadata_objects = metadata_objects
        self.data_objects = data_objects
        self.bbox = bbox
        self.template = template_manifest
        self.version = 'esa/safe/sentinel-1.0/sentinel-1/sar/level-1/slc/standard/iwdp'

        # Updated by methods
        self.information_package_map = None
        self.metadata_section = None
        self.data_object_section = None
        self.xml = None
        self.path = None
        self.crc = None

    def create_information_package_map(self):
        """Create the information package map."""
        xdfu_ns = NAMESPACES['xfdu']
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
        """Create the metadata section."""
        metadata_section = ET.Element('metadataSection')
        for metadata_object in self.metadata_objects:
            metadata_section.append(metadata_object)

        ids_to_keep = [
            'processing',
            'platform',
            'measurementOrbitReference',
            'generalProductInformation',
            'acquisitionPeriod',
            'measurementFrameSet',
        ]
        section = 'metadataSection'
        [metadata_section.append(deepcopy(x)) for x in self.template.find(section) if x.get('ID') in ids_to_keep]

        coordinates = metadata_section.find('.//{*}coordinates')
        coordinates.text = get_footprint_string(self.bbox)

        self.metadata_section = metadata_section

    def create_data_object_section(self):
        """Create the data object section."""
        self.data_object_section = ET.Element('dataObjectSection')
        for data_object in self.data_objects:
            self.data_object_section.append(data_object)

    def assemble(self):
        """Assemble the components of the SAFE manifest."""
        self.create_information_package_map()
        self.create_metadata_section()
        self.create_data_object_section()

        manifest = ET.Element('{%s}XFDU' % NAMESPACES['xfdu'], nsmap=NAMESPACES)
        manifest.set('version', self.version)
        manifest.append(self.information_package_map)
        manifest.append(self.metadata_section)
        manifest.append(self.data_object_section)
        manifest_tree = ET.ElementTree(manifest)

        ET.indent(manifest_tree, space='  ')
        self.xml = manifest_tree

    def write(self, out_path: Path, update_info: bool = True) -> None:
        """Write the SAFE manifest to a file. Optionally update the path and CRC.

        Args:
            out_path: The path to write the manifest to
            update_info: Whether to update the path and CRC
        """
        self.xml.write(out_path, pretty_print=True, xml_declaration=True, encoding='utf-8')
        if update_info:
            self.path = out_path
            self.crc = calculate_crc16(self.path)


class Kml:
    """Class representing a SAFE manifest."""

    def __init__(self, bbox: Polygon):
        """Initialize a KML object.

        Args:
            bbox: The bounding box of the product
        """
        self.bbox = bbox
        self.xml = None

    def assemble(self):
        """Assemble the components of the SAFE KML preview file."""
        kml = ET.Element('kml', nsmap=NAMESPACES)
        document = ET.SubElement(kml, 'Document')
        doc_name = ET.SubElement(document, 'name')
        doc_name.text = 'Sentinel-1 Map Overlay'

        folder = ET.SubElement(document, 'Folder')
        folder_name = ET.SubElement(folder, 'name')
        folder_name.text = 'Sentinel-1 Scene Overlay'

        ground_overlay = ET.SubElement(folder, 'GroundOverlay')
        ground_overlay_name = ET.SubElement(ground_overlay, 'name')
        ground_overlay_name.text = 'Sentinel-1 Image Overlay'
        icon = ET.SubElement(ground_overlay, 'Icon')
        href = ET.SubElement(icon, 'href')
        # TODO: we intentionally don't create this image because we don't know how to.
        href.text = 'quick-look.png'
        lat_lon_quad = ET.SubElement(ground_overlay, f'{{{NAMESPACES["gx"]}}}LatLonQuad')
        coordinates = ET.SubElement(lat_lon_quad, 'coordinates')
        coordinates.text = get_footprint_string(self.bbox, x_first=False)

        kml_tree = ET.ElementTree(kml)
        ET.indent(kml_tree, space='  ')
        self.xml = kml_tree

    def write(self, out_path: Path, update_info: bool = True) -> None:
        """Write the SAFE kml to a file.

        Args:
            out_path: The path to write the manifest to
            update_info: Whether to update the path
        """
        self.xml.write(out_path, pretty_print=True, xml_declaration=True, encoding='utf-8')
        if update_info:
            self.path = out_path
