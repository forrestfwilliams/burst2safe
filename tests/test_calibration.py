from burst2safe.calibration import Calibration
from helpers import validate_xml


class TestCalibration:
    def test_merge(self, burst_infos, tmp_path, xsd_dir):
        out_path = tmp_path / 'file-001.xml'
        xsd_file = xsd_dir / 's1-level-1-calibration.xsd'
        calibration = Calibration(burst_infos, '3.71', 1)
        calibration.assemble()
        calibration.write(out_path)
        assert validate_xml(out_path, xsd_file)
