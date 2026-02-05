// ===== 페이지 로드 시 초기화 =====
document.addEventListener("DOMContentLoaded", function () {
  loadDefaultSubwaySchedule();
});

// 기본 지하철역 시간표 로드
async function loadDefaultSubwaySchedule() {
  try {
    // q 파라미터 없이 호출하면 Config.SUBWAY_STATION_NAME (기본: "부산") 사용
    const response = await fetch('/api/search_subway_station');
    const data = await response.json();

    if (data.ok && data.station) {
      updateSubwayInfo(data.station, data);
    } else {
      console.log("기본 지하철역 정보 없음:", data);
    }
  } catch (e) {
    console.error("기본 지하철역 로드 실패:", e);
  }
}

async function sendInteraction() {
  try {
    await fetch("/api/interaction", { method: "POST" });
  } catch (e) { }
}

// ===== 택시 목적지 자동완성 관련 변수 =====
let searchTimeout = null;
let cachedPlaces = [];

// ===== 버스 정류장 자동완성 관련 변수 =====
let busSearchTimeout = null;
let cachedStops = [];

// ===== 지하철역 자동완성 관련 변수 =====
let subwaySearchTimeout = null;
let cachedStations = [];

// 입력 시 자동완성 검색 (디바운스 적용)
function onDestinationInput() {
  const input = document.getElementById("destInput");
  const query = input.value.trim();

  // 이전 타이머 취소
  if (searchTimeout) {
    clearTimeout(searchTimeout);
  }

  // 2글자 미만이면 드롭다운 숨김
  if (query.length < 2) {
    hideDropdown();
    return;
  }

  // 300ms 후에 검색 (디바운스)
  searchTimeout = setTimeout(() => {
    searchPlaces(query);
  }, 300);
}

// 장소 검색 API 호출
async function searchPlaces(query) {
  const dropdown = document.getElementById("placeDropdown");
  const status = document.getElementById("voiceStatus");

  try {
    const response = await fetch(`/api/search_destination?q=${encodeURIComponent(query)}`);
    const data = await response.json();

    if (data.ok && data.all_places && data.all_places.length > 0) {
      cachedPlaces = data.all_places;
      showDropdown(cachedPlaces);
      status.textContent = `${cachedPlaces.length}개 결과`;
    } else {
      hideDropdown();
      status.textContent = data.error || "검색 결과 없음";
    }
  } catch (e) {
    status.textContent = `검색 오류: ${e.message}`;
    hideDropdown();
  }
}

// 드롭다운 표시
function showDropdown(places) {
  const dropdown = document.getElementById("placeDropdown");
  dropdown.innerHTML = "";

  places.forEach((place, index) => {
    const item = document.createElement("div");
    item.className = "dropdown-item";
    item.innerHTML = `
      <div class="item-name">${place.name}</div>
      <div class="item-address">${place.address}</div>
    `;
    item.onclick = () => selectPlace(index);
    dropdown.appendChild(item);
  });

  dropdown.style.display = "block";
}

// 드롭다운 숨김
function hideDropdown() {
  const dropdown = document.getElementById("placeDropdown");
  dropdown.style.display = "none";
  cachedPlaces = [];
}

// 장소 선택
async function selectPlace(index) {
  const place = cachedPlaces[index];
  if (!place) return;

  const input = document.getElementById("destInput");
  const status = document.getElementById("voiceStatus");

  input.value = "";
  hideDropdown();
  status.textContent = "택시 정보 조회 중...";

  // 선택된 장소로 택시 정보 조회
  try {
    const response = await fetch(`/api/search_destination?q=${encodeURIComponent(place.name)}`);
    const data = await response.json();

    if (data.ok) {
      // 메인 택시 정보 업데이트
      updateTaxiInfo(place, data.taxi);
      status.textContent = "";
    } else {
      status.textContent = `오류: ${data.error}`;
    }
  } catch (e) {
    status.textContent = `연결 오류: ${e.message}`;
  }
}

