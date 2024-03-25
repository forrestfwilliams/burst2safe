import hashlib
from copy import deepcopy
from datetime import datetime, timedelta
from pathlib import Path
from typing import Iterable, List, Optional

import lxml.etree as ET

from burst2safe.utils import BurstInfo, drop_duplicates, flatten, get_subxml_from_metadata


class ListOfListElements:
    def __init__(
        self, inputs: List[ET.Element], start_line: Optional[int] = None, slc_lengths: Optional[List[int]] = None
    ):
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

    def get_nonduplicate_elements(self):
        list_of_element_lists = [item.findall('*') for item in self.inputs]
        for i in range(len(list_of_element_lists)):
            if i == 0:
                last_time = datetime.fromisoformat(list_of_element_lists[i][-1].find(self.time_field).text)
                remaining_elements = [deepcopy(element) for element in list_of_element_lists[i]]
                continue

            for element in list_of_element_lists[i]:
                current_time = datetime.fromisoformat(element.find(self.time_field).text)
                if current_time > last_time:
                    new_element = deepcopy(element)
                    if self.has_line:
                        new_line = int(new_element.find('line').text) + (i * self.slc_lengths[i - 1])
                        new_element.find('line').text = str(new_line)
                    remaining_elements.append(new_element)
                    last_time = current_time

        return remaining_elements

    def create_filtered_list(
        self,
        anx_bounds: Optional[tuple[float, float]] = None,
        buffer: Optional[timedelta] = timedelta(seconds=3),
        line_bounds: Optional[tuple[float, float]] = None,
    ) -> List[ET.Element]:
        """Filter elements by time. Adjust line number if present."""

        min_anx_bound = anx_bounds[0] - buffer
        max_anx_bound = anx_bounds[1] + buffer

        elements = self.get_nonduplicate_elements()

        filtered_elements = []
        for element in elements:
            azimuth_time = datetime.fromisoformat(element.find(self.time_field).text)
            if min_anx_bound < azimuth_time < max_anx_bound:
                filtered_elements.append(deepcopy(element))

        if self.has_line:
            for element in filtered_elements:
                standard_line = int(element.find('line').text)
                element.find('line').text = str(standard_line - self.start_line)

        new_element = ET.Element(self.name)
        for element in filtered_elements:
            if line_bounds is None:
                new_element.append(element)
            else:
                if line_bounds[0] <= int(element.find('line').text) <= line_bounds[1]:
                    new_element.append(element)
        new_element.set('count', str(len(filtered_elements)))
        return new_element


class Annotation:
    def __init__(self, burst_infos: Iterable[BurstInfo], metadata_type: str, image_number: int):
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

    def create_ads_header(self):
        ads_header = deepcopy(self.inputs[0].find('adsHeader'))
        ads_header.find('startTime').text = self.min_anx.isoformat()
        ads_header.find('stopTime').text = self.max_anx.isoformat()
        ads_header.find('imageNumber').text = f'{self.image_number:03d}'
        self.ads_header = ads_header

    def write(self, out_path: Path, update_info=True) -> None:
        self.xml.write(out_path, pretty_print=True, xml_declaration=True, encoding='utf-8')

        if update_info:
            self.path = out_path
            with open(out_path, 'rb') as f:
                file_bytes = f.read()
                self.size_bytes = len(file_bytes)
                self.md5 = hashlib.md5(file_bytes).hexdigest()

    def __str__(self, **kwargs):
        xml_str = ET.tostring(self.xml, pretty_print=True, **kwargs)
        return xml_str.decode()

    def create_manifest_components(self):
        """Create the components for the manifest file."""
        unit_type = 'Metadata Unit'
        mime_type = 'text/xml'

        schema = '{urn:ccsds:schema:xfdu:1}'
        rep_id = f's1Level1{self.metadata_type.capitalize()}Schema'
        simple_name = self.path.with_suffix('').name.replace('-', '')
        if self.metadata_type == 'product':
            simple_name = f'product{simple_name}'

        content_unit = ET.Element(f'{schema}contentUnit')
        content_unit.set('unitType', unit_type)
        content_unit.set('repID', rep_id)
        ET.SubElement(content_unit, 'dataObjectPointer', dataObjectID=simple_name)

        metadata_object = ET.Element('metadataObject')
        metadata_object.set('ID', f'{simple_name}Annotation')
        metadata_object.set('classification', 'DESCRIPTION')
        metadata_object.set('category', 'DMD')
        ET.SubElement(metadata_object, 'dataObjectPointer', dataObjectID=simple_name)

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

        return content_unit, metadata_object, data_object
