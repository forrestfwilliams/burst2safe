from pathlib import Path

from lxml import etree

from burst2safe import burst2safe


XSD_DIR = Path(__file__).parent.parent / 'src' / 'burst2safe' / 'data'


def validate_xml(xml_file, xsd_file):
    # Load XML file
    xml_doc = etree.parse(xml_file)

    # Load XSD file
    xsd_doc = etree.parse(xsd_file)
    schema = etree.XMLSchema(xsd_doc)

    # Validate XML against XSD
    is_valid = schema.validate(xml_doc)
    if not is_valid:
        print(schema.error_log)
    assert is_valid


def test_optional_wd():
    wd = burst2safe.optional_wd()
    assert isinstance(wd, Path)
    assert wd == Path.cwd()

    existing_dir = 'working'
    wd = burst2safe.optional_wd(existing_dir)
    assert isinstance(wd, Path)
    assert wd == Path(existing_dir)


def test_merge_calibration(burst_infos, tmp_path):
    out_path = tmp_path / 'file-001.xml'
    xsd_file = XSD_DIR / 's1-level-1-calibration.xsd'
    burst2safe.merge_calibration(burst_infos, out_path)
    validate_xml(out_path, xsd_file)


def test_merge_noise(burst_infos, tmp_path):
    out_path = tmp_path / 'file-001.xml'
    xsd_file = XSD_DIR / 's1-level-1-noise.xsd'
    burst2safe.merge_noise(burst_infos, out_path)
    validate_xml(out_path, xsd_file)


def test_merge_product(burst_infos, tmp_path):
    out_path = tmp_path / 'file-001.xml'
    xsd_file = XSD_DIR / 's1-level-1-product.xsd'
    burst2safe.merge_product(burst_infos, out_path)
    validate_xml(out_path, xsd_file)