// 메인 택시 정보 업데이트
function updateTaxiInfo(place, taxi) {
  const destName = document.getElementById("currentDestName");
  const duration = document.getElementById("currentDuration");
  const fare = document.getElementById("currentFare");
  const distance = document.getElementById("currentDistance");

  destName.textContent = place.name;

  if (taxi && taxi.ok !== false) {
    duration.textContent = `${taxi.duration_min}분`;
    fare.textContent = `💰 ${taxi.taxi_fare.toLocaleString()}원`;
    if (distance) {
      distance.textContent = `📍 ${(taxi.distance_meter / 1000).toFixed(1)}km`;
    }
  } else {
    duration.textContent = "--";
    fare.textContent = "택시 정보 없음";
    if (distance) distance.textContent = "";
  }
}

// 결과 초기화 (페이지 새로고침으로 기본 목적지 복원)
function clearResult() {
  location.reload();
}

// 음성 목적지 검색
async function startVoiceSearch() {
  const btn = document.getElementById("voiceBtn");
  const status = document.getElementById("voiceStatus");
  const input = document.getElementById("destInput");

  btn.disabled = true;
  btn.textContent = "🎧";
  status.textContent = "마이크로 목적지를 말해주세요...";
  hideDropdown();

  try {
    const response = await fetch("/api/voice_destination", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ engine: "google", timeout: 5.0 })
    });

    const data = await response.json();

    if (data.ok) {
      // 음성 인식 결과를 입력창에 넣고 드롭다운 표시
      input.value = data.speech_text;
      status.textContent = `인식: "${data.speech_text}" - 아래에서 선택하세요`;

      if (data.all_places && data.all_places.length > 0) {
        cachedPlaces = data.all_places;
        showDropdown(cachedPlaces);
      }
    } else {
      status.textContent = `오류: ${data.error}`;
      if (data.speech_text) {
        input.value = data.speech_text;
        status.textContent += ` (인식: "${data.speech_text}")`;
      }
    }
  } catch (e) {
    status.textContent = `연결 오류: ${e.message}`;
  } finally {
    btn.disabled = false;
    btn.textContent = "🎙️";
  }
}

// 입력창 외부 클릭 시 드롭다운 닫기
document.addEventListener("click", function (e) {
  const taxiContainer = document.querySelector("#taxi-card .search-container");
  const busContainer = document.querySelector("#busSearchContainer");
  const subwayContainer = document.querySelector("#subwaySearchContainer");

  if (taxiContainer && !taxiContainer.contains(e.target)) {
    hideDropdown();
  }
  if (busContainer && !busContainer.contains(e.target)) {
    hideBusDropdown();
  }
  if (subwayContainer && !subwayContainer.contains(e.target)) {
    hideSubwayDropdown();
  }
});

// ===== 버스 정류장 검색 기능 =====

// 입력 시 정류장 검색 (디바운스 적용)
function onBusStopInput() {
  const input = document.getElementById("busStopInput");
  const query = input.value.trim();

  if (busSearchTimeout) {
    clearTimeout(busSearchTimeout);
  }

  if (query.length < 1) {
    hideBusDropdown();
    return;
  }

  // 300ms 후에 검색 (디바운스)
  busSearchTimeout = setTimeout(() => {
    searchBusStops(query);
  }, 300);
}

// 버스 정류장 검색 API 호출
async function searchBusStops(query) {
  const dropdown = document.getElementById("busStopDropdown");
  const status = document.getElementById("busStatus");

  try {
    const response = await fetch(`/api/search_bus_stop?q=${encodeURIComponent(query)}`);
    const data = await response.json();

    if (data.ok && data.all_stops && data.all_stops.length > 0) {
      cachedStops = data.all_stops;
      showBusDropdown(cachedStops);
      status.textContent = `${cachedStops.length}개 정류장`;
    } else {
      hideBusDropdown();
      status.textContent = data.error || "검색 결과 없음";
    }
  } catch (e) {
    status.textContent = `검색 오류: ${e.message}`;
    hideBusDropdown();
  }
}

// 버스 정류장 드롭다운 표시
function showBusDropdown(stops) {
  const dropdown = document.getElementById("busStopDropdown");
  dropdown.innerHTML = "";

  stops.forEach((stop, index) => {
    const item = document.createElement("div");
    item.className = "dropdown-item";
    // 정류장 번호(nodeNo) 표시
    const stopNo = stop.nodeNo ? `#${stop.nodeNo}` : "";
    item.innerHTML = `
      <div class="item-name">${stop.nodeNm || "이름 없음"} <span class="stop-no">${stopNo}</span></div>
    `;
    item.onclick = () => selectBusStop(index);
    dropdown.appendChild(item);
  });

  dropdown.style.display = "block";
}

