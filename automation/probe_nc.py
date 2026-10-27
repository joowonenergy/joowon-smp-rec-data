#!/usr/bin/env python3
"""NetCDF(이진) 방식과 기존 텍스트 방식의 받는 속도·값을 비교하는 점검용 스크립트.
같은 시각(KST)의 파일을 두 방식으로 받아 걸린 시간, 용량, 변수 이름, 값 차이를 출력한다.
인증키는 환경변수 KMA_API_KEY 로만 읽고 출력하지 않는다."""
import os
import sys
import time
from datetime import datetime, timedelta

import numpy as np
import requests

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fetch_irradiance as F  # noqa: E402

NC_URL = "https://apihub.kma.go.kr/api/typ01/url/sat_file_down2.php"


def mask(s, key):
    return str(s).replace(key, "***")


def main():
    key = os.environ.get("KMA_API_KEY", "")
    if not key:
        sys.exit("KMA_API_KEY 가 없습니다")
    day = datetime.strptime(os.environ.get("PROBE_DATE", "2024-10-02"), "%Y-%m-%d")
    for h in (10, 13, 16):
        kst = day + timedelta(hours=h)
        tm_kst = kst.strftime("%Y%m%d%H00")
        tm_utc = (kst - timedelta(hours=9)).strftime("%Y%m%d%H00")
        print(f"\n== KST {tm_kst} / UTC {tm_utc}")
        t0 = time.time()
        try:
            g_txt = F.parse_grid(F.fetch_hour_text(tm_kst, key))
            print(f"텍스트: {time.time() - t0:.1f}초, 격자 {g_txt.shape}, 평균 {np.nanmean(g_txt):.3f} MJ/m2")
        except Exception as e:
            print("텍스트 실패:", mask(e, key)[:200])
            g_txt = None
        t0 = time.time()
        try:
            r = requests.get(NC_URL, params={"lvl": "l2", "dat": "ai-dsr", "are": "ko", "tm": tm_utc, "typ": "bin", "authKey": key}, timeout=180)
            dt = time.time() - t0
            print(f"NetCDF: {dt:.1f}초, HTTP {r.status_code}, {len(r.content):,} bytes, 앞 8바이트 {r.content[:8]!r}")
            if r.status_code != 200 or len(r.content) < 1000:
                print("응답:", mask(r.text[:300], key))
                continue
            path = f"/tmp/probe_{tm_utc}.nc"
            open(path, "wb").write(r.content)
            import netCDF4

            ds = netCDF4.Dataset(path)
            print("차원:", {k: len(v) for k, v in ds.dimensions.items()})
            for k, v in ds.variables.items():
                print("  변수", k, v.shape, getattr(v, "units", ""), getattr(v, "long_name", ""))
            print("전역 속성(일부):", {k: str(ds.getncattr(k))[:60] for k in list(ds.ncattrs())[:12]})
            name = next((k for k in ds.variables if k.upper().startswith("DSR")), None)
            if name:
                a = np.ma.filled(ds.variables[name][:].astype(float), np.nan)
                print(f"{name}: 형태 {a.shape}, 평균 {np.nanmean(a):.3f}, 최대 {np.nanmax(a):.3f}")
                if g_txt is not None and a.shape == g_txt.shape:
                    m = np.isfinite(a) & np.isfinite(g_txt)
                    print("텍스트와 상관계수:", round(float(np.corrcoef(a[m], g_txt[m])[0, 1]), 4), "| 비율(평균)", round(float(np.nanmean(a[m]) / np.nanmean(g_txt[m])), 4))
        except Exception as e:
            print("NetCDF 실패:", mask(type(e).__name__ + " " + str(e), key)[:300])


if __name__ == "__main__":
    main()
