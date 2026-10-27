#!/usr/bin/env python3
"""data/irr_clim_sigungu.json(수평면 월평균 일사량)에서 남향 경사면(10/20/30도) 값을 계산해
docs/irr_sigungu.json 으로 저장한다. 계산기(docs/joowon-solar-calc.html)가 이 파일을 읽는다.
방법: Liu-Jordan 등방성 모델 + Erbs 산란비(월평균), 지면 반사율 0.2.
"""
import json
import math
from pathlib import Path

from shapely.geometry import shape

ROOT = Path(__file__).resolve().parent.parent
NDAY = [17, 47, 75, 105, 135, 162, 198, 228, 258, 288, 318, 344]


def tilt_series(phi_deg, h12, beta_deg, rho=0.2):
    out = []
    phi = math.radians(phi_deg)
    beta = math.radians(beta_deg)
    for n, h in zip(NDAY, h12):
        dec = math.radians(23.45 * math.sin(math.radians(360 * (284 + n) / 365)))
        ws = math.acos(max(-1, min(1, -math.tan(phi) * math.tan(dec))))
        e0 = 1 + 0.033 * math.cos(math.radians(360 * n / 365))
        h0 = (
            24 * 3600 * 1367 / math.pi * e0
            * (math.cos(phi) * math.cos(dec) * math.sin(ws) + ws * math.sin(phi) * math.sin(dec))
            / 3.6e6
        )
        kt = min(max(h / h0, 0.05), 0.85)
        if math.degrees(ws) <= 81.4:
            fd = 1.391 - 3.560 * kt + 4.189 * kt**2 - 2.137 * kt**3
        else:
            fd = 1.311 - 3.022 * kt + 3.427 * kt**2 - 1.821 * kt**3
        fd = min(max(fd, 0.1), 1.0)
        wsp = min(ws, math.acos(max(-1, min(1, -math.tan(phi - beta) * math.tan(dec)))))
        rb = (
            math.cos(phi - beta) * math.cos(dec) * math.sin(wsp) + wsp * math.sin(phi - beta) * math.sin(dec)
        ) / (math.cos(phi) * math.cos(dec) * math.sin(ws) + ws * math.sin(phi) * math.sin(dec))
        r = (1 - fd) * rb + fd * (1 + math.cos(beta)) / 2 + rho * (1 - math.cos(beta)) / 2
        out.append(round(h * r, 3))
    return out


def main():
    clim = json.loads((ROOT / "data/irr_clim_sigungu.json").read_text(encoding="utf-8"))
    fc = json.loads((ROOT / "data/sigungu_polygons.json").read_text(encoding="utf-8"))
    lat = {(f["properties"]["sido"], f["properties"]["name"]): shape(f["geometry"]).centroid.y for f in fc["features"]}
    out = {}
    for sido, cities in clim.items():
        for city, h in cities.items():
            phi = lat[(sido, city)]
            out.setdefault(sido, {})[city] = {
                "H": h,
                "t10": tilt_series(phi, h, 10),
                "t20": tilt_series(phi, h, 20),
                "t30": tilt_series(phi, h, 30),
            }
    dst = ROOT / "docs" / "irr_sigungu.json"
    dst.parent.mkdir(exist_ok=True)
    dst.write_text(json.dumps(out, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print("저장:", dst.name, sum(len(v) for v in out.values()), "곳")


if __name__ == "__main__":
    main()
