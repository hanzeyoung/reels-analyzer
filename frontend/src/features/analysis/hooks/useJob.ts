import { useQuery } from "@tanstack/react-query";

import { ApiError, getAnalysis } from "../../../api/client";

// docs/05-api.md: "폴링 간격 권장 2초. done/failed면 중단."
const POLL_INTERVAL_MS = 2000;

export function useJob(jobId: string) {
  return useQuery({
    queryKey: ["analysis", jobId],
    queryFn: () => getAnalysis(jobId),
    refetchInterval: (query) => {
      const status = query.state.data?.status;
      if (status === "done" || status === "failed") return false;
      return POLL_INTERVAL_MS;
    },
    retry: (failureCount, error) => {
      // 404(없는 job)는 재시도해도 의미 없다.
      if (error instanceof ApiError && error.status === 404) return false;
      return failureCount < 3;
    },
  });
}
