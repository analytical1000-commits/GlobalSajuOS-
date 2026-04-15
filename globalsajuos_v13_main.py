import os,json,time,asyncio,logging
from typing import AsyncGenerator,Optional
import google.generativeai as genai
from fastapi import FastAPI
from fastapi.responses import StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel,Field,field_validator
from dotenv import load_dotenv
from gsaju_kernel import SajuCoreEngine,LOCATION_LONGITUDE
from synergy_x import SynergyX,ModuleResult
from vision_engine import VisionEngine,VisionType,vision_router
logging.basicConfig(level=logging.INFO)
logger=logging.getLogger("GlobalSajuOS")
load_dotenv()
genai.configure(api_key=os.environ["GSAJU_AI_API_KEY"])
app=FastAPI(title="GlobalSajuOS v13.0",version="13.0.0")
app.add_middleware(CORSMiddleware,allow_origins=["*"],allow_methods=["*"],allow_headers=["*"])
app.include_router(vision_router)
_se=SajuCoreEngine()
_sx=SynergyX()
_ve=VisionEngine()
class BirthInfo(BaseModel):
    year:int=Field(...,ge=1900,le=2100)
    month:int=Field(...,ge=1,le=12)
    day:int=Field(...,ge=1,le=31)
    hour:int=Field(...,ge=0,le=23)
    minute:int=Field(0,ge=0,le=59)
    gender:str=Field("M")
    location:str=Field("서울")
    is_lunar:bool=Field(False)
    @field_validator("gender")
    @classmethod
    def vg(cls,v):
        if v not in("M","F"):raise ValueError("M or F")
        return v
class SajuRequest(BaseModel):
    birth:BirthInfo
    user_query:str=Field(...,min_length=1,max_length=500)
    active_modules:list[str]=Field(default=["명리"])
    conversation_id:Optional[str]=None
gm=genai.GenerativeModel("gemini-2.0-flash",generation_config=genai.types.GenerationConfig(max_output_tokens=800,temperature=0.7))
PT="""너는 GlobalSajuOS v13.0 해석 엔진이다.
규칙:수치수정금지/흉살시remedy먼저/3문단이내/대주님짤랑짤랑금지
모듈:{modules}
사주:{engine_json}
synergy:{synergy_json}
질문:{user_query}"""
store={}
def gc(cid):
    if not cid or cid not in store:return ""
    return "\n".join([f"Q:{t['u']}\nA:{t['a']}" for t in store[cid][-3:]])
def ac(cid,u,a):
    if cid not in store:store[cid]=[]
    store[cid].append({"u":u[:80],"a":a[:150]})
    if len(store[cid])>5:store[cid]=store[cid][-3:]
      async def rk(birth:BirthInfo):
    def _s():
        bd={"year":birth.year,"month":birth.month,"day":birth.day,"hour":birth.hour,"minute":birth.minute,"gender":birth.gender}
        lon=LOCATION_LONGITUDE.get(birth.location,126.9)
        ld={"name":birth.location,"longitude":lon,"timezone":9.0}
        return _se.calculate_pillars(bd,ld)
    try:
        r=await asyncio.to_thread(_s)
        logger.info(f"커널완료:{r.get('four_pillars_string')}")
        return r
    except Exception as e:
        raise RuntimeError(str(e))
async def rs(kr,modules):
    def _s():
        results=[]
        ys=kr.get("yongsin",{})
        sh=kr.get("shinsal",[])
        gk=kr.get("gyeokguk","")
        cd=kr.get("current_daeun",{})
        d="흉" if len(sh)>=2 else "중립"
        rm="신살대처:개운법권장" if sh else None
        if ys.get("억부용신"):d="길" if ys.get("신강신약")=="신약" else "중립"
        results.append(ModuleResult("명리","원국분석",f"{kr.get('four_pillars_string','')}/{gk}",d,0.75,gk,rm,cd.get("간지","")))
        if cd:results.append(ModuleResult("명리","대운흐름",f"현재{cd.get('간지')}대운","중립",0.8,"대운주기"))
        if "재물운" in modules:results.append(ModuleResult("재물운","재물운","재물기운분석","중립",0.55,"운세참고용"))
        return _sx.analyze(results,list(set(r.topic for r in results)))
    try:
        return await asyncio.to_thread(_s)
    except Exception as e:
        logger.error(f"synergy오류:{e}")
        return {"전체충돌수":0,"전체신뢰도":0,"주제별판정":{},"remedy우선순위":[]}
async def rpe(birth,modules):
    kr=await rk(birth)
    sr=await rs(kr,modules)
    return {"kernel":kr,"synergy":sr,"modules":modules}
async def gs(er,uq,modules,cid)->AsyncGenerator[str,None]:
    start=time.time()
    kj=er.get("kernel",{})
    sj=er.get("synergy",{})
    hx=gc(cid) if cid else ""
    p=PT.format(modules=",".join(modules),engine_json=json.dumps(kj,ensure_ascii=False),synergy_json=json.dumps(sj,ensure_ascii=False),user_query=uq)
    if hx:p=hx+"\n\n"+p
    try:
        resp=await gm.generate_content_async(p,stream=True)
        ft=""
        async for chunk in resp:
            if chunk.text:
                ft+=chunk.text
                yield f"data: {chunk.text}\n\n"
        if cid:ac(cid,uq,ft)
        yield "data: [DONE]\n\n"
    except Exception as e:
        yield "data: [ERROR]\n\n"
        yield "data: [DONE]\n\n"
@app.post("/api/saju/stream")
async def ss(req:SajuRequest):
    try:er=await rpe(req.birth,req.active_modules)
    except RuntimeError as e:
        async def fb():
            yield f"data: 오류가 발생했습니다.\n\n"
            yield "data: [DONE]\n\n"
        return StreamingResponse(fb(),media_type="text/event-stream")
    return StreamingResponse(gs(er,req.user_query,req.active_modules,req.conversation_id),media_type="text/event-stream",headers={"Cache-Control":"no-cache"})
@app.post("/api/saju/sync")
async def sy(req:SajuRequest):
    er=await rpe(req.birth,req.active_modules)
    p=PT.format(modules=",".join(req.active_modules),engine_json=json.dumps(er.get("kernel",{}),ensure_ascii=False),synergy_json=json.dumps(er.get("synergy",{}),ensure_ascii=False),user_query=req.user_query)
    resp=await gm.generate_content_async(p)
    if req.conversation_id:ac(req.conversation_id,req.user_query,resp.text)
    return {"result":resp.text,"kernel_data":er.get("kernel"),"modules_used":req.active_modules}
@app.get("/api/kernel/test")
async def kt():
    b=BirthInfo(year=1973,month=10,day=12,hour=14)
    r=await rk(b)
    return {"status":"ok","four_pillars":r.get("four_pillars_string"),"gyeokguk":r.get("gyeokguk"),"version":r.get("version")}
@app.get("/api/health")
async def hl():
    return {"status":"ok","version":"v13.0","kernel":"connected","synergy":"connected","vision":"connected"}
