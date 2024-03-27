from pathlib import Path

from lxml import etree

from burst2safe import utils
from burst2safe.calibration import Calibration
from burst2safe.noise import Noise
from burst2safe.product import Product


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
        raise ValueError(f'XML failed validation with message:\n{schema.error_log}')

    return is_valid


def test_optional_wd():
    wd = utils.optional_wd()
    assert isinstance(wd, Path)
    assert wd == Path.cwd()

    existing_dir = 'working'
    wd = utils.optional_wd(existing_dir)
    assert isinstance(wd, Path)
    assert wd == Path(existing_dir)


def test_merge_calibration(burst_infos, tmp_path):
    out_path = tmp_path / 'file-001.xml'
    xsd_file = XSD_DIR / 's1-level-1-calibration.xsd'
    calibration = Calibration(burst_infos, 1)
    calibration.assemble()
    calibration.write(out_path)
    assert validate_xml(out_path, xsd_file)


def test_merge_noise(burst_infos, tmp_path):
    out_path = tmp_path / 'file-001.xml'
    xsd_file = XSD_DIR / 's1-level-1-noise.xsd'
    noise = Noise(burst_infos, 1)
    noise.assemble()
    noise.write(out_path)
    assert validate_xml(out_path, xsd_file)


def test_merge_product(burst_infos, tmp_path):
    out_path = tmp_path / 'file-001.xml'
    xsd_file = XSD_DIR / 's1-level-1-product.xsd'
    product = Product(burst_infos, 1)
    product.assemble()
    
    # Add back in omitted fields
    product.update_data_stats(1+1j, 2+2j)
    burst_elems = product.xml.findall('.//byteOffset')
    for burst_elem in burst_elems:
        burst_elem.text = '1'
    product.xml.find('generalAnnotation/productInformation/platformHeading').text = '0.1'

    product.write(out_path)
    assert validate_xml(out_path, xsd_file)
