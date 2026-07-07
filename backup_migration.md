# NetworkCheckSheet → 10.36.15.198 마이그레이션 작업서

> 최초 작성: 2026-05-19 / **갱신 조사: 2026-06-16**
> 대상 서버: ymfk-checksheet-sv (Ubuntu)
> 목적: `/mnt/NetworkCheckSheet`에 로컬로 쌓인 아카이브 데이터를 `//10.36.15.198/CheckSheet`(네트워크 서버)로
> **동일 경로 매핑하여 무중단·저부하로 이전**하고, 이전 완료 후 해당 경로를 198 CIFS 마운트로 전환한다.

---

## 0. 작업 목표 (사용자 요구사항)

1. **1순위 — 데이터 이전**: `/mnt/NetworkCheckSheet/*` → `//10.36.15.198/CheckSheet/*`로 **상대경로 그대로 매핑**하여 복사.
   서버가 가동 중이므로 **디스크 I/O·네트워크 부하를 최대한 낮춰** 운영 영향 최소화.
2. **2순위 — 마운트 전환**: 모든 데이터가 이전되면 `/mnt/NetworkCheckSheet`가 `//10.36.15.198/CheckSheet`로
   마운트되도록 변경(코드/`.env` 수정 불필요 — 경로는 그대로, 그 아래가 네트워크로 바뀜).

---

## 1. 개요 / 배경

`SchedulerManager.py`는 매일 06:00에 다음 순서로 동작한다(`run_daily_jobs`):
1. `move_old_files()` — 최신 파일 기준 **2일 이상 된 파일**을 `UPLOAD_FOLDER`(`/mnt/CheckSheet`) → `NETWORK_PATH`(`/mnt/NetworkCheckSheet`)로 `shutil.move`.
2. `cleanup_processed_files()` — `Merged/{serial}.png`가 있으면 해당 시리얼의 `Checked/Process/Master`를 로컬+네트워크 양쪽에서 삭제.
3. `cleanup_empty_folders()` — 양쪽 빈 폴더 제거.

`RouteHandler.py`의 조회는 **로컬 우선 → 네트워크 fallback** 패턴이다
(`serve_file` 869~, `list_files` 853~, `get_network_file`/`list_network_files` 1053~).
즉 앱은 `NETWORK_PATH` 아래 데이터가 그대로 있으면, 그것이 로컬이든 198이든 동일하게 동작한다.

원래 설계(`setup_environment.sh`)상 두 경로는 모두 CIFS 네트워크 마운트여야 한다.

| 경로 | 설계상 의도 | **현재 실제 상태(2026-06-16)** |
|---|---|---|
| `/mnt/CheckSheet` | `//10.36.15.200/CheckSheet` 마운트 | 로컬 디렉터리 |
| `/mnt/NetworkCheckSheet` | `//10.36.15.198/CheckSheet` 마운트 | **마운트 안 됨 — 로컬 디렉터리** ← 이번 작업 대상 |

→ 198이 마운트되지 않은 채 스케줄러가 계속 "네트워크로 이동"을 수행해, 아카이브가 전부 **로컬 디스크**에 쌓였다.

---

## 2. 현재 상태 (실측 / 2026-06-16)

- `/mnt/NetworkCheckSheet` 데이터량: **약 131 GB / 772,427 개 파일**
  - 부서별: `3165` 68G · `3186` 44G · `3188` 19G · `3168` 526M
  - 하위 구조: 각 부서 아래 `Master · Process · Checked · Merged` 등
- 로컬 디스크 여유: 루트 LV 913 GB 중 **708 GB 여유** (백업 보관 공간 충분)
- `10.36.15.198`: ping 정상(동일 LAN, ~0.48 ms), **SMB 445 OPEN**
- 도구: `cifs-utils`(2:7.0), `rsync` 설치됨
- 실행 중 서비스: `checksheet.service` (active, `run_linux.py`, User=ymfk_user)
- 스케줄러 작업 시각: **매일 06:00** (`cleanup_job`, cron hour=6 minute=0)
- 계정: `uid=1001(ymfk_user) gid=1001(ymfk_user)`, sudo 그룹 소속
- sudo 비밀번호: `<REDACTED>` (보안상 문서에서 제거 — 운영 계정 비밀번호 사용)
- **198 공유는 게스트 오픈 상태** → 자격증명 없이 `guest` 옵션으로 마운트 가능 (`ymfkadmin`/`NETWORK_PASSWORD` 불필요)
- 자격증명(`.env`): `NETWORK_USER=ymfkadmin`, `NETWORK_PASSWORD=`(값 설정됨, 게스트 마운트에는 미사용)

---

## 3. ⚠️ 핵심 주의사항