// 버스 정류장 드롭다운 숨김
function hideBusDropdown() {
  const dropdown = document.getElementById("busStopDropdown");
  if (dropdown) {
    dropdown.style.display = "none";
  }
  cachedStops = [];
}

// 버스 정류장 선택
async function selectBusStop(index) {
  const stop = cachedStops[index];
  if (!stop) return;

  const input = document.getElementById("busStopInput");
  const status = document.getElementById("busStatus");

  input.value = "";
  hideBusDropdown();
  status.textContent = "도착 정보 조회 중...";

  try {
    const response = await fetch(`/api/search_bus_stop?nodeId=${encodeURIComponent(stop.nodeId)}&nodeNm=${encodeURIComponent(stop.nodeNm || "")}`);
    const data = await response.json();

    if (data.ok) {
      updateBusInfo(stop, data);
      status.textContent = "";
    } else {
      status.textContent = `오류: ${data.error}`;
    }
  } catch (e) {
    status.textContent = `연결 오류: ${e.message}`;
  }
}

// 버스 정보 업데이트
function updateBusInfo(stop, data) {
  const stopName = document.getElementById("currentStopName");
  const eta = document.getElementById("currentETA");
  const arrivals = document.getElementById("busArrivals");

  // 정류장 이름 + 번호 표시
  const stopNo = stop.nodeNo ? ` (#${stop.nodeNo})` : "";
  stopName.textContent = (stop.nodeNm || "정류장") + stopNo;
  eta.textContent = data.eta_min !== null ? `${data.eta_min}분` : "--";

  // 도착 버스 목록 업데이트 (종점명 표시)
  arrivals.innerHTML = "";
  if (data.arrivals && data.arrivals.length > 0) {
    data.arrivals.forEach(a => {
      const row = document.createElement("div");
      row.className = "row bus-row";
      // 종점명이 있으면 방면으로 표시
      const direction = a.endNodeNm ? `<span class="bus-direction">→${a.endNodeNm}</span>` : "";
      row.innerHTML = `
        <div class="left">
          <span class="bus-no">${a.routeNo || "--"}</span>
          ${direction}
        </div>
        <div class="right">${a.arrTimeMin !== null ? a.arrTimeMin + "분" : "--"}</div>
      `;
      arrivals.appendChild(row);
    });
  } else {
    arrivals.innerHTML = '<div class="sub">도착 예정 버스 없음</div>';
  }
}

// ===== 지하철역 검색 기능 =====

// 입력 시 지하철역 검색
function onSubwayInput() {
  const input = document.getElementById("subwayInput");
  const query = input.value.trim();

  if (subwaySearchTimeout) clearTimeout(subwaySearchTimeout);

  if (query.length < 1) {
    hideSubwayDropdown();
    return;
  }

  subwaySearchTimeout = setTimeout(() => {
    searchSubway(query);
  }, 300);
}

// 지하철역 검색 API 호출
async function searchSubway(query) {
  const dropdown = document.getElementById("subwayDropdown");

  try {
    const response = await fetch(`/api/search_subway_station?q=${encodeURIComponent(query)}`);
    const data = await response.json();

    if (data.ok && data.all_stations && data.all_stations.length > 0) {
      cachedStations = data.all_stations;
      showSubwayDropdown(cachedStations);
    } else {
      hideSubwayDropdown();
    }
  } catch (e) {
    console.error("Subway search error:", e);
    hideSubwayDropdown();
  }
}

// 지하철 드롭다운 표시
function showSubwayDropdown(stations) {
  const dropdown = document.getElementById("subwayDropdown");
  dropdown.innerHTML = "";

  stations.forEach((st, index) => {
    const item = document.createElement("div");
    item.className = "dropdown-item";
    item.innerHTML = `
      <div class="item-name">${st.subwayStationName} (${st.subwayRouteName})</div>
    `;
    item.onclick = () => selectSubwayStation(index);
    dropdown.appendChild(item);
  });

  dropdown.style.display = "block";
}

// 지하철 드롭다운 숨김
function hideSubwayDropdown() {
  const dropdown = document.getElementById("subwayDropdown");
  if (dropdown) dropdown.style.display = "none";
  cachedStations = [];
}

