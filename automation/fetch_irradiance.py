#!/usr/bin/env python3
"""어제(KST) 하루치 일사량을 기상청 API허브(천리안2A호 AI 일사량, si_ai)에서 받아
시·군·구별 평균으로 정리해 data/daily-irradiance.json 에 저장한다.

사용법
  python automation/fetch_irradiance.py              # 어제 날짜로 갱신
  python automation/fetch_irradiance.py --date 2026-10-25
  python automation/fetch_irradiance.py --probe      # 1시간치만 받아서 형식을 점검(파일은 쓰지 않음)
  KMA_MOCK=1 python automation/fetch_irradiance.py   # 인증키 없이 가짜 데이터로 동작 점검

인증키는 환경변수 KMA_API_KEY 로만 읽는다(GitHub Secrets). 코드·로그에 출력하지 않는다.
"""
import argparse
import json
import math
import os
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import requests
import shapely
from pyproj import Transformer
from shapely.geometry import shape

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
KST = timezone(timedelta(hours=9))

# 격자 정의: API허브 안내 화면의 기준(경도 126E, 위도 38N, 표준위도 30N/60N, 모서리 ±899km)
# 에서 안내된 네 모서리 좌표를 그대로 재현하는 것을 확인했다.
CRS_LCC = "+proj=lcc +lat_1=30 +lat_2=60 +lat_0=38 +lon_0=126 +ellps=WGS84 +units=m +no_defs"
EDGE = 899000.0

URL = "https://apihub.kma.go.kr/api/typ01/cgi-bin/sat/nph-sat_ana_txt"
MJ_TO_KWH = 1 / 3.6
MAX_HOURLY_MJ = 5.0  # 1시간 누적 일사량의 현실적 상한(이보다 크면 결측으로 본다)


def kst_now():
    return datetime.now(KST)


def fetch_hour_text(tm, key):
    """tm: 'YYYYMMDDHH00'(KST). 응답 본문(text)을 돌려준다."""
    if os.environ.get("KMA_MOCK"):
        return mock_text(tm)
    last = None
    for attempt in range(3):
        try:
            r = requests.get(
                URL,
                params={"tm": tm, "obs": "si_ai", "help": 0, "authKey": key},
                timeout=180,
            )
            if r.status_code == 200 and len(r.text) > 1000:
                return r.text
            last = f"HTTP {r.status_code}, {len(r.text)} bytes, 응답: {r.text[:300].replace(key, '***')}"
        except requests.RequestException as e:  # 키가 URL에 섞여 출력되지 않게 종류만 남긴다
            last = type(e).__name__
        time.sleep(3 * (attempt + 1))
    raise RuntimeError(f"tm={tm} 요청 실패: {last}")


def parse_grid(text):
    """'#'로 시작하는 줄은 설명, 나머지는 위→아래, 왼쪽→오른쪽 순서의 값."""
    nums = []
    for line in text.splitlines():
        s = line.strip()
        if not s or s.startswith("#"):
            continue
        nums.extend(s.replace(",", " ").split())
    arr = np.array(nums, dtype=float)
    n = int(round(math.sqrt(arr.size)))
    if n * n != arr.size:
        raise ValueError(f"값 개수 {arr.size}가 정사각 격자가 아님")
    grid = arr.reshape(n, n)
    grid[(grid < 0) | (grid > MAX_HOURLY_MJ)] = np.nan
    return grid


def build_cell_lonlat(n):
    step = 2 * EDGE / (n - 1)
    xs = -EDGE + step * np.arange(n)
    ys = EDGE - step * np.arange(n)  # 0번 행이 맨 위
    X, Y = np.meshgrid(xs, ys)
    t = Transformer.from_crs(CRS_LCC, "EPSG:4326", always_xy=True)
    lon, lat = t.transform(X, Y)
    return lon, lat


