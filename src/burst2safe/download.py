import asyncio
import os
from concurrent.futures import ThreadPoolExecutor
from multiprocessing import cpu_count
from pathlib import Path
from typing import Iterable, Optional

import aiohttp
import asf_search
import requests
from asf_search import ASFAuthenticationError
from asf_search.ASFSession import ASFSession
from requests.exceptions import HTTPError
from tenacity import retry, retry_if_result, stop_after_delay, wait_fixed, wait_random
from tqdm.contrib.concurrent import process_map

from burst2safe.auth import get_earthdata_credentials
from burst2safe.utils import BurstInfo


def try_get_response(session: ASFSession, url: str):
    response = session.get(url, stream=True, hooks={'response': asf_search.download.strip_auth_if_aws})

    try:
        response.raise_for_status()
    except HTTPError as e:
        if 400 <= response.status_code <= 499:
            raise ASFAuthenticationError(f'HTTP {e.response.status_code}: {e.response.text}')
        raise e

    return response


@retry(
    reraise=True,
    retry=retry_if_result(lambda r: r.status_code == 202),
    wait=wait_fixed(0.5) + wait_random(0, 1),
    stop=stop_after_delay(120),
)
def retry_get_response(session: ASFSession, url: str) -> requests.Response:
    return try_get_response(session, url)


def download_response(response: requests.Response, file_path: Path) -> None:
    if not file_path.parent.exists():
        raise asf_search.exceptions.ASFDownloadError(f'Error downloading, directory not found: {file_path.parent}')
    with open(file_path, 'wb') as f:
        for chunk in response.iter_content(chunk_size=8192):
            f.write(chunk)


def download_url(session: ASFSession, url: str, file_path: Path) -> None:
    """
    Downloads a product from the specified URL to the specified file path.

    Args:
        session: The ASF session to use for downloading
        url: The URL to download
        file_path: The path to save the file
    """
    response = retry_get_response(session, url=url)
    download_response(response, file_path)


def get_url_dict(burst_infos: Iterable[BurstInfo], force: bool = False) -> dict:
    tiffs = {}
    xmls = {}
    for burst_info in burst_infos:
        if force or not burst_info.data_path.exists():
            tiffs[burst_info.data_path] = burst_info.data_url

        if force or not burst_info.metadata_path.exists():
            xmls[burst_info.metadata_path] = burst_info.metadata_url
    return tiffs, xmls


def download_bursts_thread(
    burst_infos: Iterable[BurstInfo], max_threads: Optional[int] = None, force: bool = False
) -> None:
    """Download the burst data and metadata files using multiple workers.

    Args:
        burst_infos: A list of BurstInfo objects
        n_threads: Number of threads to use for downloading
        force: If True, download the files even if they already exist
    """
    tiffs, xmls = get_url_dict(burst_infos, force)
    all_data = {**tiffs, **xmls}
    if len(all_data) == 0:
        print('All files already exist. Skipping download.')
        return

    username, password = get_earthdata_credentials()
    sess = asf_search.ASFSession().auth_with_creds(username, password)
    # max_threads = min(len(all_data), cpu_count() + 4) if max_threads is None else max_threads
    max_threads = min(cpu_count() + 4 if max_threads is None else max_threads, len(all_data))

    # Submit one request per file to start extraction of burst data
    with ThreadPoolExecutor(max_workers=max_threads):
        process_map(try_get_response, [sess] * len(all_data), all_data.values())

    print('Downloading metadata...')
    with ThreadPoolExecutor(max_workers=min(max_threads, len(xmls))):
        process_map(download_url, [sess] * len(xmls), xmls.values(), xmls.keys())

    print('Downloading data...')
    with ThreadPoolExecutor(max_workers=min(max_threads, len(tiffs))):
        process_map(download_url, [sess] * len(tiffs), tiffs.values(), tiffs.keys())


# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~#
@retry(
    reraise=True,
    retry=retry_if_result(lambda r: r.status == 202),
    wait=wait_fixed(0.5) + wait_random(0, 1),
    stop=stop_after_delay(120),
)
async def retry_get_response_async(session, url):
    response = await session.get(url)
    response.raise_for_status()
    return response


async def download_response_async(response, file_path: Path) -> None:
    if not file_path.parent.exists():
        raise ValueError(f'Error downloading, directory not found: {file_path.parent}')

    with open(file_path, 'wb') as f:
        async for chunk in response.content.iter_chunked(8192):
            f.write(chunk)


async def download_producer(url_dict, session, queue):
    print('Producer: Running')
    for path, url in url_dict.items():
        response = await retry_get_response_async(session, url=url)
        await queue.put((response, path))
    await queue.put((None, None))
    print('Producer: Done')


async def download_consumer(queue):
    print('Consumer: Running')
    while True:
        response, path = await queue.get()
        if path is None:
            break
        print(f'Downloading {path}')
        await download_response_async(response, path)
    print('Consumer: Done')


async def download_async(url_dict, token) -> None:
    queue = asyncio.Queue()
    headers = {'Authorization': f'Bearer {token}'}
    async with aiohttp.ClientSession(headers=headers, trust_env=True) as session:
        await asyncio.gather(download_producer(url_dict, session, queue), download_consumer(queue))


def download_bursts(burst_infos: Iterable[BurstInfo]):
    tiffs, xmls = get_url_dict(burst_infos)
    username, password = get_earthdata_credentials()
    token = os.getenv('EDL_TOKEN')
    token = aiohttp.BasicAuth(username, password)
    asyncio.run(download_async({**tiffs, **xmls}, token))
