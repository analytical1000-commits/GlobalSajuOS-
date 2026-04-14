"""
synergy_x.py — GlobalSajuOS v13.0 Synergy_X 교차검증 엔진

역할:
- 여러 모듈(명리·주역·사상체질·풍수 등)의 결과를 신뢰도 등급에 따라 통합
- 충돌 감지 및 조정
- 최종 통합 판정 JSON 반환

신뢰도 등급:
  S (0.60): 명리/사주, 주역, 토정비결, 성명학, 택일 — 수리 계산 기반
  A (0.25): 사상체질, 일반심리, 연애심리 — 판별 기반
  B (0.10): 관상, 수상, 풍수 — 관찰 기반
  C (0.05): 꿈해몽, 전생, 무속, 재물운 — 서사 기반
"""

from typing import Optional
from enum import Enum


# ════════════════════════════════════════════════
# 1. 등급 및 가중치 정의
# ════════════════════════════════════════════════

class Grade(Enum):
    S = "S"
    A = "A"
    B = "B"
    C = "C"

GRADE_WEIGHT = {
    Grade.S: 0.60,
    Grade.A: 0.25,
    Grade.B: 0.10,
    Grade.C: 0.05,
}

MODULE_GRADE = {
    # S등급 — 수리 계산
    "명리":     Grade.S,
    "사주":     Grade.S,
    "주역":     Grade.S,
    "토정비결": Grade.S,
    "성명학":   Grade.S,
    "택일":     Grade.S,
    # A등급 — 판별
    "사상체질": Grade.A,
    "일반심리": Grade.A,
    "연애심리": Grade.A,
    # B등급 — 관찰
    "관상":     Grade.B,
    "수상":     Grade.B,
    "풍수":     Grade.B,
    # C등급 — 서사
    "꿈해몽":   Grade.C,
    "전생":     Grade.C,
    "무속":     Grade.C,
    "재물운":   Grade.C,
}

# 충돌 유형
class ConflictType(Enum):
    DIRECT    = "직접충돌"   # 같은 영역에서 반대 결과
    DOMAIN    = "영역충돌"   # 다른 영역이지만 상충
    INTENSITY = "강도충돌"   # 방향은 같으나 강도 차이
    TEMPORAL  = "시간축충돌" # 시기 예측이 다름


# ════════════════════════════════════════════════
# 2. 모듈 결과 데이터 클래스
# ════════════════════════════════════════════════

class ModuleResult:
    """단일 모듈의 분석 결과"""

    def __init__(
        self,
        module_name: str,
        topic: str,
        verdict: str,
        direction: str,      # "길"(吉) / "흉"(凶) / "중립"
        confidence: float,   # 0.0 ~ 1.0
        detail: str,
        remedy: Optional[str] = None,
        timing: Optional[str] = None,
    ):
        self.module_name = module_name
        self.topic       = topic
        self.verdict     = verdict
        self.direction   = direction
        self.confidence  = max(0.0, min(1.0, confidence))
        self.detail      = detail
        self.remedy      = remedy
        self.timing      = timing
        self.grade       = MODULE_GRADE.get(module_name, Grade.C)
        self.weight      = GRADE_WEIGHT[self.grade]

    def weighted_score(self) -> float:
        """방향을 반영한 가중치 점수"""
        dir_sign = 1.0 if self.direction == "길" else (-1.0 if self.direction == "흉" else 0.0)
        return self.weight * self.confidence * dir_sign

    def to_dict(self) -> dict:
        return {
            "모듈":    self.module_name,
            "등급":    self.grade.value,
            "주제":    self.topic,
            "판정":    self.verdict,
            "방향":    self.direction,
            "신뢰도":  round(self.confidence, 2),
            "가중치":  self.weight,
            "상세":    self.detail,
            "remedy":  self.remedy,
            "시기":    self.timing,
        }


# ════════════════════════════════════════════════
# 3. 충돌 감지
# ════════════════════════════════════════════════

