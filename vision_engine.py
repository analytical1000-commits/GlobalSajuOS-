"""
vision_engine.py — GlobalSajuOS v13.0 Vision 분석 엔진

역할:
- 사용자가 업로드한 얼굴/손 이미지를 Gemini Vision API로 분석
- 관상(안면 12궁) / 수상(손금 4대선) 결과를 구조화된 JSON으로 반환
- Synergy_X ModuleResult 형식으로 변환하여 교차검증에 연결

등급: B (관찰 기반 — 수리 계산이 아닌 AI 관찰)
"""

import base64
import json
import logging
from enum import Enum
from typing import Optional

import google.generativeai as genai

logger = logging.getLogger("VisionEngine")


# ════════════════════════════════════════════════
# 1. 분석 유형 정의
# ════════════════════════════════════════════════

class VisionType(Enum):
    FACE  = "관상"   # 얼굴 이미지
    HAND  = "수상"   # 손 이미지
    AUTO  = "자동"   # 자동 감지


# ════════════════════════════════════════════════
# 2. 관상 분석 프롬프트
# ════════════════════════════════════════════════

FACE_PROMPT = """
당신은 동양 관상학(觀相學) 전문가입니다.
업로드된 얼굴 이미지를 안면 12궁 기준으로 분석하고
아래 JSON 형식으로만 답하세요. 다른 텍스트는 출력하지 마세요.

분석 기준:
- 명궁(命宮): 인당(미간) — 의지력, 운명의 중심
- 재백궁(財帛宮): 코 — 재물 저장 능력
- 관록궁(官祿宮): 이마 — 사회적 성취
- 처첩궁(妻妾宮): 눈꼬리 — 배우자운
- 자녀궁(子女宮): 눈 아래 — 자녀운
- 노복궁(奴僕宮): 턱 — 말년운, 부하운
- 질액궁(疾厄宮): 눈썹 사이 — 건강
- 천이궁(遷移宮): 이마 양쪽 — 이동운
- 복덕궁(福德宮): 이마 중상 — 복록
- 부모궁(父母宮): 이마 양끝 — 부모운

반드시 아래 JSON 형식으로만 출력:
{
  "분석가능": true/false,
  "전반인상": "한 줄 요약",
  "재물복": {"상태": "강/중/약", "근거": "코 형태 설명"},
  "사회운": {"상태": "강/중/약", "근거": "이마 형태 설명"},
  "건강신호": {"상태": "양호/주의/경고", "근거": "설명"},
  "배우자운": {"상태": "강/중/약", "근거": "눈꼬리 설명"},
  "말년운": {"상태": "강/중/약", "근거": "턱 형태 설명"},
  "개운포인트": "인상 개선을 위한 실천 제안",
  "종합방향": "길/흉/중립",
  "신뢰도": 0.0~1.0
}
"""

# ════════════════════════════════════════════════
# 3. 수상 분석 프롬프트
# ════════════════════════════════════════════════

HAND_PROMPT = """
당신은 동양 수상학(手相學) 전문가입니다.
업로드된 손 이미지를 4대 주요선 기준으로 분석하고
아래 JSON 형식으로만 답하세요. 다른 텍스트는 출력하지 마세요.

분석 기준:
- 생명선(生命線): 엄지 아래 곡선 — 생명력, 건강, 활동력
- 두뇌선(頭腦線): 검지 아래 가로선 — 지적 능력, 사고 유형
- 감정선(感情線): 새끼손가락 아래 가로선 — 감정 표현, 연애 스타일
- 운명선(運命線): 손바닥 중앙 세로선 — 직업운, 사회적 성취 타이밍

반드시 아래 JSON 형식으로만 출력:
{
  "분석가능": true/false,
  "전반인상": "한 줄 요약",
  "생명선": {
    "상태": "강/보통/약",
    "특징": "끊김/섬(島紋)/분기 등",
    "해석": "건강과 생명력 해석"
  },
  "두뇌선": {
    "상태": "강/보통/약",
    "유형": "논리형/직관형/균형형",
    "해석": "사고 유형 해석"
  },
  "감정선": {
    "상태": "강/보통/약",
    "연애유형": "열정형/우정형/균형형",
    "해석": "감정 표현 해석"
  },
  "운명선": {
    "존재": true/false,
    "시작점": "손목/생명선/두뇌선 등",
    "해석": "직업운 타이밍 해석"
  },
  "재물복": {"상태": "강/중/약", "근거": "설명"},
  "개운포인트": "손 관리나 생활 습관 제안",
  "종합방향": "길/흉/중립",
  "신뢰도": 0.0~1.0
}
"""


