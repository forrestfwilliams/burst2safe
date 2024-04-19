from burst2safe.rfi import Rfi
from helpers import validate_xml


class TestRfi:
    def test_merge(self, burst_infos, tmp_path, xsd_dir):
        out_path = tmp_path / 'file-001.xml'
        xsd_file = xsd_dir / 's1-level-1-rfi.xsd'
        rfi = Rfi(burst_infos, '3.71', 1)
        rfi.assemble()
        rfi.write(out_path)
        assert validate_xml(out_path, xsd_file)
