import asyncio
from pathlib import Path
from typing import Iterable

import aiohttp
from tenacity import retry, retry_if_result, stop_after_attempt, stop_after_delay, wait_random

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
    url_dict = {}
    for burst_info in burst_infos:
        if force or not burst_info.data_path.exists():
            url_dict[burst_info.data_path] = burst_info.data_url
        if force or not burst_info.metadata_path.exists():
            url_dict[burst_info.metadata_path] = burst_info.metadata_url
    return url_dict


@retry(
    reraise=True, retry=retry_if_result(lambda r: r.status == 202), wait=wait_random(0, 1), stop=stop_after_delay(120)
)
async def get_async(session: aiohttp.ClientSession, url: str) -> aiohttp.ClientResponse:
    """Retry a GET request until a non-202 response is received

    Args:
        session: An aiohttp ClientSession
        url: The URL to download

    Returns:
        The response object
    """
    response = await session.get(url)
    response.raise_for_status()
    return response


@retry(reraise=True, stop=stop_after_attempt(5))
async def download_url_async(session: aiohttp.ClientSession, url: str, file_path: Path) -> None:
    """Retry a GET request until a non-202 response is received, then download data.

    Args:
        session: An aiohttp ClientSession
        url: The URL to download
        file_path: The path to save the downloaded data to
    """
    response = await get_async(session, url)
    assert response.status == 200
    assert Path(response.content_disposition.filename).suffix == file_path.suffix
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


async def download_async(url_dict: dict) -> None:
    """Download a dictionary of URLs asynchronously.

    Args:
        url_dict: A dictionary of URLs to download
    """
    async with aiohttp.ClientSession(trust_env=True) as session:
        tasks = []
        for file_path, url in url_dict.items():
            tasks.append(download_url_async(session, url, file_path))
        await asyncio.gather(*tasks)


def download_bursts(burst_infos: Iterable[BurstInfo]) -> None:
    """Download the burst data and metadata files using an async queue.

    Args:
        burst_infos: A list of BurstInfo objects
    """
    check_earthdata_credentials()
    url_dict = get_url_dict(burst_infos)
    asyncio.run(download_async(url_dict))
    full_dict = get_url_dict(burst_infos, force=True)
    missing_data = [x for x in full_dict.keys() if not x.exists]
    if missing_data:
        raise ValueError(f'Error downloading, missing files: {", ".join(missing_data.name)}')
