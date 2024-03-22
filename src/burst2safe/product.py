from copy import deepcopy
from datetime import timedelta
from typing import Iterable

import lxml.etree as ET

from burst2safe.base import Annotation, ListOfListElements
from burst2safe.utils import BurstInfo, flatten


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
        pass

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
        # TODO: need to update burst byteOffsets
        burst_lists = [prod.find('swathTiming/burstList') for prod in self.inputs]
        burst_lol = ListOfListElements(burst_lists, self.start_line, self.slc_lengths)
        filtered = burst_lol.create_filtered_list([self.min_anx, self.max_anx], buffer=timedelta(seconds=0.5))

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

    def create_coordinate_conversion(self):
        coordinate_conversion = ET.Element('coordinateConversion')
        coordinate_conversion.set('count', '0')
        coordinate_conversion.append(ET.Element('coordinateConversionList'))
        self.coordinate_conversion = coordinate_conversion

    def create_swath_merging(self):
        swath_merging = ET.Element('swathMerging')
        swath_merging.set('count', '0')
        swath_merging.append(ET.Element('swathMergeList'))
        self.swath_merging = swath_merging

    def assemble(self):
        self.create_ads_header()
        self.create_quality_information()
        # self.create_general_annotation()
        # self.create_image_annotation()
        self.create_doppler_centroid()
        self.create_antenna_pattern()
        self.create_swath_timing()
        self.create_geolocation_grid()
        self.create_coordinate_conversion()
        self.create_swath_merging()

        product = ET.Element('product')
        product.append(self.ads_header)
        product.append(self.quality_information)
        # product.append(self.general_annotation)
        # product.append(self.image_annotation)
        product.append(self.doppler_centroid)
        product.append(self.antenna_pattern)
        product.append(self.swath_timing)
        product.append(self.geolocation_grid)
        product.append(self.coordinate_conversion)
        product.append(self.swath_merging)
        product_tree = ET.ElementTree(product)

        ET.indent(product_tree, space='  ')
        self.xml = product_tree


