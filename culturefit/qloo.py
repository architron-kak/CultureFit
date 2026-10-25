"""Small async Qloo client: rate limit (key allows 5 req/s, we use 4), cache, one retry on 429."""
import asyncio, os, time
import httpx

class Qloo:
    def __init__(self, key: str | None = None, rps: float = 4, ttl: int = 6 * 3600,
                 transport=None, max_cache: int = 512):
        key = key or os.getenv("QLOO_API_KEY", "").strip()
        if not key:
            raise RuntimeError("Set QLOO_API_KEY in the project .env file")
        if rps <= 0 or ttl < 0 or max_cache < 1:
            raise ValueError("Invalid rate limit or cache configuration")
        self.client = httpx.AsyncClient(
            base_url=os.getenv("QLOO_API_URL", "https://hackathon.api.qloo.com"),
            headers={"X-Api-Key": key, "Accept": "application/json"},
            timeout=40,
            transport=transport,
        )
        self.gap = 1 / rps
        self.ttl = ttl
        self._lock = asyncio.Lock()
        self._last = 0.0
        self._cache: dict = {}
        self.max_cache = max_cache

    async def close(self):
        await self.client.aclose()

    async def get(self, path: str, **params):
        key = (path, tuple(sorted(params.items())))
        hit = self._cache.get(key)
        if hit and time.monotonic() - hit[0] < self.ttl:
            return hit[1]
        for attempt in range(2):
            async with self._lock:  # pacing only
                wait = self._last + self.gap - time.monotonic()
                if wait > 0:
                    await asyncio.sleep(wait)
                self._last = time.monotonic()
            r = await self.client.get(path, params=params)
            if r.status_code == 429 and attempt == 0:
                try:
                    delay = float(r.headers.get("Retry-After", "1.5"))
                except ValueError:
                    delay = 1.5
                await asyncio.sleep(max(0, min(delay, 30)))
                continue
            r.raise_for_status()
            data = r.json()
            if len(self._cache) >= self.max_cache:
                self._cache.pop(next(iter(self._cache)))
            self._cache[key] = (time.monotonic(), data)
            return data

    async def search(self, query: str):
        try:
            d = await self.get("/search", query=query, take=5, sort_by="match")
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                return None
            raise
        res = d.get("results") or []
        exact = next((e for e in res if e.get("name", "").casefold() == query.casefold()), None)
        if exact:
            return exact
        return res[0] if res else None

    async def places_near(self, lat: float, lon: float, radius: int,
                          entity_ids: list[str], take: int = 20):
        d = await self.get(
            "/v2/insights",
            **{
                "filter.type": "urn:entity:place",
                "filter.location": f"POINT({lon} {lat})",
                "filter.location.radius": radius,
                "signal.interests.entities": ",".join(entity_ids),
                "feature.explainability": "true",
                "take": take,
            },
        )
        return d["results"]["entities"]