// 지하철역 선택
async function selectSubwayStation(index) {
  const station = cachedStations[index];
  if (!station) return;

  const input = document.getElementById("subwayInput");
  input.value = "";
  hideSubwayDropdown();

  // 역 정보 UI 업데이트 (임시)
  document.getElementById("currentSubwayStation").textContent = `${station.subwayStationName} 데이터 로딩중...`;

  try {
    const response = await fetch(`/api/search_subway_station?stationId=${encodeURIComponent(station.subwayStationId)}`);
    const data = await response.json();

    if (data.ok) {
      updateSubwayInfo(station, data);
    }
  } catch (e) {
    console.error("Subway select error:", e);
    document.getElementById("currentSubwayStation").textContent = "데이터 로딩 실패";
  }
}

// 지하철 정보 업데이트
function updateSubwayInfo(station, data) {
  const nameEl = document.getElementById("currentSubwayStation");
  const dayTypeEl = document.getElementById("subwayDayType");
  const upList = document.getElementById("subwayUpList");
  const downList = document.getElementById("subwayDownList");
  const mainEtaEl = document.getElementById("subwayNextETA");

  // 역 이름
  nameEl.textContent = `${station.subwayStationName} (${station.subwayRouteName})`;

  // 요일
  const dayCode = data.dayType; // 01:평일, 02:토요일, 03:공휴일
  let dayStr = "평일";
  if (dayCode === "02") dayStr = "토요일";
  if (dayCode === "03") dayStr = "공휴일";
  dayTypeEl.textContent = dayStr;

  // 리스트 렌더링 함수
  const renderList = (targetEl, list) => {
    targetEl.innerHTML = "";
    if (list && list.length > 0) {
      list.forEach(item => {
        const div = document.createElement("div");
        div.className = "row";
        // item: { depTime: "083000", endSubwayStationNm: "...", eta_min: 5 }
        const timeStr = item.depTime.substring(0, 2) + ":" + item.depTime.substring(2, 4);
        div.innerHTML = `
          <div class="left">${timeStr} <span style="font-size:0.85em; opacity:0.8">→${item.endSubwayStationNm}</span></div>
          <div class="right">${item.eta_min}분후</div>
        `;
        targetEl.appendChild(div);
      });
    } else {
      targetEl.innerHTML = '<div class="sub">운행 종료</div>';
    }
  };

  renderList(upList, data.schedule.U); // 상행
  renderList(downList, data.schedule.D); // 하행

  // 메인 ETA: 상행/하행 중 가장 가까운 열차
  const allTrains = [...(data.schedule.U || []), ...(data.schedule.D || [])];
  if (allTrains.length > 0) {
    const minEta = Math.min(...allTrains.map(t => t.eta_min));
    mainEtaEl.textContent = `${minEta}분`;
  } else {
    mainEtaEl.textContent = "--";
  }
}

// ===== (NEW) 도착시간 기반 확률 카드용 자동완성 =====
let searchTimeout2 = null;
let cachedPlaces2 = [];

function onDestinationInput2() {
  const input = document.getElementById("destInput2");
  const query = input.value.trim();

  if (searchTimeout2) clearTimeout(searchTimeout2);

  if (query.length < 2) {
    hideDropdown2();
    return;
  }

  searchTimeout2 = setTimeout(() => {
    searchPlaces2(query);
  }, 300);
}

async function searchPlaces2(query) {
  const dropdown = document.getElementById("placeDropdown2");

  try {
    const response = await fetch(`/api/search_destination?q=${encodeURIComponent(query)}`);
    const data = await response.json();

    if (data.ok && data.all_places && data.all_places.length > 0) {
      cachedPlaces2 = data.all_places;
      showDropdown2(cachedPlaces2);
    } else {
      hideDropdown2();
    }
  } catch (e) {
    console.error("Search error:", e);
    hideDropdown2();
  }
}

function showDropdown2(places) {
  const dropdown = document.getElementById("placeDropdown2");
  dropdown.innerHTML = "";

  places.forEach((place, index) => {
    const item = document.createElement("div");
    item.className = "dropdown-item";
    item.innerHTML = `
      <div class="item-name">${place.name}</div>
      <div class="item-address">${place.address}</div>
    `;
    item.onclick = () => selectPlace2(index);
    dropdown.appendChild(item);
  });

  dropdown.style.display = "block";
}

