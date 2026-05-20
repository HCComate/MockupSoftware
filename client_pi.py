import socketio
import time
import random
import threading
from datetime import datetime
from error_loader import load_error_codes, filter_equipment_errors

# Socket.IO 클라이언트 설정
sio = socketio.Client()

# 관리자 PC 서버 주소 (로컬 테스트용)
SERVER_URL = 'http://localhost:5000'

# ── CSV에서 에러 코드 로드 ──
ALL_ERRORS = load_error_codes()                          # 전체 50개
EQUIPMENT_ERRORS = filter_equipment_errors(ALL_ERRORS)   # 공정 오류만 (HM, HV, HS, SV, SS)

# 비전 검사 결함과 매핑되는 에러 코드 (SV-PR-* 계열)
VISION_DEFECT_MAP = {
    "SV-PR-01": "MISSING",
    "SV-PR-02": "DENT",
    "SV-PR-03": "OPEN",
    "SV-PR-04": "CRACK",
    "SV-PR-05": "SCRATCH",
    "SV-PR-06": "MISALIGNED",
}

# 비전 결함이 아닌 공정 오류 (HM, HV, HS, SS 계열)
MACHINE_ERRORS = {
    code: info for code, info in EQUIPMENT_ERRORS.items()
    if not code.startswith("SV-PR-")
}

DIRECTIONS = ["TOP", "BOTTOM", "SIDE_LEFT", "SIDE_RIGHT"]
ZONES = ["ZONE_A1", "ZONE_A2", "ZONE_B1", "ZONE_B2", "ZONE_B3", "ZONE_C1"]

print(f"📋 에러 코드 로드 완료: 공정 오류 {len(EQUIPMENT_ERRORS)}개 (비전 {len(VISION_DEFECT_MAP)}개 + 장비 {len(MACHINE_ERRORS)}개)")


# ── 정상 데이터 생성 ──
def generate_ok_payload(device_id, batch_id, model_name, seq):
    """정상 검사 결과 payload 생성"""
    return {
        "header": {
            "device_id": device_id,
            "batch_id": batch_id,
            "model_name": model_name
        },
        "body": {
            "sequence": seq,
            "machine_status": "RUN",
            "status_info": [
                {
                    "code": "SV-PR-00",
                    "msg": "Vision Inspection OK",
                    "severity": "LOW",
                    "direction": "TOP",
                    "part_location": "ZONE_ALL",
                    "is_capture_required": False
                }
            ],
            "vision_result": {
                "result": "OK",
                "defect_type": "NONE",
                "confidence": round(random.uniform(0.95, 0.99), 2),
                "inspection_area": "ALL",
                "image_url": None
            },
            "sensor_data": {
                "temperature": round(random.uniform(35.0, 42.0), 1),
                "vibration_x": round(random.uniform(0.005, 0.03), 3),
                "vibration_y": round(random.uniform(0.005, 0.03), 3),
                "illumination": random.randint(1150, 1300)
            },
            "timestamp": datetime.now().strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]
        }
    }


# ── 오류 데이터 생성 ──
def generate_ng_payload(device_id, batch_id, model_name, seq):
    """NG 검사 결과 payload 생성 (CSV 기반 에러 코드 사용)"""

    # 70% 확률로 비전 결함, 30% 확률로 장비 오류
    if random.random() < 0.7 and VISION_DEFECT_MAP:
        error_code = random.choice(list(VISION_DEFECT_MAP.keys()))
        defect_type = VISION_DEFECT_MAP[error_code]
    else:
        error_code = random.choice(list(MACHINE_ERRORS.keys()))
        defect_type = "MACHINE_ERROR"

    primary_error = EQUIPMENT_ERRORS[error_code]

    # 15% 확률로 복합 오류 (2차 오류 추가)
    error_codes_to_use = [error_code]
    if random.random() < 0.15:
        # 1차 오류와 다른 코드에서 2차 오류 선택
        other_codes = [c for c in EQUIPMENT_ERRORS if c != error_code]
        if other_codes:
            error_codes_to_use.append(random.choice(other_codes))

    # status_info 배열 생성
    status_info = []
    for code in error_codes_to_use:
        err = EQUIPMENT_ERRORS[code]
        status_info.append({
            "code": err["code"],
            "msg": f"{err['name']} - {err['situation']}",
            "severity": err["severity"],
            "direction": random.choice(DIRECTIONS),
            "part_location": random.choice(ZONES),
            "is_capture_required": err["severity"] in ("HIGH", "CRITICAL")
        })

    # 심각도에 따른 센서 데이터 변동
    is_critical = primary_error["severity"] == "CRITICAL"
    temp_range = (55.0, 75.0) if is_critical else (40.0, 55.0)
    vib_range = (0.10, 0.25) if is_critical else (0.05, 0.15)

    return {
        "header": {
            "device_id": device_id,
            "batch_id": batch_id,
            "model_name": model_name
        },
        "body": {
            "sequence": seq,
            "machine_status": "ERROR",
            "status_info": status_info,
            "vision_result": {
                "result": "NG",
                "defect_type": defect_type,
                "confidence": round(random.uniform(0.70, 0.95), 2),
                "inspection_area": random.choice(ZONES),
                "image_url": f"http://192.168.0.15/images/{seq}_ng_{defect_type.lower()}.jpg"
            },
            "sensor_data": {
                "temperature": round(random.uniform(*temp_range), 1),
                "vibration_x": round(random.uniform(*vib_range), 3),
                "vibration_y": round(random.uniform(*vib_range), 3),
                "illumination": random.randint(900, 1200)
            },
            "timestamp": datetime.now().strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]
        }
    }


