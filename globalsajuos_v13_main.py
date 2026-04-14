"""
GlobalSajuOS v13.0 — FastAPI 백엔드 통합본
gsaju_kernel.py + synergy_x.py 완전 연결

파이프라인:
  BirthInfo 입력
    → gsaju_kernel.SajuCoreEngine.calculate_pillars()  [Tier 1 수리 계산]
    → 보조 모듈 병렬 실행 (주역·사상체질 등)          [Tier 2]
    → synergy_x.SynergyX.analyze()                     [교차검증·충돌조정]
    → Gemini 스트리밍 해석                              [Tier 3 언어 변환]

의존성:
  pip install fastapi uvicorn google-generativeai python-dotenv pydantic
"""

import os
import json
import time
import asyncio
import logging
from typing import AsyncGenerator, Optional

import google.generativeai as genai
from fastapi import FastAPI
from fastapi.responses import StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field, validator
from dotenv import load_dotenv

# ── 내부 엔진 임포트 ──
from gsaju_kernel import SajuCoreEngine, LOCATION_LONGITUDE
from synergy_x import SynergyX, ModuleResult
from vision_engine import VisionEngine, VisionType, vision_router

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("GlobalSajuOS")

# ════════════════════════════════════════════════
# 0. 환경 설정
# ════════════════════════════════════════════════

load_dotenv()
genai.configure(api_key=os.environ["GSAJU_AI_API_KEY"])

