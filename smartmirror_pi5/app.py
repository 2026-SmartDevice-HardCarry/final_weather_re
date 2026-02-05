from flask import Flask, render_template, jsonify, request
from datetime import datetime
import json
import threading
import time
import pytz

from config import Config
from db import init_db, get_stat, set_stat, log_event
from services.openweather import get_openweather
from services.tago import get_nearby_stops, get_arrivals_by_stop
from services.subway import get_subway_station_list, get_next_subway
from services.kakao_mobility import get_taxi_time
from services.kakao_local import search_keyword
from services.speech import listen_and_recognize, test_microphone

from logic.commute_probability import compute_probabilities
from logic.briefing import make_briefing

app = Flask(__name__, template_folder="web/templates", static_folder="web/static")
init_db()

tz = pytz.timezone(Config.TZ)

def iso_now():
    return datetime.now(tz).isoformat(timespec="seconds")

def safe_int(s: str, default=0):
    try: return int(s)
    except: return default

def parse_hhmm(s: str) -> int:
    hh, mm = s.split(":")
    return int(hh)*60 + int(mm)

# ====== API: UI에서 눌렀을 때 interaction 찍기 ======
@app.route("/api/interaction", methods=["POST"])
def api_interaction():
    # 지금 구현에서는 버튼/터치가 있으면 CV의 noresponse를 풀어주기 위한 훅
    # (단순히 이벤트 로깅만 하고, 필요하면 condition_cv에 hook 연결도 가능)
    log_event(iso_now(), "user_interaction", json.dumps({"type": "touch"}, ensure_ascii=False))
    return jsonify({"ok": True})

# ====== TAGO: 근처 정류장 검색 ======
@app.route("/api/nearby_stops")
def api_nearby():
    lat = float(request.args.get("lat", Config.BUS_STOP_LAT))
    lon = float(request.args.get("lon", Config.BUS_STOP_LON))
    j = get_nearby_stops(Config.TAGO_SERVICE_KEY, lat, lon, num_rows=10)
    return jsonify(j)

# ====== TAGO: 특정 정류장 도착정보 ======
@app.route("/api/arrivals")
def api_arrivals():
    city = request.args.get("cityCode") or Config.TAGO_CITY_CODE
    node = request.args.get("nodeId")
    if not city or not node:
        return jsonify({"ok": False, "error": "need cityCode and nodeId"})
    j = get_arrivals_by_stop(Config.TAGO_SERVICE_KEY, city, node)
    return jsonify(j)

# ====== TAGO: 정류장 검색 + 도착정보 ======
@app.route("/api/search_bus_stop")
def api_search_bus_stop():
    """
    정류장 검색 API - 키워드 또는 좌표로 정류장 검색 후 도착정보 반환
    
    Query params:
        q: 검색어 (정류장 이름)
        lat, lon: 좌표 (검색어 없을 때 사용)
        nodeId: 특정 정류장 ID (직접 지정)
    """
    query = request.args.get("q", "").strip()
    node_id = request.args.get("nodeId", "").strip()
    city_code = Config.TAGO_CITY_CODE
    
    # 1. nodeId가 직접 지정된 경우
    if node_id:
        arr = get_arrivals_by_stop(Config.TAGO_SERVICE_KEY, city_code, node_id, num_rows=20)
        return jsonify({
            "ok": True,
            "stop": {"nodeId": node_id, "nodeNm": request.args.get("nodeNm", "")},
            "arrivals": arr.get("arrivals", [])[:5],
            "eta_min": arr.get("eta_min")
        })
    
    # 2. 좌표로 근처 정류장 검색
    lat = float(request.args.get("lat", Config.BUS_STOP_LAT))
    lon = float(request.args.get("lon", Config.BUS_STOP_LON))
    
    
    near = get_nearby_stops(Config.TAGO_SERVICE_KEY, lat, lon, num_rows=10)
    
    if not near.get("ok") or not near.get("stops"):
        return jsonify({"ok": False, "error": "정류장을 찾을 수 없습니다"})
    
    # 3. 검색어가 있으면 이름으로 필터링
    stops = near["stops"]
    if query:
        filtered = [s for s in stops if query.lower() in (s.get("nodeNm") or "").lower()]
        if filtered:
            stops = filtered
    
    # 4. 첫 번째 정류장의 도착정보 조회
    chosen_stop = stops[0]
    arr = get_arrivals_by_stop(Config.TAGO_SERVICE_KEY, city_code, chosen_stop["nodeId"], num_rows=20)
    
    return jsonify({
        "ok": True,
        "stop": chosen_stop,
        "all_stops": stops,
        "arrivals": arr.get("arrivals", [])[:5],
        "eta_min": arr.get("eta_min")
    })

