from concurrent.futures import ThreadPoolExecutor
from multiprocessing import cpu_count
from pathlib import Path
from typing import Iterable, Optional

import asf_search
import requests
from tenacity import retry, retry_if_result, stop_after_delay, wait_fixed, wait_random
from tqdm.contrib.concurrent import process_map

from burst2safe.auth import get_earthdata_credentials
from burst2safe.utils import BurstInfo


def try_get_response(username: str, password: str, url: str) -> requests.Response:
    session = asf_search.ASFSession().auth_with_creds(username, password)
    response = session.get(url, stream=True, hooks={'response': asf_search.download.strip_auth_if_aws})

    try:
        response.raise_for_status()
    except requests.exceptions.HTTPError as e:
        if 400 <= response.status_code <= 499:
            raise asf_search.execptions.ASFAuthenticationError(f'HTTP {e.response.status_code}: {e.response.text}')
        raise e

    return response


@retry(
    reraise=True,
    retry=retry_if_result(lambda r: r.status_code == 202),
    wait=wait_fixed(0.5) + wait_random(0, 1),
    stop=stop_after_delay(120),
)
def retry_get_response(username: str, password: str, url: str) -> requests.Response:
    response = try_get_response(username, password, url)
    return response


def download_url(username: str, password: str, url: str, file_path: Path) -> None:
    """
    Downloads a product from the specified URL to the specified file path.

    Args:
        url: The URL to download
        file_path: The path to save the file
        username: The username to use for the download
        password: The password to use for the download
    """
    if not file_path.parent.exists():
        raise asf_search.exceptions.ASFDownloadError(
            f'Error downloading {url}: directory not found: {file_path.parent}'
        )

    response = retry_get_response(username=username, password=password, url=url)

    with open(file_path, 'wb') as f:
        for chunk in response.iter_content(chunk_size=8192):
            f.write(chunk)


def download_bursts(burst_infos: Iterable[BurstInfo], n_threads: Optional[int] = None, force: bool = False) -> None:
    """Download the burst data and metadata files using multiple workers.

    Args:
        burst_infos: A list of BurstInfo objects
        n_threads: Number of threads to use for downloading
        force: If True, download the files even if they already exist
    """
    tiffs = {}
    xmls = {}
    for burst_info in burst_infos:
        if force or not burst_info.data_path.exists():
            tiffs[burst_info.data_path] = burst_info.data_url

        if force or not burst_info.metadata_path.exists():
            xmls[burst_info.metadata_path] = burst_info.metadata_url

    all_data = {**tiffs, **xmls}
    if len(all_data) == 0:
        print('All files already exist. Skipping download.')
        return

    username, password = get_earthdata_credentials()
    n_threads = min(len(all_data), cpu_count() + 4) if n_threads is None else n_threads

    # Submit one request per file to start extraction of burst data
    username_list = [username] * len(all_data)
    password_list = [password] * len(all_data)
    # with ThreadPoolExecutor(max_workers=n_threads) as executor:
    with ThreadPoolExecutor(max_workers=n_threads):
        process_map(try_get_response, username_list, password_list, all_data.values())

    print('Downloading metadata...')
    username_list = [username] * len(xmls)
    password_list = [password] * len(xmls)
    with ThreadPoolExecutor(max_workers=n_threads):
        process_map(download_url, username_list, password_list, xmls.values(), xmls.keys())
    # [download_url(u, p, url, file) for u, p, url, file in zip(username_list, password_list, xmls.values(), xmls.keys())]

    print('Downloading data...')
    username_list = [username] * len(xmls)
    password_list = [password] * len(xmls)
    with ThreadPoolExecutor(max_workers=n_threads):
        process_map(download_url, username_list, password_list, tiffs.values(), tiffs.keys())
    # [download_url(u, p, url, file) for u, p, url, file in zip(username_list, password_list, tiffs.values(), tiffs.keys())]