class ConflictDetector:
    """모듈 간 충돌 감지 및 분류"""

    def detect(self, results: list[ModuleResult]) -> list[dict]:
        conflicts = []

        for i in range(len(results)):
            for j in range(i + 1, len(results)):
                a = results[i]
                b = results[j]

                conflict = self._check_conflict(a, b)
                if conflict:
                    conflicts.append(conflict)

        return conflicts

    def _check_conflict(self, a: ModuleResult, b: ModuleResult) -> Optional[dict]:
        """두 모듈 간 충돌 확인"""

        # 같은 주제인지 확인
        same_topic = (a.topic == b.topic) or self._topic_overlap(a.topic, b.topic)

        if not same_topic:
            return None

        # 방향 비교
        if a.direction != "중립" and b.direction != "중립":
            if a.direction != b.direction:
                # 직접 충돌
                return {
                    "유형":     ConflictType.DIRECT.value,
                    "모듈A":    a.module_name,
                    "등급A":    a.grade.value,
                    "판정A":    a.verdict,
                    "모듈B":    b.module_name,
                    "등급B":    b.grade.value,
                    "판정B":    b.verdict,
                    "주제":     a.topic,
                    "우선순위": a.module_name if a.grade.value <= b.grade.value else b.module_name,
                    "해결방식": f"{a.grade.value}등급 {a.module_name} 우선 적용"
                              if a.grade.value <= b.grade.value
                              else f"{b.grade.value}등급 {b.module_name} 우선 적용",
                }

            # 강도 충돌 (같은 방향이지만 confidence 차이 큼)
            if abs(a.confidence - b.confidence) > 0.4:
                return {
                    "유형":     ConflictType.INTENSITY.value,
                    "모듈A":    a.module_name,
                    "신뢰도A":  a.confidence,
                    "모듈B":    b.module_name,
                    "신뢰도B":  b.confidence,
                    "주제":     a.topic,
                    "우선순위": a.module_name if a.confidence >= b.confidence else b.module_name,
                    "해결방식": "높은 신뢰도 모듈 우선 적용",
                }

        # 시기 충돌
        if a.timing and b.timing and a.timing != b.timing:
            return {
                "유형":     ConflictType.TEMPORAL.value,
                "모듈A":    a.module_name,
                "시기A":    a.timing,
                "모듈B":    b.module_name,
                "시기B":    b.timing,
                "주제":     a.topic,
                "해결방식": f"{a.grade.value}등급 {a.module_name}의 시기 우선 적용",
            }

        return None

    def _topic_overlap(self, topic_a: str, topic_b: str) -> bool:
        """주제 유사도 검사"""
        keywords_a = set(topic_a.replace("·", " ").replace("/", " ").split())
        keywords_b = set(topic_b.replace("·", " ").replace("/", " ").split())
        return bool(keywords_a & keywords_b)


# ════════════════════════════════════════════════
# 4. 통합 판정
# ════════════════════════════════════════════════

