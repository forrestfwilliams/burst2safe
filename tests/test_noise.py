from burst2safe.noise import Noise
from helpers import validate_xml


def test_merge_noise(burst_infos, tmp_path, xsd_dir):
    out_path = tmp_path / 'file-001.xml'
    xsd_file = xsd_dir / 's1-level-1-noise.xsd'
    noise = Noise(burst_infos, 1)
    noise.assemble()
    noise.write(out_path)
    assert validate_xml(out_path, xsd_file)
