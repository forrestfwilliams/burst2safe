# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [PEP 440](https://www.python.org/dev/peps/pep-0440/)
and uses [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.4.1]

### Fixed
* Bug in CLI parsing of granule case for `burst2safe`.

## [0.4.0]

### Added
* `burst2stack` tool for creating stacks of SAFEs.
* The ability to specify swaths and minimum number of bursts when using tool.
* The ability to specify the SAFE extent by either bounding box or vector file.

### Fixed
* `Safe.get_name()` so that it correctly parses `Safe` objects with only cross-pol data.

### Changed
* Moved all search/download functionality to `search.py` module.
* `--bbox` argument to `--extent`.

## [0.3.5]

### Fixed
* Polarization code now accurately reflects bursts contained in SAFE.
* Measurement GeoTiff metadata now correctly specifies Sentinel-1 A or B.

### Added
* CLI argument for specifying output directory.

## [0.3.4]

### Added
* Separate check of Earthdata credentials prior to download.

## [0.3.3]

### Added
* Retries of download functionality to improve robustness of download step.

## [0.3.2]

### Fixed
* Bug introduced in `0.3.1` where the `download_bursts` function would not work for a single worker.

## [0.3.1]

### Fixed
* Race condition in `download_bursts` function by switching to parallel, instead of threaded, downloads.

## [0.3.0]

### Added
* Support for IPF >=3.40 RFI annotation files.
* Support for IPF <=2.90.
* IPF-specific support files.
* Calculation of `platformHeading` and `burst/byteOffset` fields.

### Fixed
* Path information for annotation/measurement files are now are updated when the SAFE path is.
* Bug when burst widths are different by one pixel

### Changed
* Test suite to use test data from 2024 (IPF version 3.71).

## [0.2.0]

### Added
* Functionality for ensure input bursts are eligible for merging.
* A test suite for the library.
* Docstrings for the majority of methods/functions.
* Bounding-box based interface for specifying bursts to merge.
* Removal of intermediate files after merging.

### Changed
* Refactored many components of the library to enable simpler testing.
* Correctly set product unique identifier in SAFE name.

## [0.1.0]

### Added
* First working version of the library.

## [0.0.1]

### Added
* Create project structure and CI/CD tooling.

## [0.0.0]

### Added
* Initial version of project.
