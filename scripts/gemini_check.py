"""Check the configured Gemini key without displaying credentials."""
import asyncio
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from dotenv import load_dotenv
load_dotenv(ROOT / '.env')
import httpx
from culturefit import llm


async def run():
    print('Configured model:', llm.GEMINI_MODEL, flush=True)
    if '--models' in sys.argv:
        import os
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.get('https://generativelanguage.googleapis.com/v1beta/models',
                                        headers={'x-goog-api-key': os.environ['GEMINI_API_KEY']})
        print('Models HTTP:', response.status_code, flush=True)
        if response.is_success:
            print('Text models:', [m['name'] for m in response.json().get('models', [])
                                   if 'generateContent' in m.get('supportedGenerationMethods', [])], flush=True)
        else:
            raise SystemExit(1)
        return
    try:
        text = await llm._gemini('Reply with exactly: GEMINI_OK')
    except httpx.HTTPStatusError as exc:
        body = exc.response.json().get('error', {})
        print('Gemini HTTP:', exc.response.status_code, 'status:', body.get('status', 'unknown'), flush=True)
        # Google error messages may reflect request details. Only print a sanitized summary.
        if exc.response.status_code == 429:
            print('Quota/rate limit reached. Check Google AI Studio project quota or billing.')
        elif exc.response.status_code in (400, 403):
            print('Check API key validity, API permissions, and regional availability.')
        elif exc.response.status_code == 404:
            print('Configured model is unavailable for this key.')
        raise SystemExit(1)
    except httpx.RequestError as exc:
        print('Network error:', type(exc).__name__, flush=True)
        raise SystemExit(2)
    if not text or 'GEMINI_OK' not in text:
        print('No expected text response from Gemini.')
        raise SystemExit(1)
    print('Direct Gemini response: OK', flush=True)
    parsed = await llm.parse_constraint('No bars or clubs; avoid Altstadt.', ['Altstadt', 'Enge'])
    print('Constraint parsing:', json.dumps(parsed, ensure_ascii=False), flush=True)
    sample = {'areas': [{'area': 'Enge', 'scores': {'You': 85}, 'gives_up': {'You': 15},
              'evidence': {'You': [{'name': 'Example cafe', 'tags': ['Coffee', 'Art']}]}}],
              'low_confidence_for': []}
    explained = await llm.explain(sample)
    print('Explanation source:', explained['source'], flush=True)
    print('Explanation:', explained['text'], flush=True)
    assert parsed['source'] == 'gemini' and explained['source'] == 'gemini'
    assert 'Altstadt' in parsed['avoid_areas']
    print('PASS: generation, constraint parsing, and explanation use Gemini.')


if __name__ == '__main__':
    asyncio.run(run())
