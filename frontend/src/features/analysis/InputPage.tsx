import { useMutation } from "@tanstack/react-query";
import { useState } from "react";
import { useNavigate } from "react-router-dom";

import { ApiError, createAnalysis } from "../../api/client";

const EQUIPMENT_OPTIONS = ["스마트폰", "삼각대", "짐벌", "조명", "마이크"];

export function InputPage() {
  const navigate = useNavigate();

  const [keyword, setKeyword] = useState("");
  const [businessType, setBusinessType] = useState("");
  const [shootingAlone, setShootingAlone] = useState(true);
  const [equipment, setEquipment] = useState<string[]>(["스마트폰"]);
  const [space, setSpace] = useState<"좁음" | "보통" | "넓음">("보통");
  const [canShowFace, setCanShowFace] = useState(false);
  const [weeklyMinutes, setWeeklyMinutes] = useState(60);
  const [myReelUrl, setMyReelUrl] = useState("");

  const mutation = useMutation({
    mutationFn: createAnalysis,
    onSuccess: (res) => navigate(`/jobs/${res.job_id}`),
  });

  const toggleEquipment = (item: string) => {
    setEquipment((prev) =>
      prev.includes(item) ? prev.filter((e) => e !== item) : [...prev, item],
    );
  };

  const canSubmit = keyword.trim() !== "" && businessType.trim() !== "" && !mutation.isPending;

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!canSubmit) return;
    mutation.mutate({
      keyword: keyword.trim(),
      business_type: businessType.trim(),
      constraints: {
        shooting_alone: shootingAlone,
        equipment,
        space,
        can_show_face: canShowFace,
        weekly_minutes: weeklyMinutes,
      },
      my_reel_url: myReelUrl.trim() || null,
    });
  };

  return (
    <div className="mx-auto max-w-md p-6">
      <h1 className="text-xl font-semibold">부자 — 릴스 촬영 지시서</h1>
      <p className="mt-1 text-sm text-gray-500">
        키워드로 잘 나가는 릴스를 찾아 촬영 지시서를 만들어줘요.
      </p>

      <form onSubmit={handleSubmit} className="mt-6 space-y-5">
        <div>
          <label className="block text-sm font-medium text-gray-700">검색 키워드</label>
          <input
            type="text"
            value={keyword}
            onChange={(e) => setKeyword(e.target.value)}
            placeholder="예: 성수동카페"
            className="mt-1 w-full rounded-lg border border-gray-300 px-3 py-2 text-sm"
          />
        </div>

        <div>
          <label className="block text-sm font-medium text-gray-700">업종</label>
          <input
            type="text"
            value={businessType}
            onChange={(e) => setBusinessType(e.target.value)}
            placeholder="예: 카페"
            className="mt-1 w-full rounded-lg border border-gray-300 px-3 py-2 text-sm"
          />
        </div>

        <fieldset>
          <legend className="text-sm font-medium text-gray-700">촬영 조건</legend>
          <div className="mt-2 space-y-2">
            <label className="flex items-center gap-2 text-sm text-gray-600">
              <input
                type="checkbox"
                checked={shootingAlone}
                onChange={(e) => setShootingAlone(e.target.checked)}
              />
              혼자 촬영해요
            </label>
            <label className="flex items-center gap-2 text-sm text-gray-600">
              <input
                type="checkbox"
                checked={canShowFace}
                onChange={(e) => setCanShowFace(e.target.checked)}
              />
              얼굴 노출 가능해요
            </label>
          </div>
        </fieldset>

        <fieldset>
          <legend className="text-sm font-medium text-gray-700">보유 장비</legend>
          <div className="mt-2 flex flex-wrap gap-2">
            {EQUIPMENT_OPTIONS.map((item) => (
              <label
                key={item}
                className={`cursor-pointer rounded-full border px-3 py-1 text-sm ${
                  equipment.includes(item)
                    ? "border-black bg-black text-white"
                    : "border-gray-300 text-gray-600"
                }`}
              >
                <input
                  type="checkbox"
                  className="hidden"
                  checked={equipment.includes(item)}
                  onChange={() => toggleEquipment(item)}
                />
                {item}
              </label>
            ))}
          </div>
        </fieldset>

        <div>
          <label className="block text-sm font-medium text-gray-700">촬영 공간</label>
          <select
            value={space}
            onChange={(e) => setSpace(e.target.value as "좁음" | "보통" | "넓음")}
            className="mt-1 w-full rounded-lg border border-gray-300 px-3 py-2 text-sm"
          >
            <option value="좁음">좁음</option>
            <option value="보통">보통</option>
            <option value="넓음">넓음</option>
          </select>
        </div>

        <div>
          <label className="block text-sm font-medium text-gray-700">
            주당 촬영 가능 시간 (분)
          </label>
          <input
            type="number"
            min={0}
            value={weeklyMinutes}
            onChange={(e) => setWeeklyMinutes(Number(e.target.value))}
            className="mt-1 w-full rounded-lg border border-gray-300 px-3 py-2 text-sm"
          />
        </div>

        <div>
          <label className="block text-sm font-medium text-gray-700">
            내 릴스 URL <span className="text-gray-400">(선택 — 있으면 진단 카드가 나와요)</span>
          </label>
          <input
            type="url"
            value={myReelUrl}
            onChange={(e) => setMyReelUrl(e.target.value)}
            placeholder="https://www.instagram.com/reel/..."
            className="mt-1 w-full rounded-lg border border-gray-300 px-3 py-2 text-sm"
          />
        </div>

        {mutation.isError && (
          <p className="text-sm text-red-600">
            {mutation.error instanceof ApiError
              ? mutation.error.message
              : "요청 중 문제가 발생했습니다."}
          </p>
        )}

        <button
          type="submit"
          disabled={!canSubmit}
          className="w-full rounded-lg bg-black py-3 text-sm font-medium text-white disabled:opacity-40"
        >
          {mutation.isPending ? "시작하는 중..." : "분석 시작"}
        </button>
      </form>
    </div>
  );
}