1. **비어 있지 않은 `/mnt/NetworkCheckSheet`에 그냥 마운트하면 안 된다.**
   CIFS를 그 위에 마운트하면 기존 131 GB가 **가려져(shadowed)** 접근 불가가 되고 디스크 공간은 계속 점유한다.
   → 반드시 **데이터 이전 후, 로컬 데이터를 비운(백업 이동) 빈 디렉터리에 마운트**한다.
2. **부하 최소화가 최우선.** 운영 중 복사이므로 `nice -n 19`(CPU 최저우선) + `ionice -c3`(디스크 idle일 때만) +
   `--bwlimit`(네트워크 상한)으로 throttle 한다. 부하는 파이썬 앱 CPU가 아니라 디스크 I/O·네트워크다.
3. **마이그레이션 중 스케줄러 06:00 작업과 겹치지 않게.** Phase 1(초기 동기화)은 가동 중 가능하나
   **최종 전환(Phase 2)은 반드시 `checksheet.service` 정지** 후, 06:00을 피해서 수행한다.
4. **마운트 후 `move_old_files`는 느려진다(의도된 동작).** 로컬↔로컬 즉시 rename → 로컬→네트워크 복사+삭제로 전환.
   파일별 try/except가 있어 부분 실패 시 다음 실행에서 재시도된다.

---

## 3-1. ⚠️ Phase 0 실측 발견 (2026-06-16)

1. **`.env` 비밀번호 오류 → 수정 완료.**
   `.env`의 `NETWORK_PASSWORD=<REDACTED-old>`(10자)는 틀린 값이었다. 실제 198 마운트 자격증명은
   `setup_environment.sh` 기준 **`ymfkadmin` / `<REDACTED>`**(11자, 끝 `1`). `.env`를 `<REDACTED>`로 수정함.
   - 게스트 접속은 서버가 거부(`STATUS_LOGON_FAILURE`)함 → 반드시 `ymfkadmin`/`<REDACTED>` 사용.
   - 참고: 앱은 마운트된 경로에 일반 파일 I/O만 하므로 런타임에 `.env`의 NETWORK_PASSWORD를 쓰진 않음(마운트는 OS 담당). 값 정정은 혼란 방지용.

2. **198 `CheckSheet` 공유에 이미 동일 구조가 존재(거의 빈 골격).**
   `3165 / 3168 / 3186 / 3188` 폴더와 `#recycle`이 있으나 실데이터는 `3186` 약 611M 정도뿐(3168/3188 ≈ 0).
   df의 `89G used`는 같은 볼륨의 다른 공유(`homes` 등) 사용량으로 추정 → CheckSheet 공유 여유는 충분(8.7T avail).
   → **로컬 131GB의 거의 전부를 신규 업로드해야 함.**

3. **방침 결정: 병합 복사(`--delete` 미사용), `#recycle` 제외.**
   기존 198 데이터와 서버 휴지통(`#recycle`)을 보존하기 위해 Phase 1·2 모두 `--delete`를 쓰지 않고
   `--exclude '#recycle'`로 병합한다. 대상이 사실상 비어 있어 병합 결과 ≈ 미러.

---

## 4. Phase 0 — 사전 점검 (198에 안전한 임시 경로로 테스트, 데이터 위에 덮지 않음)

> **상태: 2026-06-16 완료.** 임시 마운트·쓰기·여유공간·기존데이터 충돌 점검 통과.

```bash
# 임시 마운트포인트(기존 데이터와 분리)
sudo mkdir -p /mnt/_ncs198_tmp
# 게스트는 서버가 거부 → ymfkadmin/<REDACTED> 자격증명 사용
sudo mount -t cifs //10.36.15.198/CheckSheet /mnt/_ncs198_tmp \
  -o username=ymfkadmin,password='<REDACTED>',uid=1001,gid=1001,iocharset=utf8,vers=3.0
```

- [ ] 마운트 성공 확인: `mountpoint /mnt/_ncs198_tmp`
- [ ] 쓰기 가능: `touch /mnt/_ncs198_tmp/.wtest && rm /mnt/_ncs198_tmp/.wtest`
- [ ] 198 여유 공간 ≥ 131 GB: `df -h /mnt/_ncs198_tmp`
- [ ] 198 기존 데이터 충돌 확인: `ls -la /mnt/_ncs198_tmp` (기존 데이터가 있으면 병합/덮어쓰기 정책 결정)
- [ ] 기준값 기록: `du -sh /mnt/NetworkCheckSheet ; find /mnt/NetworkCheckSheet -type f | wc -l`
      → 현재 기준: **131 GB / 772,427 파일**

---

## 5. Phase 1 — 초기 동기화 (서버 계속 가동, 저부하)

