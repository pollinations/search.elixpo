import asyncio
import itertools
import random
import os
import uuid
import requests
from urllib.parse import quote
from dotenv import load_dotenv
from loguru import logger
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from pipeline.config import POLLINATIONS_ENDPOINT_IMAGE, IMAGE_MODEL1, IMAGE_MODEL2

load_dotenv()

_model_cycle = itertools.cycle([IMAGE_MODEL1, IMAGE_MODEL2])
_BASE_URL = os.getenv("PUBLIC_BASE_URL", "https://search.elixpo.com").rstrip("/")


async def create_image_from_prompt(prompt: str) -> str:
    model = next(_model_cycle)
    seed = random.randint(0, 10000)
    image_id = str(uuid.uuid4())
    url = f"{_BASE_URL}/api/image/{image_id}"

    upstream_url = (
        f"{POLLINATIONS_ENDPOINT_IMAGE}{quote(prompt)}"
        f"?model=flux&height=462&width=768&seed={seed}&quality=hd&enhance=true"
    )
    headers = {"Authorization": f"Bearer {os.getenv('TOKEN')}"}

    logger.info(f"[Image] Upstream URL: {upstream_url}")
    logger.info(f"[Image] Model: {model} | Seed: {seed} | ID: {image_id}")

    t0 = time.perf_counter()
    try:
        response = await asyncio.to_thread(
            requests.get, upstream_url, headers=headers, timeout=60
        )
        response.raise_for_status()

        content_type = response.headers.get("Content-Type", "image/png")

        if not content_type.startswith("image/"):
            raise ValueError(f"Expected image, got Content-Type: {content_type}")
        if len(response.content) < 1000:
            raise ValueError(f"Response too small to be an image: {len(response.content)} bytes")

        from app.gateways.image import store_image
        store_image(image_id, response.content, content_type)
        elapsed = time.perf_counter() - t0
        logger.info(f"[Image] Generated with {model} (seed={seed}) in {elapsed:.2f}s ({len(response.content)} bytes) -> {image_id}")

    except requests.exceptions.Timeout:
        logger.error(f"[Image] TIMEOUT: Upstream took >60s | model={model} seed={seed} url={upstream_url[:200]}")
        raise RuntimeError(f"Image generation timed out (model={model})")
    except requests.exceptions.HTTPError as e:
        logger.error(f"[Image] HTTP {e.response.status_code} from {model} (seed={seed}) — {e.response.text[:200]}")
        raise RuntimeError(f"Image generation failed: HTTP {e.response.status_code}")
    except ValueError as e:
        logger.error(f"[Image] INVALID RESPONSE: {e} | model={model} seed={seed}")
        raise RuntimeError(str(e))
    except Exception as e:
        logger.error(f"[Image] FAILED: {type(e).__name__}: {e} | model={model} seed={seed}")
        raise

    return url


if __name__ == "__main__":
    async def main():
        prompt = "A lone celestial sorceress standing atop a crystalline tower, her flowing iridescent robes dissolving into trails of stardust, overlooking an endless ocean of glowing nebulae and floating ancient ruins, dramatic golden-hour lighting piercing through cosmic clouds, ultra-detailed digital painting, cinematic atmosphere"
        print(f"Generating image for: {prompt[:60]}...")
        try:
            url = await create_image_from_prompt(prompt)
            print(f"Success: {url}")
        except Exception as e:
            print(f"Failed: {e}")

    asyncio.run(main())
