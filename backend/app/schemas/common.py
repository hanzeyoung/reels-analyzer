from typing import Literal

Bucket = Literal["B1", "B2", "B3", "B4", "unknown"]
Track = Literal["breakout", "big_account", "control", "my_reel"]  # my_reel: P5, 풀 비교엔 안 씀

JobStatus = Literal["queued", "running", "done", "failed"]
JobStage = Literal[
    "collecting", "scoring", "preparing", "analyzing", "comparing", "diagnosing", "generating"
]

Movement = Literal["고정", "패닝", "줌", "따라가기", "핸드헬드"]
ShotPurpose = Literal["후킹", "정보", "전환", "마무리", "CTA"]
Difficulty = Literal["하", "중", "상"]
Confidence = Literal["충분", "제한적", "불충분"]