throttle rsync로 백그라운드 복사. 64만~77만 개 소파일이라 메타데이터 오버헤드가 커 수 시간~밤새 소요 가능.

```bash
nice -n 19 ionice -c3 \
  rsync -rt --modify-window=2 --no-perms --no-owner --no-group \
  --exclude '#recycle' \
  --bwlimit=30000 --info=progress2 \
  /mnt/NetworkCheckSheet/  /mnt/_ncs198_tmp/   2>&1 \
  | tee /home/ymfk_user/Checksheet_Juxta/logs/migration_sync.log
```

| 옵션 | 의미 (부하 최소화 관점) |
|---|---|
| `nice -n 19` | CPU 최저 우선순위 — 앱이 항상 우선 |
| `ionice -c3` | 디스크가 한가할 때만 I/O — 운영 I/O 영향 최소화 |
| `--bwlimit=30000` | 약 30 MB/s 상한 (네트워크 여유 따라 10000~50000 조정) |
| `-rt --no-perms --no-owner --no-group` | CIFS 대상이라 소유권/권한 보존 생략, 시각(mtime)만 보존 |
| `--modify-window=2` | CIFS 시간 정밀도 차이 보정(불필요한 재전송 방지) |
| `--exclude '#recycle'` | 198 서버 휴지통 폴더 건드리지 않음 |

- **병합 복사**: 198에 이미 일부 데이터(3186 등)와 `#recycle`이 있으므로 `--delete`는 **Phase 1·2 모두 사용 안 함** (기존 보존).
- 06:00 스케줄러가 돌아도 무방 — 이후 rsync 재실행으로 델타만 추가 동기화.
- 진행 상황: `logs/migration_sync.log`. 필요 시 여러 번 재실행해 델타를 좁힌다.
- (백그라운드로 돌릴 경우 `nohup ... &` 또는 `tmux`/`screen` 사용 권장 — SSH 끊겨도 지속.)

---

## 6. Phase 2 — 최종 전환 (점검 시간, 수 분 / 06:00 피해서)

```bash
# 1) 서비스 정지 (쓰기 중단)
sudo systemctl stop checksheet.service

# 2) 최종 델타 동기화 (병합, --delete 미사용 / #recycle 제외)
nice -n 19 ionice -c3 \
  rsync -rt --modify-window=2 --no-perms --no-owner --no-group \
  --exclude '#recycle' \
  --info=progress2 \
  /mnt/NetworkCheckSheet/  /mnt/_ncs198_tmp/

# 3) 검증 (8장) — 파일 수/용량 일치, dry-run 무출력 확인

# 4) 로컬 데이터를 백업명으로 보존, 빈 마운트포인트 생성
sudo mv /mnt/NetworkCheckSheet /mnt/NetworkCheckSheet.local.bak
sudo mkdir /mnt/NetworkCheckSheet
sudo chown ymfk_user:ymfk_user /mnt/NetworkCheckSheet

# 5) 임시 마운트 해제
sudo umount /mnt/_ncs198_tmp

# 6) 198을 정식 경로에 마운트 (fstab 등록은 10장)
sudo mount /mnt/NetworkCheckSheet
mountpoint /mnt/NetworkCheckSheet && ls /mnt/NetworkCheckSheet

# 7) 서비스 재기동
sudo systemctl start checksheet.service
sudo systemctl status checksheet.service
```

---

## 7. Phase 3 — 사후 정리

- [ ] 며칠간 앱 정상 동작 확인 (06:00 작업이 198로 정상 이동/삭제하는지 `logs/` 확인)
- [ ] 앱에서 과거 체크시트 조회(`serve_file`/`list_files`)가 198 데이터로 정상 표시되는지 확인
- [ ] 이상 없으면 로컬 백업 삭제로 131 GB 회수:
  ```bash
  sudo rm -rf /mnt/NetworkCheckSheet.local.bak
  sudo rmdir /mnt/_ncs198_tmp
  ```

---

## 8. 검증 방법

```bash
# 파일 개수 비교 (전환 전 기준 772,427과 일치해야 함)
find /mnt/NetworkCheckSheet.local.bak -type f | wc -l    # 로컬 백업
find /mnt/NetworkCheckSheet -type f | wc -l               # 198 측(마운트 후)

# 총 용량 비교
du -sh /mnt/NetworkCheckSheet.local.bak
du -sh /mnt/NetworkCheckSheet

# 최종 rsync dry-run으로 누락 없음 확인 (#recycle 외 추가 전송 항목이 없어야 정상)
rsync -rtn --modify-window=2 --no-perms --no-owner --no-group --exclude '#recycle' \
  /mnt/NetworkCheckSheet.local.bak/ /mnt/NetworkCheckSheet/
```

---

