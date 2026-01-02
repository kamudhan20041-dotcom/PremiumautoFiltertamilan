import aiohttp
import asyncio
import base64
import random
import pyshorteners
from urllib.parse import quote
from info import SHORTNER_SITE, SHORTNER_API

async def short_url(longurl):
    # -------------------------------------------------------------------------
    # OPTIMIZATION: Use aiohttp for non-blocking network requests.
    # This prevents the bot from freezing while waiting for the shortener site.
    # -------------------------------------------------------------------------
    
    if "shorte.st" in SHORTNER_SITE:
        async with aiohttp.ClientSession() as session:
            async with session.get(f'http://api.shorte.st/stxt/{SHORTNER_API}/{longurl}', ssl=False) as resp:
                return await resp.text()

    elif "linkvertise" in SHORTNER_SITE:
        # Linkvertise logic is purely local string manipulation, so it's already fast.
        url = quote(base64.b64encode(longurl.encode("utf-8")))
        linkvertise = [
            f"https://link-to.net/{SHORTNER_API}/{random.random() * 1000}/dynamic?r={url}",
            f"https://up-to-down.net/{SHORTNER_API}/{random.random() * 1000}/dynamic?r={url}",
            f"https://direct-link.net/{SHORTNER_API}/{random.random() * 1000}/dynamic?r={url}",
            f"https://file-link.net/{SHORTNER_API}/{random.random() * 1000}/dynamic?r={url}"]
        return random.choice(linkvertise)

    elif "bitly.com" in SHORTNER_SITE:
        # pyshorteners is blocking, so we run it in a separate thread to keep the bot fast.
        s = pyshorteners.Shortener(api_key=SHORTNER_API)
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, s.bitly.short, longurl)

    elif "ouo.io" in SHORTNER_SITE:
        async with aiohttp.ClientSession() as session:
            async with session.get(f'http://ouo.io/api/{SHORTNER_API}?s={longurl}', ssl=False) as resp:
                return await resp.text()

    else:
        # Generic API handler (Works for most shorteners)
        async with aiohttp.ClientSession() as session:
            try:
                async with session.get(f'https://{SHORTNER_SITE}/api?api={SHORTNER_API}&url={longurl}&format=text', ssl=False) as resp:
                    return await resp.text()
            except Exception as e:
                # Fallback if there is an error
                print(f"Shortener Error: {e}")
                return longurl