@app.route("/api/search_subway_station")
def api_search_subway_station():
    """
    지하철역 검색 API
    q=검색어 -> 결과 반환
    stationId=ID -> 해당 역 도착정보(시간표 기반) 반환
    """
    query = request.args.get("q", "").strip()
    station_id = request.args.get("stationId", "").strip()
    
    # 1. 특정 역 선택 시 -> 도착 정보 반환
    if station_id:
        sched_data = get_next_subway(Config.TAGO_SUBWAY_KEY, station_id)
        return jsonify({
            "ok": True,
            "schedule": sched_data.get("schedule"),
            "dayType": sched_data.get("dayType")
        })

    # 2. 검색어 없으면 -> 기본 역(환경변수) 검색
    if not query:
        query = Config.SUBWAY_STATION_NAME

    # 3. 역 검색
    res = get_subway_station_list(Config.TAGO_SUBWAY_KEY, query)
    stations = res.get("stations", [])
    
    # 검색 결과 중 첫 번째를 기본 선택
    chosen_station = None
    schedule = {"U": [], "D": []}
    day_type = "01"
    
    if stations:
        chosen_station = stations[0]
        sched_res = get_next_subway(Config.TAGO_SUBWAY_KEY, chosen_station["subwayStationId"])
        schedule = sched_res.get("schedule", {"U": [], "D": []})
        day_type = sched_res.get("dayType", "01")
        
    return jsonify({
        "ok": True,
        "station": chosen_station,
        "all_stations": stations,
        "schedule": schedule,
        "dayType": day_type
    })

# ====== 음성 목적지 검색 ======
@app.route("/api/voice_destination", methods=["POST"])
def api_voice_destination():
    """
    음성으로 목적지를 입력받아 좌표 검색 + 택시 정보 반환
    
    Request JSON (optional):
        {"engine": "google" | "vosk", "timeout": 5.0}
    
    Returns:
        {
            "ok": True/False,
            "speech_text": "인식된 텍스트",
            "destination": {"name": ..., "lat": ..., "lon": ...},
            "taxi": {"duration_min": ..., "taxi_fare": ...},
            "error": "에러 메시지"
        }
    """
    data = request.get_json() or {}
    engine = data.get("engine", "google")
    timeout = float(data.get("timeout", 5.0))
    
    # 1. 음성 인식
    speech_result = listen_and_recognize(engine=engine, timeout=timeout)
    if not speech_result.get("ok"):
        return jsonify({
            "ok": False, 
            "error": f"음성 인식 실패: {speech_result.get('error')}"
        })
    
    destination_text = speech_result.get("text", "").strip()
    if not destination_text:
        return jsonify({"ok": False, "error": "인식된 음성이 없습니다"})
    
    # 2. 목적지 좌표 검색
    search_result = search_keyword(
        Config.KAKAO_REST_API_KEY, 
        destination_text,
        x=Config.HOME_LON,  # 집 기준으로 가까운 곳 우선
        y=Config.HOME_LAT
    )
    
    if not search_result.get("ok") or not search_result.get("places"):
        return jsonify({
            "ok": False,
            "speech_text": destination_text,
            "error": f"'{destination_text}' 검색 결과 없음"
        })
    
    # 첫 번째 결과 사용
    place = search_result["places"][0]
    dest_lat = place["lat"]
    dest_lon = place["lon"]
    
    # 3. 택시 정보 조회
    taxi_result = get_taxi_time(
        Config.KAKAO_REST_API_KEY,
        Config.HOME_LAT, Config.HOME_LON,  # 출발지: 집
        dest_lat, dest_lon  # 도착지: 검색된 장소
    )
    
    # 이벤트 로깅
    log_event(iso_now(), "voice_destination_search", json.dumps({
        "speech_text": destination_text,
        "destination": place["name"],
        "lat": dest_lat,
        "lon": dest_lon,
        "taxi_ok": taxi_result.get("ok", False)
    }, ensure_ascii=False))
    
    return jsonify({
        "ok": True,
        "speech_text": destination_text,
        "destination": {
            "name": place["name"],
            "address": place["address"],
            "lat": dest_lat,
            "lon": dest_lon,
            "category": place.get("category", "")
        },
        "taxi": taxi_result if taxi_result.get("ok") else None,
        "all_places": search_result["places"]  # 다른 검색 결과도 제공
    })

