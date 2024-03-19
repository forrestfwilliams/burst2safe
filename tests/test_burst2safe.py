from pathlib import Path

from lxml import etree

from burst2safe import burst2safe


def test_optional_wd():
    wd = burst2safe.optional_wd()
    assert isinstance(wd, Path)
    assert wd == Path.cwd()

    existing_dir = 'working'
    wd = burst2safe.optional_wd(existing_dir)
    assert isinstance(wd, Path)
    assert wd == Path(existing_dir)


def validate_xml(xml_file, xsd_file):
    # Load XML file
    xml_doc = etree.parse(xml_file)

    # Load XSD file
    xsd_doc = etree.parse(xsd_file)
    schema = etree.XMLSchema(xsd_doc)

    # Validate XML against XSD
    if schema.validate(xml_doc):
        print('XML is valid against the XSD.')
    else:
        print('XML is not valid against the XSD.')
        print(schema.error_log)


xml_file = 'S1A_IW_SLC__1SSV_20200604T022312_20200604T022315_032861_03CE65_2203.SAFE/annotation/calibration/calibration-s1a-iw2-slc-vv-20200604t022312-20200604t022318-032861-03ce65-001.xml'
xsd_file = 'S1A_IW_SLC__1SDV_20200604T022251_20200604T022318_032861_03CE65_7C85.SAFE/support/s1-level-1-calibration.xsd'
validate_xml(xml_file, xsd_file)
