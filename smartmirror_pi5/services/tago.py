import requests

BASE_STTN = "http://apis.data.go.kr/1613000/BusSttnInfoInqireService"
BASE_ARVL = "http://apis.data.go.kr/1613000/ArvlInfoInqireService"
BASE_ROUTE = "http://apis.data.go.kr/1613000/BusRouteInfoInqireService"

# 노선 정보 캐시 (routeId -> {startNodeNm, endNodeNm})
_route_cache = {}

def _get(url: str, params: dict) -> dict:
    r = requests.get(url, params=params, timeout=8)
    r.raise_for_status()
    return r.json()

def get_nearby_stops(service_key: str, gps_lati: float, gps_long: float, num_rows: int = 10) -> dict:
    # 좌표기반 근접정류소 목록조회: getCrdntPrxmtSttnList
    url = f"{BASE_STTN}/getCrdntPrxmtSttnList"
    params = {
        "serviceKey": service_key,
        "pageNo": 1,
        "numOfRows": num_rows,
        "_type": "json",
        "gpsLati": gps_lati,
        "gpsLong": gps_long,
    }
    j = _get(url, params)
    items = (((j.get("response") or {}).get("body") or {}).get("items") or {}).get("item") or []
    if isinstance(items, dict):
        items = [items]

    # 표준화
    out = []
    for it in items:
        out.append({
            "nodeId": it.get("nodeid") or it.get("nodeId"),
            "nodeNm": it.get("nodenm") or it.get("nodeNm"),
            "nodeNo": it.get("nodeno") or it.get("nodeNo"),  # 정류장 번호
            "gpsLati": it.get("gpslati") or it.get("gpsLati"),
            "gpsLong": it.get("gpslong") or it.get("gpsLong"),
        })
    return {"ok": True, "stops": out, "raw": j}

def get_route_info(service_key: str, city_code: str, route_id: str) -> dict:
    """
    노선 정보 조회 - 기점/종점 정보 반환
    getRouteInfoIem API 사용
    """
    global _route_cache
    
    # 캐시 확인
    cache_key = f"{city_code}_{route_id}"
    if cache_key in _route_cache:
        return _route_cache[cache_key]
    
    url = f"{BASE_ROUTE}/getRouteInfoIem"
    params = {
        "serviceKey": service_key,
        "pageNo": 1,
        "numOfRows": 1,
        "_type": "json",
        "cityCode": city_code,
        "routeId": route_id,
    }
    
    try:
        j = _get(url, params)
        items = (((j.get("response") or {}).get("body") or {}).get("items") or {}).get("item") or []
        if isinstance(items, dict):
            items = [items]
        
        if items:
            it = items[0]
            result = {
                "startNodeNm": it.get("startnodenm") or it.get("startnodename"),
                "endNodeNm": it.get("endnodenm") or it.get("endnodename"),
                "routeNo": it.get("routeno"),
            }
            _route_cache[cache_key] = result
            return result
    except Exception as e:
        print(f"[노선정보 조회 오류] {route_id}: {e}")
    
    return {"startNodeNm": None, "endNodeNm": None}

def get_arrivals_by_stop(service_key: str, city_code: str, node_id: str, num_rows: int = 30, enrich_route: bool = True) -> dict:
    """
    정류소별 도착예정정보 목록 조회
    enrich_route=True면 노선 정보도 조회하여 기점/종점 정보 추가
    """
    url = f"{BASE_ARVL}/getSttnAcctoArvlPrearngeInfoList"
    params = {
        "serviceKey": service_key,
        "pageNo": 1,
        "numOfRows": num_rows,
        "_type": "json",
        "cityCode": city_code,
        "nodeId": node_id,
    }
    j = _get(url, params)
    items = (((j.get("response") or {}).get("body") or {}).get("items") or {}).get("item") or []
    if isinstance(items, dict):
        items = [items]

    out = []
    for it in items:
        # arrtime: 초 단위
        arr_sec = it.get("arrtime")
        try:
            arr_min = int(round(int(arr_sec) / 60)) if arr_sec is not None else None
        except Exception:
            arr_min = None

        route_id = it.get("routeid")
        end_node_nm = it.get("endnodenm")  # 도착정보에서 먼저 확인
        start_node_nm = None
        
        # 종점 정보가 없으면 노선 정보 API에서 조회
        if enrich_route and route_id and not end_node_nm:
            route_info = get_route_info(service_key, city_code, route_id)
            end_node_nm = route_info.get("endNodeNm")
            start_node_nm = route_info.get("startNodeNm")

        out.append({
            "routeId": route_id,
            "routeNo": it.get("routeno"),
            "routeTp": it.get("routetp"),
            "arrPrevStationCnt": it.get("arrprevstationcnt"),
            "vehicleTp": it.get("vehicletp"),
            "startNodeNm": start_node_nm,  # 기점명
            "endNodeNm": end_node_nm,       # 종점명 (방면 정보)
            "arrTimeSec": arr_sec,
            "arrTimeMin": arr_min,
        })

    # "가장 빨리 오는 버스" ETA(min) 하나 뽑아주기
    eta_min = None
    mins = [x["arrTimeMin"] for x in out if isinstance(x.get("arrTimeMin"), int)]
    if mins:
        eta_min = min(mins)

    return {"ok": True, "arrivals": out, "eta_min": eta_min, "raw": j}