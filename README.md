# HCComate - Raspi (Device Emulator)

현장에 설치된 비전 검사 장비(혹은 산업용 라즈베리 파이 엣지 컴퓨팅 노드)의 역할을 수행하는 Python 클라이언트 모듈입니다. 본 시스템에서는 실제 장비의 동작을 모사하는 에뮬레이터(`client_pi.py`)로 제공됩니다.

## 🛠 기술 스택

- **Language**: Python 3
- **Networking**: `python-socketio` (백엔드 서버와의 양방향 통신)
- **Data Loading**: `pandas` (가상 에러 데이터 및 센서 덤프 파일 로드용)

## ✨ 작동 방식 (가상 환경 시나리오)

1. **소켓 연결 및 대기**: 서버(`AdminPC Server`)에 소켓으로 연결한 후 대기 상태에 돌입합니다.
2. **연속 가동(Continuous Mode)**: 서버로부터 `start_continuous` 명령을 수신하면 스레드를 생성하여 무한 루프 검사를 시작합니다.
3. **가상 결함 주입 (Fault Injection)**:
   - 지정된 틱(Tick)마다 설정된 불량률(NG Ratio)에 기반하여 검사 결과를 생성합니다.
   - `error_code.csv` 등에서 정의된 치명적 결함(CRITICAL) 코드가 발생하면, 자체적으로 가동을 일시 중지하고 서버에 에러 상태를 보고합니다.
4. **명령 수신 및 가동 재개**: 잠금 해제(`device_unlock`) 및 가동 중지(`stop_continuous`) 명령을 실시간으로 수신하여 가동 상태를 변경합니다.

## 🚀 실행 방법

```bash
# 의존성 패키지 설치
pip install -r requirements.txt

# (선택) .env 설정을 통해 서버 IP 변경 가능
# SERVER_URL=http://<서버IP>:5000

# 에뮬레이터 실행
python client_pi.py
```
