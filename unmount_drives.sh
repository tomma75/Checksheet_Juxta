#!/bin/bash

# 네트워크 드라이브 언마운트 스크립트
SUDO_PASSWORD="1234"

echo "네트워크 드라이브 언마운트 중..."

echo $SUDO_PASSWORD | sudo -S umount /mnt/CheckSheet
if [ $? -eq 0 ]; then
    echo "✓ /mnt/CheckSheet 언마운트 성공"
else
    echo "✗ /mnt/CheckSheet 언마운트 실패 (이미 언마운트되었을 수 있음)"
fi

echo $SUDO_PASSWORD | sudo -S umount /mnt/NetworkCheckSheet
if [ $? -eq 0 ]; then
    echo "✓ /mnt/NetworkCheckSheet 언마운트 성공"
else
    echo "✗ /mnt/NetworkCheckSheet 언마운트 실패 (이미 언마운트되었을 수 있음)"
fi

echo ""
echo "현재 마운트 상태:"
df -h | grep -E "CheckSheet|Filesystem"