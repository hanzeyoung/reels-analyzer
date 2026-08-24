import type { ReactNode } from "react";

export function Skeleton() {
  return (
    <div className="animate-pulse space-y-3">
      <div className="h-4 w-1/3 rounded bg-gray-200" />
      <div className="h-24 rounded bg-gray-200" />
      <div className="h-24 rounded bg-gray-200" />
    </div>
  );
}

export function ErrorState({
  message,
  onRetry,
}: {
  message: string;
  onRetry: () => void;
}) {
  return (
    <div className="rounded-xl border border-red-200 bg-red-50 p-6 text-center">
      <p className="text-sm text-red-700">{message}</p>
      <button
        type="button"
        onClick={onRetry}
        className="mt-4 rounded-lg bg-red-600 px-4 py-2 text-sm font-medium text-white"
      >
        다시 시도
      </button>
    </div>
  );
}

export function EmptyNote({ children }: { children: ReactNode }) {
  return <p className="rounded-lg bg-gray-100 p-4 text-sm text-gray-500">{children}</p>;
}
