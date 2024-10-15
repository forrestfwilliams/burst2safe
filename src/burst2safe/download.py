import asyncio
import os
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Iterable

import aiohttp
import numpy as np
from tenacity import retry, retry_if_result, stop_after_attempt, stop_after_delay, wait_fixed, wait_random

from burst2safe.auth import check_earthdata_credentials
from burst2safe.utils import BurstInfo


def get_url_dict(burst_infos: Iterable[BurstInfo], force: bool = False) -> dict:
    """Get a dictionary of URLs to download. Keys are save paths, and values are download URLs.

    Args:
        burst_infos: A list of BurstInfo objects
        force: If True, download even if the file already exists

    Returns:
        A dictionary of URLs to download
    """
    tiffs = {}
    xmls = {}
    for burst_info in burst_infos:
        if force or not burst_info.data_path.exists():
            tiffs[burst_info.data_path] = burst_info.data_url

        if force or not burst_info.metadata_path.exists():
            xmls[burst_info.metadata_path] = burst_info.metadata_url
    return tiffs, xmls


@retry(
    reraise=True,
    retry=retry_if_result(lambda r: r.status == 202),
    wait=wait_fixed(0.5) + wait_random(0, 1),
    stop=stop_after_delay(120),
)
async def retry_get_response_async(session: aiohttp.ClientSession, url: str) -> aiohttp.ClientResponse:
    """Retry a GET request until a non-202 response is received.

    Args:
        session: An aiohttp ClientSession
        url: The URL to GET

    Returns:
        An aiohttp ClientResponse
    """
    response = await session.get(url)
    response.raise_for_status()
    return response


@retry(wait=wait_fixed(0.5), stop=stop_after_attempt(3))
async def download_response_async(response: aiohttp.ClientResponse, file_path: Path) -> None:
    """Download the response content to a file.

    Args:
        response: An aiohttp ClientResponse
        file_path: The path to save the response content to
    """
    try:
        with open(file_path, 'wb') as f:
            async for chunk in response.content.iter_chunked(2**14):
                f.write(chunk)
        response.close()
    except Exception as e:
        response.close()
        if file_path.exists():
            file_path.unlink()
        raise e


async def response_producer(url_dict: dict, session: aiohttp.ClientSession, queue: asyncio.Queue) -> None:
    """Produce responses to download and put them in a queue.

    Args:
        url_dict: A dictionary of URLs to download
        session: An aiohttp ClientSession
        queue: An asyncio Queue
    """
    for path, url in url_dict.items():
        response = await retry_get_response_async(session, url=url)
        await queue.put((response, path))
    await queue.put((None, None))


async def response_consumer(queue: asyncio.Queue) -> None:
    """Consume responses from a queue and download them.

    Args:
        queue: An asyncio Queue
    """
    while True:
        response, path = await queue.get()
        if path is None:
            break
        await download_response_async(response, path)


async def download_async(url_dict: dict) -> None:
    """Download a dictionary of URLs asynchronously.

    Args:
        url_dict: A dictionary of URLs to download
    """
    queue = asyncio.Queue()
    async with aiohttp.ClientSession(trust_env=True) as session:
        await asyncio.gather(response_producer(url_dict, session, queue), response_consumer(queue))


def download_bursts_async(burst_infos: Iterable[BurstInfo]) -> None:
    """Download the burst data and metadata files using an async queue.

    Args:
        burst_infos: A list of BurstInfo objects
    """
    tiffs, xmls = get_url_dict(burst_infos)
    check_earthdata_credentials()
    asyncio.run(download_async({**xmls, **tiffs}))


def download_bursts(burst_infos: Iterable[BurstInfo], parallel: bool = False) -> None:
    """Download the burst data and metadata files using multiple workers.

    Args:
        burst_infos: A list of BurstInfo objects
    """
    check_earthdata_credentials()
    if parallel:
        max_threads = min(len(burst_infos), os.cpu_count() + 2)
        burst_info_sets = [list(x) for x in np.array_split(burst_infos, max_threads)]
        with ThreadPoolExecutor(max_threads) as executor:
            executor.map(download_bursts_async, burst_info_sets)
    else:
        download_bursts_async(burst_infos)

    tiffs, xmls = get_url_dict(burst_infos, force=True)
    missing_data = [x for x in {**xmls, **tiffs}.keys() if not x.exists]
    if missing_data:
        raise ValueError(f'Error downloading, missing files: {", ".join(missing_data.name)}')
