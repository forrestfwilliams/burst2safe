import asyncio
import os
from pathlib import Path
from urllib.parse import urlparse

from aiohttp import ClientSession
from aiohttp.hdrs import AUTHORIZATION


TRUSTED_HOSTS = [
    'urs.earthdata.nasa.gov',
    'cumulus.asf.alaska.edu',
    'sentinel1.asf.alaska.edu',
    'sentinel1-burst.asf.alaska.edu',
    'datapool.asf.alaska.edu',
    'auth.asf.alaska.edu',
]


async def download_file_token(url: str, out_path: Path) -> None:
    token = os.getenv('EDL_TOKEN')
    headers = {AUTHORIZATION: f'Bearer {token}'}
    async with ClientSession(headers=headers, trust_env=True) as session:
        response = await session.get(url)
        response.raise_for_status()
        with open(out_path, 'wb') as f:
            async for chunk in response.content.iter_chunked(2**14):
                f.write(chunk)
        response.close()


async def download_file_netrc(url: str, out_path: Path) -> None:
    async with ClientSession(trust_env=True) as session:
        response = await session.get(url)
        response.raise_for_status()
        with open(out_path, 'wb') as f:
            async for chunk in response.content.iter_chunked(2**14):
                f.write(chunk)
        response.close()


async def download_file_token_v2(url: str, out_path: Path, max_redirects: int = 8) -> None:
    token = os.getenv('EDL_TOKEN')
    headers = {AUTHORIZATION: f'Bearer {token}'}
    async with ClientSession(headers=headers, trust_env=True) as session:
        for i in range(max_redirects):
            print(url)
            host = urlparse(url).hostname
            if host not in TRUSTED_HOSTS:
                session.headers.pop(AUTHORIZATION, None)
            response = await session.get(url, allow_redirects=False)
            response.raise_for_status()
            if 300 <= response.status < 400:
                url = response.headers['Location']
                session.cookie_jar.update_cookies(response.cookies)
                if i == max_redirects - 1:
                    raise Exception(f'Maximum number of redirects reached: {max_redirects}')
            elif 200 <= response.status < 300:
                break

        with open(out_path, 'wb') as f:
            async for chunk in response.content.iter_chunked(2**14):
                f.write(chunk)

        response.close()


def main():
    # test_xml = 'https://datapool.asf.alaska.edu/CSLC/OPERA-S1/OPERA_L2_CSLC-S1_T115-245714-IW1_20241113T141635Z_20241114T085631Z_S1A_VV_v1.1.iso.xml'
    # test_url = 'https://datapool.asf.alaska.edu/CSLC/OPERA-S1/OPERA_L2_CSLC-S1_T115-245714-IW1_20241113T141635Z_20241114T085631Z_S1A_VV_v1.1.h5'
    # test_safe = 'https://datapool.asf.alaska.edu/SLC/SA/S1A_IW_SLC__1SDV_20241116T130250_20241116T130317_056580_06F04D_176C.zip'
    test_burst = 'https://sentinel1-burst.asf.alaska.edu/S1A_IW_SLC__1SDV_20241116T130250_20241116T130317_056580_06F04D_176C/IW2/VH/2.xml'

    # works when .netric is present, but EDL_TOKEN isn't
    # asyncio.run(download_file_netrc(test_url, test_path))

    # doesn't work when .netric isn't present, but EDL_TOKEN is
    # asyncio.run(download_file_token(test_url, test_path))

    # asyncio.run(download_file_token_v2(test_safe, 'test.safe'))
    # print('---')
    # asyncio.run(download_file_token_v2(test_burst, 'test.xml'))
    asyncio.run(download_file_token_v2(test_burst, 'test.xml'))
    # asyncio.run(download_file_netrc(test_burst, 'test.xml'))
    # asyncio.run(download_file_token(test_url, test_path))


if __name__ == '__main__':
    main()