# ════════════════════════════════════════════════
# 4. Vision 분석 엔진
# ════════════════════════════════════════════════

class VisionEngine:
    """
    GlobalSajuOS v13.0 Vision 분석 엔진

    사용법:
        engine = VisionEngine()

        # 파일 경로로 분석
        result = await engine.analyze_file("face.jpg", VisionType.FACE)

        # base64 데이터로 분석
        result = await engine.analyze_base64(b64_data, "image/jpeg", VisionType.HAND)
    """

    VERSION = "1.0.0"
    GRADE   = "B"

    def __init__(self):
        self.model = genai.GenerativeModel("gemini-2.0-flash")
        logger.info("✅ VisionEngine 초기화 완료")

    def _load_image_bytes(self, file_path: str) -> bytes:
        with open(file_path, "rb") as f:
            return f.read()

    def _detect_mime(self, file_path: str) -> str:
        ext = file_path.lower().split(".")[-1]
        return {
            "jpg":  "image/jpeg",
            "jpeg": "image/jpeg",
            "png":  "image/png",
            "webp": "image/webp",
            "gif":  "image/gif",
        }.get(ext, "image/jpeg")

    async def analyze_file(
        self,
        file_path: str,
        vision_type: VisionType = VisionType.AUTO
    ) -> dict:
        """파일 경로로 이미지 분석"""
        try:
            img_bytes = self._load_image_bytes(file_path)
            mime_type = self._detect_mime(file_path)
            return await self._analyze(img_bytes, mime_type, vision_type)
        except FileNotFoundError:
            return self._error_result(f"파일을 찾을 수 없습니다: {file_path}")
        except Exception as e:
            return self._error_result(str(e))

    async def analyze_base64(
        self,
        b64_data: str,
        mime_type: str = "image/jpeg",
        vision_type: VisionType = VisionType.AUTO
    ) -> dict:
        """base64 인코딩된 이미지 분석"""
        try:
            img_bytes = base64.b64decode(b64_data)
            return await self._analyze(img_bytes, mime_type, vision_type)
        except Exception as e:
            return self._error_result(str(e))

    async def analyze_bytes(
        self,
        img_bytes: bytes,
        mime_type: str = "image/jpeg",
        vision_type: VisionType = VisionType.AUTO
    ) -> dict:
        """바이트 데이터로 이미지 분석"""
        return await self._analyze(img_bytes, mime_type, vision_type)

    async def _analyze(
        self,
        img_bytes: bytes,
        mime_type: str,
        vision_type: VisionType
    ) -> dict:
        """실제 Gemini Vision API 호출"""

        # 프롬프트 선택
        if vision_type == VisionType.FACE:
            prompt = FACE_PROMPT
            module_name = "관상"
        elif vision_type == VisionType.HAND:
            prompt = HAND_PROMPT
            module_name = "수상"
        else:
            # 자동 감지: 두 프롬프트 모두 시도 후 더 나은 것 선택
            face_result = await self._call_vision(img_bytes, mime_type, FACE_PROMPT)
            hand_result = await self._call_vision(img_bytes, mime_type, HAND_PROMPT)

            # 신뢰도 비교
            face_conf = face_result.get("신뢰도", 0) if face_result.get("분석가능") else 0
            hand_conf = hand_result.get("신뢰도", 0) if hand_result.get("분석가능") else 0

            if face_conf >= hand_conf:
                return self._wrap_result(face_result, "관상", VisionType.FACE)
            else:
                return self._wrap_result(hand_result, "수상", VisionType.HAND)

        raw = await self._call_vision(img_bytes, mime_type, prompt)
        return self._wrap_result(raw, module_name, vision_type)

    async def _call_vision(
        self,
        img_bytes: bytes,
        mime_type: str,
        prompt: str
    ) -> dict:
        """Gemini Vision API 실제 호출"""
        try:
            import google.generativeai as genai

            image_part = {
                "inline_data": {
                    "mime_type": mime_type,
                    "data": base64.b64encode(img_bytes).decode("utf-8")
                }
            }

            response = await self.model.generate_content_async(
                [prompt, image_part]
            )

            text = response.text.strip()

            # JSON 파싱
            # 코드블록 제거
            if "```json" in text:
                text = text.split("```json")[1].split("```")[0].strip()
            elif "```" in text:
                text = text.split("```")[1].split("```")[0].strip()

            return json.loads(text)

        except json.JSONDecodeError as e:
            logger.warning(f"JSON 파싱 실패: {e}")
            return {"분석가능": False, "오류": "응답 파싱 실패"}
        except Exception as e:
            logger.error(f"Vision API 오류: {e}")
            return {"분석가능": False, "오류": str(e)}

    def _wrap_result(self, raw: dict, module_name: str, vtype: VisionType) -> dict:
        """분석 결과를 표준 형식으로 래핑"""
        if not raw.get("분석가능", False):
            return {
                "success":     False,
                "module":      module_name,
                "type":        vtype.value,
                "error":       raw.get("오류", "이미지 분석 불가"),
                "grade":       self.GRADE,
                "synergy_input": None,
            }

        # Synergy_X 연결용 ModuleResult 파라미터 추출
        direction  = raw.get("종합방향", "중립")
        confidence = float(raw.get("신뢰도", 0.5))
        verdict    = raw.get("전반인상", "분석 완료")

        # remedy 추출 (흉이면 개운포인트)
        remedy = raw.get("개운포인트") if direction == "흉" else None

        return {
            "success":    True,
            "module":     module_name,
            "type":       vtype.value,
            "grade":      self.GRADE,
            "raw":        raw,
            "synergy_input": {
                "module_name": module_name,
                "topic":       f"{module_name}분석",
                "verdict":     verdict,
                "direction":   direction,
                "confidence":  confidence,
                "detail":      json.dumps(raw, ensure_ascii=False),
                "remedy":      remedy,
            }
        }

    def _error_result(self, error_msg: str) -> dict:
        return {
            "success": False,
            "module":  "vision",
            "type":    "error",
            "error":   error_msg,
            "grade":   self.GRADE,
            "synergy_input": None,
        }

    def to_module_result(self, vision_result: dict):
        """
        VisionEngine 결과 → Synergy_X ModuleResult 변환
        main.py의 run_synergy에서 사용
        """
        from synergy_x import ModuleResult

        si = vision_result.get("synergy_input")
        if not si or not vision_result.get("success"):
            return None

        return ModuleResult(
            module_name=si["module_name"],
            topic=si["topic"],
            verdict=si["verdict"],
            direction=si["direction"],
            confidence=si["confidence"],
            detail=si["detail"],
            remedy=si.get("remedy"),
        )


