# Steganalysis Detection Tool — Frontend

Next.js (App Router, TypeScript, Tailwind CSS) frontend for the
[stego-api](../stego-api) backend. Upload a PNG/BMP image and see a
chi-square attack + RS analysis steganalysis report, or try one of the
built-in sample images.

This is a separate deploy from the backend by design — Vercel for this,
Render/Railway for the API. See `../steganalysis-remaining-steps.md` for
the full build/deploy plan this project follows.

## Local development

```bash
npm install
cp .env.example .env.local   # point NEXT_PUBLIC_API_URL at your backend
npm run dev
```

Open [http://localhost:3000](http://localhost:3000). By default
`.env.local` points at `http://localhost:8000`, so run `stego-api`'s dev
server alongside this one (see its README).

## Environment variables

| Variable               | Description                                                        |
| ----------------------- | ------------------------------------------------------------------ |
| `NEXT_PUBLIC_API_URL`   | Base URL of the backend (no trailing slash). Set per-environment — localhost in dev, the deployed Render/Railway URL in Vercel's project settings for production. |

## Project structure

```
src/
├── app/
│   ├── page.tsx           # Home page — owns upload/analysis state
│   ├── layout.tsx
│   └── globals.css
├── components/
│   ├── UploadArea.tsx     # Drag-and-drop upload, client-side validation
│   ├── SampleImages.tsx   # "Try a sample" pre-loaded images
│   └── ResultsSection.tsx # Idle/loading/error/success result states
└── lib/
    ├── api.ts             # POST /analyze client, timeout + error handling
    ├── types.ts           # Mirrors stego-api's Pydantic response schema
    └── format.ts          # Small display helpers (file size, etc.)

public/samples/             # Static sample images (copies of stego-api's
                             # tests/fixtures/photo_like_*.png)
```

## Notes

- Only PNG/BMP uploads are accepted — JPEG's lossy compression destroys
  the LSB data both detection methods rely on (validated client-side and
  rejected server-side).
- Max upload size is 5MB, matching the backend's limit.
- If the backend is on a free hosting tier and asleep, the first request
  can take 20-50s; the UI shows a "waking up" message if a request runs
  past ~5s.

## Deploy (Vercel)

1. Push this repo to GitHub.
2. Import it into Vercel.
3. Add `NEXT_PUBLIC_API_URL` in the project's environment variables,
   pointing at your deployed backend.
4. Deploy, then test the live site end-to-end with a real upload.
