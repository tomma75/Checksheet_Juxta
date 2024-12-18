@echo on
setlocal enabledelayedexpansion

:: ===== 초기 설정 =====
:: 로컬과 네트워크 기본 경로 설정
:: %~dp0는 현재 배치 파일이 있는 디렉토리의 경로를 의미
set "LOCAL_BASE=%~dp0CheckSheet"
:: 네트워크 공유 폴더 경로 설정
set "NETWORK_BASE=\\10.36.15.198\CheckSheet"

:: ===== 최신 파일 날짜 찾기 =====
set "LATEST_DATE=0"
for /r "%LOCAL_BASE%" %%F in (*.*) do (
    for /f "tokens=1-3 delims=- " %%a in ('echo %%~tF') do (
        set "YEAR=%%a"
        set "MONTH=%%b"
        set "DAY=%%c"
        set /a "FILE_DATE=!YEAR!*10000 + !MONTH!*100 + !DAY!"
        if !FILE_DATE! GTR !LATEST_DATE! (
            set "LATEST_DATE=!FILE_DATE!"
        )
    )
)

:: ===== 기준일 계산 =====
:: 최신 파일 날짜에서 2일을 뺌 (200은 2일을 의미)
set /a TARGET_DATE=!LATEST_DATE! - 200

:: ===== 파일 처리 시작 =====
:: 모든 파일을 재귀적으로 처리
for /r "%LOCAL_BASE%" %%F in (*.*) do (
    echo Processing file: %%F
    
    :: 파일의 전체 경로에서 상대 경로 추출
    :: LOCAL_BASE를 제거하여 상대 경로만 남김
    set "FULL_PATH=%%F"
    set "REL_PATH=!FULL_PATH:%LOCAL_BASE%=!"
    
    :: 현재 처리중인 파일의 날짜 정보 추출
    for /f "tokens=1-3 delims=- " %%a in ('echo %%~tF') do (
        set "YEAR=%%a"
        set "MONTH=%%b"
        set "DAY=%%c"
        set /a "CURRENT_FILE_DATE=!YEAR!*10000 + !MONTH!*100 + !DAY!"
        
        :: 파일이 기준일보다 오래된 경우 처리
        if !CURRENT_FILE_DATE! LSS !TARGET_DATE! (
            :: 네트워크 대상 경로 생성
            set "TARGET_PATH=%NETWORK_BASE%!REL_PATH!"
            
            :: 대상 폴더 존재 여부 확인 및 생성
            :: %%~dpD는 드라이브 문자와 경로를 반환
            for %%D in ("!TARGET_PATH!\.") do (
                if not exist "%%~dpD" mkdir "%%~dpD"
            )
            
            :: 대상 경로에 파일이 없는 경우에만 이동
            if not exist "!TARGET_PATH!" (
                echo Moving file to: !TARGET_PATH!
                :: 파일 이동 실행
                move "%%F" "!TARGET_PATH!"
                :: 이동 결과 확인
                if errorlevel 1 (
                    echo Error moving file: %%F
                ) else (
                    :: %%~nxF는 파일명과 확장자만 반환
                    echo Successfully moved: %%~nxF
                )
            )
        )
    )
)

:: ===== 작업 완료 =====
echo File moving process completed.
:: 사용자가 결과를 확인할 수 있도록 일시 정지
pause