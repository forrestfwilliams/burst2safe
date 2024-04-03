import hashlib
from copy import deepcopy
from datetime import datetime, timedelta
from pathlib import Path
from typing import Iterable, List, Optional

import lxml.etree as ET

from burst2safe.utils import BurstInfo, drop_duplicates, flatten, get_subxml_from_metadata, set_text


SCHEMA = '{urn:ccsds:schema:xfdu:1}'


class ListOfListElements:
    def __init__(
        self, inputs: List[ET.Element], start_line: Optional[int] = None, slc_lengths: Optional[List[int]] = None
    ):
        """Initialize the ListOfListElements object.

        Args:
            inputs: The list of elements to be processed.
            start_line: The starting line number of the first element.
            slc_lengths: The total line lengths of the SLCs corresponding to each element.
        """
        self.inputs = inputs
        self.start_line = start_line
        self.slc_lengths = slc_lengths

        self.name = self.inputs[0].tag
        elements = flatten([element.findall('*') for element in self.inputs])
        names = drop_duplicates([x.tag for x in elements])
        if len(names) != 1:
            raise ValueError('Elements must contain only one type of subelement.')
        self.subelement_name = names[0]

        if self.name == 'replicaInformationList':
            self.time_field = 'referenceReplica/azimuthTime'
        elif 'azimuthTime' in [x.tag for x in elements[0].iter()]:
            self.time_field = 'azimuthTime'
        elif 'time' in [x.tag for x in elements[0].iter()]:
            self.time_field = 'time'
        else:
            raise ValueError('No time field found in element.')

        self.has_line = elements[0].find('line') is not None

    def get_unique_elements(self) -> List[ET.Element]:
        """Get the elements without duplicates. Adjust line number if present.

        Returns:
            The list of elements without duplicates.
        """
        list_of_element_lists = [item.findall('*') for item in self.inputs]

        last_time = datetime.fromisoformat(list_of_element_lists[0][-1].find(self.time_field).text)
        uniques = [deepcopy(element) for element in list_of_element_lists[0]]
        if self.has_line:
            previous_line_count = self.slc_lengths[0]

        for i, element_list in enumerate(list_of_element_lists[1:]):
            times = [datetime.fromisoformat(element.find(self.time_field).text) for element in element_list]
            keep_index = [index for index, time in enumerate(times) if time > last_time]
            to_keep = [deepcopy(element_list[index]) for index in keep_index]

            if self.has_line:
                new_lines = [int(elem.find('line').text) + previous_line_count for elem in to_keep]
                [set_text(elem.find('line'), line) for elem, line in zip(to_keep, new_lines)]
                previous_line_count += self.slc_lengths[i]

            last_time = max([times[index] for index in keep_index])
            uniques += to_keep

        return uniques

    @staticmethod
    def filter_by_line(element_list: List[ET.Element], line_bounds: tuple[float, float]) -> List[ET.Element]:
        """Filter elements by line number.

        Args:
            line_bounds: The bounds of the line numbers.

        Returns:
            A filtered element list.
        """

        new_list = []
        for elem in element_list:
            if line_bounds[0] <= int(elem.find('line').text) <= line_bounds[1]:
                new_list.append(deepcopy(elem))
        return new_list

    def create_filtered_list(
        self,
        anx_bounds: Optional[tuple[float, float]] = None,
        buffer: Optional[timedelta] = timedelta(seconds=3),
        line_bounds: Optional[tuple[float, float]] = None,
    ) -> ET.Element:
        """Filter elements by time/line. Adjust line number if present.

        Args:
            anx_bounds: The bounds of the ANX time.
            buffer: The buffer to add to the ANX bounds.
            line_bounds: The bounds of the line numbers.

        Returns:
            A filtered list element.
        """

        min_anx_bound = anx_bounds[0] - buffer
        max_anx_bound = anx_bounds[1] + buffer

        elements = self.get_unique_elements()

        filtered_elements = []
        for element in elements:
            azimuth_time = datetime.fromisoformat(element.find(self.time_field).text)
            if min_anx_bound < azimuth_time < max_anx_bound:
                filtered_elements.append(deepcopy(element))

        if self.has_line:
            for element in filtered_elements:
                standard_line = int(element.find('line').text)
                element.find('line').text = str(standard_line - self.start_line)

        if line_bounds is not None:
            if not self.has_line:
                raise ValueError('Line bounds cannot be applied to elements without line numbers.')
            filtered_elements = self.filter_by_line(filtered_elements, line_bounds)

        new_element = ET.Element(self.name)
        [new_element.append(element) for element in filtered_elements]
        new_element.set('count', str(len(filtered_elements)))
        return new_element


def create_content_unit(simple_name: str, unit_type: str, rep_id: str) -> ET.Element:
    """Create a content unit element for a manifest.safe file.

    Args:
        simple_name: The simple name of the content unit.
        unit_type: The type of the content unit.
        rep_id: The representation ID.

    Returns:
        The content unit element.
    """
    content_unit = ET.Element(f'{SCHEMA}contentUnit')
    content_unit.set('unitType', unit_type)
    content_unit.set('repID', rep_id)
    ET.SubElement(content_unit, 'dataObjectPointer', dataObjectID=simple_name)
    return content_unit


