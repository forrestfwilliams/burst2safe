import numpy as np
from osgeo import gdal, osr


gdal.UseExceptions()


def create_test_geotiff(output_file, dtype='float', shape=(10, 10, 1)):
    """Create a test geotiff for testing"""
    opts = {'float': (np.float64, gdal.GDT_Float64), 'cfloat': (np.complex64, gdal.GDT_CFloat32)}
    np_dtype, gdal_dtype = opts[dtype]
    data = np.ones(shape[0:2], dtype=np_dtype)
    geotransform = [0.0, 1.0, 0.0, 0.0, 0.0, 1.0]
    driver = gdal.GetDriverByName('GTiff')
    dataset = driver.Create(output_file, shape[0], shape[1], shape[2], gdal_dtype)
    dataset.SetGeoTransform(geotransform)
    srs = osr.SpatialReference()
    srs.ImportFromEPSG(4326)
    dataset.SetProjection(srs.ExportToWkt())
    for i in range(shape[2]):
        band = dataset.GetRasterBand(i + 1)
        band.WriteArray(data)
    dataset = None
