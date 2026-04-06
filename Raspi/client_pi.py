import socketio
import time
import random
import threading
from datetime import datetime

# Socket.IO 클라이언트 설정
sio = socketio.Client()

# 관리자 PC 서버 주소 (실제 관리자 PC의 IP 주소로 변경 필요)
SERVER_URL = 'http://192.168.0.10:5000'

# 1. 스레드 1개가 담당할 '가상 장비 1대'의 동작 로직
def simulate_machine(device_id, batch_id):
    print(f"[{device_id}] 개별 가동 시작...")
    
    # 100개의 가상 검사 데이터 생성 및 전송
    for i in range(1, 101):
        # 98% 확률로 OK, 2% 확률로 NG 판정
        result = "OK" if random.random() > 0.02 else "NG"
        
        payload = {
            "header": {
                "msg_type": "DATA",
                "device_id": device_id,
                "batch_id": batch_id
            },
            "body": {
                "sequence": i,
                "machine_status": "RUN",
                "test_result": result,
                "timestamp": datetime.now().strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]
            }
        }
        
        # 서버로 실시간 데이터 전송
        sio.emit('device_data', payload)
        
        # 실제 공정 속도 체감을 위한 지연 시간 (0.1초)
        time.sleep(0.1) 
        
    # 100개 완료 후 장비별 완료 신호 전송
    sio.emit('batch_complete', {"device_id": device_id, "batch_id": batch_id, "status": "FINISHED"})
    print(f"[{device_id}] 검사 완료!")

@sio.event
def connect():
    print("✅ 관리자 PC 서버에 연결되었습니다.")

# 2. 관리자 PC에서 특정 장비의 검사 시작 명령이 들어왔을 때 실행
@sio.on('start_request')
def on_start(data):
    # 관리자 PC에서 보내준 '특정 장비 ID' 추출
    target_device = data.get('device_id', 'UNKNOWN_DEVICE') 
    batch_id = data.get('batch_id', 'BATCH_DEFAULT')
    
    print(f"\n--- [{target_device}] 검사 시작 명령 수신 ---")
    
    # 해당 장비 번호를 달고 독립적인 스레드 1개 생성 및 실행
    t = threading.Thread(target=simulate_machine, args=(target_device, batch_id))
    t.start()

@sio.event
def disconnect():
    print("❌ 관리자 PC 서버와 연결이 끊어졌습니다.")

# 3. 메인 실행부: 서버 연결 시도 및 대기
if __name__ == '__main__':
    try:
        print(f"서버({SERVER_URL}) 접속 시도 중...")
        sio.connect(SERVER_URL)
        sio.wait()
    except Exception as e:
        print(f"연결 실패: {e}")