def create_metadata_object(simple_name: str) -> ET.Element:
    """Create a metadata object element for a manifest.safe file.

    Args:
        simple_name: The simple name of the metadata object.

    Returns:
        The metadata object element.
    """
    metadata_object = ET.Element('metadataObject')
    metadata_object.set('ID', f'{simple_name}Annotation')
    metadata_object.set('classification', 'DESCRIPTION')
    metadata_object.set('category', 'DMD')
    ET.SubElement(metadata_object, 'dataObjectPointer', dataObjectID=simple_name)
    return metadata_object


def create_data_object(
    simple_name: str, relative_path: Path, rep_id: str, mime_type: str, size_bytes: int, md5: str
) -> ET.Element:
    """Create a data object element for a manifest.safe file.

    Args:
        simple_name: The simple name of the data object.
        relative_path: The relative path to the data object.
        rep_id: The representation ID.
        mime_type: The MIME type of the data object.
        size_bytes: The size of the data object in bytes.
        md5: The MD5 checksum of the data object.

    Returns:
        The data object element.
    """
    data_object = ET.Element('dataObject')
    data_object.set('ID', simple_name)
    data_object.set('repID', rep_id)
    byte_stream = ET.SubElement(data_object, 'byteStream')
    byte_stream.set('mimeType', mime_type)
    byte_stream.set('size', str(size_bytes))
    file_location = ET.SubElement(byte_stream, 'fileLocation')
    file_location.set('locatorType', 'URL')
    file_location.set('href', f'./{relative_path}')
    checksum = ET.SubElement(byte_stream, 'checksum')
    checksum.set('checksumName', 'MD5')
    checksum.text = md5
    return data_object


class Annotation:
    def __init__(self, burst_infos: Iterable[BurstInfo], metadata_type: str, image_number: int):
        """Initialize the Annotation object."""
        self.burst_infos = burst_infos
        self.metadata_type = metadata_type
        self.image_number = image_number
        self.metadata_paths = drop_duplicates([x.metadata_path for x in burst_infos])
        self.swath, self.pol = burst_infos[0].swath, burst_infos[0].polarization
        self.start_line = burst_infos[0].burst_index * burst_infos[0].length
        self.total_lines = len(burst_infos) * burst_infos[0].length
        self.stop_line = self.start_line + self.total_lines
        self.min_anx = min([x.start_utc for x in burst_infos])
        self.max_anx = max([x.stop_utc for x in burst_infos])

        self.inputs = [
            get_subxml_from_metadata(path, metadata_type, self.swath, self.pol) for path in self.metadata_paths
        ]

        products = [get_subxml_from_metadata(path, 'product', self.swath, self.pol) for path in self.metadata_paths]
        slc_lengths = []
        for annotation in products:
            n_bursts = int(annotation.find('.//burstList').get('count'))
            burst_length = int(annotation.find('.//linesPerBurst').text)
            slc_lengths.append(n_bursts * burst_length)
        self.slc_lengths = slc_lengths

        # annotation components to be extended by subclasses
        self.ads_header = None
        self.xml = None

        # these attributes are updated when the annotation is written to a file
        self.size_bytes = None
        self.md5 = None

    def create_ads_header(self):
        """Create the ADS header for the annotation."""
        ads_header = deepcopy(self.inputs[0].find('adsHeader'))
        ads_header.find('startTime').text = self.min_anx.isoformat()
        ads_header.find('stopTime').text = self.max_anx.isoformat()
        ads_header.find('imageNumber').text = f'{self.image_number:03d}'
        self.ads_header = ads_header

    def write(self, out_path: Path, update_info=True) -> None:
        """Write the annotation to a file.

        Args:
            out_path: The path to write the annotation to.
            update_info: Whether to update the size and md5 attributes of the annotation.
        """
        self.xml.write(out_path, pretty_print=True, xml_declaration=True, encoding='utf-8')

        if update_info:
            self.path = out_path
            with open(out_path, 'rb') as f:
                file_bytes = f.read()
                self.size_bytes = len(file_bytes)
                self.md5 = hashlib.md5(file_bytes).hexdigest()

    def __str__(self, **kwargs):
        """Return the XML string representation of the annotation.

        Args:
            kwargs: Keyword arguments to pass to the lxml
        """
        xml_str = ET.tostring(self.xml, pretty_print=True, **kwargs)
        return xml_str.decode()

    def create_manifest_components(self):
        """Create the components for the manifest file."""
        unit_type = 'Metadata Unit'
        mime_type = 'text/xml'

        rep_id = f's1Level1{self.metadata_type.capitalize()}Schema'
        simple_name = self.path.with_suffix('').name.replace('-', '')
        if self.metadata_type == 'product':
            simple_name = f'product{simple_name}'

        safe_index = [i for i, x in enumerate(self.path.parts) if 'SAFE' in x][-1]
        safe_path = Path(*self.path.parts[: safe_index + 1])
        rel_path = self.path.relative_to(safe_path)

        content_unit = create_content_unit(simple_name, unit_type, rep_id)
        metadata_object = create_metadata_object(simple_name)
        data_object = create_data_object(simple_name, rel_path, rep_id, mime_type, self.size_bytes, self.md5)

        return content_unit, metadata_object, data_object
