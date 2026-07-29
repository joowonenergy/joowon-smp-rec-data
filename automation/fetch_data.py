"""
주원에너지 SMP·REC 자동 갱신 스크립트
- 매일 GitHub Actions가 이 스크립트를 실행해서 data/smp-rec.json을 자동 업데이트합니다.
- SMP: 공공데이터포털 "한국전력거래소_계통한계가격 및 수요예측(하루전 발전계획용)" API
- REC: 공공데이터포털 "한국전력거래소_REC 현물시장 정보" API
"""

import json
import os
import sys
from datetime import datetime, timedelta, timezone

import requests

# ── 설정 ──────────────────────────────────────────────
SERVICE_KEY = os.environ.get("DATA_GO_KR_KEY", "")
JSON_PATH = "data/smp-rec.json"
KEEP_DAYS = 90  # JSON에 최근 며칠치까지만 보관할지 (너무 커지지 않게)

SMP_URL = "https://apis.data.go.kr/B552115/SmpWithForecastDemand/getSmpWithForecastDemand"
REC_URL = "https://apis.data.go.kr/B552115/RecMarketInfo2/getRecMarketInfo2"

KST = timezone(timedelta(hours=9))


def today_kst_str():
    """오늘 날짜(KST 기준)를 YYYYMMDD 문자열로 반환"""
    return datetime.now(KST).strftime("%Y%m%d")


def today_kst_dashed():
    """오늘 날짜(KST 기준)를 YYYY-MM-DD 문자열로 반환"""
    return datetime.now(KST).strftime("%Y-%m-%d")


def fetch_smp(date_str):
    """해당 날짜의 육지/제주 SMP 24시간 평균값을 반환. 실패 시 (None, None)"""
    params = {
        "serviceKey": SERVICE_KEY,
        "pageNo": 1,
        "numOfRows": 48,  # 24시간 x 2지역
        "dataType": "json",
        "date": date_str,
    }
    try:
        res = requests.get(SMP_URL, params=params, timeout=15)
        res.raise_for_status()
        data = res.json()
        result_code = data["response"]["header"]["resultCode"]
        if result_code != "00":
            print(f"[SMP] API 오류: {data['response']['header']['resultMsg']}")
            return None, None

        items = data["response"]["body"]["items"]["item"]

        land_values = [float(i["smp"]) for i in items if i["areaName"] == "육지"]
        jeju_values = [float(i["smp"]) for i in items if i["areaName"] == "제주"]

        if not land_values or not jeju_values:
            print("[SMP] 육지 또는 제주 데이터가 비어있음")
            return None, None

        smp_land = round(sum(land_values) / len(land_values), 2)
        smp_jeju = round(sum(jeju_values) / len(jeju_values), 2)
        return smp_land, smp_jeju

    except Exception as e:
        print(f"[SMP] 요청 실패: {e}")
        return None, None


def fetch_rec(date_str):
    """해당 날짜의 REC 종가(clsPrc)를 반환. 거래일이 아니면 None"""
    params = {
        "serviceKey": SERVICE_KEY,
        "pageNo": 1,
        "numOfRows": 30,
        "dataType": "json",
        "bzDd": date_str,
    }
    try:
        res = requests.get(REC_URL, params=params, timeout=15)
        res.raise_for_status()
        data = res.json()
        result_code = data["response"]["header"]["resultCode"]
        if result_code != "00":
            print(f"[REC] API 오류(비거래일일 수 있음): {data['response']['header']['resultMsg']}")
            return None

        body = data["response"]["body"]
        if int(body.get("totalCount", 0)) == 0:
            print("[REC] 오늘은 거래일이 아님 (데이터 없음)")
            return None

        items = body["items"]["item"]
        item = items[0] if isinstance(items, list) else items
        return float(item["clsPrc"])

    except Exception as e:
        print(f"[REC] 요청 실패: {e}")
        return None


def load_existing_data():
    if not os.path.exists(JSON_PATH):
        return []
    with open(JSON_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def save_data(records):
    # 최신순으로 정렬 후, 오래된 데이터 정리
    records.sort(key=lambda r: r["date"], reverse=True)
    records = records[:KEEP_DAYS]
    os.makedirs(os.path.dirname(JSON_PATH), exist_ok=True)
    with open(JSON_PATH, "w", encoding="utf-8") as f:
        json.dump(records, f, ensure_ascii=False, indent=2)


def main():
    if not SERVICE_KEY:
        print("ERROR: DATA_GO_KR_KEY 환경변수(시크릿)가 설정되지 않았습니다.")
        sys.exit(1)

    date_compact = today_kst_str()      # 예: 20260729
    date_dashed = today_kst_dashed()    # 예: 2026-07-29

    print(f"=== {date_dashed} 데이터 수집 시작 ===")

    smp_land, smp_jeju = fetch_smp(date_compact)
    rec_price = fetch_rec(date_compact)

    records = load_existing_data()

    # SMP를 못 가져온 경우: 전날 값으로라도 채워서 위젯이 깨지지 않게 함
    if smp_land is None or smp_jeju is None:
        if records:
            print("SMP 조회 실패 → 직전 값 유지")
            smp_land = records[0]["smp_land"]
            smp_jeju = records[0]["smp_jeju"]
        else:
            print("SMP 조회 실패 & 기존 데이터도 없음 → 종료")
            sys.exit(1)

    # REC 비거래일이면: 마지막 거래일 종가를 그대로 이어서 사용
    if rec_price is None:
        if records:
            print("REC 비거래일 → 직전 거래가 유지")
            rec_price = records[0]["rec"]
        else:
            print("REC 데이터 없음 & 기존 데이터도 없음 → 0으로 처리")
            rec_price = 0

    new_record = {
        "date": date_dashed,
        "smp_land": smp_land,
        "smp_jeju": smp_jeju,
        "rec": rec_price,
    }

    # 오늘자 레코드가 이미 있으면 교체, 없으면 추가
    records = [r for r in records if r["date"] != date_dashed]
    records.append(new_record)

    save_data(records)
    print(f"저장 완료: {new_record}")


if __name__ == "__main__":
    main()
