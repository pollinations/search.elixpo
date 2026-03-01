import asyncio
import random
import os
import requests
from urllib.parse import quote
from dotenv import load_dotenv
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from pipeline.config import POLLINATIONS_ENDPOINT_IMAGE

load_dotenv()


async def create_image_from_prompt(prompt: str) -> str:
    """Generate an image via Pollinations and return the direct URL."""
    seed = random.randint(0, 10000)
    image_url = f"{POLLINATIONS_ENDPOINT_IMAGE}{quote(prompt)}?model=flux&height=512&width=512&seed={seed}&quality=high&enhance=true"

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {os.getenv('TOKEN')}"
    }

    response = await asyncio.to_thread(
        requests.head, image_url, headers=headers, timeout=15
    )
    response.raise_for_status()

    return image_url


if __name__ == "__main__":
    async def main():
        url = await create_image_from_prompt("a beautiful landscape")
        print(url)
    asyncio.run(main())