class SynergyFusion:
    """모듈 결과 통합 및 최종 판정"""

    def __init__(self):
        self.detector = ConflictDetector()

    def fuse(self, results: list[ModuleResult], topic: str) -> dict:
        """
        여러 모듈 결과를 통합하여 최종 판정 반환

        topic: 분석 주제 (예: "재물운", "연애운", "건강")
        """
        if not results:
            return self._empty_result(topic)

        # 관련 결과만 필터링
        relevant = [r for r in results if r.topic == topic or topic in r.topic]
        if not relevant:
            relevant = results

        # 충돌 감지
        conflicts = self.detector.detect(relevant)

        # 가중치 점수 계산
        total_weight = sum(r.weight for r in relevant)
        weighted_score = sum(r.weighted_score() for r in relevant)
        normalized_score = weighted_score / total_weight if total_weight > 0 else 0

        # 최종 방향 결정
        if normalized_score > 0.15:
            final_direction = "길"
        elif normalized_score < -0.15:
            final_direction = "흉"
        else:
            final_direction = "중립"

        # 신뢰도 계산 (등급 가중 평균)
        confidence = sum(r.weight * r.confidence for r in relevant) / total_weight

        # S등급 모듈 결과 우선 표기
        s_grade_results = [r for r in relevant if r.grade == Grade.S]
        a_grade_results = [r for r in relevant if r.grade == Grade.A]

        # 통합 판정문 생성
        verdict_text = self._build_verdict(relevant, conflicts, final_direction, topic)

        # remedy 수집 (흉 결과에서)
        remedies = [r.remedy for r in relevant if r.remedy and r.direction == "흉"]

        return {
            "주제":        topic,
            "최종방향":    final_direction,
            "통합점수":    round(normalized_score, 3),
            "신뢰도":      round(confidence, 2),
            "판정문":      verdict_text,
            "S등급판정":   [r.to_dict() for r in s_grade_results],
            "A등급판정":   [r.to_dict() for r in a_grade_results],
            "전체판정":    [r.to_dict() for r in relevant],
            "충돌목록":    conflicts,
            "충돌수":      len(conflicts),
            "remedy목록":  remedies,
            "분석모듈수":  len(relevant),
        }

    def _build_verdict(
        self,
        results: list[ModuleResult],
        conflicts: list[dict],
        direction: str,
        topic: str
    ) -> str:
        """통합 판정문 생성"""

        lines = []

        # S등급 결과 우선
        s_results = [r for r in results if r.grade == Grade.S]
        if s_results:
            main = s_results[0]
            lines.append(f"[{main.module_name} 기준] {main.verdict}")

        # 충돌이 있으면 언급
        if conflicts:
            for c in conflicts[:2]:  # 최대 2개만
                if c["유형"] == ConflictType.DIRECT.value:
                    lines.append(
                        f"※ {c['모듈A']}({c['등급A']})과 {c['모듈B']}({c['등급B']})의 판정이 "
                        f"다릅니다. {c['해결방식']}합니다."
                    )

        # 다른 등급 결과 보조
        other = [r for r in results if r.grade != Grade.S and r.direction != "중립"]
        if other:
            lines.append(
                ", ".join([f"{r.module_name}: {r.verdict}" for r in other[:2]])
            )

        # 방향 요약
        direction_text = {
            "길":  f"종합적으로 {topic}에 긍정적인 기운이 감지됩니다.",
            "흉":  f"종합적으로 {topic}에 주의가 필요합니다.",
            "중립": f"{topic}에 대해 복합적인 기운이 작용하고 있습니다.",
        }
        lines.append(direction_text.get(direction, ""))

        return " / ".join(filter(None, lines))

    def _empty_result(self, topic: str) -> dict:
        return {
            "주제":       topic,
            "최종방향":   "중립",
            "통합점수":   0.0,
            "신뢰도":     0.0,
            "판정문":     "분석 데이터가 없습니다.",
            "S등급판정":  [],
            "A등급판정":  [],
            "전체판정":   [],
            "충돌목록":   [],
            "충돌수":     0,
            "remedy목록": [],
            "분석모듈수": 0,
        }


# ════════════════════════════════════════════════
# 5. Synergy_X 메인 클래스
# ════════════════════════════════════════════════

