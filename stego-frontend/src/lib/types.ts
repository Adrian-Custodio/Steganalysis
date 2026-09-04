// Mirrors app/models.py in stego-api — keep in sync if the backend schema changes.

export type Verdict = "clean" | "suspicious" | "likely_stego";

export type MethodResult = {
  score: number;
  verdict: Verdict;
  explanation: string;
};

export type AnalyzeResponse = {
  filename: string;
  chi_square: MethodResult;
  rs_analysis: MethodResult;
  overall_verdict: Verdict;
  bit_plane_preview: string;
};