# ── 장비별 잠금 플래그 (CRITICAL 오류 시 서버에서 잠금 명령 수신) ──
device_locked = {}   # { "RASP_PI_01": True/False }


# ── 장비 시뮬레이션 메인 로직 ──
def simulate_machine(device_id, batch_id, model_name):
    """스레드 1개가 담당할 '가상 장비 1대'의 동작 로직"""
    print(f"[{device_id}] 개별 가동 시작 (모델: {model_name})...")

    for i in range(1, 101):
        # ⚡ 잠금 체크: 서버에서 CRITICAL 잠금 명령이 오면 즉시 검사 중단
        if device_locked.get(device_id, False):
            print(f"🛑 [{device_id}] CRITICAL 오류로 검사 강제 중단됨 ({i-1}/100)")
            return  # batch_complete를 보내지 않고 종료

        # 98% 확률로 OK, 2% 확률로 NG 판정
        if random.random() > 0.02:
            payload = generate_ok_payload(device_id, batch_id, model_name, i)
        else:
            payload = generate_ng_payload(device_id, batch_id, model_name, i)

        # 서버로 실시간 데이터 전송
        sio.emit('device_data', payload)

        # 실제 공정 속도 체감을 위한 지연 시간 (0.1초)
        time.sleep(0.1)

    # 100개 완료 후 장비별 완료 신호 전송
    sio.emit('batch_complete', {
        "device_id": device_id,
        "batch_id": batch_id,
        "model_name": model_name,
        "status": "FINISHED"
    })
    print(f"[{device_id}] 검사 완료!")


@sio.event
def connect():
    print("✅ 관리자 PC 서버에 연결되었습니다.")


# 관리자 PC에서 특정 장비의 검사 시작 명령이 들어왔을 때 실행
@sio.on('start_request')
def on_start(data):
    target_device = data.get('device_id', 'UNKNOWN_DEVICE')
    batch_id = data.get('batch_id', 'BATCH_DEFAULT')
    model_name = data.get('model_name', 'MODEL_DEFAULT')

    print(f"\n--- [{target_device}] 검사 시작 명령 수신 (모델: {model_name}) ---")

    t = threading.Thread(
        target=simulate_machine,
        args=(target_device, batch_id, model_name)
    )
    t.start()


# ── 서버로부터 장비 잠금 명령 수신 (CRITICAL 오류 발생 시) ──
@sio.on('device_lock')
def on_device_lock(data):
    device_id = data.get('device_id')
    device_locked[device_id] = True
    print(f"🔒 [{device_id}] 서버로부터 긴급 정지 명령 수신! 장비 잠금됨.")


# ── 서버로부터 장비 잠금 해제 명령 수신 (모바일 앱에서 확인 시) ──
@sio.on('device_unlock')
def on_device_unlock(data):
    device_id = data.get('device_id')
    resolved_by = data.get('resolved_by', '알 수 없음')
    device_locked[device_id] = False
    print(f"🔓 [{device_id}] 장비 잠금 해제됨! (해제자: {resolved_by}) 재가동 가능.")


@sio.event
def disconnect():
    print("❌ 관리자 PC 서버와 연결이 끊어졌습니다.")


# 메인 실행부: 서버 연결 시도 및 대기
if __name__ == '__main__':
    try:
        print(f"서버({SERVER_URL}) 접속 시도 중...")
        sio.connect(SERVER_URL)
        sio.wait()
    except Exception as e:
        print(f"연결 실패: {e}")