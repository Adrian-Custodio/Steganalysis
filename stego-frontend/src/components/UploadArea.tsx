"use client";

import { useCallback, useRef, useState } from "react";
import { formatFileSize } from "@/lib/format";

// Mirrors the backend's validation rules (app/config.py in stego-api) so
// the user gets instant feedback instead of waiting on a round trip.
// JPEG is rejected because its lossy compression destroys the LSB data
// both detection methods depend on.
const ACCEPTED_EXTENSIONS = [".png", ".bmp"];
const MAX_FILE_SIZE_BYTES = 5 * 1024 * 1024; // 5MB

type UploadAreaProps = {
  file: File | null;
  onFileChange: (file: File | null) => void;
  onAnalyze: () => void;
  isAnalyzing: boolean;
};

function validateFile(file: File): string | null {
  const lowerName = file.name.toLowerCase();
  const hasAcceptedExtension = ACCEPTED_EXTENSIONS.some((ext) =>
    lowerName.endsWith(ext)
  );
  if (!hasAcceptedExtension) {
    return `Unsupported file type. Only ${ACCEPTED_EXTENSIONS.join(
      " and "
    )} are supported — JPEG's lossy compression destroys the LSB data this tool analyzes.`;
  }
  if (file.size > MAX_FILE_SIZE_BYTES) {
    return `File too large (${formatFileSize(
      file.size
    )}). Max size is ${formatFileSize(MAX_FILE_SIZE_BYTES)}.`;
  }
  return null;
}

export default function UploadArea({
  file,
  onFileChange,
  onAnalyze,
  isAnalyzing,
}: UploadAreaProps) {
  const [isDragging, setIsDragging] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  const handleFiles = useCallback(
    (fileList: FileList | null) => {
      const candidate = fileList?.[0];
      if (!candidate) return;

      const validationError = validateFile(candidate);
      if (validationError) {
        setError(validationError);
        onFileChange(null);
        return;
      }

      setError(null);
      onFileChange(candidate);
    },
    [onFileChange]
  );

  const handleDrop = useCallback(
    (e: React.DragEvent<HTMLDivElement>) => {
      e.preventDefault();
      setIsDragging(false);
      handleFiles(e.dataTransfer.files);
    },
    [handleFiles]
  );

  const clearFile = () => {
    setError(null);
    onFileChange(null);
    if (inputRef.current) inputRef.current.value = "";
  };

  return (
    <div className="w-full">
      <div
        role="button"
        tabIndex={0}
        onClick={() => inputRef.current?.click()}
        onKeyDown={(e) => {
          if (e.key === "Enter" || e.key === " ") inputRef.current?.click();
        }}
        onDragOver={(e) => {
          e.preventDefault();
          setIsDragging(true);
        }}
        onDragLeave={() => setIsDragging(false)}
        onDrop={handleDrop}
        className={[
          "flex flex-col items-center justify-center gap-3 rounded-xl border-2 border-dashed p-10 text-center transition-colors cursor-pointer",
          isDragging
            ? "border-emerald-400 bg-emerald-400/5"
            : "border-neutral-700 hover:border-neutral-500 bg-neutral-900/40",
        ].join(" ")}
      >
        <svg
          xmlns="http://www.w3.org/2000/svg"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth={1.5}
          className="h-10 w-10 text-neutral-500"
          aria-hidden="true"
        >
          <path
            strokeLinecap="round"
            strokeLinejoin="round"
            d="M3 16.5v2.25A2.25 2.25 0 0 0 5.25 21h13.5A2.25 2.25 0 0 0 21 18.75V16.5M16.5 8.25 12 3.75m0 0L7.5 8.25M12 3.75v12.75"
          />
        </svg>
        <p className="text-sm text-neutral-300">
          <span className="font-medium text-neutral-100">
            Drag and drop an image here
          </span>
          , or click to browse
        </p>
        <p className="text-xs text-neutral-500">
          PNG or BMP only &middot; max 5MB
        </p>
        <input
          ref={inputRef}
          type="file"
          accept={ACCEPTED_EXTENSIONS.join(",")}
          className="hidden"
          onChange={(e) => handleFiles(e.target.files)}
        />
      </div>

      {error && (
        <p className="mt-3 text-sm text-red-400" role="alert">
          {error}
        </p>
      )}

      {file && !error && (
        <div className="mt-4 flex items-center justify-between rounded-lg border border-neutral-800 bg-neutral-900/60 px-4 py-3">
          <div className="min-w-0">
            <p className="truncate text-sm font-medium text-neutral-100">
              {file.name}
            </p>
            <p className="text-xs text-neutral-500">
              {formatFileSize(file.size)}
            </p>
          </div>
          <button
            type="button"
            onClick={clearFile}
            className="ml-4 shrink-0 text-xs text-neutral-400 hover:text-neutral-200"
          >
            Remove
          </button>
        </div>
      )}

      <div className="mt-4">
        <button
          type="button"
          disabled={!file || !!error || isAnalyzing}
          onClick={onAnalyze}
          className={[
            "w-full rounded-lg px-4 py-2.5 text-sm font-medium transition-colors",
            !file || !!error || isAnalyzing
              ? "cursor-not-allowed bg-emerald-600/40 text-emerald-100/60"
              : "bg-emerald-600 text-white hover:bg-emerald-500",
          ].join(" ")}
        >
          {isAnalyzing ? (
            <span className="flex items-center justify-center gap-2">
              <svg
                className="h-4 w-4 animate-spin"
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
              Analyzing…
            </span>
          ) : (
            "Analyze Image"
          )}
        </button>
      </div>
    </div>
  );
}
