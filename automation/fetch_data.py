"""
주원에너지 SMP·REC 자동 갱신 스크립트
- 매일 GitHub Actions가 이 스크립트를 실행해서 data/smp-rec.json을 자동 업데이트합니다.
- docs/index.html: 히어로 카드 페이지 (GitHub Pages)
- docs/trend.html: 최근 30일 추이 그래프 페이지 (GitHub Pages)
"""

import json
import os
import sys
from datetime import datetime, timedelta, timezone

import requests

SERVICE_KEY = os.environ.get("DATA_GO_KR_KEY", "")
JSON_PATH = "data/smp-rec.json"
KEEP_DAYS = 90

SMP_URL = "https://apis.data.go.kr/B552115/SmpWithForecastDemand/getSmpWithForecastDemand"
REC_URL = "https://apis.data.go.kr/B552115/RecMarketInfo2/getRecMarketInfo2"

KST = timezone(timedelta(hours=9))


def today_kst_str():
    return datetime.now(KST).strftime("%Y%m%d")


def today_kst_dashed():
    return datetime.now(KST).strftime("%Y-%m-%d")


def fetch_smp(date_str):
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
        print("[DEBUG] SMP 전체 응답:", json.dumps(data, ensure_ascii=False))
        result_code = data["response"]["header"]["resultCode"]
        if result_code != "00":
            print(f"[SMP] API 오류: {data['response']['header']['resultMsg']}")
            return None, None
        items = data["response"]["body"]["items"]["item"]
        print("[DEBUG] items 개수:", len(items) if isinstance(items, list) else 1)
        land_values = [float(i["smp"]) for i in items if i["areaName"] == "육지"]
        jeju_values = [float(i["smp"]) for i in items if i["areaName"] == "제주"]
        print("[DEBUG] land_values:", land_values)
        print("[DEBUG] jeju_values:", jeju_values)
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


def generate_html(records):
    """히어로 카드 페이지 (docs/index.html)"""
    records_json = json.dumps(records[:30], ensure_ascii=False)

    html = """<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>SMP·REC 현황</title>
<style>
  body { margin:0; font-family:'Pretendard',sans-serif; background:#ffffff; }
  #jwHero { position:relative; background:#E4EBF7; overflow:hidden; min-height:832px; }
  .jw-bg-svg { position:absolute; top:0; left:0; display:block; width:100%; height:100%; }
  .jw-header { position:relative; padding:90px 56px 0; text-align:center; }
  .jw-eyebrow { font-size:20px; color:#0F6E56; font-weight:700; margin-bottom:16px; }
  .jw-title { font-size:clamp(48px,6vw,68px); font-weight:800; color:#132E80; margin-bottom:20px; }
  .jw-date { display:inline-flex; align-items:center; gap:8px; font-size:20px; color:#1F2937; font-weight:700; margin-bottom:36px; }
  .jw-dot { width:8px; height:8px; border-radius:50%; background:#34B686; display:inline-block; }
  .jw-controls { display:flex; justify-content:center; gap:14px; margin-bottom:56px; }
  .jw-select { background:#fff; border:1px solid #9CA3AF; border-radius:10px; padding:14px 20px; font-size:18px; font-weight:700; color:#132E80; cursor:pointer; }
  .jw-cards { position:relative; display:grid; grid-template-columns:repeat(3,1fr); gap:24px; padding:0 56px 90px; max-width:1240px; margin:0 auto; }
  .jw-card { background:#fff; border:1px solid #E5E7EB; border-radius:16px; padding:36px; box-shadow:0 4px 16px rgba(19,46,128,0.08); }
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


def generate_trend_html(records):
    """최근 30일 추이 그래프 페이지 (docs/trend.html)"""
    trend = list(reversed(records[:30]))
    labels = [r["date"][5:] for r in trend]
    land = [r["smp_land"] for r in trend]
    jeju = [r["smp_jeju"] for r in trend]
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
  .jw-dot-green { width:10px; height:10px; border-radius:2px; background:#34B686; }
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
      <span><span class="jw-dot-blue"></span>SMP 육지</span>
      <span><span class="jw-dot-green"></span>SMP 제주</span>
      <span><span class="jw-dot-coral"></span>REC (우측 축)</span>
    </div>
    <div class="jw-chart-box">
      <canvas id="jwTrendChart" role="img" aria-label="최근 30일 SMP 육지, 제주, REC 추이 라인 차트">최근 30일 SMP와 REC 데이터 추이를 보여주는 차트입니다.</canvas>
    </div>
  </div>
</div>
<script src="https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.4.1/chart.umd.js"></script>
<script>
var labels = REPLACE_LABELS;
var land = REPLACE_LAND;
var jeju = REPLACE_JEJU;
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
    { label:'SMP 육지', data: land, borderColor:'#132E80', backgroundColor:'rgba(19,46,128,0.08)', borderWidth:2.5, pointRadius:0, yAxisID:'y' },
    { label:'SMP 제주', data: jeju, borderColor:'#34B686', backgroundColor:'rgba(52,182,134,0.08)', borderWidth:2.5, pointRadius:0, yAxisID:'y' },
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
    html = html.replace("REPLACE_LAND", json.dumps(land))
    html = html.replace("REPLACE_JEJU", json.dumps(jeju))
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

    smp_land, smp_jeju = fetch_smp(date_compact)
    rec_price = fetch_rec(date_compact)

    records = load_existing_data()

    if smp_land is None or smp_jeju is None:
        if records:
            print("SMP 조회 실패 → 직전 값 유지")
            smp_land = records[0]["smp_land"]
            smp_jeju = records[0]["smp_jeju"]
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
        "smp_land": smp_land,
        "smp_jeju": smp_jeju,
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
