"""오늘의 음력 날짜와 24절기.

- 음력: korean_lunar_calendar (한국천문연구원 기준 데이터). 설치 안 돼 있으면 음력은 생략
- 24절기: 태양 황경이 15°의 배수가 되는 순간(한국 시간)이 든 날. Meeus 저정밀 식(±0.01°, 몇 분 오차)
"""
import datetime as dt
import math

KST = dt.timezone(dt.timedelta(hours=9))
# (이름, 황경) — 1월부터
TERMS = [("소한", 285), ("대한", 300), ("입춘", 315), ("우수", 330), ("경칩", 345), ("춘분", 0),
         ("청명", 15), ("곡우", 30), ("입하", 45), ("소만", 60), ("망종", 75), ("하지", 90),
         ("소서", 105), ("대서", 120), ("입추", 135), ("처서", 150), ("백로", 165), ("추분", 180),
         ("한로", 195), ("상강", 210), ("입동", 225), ("소설", 240), ("대설", 255), ("동지", 270)]


def sun_longitude(when):
    """when(aware datetime) → 태양의 겉보기 황경(도)"""
    jd = when.timestamp() / 86400 + 2440587.5
    t = (jd - 2451545.0) / 36525
    l0 = 280.46646 + 36000.76983 * t + 0.0003032 * t * t
    m = math.radians(357.52911 + 35999.05029 * t - 0.0001537 * t * t)
    c = ((1.914602 - 0.004817 * t - 0.000014 * t * t) * math.sin(m)
         + (0.019993 - 0.000101 * t) * math.sin(2 * m) + 0.000289 * math.sin(3 * m))
    omega = math.radians(125.04 - 1934.136 * t)
    return (l0 + c - 0.00569 - 0.00478 * math.sin(omega)) % 360


def _passed(lon_before, lon_after, angle):
    """황경이 angle을 지났는가 (360→0 넘어가는 것 포함)"""
    a = (angle - lon_before) % 360
    return 0 < a <= (lon_after - lon_before) % 360


def solar_terms(year):
    """→ [(이름, date)] 그 해의 24절기 (한국 시간 날짜)"""
    out = []
    day = dt.datetime(year, 1, 1, tzinfo=KST)
    lon = sun_longitude(day)
    names = {angle: name for name, angle in TERMS}
    while day.year == year:
        nxt = day + dt.timedelta(days=1)
        lon_next = sun_longitude(nxt)
        for angle, name in names.items():
            if _passed(lon, lon_next, angle):
                out.append((name, day.date()))
        day, lon = nxt, lon_next
    return out


def today_info(today=None):
    today = today or dt.date.today()  # 화면(브라우저)과 같은 PC 시계 기준 — TV PC는 한국 시간
    terms = solar_terms(today.year - 1) + solar_terms(today.year) + solar_terms(today.year + 1)
    prev = max((t for t in terms if t[1] <= today), key=lambda t: t[1])
    nxt = min((t for t in terms if t[1] > today), key=lambda t: t[1])
    info = {
        "date": today.isoformat(),
        "term_today": prev[0] if prev[1] == today else None,
        "term_prev": {"name": prev[0], "date": prev[1].isoformat()},
        "term_next": {"name": nxt[0], "date": nxt[1].isoformat()},
        "lunar": None,
    }
    try:
        from korean_lunar_calendar import KoreanLunarCalendar
        cal = KoreanLunarCalendar()
        cal.setSolarDate(today.year, today.month, today.day)
        info["lunar"] = {"year": cal.lunarYear, "month": cal.lunarMonth, "day": cal.lunarDay,
                         "leap": bool(cal.isIntercalation), "ganji": cal.getGapJaString().split()[0]}
    except Exception:
        pass
    return info


if __name__ == "__main__":
    import json
    print(json.dumps(today_info(), ensure_ascii=False, indent=1))
