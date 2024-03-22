from copy import deepcopy
from typing import Iterable

import lxml.etree as ET

from burst2safe.base import Annotation, ListOfListElements
from burst2safe.utils import BurstInfo


class Calibration(Annotation):
    def __init__(self, burst_infos: Iterable[BurstInfo], image_number: int):
        super().__init__(burst_infos, 'calibration', image_number)
        self.calibration_information = None
        self.calibrattion_vector_list = None

    def create_calibration_information(self):
        calibration_information = [calibration.find('calibrationInformation') for calibration in self.inputs][0]
        self.calibration_information = deepcopy(calibration_information)

    def create_calibration_vector_list(self):
        cal_vectors = [cal.find('calibrationVectorList') for cal in self.inputs]
        cal_vector_lol = ListOfListElements(cal_vectors, self.start_line, self.slc_lengths)
        self.calibration_vector_list = cal_vector_lol.create_filtered_list([self.min_anx, self.max_anx])

    def assemble(self):
        self.create_ads_header()
        self.create_calibration_information()
        self.create_calibration_vector_list()

        calibration = ET.Element('calibration')
        calibration.append(self.ads_header)
        calibration.append(self.calibration_information)
        calibration.append(self.calibration_vector_list)
        calibration_tree = ET.ElementTree(calibration)

        ET.indent(calibration_tree, space='  ')
        self.xml = calibration_tree
