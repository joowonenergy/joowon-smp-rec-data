"""
주원에너지 SMP·REC 자동 갱신 스크립트
- 매일 GitHub Actions가 이 스크립트를 실행해서 data/smp-rec.json을 자동 업데이트합니다.
- docs/index.html: 히어로 카드 페이지 (GitHub Pages)
- docs/trend.html: 최근 30일 추이 그래프 페이지 (GitHub Pages)

* 2026-07-30: API가 육지/제주 SMP를 동일한 값으로 잘못 제공하는 문제를 확인.
  주원에너지 사업장은 전부 육지(경남 김해) 소재이므로, 육지 기준 SMP 단일값만
  사용하도록 구조를 단순화함 (KPX 공식 사이트 대조 검증 완료, 육지 값 자체는 정확함).
* 2026-08-25: REC는 매주 화·목요일에만 고시되므로, REC 카드의 "전일대비" 증감 표시를
  제거하고 정적 안내 문구로 대체. 카드 디자인을 아이콘+컬러 상단바 스타일로 리뉴얼.
"""

import json
import os
import sys
from datetime import datetime, timedelta, timezone

import requests

SERVICE_KEY = os.environ.get("DATA_GO_KR_KEY", "")
JSON_PATH = "data/smp-rec.json"
KEEP_DAYS = 90
REC_WEIGHT = 1.2  # 화면에 고정 표기되는 REC 가중치

SMP_URL = "https://apis.data.go.kr/B552115/SmpWithForecastDemand/getSmpWithForecastDemand"
REC_URL = "https://apis.data.go.kr/B552115/RecMarketInfo2/getRecMarketInfo2"

KST = timezone(timedelta(hours=9))


def today_kst_str():
    return datetime.now(KST).strftime("%Y%m%d")


def today_kst_dashed():
    return datetime.now(KST).strftime("%Y-%m-%d")