function hideDropdown2() {
  const dropdown = document.getElementById("placeDropdown2");
  if (!dropdown) return;
  dropdown.style.display = "none";
  dropdown.innerHTML = "";
}

function selectPlace2(index) {
  const p = cachedPlaces2[index];
  if (!p) return;

  document.getElementById("destInput2").value = p.name;
  document.getElementById("destLat2").value = p.lat;
  document.getElementById("destLon2").value = p.lon;
  document.getElementById("destName2").value = p.name;

  hideDropdown2();
}

// ===== (NEW) 확률 계산 =====
async function calcCommuteProb() {
  const resultEl = document.getElementById("probResult");

  const arrive = document.getElementById("arriveTime").value;
  const lat = parseFloat(document.getElementById("destLat2").value || "0");
  const lon = parseFloat(document.getElementById("destLon2").value || "0");
  const name = document.getElementById("destName2").value || document.getElementById("destInput2").value || "목적지";

  if (!arrive) {
    resultEl.textContent = "도착 시간을 먼저 선택해주세요.";
    return;
  }
  if (!lat || !lon) {
    resultEl.textContent = "목적지를 자동완성에서 선택해주세요 (좌표가 필요합니다).";
    return;
  }

  resultEl.textContent = "계산 중...";

  try {
    const res = await fetch("/api/commute_probability", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        arrive_hhmm: arrive,
        dest: { name, lat, lon }
      })
    });

    const data = await res.json();
    if (!data.ok) {
      resultEl.textContent = `오류: ${data.error || "unknown"}`;
      return;
    }

    const probs = data.probabilities || {};
    const fmt = (x) => (x == null ? "--" : Math.round(x * 100) + "%");

    // 운행 여부 확인 함수
    const getStatus = (p) => {
      if (!p || !p.ok) return { pct: "N/A", mean: null, note: "" };
      if (p.detail && p.detail.not_operating) {
        return { pct: "0%", mean: null, note: "운행없음" };
      }
      return { pct: fmt(p.p_on_time), mean: p.mean_min, note: "" };
    };

    const taxiS = getStatus(probs.taxi);
    const busS = getStatus(probs.bus);
    const subS = getStatus(probs.subway);

    const renderItem = (icon, mode, status, className) => {
      const meanText = status.mean != null ? `(평균 ${status.mean}분)` : "";
      const noteText = status.note ? `<span class="prob-note">${status.note}</span>` : "";
      return `<div class="prob-item ${className}">
        <span class="prob-mode">${icon} ${mode}</span> 
        <span class="prob-pct">${status.pct}</span> 
        <span class="prob-mean">${meanText}</span>
        ${noteText}
      </div>`;
    };

    resultEl.innerHTML = `
      <div class="prob-summary">지금 ${data.now} → 도착희망 ${data.arrive_hhmm} (남은시간: ${data.time_budget_min}분)</div>
      ${renderItem("🚕", "택시", taxiS, "taxi")}
      ${renderItem("🚌", "버스", busS, "bus")}
      ${renderItem("🚇", "지하철", subS, "subway")}
    `;

    // ===== Ambient Light Logic =====
    // 1. 유효한 p_on_time 중 최대값 찾기
    const validProbs = [];
    if (probs.taxi && probs.taxi.ok) validProbs.push(probs.taxi.p_on_time);
    if (probs.bus && probs.bus.ok && !probs.bus.detail?.not_operating) validProbs.push(probs.bus.p_on_time);
    if (probs.subway && probs.subway.ok && !probs.subway.detail?.not_operating) validProbs.push(probs.subway.p_on_time);

    // 초기화
    document.body.className = "";

    if (validProbs.length > 0) {
      const maxP = Math.max(...validProbs);
      console.log("Max Probability:", maxP);

      if (maxP >= 0.9) {
        document.body.classList.add("status-good");
      } else if (maxP >= 0.7) {
        document.body.classList.add("status-warning");
      } else {
        document.body.classList.add("status-critical");
      }
    }
    // ===============================
  } catch (e) {
    resultEl.textContent = `요청 실패: ${e.message}`;
  }
}

// destSearchContainer2 외부 클릭 시 드롭다운 닫기
document.addEventListener("click", function (e) {
  const container = document.getElementById("destSearchContainer2");
  if (container && !container.contains(e.target)) {
    hideDropdown2();
  }
});