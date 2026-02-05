# smartmirror_pi5/logic/commute_probability.py
"""
대중교통별 정시 도착 확률 계산 모듈
버스, 지하철, 택시 각각의 정시 도착 확률을 정규분포 기반으로 계산합니다.
"""
import math
from typing import Optional, Dict
from dataclasses import dataclass, asdict


@dataclass
class ModeResult:
    ok: bool
    mode: str
    mean_min: float = 0.0
    std_min: float = 0.0
    p_on_time: float = 0.0
    factors: list = None
    detail: dict = None
    error: str = ""
    
    def __post_init__(self):
        if self.factors is None:
            self.factors = []
        if self.detail is None:
            self.detail = {}


def ontime_prob(time_budget: float, mean: float, std: float) -> float:
    """
    정규분포 CDF를 사용하여 정시 도착 확률 계산
    time_budget: 남은 시간 (분)
    mean: 예상 소요 시간 평균 (분)
    std: 예상 소요 시간 표준편차 (분)
    
    P(소요시간 <= time_budget) = CDF((time_budget - mean) / std)
    """
    if std <= 0:
        std = 1.0
    z = (time_budget - mean) / std
    # 표준정규분포 CDF 근사 (에러함수 사용)
    return 0.5 * (1 + math.erf(z / math.sqrt(2)))


def compute_probabilities(
    time_budget_min: float,
    taxi_duration_min: Optional[float],
    taxi_distance_m: Optional[float],
    bus_wait_min: Optional[float],
    subway_wait_min: Optional[float],
    bus_available: bool = True,
    subway_available: bool = True,
    current_hour: int = 12,  # 현재 시간(0~23)으로 운행시간 판단
) -> Dict[str, dict]:
    """
    각 교통수단별 정시 도착 확률 계산
    
    Args:
        time_budget_min: 남은 시간 (목표 도착 시간 - 현재 시간) (분)
        taxi_duration_min: 카카오모빌리티 자동차 길찾기 소요시간(분) (택시 근사)
        taxi_distance_m: 택시 이동 거리 (미터)
        bus_wait_min: TAGO 정류장 도착정보에서 가장 빠른 도착(분), None이면 정보 없음
        subway_wait_min: 시간표 기반 다음 열차까지 대기(분), None이면 정보 없음
        bus_available: 버스 API 조회가 성공했는지 여부
        subway_available: 지하철 API 조회가 성공했는지 여부
        current_hour: 현재 시간 (0~23), 새벽 시간대 판단에 사용
    
    Returns:
        Dict[str, dict]: 각 교통수단별 결과
    """
    out: Dict[str, ModeResult] = {}
    
    # 새벽 시간대 (대중교통 미운행 시간): 00:00 ~ 05:29
    is_early_morning = current_hour < 6

    # ---- 택시 ----
    if taxi_duration_min is None:
        out["taxi"] = ModeResult(ok=False, mode="taxi", error="택시 소요시간을 구할 수 없음")
    else:
        mean = float(taxi_duration_min) + 3.0  # 호출/승차/신호 대기 약간 가산
        std = max(3.0, mean * 0.18)           # 택시는 변동성 낮음(대략 18%)
        p = ontime_prob(time_budget_min, mean, std)
        factors = []
        if mean > time_budget_min:
            factors.append("시간이 촉박")
        if taxi_distance_m and taxi_distance_m > 12000:
            factors.append("장거리 이동")
        out["taxi"] = ModeResult(
            ok=True, mode="taxi", mean_min=round(mean, 1), std_min=round(std, 1),
            p_on_time=round(p, 3), factors=factors, detail={"base_drive_min": taxi_duration_min}
        )

    # 버스/지하철은 택시 시간 기반 근사 필요
    base = float(taxi_duration_min) if taxi_duration_min is not None else None

    # ---- 버스 ----
    if base is None:
        out["bus"] = ModeResult(ok=False, mode="bus", error="버스 근사 계산에 필요한 기준(택시시간)이 없음")
    elif is_early_morning and (not bus_available or bus_wait_min is None):
        # 새벽 시간대 + 정보 없음 → 운행 없음
        out["bus"] = ModeResult(
            ok=True, mode="bus", mean_min=0.0, std_min=0.0,
            p_on_time=0.0,
            factors=["현재 버스 운행 없음 (새벽 시간대)"],
            detail={"not_operating": True}
        )
    else:
        # 일반 시간대 or 실시간 정보 있음
        walk_to_stop = 4.0  # 집→정류장 보행 근사
        if bus_wait_min is not None:
            wait = float(bus_wait_min)
            wait_estimated = False
        else:
            wait = 8.0  # 정보 없으면 평균 대기시간 사용
            wait_estimated = True
        in_vehicle = base * 1.55 + 6.0  # 정차/우회/환승 리스크 포함 근사
        mean = walk_to_stop + wait + in_vehicle
        std = max(5.0, mean * 0.30)     # 버스는 변동성 큼(30%)
        p = ontime_prob(time_budget_min, mean, std)

        factors = []
        if wait_estimated:
            factors.append("실시간 정보 없음 (평균 대기시간 사용)")
        if wait >= 10:
            factors.append("버스 대기 길음")
        if mean > time_budget_min:
            factors.append("시간이 촉박")
        out["bus"] = ModeResult(
            ok=True, mode="bus", mean_min=round(mean, 1), std_min=round(std, 1),
            p_on_time=round(p, 3),
            factors=factors,
            detail={"walk_to_stop": walk_to_stop, "wait_min": round(wait, 1), "in_vehicle_min": round(in_vehicle, 1), "wait_estimated": wait_estimated}
        )

    # ---- 지하철 ----
    if base is None:
        out["subway"] = ModeResult(ok=False, mode="subway", error="지하철 근사 계산에 필요한 기준(택시시간)이 없음")
    elif is_early_morning and (not subway_available or subway_wait_min is None):
        # 새벽 시간대 + 정보 없음 → 운행 없음
        out["subway"] = ModeResult(
            ok=True, mode="subway", mean_min=0.0, std_min=0.0,
            p_on_time=0.0,
            factors=["현재 지하철 운행 없음 (새벽 시간대)"],
            detail={"not_operating": True}
        )
    else:
        # 일반 시간대 or 실시간 정보 있음
        walk_to_station = 7.0
        if subway_wait_min is not None:
            wait = float(subway_wait_min)
            wait_estimated = False
        else:
            wait = 6.0  # 정보 없으면 평균 대기시간 사용
            wait_estimated = True
        in_vehicle = base * 1.25 + 5.0  # 지하철은 비교적 일정 (버스보다 낮게)
        mean = walk_to_station + wait + in_vehicle
        std = max(4.0, mean * 0.22)     # 지하철 변동성 중간(22%)
        p = ontime_prob(time_budget_min, mean, std)

        factors = []
        if wait_estimated:
            factors.append("실시간 정보 없음 (평균 대기시간 사용)")
        if wait >= 8:
            factors.append("다음 열차까지 대기")
        if mean > time_budget_min:
            factors.append("시간이 촉박")
        out["subway"] = ModeResult(
            ok=True, mode="subway", mean_min=round(mean, 1), std_min=round(std, 1),
            p_on_time=round(p, 3),
            factors=factors,
            detail={"walk_to_station": walk_to_station, "wait_min": round(wait, 1), "in_vehicle_min": round(in_vehicle, 1), "wait_estimated": wait_estimated}
        )

    # dict로 변환
    return {k: asdict(v) for k, v in out.items()}