def fetch_smp(date_str):
    """육지 기준 SMP 단일값을 반환한다 (주원에너지 사업장이 전부 육지 소재이므로)."""
    params = {
        "serviceKey": SERVICE_KEY,
        "pageNo": 1,
        "numOfRows": 48,
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
            return None
        items = data["response"]["body"]["items"]["item"]
        land_values = [float(i["smp"]) for i in items if i["areaName"] == "육지"]
        if not land_values:
            print("[SMP] 육지 데이터가 비어있음")
            return None
        smp = round(sum(land_values) / len(land_values), 2)
        return smp
    except Exception as e:
        print(f"[SMP] 요청 실패: {e}")
        return None


def fetch_rec(date_str):
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
    records.sort(key=lambda r: r["date"], reverse=True)
    records = records[:KEEP_DAYS]
    os.makedirs(os.path.dirname(JSON_PATH), exist_ok=True)
    with open(JSON_PATH, "w", encoding="utf-8") as f:
        json.dump(records, f, ensure_ascii=False, indent=2)
    return records


def get_smp(record):
    """신규 'smp' 필드와, 이전 스키마의 'smp_land' 필드 모두 호환 처리."""
    if record.get("smp") is not None:
        return record["smp"]
    return record.get("smp_land")


def generate_html(records):
    """히어로 카드 페이지 (docs/index.html) — 아이콘+컬러 상단바 카드 스타일"""
    records_json = json.dumps(records[:30], ensure_ascii=False)

    html = """<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>SMP·REC 현황</title>
<style>
  * { box-sizing: border-box; }
  body { margin:0; font-family:'Pretendard',sans-serif; background:#ffffff; }
  .jw-widget { max-width:1120px; margin:0 auto; padding:60px 24px; text-align:center; }
  .jw-accent { width:48px; height:4px; background:#34B686; border-radius:2px; margin:0 auto 20px; }
  .jw-eyebrow { font-size:15px; font-weight:700; color:#0F6E56; letter-spacing:0.04em; margin-bottom:12px; }
  .jw-title { font-size:clamp(28px,4vw,36px); font-weight:800; color:#132E80; margin-bottom:10px; }
  .jw-date { font-size:15px; color:#9CA3AF; margin-bottom:36px; }
  .jw-cards { display:grid; grid-template-columns:repeat(3,1fr); gap:20px; text-align:left; }
  .jw-card { background:#fff; border:1px solid #E5E7EB; border-radius:16px; padding:28px 24px;
    border-top:4px solid #34B686; box-shadow:0 4px 14px rgba(19,46,128,0.06); }
  .jw-card-navy { border-top-color:#132E80; background:#F5F7FC; }
  .jw-icon { width:40px; height:40px; border-radius:50%; background:#EAF9F1; display:flex;
    align-items:center; justify-content:center; font-size:18px; margin-bottom:16px; }
  .jw-card-navy .jw-icon { background:#E4EAF8; }
  .jw-label { font-size:15px; font-weight:600; color:#4B5563; margin-bottom:10px; }
  .jw-value { font-size:32px; font-weight:800; color:#132E80; }
  .jw-unit { font-size:16px; font-weight:400; color:#9CA3AF; }
  .jw-delta { font-size:14px; font-weight:700; color:#B94A1F; margin-top:12px; }
  .jw-note { font-size:13px; color:#6B7280; margin-top:12px; line-height:1.5; }
  @media (max-width:640px){
    .jw-cards{ grid-template-columns:1fr; }
  }
</style>
</head>
<body>
<div class="jw-widget">
  <div class="jw-accent"></div>
  <div class="jw-eyebrow">SMP · REC</div>
  <div class="jw-title">실시간 시장 현황</div>
  <div class="jw-date" id="jwDateLabel">- 기준</div>
  <div class="jw-cards">
    <div class="jw-card">
      <div class="jw-icon">⚡</div>
      <div class="jw-label">SMP</div>
      <div class="jw-value"><span id="jwSmpValue">-</span><span class="jw-unit"> 원/kWh</span></div>
      <div id="jwSmpDelta" class="jw-delta"></div>
    </div>
    <div class="jw-card">
      <div class="jw-icon">🌱</div>
      <div class="jw-label">REC</div>
      <div class="jw-value"><span id="jwRecValue">-</span><span class="jw-unit"> 원/REC</span></div>
      <div class="jw-note">화·목요일에만 고시가가 갱신돼요</div>
    </div>
    <div class="jw-card jw-card-navy">
      <div class="jw-icon">💰</div>
      <div class="jw-label">1kW당 예상 수익</div>
      <div class="jw-value"><span id="jwSmpPlusValue">-</span><span class="jw-unit"> 원/kWh</span></div>
      <div class="jw-note">SMP + (REC × """ + str(REC_WEIGHT) + """)</div>
    </div>
  </div>
</div>
<script>
var jwData = REPLACE_WITH_JSON;
var REC_WEIGHT = """ + str(REC_WEIGHT) + """;
function jwGetSmp(rec) {
  if (rec.smp !== undefined && rec.smp !== null) return Number(rec.smp) || 0;
  return Number(rec.smp_land) || 0;
}
function jwUpdateValues() {
  if (!jwData || jwData.length === 0) return;
  var today = jwData[0];
  var yesterday = jwData[1] || today;
  var smpToday = jwGetSmp(today);
  var smpYesterday = jwGetSmp(yesterday);
  var recToday = Number(today.rec) || 0;
  var smpDelta = smpToday - smpYesterday;
  var smpPlus = smpToday + (recToday * REC_WEIGHT) / 1000;
  document.getElementById('jwDateLabel').textContent = today.date + ' 기준';
  document.getElementById('jwSmpValue').textContent = smpToday.toFixed(2);
  document.getElementById('jwSmpDelta').innerHTML = (smpDelta >= 0 ? '▲ ' : '▼ ') + Math.abs(smpDelta).toFixed(2) + ' (전일대비)';
  document.getElementById('jwRecValue').textContent = recToday.toLocaleString();
  document.getElementById('jwSmpPlusValue').textContent = smpPlus.toFixed(2);
}
jwUpdateValues();
</script>
</body>
</html>"""

    html = html.replace("REPLACE_WITH_JSON", records_json)
    os.makedirs("docs", exist_ok=True)
    with open("docs/index.html", "w", encoding="utf-8") as f:
        f.write(html)
    print("docs/index.html 생성 완료")


def generate_trend_html(records):
    """최근 30일 추이 그래프 페이지 (docs/trend.html)"""
    trend = list(reversed(records[:30]))
    labels = [r["date"][5:] for r in trend]
    smp = [get_smp(r) for r in trend]
    rec = [r["rec"] for r in trend]

    html = """<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>SMP·REC 추이</title>
<style>
  body { margin:0; font-family:'Pretendard',sans-serif; background:#FBFCFE; }
  .jw-trend-wrap { padding:56px 40px; }
  .jw-trend-head { text-align:center; max-width:720px; margin:0 auto 40px; }
  .jw-accent-bar { width:48px; height:5px; background:#34B686; border-radius:3px; margin:0 auto 20px; }
  .jw-trend-eyebrow { font-size:20px; color:#0F6E56; font-weight:800; margin-bottom:14px; }
  .jw-trend-title { font-size:clamp(32px,5vw,44px); font-weight:800; color:#132E80; }
  .jw-trend-card { max-width:1000px; margin:0 auto; background:#fff; border:1px solid #D1D5DB; border-radius:20px; box-shadow:0 12px 32px rgba(19,46,128,0.12); padding:32px; }
  .jw-legend { display:flex; flex-wrap:wrap; gap:16px; margin-bottom:16px; font-size:14px; font-weight:700; color:#374151; }
  .jw-legend span { display:flex; align-items:center; gap:6px; }
  .jw-dot-blue { width:10px; height:10px; border-radius:2px; background:#132E80; }
  .jw-dot-coral { width:10px; height:10px; border-radius:2px; background:#D85A30; }
  .jw-chart-box { position:relative; height:340px; }
</style>
</head>
<body>
<div class="jw-trend-wrap">
  <div class="jw-trend-head">
    <div class="jw-accent-bar"></div>
    <div class="jw-trend-eyebrow">데이터로 보는 흐름</div>
    <div class="jw-trend-title">최근 30일 SMP·REC 추이</div>
  </div>
  <div class="jw-trend-card">
    <div class="jw-legend">
      <span><span class="jw-dot-blue"></span>SMP</span>
      <span><span class="jw-dot-coral"></span>REC (우측 축)</span>
    </div>
    <div class="jw-chart-box">
      <canvas id="jwTrendChart" role="img" aria-label="최근 30일 SMP, REC 추이 라인 차트">최근 30일 SMP와 REC 데이터 추이를 보여주는 차트입니다.</canvas>
    </div>
  </div>
</div>
<script src="https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.4.1/chart.umd.js"></script>
<script>
var labels = REPLACE_LABELS;
var smp = REPLACE_SMP;
var rec = REPLACE_REC;
var flowOffset = 0;
var flowPlugin = {
  id: 'jwFlow',
  beforeDatasetsDraw: function(chart) {
    chart.ctx.save();
    chart.ctx.lineDashOffset = -flowOffset;
  },
  afterDatasetsDraw: function(chart) {
    chart.ctx.restore();
  }
};
var jwChart = new Chart(document.getElementById('jwTrendChart'), {
  type: 'line',
  data: { labels: labels, datasets: [
    { label:'SMP', data: smp, borderColor:'#132E80', backgroundColor:'rgba(19,46,128,0.08)', borderWidth:2.5, pointRadius:0, yAxisID:'y' },
    { label:'REC', data: rec, borderColor:'#D85A30', borderWidth:2, borderDash:[6,4], pointRadius:0, yAxisID:'y1' }
  ]},
  options: { responsive:true, maintainAspectRatio:false, animation:false, plugins:{legend:{display:false}}, scales:{
    x:{ ticks:{ maxTicksLimit:8, color:'#6B7280' }, grid:{ display:false } },
    y:{ position:'left', title:{display:true,text:'원/kWh',color:'#6B7280'}, ticks:{color:'#6B7280'}, grid:{color:'#F1F1F1'} },
    y1:{ position:'right', title:{display:true,text:'원/REC',color:'#6B7280'}, ticks:{color:'#6B7280'}, grid:{display:false} }
  }},
  plugins: [flowPlugin]
});
function animateFlow(){ flowOffset = (flowOffset+0.4)%10; jwChart.draw(); requestAnimationFrame(animateFlow); }
animateFlow();
</script>
</body>
</html>"""

    html = html.replace("REPLACE_LABELS", json.dumps(labels, ensure_ascii=False))
    html = html.replace("REPLACE_SMP", json.dumps(smp))
    html = html.replace("REPLACE_REC", json.dumps(rec))

    os.makedirs("docs", exist_ok=True)
    with open("docs/trend.html", "w", encoding="utf-8") as f:
        f.write(html)
    print("docs/trend.html 생성 완료")


def main():
    if not SERVICE_KEY:
        print("ERROR: DATA_GO_KR_KEY 환경변수(시크릿)가 설정되지 않았습니다.")
        sys.exit(1)

    date_compact = today_kst_str()
    date_dashed = today_kst_dashed()

    print(f"=== {date_dashed} 데이터 수집 시작 ===")

    smp = fetch_smp(date_compact)
    rec_price = fetch_rec(date_compact)

    records = load_existing_data()

    if smp is None:
        if records:
            print("SMP 조회 실패 → 직전 값 유지")
            smp = get_smp(records[0])
        else:
            print("SMP 조회 실패 & 기존 데이터도 없음 → 종료")
            sys.exit(1)

    if rec_price is None:
        if records:
            print("REC 비거래일 → 직전 거래가 유지")
            rec_price = records[0]["rec"]
        else:
            print("REC 데이터 없음 & 기존 데이터도 없음 → 0으로 처리")
            rec_price = 0

    new_record = {
        "date": date_dashed,
        "smp": smp,
        "rec": rec_price,
    }

    records = [r for r in records if r["date"] != date_dashed]
    records.append(new_record)

    records = save_data(records)
    generate_html(records)
    generate_trend_html(records)

    print(f"저장 완료: {new_record}")


if __name__ == "__main__":
    main()
