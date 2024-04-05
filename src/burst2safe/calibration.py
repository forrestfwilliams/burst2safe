from copy import deepcopy
from typing import Iterable

import lxml.etree as ET

from burst2safe.base import Annotation
from burst2safe.utils import BurstInfo


class Calibration(Annotation):
    """Class representing a calibration XML."""

    def __init__(self, burst_infos: Iterable[BurstInfo], image_number: int):
        """Create a calibration object.

        Args:
            burst_infos: List of BurstInfo objects.
            image_number: Image number.
        """
        super().__init__(burst_infos, 'calibration', image_number)
        self.calibration_information = None
        self.calibrattion_vector_list = None

    def create_calibration_information(self):
        """Create the calibration information."""
        calibration_information = [calibration.find('calibrationInformation') for calibration in self.inputs][0]
        self.calibration_information = deepcopy(calibration_information)

    def create_calibration_vector_list(self):
        """Create the calibration vector list."""
        self.calibration_vector_list = self.merge_lists('calibrationVectorList')

    def assemble(self):
        """Assemble the calibration object components."""
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
