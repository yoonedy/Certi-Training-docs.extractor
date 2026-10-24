"""한국 시·도 GeoJSON → 1920x1080 무대 좌표의 SVG path 데이터(static/korea-map.js) 생성.

원본: southkorea/southkorea-maps (kostat 2013, simple). 지도를 다시 그릴 일이 없으면 실행할 필요 없음.
    python tools/build_map.py
"""
import json
import math
from pathlib import Path

from shapely.geometry import shape, mapping
from shapely.ops import unary_union

HERE = Path(__file__).resolve().parent
SRC = HERE / "skorea_provinces_geo_simple.json"
OUT = HERE.parent / "static" / "korea-map.js"

# 본토 투영 (equirectangular, 위도 36° 보정) — 1920x1080 무대 기준
# 하단 메모 칸 자리를 위해 위로 올림 (북쪽 끝은 상단 바에 살짝 가려짐)
LAT0 = 36.0
K = 190.0                      # px / 위도 1°
KX = K * math.cos(math.radians(LAT0))
LON_MIN, LAT_MAX = 126.05, 38.62
X0, Y0 = 668.0, 40.0
# 제주는 좌하단 인셋 박스로 옮김
JEJU = {"lon": 126.15, "lat": 33.57, "x": 476.0, "y": 950.0}


def proj(lon, lat):
    return X0 + (lon - LON_MIN) * KX, Y0 + (LAT_MAX - lat) * K


def proj_jeju(lon, lat):
    return JEJU["x"] + (lon - JEJU["lon"]) * KX, JEJU["y"] + (JEJU["lat"] - lat) * K


def ring_d(ring, fn):
    pts = [fn(x, y) for x, y in ring]
    return "M" + "L".join(f"{x:.1f},{y:.1f}" for x, y in pts) + "Z"


def geom_d(geom, fn, min_area=0.0):
    polys = [geom] if geom.geom_type == "Polygon" else list(geom.geoms)
    out = []
    for p in polys:
        if p.area < min_area:
            continue
        out.append(ring_d(p.exterior.coords, fn))
    return "".join(out)


def main():
    fc = json.loads(SRC.read_text(encoding="utf-8"))
    provinces = []
    mainland_geoms = []
    jeju_d = ""
    for f in fc["features"]:
        code = f["properties"]["code"]
        g = shape(f["geometry"]).buffer(0)
        if code == "39":
            jeju_d = geom_d(g.simplify(0.003), proj_jeju, 1e-4)
            continue
        # 울릉도·독도(동경 130° 이상)는 인셋으로 따로 표시
        g = g.difference(shape({"type": "Polygon", "coordinates": [[[130, 30], [133, 30], [133, 40], [130, 40], [130, 30]]]}))
        provinces.append({"code": code, "name": f["properties"]["name"],
                          "d": geom_d(g.simplify(0.002), proj, 2e-5)})
        mainland_geoms.append(g)

    # 자동차 경로: 본토 외곽선을 바깥으로 살짝 띄우고 매끈하게
    land = unary_union(mainland_geoms).buffer(0.02)
    main_poly = max(land.geoms, key=lambda p: p.area) if land.geom_type == "MultiPolygon" else land
    route = main_poly.buffer(0.16, join_style=1).buffer(-0.04).simplify(0.03)
    if route.geom_type == "MultiPolygon":
        route = max(route.geoms, key=lambda p: p.area)
    route_d = ring_d(route.exterior.coords, proj)

    data = {
        "projection": {"lat0": LAT0, "k": K, "kx": KX, "lonMin": LON_MIN, "latMax": LAT_MAX, "x0": X0, "y0": Y0},
        "provinces": provinces,
        "jeju": jeju_d,
        "carRoute": route_d,
    }
    OUT.write_text("// 자동 생성: tools/build_map.py\nwindow.KOREA_MAP = " + json.dumps(data, ensure_ascii=False) + ";\n",
                   encoding="utf-8")
    print(f"wrote {OUT} ({OUT.stat().st_size // 1024} KB)")


if __name__ == "__main__":
    main()
