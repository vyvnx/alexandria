# alexandria

aggregate all your knowledge and find relations to it.

ingest urls and notes, an llm pulls out the entities, they get embedded and
stored in a graph, and you explore the whole thing as a map.


## tech

monorepo: turborepo, uv workspace (python), npm workspaces (js)

- core (python): pydantic, sqlite + sqlite-vec, trafilatura, rapidfuzz
- api (python): fastapi, uvicorn
- engine (python): qwen3 embeddings (sentence-transformers), openai / ollama providers
- web (typescript): vite, react, sigma.js, graphology, tailwind

## run

needs `uv` and `node`.

```sh
uv sync            # python deps
npm install        # js deps
cp .env.example .env   # then set ALEX_OPENAI_API_KEY
```

everything at once:

```sh
npm run dev        # turbo runs every app
```

or one at a time:

```sh
cd apps/api && uv run python -m alexandria_api   # http://localhost:8000
cd apps/web && npm run dev                       # vite dev server
```

tests:

```sh
npm test           # or: uv run pytest
```

## deploy

```sh
docker compose up --build
```

api on `:8000`, engine on `:8100`. in v1 the api embeds the engine in-process,
so it runs standalone; the engine service is the seam for moving ml/gpu compute
onto its own box later.
