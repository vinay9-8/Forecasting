# Academic Planning Dashboard

Responsive React, Vite, and TypeScript frontend for the academic planning API.

## Run locally

```bash
npm install
copy .env.example .env
npm run dev
```

Set `VITE_API_BASE_URL` to the API root before starting Vite. It defaults to
`http://localhost:5000/api`. The API is expected to provide the endpoints in
the project brief; the dashboard intentionally displays loading, empty, and
API error states rather than substituting sample data.

## Other commands

- `npm run build` — type-check and create a production build in `dist/`
- `npm run preview` — serve the production build locally
- `npm run typecheck` — run the TypeScript project checks