@app.route("/api/search_destination")
def api_search_destination():
    """
    텍스트로 목적지 검색 (키보드 입력용)
    
    Query params:
        q: 검색어
    """
    query = request.args.get("q", "").strip()
    if not query:
        return jsonify({"ok": False, "error": "검색어가 없습니다"})
    
    # 목적지 좌표 검색
    search_result = search_keyword(
        Config.KAKAO_REST_API_KEY, 
        query,
        x=Config.HOME_LON,
        y=Config.HOME_LAT
    )
    
    if not search_result.get("ok") or not search_result.get("places"):
        return jsonify({"ok": False, "error": f"'{query}' 검색 결과 없음"})
    
    place = search_result["places"][0]
    
    # 택시 정보 조회
    taxi_result = get_taxi_time(
        Config.KAKAO_REST_API_KEY,
        Config.HOME_LAT, Config.HOME_LON,
        place["lat"], place["lon"]
    )
    
    return jsonify({
        "ok": True,
        "destination": {
            "name": place["name"],
            "address": place["address"],
            "lat": place["lat"],
            "lon": place["lon"]
        },
        "taxi": taxi_result if taxi_result.get("ok") else None,
        "all_places": search_result["places"]
    })

# ====== 교통수단별 도착 확률 계산 ======
@app.route("/api/commute_probability", methods=["POST"])
def api_commute_probability():
    """
    목표 도착 시간과 목적지를 입력받아 각 교통수단별 정시 도착 확률 계산
    
    Request JSON:
        {
            "arrive_hhmm": "09:00",
            "dest": {"name": "부산역", "lat": 35.1152, "lon": 129.0416},
            "bus_nodeId": "optional",
            "bus_cityCode": "optional",
            "subway_stationId": "optional"
        }
    
    Returns:
        {
            "ok": True,
            "now": "08:00",
            "arrive_hhmm": "09:00",
            "time_budget_min": 60.0,
            "probabilities": {
                "taxi": {"ok": true, "p_on_time": 0.95, "mean_min": 25, ...},
                "bus": {"ok": true, "p_on_time": 0.72, "mean_min": 45, ...},
                "subway": {"ok": true, "p_on_time": 0.85, "mean_min": 35, ...}
            }
        }
    """
    try:
        data = request.get_json() or {}
        arrive_hhmm = (data.get("arrive_hhmm") or "").strip()
        dest = data.get("dest") or {}
        dest_name = dest.get("name", "목적지")
        dest_lat = dest.get("lat")
        dest_lon = dest.get("lon")

        if not arrive_hhmm:
            return jsonify({"ok": False, "error": "arrive_hhmm 이 필요합니다 (예: 09:00)"})
        if dest_lat is None or dest_lon is None:
            return jsonify({"ok": False, "error": "dest.lat / dest.lon 이 필요합니다"})

        now = datetime.now(tz)
        now_min = now.hour * 60 + now.minute

        # arrive_hhmm 을 오늘 기준 minute으로
        hh, mm = arrive_hhmm.split(":")
        arrive_min = int(hh) * 60 + int(mm)

        # 자정 넘어가는 입력 처리(예: 지금 23:50인데 00:10 입력)
        if arrive_min < now_min:
            arrive_min += 24 * 60

        time_budget = float(arrive_min - now_min)

        # ---- 택시(카카오모빌리티) ----
        taxi = get_taxi_time(
            Config.KAKAO_REST_API_KEY,
            Config.HOME_LAT, Config.HOME_LON,
            dest_lat, dest_lon
        )
        taxi_duration_min = taxi.get("duration_min") if taxi.get("ok") else None
        taxi_distance_m = taxi.get("distance_meter") if taxi.get("ok") else None

        # ---- 버스 대기(집 근처 정류장 기준) ----
        bus_wait_min = None
        bus_detail = {"ok": False}
        try:
            node_id = (data.get("bus_nodeId") or "").strip()
            city_code = (data.get("bus_cityCode") or Config.TAGO_CITY_CODE).strip()

            if node_id and city_code:
                arr = get_arrivals_by_stop(Config.TAGO_SERVICE_KEY, city_code, node_id, num_rows=30)
                bus_wait_min = arr.get("eta_min")
                bus_detail = {"ok": True, "cityCode": city_code, "nodeId": node_id, "eta_min": bus_wait_min}
            else:
                if Config.BUS_STOP_LAT != 0.0 and Config.BUS_STOP_LON != 0.0 and Config.TAGO_CITY_CODE:
                    near = get_nearby_stops(Config.TAGO_SERVICE_KEY, Config.BUS_STOP_LAT, Config.BUS_STOP_LON, num_rows=5)
                    stops = near.get("stops") or []
                    if stops:
                        chosen = stops[0]
                        arr = get_arrivals_by_stop(Config.TAGO_SERVICE_KEY, Config.TAGO_CITY_CODE, chosen["nodeId"], num_rows=30)
                        bus_wait_min = arr.get("eta_min")
                        bus_detail = {"ok": True, "cityCode": Config.TAGO_CITY_CODE, "stop": chosen, "eta_min": bus_wait_min}
        except Exception as e:
            bus_detail = {"ok": False, "error": str(e)}

        # ---- 지하철 대기(Config.SUBWAY_STATION_NAME 기준) ----
        subway_wait_min = None
        subway_detail = {"ok": False}
        try:
            station_id = (data.get("subway_stationId") or "").strip()
            if not station_id:
                res = get_subway_station_list(Config.TAGO_SUBWAY_KEY, Config.SUBWAY_STATION_NAME)
                stations = res.get("stations") or []
                if stations:
                    station_id = stations[0]["subwayStationId"]
                    subway_detail["station"] = stations[0]

            if station_id:
                sched = get_next_subway(Config.TAGO_SUBWAY_KEY, station_id)
                sch = (sched.get("schedule") or {})
                etas = []
                for ud in ["U", "D"]:
                    for tr in (sch.get(ud) or []):
                        if isinstance(tr.get("eta_min"), (int, float)):
                            etas.append(float(tr["eta_min"]))
                if etas:
                    subway_wait_min = min(etas)
                subway_detail.update({"ok": True, "stationId": station_id, "eta_min": subway_wait_min})
        except Exception as e:
            subway_detail = {"ok": False, "error": str(e)}

        # 확률 계산 - 버스/지하철 운행 여부 확인
        # bus_wait_min이 None이면 버스 운행 없음 (새벽 등)
        # subway_wait_min이 None이면 지하철 운행 없음 (새벽 등)
        bus_available = bus_detail.get("ok", False) and bus_wait_min is not None
        subway_available = subway_detail.get("ok", False) and subway_wait_min is not None
        
        probs = compute_probabilities(
            time_budget_min=time_budget,
            taxi_duration_min=taxi_duration_min,
            taxi_distance_m=taxi_distance_m,
            bus_wait_min=bus_wait_min,
            subway_wait_min=subway_wait_min,
            bus_available=bus_available,
            subway_available=subway_available,
            current_hour=now.hour,
        )

        return jsonify({
            "ok": True,
            "now": now.strftime("%H:%M"),
            "arrive_hhmm": arrive_hhmm,
            "time_budget_min": round(time_budget, 1),
            "destination": {"name": dest_name, "lat": dest_lat, "lon": dest_lon},
            "taxi": taxi if taxi.get("ok") else {"ok": False, "error": taxi.get("error")},
            "bus_wait": bus_detail,
            "subway_wait": subway_detail,
            "probabilities": probs
        })

    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"ok": False, "error": str(e)})