# def merge_product(burst_infos: Iterable[BurstInfo], out_path: Path):
#     """Merge annotation data into a single file."""
#     annotation, min_anx, max_anx, start_line = prep_info(burst_infos, 'product')
#     new_annotation = ET.Element('product')
#
#     image_number = int(out_path.with_suffix('').name.split('-')[-1])
#     ads_header = update_ads_header(annotation.find('adsHeader'), min_anx, max_anx, image_number)
#     new_annotation.append(ads_header)
#
#     quality = deepcopy(annotation.find('qualityInformation'))
#     new_annotation.append(quality)
#
#     xml_lists = {}
#     for list_name in ['orbitList', 'attitudeList', 'noiseList', 'terrainHeightList', 'azimuthFmRateList']:
#         if list_name == 'orbitList':
#             buffer = 30
#         else:
#             buffer = 5
#
#         xml_list = annotation.find(f'generalAnnotation/{list_name}')
#         new_xml_list = filter_elements_by_time(xml_list, min_anx, max_anx, buffer=timedelta(seconds=buffer))
#         xml_lists[list_name] = new_xml_list
#
#     new_general = ET.Element('generalAnnotation')
#     new_general.append(deepcopy(annotation.find('generalAnnotation/productInformation')))
#     new_general.append(deepcopy(annotation.find('generalAnnotation/downlinkInformationList')))
#     new_general.append(xml_lists['orbitList'])
#     new_general.append(xml_lists['attitudeList'])
#     new_general.append(deepcopy(annotation.find('generalAnnotation/rawDataAnalysisList')))
#     new_general.append(deepcopy(annotation.find('generalAnnotation/replicaInformationList')))
#     new_general.append(xml_lists['noiseList'])
#     new_general.append(xml_lists['terrainHeightList'])
#     new_general.append(xml_lists['azimuthFmRateList'])
#     new_annotation.append(new_general)
#
#     new_image_info = ET.Element('imageInformation')
#     start_time = ET.SubElement(new_image_info, 'productFirstLineUtcTime')
#     start_time.text = min_anx.isoformat()
#     stop_time = ET.SubElement(new_image_info, 'productLastLineUtcTime')
#     stop_time.text = max_anx.isoformat()
#     new_image_info.append(deepcopy(annotation.find('imageAnnotation/imageInformation/ascendingNodeTime')))
#     new_image_info.append(deepcopy(annotation.find('imageAnnotation/imageInformation/anchorTime')))
#     composition = ET.SubElement(new_image_info, 'productComposition')
#     composition.text = 'Assembled'
#     slice_number = ET.SubElement(new_image_info, 'sliceNumber')
#     slice_number.text = '0'
#     slice_list = ET.SubElement(new_image_info, 'sliceList')
#     slice_list.set('count', '0')
#     copy_list = [
#         'slantRangeTime',
#         'pixelValue',
#         'outputPixels',
#         'rangePixelSpacing',
#         'azimuthPixelSpacing',
#         'azimuthTimeInterval',
#         'azimuthFrequency',
#         'numberOfSamples',
#     ]
#     for element_name in copy_list:
#         new_image_info.append(deepcopy(annotation.find(f'imageAnnotation/imageInformation/{element_name}')))
#
#     n_lines = ET.SubElement(new_image_info, 'numberOfLines')
#     n_lines.text = str(burst_infos[0].length * len(burst_infos))
#
#     copy_list = ['zeroDopMinusAcqTime', 'incidenceAngleMidSwath', 'imageStatistics']
#     for element_name in copy_list:
#         new_image_info.append(deepcopy(annotation.find(f'imageAnnotation/imageInformation/{element_name}')))
#
#     # TODO: recalculate imageStatistics
#
#     new_image = ET.Element('imageAnnotation')
#     new_image.append(new_image_info)
#     new_image.append(deepcopy(annotation.find('imageAnnotation/processingInformation')))
#
#     new_annotation.append(new_image)
#
#     dop_centroid_list = annotation.find('dopplerCentroid/dcEstimateList')
#     new_dop_centroid_list = filter_elements_by_time(dop_centroid_list, min_anx, max_anx)
#     new_dop_centroid = ET.Element('dopplerCentroid')
#     new_dop_centroid.append(new_dop_centroid_list)
#     new_annotation.append(new_dop_centroid)
#
#     antenna_list = annotation.find('antennaPattern/antennaPatternList')
#     new_antenna_list = filter_elements_by_time(antenna_list, min_anx, max_anx)
#     new_antenna = ET.Element('antennaPattern')
#     new_antenna.append(new_antenna_list)
#     new_annotation.append(new_antenna)
#
#     swath_timing = annotation.find('swathTiming')
#     bursts = swath_timing.find('burstList')
#     new_bursts = filter_elements_by_time(bursts, min_anx, max_anx, buffer=timedelta(seconds=0.5))
#     new_swath_timing = ET.Element('swathTiming')
#     new_swath_timing.append(deepcopy(swath_timing.find('linesPerBurst')))
#     new_swath_timing.append(deepcopy(swath_timing.find('samplesPerBurst')))
#     new_swath_timing.append(new_bursts)
#     new_annotation.append(new_swath_timing)
#
#     gcp_list = annotation.find('geolocationGrid/geolocationGridPointList')
#     new_gcp_list = filter_elements_by_time(
#         gcp_list, min_anx, max_anx, start_line, line_bounds=[0, burst_infos[0].length * len(burst_infos)]
#     )
#     new_gcp = ET.Element('geolocationGrid')
#     new_gcp.append(new_gcp_list)
#     new_annotation.append(new_gcp)
#
#     # Both of these fields are not used for SLCs, only GRDs
#     new_annotation.append(create_empty_xml_list('coordinateConversion'))
#     new_annotation.append(create_empty_xml_list('swathMerging', 'swathMergeList'))
#
#     write_xml(new_annotation, out_path)
