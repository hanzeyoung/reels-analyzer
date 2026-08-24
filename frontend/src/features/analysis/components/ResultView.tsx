import { useState } from "react";

import type { Guide } from "../../../api/client";
import { EmptyNote } from "./StatusStates";

const CONFIDENCE_STYLE: Record<Guide["confidence"], string> = {
  충분: "bg-green-100 text-green-800",
  제한적: "bg-yellow-100 text-yellow-800",
  불충분: "bg-red-100 text-red-800",
};

type Tab = "shots" | "captions" | "audio" | "diagnosis";

export function ResultView({ guide }: { guide: Guide }) {
  const hasDiagnosis = guide.diagnosis.length > 0;
  const [tab, setTab] = useState<Tab>("shots");

  const tabs: { key: Tab; label: string }[] = [
    { key: "shots", label: "샷 리스트" },
    { key: "captions", label: "자막 카피" },
    { key: "audio", label: "음원" },
    // docs/07-ui.md: 내 릴스 없으면 탭 숨김.
    ...(hasDiagnosis ? [{ key: "diagnosis" as const, label: "진단" }] : []),
  ];

  return (
    <div className="space-y-4">
      <div className="rounded-xl border border-gray-200 bg-white p-4">
        <div className="flex items-center gap-2">
          <span
            className={`rounded-full px-2 py-0.5 text-xs font-medium ${CONFIDENCE_STYLE[guide.confidence]}`}
          >
            표본 신뢰도: {guide.confidence}
          </span>
        </div>
        <p className="mt-2 text-sm text-gray-600">{guide.evidence_note}</p>
        {guide.confidence !== "충분" && guide.caveat && (
          <p className="mt-2 rounded-lg bg-amber-50 p-3 text-sm text-amber-800">
            ⚠ {guide.caveat}
          </p>
        )}
      </div>

      <div className="flex gap-1 border-b border-gray-200">
        {tabs.map((t) => (
          <button
            key={t.key}
            type="button"
            onClick={() => setTab(t.key)}
            className={`px-3 py-2 text-sm font-medium ${
              tab === t.key
                ? "border-b-2 border-black text-black"
                : "text-gray-400 hover:text-gray-600"
            }`}
          >
            {t.label}
          </button>
        ))}
      </div>

      {tab === "shots" && <ShotListTab guide={guide} />}
      {tab === "captions" && <CaptionTab guide={guide} />}
      {tab === "audio" && <AudioTab guide={guide} />}
      {tab === "diagnosis" && hasDiagnosis && <DiagnosisTab guide={guide} />}
    </div>
  );
}

function ShotListTab({ guide }: { guide: Guide }) {
  if (guide.shot_list.length === 0) {
    return <EmptyNote>수집된 릴스가 없습니다. 키워드를 넓혀서 다시 시도해보세요.</EmptyNote>;
  }
  return (
    <div className="space-y-3">
      {guide.shot_list.map((shot) => (
        <div key={shot.order} className="rounded-xl border border-gray-200 bg-white p-4">
          <div className="flex items-center justify-between text-xs text-gray-400">
            <span>
              #{shot.order} · {shot.t_start_sec.toFixed(1)}s ~{" "}
              {(shot.t_start_sec + shot.duration_sec).toFixed(1)}s
            </span>
            <span>{shot.angle}</span>
          </div>
          <p className="mt-1 text-sm font-medium text-gray-800">{shot.subject}</p>
          {shot.on_screen_text && (
            <p className="mt-1 text-sm text-gray-500">자막: {shot.on_screen_text}</p>
          )}
          <p className="mt-2 text-sm text-gray-600">💡 {shot.note}</p>
        </div>
      ))}
    </div>
  );
}

function CaptionTab({ guide }: { guide: Guide }) {
  if (guide.caption_drafts.length === 0) {
    return <EmptyNote>추천할 자막 문구가 없습니다.</EmptyNote>;
  }
  return (
    <div className="space-y-3">
      {guide.caption_drafts.map((draft, i) => (
        <div
          key={i}
          className="flex items-start justify-between gap-3 rounded-xl border border-gray-200 bg-white p-4"
        >
          <div>
            <p className="text-xs text-gray-400">{draft.pattern}</p>
            <p className="mt-1 text-sm text-gray-800">{draft.text}</p>
          </div>
          <button
            type="button"
            onClick={() => navigator.clipboard.writeText(draft.text)}
            className="shrink-0 rounded-lg border border-gray-300 px-3 py-1 text-xs text-gray-600"
          >
            복사
          </button>
        </div>
      ))}
    </div>
  );
}

function AudioTab({ guide }: { guide: Guide }) {
  if (guide.audio.length === 0) {
    return <EmptyNote>추천할 음원 데이터가 없습니다.</EmptyNote>;
  }
  return (
    <div className="space-y-2">
      {guide.audio.map((a, i) => (
        <div
          key={i}
          className="flex items-center justify-between rounded-xl border border-gray-200 bg-white p-4 text-sm"
        >
          <span className="text-gray-800">{a.title}</span>
          <span className="text-gray-400">
            {a.total}개 중 {a.seen_count}개
          </span>
        </div>
      ))}
    </div>
  );
}

function DiagnosisTab({ guide }: { guide: Guide }) {
  return (
    <div className="space-y-3">
      {guide.diagnosis.map((card, i) => (
        <div key={i} className="rounded-xl border border-gray-200 bg-white p-4">
          <p className="text-sm font-medium text-gray-800">{card.metric}</p>
          <div className="mt-2 flex items-center gap-4 text-sm">
            <span className="text-gray-600">내 릴스: {card.mine}</span>
            <span className="text-gray-400">상위 평균: {card.benchmark}</span>
          </div>
          <p className="mt-2 text-sm text-gray-600">{card.gap_note}</p>
        </div>
      ))}
    </div>
  );
}