@app.route("/api/mic_test")
def api_mic_test():
    """마이크 테스트 - 사용 가능한 마이크 목록 반환"""
    return jsonify(test_microphone())

@app.route("/")
def dashboard():
    now = datetime.now(tz)
    now_min = now.hour*60 + now.minute



    # ---- Weather ----
    weather = get_openweather(Config.OWM_API_KEY, Config.HOME_LAT, Config.HOME_LON)
    precip_prob = float(weather.get("precip_prob", 0.0)) if weather.get("ok") else 0.0
    rain_like = precip_prob >= 0.5

    # ---- TAGO: “근처 정류장 1개 자동 선택” + ETA ----
    eta_min = None
    chosen_stop = None
    arrivals_preview = []
    city_code = Config.TAGO_CITY_CODE or ""

    try:
        near = get_nearby_stops(Config.TAGO_SERVICE_KEY, Config.BUS_STOP_LAT, Config.BUS_STOP_LON, num_rows=8)
        if near.get("ok") and near["stops"]:
            chosen_stop = near["stops"][0]  # 제일 가까운 정류장
            # cityCode는 필수라서: 기본은 env에서 넣고, 없으면 UI에서 선택하도록
            if city_code:
                arr = get_arrivals_by_stop(Config.TAGO_SERVICE_KEY, city_code, chosen_stop["nodeId"], num_rows=20)
                eta_min = arr.get("eta_min")
                all_arrivals = arr.get("arrivals") or []
                arrivals_preview = all_arrivals[:5]
                print(f"[TAGO 정보] 정류장: {chosen_stop['nodeNm']}, 전체 버스: {len(all_arrivals)}개, 표시: {len(arrivals_preview)}개")
                for a in arrivals_preview:
                    print(f"  - {a.get('routeNo')}: {a.get('arrTimeMin')}분")
            else:
                print("[TAGO 경고] TAGO_CITY_CODE가 설정되지 않아 도착정보를 조회하지 않습니다")
        else:
            print(f"[TAGO 경고] 근처 정류장 조회 실패: {near}")
    except Exception as e:
        import traceback
        print(f"[TAGO 에러] {e}")
        traceback.print_exc()

    # ---- Kakao Taxi ----
    taxi = get_taxi_time(
        Config.KAKAO_REST_API_KEY, 
        Config.HOME_LAT, Config.HOME_LON,
        Config.DEST_LAT, Config.DEST_LON
    )

    # ---- 개인 통계(간단) ----
    avg_depart = get_stat("avg_departure_hhmm", "08:10")
    late_7 = safe_int(get_stat("late_count_7days", "0"), 0)

    depart_delay = max(now_min - parse_hhmm(avg_depart), 0)

    # congestion proxy:
    # - 버스 ETA가 길면 혼잡으로 간주(대중교통 기반)
    # - ETA 없으면 중립값
    if eta_min is None:
        congestion = 0.5
    else:
        # 3~20분 ETA를 0~1로 매핑(임시)
        congestion = min(max((eta_min - 5) / 15.0, 0.0), 1.0)



    # ---- 추천 출발(간단 룰: ETA 기반) ----
    if eta_min is None:
        rec_depart = 5
    elif eta_min <= 5:
        rec_depart = 0
    elif eta_min <= 10:
        rec_depart = 5
    else:
        rec_depart = 10

    # ---- 브리핑 ----
    brief = make_briefing({
        "recommend_depart_in_min": rec_depart,
        "weather": weather
    })

    # ---- 로깅 ----
    log_event(iso_now(), "dashboard_loaded", json.dumps({
        "congestion": congestion,
        "precip_prob": precip_prob
    }, ensure_ascii=False))

    return render_template(
        "dashboard.html",
        now=now.strftime("%Y-%m-%d %H:%M"),

        weather=weather if weather.get("ok") else {"temp": None, "feels_like": None, "precip_prob": 0.0},
        precip_prob=precip_prob,

        stop=chosen_stop,
        city_code=city_code,
        eta_min=eta_min,
        arrivals_preview=arrivals_preview,

        congestion=round(congestion, 3),

        taxi=taxi,
        dest_name=Config.DEST_NAME,

        briefing=brief
    )

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080, debug=False)