# ════════════════════════════════════════════════
# 5. FastAPI 라우터 (main.py에서 include)
# ════════════════════════════════════════════════

from fastapi import APIRouter, UploadFile, File, Form
from fastapi.responses import JSONResponse

vision_router = APIRouter(prefix="/api/vision", tags=["Vision"])
_vision_engine = VisionEngine()


@vision_router.post("/face")
async def analyze_face(
    image: UploadFile = File(..., description="얼굴 이미지 (jpg/png)"),
):
    """
    관상 분석 엔드포인트
    얼굴 이미지 업로드 → 안면 12궁 분석
    """
    if not image.content_type.startswith("image/"):
        return JSONResponse(status_code=400, content={"error": "이미지 파일만 업로드 가능합니다"})

    img_bytes = await image.read()
    result = await _vision_engine.analyze_bytes(img_bytes, image.content_type, VisionType.FACE)
    return result


@vision_router.post("/hand")
async def analyze_hand(
    image: UploadFile = File(..., description="손 이미지 (jpg/png)"),
):
    """
    수상 분석 엔드포인트
    손 이미지 업로드 → 손금 4대선 분석
    """
    if not image.content_type.startswith("image/"):
        return JSONResponse(status_code=400, content={"error": "이미지 파일만 업로드 가능합니다"})

    img_bytes = await image.read()
    result = await _vision_engine.analyze_bytes(img_bytes, image.content_type, VisionType.HAND)
    return result


@vision_router.post("/auto")
async def analyze_auto(
    image: UploadFile = File(..., description="얼굴 또는 손 이미지"),
):
    """
    자동 감지 분석 — 관상/수상 자동 판별
    """
    if not image.content_type.startswith("image/"):
        return JSONResponse(status_code=400, content={"error": "이미지 파일만 업로드 가능합니다"})

    img_bytes = await image.read()
    result = await _vision_engine.analyze_bytes(img_bytes, image.content_type, VisionType.AUTO)
    return result


@vision_router.get("/health")
async def vision_health():
    return {
        "status":  "ok",
        "module":  "VisionEngine",
        "version": VisionEngine.VERSION,
        "grade":   VisionEngine.GRADE,
        "endpoints": ["/api/vision/face", "/api/vision/hand", "/api/vision/auto"],
    }
