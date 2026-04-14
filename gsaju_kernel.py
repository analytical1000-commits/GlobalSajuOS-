"""
gsaju_kernel.py — GlobalSajuOS v13.0 핵심 명리 계산 커널
SajuCoreEngine 클래스 / calculate_pillars 메서드

설계 원칙:
- AI 개입 완전 차단 — 순수 수리 연산만 수행
- Jean Meeus 천문 알고리즘 기반 절기 계산
- TST(진태양시) 경도 보정 적용
- 야자시/정자시 처리
- 윤달 절기 기준 처리
- 반환: RAW JSON (v13.0 표준 규격)
"""

import math
from datetime import datetime, timedelta
from typing import Optional


# ════════════════════════════════════════════════
# 1. 기본 상수 — 천간·지지·오행
# ════════════════════════════════════════════════

# 천간 (10개)
STEMS = ["甲", "乙", "丙", "丁", "戊", "己", "庚", "辛", "壬", "癸"]
STEMS_KR = ["갑", "을", "병", "정", "무", "기", "경", "신", "임", "계"]

# 지지 (12개)
BRANCHES = ["子", "丑", "寅", "卯", "辰", "巳", "午", "未", "申", "酉", "戌", "亥"]
BRANCHES_KR = ["자", "축", "인", "묘", "진", "사", "오", "미", "신", "유", "술", "해"]

# 천간 오행
STEM_ELEMENT = {
    "甲": "木", "乙": "木",
    "丙": "火", "丁": "火",
    "戊": "土", "己": "土",
    "庚": "金", "辛": "金",
    "壬": "水", "癸": "水",
}

# 천간 음양
STEM_YIN_YANG = {
    "甲": "陽", "乙": "陰", "丙": "陽", "丁": "陰", "戊": "陽",
    "己": "陰", "庚": "陽", "辛": "陰", "壬": "陽", "癸": "陰",
}

# 지지 오행
BRANCH_ELEMENT = {
    "子": "水", "丑": "土", "寅": "木", "卯": "木",
    "辰": "土", "巳": "火", "午": "火", "未": "土",
    "申": "金", "酉": "金", "戌": "土", "亥": "水",
}

# 지지 음양
BRANCH_YIN_YANG = {
    "子": "陽", "丑": "陰", "寅": "陽", "卯": "陰",
    "辰": "陽", "巳": "陰", "午": "陽", "未": "陰",
    "申": "陽", "酉": "陰", "戌": "陽", "亥": "陰",
}

# 지지 지장간 (본기·중기·여기)
BRANCH_JIJANGGAN = {
    "子": {"본기": "癸", "중기": None,  "여기": None},
    "丑": {"본기": "己", "중기": "癸",  "여기": "辛"},
    "寅": {"본기": "甲", "중기": "丙",  "여기": "戊"},
    "卯": {"본기": "乙", "중기": None,  "여기": None},
    "辰": {"본기": "戊", "중기": "乙",  "여기": "癸"},
    "巳": {"본기": "丙", "중기": "戊",  "여기": "庚"},
    "午": {"본기": "丁", "중기": "己",  "여기": None},
    "未": {"본기": "己", "중기": "丁",  "여기": "乙"},
    "申": {"본기": "庚", "중기": "壬",  "여기": "戊"},
    "酉": {"본기": "辛", "중기": None,  "여기": None},
    "戌": {"본기": "戊", "중기": "辛",  "여기": "丁"},
    "亥": {"본기": "壬", "중기": "甲",  "여기": None},
}

# 오행 상생
ELEMENT_BIRTH = {
    "木": "火", "火": "土", "土": "金", "金": "水", "水": "木"
}

# 오행 상극
ELEMENT_KILL = {
    "木": "土", "土": "水", "水": "火", "火": "金", "金": "木"
}

# 위치별 경도 (TST 보정용)
LOCATION_LONGITUDE = {
    "서울":    126.9, "부산":    129.0, "창원":    128.6,
    "제주":    126.5, "대구":    128.6, "광주":    126.9,
    "인천":    126.7, "수원":    127.0, "대전":    127.4,
    "도쿄":    139.7, "오사카":  135.5, "베이징":  116.4,
    "상하이":  121.5, "뉴욕":    -74.0, "LA":     -118.2,
    "런던":     -0.1, "파리":      2.3, "시드니":  151.2,
    "싱가포르": 103.8, "두바이":   55.3, "홍콩":    114.2,
}


# ════════════════════════════════════════════════
# 2. 절기 계산 — Jean Meeus 알고리즘
# ════════════════════════════════════════════════

