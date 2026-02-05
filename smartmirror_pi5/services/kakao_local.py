import requests
import logging

logger = logging.getLogger(__name__)

def search_keyword(api_key: str, query: str, x: float = None, y: float = None) -> dict:
    """
    카카오 로컬 API - 키워드 검색 (하이브리드 정렬)
    
    정렬 로직:
    1. API에서 accuracy(정확도) 기준으로 검색
    2. 결과를 재정렬: 검색어로 시작하는 장소 > 검색어 포함 장소
    
    Args:
        api_key: 카카오 REST API 키
        query: 검색어 (예: "서울역", "강남역", "롯데타워")
        x: 중심 경도 (검색 범위용, 선택)
        y: 중심 위도 (검색 범위용, 선택)
    
    Returns:
        {
            "ok": True/False,
            "places": [{"name": str, "address": str, "lat": float, "lon": float}, ...],
            "error": str (실패 시)
        }
    """
    if not api_key:
        return {"ok": False, "error": "No API Key"}
    
    if not query or not query.strip():
        return {"ok": False, "error": "Empty query"}
    
    query = query.strip()
    
    url = "https://dapi.kakao.com/v2/local/search/keyword.json"
    headers = {
        "Authorization": f"KakaoAK {api_key}"
    }
    params = {
        "query": query,
        "size": 10,  # 더 많은 결과를 가져와서 재정렬
        "sort": "accuracy"  # 정확도 기준 정렬
    }
    
    # 중심 좌표가 있으면 검색 범위 힌트로 사용
    if x is not None and y is not None:
        params["x"] = x
        params["y"] = y
    
    try:
        res = requests.get(url, headers=headers, params=params, timeout=5)
        
        if res.status_code != 200:
            logger.error(f"[Kakao Local API] HTTP {res.status_code}: {res.text}")
            return {"ok": False, "error": f"HTTP {res.status_code}"}
        
        data = res.json()
        documents = data.get("documents", [])
        
        if not documents:
            return {"ok": False, "error": "No results found", "places": []}
        
        places = []
        for doc in documents:
            places.append({
                "name": doc.get("place_name", ""),
                "address": doc.get("road_address_name") or doc.get("address_name", ""),
                "lat": float(doc.get("y", 0)),
                "lon": float(doc.get("x", 0)),
                "category": doc.get("category_group_name", ""),
                "phone": doc.get("phone", "")
            })
        
        # 하이브리드 재정렬
        places = _rerank_places(places, query)
        
        # 상위 5개만 반환
        places = places[:5]
        
        return {
            "ok": True,
            "places": places,
            "total_count": data.get("meta", {}).get("total_count", len(places))
        }
        
    except Exception as e:
        logger.error(f"[Kakao Local API Error] {e}")
        return {"ok": False, "error": str(e)}


def _rerank_places(places: list, query: str) -> list:
    """
    검색 결과를 하이브리드 방식으로 재정렬
    
    우선순위:
    1. 이름이 검색어로 시작하는 경우 (최우선)
    2. 이름이 검색어와 정확히 일치하는 경우 (최우선)
    3. 이름에 검색어가 포함된 경우 (중간)
    4. 나머지 (하위)
    """
    query_lower = query.lower()
    
    def get_priority(place):
        name = place.get("name", "").lower()
        
        # 정확히 일치
        if name == query_lower:
            return 0
        # 검색어로 시작
        if name.startswith(query_lower):
            return 1
        # 검색어 포함 (단어 시작 부분에서)
        if f" {query_lower}" in f" {name}" or query_lower in name:
            return 2
        # 나머지
        return 3
    
    return sorted(places, key=get_priority)


def search_address(api_key: str, query: str) -> dict:
    """
    카카오 로컬 API - 주소 검색
    도로명 주소나 지번 주소를 검색하여 좌표를 반환합니다.
    
    Args:
        api_key: 카카오 REST API 키
        query: 주소 (예: "서울시 중구 세종대로 110")
    
    Returns:
        {
            "ok": True/False,
            "lat": float,
            "lon": float,
            "address": str,
            "error": str (실패 시)
        }
    """
    if not api_key:
        return {"ok": False, "error": "No API Key"}
    
    if not query or not query.strip():
        return {"ok": False, "error": "Empty query"}
    
    url = "https://dapi.kakao.com/v2/local/search/address.json"
    headers = {
        "Authorization": f"KakaoAK {api_key}"
    }
    params = {
        "query": query
    }
    
    try:
        res = requests.get(url, headers=headers, params=params, timeout=5)
        
        if res.status_code != 200:
            logger.error(f"[Kakao Local API] HTTP {res.status_code}: {res.text}")
            return {"ok": False, "error": f"HTTP {res.status_code}"}
        
        data = res.json()
        documents = data.get("documents", [])
        
        if not documents:
            return {"ok": False, "error": "No results found"}
        
        doc = documents[0]
        address_info = doc.get("road_address") or doc.get("address", {})
        
        return {
            "ok": True,
            "lat": float(doc.get("y", 0)),
            "lon": float(doc.get("x", 0)),
            "address": doc.get("address_name", "")
        }
        
    except Exception as e:
        logger.error(f"[Kakao Local API Error] {e}")
        return {"ok": False, "error": str(e)}