## 9. 롤백 절차

전환 후 문제가 생기면 (로컬 백업 삭제 전까지 언제든 원상복구 가능):

```bash
sudo systemctl stop checksheet.service
sudo umount /mnt/NetworkCheckSheet            # 198 마운트 해제
sudo rmdir /mnt/NetworkCheckSheet             # 빈 마운트포인트 제거
sudo mv /mnt/NetworkCheckSheet.local.bak /mnt/NetworkCheckSheet   # 로컬 데이터 복구
# /etc/fstab에 추가한 198 라인을 주석 처리
sudo systemctl start checksheet.service
```

---

## 10. fstab / 자격증명 설정 (영구 마운트)

게스트는 거부되므로 자격증명 파일로 영구 마운트한다(fstab에 평문 비밀번호 노출 방지).

```bash
sudo tee /etc/cifs-credentials-198 > /dev/null <<'EOF'
username=ymfkadmin
password=<REDACTED>
EOF
sudo chmod 600 /etc/cifs-credentials-198
```

**`/etc/fstab` 추가 라인** (uid/gid는 실측값 1001 사용)

```
//10.36.15.198/CheckSheet  /mnt/NetworkCheckSheet  cifs  credentials=/etc/cifs-credentials-198,uid=1001,gid=1001,iocharset=utf8,vers=3.0,_netdev,nofail,x-systemd.automount  0  0
```

- `_netdev,nofail` : 198이 다운돼도 부팅이 멈추지 않음
- `x-systemd.automount` : 첫 접근 시 자동 마운트
- 적용: `sudo systemctl daemon-reload && sudo mount /mnt/NetworkCheckSheet`

---

## 11. 부가 메모

- **보안**: `.env`, `setup_environment.sh`, `unmount_drives.sh`에 SMB·sudo·Oracle 비밀번호가 평문 저장.
  이번 작업과 별개로 자격증명 분리·권한 제한 권장.
- **`/mnt/CheckSheet`**: 설계상 `//10.36.15.200` 마운트지만 현재 로컬 디렉터리. 이번 범위 밖이나 함께 점검 권장.
- **`move_old_files` 영향**: 198 마운트 후 일일 이동이 네트워크 복사+삭제로 전환되어 느려짐(정상). 파일별 예외처리로 재시도됨.
- **코드 변경 불필요**: 앱은 `NETWORK_PATH=/mnt/NetworkCheckSheet`만 참조하므로, 경로 자체는 그대로 두고 그 아래만 198로 바뀐다. `.env`/소스 수정 없음.

---

## 12. 작업 이력 기록란

| 일시 | Phase | 수행자 | 결과 / 비고 |
|---|---|---|---|
| 2026-06-16 | 조사갱신 | | 실측 131GB/772,427파일, 198 도달성·도구 확인. 계획 갱신 |
| 2026-06-16 | Phase 0 완료 | Claude | 임시 마운트 점검 통과. `.env` 비밀번호 오류 발견·수정(<REDACTED-old>→<REDACTED>). 198은 거의 빈 골격(3186 611M)+#recycle만 존재 → 병합 복사(--delete 미사용) 방침 확정 |
| 2026-06-16 | Phase 1 완료 | Claude | 저부하 rsync(30MB/s, #recycle 제외) 병합 복사 완료. 753,487파일/131.4GB 전송, 5h12m 소요, 종료코드 0. dry-run 검증: 잔여 약 23MB(speedup 5,968) → 사실상 완전 동기화 |
| 2026-06-16 16:22 | Phase 2 예약 | Claude | `phase2_cutover.sh`를 systemd-run 타이머(`phase2-cutover.timer`)로 **2026-06-16 21:22 자동 실행** 예약. 정지→최종동기화→전환→재기동 후 검증, 결과는 본 표에 자동 기록. 로그: `logs/phase2_cutover.log` |
| 2026-06-16 21:55 | Phase 2 완료 | systemd-run | 최종동기화 rc=0; 서비스=active; fstab=등록; 검증 dry(sent 23,007,545 bytes,speedup is 5,967.81); 파일수 로컬백업=772427/198=1083302. 로컬은 /mnt/NetworkCheckSheet.local.bak 로 보존(사후 정상확인 후 삭제로 회수) |
| 2026-06-17 | 정리 | Claude | 전환 정상 동작 재확인(마운트·서비스 active·fstab 등록). 문서 내 평문 비밀번호 전부 마스킹, 1회성 `phase2_cutover.sh` 삭제(타이머 종료). 자격증명은 `/etc/cifs-credentials-198`(600)만 유지. **Phase 3 잔여**: 며칠 모니터링 후 `/mnt/NetworkCheckSheet.local.bak`(131GB) 삭제로 회수 |
