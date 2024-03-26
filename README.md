# burst2safe
Utility for converting ASF-derived Sentinel-1 burst SLC products to the ESA SAFE format.

## Usage
To use the tool, install it, then provide a list of Sentinel-1 burst granule IDs to be merged into a SAFE file to the `burst2safe` CLI tool using the following structure:

```bash
burst2safe S1_136231_IW2_20200604T022312_VV_7C85-BURST S1_136232_IW2_20200604T022315_VV_7C85-BURST
```
The output SAFE file will be created in the current directory.
