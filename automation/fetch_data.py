"""
주원에너지 SMP·REC 자동 갱신 스크립트
- 매일 GitHub Actions가 이 스크립트를 실행해서 data/smp-rec.json을 자동 업데이트합니다.
- SMP: 공공데이터포털 "한국전력거래소_계통한계가격 및 수요예측(하루전 발전계획용)" API
- REC: 공공데이터포털 "한국전력거래소_REC 현물시장 정보" API
- 추가: 카드 디자인이 적용된 docs/index.html도 같이 생성 (GitHub Pages 공개용)
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
    return records


def generate_html(records):
    """카드 디자인이 적용된 정적 HTML 페이지를 docs/index.html로 생성"""
    records_json = json.dumps(records[:30], ensure_ascii=False)

    html = """<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>SMP·REC 현황</title>
<style>
  body { margin:0; font-family:'Pretendard',sans-serif; }
  #jwHero { position:relative; background:#F7FAFD; overflow:hidden; min-height:832px; }
  .jw-bg-svg { position:absolute; top:0; left:0; display:block; width:100%; height:100%; }
  .jw-header { position:relative; padding:90px 56px 0; text-align:center; }
  .jw-eyebrow { font-size:20px; color:#0F6E56; font-weight:700; margin-bottom:16px; }
  .jw-title { font-size:clamp(48px,6vw,68px); font-weight:800; color:#132E80; margin-bottom:20px; }
  .jw-date { display:inline-flex; align-items:center; gap:8px; font-size:20px; color:#1F2937; font-weight:700; margin-bottom:36px; }
  .jw-dot { width:8px; height:8px; border-radius:50%; background:#34B686; display:inline-block; }
  .jw-controls { display:flex; justify-content:center; gap:14px; margin-bottom:56px; }
  .jw-select { background:#fff; border:1px solid #9CA3AF; border-radius:10px; padding:14px 20px; font-size:18px; font-weight:700; color:#132E80; cursor:pointer; }
  .jw-cards { position:relative; display:grid; grid-template-columns:repeat(3,1fr); gap:24px; padding:0 56px 90px; max-width:1240px; margin:0 auto; }
  .jw-card { background:#fff; border:1px solid #9CA3AF; border-radius:16px; padding:36px; }
  .jw-card-top { display:flex; justify-content:space-between; align-items:baseline; margin-bottom:18px; font-size:19px; font-weight:700; color:#1F2937; }
  .jw-card-date { font-size:15px; font-weight:400; color:#6B7280; }
  .jw-card-value { font-size:42px; font-weight:800; color:#132E80; }
  .jw-unit { font-size:20px; font-weight:400; color:#6B7280; }
  .jw-delta { font-size:18px; font-weight:700; color:#B94A1F; margin-top:14px; }
  .jw-card-highlight { background:#EAF9F1; border:3px solid #34B686; }
  .jw-highlight-label { font-size:22px; font-weight:800; color:#0F6E56; margin-bottom:18px; }
  .jw-highlight-value { color:#0F6E56; font-size:46px; }
  .jw-highlight-unit { color:#0F6E56; }
  .jw-highlight-note { font-size:16px; font-weight:600; color:#0F6E56; margin-top:14px; }
</style>
</head>
<body>
<div id="jwHero">
  <svg width="100%" height="100%" viewBox="0 0 1200 832" preserveAspectRatio="none" class="jw-bg-svg">
    <defs>
      <radialGradient id="jwGlow1" cx="15%" cy="5%" r="55%">
        <stop offset="0%" stop-color="#34B686" stop-opacity="0.14"/>
        <stop offset="100%" stop-color="#34B686" stop-opacity="0"/>
      </radialGradient>
      <radialGradient id="jwGlow2" cx="90%" cy="95%" r="55%">
        <stop offset="0%" stop-color="#132E80" stop-opacity="0.09"/>
        <stop offset="100%" stop-color="#132E80" stop-opacity="0"/>
      </radialGradient>
    </defs>
    <rect x="0" y="0" width="1200" height="832" fill="url(#jwGlow1)"/>
    <rect x="0" y="0" width="1200" height="832" fill="url(#jwGlow2)"/>
    <g stroke="#132E80" stroke-opacity="0.12">
      <line x1="80" y1="0" x2="80" y2="832"/><line x1="200" y1="0" x2="200" y2="832"/><line x1="320" y1="0" x2="320" y2="832"/><line x1="440" y1="0" x2="440" y2="832"/><line x1="560" y1="0" x2="560" y2="832"/><line x1="680" y1="0" x2="680" y2="832"/><line x1="800" y1="0" x2="800" y2="832"/><line x1="920" y1="0" x2="920" y2="832"/><line x1="1040" y1="0" x2="1040" y2="832"/><line x1="1160" y1="0" x2="1160" y2="832"/>
    </g>
    <g stroke="#132E80" stroke-opacity="0.08">
      <line x1="0" y1="90" x2="1200" y2="90"/><line x1="0" y1="210" x2="1200" y2="210"/><line x1="0" y1="330" x2="1200" y2="330"/><line x1="0" y1="450" x2="1200" y2="450"/><line x1="0" y1="570" x2="1200" y2="570"/><line x1="0" y1="690" x2="1200" y2="690"/><line x1="0" y1="800" x2="1200" y2="800"/>
    </g>
    <path id="jwP1" d="M 0 140 Q 300 40 600 100 T 1200 60" fill="none" stroke="#34B686" stroke-width="2" stroke-opacity="0.35"/>
    <path id="jwP2" d="M 0 390 Q 300 300 600 360 T 1200 320" fill="none" stroke="#132E80" stroke-width="1.5" stroke-opacity="0.2"/>
    <path id="jwP3" d="M 0 610 Q 300 530 600 580 T 1200 550" fill="none" stroke="#34B686" stroke-width="1.5" stroke-opacity="0.25"/>
    <rect x="-7" y="-7" width="14" height="14" fill="#34B686" fill-opacity="0.5"><animateMotion dur="10s" repeatCount="indefinite"><mpath href="#jwP1"/></animateMotion></rect>
    <rect x="-6" y="-6" width="12" height="12" fill="#132E80" fill-opacity="0.35"><animateMotion dur="13s" repeatCount="indefinite" begin="-3s"><mpath href="#jwP1"/></animateMotion></rect>
    <rect x="-6" y="-6" width="12" height="12" fill="#132E80" fill-opacity="0.35"><animateMotion dur="11s" repeatCount="indefinite"><mpath href="#jwP2"/></animateMotion></rect>
    <rect x="-7" y="-7" width="14" height="14" fill="#34B686" fill-opacity="0.45"><animateMotion dur="14s" repeatCount="indefinite" begin="-5s"><mpath href="#jwP2"/></animateMotion></rect>
    <rect x="-6" y="-6" width="12" height="12" fill="#34B686" fill-opacity="0.45"><animateMotion dur="12s" repeatCount="indefinite"><mpath href="#jwP3"/></animateMotion></rect>
    <rect x="-7" y="-7" width="14" height="14" fill="#132E80" fill-opacity="0.3"><animateMotion dur="9s" repeatCount="indefinite" begin="-2s"><mpath href="#jwP3"/></animateMotion></rect>
  </svg>
  <div class="jw-header">
    <div class="jw-eyebrow">실시간 태양광 시장 정보</div>
    <div class="jw-title">SMP·REC 현황</div>
    <div class="jw-date">
      <span class="jw-dot"></span>
      <span id="jwDateLabel">-</span> (매일 자동 갱신)
    </div>
    <div class="jw-controls">
      <select id="jwRecWeight" class="jw-select">
        <option value="0.8">REC 가중치 0.8</option>
        <option value="1.0">REC 가중치 1.0</option>
        <option value="1.2" selected>REC 가중치 1.2</option>
        <option value="1.5">REC 가중치 1.5</option>
      </select>
      <select id="jwRegion" class="jw-select">
        <option value="land">육지</option>
        <option value="jeju" selected>제주</option>
      </select>
    </div>
  </div>
  <div class="jw-cards">
    <div class="jw-card">
      <div class="jw-card-top"><span id="jwSmpLabel">SMP</span><span id="jwSmpDate" class="jw-card-date"></span></div>
      <div class="jw-card-value"><span id="jwSmpValue">-</span><span class="jw-unit"> 원/kWh</span></div>
      <div id="jwSmpDelta" class="jw-delta"></div>
    </div>
    <div class="jw-card">
      <div class="jw-card-top"><span>REC</span><span id="jwRecDate" class="jw-card-date"></span></div>
      <div class="jw-card-value"><span id="jwRecValue">-</span><span class="jw-unit"> 원/REC</span></div>
      <div id="jwRecDelta" class="jw-delta"></div>
    </div>
    <div class="jw-card jw-card-highlight">
      <div class="jw-highlight-label">1kW당 예상 수익</div>
      <div class="jw-card-value jw-highlight-value"><span id="jwSmpPlusValue">-</span><span class="jw-unit jw-highlight-unit"> 원/kWh</span></div>
      <div id="jwSmpPlusNote" class="jw-highlight-note"></div>
    </div>
  </div>
</div>
<script>
var jwData = REPLACE_WITH_JSON;

function jwUpdateValues() {
  if (!jwData || jwData.length === 0) return;
  var today = jwData[0];
  var yesterday = jwData[1] || today;
  var weight = parseFloat(document.getElementById('jwRecWeight').value);
  var region = document.getElementById('jwRegion').value;
  var regionLabel = region === 'jeju' ? '제주' : '육지';

  var smpToday = Number(region === 'jeju' ? today.smp_jeju : today.smp_land) || 0;
  var smpYesterday = Number(region === 'jeju' ? yesterday.smp_jeju : yesterday.smp_land) || 0;
  var recToday = Number(today.rec) || 0;
  var recYesterday = Number(yesterday.rec) || 0;

  var smpDelta = smpToday - smpYesterday;
  var recDelta = recToday - recYesterday;
  var smpPlus = smpToday + (recToday * weight) / 1000;

  document.getElementById('jwDateLabel').textContent = today.date + ' 기준';
  document.getElementById('jwSmpLabel').textContent = 'SMP (' + regionLabel + ')';
  document.getElementById('jwSmpDate').textContent = today.date;
  document.getElementById('jwSmpValue').textContent = smpToday.toFixed(2);
  document.getElementById('jwSmpDelta').innerHTML = (smpDelta >= 0 ? '▲ ' : '▼ ') + Math.abs(smpDelta).toFixed(2) + ' (전일대비)';

  document.getElementById('jwRecDate').textContent = today.date;
  document.getElementById('jwRecValue').textContent = recToday.toLocaleString();
  document.getElementById('jwRecDelta').innerHTML = (recDelta >= 0 ? '▲ ' : '▼ ') + Math.abs(recDelta).toLocaleString() + ' (전일대비)';

  document.getElementById('jwSmpPlusValue').textContent = smpPlus.toFixed(2);
  document.getElementById('jwSmpPlusNote').textContent = 'SMP + REC×' + weight.toFixed(1) + ' 가중치 반영';
}

document.getElementById('jwRecWeight').addEventListener('change', jwUpdateValues);
document.getElementById('jwRegion').addEventListener('change', jwUpdateValues);
jwUpdateValues();
</script>
</body>
</html>"""

    html = html.replace("REPLACE_WITH_JSON", records_json)

    os.makedirs("docs", exist_ok=True)
    with open("docs/index.html", "w", encoding="utf-8") as f:
        f.write(html)
    print("docs/index.html 생성 완료")


def main():
    if not SERVICE_KEY:
        print("ERROR: DATA_GO_KR_KEY 환경변수(시크릿)가 설정되지 않았습니다.")
        sys.exit(1)

    date_compact = today_kst_str()  # 예: 20260729
    date_dashed = today_kst_dashed()  # 예: 2026-07-29

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

    records = save_data(records)
    generate_html(records)

    print(f"저장 완료: {new_record}")


if __name__ == "__main__":
    main()