def build_mapping(n):
    """시·군·구별 격자 칸(flat index) 목록을 만든다."""
    lon, lat = build_cell_lonlat(n)
    lon_f, lat_f = lon.ravel(), lat.ravel()
    box = (lon_f > 124) & (lon_f < 132.2) & (lat_f > 32.5) & (lat_f < 39.2)
    idx_box = np.where(box)[0]
    lb, tb = lon_f[idx_box], lat_f[idx_box]
    fc = json.loads((DATA / "sigungu_polygons.json").read_text(encoding="utf-8"))
    mapping = {}
    for f in fc["features"]:
        g = shape(f["geometry"])
        key = (f["properties"]["sido"], f["properties"]["name"])
        minx, miny, maxx, maxy = g.bounds
        sel = np.where((lb >= minx) & (lb <= maxx) & (tb >= miny) & (tb <= maxy))[0]
        inside = sel[shapely.contains_xy(g, lb[sel], tb[sel])] if sel.size else sel
        if inside.size < 3:  # 면적이 작은 곳은 대표점에서 가장 가까운 4칸
            c = g.representative_point()
            d = (lb - c.x) ** 2 + (tb - c.y) ** 2
            inside = np.argsort(d)[:4]
        mapping[key] = idx_box[inside]
    return mapping


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", help="YYYY-MM-DD (KST). 기본값은 어제")
    ap.add_argument("--probe", action="store_true", help="1시간치만 받아 형식 점검")
    args = ap.parse_args()

    key = os.environ.get("KMA_API_KEY", "")
    if not key and not os.environ.get("KMA_MOCK"):
        sys.exit("KMA_API_KEY 가 없습니다 (GitHub Secrets 확인)")

    day = (
        datetime.strptime(args.date, "%Y-%m-%d").replace(tzinfo=KST)
        if args.date
        else (kst_now() - timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    )

    if args.probe:
        tm = (day + timedelta(hours=13)).strftime("%Y%m%d%H00")
        text = fetch_hour_text(tm, key)
        heads = [l for l in text.splitlines() if l.strip().startswith("#")]
        print("tm(KST)=", tm, "| 전체 글자수", len(text), "| 설명줄", len(heads))
        print("\n".join(heads[:30]))
        g = parse_grid(text)
        print("격자", g.shape, "| 유효", int(np.isfinite(g).sum()), "| min/max/mean", np.nanmin(g), np.nanmax(g), np.nanmean(g))
        return

    # 해당 일(KST)의 01시~다음날 00시, 24개 시각(1시간 누적값을 합산)
    tms = [(day + timedelta(hours=h)).strftime("%Y%m%d%H00") for h in range(1, 25)]
    total = None
    n = None
    mapping = None
    korea_idx = None
    missing_day = 0
    from concurrent.futures import ThreadPoolExecutor

    def work(tm):
        try:
            return tm, parse_grid(fetch_hour_text(tm, key)), None
        except Exception as e:
            return tm, None, str(e)[:120]

    with ThreadPoolExecutor(max_workers=4) as ex:
        results = list(ex.map(work, tms))
    for tm, g, err in results:
        hour = int(tm[8:10]) or 24
        if g is None:
            print("누락:", tm, err)
            if 7 <= hour <= 18:
                missing_day += 1
            continue
        if n is None:
            n = g.shape[0]
            total = np.zeros_like(g)
            mapping = build_mapping(n)
            korea_idx = np.unique(np.concatenate(list(mapping.values())))
        # 한반도 남쪽 칸들만 기준으로 유효 비율을 본다(바다·북쪽 결측은 무시)
        valid_ratio = np.isfinite(g.ravel()[korea_idx]).mean()
        if valid_ratio < 0.5:
            print("유효 칸 비율 낮음:", tm, round(float(valid_ratio), 2))
            if 7 <= hour <= 18:
                missing_day += 1
            continue
        total += np.nan_to_num(g, nan=0.0)
    if total is None or missing_day > 3:
        sys.exit(f"낮 시간 자료 누락 {missing_day}건 — 기존 파일을 덮어쓰지 않고 종료합니다")

    daily_kwh = total * MJ_TO_KWH  # kWh/m²(하루 합)
    clim = json.loads((DATA / "irr_clim_sigungu.json").read_text(encoding="utf-8"))
    month = day.month - 1
    flat = daily_kwh.ravel()
    out = {}
    for (sido, name), idx in mapping.items():
        v = float(np.nanmean(flat[idx]))
        c = clim.get(sido, {}).get(name, [None] * 12)[month]
        out.setdefault(sido, {})[name] = {
            "h": round(v, 2),
            "clim": c,
            "ratio": round(v / c, 3) if c else None,
        }
    result = {
        "date": day.strftime("%Y-%m-%d"),
        "updated": kst_now().strftime("%Y-%m-%d %H:%M KST"),
        "unit": "kWh/m2/day (수평면 전일사량 하루 합)",
        "source": "기상청 API허브 천리안2A호 인공지능 기반 일사량(si_ai)",
        "clim_source": "한국에너지기술연구원 신재생자원지도(천리안1호, 2012~2019 월평균)",
        "missing_daytime_hours": missing_day,
        "data": out,
    }
    DATA.mkdir(exist_ok=True)
    (DATA / "daily-irradiance.json").write_text(
        json.dumps(result, ensure_ascii=False, separators=(",", ":")), encoding="utf-8"
    )
    print("저장:", result["date"], "시·군·구", sum(len(v) for v in out.values()), "곳")


# ---------- 인증키 없이 점검하는 가짜 데이터 ----------
def mock_text(tm):
    n = 900
    lon, lat = build_cell_lonlat(n)
    hour = int(tm[8:10]) or 24
    sun = max(0.0, math.sin(math.pi * (hour - 6.5) / 12.0))
    field = (0.9 + 0.1 * np.cos(np.radians((lat - 36) * 12))) * sun * 2.2
    field = np.where((lon < 124.2) | (lon > 131.5) | (lat < 32.5) | (lat > 39.5), -999.0, field)
    rows = [" ".join(f"{v:.3f}" for v in row) for row in field]
    return "# mock\n# grid 900x900\n" + "\n".join(rows)


if __name__ == "__main__":
    main()