# 절기 목록 (월주 기준)
# 인월(1월) 시작 = 입춘(2월 4일경) → 월지 寅
SOLAR_TERMS = [
    # (절기명, 태양황경도, 월지인덱스)
    ("소한",  285, 11),  # 12월 → 亥
    ("대한",  300, 11),
    ("입춘",  315,  0),  # 1월  → 寅 (인월 시작)
    ("우수",  330,  0),
    ("경칩",  345,  1),  # 2월  → 卯
    ("춘분",    0,  1),
    ("청명",   15,  2),  # 3월  → 辰
    ("곡우",   30,  2),
    ("입하",   45,  3),  # 4월  → 巳
    ("소만",   60,  3),
    ("망종",   75,  4),  # 5월  → 午
    ("하지",   90,  4),
    ("소서",  105,  5),  # 6월  → 未
    ("대서",  120,  5),
    ("입추",  135,  6),  # 7월  → 申
    ("처서",  150,  6),
    ("백로",  165,  7),  # 8월  → 酉
    ("추분",  180,  7),
    ("한로",  195,  8),  # 9월  → 戌
    ("상강",  210,  8),
    ("입동",  225,  9),  # 10월 → 亥
    ("소설",  240,  9),
    ("대설",  255, 10),  # 11월 → 子
    ("동지",  270, 10),
]

# 월지 순서: 인(寅)부터 시작
MONTH_BRANCHES = ["寅", "卯", "辰", "巳", "午", "未", "申", "酉", "戌", "亥", "子", "丑"]


def _calc_solar_longitude(year: int, month: int, day: int, hour: float = 12.0) -> float:
    """
    태양 황경 계산 (Jean Meeus 간략 알고리즘)
    반환: 태양 황경(도)
    """
    # JDE 계산
    if month <= 2:
        year -= 1
        month += 12
    A = int(year / 100)
    B = 2 - A + int(A / 4)
    JDE = int(365.25 * (year + 4716)) + int(30.6001 * (month + 1)) + day + hour / 24 + B - 1524.5

    # T = 율리우스 세기
    T = (JDE - 2451545.0) / 36525.0

    # 태양 평균 경도
    L0 = 280.46646 + 36000.76983 * T + 0.0003032 * T * T
    L0 = L0 % 360

    # 태양 평균 이상
    M = 357.52911 + 35999.05029 * T - 0.0001537 * T * T
    M = math.radians(M % 360)

    # 방정식의 중심
    C = (1.914602 - 0.004817 * T - 0.000014 * T * T) * math.sin(M)
    C += (0.019993 - 0.000101 * T) * math.sin(2 * M)
    C += 0.000289 * math.sin(3 * M)

    sun_lon = (L0 + C) % 360
    return sun_lon


def _find_solar_term_datetime(year: int, target_longitude: float) -> datetime:
    """
    특정 태양 황경에 도달하는 날짜·시각 계산
    이분법(bisection)으로 정밀 탐색
    """
    # 대략적인 시작 날짜 추정
    # 황경 315 = 입춘 ≈ 2월 4일
    approx_day = int((target_longitude - 315) % 360 / 360 * 365) + 35
    start = datetime(year, 1, 1) + timedelta(days=approx_day - 15)
    end   = start + timedelta(days=30)

    # 이분법으로 정밀화
    for _ in range(50):
        mid = start + (end - start) / 2
        lon = _calc_solar_longitude(mid.year, mid.month, mid.day, mid.hour + mid.minute / 60)

        # 황경 경계 처리 (0°/360° 근처)
        diff = (lon - target_longitude + 180) % 360 - 180

        if abs(diff) < 0.0001:
            return mid
        if diff < 0:
            start = mid
        else:
            end = mid

    return start + (end - start) / 2


def get_solar_term_for_month(year: int, month: int) -> datetime:
    """
    해당 연월의 절기(입절) 날짜·시각 반환
    month: 명리 월 기준 (1=인월/입춘, 2=묘월/경칩, ...)
    """
    # 절기 황경: 입춘=315, 경칩=345, 청명=15, ...
    base_longitudes = [315, 345, 15, 45, 75, 105, 135, 165, 195, 225, 255, 285]
    target_lon = base_longitudes[month - 1]

    # 연도 보정 (子월=12월은 다음해 1월)
    calc_year = year
    if month == 12:  # 丑월 (대한 = 1월)
        calc_year = year + 1 if month > 10 else year

    return _find_solar_term_datetime(calc_year, target_lon)


# ════════════════════════════════════════════════
# 3. TST (진태양시) 보정
# ════════════════════════════════════════════════

