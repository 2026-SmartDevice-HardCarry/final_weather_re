import requests
import json
import logging

def get_taxi_time(api_key: str, origin_lat: float, origin_lon: float, dest_lat: float, dest_lon: float):
    """
    카카오 모빌리티(내비) API를 사용하여 택시 예상 시간 및 요금을 조회합니다.
    Ref: https://developers.kakao.com/docs/latest/ko/kakaonavi/common
    """
    if not api_key:
        return {"ok": False, "error": "No API Key"}
    
    # 목적지나 출발지 좌표가 0.0이면 스킵
    if (origin_lat == 0.0 and origin_lon == 0.0) or (dest_lat == 0.0 and dest_lon == 0.0):
        return {"ok": False, "error": "Invalid coordinates"}

    url = "https://apis-navi.kakaomobility.com/v1/directions"
    # origin, destination: "lon,lat"
    params = {
        "origin": f"{origin_lon},{origin_lat}",
        "destination": f"{dest_lon},{dest_lat}",
        "priority": "RECOMMEND",
        "car_type": 1,  # 일반 승용차 기준 (택시 요금 추산용)
        "summary": True
    }
    
    headers = {
        "Authorization": f"KakaoAK {api_key}"
    }
    
    try:
        res = requests.get(url, params=params, headers=headers, timeout=3)
        if res.status_code != 200:
            return {"ok": False, "error": f"HTTP {res.status_code}", "raw": res.text}
        
        data = res.json()
        routes = data.get("routes", [])
        if not routes:
            return {"ok": False, "error": "No routes found"}
        
        summary = routes[0].get("summary", {})
        duration_sec = summary.get("duration", 0)
        fare = summary.get("fare", {})
        taxi_fare = fare.get("taxi", 0)  # 예상 택시 요금
        
        return {
            "ok": True,
            "duration_min": duration_sec // 60,
            "taxi_fare": taxi_fare,
            "distance_meter": summary.get("distance", 0)
        }
            
    except Exception as e:
        return {"ok": False, "error": str(e)}
