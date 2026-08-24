import type { components } from "./generated/schema";

export type AnalysisRequest = components["schemas"]["AnalysisRequest"];
export type UserConstraints = components["schemas"]["UserConstraints"];
export type CreateJobResponse = components["schemas"]["CreateJobResponse"];
export type JobDetailResponse = components["schemas"]["JobDetailResponse"];
export type Guide = components["schemas"]["Guide"];
export type ShotListItem = components["schemas"]["ShotListItem"];
export type CaptionDraft = components["schemas"]["CaptionDraft"];
export type AudioRecommendation = components["schemas"]["AudioRecommendation"];
export type DiagnosisCard = components["schemas"]["DiagnosisCard"];
export type JobStage = NonNullable<JobDetailResponse["stage"]>;

export class ApiError extends Error {
  status: number;

  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`/api${path}`, {
    headers: { "Content-Type": "application/json" },
    ...init,
  });
  if (!response.ok) {
    // docs/05-api.md: 에러는 항상 {"detail": "..."} 형태.
    const body = (await response.json().catch(() => null)) as { detail?: string } | null;
    throw new ApiError(response.status, body?.detail ?? "요청을 처리하지 못했습니다.");
  }
  return response.json() as Promise<T>;
}

export function createAnalysis(payload: AnalysisRequest): Promise<CreateJobResponse> {
  return request<CreateJobResponse>("/analyses", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function getAnalysis(jobId: string): Promise<JobDetailResponse> {
  return request<JobDetailResponse>(`/analyses/${jobId}`);
}