def _calc_equation_of_time(year: int, month: int, day: int) -> float:
    """
    균시차(Equation of Time) 계산 (분 단위)
    Jean Meeus 방법
    """
    T = (_calc_jde(year, month, day) - 2451545.0) / 36525.0
    epsilon0 = 23.4392911 - 0.013004167 * T
    epsilon = math.radians(epsilon0)

    L0 = math.radians(280.46646 + 36000.76983 * T)
    M  = math.radians(357.52911 + 35999.05029 * T)
    e  = 0.016708634 - 0.000042037 * T

    y = math.tan(epsilon / 2) ** 2

    E = (y * math.sin(2 * L0)
         - 2 * e * math.sin(M)
         + 4 * e * y * math.sin(M) * math.cos(2 * L0)
         - 0.5 * y * y * math.sin(4 * L0)
         - 1.25 * e * e * math.sin(2 * M))

    return math.degrees(E) * 4  # 분 단위


def _calc_jde(year: int, month: int, day: int) -> float:
    if month <= 2:
        year -= 1
        month += 12
    A = int(year / 100)
    B = 2 - A + int(A / 4)
    return int(365.25 * (year + 4716)) + int(30.6001 * (month + 1)) + day + B - 1524.5


def calc_tst(year: int, month: int, day: int,
             hour: int, minute: int,
             longitude: float, timezone_offset: float = 9.0) -> tuple[int, int]:
    """
    진태양시(TST) 계산
    반환: (tst_hour, tst_minute)

    공식: TST = 표준시 + 경도보정 + 균시차
    경도보정 = (경도 - 표준경도) / 15 × 60분
    표준경도 = timezone_offset × 15
    """
    std_meridian = timezone_offset * 15

    # 경도 보정 (분)
    longitude_correction = (longitude - std_meridian) / 15 * 60

    # 균시차 (분)
    eot = _calc_equation_of_time(year, month, day)

    # 총 보정 (분)
    total_correction = longitude_correction + eot

    # TST 계산
    total_minutes = hour * 60 + minute + total_correction
    tst_hour   = int(total_minutes // 60) % 24
    tst_minute = int(total_minutes % 60)

    return tst_hour, tst_minute


# ════════════════════════════════════════════════
# 4. 연주·월주·일주·시주 계산
# ════════════════════════════════════════════════

def calc_year_pillar(year: int, month: int, day: int,
                     month_branch_idx: int) -> tuple[str, str]:
    """
    연주 계산
    입춘(인월 시작) 이전 출생 → 전년도 연주
    """
    # 입춘 날짜 확인
    ipchun = _find_solar_term_datetime(year, 315)  # 황경 315 = 입춘

    birth_dt = datetime(year, month, day)

    # 입춘 이전이면 전년도 기준
    ref_year = year if birth_dt >= ipchun else year - 1

    stem_idx   = (ref_year - 4) % 10
    branch_idx = (ref_year - 4) % 12

    return STEMS[stem_idx], BRANCHES[branch_idx]


def calc_month_pillar(year: int, month: int, day: int,
                      hour: int, minute: int,
                      longitude: float,
                      timezone_offset: float = 9.0) -> tuple[str, str]:
    """
    월주 계산 — TST 기준 절기 판단
    """
    tst_h, tst_m = calc_tst(year, month, day, hour, minute, longitude, timezone_offset)

    # TST 기준 출생 시각
    birth_tst = datetime(year, month, day, tst_h, tst_m)

    # 현재 월의 절기와 다음 달 절기를 비교하여 월지 결정
    # 명리 월 인덱스 탐색 (입춘=1월 기준)
    myungri_month = _find_myungri_month(year, month, day, birth_tst)

    # 월주 천간 계산
    # 갑기년→병인월 시작, 을경년→무인월 시작, 병신년→경인월 시작
    # 정임년→임인월 시작, 무계년→갑인월 시작
    year_stem_idx = (year - 4) % 10
    # 입춘 이전이면 전년도 기준
    ipchun = _find_solar_term_datetime(year, 315)
    birth_dt = datetime(year, month, day)
    if birth_dt < ipchun:
        year_stem_idx = (year - 5) % 10

    # 인월 천간 기준값
    month_stem_base = [2, 4, 6, 8, 0, 2, 4, 6, 8, 0]  # 甲己→丙, 乙庚→戊...
    base_stem = month_stem_base[year_stem_idx]

    stem_idx   = (base_stem + myungri_month - 1) % 10
    branch_idx = (myungri_month - 1) % 12  # 인월=0 → 寅=0

    return STEMS[stem_idx], MONTH_BRANCHES[branch_idx]


def _find_myungri_month(year: int, month: int, day: int, birth_tst: datetime) -> int:
    """
    TST 기준으로 명리 월(1~12) 결정
    1 = 인월(입춘~경칩 전), 2 = 묘월(경칩~청명 전), ...
    """
    base_longitudes = [315, 345, 15, 45, 75, 105, 135, 165, 195, 225, 255, 285]

    for m_idx in range(12):
        this_term = _find_solar_term_datetime(year, base_longitudes[m_idx])
        next_m    = (m_idx + 1) % 12
        next_year = year + 1 if next_m == 0 and m_idx == 11 else year
        next_term = _find_solar_term_datetime(next_year, base_longitudes[next_m])

        if this_term <= birth_tst < next_term:
            return m_idx + 1

    return 1  # fallback


def calc_day_pillar(year: int, month: int, day: int,
                    hour: int, minute: int,
                    is_yajasi: bool = False) -> tuple[str, str]:
    """
    일주 계산
    야자시(23:00~24:00): 전날 일주 사용
    기준: 2000-01-01 = 甲辰일 (offset=0)
    """
    ref = datetime(2000, 1, 1)
    birth = datetime(year, month, day)

    # 야자시: 23:00 이후면 다음날 자시 → 당일 일주 그대로 사용
    # 야자시(전날 기준): 23:00~24:00 → 전날 일주
    if is_yajasi and hour == 23:
        birth -= timedelta(days=1)

    delta = (birth - ref).days

    # 甲辰 기준 offset
    # 2000-01-01 甲辰: 甲=0, 辰=4
    stem_idx   = (0 + delta) % 10
    branch_idx = (4 + delta) % 12

    return STEMS[stem_idx], BRANCHES[branch_idx]


def calc_hour_pillar(day_stem: str, tst_hour: int) -> tuple[str, str]:
    """
    시주 계산 — TST 기준 시지 결정
    일간에 따른 시간 천간 조견표 적용
    """
    # 시지 결정 (TST 기준)
    # 子시: 23~01, 丑시: 01~03, 寅시: 03~05...
    hour_branch_map = [
        (23, 1,  0),  # 子
        (1,  3,  1),  # 丑
        (3,  5,  2),  # 寅
        (5,  7,  3),  # 卯
        (7,  9,  4),  # 辰
        (9,  11, 5),  # 巳
        (11, 13, 6),  # 午
        (13, 15, 7),  # 未
        (15, 17, 8),  # 申
        (17, 19, 9),  # 酉
        (19, 21, 10), # 戌
        (21, 23, 11), # 亥
    ]

    branch_idx = 0
    for start, end, idx in hour_branch_map:
        if start == 23:
            if tst_hour >= 23 or tst_hour < 1:
                branch_idx = idx
                break
        elif start <= tst_hour < end:
            branch_idx = idx
            break

    # 시간 천간 조견표
    # 甲己일→甲子시, 乙庚일→丙子시, 丙辛일→戊子시, 丁壬일→庚子시, 戊癸일→壬子시
    day_stem_idx = STEMS.index(day_stem)
    hour_stem_base = [0, 2, 4, 6, 8, 0, 2, 4, 6, 8]  # 갑=甲, 을=丙...
    base = hour_stem_base[day_stem_idx]
    stem_idx = (base + branch_idx) % 10

    return STEMS[stem_idx], BRANCHES[branch_idx]


# ════════════════════════════════════════════════
# 5. 오행 분포 계산
# ════════════════════════════════════════════════

def calc_elements(pillars: list[tuple[str, str]]) -> dict:
    """
    사주 원국 오행 분포 계산
    pillars: [(연간, 연지), (월간, 월지), (일간, 일지), (시간, 시지)]
    """
    elements = {"木": 0, "火": 0, "土": 0, "金": 0, "水": 0}

    for stem, branch in pillars:
        # 천간 오행
        if stem in STEM_ELEMENT:
            elements[STEM_ELEMENT[stem]] += 1

        # 지지 오행
        if branch in BRANCH_ELEMENT:
            elements[BRANCH_ELEMENT[branch]] += 1

        # 지장간 본기 추가 (0.5 가중치)
        jjg = BRANCH_JIJANGGAN.get(branch, {})
        if jjg.get("본기"):
            el = STEM_ELEMENT.get(jjg["본기"])
            if el:
                elements[el] += 0.5

    return {k: round(v, 1) for k, v in elements.items()}


# ════════════════════════════════════════════════
# 6. 용신 판단
# ════════════════════════════════════════════════

def calc_yongsin(day_stem: str, elements: dict, month_branch: str) -> dict:
    """
    용신 판단 — 억부용신 우선, 조후 보조

    억부용신:
    - 신강(일간 강함) → 극설(克洩) 오행이 용신
    - 신약(일간 약함) → 생부(生扶) 오행이 용신

    조후용신:
    - 월지 기준 한난조습 판단
    """
    day_element = STEM_ELEMENT[day_stem]
    day_yin_yang = STEM_YIN_YANG[day_stem]

    # 일간 강약 판단 (간략 버전)
    same_element = elements.get(day_element, 0)
    total = sum(elements.values())
    strength_ratio = same_element / total if total > 0 else 0

    # 신강/신약 판단
    is_strong = strength_ratio >= 0.3

    if is_strong:
        # 신강 → 극(克)하거나 설기(洩氣)하는 오행
        kill_element = ELEMENT_KILL[day_element]
        drain_element = ELEMENT_BIRTH[day_element]
        yongsin_elements = [kill_element, drain_element]
        gishin_elements = [day_element, ELEMENT_BIRTH.get(
            [k for k, v in ELEMENT_KILL.items() if v == day_element][0], day_element
        )]
        type_kr = "억부용신(신강)"
    else:
        # 신약 → 생(生)하거나 같은 오행
        birth_element = [k for k, v in ELEMENT_BIRTH.items() if v == day_element]
        birth_el = birth_element[0] if birth_element else day_element
        yongsin_elements = [birth_el, day_element]
        gishin_elements = [ELEMENT_KILL[day_element]]
        type_kr = "억부용신(신약)"

    # 조후 보조 — 월지 기준
    johu_season = {
        "寅": "봄(木)", "卯": "봄(木)", "辰": "봄(土)",
        "巳": "여름(火)", "午": "여름(火)", "未": "여름(土)",
        "申": "가을(金)", "酉": "가을(金)", "戌": "가을(土)",
        "亥": "겨울(水)", "子": "겨울(水)", "丑": "겨울(土)",
    }

    johu_yongsin = []
    season = johu_season.get(month_branch, "")
    if "여름" in season or "火" in season:
        johu_yongsin = ["水", "金"]  # 더위 조절
    elif "겨울" in season or "水" in season:
        johu_yongsin = ["火", "木"]  # 추위 조절

    return {
        "억부용신": yongsin_elements,
        "기신": gishin_elements,
        "조후용신": johu_yongsin,
        "신강신약": "신강" if is_strong else "신약",
        "용신타입": type_kr,
        "일간강도": round(strength_ratio, 2),
    }


# ════════════════════════════════════════════════
# 7. 격국 판별
# ════════════════════════════════════════════════

def calc_gyeokguk(month_branch: str, day_stem: str, elements: dict) -> str:
    """
    격국 판별 — 월지 본기 기준 내격 판별
    """
    jjg = BRANCH_JIJANGGAN.get(month_branch, {})
    bongi_stem = jjg.get("본기", "")
    day_element = STEM_ELEMENT[day_stem]

    if not bongi_stem:
        return "미상격"

    bongi_element = STEM_ELEMENT.get(bongi_stem, "")

    # 십신 관계 파악
    relation = _get_shipsin(day_stem, bongi_stem)

    gyeokguk_map = {
        "비겁": "비겁격",
        "식신": "식신격",
        "상관": "상관격",
        "편재": "편재격",
        "정재": "정재격",
        "편관": "편관격(七殺格)",
        "정관": "정관격",
        "편인": "편인격(梟神格)",
        "정인": "정인격",
    }

    return gyeokguk_map.get(relation, f"{relation}격")


def _get_shipsin(day_stem: str, other_stem: str) -> str:
    """
    일간 기준 십신 관계 계산
    """
    day_el = STEM_ELEMENT[day_stem]
    other_el = STEM_ELEMENT[other_stem]
    day_yin = STEM_YIN_YANG[day_stem]
    other_yin = STEM_YIN_YANG[other_stem]
    same_yin = (day_yin == other_yin)

    if day_el == other_el:
        return "비견" if same_yin else "겁재"

    # 일간이 생하는 오행 (식상)
    if ELEMENT_BIRTH[day_el] == other_el:
        return "식신" if same_yin else "상관"

    # 일간을 생하는 오행 (인성)
    if ELEMENT_BIRTH[other_el] == day_el:
        return "정인" if same_yin else "편인"

    # 일간이 극하는 오행 (재성)
    if ELEMENT_KILL[day_el] == other_el:
        return "정재" if same_yin else "편재"

    # 일간을 극하는 오행 (관성)
    if ELEMENT_KILL[other_el] == day_el:
        return "정관" if same_yin else "편관"

    return "미상"


# ════════════════════════════════════════════════
# 8. 신살 계산
# ════════════════════════════════════════════════

def calc_shinsal(pillars: list[tuple[str, str]], year: int) -> list[str]:
    """
    주요 신살 계산
    pillars: [(연간, 연지), (월간, 월지), (일간, 일지), (시간, 시지)]
    """
    shinsal = []
    stems   = [p[0] for p in pillars]
    branches = [p[1] for p in pillars]
    day_stem   = stems[2]
    day_branch = branches[2]
    year_branch = branches[0]

    # 천을귀인 (天乙貴人)
    chuneul = {
        "甲": ["丑", "未"], "乙": ["子", "申"], "丙": ["亥", "酉"],
        "丁": ["亥", "酉"], "戊": ["丑", "未"], "己": ["子", "申"],
        "庚": ["丑", "未"], "辛": ["寅", "午"], "壬": ["卯", "巳"],
        "癸": ["卯", "巳"],
    }
    chuneul_branches = chuneul.get(day_stem, [])
    for b in branches:
        if b in chuneul_branches:
            shinsal.append("天乙貴人(천을귀인)")
            break

    # 양인살 (羊刃殺)
    yangrin = {
        "甲": "卯", "丙": "午", "戊": "午", "庚": "酉", "壬": "子",
        "乙": "辰", "丁": "未", "己": "未", "辛": "戌", "癸": "丑",
    }
    if yangrin.get(day_stem) in branches:
        shinsal.append("羊刃殺(양인살)")

    # 괴강살 (魁罡殺)
    if day_stem + day_branch in ["庚辰", "庚戌", "壬辰", "壬戌"]:
        shinsal.append("魁罡殺(괴강살)")

    # 백호대살 (白虎大殺)
    baekoho_pillars = ["甲辰", "乙未", "丙戌", "丁丑", "戊辰", "己未", "庚戌", "辛丑", "壬辰", "癸未"]
    for s, b in pillars:
        if s + b in baekoho_pillars:
            shinsal.append("白虎大殺(백호대살)")
            break

    # 삼형살 — 축술미(丑戌未)
    count_chuk_sul_mi = sum(1 for b in branches if b in ["丑", "戌", "未"])
    if count_chuk_sul_mi >= 3:
        shinsal.append("丑戌未三刑殺(축술미삼형살)")

    # 삼형살 — 인사신(寅巳申)
    count_in_sa_sin = sum(1 for b in branches if b in ["寅", "巳", "申"])
    if count_in_sa_sin >= 3:
        shinsal.append("寅巳申三刑殺(인사신삼형살)")

    # 지지 충 (六沖)
    chung_pairs = [("子", "午"), ("丑", "未"), ("寅", "申"), ("卯", "酉"), ("辰", "戌"), ("巳", "亥")]
    for a, b in chung_pairs:
        count_a = branches.count(a)
        count_b = branches.count(b)
        if count_a > 0 and count_b > 0:
            shinsal.append(f"{a}{b}沖({a}{b}충)")

    # 원진살 (怨嗔殺)
    wonjin = {
        "子": "未", "丑": "午", "寅": "酉", "卯": "申",
        "辰": "亥", "巳": "戌", "午": "丑", "未": "子",
        "申": "卯", "酉": "寅", "戌": "巳", "亥": "辰",
    }
    if wonjin.get(day_branch) in branches:
        shinsal.append("怨嗔殺(원진살)")

    # 역마살 (驛馬殺)
    yeokma = {"子": "寅", "午": "申", "卯": "亥", "酉": "巳",
              "寅": "申", "申": "寅", "巳": "亥", "亥": "巳",
              "辰": "寅", "戌": "申", "丑": "亥", "未": "巳"}
    if yeokma.get(year_branch) in branches:
        shinsal.append("驛馬殺(역마살)")

    # 공망 (空亡)
    gongmang = _calc_gongmang(stems[0], branches[0])
    for b in branches[1:]:  # 월지·일지·시지에서 공망 확인
        if b in gongmang:
            shinsal.append(f"空亡(공망-{b})")

    return list(set(shinsal))  # 중복 제거


def _calc_gongmang(year_stem: str, year_branch: str) -> list[str]:
    """
    공망 계산 — 연주 기준
    60갑자에서 빠진 두 지지
    """
    stem_idx   = STEMS.index(year_stem)
    branch_idx = BRANCHES.index(year_branch)

    # 60갑자 순환에서 마지막 두 지지가 공망
    # 기준: 천간 10개, 지지 12개 → 차이 2개가 공망
    gongmang_start = (branch_idx + 10) % 12
    return [BRANCHES[gongmang_start], BRANCHES[(gongmang_start + 1) % 12]]


# ════════════════════════════════════════════════
# 9. 대운 계산
# ════════════════════════════════════════════════

def calc_daeun(year: int, month: int, day: int,
               year_stem: str, year_branch: str,
               month_stem: str, month_branch: str,
               gender: str = "M") -> list[dict]:
    """
    대운 계산 (10년 주기)
    순행/역행: 양남음녀 순행, 음남양녀 역행

    반환: 최대 8개 대운 목록
    """
    year_yin = STEM_YIN_YANG[year_stem]

    # 순역 결정
    if gender == "M":
        forward = (year_yin == "陽")
    else:
        forward = (year_yin == "陰")

    # 대운 시작 나이 계산 (절기까지 날수 / 3)
    birth_dt = datetime(year, month, day)

    if forward:
        # 다음 절기까지 일수
        next_term = _get_next_solar_term(year, month, day)
        days_to_term = (next_term - birth_dt).days
    else:
        # 이전 절기까지 일수
        prev_term = _get_prev_solar_term(year, month, day)
        days_to_term = (birth_dt - prev_term).days

    start_age = max(1, round(days_to_term / 3))

    # 대운 간지 생성 (월주 기준 순역)
    month_stem_idx   = STEMS.index(month_stem)
    month_branch_idx = BRANCHES.index(month_branch)

    daeun_list = []
    for i in range(8):
        if forward:
            s_idx = (month_stem_idx   + i + 1) % 10
            b_idx = (month_branch_idx + i + 1) % 12
        else:
            s_idx = (month_stem_idx   - i - 1) % 10
            b_idx = (month_branch_idx - i - 1) % 12

        age = start_age + i * 10
        daeun_list.append({
            "순서":   i + 1,
            "간지":   STEMS[s_idx] + BRANCHES[b_idx],
            "천간":   STEMS[s_idx],
            "지지":   BRANCHES[b_idx],
            "시작나이": age,
            "종료나이": age + 9,
        })

    return daeun_list


def _get_next_solar_term(year: int, month: int, day: int) -> datetime:
    base_longitudes = [315, 345, 15, 45, 75, 105, 135, 165, 195, 225, 255, 285]
    birth_dt = datetime(year, month, day)
    for lon in base_longitudes:
        term = _find_solar_term_datetime(year, lon)
        if term > birth_dt:
            return term
    return _find_solar_term_datetime(year + 1, 315)


def _get_prev_solar_term(year: int, month: int, day: int) -> datetime:
    base_longitudes = [315, 345, 15, 45, 75, 105, 135, 165, 195, 225, 255, 285]
    birth_dt = datetime(year, month, day)
    result = datetime(year - 1, 12, 1)
    for lon in base_longitudes:
        term = _find_solar_term_datetime(year, lon)
        if term < birth_dt:
            result = term
    return result


# ════════════════════════════════════════════════
# 10. SajuCoreEngine — 메인 클래스
# ════════════════════════════════════════════════

class SajuCoreEngine:
    """
    GlobalSajuOS v13.0 핵심 명리 계산 엔진

    사용법:
        engine = SajuCoreEngine()
        result = engine.calculate_pillars(birth_data, location_data)
    """

    VERSION = "13.0.0"

    def calculate_pillars(
        self,
        birth_data: dict,
        location_data: dict
    ) -> dict:
        """
        사주 원국 전체 계산

        birth_data: {
            "year": int,
            "month": int,
            "day": int,
            "hour": int,
            "minute": int (기본값 0),
            "gender": str ("M"/"F", 기본값 "M"),
            "is_lunar": bool (기본값 False),
        }

        location_data: {
            "name": str,
            "longitude": float,
            "timezone": float (기본값 9.0),
        }

        반환: RAW JSON dict (v13.0 표준 규격)
        """
        year    = birth_data["year"]
        month   = birth_data["month"]
        day     = birth_data["day"]
        hour    = birth_data["hour"]
        minute  = birth_data.get("minute", 0)
        gender  = birth_data.get("gender", "M")

        longitude = location_data.get("longitude", 126.9)
        tz_offset = location_data.get("timezone", 9.0)
        loc_name  = location_data.get("name", "서울")

        # ── TST 계산 ──
        tst_h, tst_m = calc_tst(year, month, day, hour, minute, longitude, tz_offset)

        # ── 야자시 판별 ──
        is_yajasi  = (hour == 23)
        is_jeongjasi = (hour == 0)

        # ── 연주 계산 ──
        year_stem, year_branch = calc_year_pillar(year, month, day, 0)

        # ── 월주 계산 (TST 기준) ──
        month_stem, month_branch = calc_month_pillar(
            year, month, day, hour, minute, longitude, tz_offset
        )

        # ── 일주 계산 ──
        day_stem, day_branch = calc_day_pillar(
            year, month, day, hour, minute, is_yajasi
        )

        # ── 시주 계산 (TST 기준) ──
        hour_stem, hour_branch = calc_hour_pillar(day_stem, tst_h)

        # ── 사주 기둥 모음 ──
        pillars = [
            (year_stem,  year_branch),
            (month_stem, month_branch),
            (day_stem,   day_branch),
            (hour_stem,  hour_branch),
        ]

        # ── 오행 분포 ──
        elements = calc_elements(pillars)

        # ── 용신 판단 ──
        yongsin_data = calc_yongsin(day_stem, elements, month_branch)

        # ── 격국 판별 ──
        gyeokguk = calc_gyeokguk(month_branch, day_stem, elements)

        # ── 신살 계산 ──
        shinsal = calc_shinsal(pillars, year)

        # ── 대운 계산 ──
        daeun_list = calc_daeun(
            year, month, day,
            year_stem, year_branch,
            month_stem, month_branch,
            gender
        )

        # ── 현재 대운 (출생년 기준 현재 나이 계산) ──
        current_year = datetime.now().year
        birth_age = current_year - year
        current_daeun = next(
            (d for d in daeun_list if d["시작나이"] <= birth_age <= d["종료나이"]),
            daeun_list[0] if daeun_list else {}
        )

        # ── 반환 JSON ──
        return {
            "version": self.VERSION,
            "input": {
                "year": year, "month": month, "day": day,
                "hour": hour, "minute": minute,
                "gender": gender,
                "location": loc_name,
                "longitude": longitude,
            },
            "tst": {
                "tst_hour": tst_h,
                "tst_minute": tst_m,
                "is_yajasi": is_yajasi,
                "is_jeongjasi": is_jeongjasi,
            },
            "pillars": {
                "year":  {"stem": year_stem,  "branch": year_branch,  "pillar": year_stem  + year_branch},
                "month": {"stem": month_stem, "branch": month_branch, "pillar": month_stem + month_branch},
                "day":   {"stem": day_stem,   "branch": day_branch,   "pillar": day_stem   + day_branch},
                "hour":  {"stem": hour_stem,  "branch": hour_branch,  "pillar": hour_stem  + hour_branch},
            },
            "four_pillars_string": (
                f"{year_stem}{year_branch} "
                f"{month_stem}{month_branch} "
                f"{day_stem}{day_branch} "
                f"{hour_stem}{hour_branch}"
            ),
            "elements": elements,
            "elements_balance": _get_elements_balance(elements),
            "yongsin": yongsin_data,
            "gyeokguk": gyeokguk,
            "shinsal": shinsal,
            "daeun": daeun_list,
            "current_daeun": current_daeun,
            "jijanggan": {
                "year_branch":  BRANCH_JIJANGGAN.get(year_branch, {}),
                "month_branch": BRANCH_JIJANGGAN.get(month_branch, {}),
                "day_branch":   BRANCH_JIJANGGAN.get(day_branch, {}),
                "hour_branch":  BRANCH_JIJANGGAN.get(hour_branch, {}),
            },
            "reliability": {
                "engine": "gsaju_kernel.py v13.0",
                "note": "AI 개입 없는 순수 수리 연산 결과",
                "cross_check": "공식 만세력 교차 확인 권장 (절기 경계일 특히 주의)",
            }
        }


def _get_elements_balance(elements: dict) -> str:
    """오행 균형 상태 텍스트 요약"""
    sorted_el = sorted(elements.items(), key=lambda x: x[1], reverse=True)
    strongest = sorted_el[0]
    weakest   = sorted_el[-1]
    zeros     = [k for k, v in elements.items() if v == 0]

    lines = []
    lines.append(f"가장 강한 오행: {strongest[0]}({strongest[1]})")
    lines.append(f"가장 약한 오행: {weakest[0]}({weakest[1]})")
    if zeros:
        lines.append(f"결핍 오행: {', '.join(zeros)}")
    return " / ".join(lines)


# ════════════════════════════════════════════════
# 11. 단독 실행 테스트
# ════════════════════════════════════════════════

if __name__ == "__main__":
    import json

    engine = SajuCoreEngine()

    # 테스트 케이스
    birth_data = {
        "year":   1973,
        "month":  10,
        "day":    12,
        "hour":   14,
        "minute": 0,
        "gender": "F",
        "is_lunar": False,
    }

    location_data = {
        "name":      "서울",
        "longitude": 126.9,
        "timezone":  9.0,
    }

    result = engine.calculate_pillars(birth_data, location_data)
    print(json.dumps(result, ensure_ascii=False, indent=2))
