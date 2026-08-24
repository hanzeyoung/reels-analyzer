import { Link, useParams } from "react-router-dom";

import { ApiError } from "../../api/client";
import { ProgressView } from "./components/ProgressView";
import { ResultView } from "./components/ResultView";
import { ErrorState, Skeleton } from "./components/StatusStates";
import { useJob } from "./hooks/useJob";

export function JobPage() {
  const { jobId } = useParams<{ jobId: string }>();
  const query = useJob(jobId ?? "");

  return (
    <div className="mx-auto max-w-md p-6">
      <Link to="/" className="text-sm text-gray-400">
        ← 새 분석
      </Link>
      <h1 className="mt-2 text-xl font-semibold">분석 결과</h1>

      <div className="mt-6">
        {query.isPending && <Skeleton />}

        {query.isError && (
          <ErrorState
            message={
              query.error instanceof ApiError && query.error.status === 404
                ? "해당 분석을 찾을 수 없습니다. URL을 다시 확인해주세요."
                : "결과를 불러오지 못했습니다. 네트워크 상태를 확인해주세요."
            }
            onRetry={() => query.refetch()}
          />
        )}

        {query.data?.status === "failed" && (
          <ErrorState
            message={query.data.error ?? "분석이 실패했습니다."}
            onRetry={() => query.refetch()}
          />
        )}

        {query.data && (query.data.status === "queued" || query.data.status === "running") && (
          <ProgressView job={query.data} />
        )}

        {query.data?.status === "done" && query.data.result && (
          <ResultView guide={query.data.result} />
        )}
      </div>
    </div>
  );
}
