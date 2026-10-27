#!/usr/bin/env python3
"""과거 날짜(표본)의 하루 일사량을 시·군·구별로 받아 data/backfill-2a.json 에 쌓는다.

예) python automation/backfill_irradiance.py --start 2020-01-01 --end 2020-12-31 --step 5
- 하루 합계 = 해가 떠 있는 시간대의 1시간 누적값(MJ/㎡)을 합산한 뒤 kWh/㎡로 환산
- 이미 받은 날짜는 건너뛰고(이어 받기), --max-minutes 가 지나면 저장하고 멈춘다
- 인증키는 환경변수 KMA_API_KEY 로만 읽는다
"""
import argparse
import json
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fetch_irradiance as F  # noqa: E402


def hours_for(month):
    """해가 떠 있는 시간대(KST, 1시간 누적값의 끝 시각)."""
    if month in (11, 12, 1, 2):
        return range(7, 19)
    if month in (3, 4, 9, 10):
        return range(6, 20)
    return range(5, 22)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", required=True)
    ap.add_argument("--end", required=True)
    ap.add_argument("--step", type=int, default=5)
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--max-minutes", type=float, default=300)
    args = ap.parse_args()

    key = os.environ.get("KMA_API_KEY", "")
    if not key and not os.environ.get("KMA_MOCK"):
        sys.exit("KMA_API_KEY 가 없습니다")

    t0 = time.time()
    path = F.DATA / "backfill-2a.json"
    hist = {"unit": "kWh/m2/day (수평면 전일사량 하루 합, 표본 날짜)", "source": "기상청 API허브 천리안2A호 인공지능 기반 일사량(si_ai)", "keys": None, "days": {}}
    if path.exists():
        hist = json.loads(path.read_text(encoding="utf-8"))

    d = datetime.strptime(args.start, "%Y-%m-%d")
    d_end = datetime.strptime(args.end, "%Y-%m-%d")
    days = []
    while d <= d_end:
        days.append(d)
        d += timedelta(days=args.step)
    todo = [x for x in days if x.strftime("%Y-%m-%d") not in hist["days"]]
    print(f"대상 {len(days)}일 중 새로 받을 날 {len(todo)}일 (이미 {len(hist['days'])}일 기록됨)")

    mapping = None
    keys = None
    n_ok = n_skip = n_files = 0
    for day in todo:
        if (time.time() - t0) / 60 > args.max_minutes:
            print("시간 한도에 도달 — 여기까지 저장하고 멈춥니다")
            break
        ds = day.strftime("%Y-%m-%d")
        tms = [(day + timedelta(hours=h)).strftime("%Y%m%d%H00") for h in hours_for(day.month)]

        def work(tm):
            try:
                return tm, F.parse_grid(F.fetch_hour_text(tm, key)), None
            except Exception as e:  # 키는 메시지에 섞이지 않는다
                return tm, None, str(e)[:100]

        with ThreadPoolExecutor(max_workers=args.workers) as ex:
            results = list(ex.map(work, tms))
        n_files += len(results)
        ok = [g for _, g, _ in results if g is not None]
        miss = len(results) - len(ok)
        if not ok or miss > 2:
            n_skip += 1
            errs = {e for _, g, e in results if e}
            print("건너뜀", ds, "누락", miss, "/", len(results), "|", list(errs)[:1])
            continue
        total = np.zeros_like(ok[0])
        for g in ok:
            total += np.nan_to_num(g, nan=0.0)
        if mapping is None:
            mapping = F.build_mapping(total.shape[0])
            keys = sorted(f"{s}|{c}" for (s, c) in mapping)
        flat = (total * F.MJ_TO_KWH).ravel()
        hist["days"][ds] = [round(float(np.nanmean(flat[mapping[tuple(k.split("|"))]])), 2) for k in keys]
        hist["keys"] = keys
        n_ok += 1
        path.write_text(json.dumps(hist, ensure_ascii=False, separators=(",", ":"), sort_keys=True), encoding="utf-8")
        mins = (time.time() - t0) / 60
        print(f"{ds} 저장 (누락 {miss}) | 누적 {len(hist['days'])}일 | 경과 {mins:.1f}분 | 파일 {n_files}개")

    mins = (time.time() - t0) / 60
    print(f"완료: 성공 {n_ok}일, 건너뜀 {n_skip}일, 받은 파일 {n_files}개, {mins:.1f}분, 파일당 평균 {mins * 60 / max(n_files, 1):.1f}초")


if __name__ == "__main__":
    main()
