import builtins
import os
import runpy # <--- runpy 모듈을 추가합니다.

# 1. 원래의 내장 open 함수를 다른 이름으로 잠시 저장합니다.
original_open = builtins.open

# 2. 파일 경로를 변환하는 새로운 open 함수를 정의합니다.
def new_open(file, *args, **kwargs):
    if isinstance(file, str):
        # 윈도우 경로('\\')를 리눅스 경로('/')로 변환합니다.
        linux_path = file.replace('\\', os.sep)
        # 아래 print 문은 디버깅용입니다. 성공 후에는 주석 처리(#)하거나 삭제해도 좋습니다.
        # print(f"Path converted: '{file}' -> '{linux_path}'")
        return original_open(linux_path, *args, **kwargs)
    
    return original_open(file, *args, **kwargs)

# 3. 파이썬의 기본 내장 open 함수를 우리가 만든 new_open으로 교체합니다.
builtins.open = new_open

# 4. 'run_server.py'를 직접 실행한 것처럼 구동합니다.
#    이렇게 하면 'run_server.py' 내부의 if __name__ == "__main__": 블록이 실행됩니다.
print("Starting application with patched 'open' function...")
runpy.run_path('run_server.py', run_name='__main__')

