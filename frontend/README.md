# Frontend

React 19 + Vite + TypeScript + Tailwind.

```bash
npm install
npm run dev      # http://localhost:5173, proxies /api to :8000
npm run build    # -> dist/
```

Run the backend alongside it:
```bash
uvicorn app.api.main:app --port 8000
```

In production nginx serves `dist/` and proxies `/api` to the API container,
so the frontend is same-origin with the backend — no CORS, and no backend
hostname baked into the build.
