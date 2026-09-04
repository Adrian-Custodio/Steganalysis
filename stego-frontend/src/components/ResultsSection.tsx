// Renders the four analysis states: idle, loading, error, and result.

import type { AnalyzeResponse, MethodResult, Verdict } from "@/lib/types";

const VERDICT_STYLES: Record<
  Verdict,
  { label: string; badge: string; bar: string }
> = {
  clean: {
    label: "Clean",
    badge: "border-emerald-500/40 bg-emerald-500/10 text-emerald-300",
    bar: "bg-emerald-500",
  },
  suspicious: {
    label: "Suspicious",
    badge: "border-amber-500/40 bg-amber-500/10 text-amber-300",
    bar: "bg-amber-500",
  },
  likely_stego: {
    label: "Likely Stego",
    badge: "border-red-500/40 bg-red-500/10 text-red-300",
    bar: "bg-red-500",
  },
};

const METHOD_INFO: Record<"chi_square" | "rs_analysis", { label: string; blurb: string }> = {
  chi_square: {
    label: "Chi-Square Attack",
    blurb:
      "LSB embedding tends to equalize the frequency of pixel value pairs " +
      "(e.g. 2k and 2k+1). This test checks how far each color channel's " +
      "pair frequencies drift from what a natural image would show — a " +
      "strong drift suggests tampering. Fast, but can misfire on smooth " +
      "or naturally noisy images.",
  },
  rs_analysis: {
    label: "RS Analysis",
    blurb:
      "Groups of pixels are flipped in their least-significant bit and " +
      "reclassified as “Regular” or “Singular” based on how " +
      "that changes local smoothness. A significant imbalance between " +
      "flipped and unflipped groups indicates likely LSB embedding. More " +
      "robust than chi-square, but more compute-intensive.",
  },
};

type Status = "idle" | "loading" | "error" | "success";

type ResultsSectionProps = {
  status: Status;
  result: AnalyzeResponse | null;
  error: string | null;
  isSlow: boolean;
};

function VerdictBadge({ verdict }: { verdict: Verdict }) {
  const style = VERDICT_STYLES[verdict];
  return (
    <span
      className={`inline-flex items-center rounded-full border px-3 py-1 text-sm font-medium ${style.badge}`}
    >
      {style.label}
    </span>
  );
}

function MethodCard({
  method,
  result,
}: {
  method: "chi_square" | "rs_analysis";
  result: MethodResult;
}) {
  const info = METHOD_INFO[method];
  const style = VERDICT_STYLES[result.verdict];
  const pct = Math.round(result.score * 100);

  return (
    <div className="rounded-lg border border-neutral-800 bg-neutral-950/40 p-4">
      <div className="flex items-center justify-between gap-2">
        <p className="text-xs font-medium uppercase tracking-wide text-neutral-500">
          {info.label}
        </p>
        <span className="text-xs font-medium text-neutral-400">{pct}%</span>
      </div>

      <div
        className="mt-3 h-2 w-full overflow-hidden rounded-full bg-neutral-800"
        role="progressbar"
        aria-valuenow={pct}
        aria-valuemin={0}
        aria-valuemax={100}
        aria-label={`${info.label} suspicion score`}
      >
        <div
          className={`h-full rounded-full transition-all ${style.bar}`}
          style={{ width: `${pct}%` }}
        />
      </div>

      <p className="mt-3 text-sm text-neutral-400">{result.explanation}</p>

      <details className="mt-2 group">
        <summary className="cursor-pointer text-xs text-neutral-500 hover:text-neutral-300 [&::-webkit-details-marker]:hidden">
          What is {info.label}?
        </summary>
        <p className="mt-2 text-xs leading-relaxed text-neutral-500">
          {info.blurb}
        </p>
      </details>
    </div>
  );
}

function IdleState() {
  return (
    <div className="flex flex-col items-center text-center">
      <svg
        xmlns="http://www.w3.org/2000/svg"
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        strokeWidth={1.5}
        className="h-8 w-8 text-neutral-600"
        aria-hidden="true"
      >
        <path
          strokeLinecap="round"
          strokeLinejoin="round"
          d="M9.75 3.104v5.714a2.25 2.25 0 0 1-.659 1.591L5 14.5M9.75 3.104c-.251.023-.501.05-.75.082m.75-.082a24.301 24.301 0 0 1 4.5 0m0 0v5.714c0 .597.237 1.17.659 1.591L19.8 15.3M14.25 3.104c.251.023.501.05.75.082M19.8 15.3l-1.57.393A9.065 9.065 0 0 1 12 15a9.065 9.065 0 0 0-6.23-.696L5 14.5m14.8.8 1.402 1.402c1.232 1.232.65 3.318-1.067 3.611A48.309 48.309 0 0 1 12 21c-2.773 0-5.491-.235-8.135-.687-1.718-.293-2.3-2.379-1.067-3.611L5 14.5"
        />
      </svg>
      <p className="mt-3 text-sm text-neutral-400">
        Upload an image above to see its analysis here.
      </p>
    </div>
  );
}

