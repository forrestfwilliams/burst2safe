from burst2safe import Product
from helpers import validate_xml


class TestProduct:
    def test_update_data_stats(self, burst_infos):
        base_path = 'imageInformation/imageStatistics/outputData'
        product = Product(burst_infos, 1)
        product.assemble()
        product.update_data_stats(1 + 1j, 2 + 2j)
        for elem in [product.image_annotation, product.xml.find('imageAnnotation')]:
            elem.find(f'{base_path}Mean/re').text = '1'
            # elem.find(f'{base_path}Mean/im').text = data_mean_im
            # elem.find(f'{base_path}StdDev/re').text = data_std_re
            # elem.find(f'{base_path}StdDev/im').text = data_std_im

    def test_merge(burst_infos, tmp_path, xsd_dir):
        out_path = tmp_path / 'file-001.xml'
        xsd_file = xsd_dir / 's1-level-1-product.xsd'
        product = Product(burst_infos, 1)
        product.assemble()

        # Add back in omitted fields
        product.update_data_stats(1 + 1j, 2 + 2j)
        burst_elems = product.xml.findall('.//byteOffset')
        for burst_elem in burst_elems:
            burst_elem.text = '1'
        product.xml.find('generalAnnotation/productInformation/platformHeading').text = '0.1'

        product.write(out_path)
        assert validate_xml(out_path, xsd_file)
