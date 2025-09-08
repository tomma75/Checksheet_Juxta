#!/bin/bash

# 색상 정의
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}  Checksheet Juxta 환경 설정 스크립트${NC}"
echo -e "${GREEN}========================================${NC}"

# 변수 설정
SUDO_PASSWORD="1234"
NETWORK_USER="ymfkadmin"
NETWORK_PASSWORD="Supervis0r1"
UPLOAD_SERVER="10.36.15.200"
NETWORK_SERVER="10.36.15.198"
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )"

# 1. 마운트 디렉토리 생성
echo -e "\n${YELLOW}[1/6] 마운트 디렉토리 생성 중...${NC}"
echo $SUDO_PASSWORD | sudo -S mkdir -p /mnt/CheckSheet /mnt/NetworkCheckSheet
if [ $? -eq 0 ]; then
    echo -e "${GREEN}✓ 디렉토리 생성 완료${NC}"
else
    echo -e "${RED}✗ 디렉토리 생성 실패${NC}"
    exit 1
fi

# 2. 기존 마운트 해제 (있을 경우)
echo -e "\n${YELLOW}[2/6] 기존 마운트 해제 중...${NC}"
echo $SUDO_PASSWORD | sudo -S umount /mnt/CheckSheet 2>/dev/null
echo $SUDO_PASSWORD | sudo -S umount /mnt/NetworkCheckSheet 2>/dev/null
echo -e "${GREEN}✓ 기존 마운트 해제 완료${NC}"

# 3. 네트워크 드라이브 마운트
echo -e "\n${YELLOW}[3/6] 네트워크 드라이브 마운트 중...${NC}"

# UPLOAD_FOLDER 마운트
echo "  - UPLOAD_FOLDER (${UPLOAD_SERVER}/CheckSheet) 마운트 중..."
echo $SUDO_PASSWORD | sudo -S mount -t cifs //${UPLOAD_SERVER}/CheckSheet /mnt/CheckSheet \
    -o username=${NETWORK_USER},password=${NETWORK_PASSWORD},uid=$(id -u),gid=$(id -g),iocharset=utf8

if [ $? -eq 0 ]; then
    echo -e "  ${GREEN}✓ UPLOAD_FOLDER 마운트 성공${NC}"
else
    echo -e "  ${RED}✗ UPLOAD_FOLDER 마운트 실패${NC}"
    exit 1
fi

# NETWORK_PATH 마운트
echo "  - NETWORK_PATH (${NETWORK_SERVER}/CheckSheet) 마운트 중..."
echo $SUDO_PASSWORD | sudo -S mount -t cifs //${NETWORK_SERVER}/CheckSheet /mnt/NetworkCheckSheet \
    -o username=${NETWORK_USER},password=${NETWORK_PASSWORD},uid=$(id -u),gid=$(id -g),iocharset=utf8

if [ $? -eq 0 ]; then
    echo -e "  ${GREEN}✓ NETWORK_PATH 마운트 성공${NC}"
else
    echo -e "  ${RED}✗ NETWORK_PATH 마운트 실패${NC}"
    exit 1
fi

# 마운트 확인
echo -e "\n${YELLOW}[4/6] 마운트 상태 확인${NC}"
df -h | grep -E "CheckSheet|Filesystem" | while read line; do
    echo "  $line"
done

# 4. Oracle Instant Client 환경변수 설정
echo -e "\n${YELLOW}[5/6] Oracle Instant Client 환경 설정 중...${NC}"
export LD_LIBRARY_PATH=${SCRIPT_DIR}/instantclient_21_7:$LD_LIBRARY_PATH
export PATH=${SCRIPT_DIR}/instantclient_21_7:$PATH
echo -e "${GREEN}✓ Oracle 환경변수 설정 완료${NC}"
echo "  LD_LIBRARY_PATH: ${SCRIPT_DIR}/instantclient_21_7"

# 5. Python 가상환경 활성화 및 서버 실행
echo -e "\n${YELLOW}[6/6] Python 가상환경 활성화 및 서버 시작...${NC}"

# 가상환경 존재 확인
if [ ! -d "${SCRIPT_DIR}/venv" ]; then
    echo -e "${RED}✗ 가상환경을 찾을 수 없습니다: ${SCRIPT_DIR}/venv${NC}"
    echo "  python3 -m venv venv 명령으로 가상환경을 먼저 생성해주세요."
    exit 1
fi

echo -e "${GREEN}✓ 가상환경 발견${NC}"
echo ""
echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}  환경 설정 완료! 서버를 시작합니다...${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""

# 서버 실행 (sudo 권한으로, 환경변수 유지)
cd ${SCRIPT_DIR}
echo $SUDO_PASSWORD | sudo -S -E env \
    LD_LIBRARY_PATH=${SCRIPT_DIR}/instantclient_21_7:$LD_LIBRARY_PATH \
    PATH=${SCRIPT_DIR}/instantclient_21_7:$PATH \
    ${SCRIPT_DIR}/venv/bin/python ${SCRIPT_DIR}/run_linux.py