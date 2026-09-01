# Steganalysis Detection API

A small FastAPI backend that inspects an uploaded PNG/BMP image and reports
whether it likely contains **LSB (Least Significant Bit) steganography** —
the most common technique for hiding data inside images — using two
classic detection methods: the **chi-square attack** and **RS
(Regular-Singular) analysis**.

This is a simplified, web-deployable version of a broader thesis project
on stegomalware detection. The goal here is a clean, explainable,
working demo, not a forensic-grade tool — see [Limitations](#limitations)
for what that means in practice.

## Why steganalysis?

Steganography — hiding data inside other data so its presence isn't
obvious — has legitimate uses (watermarking, covert communication in
censored environments) and malicious ones (stegomalware: hiding payloads,
C2 instructions, or exfiltrated data inside innocuous-looking images to
slip past content filters and antivirus scanning). LSB embedding is the
simplest and most widely taught form of image steganography: it hides
data by overwriting the least-significant bit of each pixel's color
value, a change invisible to the eye but statistically detectable.
Steganalysis is the corresponding detection field — this project applies
two of its foundational statistical techniques.

## How it works

### Chi-square attack

LSB embedding pulls the frequency of "pairs of values" — e.g. pixel
values 4 and 5, or 118 and 119 — toward each other, because flipping a
pixel's LSB only ever moves it between the two members of its pair, and
payload bits are typically ~50/50 ones and zeros. A natural photo has no
such reason for a pair's two values to be equally common. The chi-square
attack runs a statistical goodness-of-fit test, block by block, checking
how well each block's pair frequencies match "already equalized" — the
more blocks that match, the more of the image looks embedded.

**Known weak spot** (and it shows up in this repo's own test fixtures —
see `tests/fixtures/`): images with smooth gradients or a lot of natural
noise can *already* have close-to-equal pair frequencies for reasons that
have nothing to do with steganography, causing false positives. This is
a documented limitation of the classic chi-square attack, not a bug —
it's the reason the field moved on to more robust methods like RS
analysis.

### RS (Regular-Singular) Analysis

More robust than chi-square, at the cost of more compute. The image is
split into small groups of 4 adjacent pixels. Each group gets a
"discrimination value" — roughly, how noisy/rough it is (sum of
differences between adjacent pixels). Each group is then flipped two
different ways (a fixed mask pattern applied with two different bit-flip
functions) and reclassified as **Regular** (flipping made it noisier),
**Singular** (flipping made it smoother), or **Unusable** (no change).

In an untouched image, the two flip variants produce roughly symmetric
R/S statistics. LSB embedding — which overwrites LSBs with close-to-random
bits — breaks that symmetry. The suspicion score here is a scaled measure
of that asymmetry. In this repo's own testing (see below), RS analysis
correctly and monotonically tracked embedding rate from 10% to 100%
payload capacity, while staying near-zero on every clean test image —
noticeably more reliable than chi-square across the board.

### Combining the two into `overall_verdict`

`overall_verdict` is the average of the two methods' scores, not simply
whichever verdict is worse. Given chi-square's known false-positive
tendency on smooth/noisy images (above), letting either method's flag
dominate would make the tool cry wolf on plenty of legitimate images.
Both raw per-method scores are always returned in the response, so a
caller can weigh them differently if needed — RS analysis is the more
trustworthy signal of the two.

### Verdict thresholds

Each score is 0-1. `< 0.3` → `clean`, `0.3–0.6` → `suspicious`,
`>= 0.6` → `likely_stego`. These are heuristic cutoffs picked by manual
tuning against real and synthetic test images, not derived from formal
statistical theory — treat them as a rough triage signal, not a
certainty.

## Limitations

- **JPEG is rejected outright.** JPEG's lossy DCT compression alters or
  destroys the raw LSB plane both methods depend on — there's no
  reliable "LSB" to analyze in a re-compressed image. Only PNG and BMP
  (lossless formats) are accepted.
- **LSB-focused only.** This tool detects naive, sequential LSB
  embedding — the technique taught as the introductory case in
  steganalysis. It will **not** reliably detect more advanced/adaptive
  embedding (e.g. matrix embedding, F5, adaptive edge-based embedding,
  spread-spectrum techniques) which are specifically designed to evade
  exactly these statistical signatures.
- **Chi-square false positives on smooth/noisy images.** Documented
  above — verified against this repo's own generated test fixtures. This
  is exactly why `overall_verdict` averages both scores instead of
  trusting either one alone.
- **Heuristic thresholds, not forensic-grade.** Score cutoffs are
  reasonable defaults, not calibrated against a large labeled dataset.
  Treat results as "worth a closer look," not a legal or definitive
  determination.
- **Small message / low embedding-rate payloads are hard to detect.**
  Both methods rely on statistical drift across many pixels; a small
  payload embedded in a large image can fall under the detection floor
  (visible in this repo's own `tests/fixtures/*_stego_1kb.png` results).

## Project structure

```
stego-api/
├── app/
│   ├── main.py              # FastAPI app, routes, CORS config
│   ├── analysis/
│   │   ├── chi_square.py    # Chi-square attack
│   │   ├── rs_analysis.py   # RS Analysis
│   │   └── utils.py         # image loading, bit-plane extraction, shared helpers
│   ├── models.py             # Pydantic response schemas
│   └── config.py             # settings (max file size, allowed origins, thresholds)
├── tests/
│   ├── generate_test_images.py   # synthetic clean images + LSB embedder + fixture generator
│   ├── fixtures/                  # generated clean + stego PNGs (1KB/10KB/50KB payloads)
│   └── test_analysis.py
├── requirements.txt
├── requirements-dev.txt
├── render.yaml / Procfile
└── README.md
```

## API

### `POST /analyze`

Multipart form upload, field name `file`. PNG/BMP only, 5MB max.

```json
{
  "filename": "sample.png",
  "chi_square": {
    "score": 0.83,
    "verdict": "likely_stego",
    "explanation": "..."
  },
  "rs_analysis": {
    "score": 0.71,
    "verdict": "likely_stego",
    "explanation": "..."
  },
  "overall_verdict": "likely_stego",
  "bit_plane_preview": "<base64-encoded PNG of the LSB plane>"
}
```

### `GET /health`

Basic liveness check for deploy monitoring — returns `{"status": "ok"}`.

Interactive docs are auto-generated by FastAPI at `/docs` (Swagger UI) and
`/redoc` once the server is running.

## Local development

```bash
cd stego-api
python3 -m venv venv
source venv/bin/activate          # Windows: venv\Scripts\activate
pip install -r requirements-dev.txt   # includes requirements.txt + test deps

# Generate the test fixture images (clean + LSB-embedded samples)
python -m tests.generate_test_images

# Run the test suite
pytest

# Run the dev server
uvicorn app.main:app --reload
# -> http://127.0.0.1:8000/docs
```

Try it against a generated fixture:

```bash
curl -F "file=@tests/fixtures/photo_like_stego_50kb.png;type=image/png" \
  http://127.0.0.1:8000/analyze
```

## Deployment (Render or Railway)

Both `render.yaml` (Render Blueprint) and a `Procfile` (Railway/Heroku-style)
are included — either platform's free tier works.

**Render:** connect the repo, choose "New +" → "Blueprint", it picks up
`render.yaml` automatically. Set the `ALLOWED_ORIGINS` env var in the
dashboard to your deployed frontend's URL (comma-separated for multiple
origins) — it defaults to `http://localhost:3000` only.

**Railway:** connect the repo; it detects the `Procfile` automatically.
Set `ALLOWED_ORIGINS` (and optionally `MAX_FILE_SIZE_BYTES`) as env vars
in the Railway dashboard.

Either way, the start command is:

```bash
uvicorn app.main:app --host 0.0.0.0 --port $PORT
```

## Credit

The chi-square attack and RS analysis implementations here are simplified
adaptations of the detection approaches from:

- A. Westfeld & A. Pfitzmann, *"Attacks on Steganographic Systems"* (2000)
  — chi-square (pairs-of-values) attack.
- J. Fridrich, M. Goljan & R. Du, *"Reliable Detection of LSB
  Steganography in Color and Grayscale Images"* (2001) — RS analysis.

This backend is a portfolio-scale re-implementation of detection concepts
originally explored in more depth as part of a thesis project on
stegomalware detection.
