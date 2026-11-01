# Academic Planning Dashboard

Responsive React, Vite, and TypeScript frontend for the academic planning API.

## Run locally

```bash
npm install
copy .env.example .env
npm run dev
```

During local development, Vite proxies `/api` requests to the Flask API at
`http://127.0.0.1:5000`, avoiding cross-origin browser requests. Start the API
in a separate terminal before using the dashboard. Set `VITE_API_BASE_URL` to
an absolute API root when deploying the frontend separately; its default is
`/api`. The dashboard displays loading, empty, and API error states rather than
substituting sample data.

## Other commands

- `npm run build` — type-check and create a production build in `dist/`
- `npm run preview` — serve the production build locally
- `npm run typecheck` — run the TypeScript project checks
