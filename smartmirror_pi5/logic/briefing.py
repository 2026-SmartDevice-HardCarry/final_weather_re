def make_briefing(payload: dict) -> dict:
    depart_in = payload.get("recommend_depart_in_min", 5)
    weather = payload.get("weather", {})
    temp = weather.get("temp")
    
    points = []
    
    # 1. 날씨 기반 멘트 (최우선)
    weather_msgs = []
    
    # 비/눈
    if weather.get("is_snow"):
        weather_msgs.append("눈이 오고 있습니다. 우산을 챙기시고 미끄럼에 주의하세요.")
    elif weather.get("is_rain"):
        weather_msgs.append("비가 오고 있습니다. 우산을 꼭 챙기세요.")
        
    # 기온 (폭염/한파)
    if temp is not None:
        if temp >= 30:
            weather_msgs.append(f"현재 {int(temp)}도로 매우 덥습니다. 얇은 옷과 미니 선풍기를 챙기셨나요?")
        elif temp >= 27:
            weather_msgs.append(f"현재 {int(temp)}도로 덥습니다. 시원하게 입으시는 게 좋겠어요.")
        elif temp <= -2:
            weather_msgs.append(f"현재 영하 {abs(int(temp))}도로 매우 춥습니다. 옷을 두껍게 입고 목도리도 챙기세요.")
        elif temp <= 3:
            weather_msgs.append(f"현재 {int(temp)}도로 쌀쌀합니다. 코트나 패딩을 입으시는 게 좋겠어요.")

    # 날씨 멘트가 있으면 최상단에 추가
    if weather_msgs:
        points.extend(weather_msgs)

    # 2. 출발 추천
    points.append(f"{depart_in}분 후 출발을 추천합니다.")
    
    # 3. 요약 생성
    summary = "오늘의 외출 준비를 도와드릴게요."
    if weather.get("is_rain") or weather.get("is_snow"):
        summary = "비나 눈이 오는 날이네요. 안전에 유의하세요."
    elif temp is not None and (temp >= 30 or temp <= 0):
        summary = "날씨가 극단적입니다. 건강 관리에 유의하세요."

    return {"summary": summary, "action_points": points}