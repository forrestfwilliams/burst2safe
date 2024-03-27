from copy import deepcopy
from dataclasses import dataclass
from datetime import timedelta
from typing import Iterable

import lxml.etree as ET
import numpy as np

from burst2safe.base import Annotation, ListOfListElements
from burst2safe.utils import BurstInfo, flatten


@dataclass
class GeoPoint:
    x: float
    y: float
    z: float
    line: int
    pixel: int


class Product(Annotation):
    def __init__(self, burst_infos: Iterable[BurstInfo], image_number: int):
        super().__init__(burst_infos, 'product', image_number)
        self.qulatity_information = None
        self.general_annotation = None
        self.image_annotation = None
        self.doppler_centroid = None
        self.antenna_pattern = None
        self.swath_timing = None
        self.geolocation_grid = None
        self.coordinate_conversion = None
        self.swath_merging = None
        self.gcps = []

    def create_quality_information(self):
        quality_information = ET.Element('qualityInformation')
        quality_information.append(deepcopy(self.inputs[0].find('qualityInformation/productQualityIndex')))

        quality_datas = flatten([cal.findall('qualityInformation/qualityDataList/qualityData') for cal in self.inputs])
        quality_data_list = ET.Element('qualityDataList')
        quality_data_list.set('count', str(len(quality_datas)))
        for quality_data in quality_datas:
            quality_data_list.append(deepcopy(quality_data))

        quality_information.append(quality_data_list)

        self.quality_information = quality_information

    def create_general_annotation(self):
        """The productInformation sub-record contains single value fields that
        are merged and included. All other sub-records contain lists which are
        concatenated. Details are presented in Table 3-11."""
        general_annotation = ET.Element('generalAnnotation')

        product_information = deepcopy(self.inputs[0].find('generalAnnotation/productInformation'))
        # TODO: productInformation/platformHeading should be calculated more accurately
        product_information.find('platformHeading').text = ''
        general_annotation.append(product_information)

        lists = [
            'downlinkInformationList',
            'orbitList',
            'attitudeList',
            'rawDataAnalysisList',
            'replicaInformationList',
            'noiseList',
            'terrainHeightList',
            'azimuthFmRateList',
        ]
        for list_name in lists:
            list_elements = [prod.find(f'generalAnnotation/{list_name}') for prod in self.inputs]
            if list_name == 'replicaInformationList':
                lol = ListOfListElements(list_elements, self.start_line, self.slc_lengths)
                unique = lol.get_nonduplicate_elements()
                filtered = ET.Element('replicaInformationList')
                filtered.set('count', str(len(unique)))
                [filtered.append(element) for element in unique]
            else:
                lol = ListOfListElements(list_elements, self.start_line, self.slc_lengths)
                filtered = lol.create_filtered_list([self.min_anx, self.max_anx], buffer=timedelta(seconds=500))

            general_annotation.append(filtered)

        self.general_annotation = general_annotation

    def create_image_annotation(self):
        """This DSR contains two records which contain only single value fields.
        The fields in the imageInformation record are included and merged
        and all the fields for the processingInformation record are included;
        except for the inputDimensionsList record, which is concatenated.
        Details are presented in Table 3-12."""
        image_annotation = ET.Element('imageAnnotation')

        image_information = deepcopy(self.inputs[0].find('imageAnnotation/imageInformation'))
        image_information.find('productFirstLineUtcTime').text = self.min_anx.isoformat()
        image_information.find('productLastLineUtcTime').text = self.max_anx.isoformat()
        image_information.find('productComposition').text = 'Assembled'
        image_information.find('sliceNumber').text = '0'

        slice_list = image_information.find('sliceList')
        slice_list.set('count', '0')
        for element in slice_list:
            slice_list.remove(element)

        image_information.find('numberOfLines').text = str(self.total_lines)

        az_spacing_path = 'imageAnnotation/imageInformation/azimuthPixelSpacing'
        az_spacing = np.mean([float(prod.find(az_spacing_path).text) for prod in self.inputs])
        image_information.find('azimuthPixelSpacing').text = f'{az_spacing:.6e}'

        image_information.find('imageStatistics/outputDataMean/re').text = ''
        image_information.find('imageStatistics/outputDataMean/im').text = ''
        image_information.find('imageStatistics/outputDataStdDev/re').text = ''
        image_information.find('imageStatistics/outputDataStdDev/im').text = ''

        image_annotation.append(image_information)

        processing_information = deepcopy(self.inputs[0].find('imageAnnotation/processingInformation'))
        dimensions_list = processing_information.find('inputDimensionsList')
        for element in slice_list:
            dimensions_list.remove(element)

        list_elements = [prod.find('imageAnnotation/processingInformation/inputDimensionsList') for prod in self.inputs]
        lol = ListOfListElements(list_elements, self.start_line, self.slc_lengths)
        filtered = lol.create_filtered_list([self.min_anx, self.max_anx])
        [dimensions_list.append(element) for element in filtered]

        image_annotation.append(processing_information)
        self.image_annotation = image_annotation

    def update_data_stats(self, data_mean, data_std):
        base_path = 'imageInformation/imageStatistics/outputData'
        data_mean_re = f'{data_mean.real:.6e}'
        data_mean_im = f'{data_mean.imag:.6e}'
        data_std_re = f'{data_std.real:.6e}'
        data_std_im = f'{data_std.imag:.6e}'

        for elem in [self.image_annotation, self.xml.find('imageAnnotation')]:
            elem.find(f'{base_path}Mean/re').text = data_mean_re
            elem.find(f'{base_path}Mean/im').text = data_mean_im
            elem.find(f'{base_path}StdDev/re').text = data_std_re
            elem.find(f'{base_path}StdDev/im').text = data_std_im

    def create_doppler_centroid(self):
        dc_lists = [prod.find('dopplerCentroid/dcEstimateList') for prod in self.inputs]
        dc_lol = ListOfListElements(dc_lists, self.start_line, self.slc_lengths)
        filtered = dc_lol.create_filtered_list([self.min_anx, self.max_anx])
        doppler_centroid = ET.Element('dopplerCentroid')
        doppler_centroid.append(filtered)
        self.doppler_centroid = doppler_centroid

    def create_antenna_pattern(self):
        pattern_lists = [prod.find('antennaPattern/antennaPatternList') for prod in self.inputs]
        pattern_lol = ListOfListElements(pattern_lists, self.start_line, self.slc_lengths)
        filtered = pattern_lol.create_filtered_list([self.min_anx, self.max_anx])
        antenna_pattern = ET.Element('antennaPattern')
        antenna_pattern.append(filtered)
        self.antenna_pattern = antenna_pattern

    def create_swath_timing(self):
        burst_lists = [prod.find('swathTiming/burstList') for prod in self.inputs]
        burst_lol = ListOfListElements(burst_lists, self.start_line, self.slc_lengths)
        filtered = burst_lol.create_filtered_list([self.min_anx, self.max_anx], buffer=timedelta(seconds=0.1))

        # TODO: This is needed since we always buffer backward AND forward
        if int(filtered.get('count')) > len(self.burst_infos):
            filtered.remove(filtered[-1])
            filtered.set('count', str(int(filtered.get('count')) - 1))

        # TODO: need to update burst byteOffset field
        for burst in filtered:
            burst.find('byteOffset').text = ''

        swath_timing = ET.Element('swathTiming')
        swath_timing.append(deepcopy(self.inputs[0].find('swathTiming/linesPerBurst')))
        swath_timing.append(deepcopy(self.inputs[0].find('swathTiming/samplesPerBurst')))
        swath_timing.append(filtered)
        self.swath_timing = swath_timing

    def create_geolocation_grid(self):
        grid_points = [prod.find('geolocationGrid/geolocationGridPointList') for prod in self.inputs]
        grid_point_lol = ListOfListElements(grid_points, self.start_line, self.slc_lengths)
        filtered = grid_point_lol.create_filtered_list([self.min_anx, self.max_anx], line_bounds=[0, self.total_lines])
        geolocation_grid = ET.Element('geolocationGrid')
        geolocation_grid.append(filtered)
        self.geolocation_grid = geolocation_grid

        gcp_xmls = geolocation_grid.find('geolocationGridPointList').findall('*')
        for gcp_xml in gcp_xmls:
            gcp = GeoPoint(
                float(gcp_xml.find('longitude').text),
                float(gcp_xml.find('latitude').text),
                float(gcp_xml.find('height').text),
                int(gcp_xml.find('line').text),
                int(gcp_xml.find('pixel').text),
            )
            self.gcps.append(gcp)

    def create_coordinate_conversion(self):
        coordinate_conversion = ET.Element('coordinateConversion')
        coordinate_conversion_list = ET.SubElement(coordinate_conversion, 'coordinateConversionList')
        coordinate_conversion_list.set('count', '0')
        self.coordinate_conversion = coordinate_conversion

    def create_swath_merging(self):
        swath_merging = ET.Element('swathMerging')
        swath_merge_list = ET.SubElement(swath_merging, 'swathMergeList')
        swath_merge_list.set('count', '0')
        self.swath_merging = swath_merging

    def assemble(self):
        self.create_ads_header()
        self.create_quality_information()
        self.create_general_annotation()
        self.create_image_annotation()
        self.create_doppler_centroid()
        self.create_antenna_pattern()
        self.create_swath_timing()
        self.create_geolocation_grid()
        self.create_coordinate_conversion()
        self.create_swath_merging()

        product = ET.Element('product')
        product.append(self.ads_header)
        product.append(self.quality_information)
        product.append(self.general_annotation)
        product.append(self.image_annotation)
        product.append(self.doppler_centroid)
        product.append(self.antenna_pattern)
        product.append(self.swath_timing)
        product.append(self.geolocation_grid)
        product.append(self.coordinate_conversion)
        product.append(self.swath_merging)
        product_tree = ET.ElementTree(product)

        ET.indent(product_tree, space='  ')
        self.xml = product_tree
