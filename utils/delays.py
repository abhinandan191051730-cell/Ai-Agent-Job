import random
import asyncio


async def human_delay(min_sec: float = 2.0, max_sec: float = 8.0):
    delay = random.uniform(min_sec, max_sec)
    await asyncio.sleep(delay)


async def random_jitter(base: float = 1.0, jitter: float = 0.5):
    delay = base + random.uniform(-jitter, jitter)
    await asyncio.sleep(max(0.1, delay))