class SynergyX:
    """
    GlobalSajuOS v13.0 Synergy_X 교차검증 엔진

    사용법:
        sx = SynergyX()
        results = [
            ModuleResult("명리", "재물운", "재성 강함, 올해 재물 상승", "길", 0.8, "상세내용"),
            ModuleResult("주역", "재물운", "수뢰둔 - 초기 어려움 후 발전", "중립", 0.6, "상세"),
            ModuleResult("사상체질", "건강", "태음인 소화 주의", "흉", 0.7, "상세", remedy="소화 관리"),
        ]
        report = sx.analyze(results, topics=["재물운", "건강"])
    """

    VERSION = "1.0.0"

    def __init__(self):
        self.fusion = SynergyFusion()

    def analyze(
        self,
        results: list[ModuleResult],
        topics: Optional[list[str]] = None
    ) -> dict:
        """
        전체 모듈 결과 교차 분석

        results: ModuleResult 목록
        topics: 분석할 주제 목록 (None이면 자동 추출)
        """
        if not topics:
            topics = list(set(r.topic for r in results))

        # 주제별 통합 판정
        topic_reports = {}
        for topic in topics:
            topic_reports[topic] = self.fusion.fuse(results, topic)

        # 전체 충돌 감지
        all_conflicts = ConflictDetector().detect(results)

        # 전체 신뢰도 점수
        if results:
            total_w = sum(r.weight for r in results)
            overall_confidence = sum(r.weight * r.confidence for r in results) / total_w
        else:
            overall_confidence = 0.0

        # 모듈별 요약
        module_summary = {}
        for r in results:
            module_summary[r.module_name] = {
                "등급":    r.grade.value,
                "가중치":  r.weight,
                "방향":    r.direction,
                "신뢰도":  r.confidence,
            }

        # remedy 우선순위 정렬 (S등급 remedy 먼저)
        all_remedies = []
        for r in sorted(results, key=lambda x: x.grade.value):
            if r.remedy and r.direction == "흉":
                all_remedies.append({
                    "모듈":   r.module_name,
                    "등급":   r.grade.value,
                    "주제":   r.topic,
                    "remedy": r.remedy,
                })

        return {
            "version":          self.VERSION,
            "분석모듈수":       len(results),
            "주제별판정":       topic_reports,
            "전체충돌":         all_conflicts,
            "전체충돌수":       len(all_conflicts),
            "전체신뢰도":       round(overall_confidence, 2),
            "모듈요약":         module_summary,
            "remedy우선순위":   all_remedies,
            "판정원칙": {
                "S등급가중치":  GRADE_WEIGHT[Grade.S],
                "A등급가중치":  GRADE_WEIGHT[Grade.A],
                "B등급가중치":  GRADE_WEIGHT[Grade.B],
                "C등급가중치":  GRADE_WEIGHT[Grade.C],
                "충돌해결":     "높은 등급 모듈 우선",
                "흉살처리":     "remedy 반드시 포함",
            }
        }


# ════════════════════════════════════════════════
# 6. 단독 실행 테스트
# ════════════════════════════════════════════════

if __name__ == "__main__":
    import json

    sx = SynergyX()

    # 테스트 데이터
    results = [
        ModuleResult(
            "명리", "재물운",
            "재성 편재 강함, 2026년 丙午 세운에서 재물 활동 왕성",
            "길", 0.85,
            "편재격 원국, 丙午 세운 재성 활발",
            timing="2026년 상반기"
        ),
        ModuleResult(
            "주역", "재물운",
            "수뢰둔(水雷屯) — 초기 어려움이 있으나 뚫고 나가면 발전",
            "중립", 0.65,
            "어려움 속 전진의 괘",
            timing="2026년 하반기"
        ),
        ModuleResult(
            "사상체질", "건강",
            "태음인 소화기 약점 주의, 과식 삼가",
            "흉", 0.70,
            "태음인 체질적 소화 취약",
            remedy="소식(小食) 습관화, 발효 음식 권장"
        ),
        ModuleResult(
            "풍수", "재물운",
            "현관 방향이 재물궁(동남)과 충돌",
            "흉", 0.55,
            "현관 서향, 재물궁 동남 충돌",
            remedy="현관에 거울 제거, 조명 밝게"
        ),
        ModuleResult(
            "무속", "재물운",
            "삼재 기간 아님, 수호신 기운 양호",
            "길", 0.50,
            "삼재 비해당"
        ),
    ]

    report = sx.analyze(results, topics=["재물운", "건강"])
    print(json.dumps(report, ensure_ascii=False, indent=2))