function LoadingState({ isSlow }: { isSlow: boolean }) {
  return (
    <div className="flex flex-col items-center text-center">
      <svg
        className="h-8 w-8 animate-spin text-emerald-500"
        viewBox="0 0 24 24"
        fill="none"
        aria-hidden="true"
      >
        <circle
          className="opacity-25"
          cx="12"
          cy="12"
          r="10"
          stroke="currentColor"
          strokeWidth="4"
        />
        <path
          className="opacity-75"
          fill="currentColor"
          d="M4 12a8 8 0 0 1 8-8v4a4 4 0 0 0-4 4H4z"
        />
      </svg>
      <p className="mt-3 text-sm text-neutral-400">Running analysis…</p>
      {isSlow && (
        <p className="mt-2 max-w-sm text-xs text-neutral-500">
          Taking longer than usual — this backend runs on a free hosting
          tier and may need ~20-50s to wake up from sleep. Hang tight.
        </p>
      )}
    </div>
  );
}

function ErrorState({ message }: { message: string }) {
  return (
    <div className="flex flex-col items-center text-center">
      <svg
        xmlns="http://www.w3.org/2000/svg"
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        strokeWidth={1.5}
        className="h-8 w-8 text-red-500"
        aria-hidden="true"
      >
        <path
          strokeLinecap="round"
          strokeLinejoin="round"
          d="M12 9v3.75m9-.75a9 9 0 1 1-18 0 9 9 0 0 1 18 0Zm-9 3.75h.008v.008H12v-.008Z"
        />
      </svg>
      <p className="mt-3 text-sm font-medium text-red-400">
        Analysis failed
      </p>
      <p className="mt-1 max-w-sm text-sm text-neutral-500">{message}</p>
    </div>
  );
}

function SuccessState({ result }: { result: AnalyzeResponse }) {
  return (
    <div>
      <div className="flex flex-col items-center gap-3 text-center">
        <p className="text-xs uppercase tracking-wide text-neutral-500">
          Overall verdict
        </p>
        <VerdictBadge verdict={result.overall_verdict} />
        <p className="max-w-sm text-xs text-neutral-600">
          Heuristic result averaging both methods below — not
          forensic-grade.
        </p>
      </div>

      <div className="mt-8 grid gap-4 sm:grid-cols-2">
        <MethodCard method="chi_square" result={result.chi_square} />
        <MethodCard method="rs_analysis" result={result.rs_analysis} />
      </div>

      <div className="mt-6">
        <p className="text-xs font-medium uppercase tracking-wide text-neutral-500">
          LSB bit-plane preview
        </p>
        <p className="mt-1 text-xs text-neutral-600">
          The least-significant bit of each pixel, rendered as black/white —
          embedded data often shows up as visual noise or patterns here.
        </p>
        <div className="mt-3 overflow-hidden rounded-lg border border-neutral-800 bg-neutral-950">
          {/* eslint-disable-next-line @next/next/no-img-element -- base64 data URI, not a static asset */}
          <img
            src={`data:image/png;base64,${result.bit_plane_preview}`}
            alt="LSB bit-plane of the analyzed image"
            className="w-full"
          />
        </div>
      </div>
    </div>
  );
}

export default function ResultsSection({
  status,
  result,
  error,
  isSlow,
}: ResultsSectionProps) {
  return (
    <section className="w-full">
      <h2 className="text-sm font-medium text-neutral-400">Results</h2>

      <div className="mt-3 rounded-xl border border-neutral-800 bg-neutral-900/40 p-8">
        {status === "idle" && <IdleState />}
        {status === "loading" && <LoadingState isSlow={isSlow} />}
        {status === "error" && <ErrorState message={error ?? "Unknown error."} />}
        {status === "success" && result && <SuccessState result={result} />}
      </div>
    </section>
  );
}
