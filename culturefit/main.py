import json
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, StringConstraints, model_validator
from typing import Annotated
import httpx

load_dotenv(Path(__file__).resolve().parents[1] / ".env")

from .districts import CITIES  # noqa: E402
from .llm import explain, parse_constraint  # noqa: E402
from .qloo import Qloo  # noqa: E402
from .scoring import rank_areas  # noqa: E402

qloo: Qloo | None = None


@asynccontextmanager
async def lifespan(app):
    global qloo
    qloo = Qloo()
    try:
        yield
    finally:
        await qloo.close()
        qloo = None


app = FastAPI(lifespan=lifespan)
Text = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=120)]


class Person(BaseModel):
    name: Text
    favorites: list[Text] = Field(min_length=1, max_length=6)


class RankRequest(BaseModel):
    city: Text = "Zurich"
    people: list[Person] = Field(min_length=1, max_length=2)
    exclude: list[Text] = Field(default_factory=list, max_length=32)
    avoid_areas: list[Text] = Field(default_factory=list, max_length=20)

    @model_validator(mode="after")
    def unique_names(self):
        names = [p.name.casefold() for p in self.people]
        if len(set(names)) != len(names):
            raise ValueError("Participant names must be unique")
        return self


class Refine(BaseModel):
    city: Text = "Zurich"
    text: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=300)]


def sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


@app.get("/api/cities")
async def cities():
    return {c: list(v["areas"]) for c, v in CITIES.items()}


@app.post("/api/refine")
async def refine(r: Refine):
    city = CITIES.get(r.city)
    if not city:
        raise HTTPException(422, "Unknown city")
    return await parse_constraint(r.text, list(city["areas"]))


@app.post("/api/rank")
async def rank(req: RankRequest):
    city = CITIES.get(req.city)
    if not city:
        raise HTTPException(422, "Unknown city")
    known = {a.casefold() for a in city["areas"]}
    avoid = {a.casefold() for a in req.avoid_areas}
    if avoid - known:
        raise HTTPException(422, "Unknown area in avoid_areas")
    areas = {k: v for k, v in city["areas"].items() if k.casefold() not in avoid}
    if not areas:
        raise HTTPException(422, "All areas were excluded")
    if qloo is None:
        raise HTTPException(503, "Qloo client is not available")

    async def stream():
        trace = []

        def step(text):
            trace.append(text)
            return sse("step", {"text": text})

        try:
            ids = {}
            for p in req.people:
                ids[p.name] = []
                for fav in dict.fromkeys(p.favorites):
                    yield step(f"[{p.name}] searching Qloo for '{fav}'")
                    hit = await qloo.search(fav)
                    if hit:
                        if hit["entity_id"] not in ids[p.name]:
                            ids[p.name].append(hit["entity_id"])
                        yield step(f"[{p.name}] matched: {hit['name']}")
                    else:
                        yield step(f"[{p.name}] not found in Qloo: {fav}")
                if not ids[p.name]:
                    yield sse("error", {"message": f"no favorites matched for {p.name}"})
                    return

            data = {p: {} for p in ids}
            for area, (lat, lon) in areas.items():
                for p in ids:
                    yield step(f"[{p}] checking {area}")
                    data[p][area] = await qloo.places_near(lat, lon, city["radius"], ids[p])

            yield step("comparing areas, group fit = the weakest person's score")
            result = rank_areas(data, req.exclude)
            for a in result["areas"]:
                a["lat"], a["lon"] = areas[a["area"]]
            result["radius"] = city["radius"]
            result["trace"] = trace
            yield sse("result", result)

            yield step("writing the explanation")
            yield sse("explanation", await explain(result))
        except httpx.HTTPStatusError as e:
            yield sse("error", {"message": f"Qloo returned HTTP {e.response.status_code}. Check API access or try again later."})
        except httpx.RequestError:
            yield sse("error", {"message": "Could not reach Qloo. Check your connection and try again."})
        except Exception:
            logging.getLogger(__name__).exception("Ranking failed")
            yield sse("error", {"message": "Could not complete ranking. Check the server logs."})

    return StreamingResponse(stream(), media_type="text/event-stream", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


app.mount("/", StaticFiles(directory=Path(__file__).parent / "static", html=True), name="static")
