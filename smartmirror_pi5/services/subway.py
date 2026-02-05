import requests
from datetime import datetime
import time

BASE_SUBWAY = "http://apis.data.go.kr/1613000/SubwayInfoService"

def _get(url: str, params: dict) -> dict:
    try:
        # 디버깅용 로그
        print(f"[TAGO Subway] Request: {url} params={params}")
        r = requests.get(url, params=params, timeout=8)
        # 응답 내용 확인
        if r.status_code != 200:
            print(f"[TAGO Subway] Error Status: {r.status_code}, Body: {r.text}")
        
        r.raise_for_status()
        j = r.json()
        
        # 결과 코드 확인 (OpenAPI 공통 에러)
        header = (j.get("response") or {}).get("header") or {}
        result_code = header.get("resultCode")
        if result_code != "00":
            print(f"[TAGO Subway] Result Code: {result_code}, Msg: {header.get('resultMsg')}")
            
        return j
    except Exception as e:
        print(f"[TAGO Subway API Error] {e}")
        return {}

def get_subway_station_list(service_key: str, subway_station_name: str, page_no: int = 1, num_of_rows: int = 10) -> dict:
    """
    지하철역 목록 조회 (키워드 검색)
    API: getKwrdFndSubwaySttnList
    """
    url = f"{BASE_SUBWAY}/getKwrdFndSubwaySttnList"
    params = {
        "serviceKey": service_key,
        "pageNo": page_no,
        "numOfRows": num_of_rows,
        "_type": "json",
        "subwayStationName": subway_station_name
    }
    j = _get(url, params)
    
    items = (((j.get("response") or {}).get("body") or {}).get("items") or {}).get("item") or []
    if isinstance(items, dict):
        items = [items]
        
    out = []
    for it in items:
        out.append({
            "subwayStationId": it.get("subwayStationId"),
            "subwayStationName": it.get("subwayStationName"),
            "subwayRouteName": it.get("subwayRouteName")
        })
        
    return {"ok": True, "stations": out, "raw": j}

def get_subway_sched(service_key: str, subway_station_id: str, daily_tag: str, up_down_type: str) -> list:
    """
    지하철역 시간표 조회
    API: getSubwaySttnAcctoSchdulList
    
    daily_tag: 1(평일), 2(토요일), 3(공휴일/일요일)
    up_down_type: U(상행/내선), D(하행/외선)
    """
    url = f"{BASE_SUBWAY}/getSubwaySttnAcctoSchdulList"
    params = {
        "serviceKey": service_key,
        "pageNo": 1,
        "numOfRows": 500,  # 하루치 전체
        "_type": "json",
        "subwayStationId": subway_station_id,
        "dailyTypeCode": daily_tag,
        "upDownTypeCode": up_down_type
    }
    j = _get(url, params)
    
    items = (((j.get("response") or {}).get("body") or {}).get("items") or {}).get("item") or []
    if isinstance(items, dict):
        items = [items]
        
    # 시간표 파싱
    # item: { "arrTime": "053000", "depTime": "053030", "endSubwayStationNm": "...", ... }
    schedule = []
    for it in items:
        # depTime (HHMMSS) 사용
        dep_time = it.get("depTime")
        if not dep_time or len(dep_time) < 4:
            continue
            
        hh = int(dep_time[0:2])
        mm = int(dep_time[2:4])
        
        # 24시 넘어가면 00시 등으로 처리되는데, API는 00, 01 등으로 줌.
        # 정렬을 위해 분(minute)으로 환산
        minutes = hh * 60 + mm
        
        schedule.append({
            "arrTime": it.get("arrTime"),
            "depTime": dep_time,
            "endSubwayStationNm": it.get("endSubwayStationNm"),
            "subwayStationNm": it.get("subwayStationNm"),
            "minutes": minutes
        })
        
    # 시간순 정렬
    schedule.sort(key=lambda x: x["minutes"])
    return schedule

def get_next_subway(service_key: str, subway_station_id: str) -> dict:
    """
    현재 시간 기준, 상행/하행 각각 다음 열차 정보 조회
    """
    now = datetime.now()
    # 요일 구분 (0:월 ~ 6:일)
    wd = now.weekday()
    if wd <= 4:
        daily_tag = "01" # 평일
    elif wd == 5:
        daily_tag = "02" # 토요일
    else:
        daily_tag = "03" # 공휴일/일요일
        
    now_min = now.hour * 60 + now.minute
    
    # 상행(U), 하행(D) 각각 조회
    result = {"U": [], "D": []}
    
    for ud in ["U", "D"]:
        sched = get_subway_sched(service_key, subway_station_id, daily_tag, ud)
        # 현재 시간 이후인 것 필터
        upcoming = [s for s in sched if s["minutes"] >= now_min]
        
        # 만약 자정 넘어서(24:xx -> 00:xx)의 케이스 처리 필요하다면 복잡해지나,
        # 보통 첫차/막차 끊기므로 심플하게 처리.
        # 새벽 0시~3시 사이라면, now_min이 작아서 전체가 다 나올 수 있음.
        # 실제로는 배차 간격이 커서 새벽엔 없을 것.
        
        # 3개만 미리보기
        result[ud] = upcoming[:3]
        
        # ETA 계산
        for tr in result[ud]:
            tr["eta_min"] = max(tr["minutes"] - now_min, 0)
            
    return {"ok": True, "schedule": result, "dayType": daily_tag}
