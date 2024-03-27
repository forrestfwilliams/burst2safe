# burst2safe
Utility for converting ASF-derived Sentinel-1 burst SLC products to the ESA SAFE format.

**This is still a work in progress, and we recommend waiting until the release of version 1.0.0 for use in production environments!**

## Usage
To use the tool, install it via pip:

```bash
pip install burst2safe
```

Or conda:
```bash
conda install -c conda-forge burst2safe
```

Then provide a list of Sentinel-1 burst granule IDs to be merged into a SAFE file to the `burst2safe` CLI tool using the following structure:

```bash
burst2safe S1_136231_IW2_20200604T022312_VV_7C85-BURST S1_136232_IW2_20200604T022315_VV_7C85-BURST
```
The output SAFE file will be created in the current directory.
To be eligible for processing, all burst granules must:
1. Have the same acquisition mode
1. Be in the same polarization
1. Be from the same absolute orbit
1. Be contiguous in time and space.

The tool should raise an error if any of these conditions are not met.

## Strategy
`burst2safe` combines and reformats individual bursts into a SAFE file following the procedure described in the [Sentinel-1 Product Specification Document](https://sentinel.esa.int/web/sentinel/user-guides/sentinel-1-sar/document-library/-/asset_publisher/1dO7RF5fJMbd/content/sentinel-1-product-specification-from-ipf-360?_com_liferay_asset_publisher_web_portlet_AssetPublisherPortlet_INSTANCE_1dO7RF5fJMbd_assetEntryId=4846613&_com_liferay_asset_publisher_web_portlet_AssetPublisherPortlet_INSTANCE_1dO7RF5fJMbd_redirect=https%3A%2F%2Fsentinel.esa.int%2Fweb%2Fsentinel%2Fuser-guides%2Fsentinel-1-sar%2Fdocument-library%3Fp_p_id%3Dcom_liferay_asset_publisher_web_portlet_AssetPublisherPortlet_INSTANCE_1dO7RF5fJMbd%26p_p_lifecycle%3D0%26p_p_state%3Dnormal%26p_p_mode%3Dview%26_com_liferay_asset_publisher_web_portlet_AssetPublisherPortlet_INSTANCE_1dO7RF5fJMbd_assetEntryId%3D4846613%26_com_liferay_asset_publisher_web_portlet_AssetPublisherPortlet_INSTANCE_1dO7RF5fJMbd_cur%3D0%26p_r_p_resetCur%3Dfalse)
In this document, ESA describes how to create an Assembled Sentinel-1 Level 1 product from individual Sentinel-1 Level 1 SAFEs. We use this same strategy to combine ASF-extracted burst SLC products into a SAFE file that should be compatible with any SAR processor currently capable of using Sentinel-1 Level SAFEs. For in-depth technical details of the implementation, we refer you to the Sentinel-1 Product Specification document above. However, it is important to know that ESA recommends merging Sentinel-1 data/metadata components using three primary strategies:

### Include
A given data/metadata component is the same for all data slices, and any value can be used (i.e., polarization).

For `Include` components, the value associated with the earliest burst is always used.

### Concatenate
A given data/metadata component is a series of time-ordered fields that can be combined into a single list (i.e., ground control points).

For `Concatenate` components, the fields are merged and subset to the start/stop times of the included bursts. Where present `line` sub-fields have also been updated.

### Merge
A given data/metadata component must be recalculated using a process unique to each component (i.e., platform heading).

For `Merge` components, we have made the best effort to follow the merging instructions outlined in the product specification. While we hope to eventually correctly reconstruct all merged fields, there are some components for whom the implementation is unclear. In these cases, we have set the values of these fields to NULL (`''`) so that downstream processors raise errors instead of using incorrect values. **If any fields we have omitted in this way cause your application to fail, let us know so that we can prioritize its development!**

### Omissions and Nulls
In some cases, we have not created certain datasets or metadata components because the creation process is unknown to us or is irrelevant for assembled products. This includes datasets such as all datasets in the SAFE `preview` directory the SAFE report PDF included with each SAFE file.

All full accounting of omitted datasets and fields can be found below:

* Annotation
    * Noise
        * No intentional omissions or nulls.
    * Calibration
        * No intentional omissions or nulls.
    * RFI
        * RFI annotation XMLs are currently omitted, but we plan to add this soon.
    * Product
        * `generalAnnotation/productInformation/platformHeading` set to `''`.
        * `imageAnnotation/imageInformation/azimuthPixelSpacing` set to `''`.
        * `imageAnnotation/imageInformation/imageStatistics/outputDataMean` set to `''`.
        * `imageAnnotation/imageInformation/imageStatistics/outputDataStdDev` set to `''`.
        * `swathTiming/burstList/burst/byteOffset` components are set to `''`.
* Measurement GeoTIFFs
    * TIFF tags **that are not GeoTIFF tags** are omitted. See Product Specification Table 3-8 for full list.
* Preview
    * All preview datasets and the preview directory are omitted.
* Support
    * s1-product-preview.xsd, s1-map-overlay.xsd, s1-quicklook.xsd and are omitted.
* Manifest
    * `metadataObjects` associated with support datasets are omitted.
* SAFE report
    * The SAFE report PDF is omitted.

### Other Known Compatibility Issues
This tool may not work for SAFEs created with Sentinel-1 IPF version <= v3.19. In the product annotation files, the `height` sub-field of `GeolocationGridPoint` components was not available prior to IPF v3.19. This field is currently used to concatenate geocontrol points for the measurment GeoTIFFs, and thus the tool may fail if these sub-fields are not present.

## License
`burst2safe` is licensed under the BSD 2-Clause License. See the LICENSE file for more details.

## Contributing
Contributions this project are welcome! If you would like to contribute, please submit a pull request on the GitHub repository.

## Contact Us
Want to talk about `burst2safe`? We would love to hear from you!

Found a bug? Want to request a feature?
[open an issue](https://github.com/ASFHyP3/asf_tools/issues/new)

General questions? Suggestions? Or just want to talk to the team?
[chat with us on burst2safe's discussion page](https://github.com/forrestfwilliams/burst2safe/discussions) 
