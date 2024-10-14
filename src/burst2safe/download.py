import asyncio
from pathlib import Path
from typing import Iterable

import aiohttp
from tenacity import retry, retry_if_result, stop_after_delay, wait_fixed, wait_random

from burst2safe.utils import BurstInfo


def get_url_dict(burst_infos: Iterable[BurstInfo], force: bool = False) -> dict:
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
async def retry_get_response_async(session, url):
    response = await session.get(url)
    response.raise_for_status()
    return response


async def download_response_async(response, file_path: Path) -> None:
    if not file_path.parent.exists():
        raise ValueError(f'Error downloading, directory not found: {file_path.parent}')

    with open(file_path, 'wb') as f:
        async for chunk in response.content.iter_chunked(2**14):
            f.write(chunk)


async def response_producer(url_dict, session, queue):
    for path, url in url_dict.items():
        response = await retry_get_response_async(session, url=url)
        await queue.put((response, path))
    await queue.put((None, None))


async def response_consumer(queue):
    while True:
        response, path = await queue.get()
        if path is None:
            break
        await download_response_async(response, path)


async def download_async(url_dict) -> None:
    queue = asyncio.Queue()
    async with aiohttp.ClientSession(trust_env=True) as session:
        await asyncio.gather(response_producer(url_dict, session, queue), response_consumer(queue))


def download_bursts(burst_infos: Iterable[BurstInfo]):
    tiffs, xmls = get_url_dict(burst_infos)
    asyncio.run(download_async({**tiffs, **xmls}))
    missing_data = [x for x in {**tiffs, **xmls}.keys() if not x.exists]
    if missing_data:
        raise ValueError(f'Error downloading, missing files: {", ".join(missing_data.name)}')