app = FastAPI(
    title="GlobalSajuOS v13.0",
    description="명리 AI 상담 엔진 — gsaju_kernel + synergy_x 통합",
    version="13.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "https://yourdomain.com"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Vision 라우터 등록
app.include_router(vision_router)

# 엔진 싱글턴 (서버 시작 시 1회 생성)
_saju_engine  = SajuCoreEngine()
_synergy_x    = SynergyX()
_vision_engine = VisionEngine()

logger.info("✅ gsaju_kernel.SajuCoreEngine 로드 완료")
logger.info("✅ synergy_x.SynergyX 로드 완료")
logger.info("✅ vision_engine.VisionEngine 로드 완료")


# ════════════════════════════════════════════════
# 1. Pydantic 모델
# ════════════════════════════════════════════════

class BirthInfo(BaseModel):
    year:     int  = Field(..., ge=1900, le=2100)
    month:    int  = Field(..., ge=1,    le=12)
    day:      int  = Field(..., ge=1,    le=31)
    hour:     int  = Field(..., ge=0,    le=23)
    minute:   int  = Field(0,   ge=0,   le=59)
    gender:   str  = Field("M")          # "M" / "F"
    location: str  = Field("서울")
    is_lunar: bool = Field(False)

    @validator("gender")
    def validate_gender(cls, v):
        if v not in ("M", "F"):
            raise ValueError("gender는 'M' 또는 'F' 이어야 합니다")
        return v


class SajuRequest(BaseModel):
    birth:           BirthInfo
    user_query:      str       = Field(..., min_length=1, max_length=500)
    active_modules:  list[str] = Field(default=["명리"])
    conversation_id: Optional[str] = None

    @validator("active_modules")
    def validate_modules(cls, v):
        allowed = {
            "명리", "주역", "토정비결", "성명학", "택일",
            "사상체질", "관상", "수상", "풍수", "재물운",
            "꿈해몽", "전생", "무속", "일반심리", "연애심리",
        }
        invalid = set(v) - allowed
        if invalid:
            raise ValueError(f"유효하지 않은 모듈: {invalid}")
        if "독립심리" in v and len(v) > 1:
            raise ValueError("독립심리상담은 단독 실행만 가능합니다")
        return v


# ════════════════════════════════════════════════
# 2. Gemini 모델 설정
# ════════════════════════════════════════════════

gemini_model = genai.GenerativeModel(
    model_name="gemini-2.0-flash",
    generation_config=genai.types.GenerationConfig(
        max_output_tokens=800,
        temperature=0.7,
        top_p=0.9,
    )
)

SYSTEM_PROMPT = """
너는 GlobalSajuOS v13.0의 언어 해석 엔진이다.

역할:
- gsaju_kernel이 수리 계산한 JSON과 Synergy_X 교차검증 결과를
  공감적이고 명확한 한국어로 변환한다.

절대 규칙:
1. engine_json의 수치와 간지를 절대 수정하거나 임의로 생성하지 않는다
2. shinsal(신살)·흉살 언급 시 반드시 remedy를 먼저 제시한다
3. synergy_결과의 충돌이 있으면 "S등급 기준" 표현을 사용한다
4. 투자·의료 결정 근거로 사용 불가 톤 유지
5. 응답은 3문단 이내, 모바일 최적화
6. 금지: "대주님", "짤랑짤랑", "완벽", "무결", "제국"

활성 모듈: {modules}

[사주 원국 — gsaju_kernel 계산값]
{engine_json}

[Synergy_X 교차검증 결과]
{synergy_json}

사용자 질문: {user_query}
"""


# ════════════════════════════════════════════════
# 3. AutoOptimizer
# ════════════════════════════════════════════════

class AutoOptimizer:
    SLOW_THRESHOLD = 3.0

    def __init__(self):
        self.log: list[dict] = []
        self.lite_mode = False

    def record(self, elapsed: float, tokens: int):
        self.log.append({"elapsed": elapsed, "tokens": tokens, "ts": time.time()})
        if len(self.log) > 10:
            self.log = self.log[-10:]
        recent = [r["elapsed"] for r in self.log[-5:]]
        if len(recent) >= 3 and sum(recent) / len(recent) > self.SLOW_THRESHOLD:
            self.lite_mode = True
            logger.warning("⚡ AutoOptimizer: 라이트 모드 활성화")

    def trim_kernel(self, kernel_json: dict) -> dict:
        """라이트 모드 시 핵심 필드만 추출"""
        if not self.lite_mode:
            return kernel_json
        p = kernel_json.get("pillars", {})
        return {
            "four_pillars_string": kernel_json.get("four_pillars_string"),
            "pillars": p,
            "elements": kernel_json.get("elements"),
            "yongsin":  kernel_json.get("yongsin"),
            "gyeokguk": kernel_json.get("gyeokguk"),
            "current_daeun": kernel_json.get("current_daeun"),
        }

    def trim_synergy(self, synergy_json: dict) -> dict:
        """라이트 모드 시 synergy 요약만 추출"""
        if not self.lite_mode:
            return synergy_json
        return {
            "전체신뢰도":  synergy_json.get("전체신뢰도"),
            "전체충돌수":  synergy_json.get("전체충돌수"),
            "remedy우선순위": synergy_json.get("remedy우선순위", [])[:2],
            "주제별판정": {
                k: {"최종방향": v.get("최종방향"), "판정문": v.get("판정문")}
                for k, v in synergy_json.get("주제별판정", {}).items()
            }
        }

    def report(self) -> dict:
        if not self.log:
            return {"status": "no_data"}
        times = [r["elapsed"] for r in self.log]
        return {
            "avg_sec":    round(sum(times) / len(times), 2),
            "max_sec":    round(max(times), 2),
            "min_sec":    round(min(times), 2),
            "lite_mode":  self.lite_mode,
            "total_calls": len(self.log),
        }


optimizer = AutoOptimizer()


# ════════════════════════════════════════════════
# 4. 대화 히스토리
# ════════════════════════════════════════════════

class ConversationStore:
    MAX_RECENT  = 3
    MAX_HISTORY = 5

    def __init__(self):
        self._store: dict[str, list] = {}

    def add(self, conv_id: str, user: str, assistant: str):
        if conv_id not in self._store:
            self._store[conv_id] = []
        self._store[conv_id].append({
            "user": user[:80],
            "assistant": assistant[:150]
        })
        if len(self._store[conv_id]) > self.MAX_HISTORY:
            self._store[conv_id] = self._store[conv_id][-self.MAX_RECENT:]

    def get_context(self, conv_id: str) -> str:
        if not conv_id or conv_id not in self._store:
            return ""
        lines = ["[이전 대화 요약]"]
        for t in self._store[conv_id][-self.MAX_RECENT:]:
            lines.append(f"사용자: {t['user']}")
            lines.append(f"응답: {t['assistant']}...")
        return "\n".join(lines)


store = ConversationStore()


# ════════════════════════════════════════════════
# 5. 엔진 실행 함수
# ════════════════════════════════════════════════

async def run_kernel(birth: BirthInfo) -> dict:
    """
    Tier 1 — gsaju_kernel 비동기 래핑
    CPU 연산을 별도 스레드에서 실행 (이벤트 루프 블로킹 방지)
    """
    def _sync():
        birth_data = {
            "year":   birth.year,
            "month":  birth.month,
            "day":    birth.day,
            "hour":   birth.hour,
            "minute": birth.minute,
            "gender": birth.gender,
        }
        lon = LOCATION_LONGITUDE.get(birth.location, 126.9)
        location_data = {
            "name":      birth.location,
            "longitude": lon,
            "timezone":  9.0,
        }
        result = _saju_engine.calculate_pillars(birth_data, location_data)
        if not isinstance(result, dict):
            raise ValueError("커널 반환값 오류")
        return result

    try:
        result = await asyncio.to_thread(_sync)
        logger.info(f"✅ 커널 계산 완료: {result.get('four_pillars_string')}")
        return result
    except Exception as e:
        logger.error(f"❌ 커널 오류: {e}")
        raise RuntimeError(str(e))


async def run_synergy(kernel_result: dict, modules: list[str]) -> dict:
    """
    Synergy_X 교차검증
    kernel_result에서 ModuleResult 목록을 구성하여 분석
    """
    def _sync():
        results = []

        # ── 명리 결과 → ModuleResult 변환 ──
        pillars = kernel_result.get("pillars", {})
        yongsin = kernel_result.get("yongsin", {})
        shinsal = kernel_result.get("shinsal", [])
        gyeokguk = kernel_result.get("gyeokguk", "")
        elements = kernel_result.get("elements", {})
        cur_daeun = kernel_result.get("current_daeun", {})

        # 명리 전반 결과
        myungri_direction = "중립"
        myungri_confidence = 0.75
        myungri_verdict = f"{kernel_result.get('four_pillars_string', '')} / {gyeokguk}"

        # 신살이 있으면 흉 요소 포함
        if shinsal:
            myungri_direction = "흉" if len(shinsal) >= 2 else "중립"
            myungri_remedy = "신살 대처: 흉살의 기운을 약화시키는 개운법 적용 권장"
        else:
            myungri_remedy = None

        # 용신 기반 방향
        yongsin_els = yongsin.get("억부용신", [])
        if yongsin_els:
            myungri_direction = "길" if yongsin.get("신강신약") == "신약" else "중립"

        results.append(ModuleResult(
            module_name="명리",
            topic="원국분석",
            verdict=myungri_verdict,
            direction=myungri_direction,
            confidence=myungri_confidence,
            detail=f"격국: {gyeokguk} / 신강신약: {yongsin.get('신강신약', '미상')}",
            remedy=myungri_remedy,
            timing=cur_daeun.get("간지", "") + " 대운"
        ))

        # ── 대운 결과 ──
        daeun_list = kernel_result.get("daeun", [])
        if daeun_list and cur_daeun:
            results.append(ModuleResult(
                module_name="명리",
                topic="대운흐름",
                verdict=f"현재 {cur_daeun.get('간지')} 대운 ({cur_daeun.get('시작나이')}~{cur_daeun.get('종료나이')}세)",
                direction="중립",
                confidence=0.80,
                detail="10년 대운 주기 분석",
                timing=cur_daeun.get("간지")
            ))

        # ── 주역 모듈 요청 시 ──
        if "주역" in modules:
            results.append(ModuleResult(
                module_name="주역",
                topic="원국분석",
                verdict="주역 점단은 별도 요청 시 생성됩니다",
                direction="중립",
                confidence=0.60,
                detail="주역 독립 모듈"
            ))

        # ── 재물운 모듈 요청 시 ──
        if "재물운" in modules:
            재성_count = elements.get("金", 0) + elements.get("水", 0)
            재물_방향 = "길" if 재성_count >= 2 else "중립"
            results.append(ModuleResult(
                module_name="재물운",
                topic="재물운",
                verdict=f"재물 기운: {'활발' if 재물_방향=='길' else '보통'}",
                direction=재물_방향,
                confidence=0.55,
                detail="⚠️ 운세 참고용 — 실제 투자 결정 근거 불가"
            ))

        # ── 건강 모듈 요청 시 ──
        if "사상체질" in modules:
            results.append(ModuleResult(
                module_name="사상체질",
                topic="건강체질",
                verdict="체질 판별은 추가 문진이 필요합니다",
                direction="중립",
                confidence=0.50,
                detail="사상체질 4분류 판별"
            ))

        # 분석 주제 목록
        topics = list(set(r.topic for r in results))
        return _synergy_x.analyze(results, topics)

    try:
        result = await asyncio.to_thread(_sync)
        logger.info(f"✅ Synergy_X 분석 완료: 충돌 {result.get('전체충돌수', 0)}건")
        return result
    except Exception as e:
        logger.error(f"❌ Synergy_X 오류: {e}")
        # Synergy_X 실패 시 빈 결과 반환 (전체 중단 없음)
        return {"전체충돌수": 0, "전체신뢰도": 0, "주제별판정": {}, "remedy우선순위": []}


async def run_parallel_engines(birth: BirthInfo, modules: list[str]) -> dict:
    """
    전체 파이프라인 실행
    Tier 1 (커널) → Tier 2 (보조 모듈) → Synergy_X
    """
    # Tier 1: 커널 계산 (필수)
    kernel_result = await run_kernel(birth)

    # Tier 2 보조 모듈 + Synergy_X 병렬 실행
    synergy_result = await run_synergy(kernel_result, modules)

    return {
        "kernel":  kernel_result,
        "synergy": synergy_result,
        "modules": modules,
    }


# ════════════════════════════════════════════════
# 6. Gemini 스트리밍
# ════════════════════════════════════════════════

async def gemini_stream(
    engine_results: dict,
    user_query: str,
    modules: list[str],
    conv_id: Optional[str],
) -> AsyncGenerator[str, None]:

    start = time.time()

    kernel_json  = optimizer.trim_kernel(engine_results.get("kernel", {}))
    synergy_json = optimizer.trim_synergy(engine_results.get("synergy", {}))

    history_ctx = store.get_context(conv_id) if conv_id else ""

    prompt = SYSTEM_PROMPT.format(
        modules     = ", ".join(modules),
        engine_json = json.dumps(kernel_json,  ensure_ascii=False),
        synergy_json= json.dumps(synergy_json, ensure_ascii=False),
        user_query  = user_query,
    )
    if history_ctx:
        prompt = history_ctx + "\n\n" + prompt

    try:
        response = await gemini_model.generate_content_async(prompt, stream=True)
        full_text = ""
        async for chunk in response:
            if chunk.text:
                full_text += chunk.text
                yield f"data: {chunk.text}\n\n"

        if conv_id:
            store.add(conv_id, user_query, full_text)

        elapsed = time.time() - start
        optimizer.record(elapsed, len(full_text) // 4)
        logger.info(f"✅ Gemini 스트리밍 완료: {elapsed:.2f}초")
        yield "data: [DONE]\n\n"

    except Exception as e:
        logger.error(f"❌ Gemini 오류: {e}")
        yield "data: [ERROR] 해석 엔진 오류가 발생했습니다.\n\n"
        yield "data: [DONE]\n\n"


async def _fallback_stream(error_detail: str) -> AsyncGenerator[str, None]:
    """Circuit Breaker Fallback"""
    logger.error(f"[CIRCUIT_BREAKER] {error_detail}")
    msg = "잠시 기운의 흐름이 정체되고 있습니다. 생년월일시를 다시 확인하시고 잠시 후 다시 시도해 주세요."
    for char in msg:
        yield f"data: {char}\n\n"
        await asyncio.sleep(0.02)
    yield "data: [DONE]\n\n"


# ════════════════════════════════════════════════
# 7. API 엔드포인트
# ════════════════════════════════════════════════

@app.post("/api/saju/stream")
async def saju_stream(req: SajuRequest):
    """메인 엔드포인트 — 스트리밍 사주 상담"""
    try:
        engine_results = await run_parallel_engines(req.birth, req.active_modules)
    except RuntimeError as e:
        return StreamingResponse(
            _fallback_stream(str(e)),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache"}
        )
    return StreamingResponse(
        gemini_stream(engine_results, req.user_query, req.active_modules, req.conversation_id),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"}
    )


@app.post("/api/saju/sync")
async def saju_sync(req: SajuRequest):
    """동기 엔드포인트 — 전체 결과 한 번에 반환"""
    engine_results = await run_parallel_engines(req.birth, req.active_modules)

    kernel_json  = optimizer.trim_kernel(engine_results.get("kernel", {}))
    synergy_json = optimizer.trim_synergy(engine_results.get("synergy", {}))

    prompt = SYSTEM_PROMPT.format(
        modules      = ", ".join(req.active_modules),
        engine_json  = json.dumps(kernel_json,  ensure_ascii=False),
        synergy_json = json.dumps(synergy_json, ensure_ascii=False),
        user_query   = req.user_query,
    )
    response = await gemini_model.generate_content_async(prompt)
    result_text = response.text

    if req.conversation_id:
        store.add(req.conversation_id, req.user_query, result_text)

    return {
        "result":       result_text,
        "kernel_data":  engine_results.get("kernel"),
        "synergy_data": engine_results.get("synergy"),
        "modules_used": req.active_modules,
    }


@app.get("/api/kernel/test")
async def kernel_test():
    """커널 동작 확인용 테스트 엔드포인트"""
    birth = BirthInfo(year=1973, month=10, day=12, hour=14)
    result = await run_kernel(birth)
    return {
        "status":          "ok",
        "four_pillars":    result.get("four_pillars_string"),
        "gyeokguk":        result.get("gyeokguk"),
        "yongsin":         result.get("yongsin", {}).get("억부용신"),
        "shinsal_count":   len(result.get("shinsal", [])),
        "kernel_version":  result.get("version"),
    }


@app.get("/api/synergy/test")
async def synergy_test():
    """Synergy_X 동작 확인용 테스트 엔드포인트"""
    birth = BirthInfo(year=1973, month=10, day=12, hour=14)
    kernel = await run_kernel(birth)
    synergy = await run_synergy(kernel, ["명리", "재물운"])
    return {
        "status":         "ok",
        "분석모듈수":      synergy.get("분석모듈수"),
        "전체충돌수":      synergy.get("전체충돌수"),
        "전체신뢰도":      synergy.get("전체신뢰도"),
        "remedy수":        len(synergy.get("remedy우선순위", [])),
    }


@app.get("/api/performance")
async def performance():
    return optimizer.report()


@app.get("/api/health")
async def health():
    return {
        "status":      "ok",
        "version":     "v13.0",
        "kernel":      "gsaju_kernel.py 연결됨",
        "synergy":     "synergy_x.py 연결됨",
        "lite_mode":   optimizer.lite_mode,
    }


# ════════════════════════════════════════════════
# 8. 실행
# ════════════════════════════════════════════════

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level="info"
    )
