import type { AnalyzeResponse } from "./types";

// Backend base URL — points at localhost in dev, the deployed Render/Railway
// URL in production. Set in .env.local (see .env.example).
const API_URL = process.env.NEXT_PUBLIC_API_URL;

// Render/Railway free-tier instances sleep after inactivity; the first
// request after idle can take 20-50s to wake up. 60s gives that room
// without leaving a genuinely broken request hanging forever.
const REQUEST_TIMEOUT_MS = 60_000;

export class ApiError extends Error {
  status?: number;

  constructor(message: string, status?: number) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

/**
 * POSTs an image to `${NEXT_PUBLIC_API_URL}/analyze` as multipart/form-data
 * and returns the parsed steganalysis report.
 */
export async function analyzeImage(file: File): Promise<AnalyzeResponse> {
  if (!API_URL) {
    throw new ApiError(
      "NEXT_PUBLIC_API_URL is not set — the app doesn't know where the detection API lives."
    );
  }

  const formData = new FormData();
  formData.append("file", file);

  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), REQUEST_TIMEOUT_MS);

  let response: Response;
  try {
    response = await fetch(`${API_URL}/analyze`, {
      method: "POST",
      body: formData,
      signal: controller.signal,
    });
  } catch (err) {
    if (err instanceof DOMException && err.name === "AbortError") {
      throw new ApiError(
        "The request timed out. The backend may be slow to wake up (free hosting tier) — please try again."
      );
    }
    throw new ApiError(
      "Couldn't reach the detection API. Check your connection and that the backend is running."
    );
  } finally {
    clearTimeout(timeoutId);
  }

  if (!response.ok) {
    let detail = `Request failed (${response.status}).`;
    try {
      const body = await response.json();
      if (typeof body?.detail === "string") detail = body.detail;
    } catch {
      // Non-JSON error body — fall back to the generic message above.
    }
    throw new ApiError(detail, response.status);
  }

  return (await response.json()) as AnalyzeResponse;
}
