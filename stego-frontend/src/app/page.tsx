"use client";

import { useCallback, useRef, useState } from "react";
import UploadArea from "@/components/UploadArea";
import ResultsSection from "@/components/ResultsSection";
import SampleImages from "@/components/SampleImages";
import { analyzeImage, ApiError } from "@/lib/api";
import type { AnalyzeResponse } from "@/lib/types";

type Status = "idle" | "loading" | "error" | "success";

// Free-tier backends (Render/Railway) can take 20-50s to wake up from
// sleep. If a request is still pending past this, show a friendlier
// "waking up" message instead of leaving a bare spinner.
const SLOW_REQUEST_THRESHOLD_MS = 5_000;

export default function Home() {
  const [file, setFile] = useState<File | null>(null);
  const [status, setStatus] = useState<Status>("idle");
  const [result, setResult] = useState<AnalyzeResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [isSlow, setIsSlow] = useState(false);
  const slowTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const runAnalysis = useCallback(async (target: File) => {
    setStatus("loading");
    setError(null);
    setIsSlow(false);

    slowTimerRef.current = setTimeout(
      () => setIsSlow(true),
      SLOW_REQUEST_THRESHOLD_MS
    );

    try {
      const response = await analyzeImage(target);
      setResult(response);
      setStatus("success");
    } catch (err) {
      const message =
        err instanceof ApiError
          ? err.message
          : "Something went wrong analyzing the image.";
      setError(message);
      setStatus("error");
    } finally {
      if (slowTimerRef.current) clearTimeout(slowTimerRef.current);
      setIsSlow(false);
    }
  }, []);

  const handleFileChange = (next: File | null) => {
    setFile(next);
    if (!next) {
      setStatus("idle");
      setResult(null);
      setError(null);
    }
  };

  const handleAnalyze = () => {
    if (file) runAnalysis(file);
  };

  const handleSampleSelect = (sampleFile: File) => {
    setFile(sampleFile);
    runAnalysis(sampleFile);
  };

  return (
    <main className="mx-auto flex w-full max-w-2xl flex-1 flex-col gap-10 px-6 py-16">
      <header className="text-center">
        <h1 className="text-2xl font-semibold text-neutral-100">
          Steganalysis Detection Tool
        </h1>
        <p className="mt-2 text-sm text-neutral-400">
          Upload a PNG or BMP image to check it for LSB steganography using
          a chi-square attack and RS analysis.
        </p>
      </header>

      <UploadArea
        file={file}
        onFileChange={handleFileChange}
        onAnalyze={handleAnalyze}
        isAnalyzing={status === "loading"}
      />

      <SampleImages onSelect={handleSampleSelect} disabled={status === "loading"} />

      <ResultsSection status={status} result={result} error={error} isSlow={isSlow} />

      <footer className="mt-4 text-center text-xs text-neutral-600">
        Heuristic, educational tool — not forensic-grade. LSB-focused
        detection only.
      </footer>
    </main>
  );
}
