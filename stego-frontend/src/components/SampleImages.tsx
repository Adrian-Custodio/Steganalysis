"use client";

// "Try a sample" section — runs the tool on static PNGs in /public/samples/.

import { useState } from "react";

const SAMPLES = [
  {
    id: "clean",
    label: "Clean",
    description: "No embedded payload",
    src: "/samples/sample-clean.png",
  },
  {
    id: "small",
    label: "Small payload",
    description: "~1KB embedded",
    src: "/samples/sample-stego-small.png",
  },
  {
    id: "large",
    label: "Large payload",
    description: "~50KB embedded",
    src: "/samples/sample-stego-large.png",
  },
] as const;

type SampleImagesProps = {
  onSelect: (file: File) => void;
  disabled?: boolean;
};

export default function SampleImages({ onSelect, disabled }: SampleImagesProps) {
  const [loadingId, setLoadingId] = useState<string | null>(null);

  const handlePick = async (sample: (typeof SAMPLES)[number]) => {
    if (disabled) return;
    setLoadingId(sample.id);
    try {
      const response = await fetch(sample.src);
      const blob = await response.blob();
      const file = new File([blob], `${sample.id}.png`, { type: "image/png" });
      onSelect(file);
    } finally {
      setLoadingId(null);
    }
  };

  return (
    <div className="w-full">
      <h2 className="text-sm font-medium text-neutral-400">
        Or try a sample image
      </h2>
      <div className="mt-3 grid grid-cols-3 gap-3">
        {SAMPLES.map((sample) => (
          <button
            key={sample.id}
            type="button"
            disabled={disabled}
            onClick={() => handlePick(sample)}
            className="group overflow-hidden rounded-lg border border-neutral-800 bg-neutral-900/40 text-left transition-colors hover:border-neutral-600 disabled:cursor-not-allowed disabled:opacity-50"
          >
            <div className="relative aspect-square w-full bg-neutral-950">
              {/* eslint-disable-next-line @next/next/no-img-element -- small static thumbnail, not worth next/image config here */}
              <img
                src={sample.src}
                alt={`Sample: ${sample.label}`}
                className="h-full w-full object-cover transition-opacity group-hover:opacity-80"
              />
              {loadingId === sample.id && (
                <div className="absolute inset-0 flex items-center justify-center bg-neutral-950/60">
                  <svg
                    className="h-5 w-5 animate-spin text-emerald-400"
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
                </div>
              )}
            </div>
            <div className="px-2 py-2">
              <p className="text-xs font-medium text-neutral-200">
                {sample.label}
              </p>
              <p className="text-[11px] text-neutral-500">
                {sample.description}
              </p>
            </div>
          </button>
        ))}
      </div>
    </div>
  );
}
