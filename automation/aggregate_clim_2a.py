#!/usr/bin/env python3
"""data/backfill-2a.json 의 표본 날짜들로 월별 평균(새 평년 후보)을 만든다.
결과: data/irr_clim_2a.json, 그리고 기존 평년(천리안1호, 2012~2019)과의 비율을 로그로 출력한다.
"""
import json
import statistics
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def main():
    bf = json.loads((ROOT / "data/backfill-2a.json").read_text(encoding="utf-8"))
    old = json.loads((ROOT / "data/irr_clim_sigungu.json").read_text(encoding="utf-8"))
    keys = bf["keys"]
    by_month = {m: [] for m in range(1, 13)}
    for ds, arr in bf["days"].items():
        by_month[int(ds[5:7])].append(arr)
    monthly, counts, ratios = {}, {}, {}
    for m, rows in by_month.items():
        counts[m] = len(rows)
        if not rows:
            continue
        monthly[m] = [round(sum(r[i] for r in rows) / len(rows), 3) for i in range(len(keys))]
        rs = []
        for i, k in enumerate(keys):
            s, c = k.split("|")
            o = old.get(s, {}).get(c)
            if o and o[m - 1]:
                rs.append(monthly[m][i] / o[m - 1])
        ratios[m] = round(statistics.median(rs), 3) if rs else None
    out = {
        "unit": "kWh/m2/day (수평면, 월별 표본 평균)",
        "source": bf["source"],
        "period": [min(bf["days"]), max(bf["days"])],
        "n_days": counts,
        "keys": keys,
        "monthly": {str(m): v for m, v in monthly.items()},
    }
    (ROOT / "data/irr_clim_2a.json").write_text(json.dumps(out, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print("표본 일수(월별):", counts)
    print("새 평년 후보 ÷ 기존 평년(전국 중앙값):", ratios)


if __name__ == "__main__":
    main()
