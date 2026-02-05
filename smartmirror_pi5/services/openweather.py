import requests

def get_openweather(api_key: str, lat: float, lon: float) -> dict:
    """
    OpenWeather 무료 API (2.5)를 사용하여 현재 날씨 + 강수확률 조회
    - Current Weather API: 현재 날씨
    - 5-day Forecast API: 강수확률 (pop)
    """
    if not api_key:
        return {"ok": False, "error": "OWM_API_KEY missing"}

    result = {
        "ok": False,
        "temp": None,
        "feels_like": None,
        "humidity": None,
        "wind": None,
        "precip_prob": 0.0,
        "weather_desc": "",
        "weather_main": "",      # 날씨 메인 카테고리 (Rain, Snow, Clear 등)
        "weather_id": None,      # 날씨 ID (상세 구분용)
        "icon": "",
        "is_rain": False,        # 비 오는 중
        "is_snow": False,        # 눈 오는 중
        "rain_1h": 0.0,          # 1시간 강수량 (mm)
        "snow_1h": 0.0,          # 1시간 적설량 (mm)
    }

    # 1. 현재 날씨 조회 (무료 API 2.5)
    weather_url = "https://api.openweathermap.org/data/2.5/weather"
    weather_params = {
        "lat": lat, "lon": lon,
        "appid": api_key,
        "units": "metric",
        "lang": "kr"
    }
    try:
        r = requests.get(weather_url, params=weather_params, timeout=8)
        r.raise_for_status()
        w = r.json()
        
        result["temp"] = w.get("main", {}).get("temp")
        result["feels_like"] = w.get("main", {}).get("feels_like")
        result["humidity"] = w.get("main", {}).get("humidity")
        result["wind"] = w.get("wind", {}).get("speed")
        
        weather_list = w.get("weather", [])
        if weather_list:
            weather_info = weather_list[0]
            result["weather_desc"] = weather_info.get("description", "")
            result["weather_main"] = weather_info.get("main", "")
            result["weather_id"] = weather_info.get("id")
            result["icon"] = weather_info.get("icon", "")
            
            # 날씨 ID로 비/눈 판단
            # 2xx: 천둥번개, 3xx: 이슬비, 5xx: 비, 6xx: 눈
            weather_id = weather_info.get("id", 0)
            if 200 <= weather_id < 600:  # 비 (천둥번개, 이슬비, 비)
                result["is_rain"] = True
            elif 600 <= weather_id < 700:  # 눈
                result["is_snow"] = True
        
        # 현재 강수량/적설량 (있는 경우)
        rain_data = w.get("rain", {})
        snow_data = w.get("snow", {})
        result["rain_1h"] = rain_data.get("1h", 0.0)
        result["snow_1h"] = snow_data.get("1h", 0.0)
        
        # 강수량이 있으면 비/눈 플래그 업데이트
        if result["rain_1h"] > 0:
            result["is_rain"] = True
        if result["snow_1h"] > 0:
            result["is_snow"] = True
        
        result["ok"] = True
        
    except Exception as e:
        print(f"[OpenWeatherMap Current API Error] {e}")
        return {"ok": False, "error": str(e)}

    # 2. 3시간 예보에서 강수확률 조회 (무료 API 2.5)
    forecast_url = "https://api.openweathermap.org/data/2.5/forecast"
    forecast_params = {
        "lat": lat, "lon": lon,
        "appid": api_key,
        "units": "metric",
        "cnt": 4  # 다음 12시간 (3시간 x 4)
    }
    try:
        r = requests.get(forecast_url, params=forecast_params, timeout=8)
        r.raise_for_status()
        f = r.json()
        
        # 다음 6시간 내 강수확률 최대값
        forecast_list = f.get("list", [])[:2]  # 3시간 x 2 = 6시간
        pops = [item.get("pop", 0.0) for item in forecast_list]
        result["precip_prob"] = max(pops) if pops else 0.0
        
    except Exception as e:
        print(f"[OpenWeatherMap Forecast API Error] {e}")
        # 현재 날씨는 성공했으므로 ok 유지, 강수확률만 0으로

    return result