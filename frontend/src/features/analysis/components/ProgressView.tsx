import type { JobDetailResponse, JobStage } from "../../../api/client";

// docs/07-ui.md: 수집 → 점수 → 다운로드 → 분석 → 비교 → 내 릴스 진단 → 작성
const STEPS: { stage: JobStage; label: string }[] = [
  { stage: "collecting", label: "수집" },
  { stage: "scoring", label: "점수" },
  { stage: "preparing", label: "다운로드" },
  { stage: "analyzing", label: "분석" },
  { stage: "comparing", label: "비교" },
  { stage: "diagnosing", label: "내 릴스 진단" },
  { stage: "generating", label: "작성" },
];

export function ProgressView({ job }: { job: JobDetailResponse }) {
  const currentIndex = job.stage ? STEPS.findIndex((s) => s.stage === job.stage) : -1;

  return (
    <div className="space-y-6">
      {job.status === "queued" && (
        <p className="text-sm text-gray-500">대기 중이에요. 잠시만 기다려주세요.</p>
      )}

      <ol className="space-y-2">
        {STEPS.map((step, i) => {
          const state = i < currentIndex ? "done" : i === currentIndex ? "active" : "pending";
          return (
            <li key={step.stage} className="flex items-center gap-3 text-sm">
              <span
                className={`flex h-6 w-6 shrink-0 items-center justify-center rounded-full text-xs ${
                  state === "done"
                    ? "bg-black text-white"
                    : state === "active"
                      ? "bg-black text-white animate-pulse"
                      : "bg-gray-200 text-gray-400"
                }`}
              >
                {state === "done" ? "✓" : i + 1}
              </span>
              <span className={state === "pending" ? "text-gray-400" : "text-gray-800"}>
                {step.label}
                {state === "active" &&
                  step.stage === "analyzing" &&
                  job.progress.total > 0 &&
                  ` (${job.progress.current}/${job.progress.total})`}
              </span>
            </li>
          );
        })}
      </ol>

      <div className="rounded-lg bg-blue-50 p-4 text-sm text-blue-700">
        보통 5~15분 정도 걸려요. 이 화면을 나가도 괜찮아요 — 이 주소를 저장해두면 나중에
        다시 열어서 이어볼 수 있어요.
      </div>
    </div>
  );
}
