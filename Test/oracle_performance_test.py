import cx_Oracle
import time
import random
from datetime import datetime, timedelta
from dotenv import load_dotenv
import os

def generate_test_data(num_records):
    data = []
    for i in range(num_records):
        # 7자리 랜덤 숫자 생성 (1000000 ~ 9999999)
        index_no = f"{random.randint(1000000, 9999999)}"
        
        # 2자리 랜덤 숫자 생성 (10 ~ 99)
        index_no_sfix = f"{random.randint(10, 99)}"
        
        # 'T1' 접두사와 6자리 랜덤 숫자로 시리얼 번호 생성
        serial_no = f"T1{random.randint(100000, 999999)}"
        
        # 'D' 접두사와 3자리 랜덤 숫자로 부서 코드 생성
        dept_code = f"D{random.randint(100, 999)}"
        
        # 'P' 접두사와 3자리 랜덤 숫자로 프로세스 코드 생성
        process_code = f"P{random.randint(100, 999)}"
        
        # 상태를 1 또는 2 중 랜덤 선택
        status = random.choice([1, 2])
        
        # 'E' 접두사와 4자리 랜덤 숫자로 직원 번호 생성
        emp_no = f"E{random.randint(1000, 9999)}"
        
        # 현재 날짜로부터 최대 1년 전까지의 랜덤 날짜 생성
        entry_d = datetime.now() - timedelta(days=random.randint(0, 365))
        
        # 'PC' 접두사와 3자리 랜덤 숫자로 입력 장치 ID 생성
        entry_by = f"PC{random.randint(100, 999)}"
        
        # 생성된 데이터를 튜플로 리스트에 추가
        data.append((index_no, index_no_sfix, serial_no, dept_code, process_code, status, emp_no, entry_d, entry_by))
    
    return data

def insert_test_data(connection, data):
    cursor = connection.cursor()
    sql = """
    INSERT INTO DCS_HISTORY 
    (INDEX_NO, INDEX_NO_SFIX, SERIAL_NO, DEPT_CODE, PROCESS_CODE, STATUS, EMP_NO, ENTRY_D, ENTRY_BY)
    VALUES (:1, :2, :3, :4, :5, :6, :7, :8, :9)
    """
    cursor.executemany(sql, data)
    connection.commit()
    cursor.close()

def monitor_performance(connection, test_function, test_name, data_count):
    cursor = connection.cursor()
    sql = """
    SELECT 
        (SELECT VALUE FROM V$SYSSTAT WHERE NAME = 'user commits') as user_commits,
        (SELECT VALUE FROM V$SYSSTAT WHERE NAME = 'physical reads') as physical_reads,
        (SELECT VALUE FROM V$SYSSTAT WHERE NAME = 'physical writes') as physical_writes
    FROM DUAL
    """
    start_time = time.time()
    initial_stats = cursor.execute(sql).fetchone()
    
    # 테스트 실행
    test_function()
    
    end_time = time.time()
    final_stats = cursor.execute(sql).fetchone()
    
    execution_time = end_time - start_time
    print(f"\n--- {test_name} 결과 ---")
    print(f"실행 시간: {execution_time:.2f} 초")
    print(f"실행된 SQL 수: {data_count}")  # 데이터 건수로 대체
    print(f"커밋 수: {final_stats[0] - initial_stats[0]}")
    
    cursor.close()
    return execution_time

def main():
    # 환경 변수 로드
    load_dotenv()

    # 데이터베이스 연결 정보
    user = str(os.getenv('NEURON_USER', 'default_user'))
    password = str(os.getenv('NEURON_PASSWORD', 'default_password'))
    host = str(os.getenv('NEURON_HOST', 'default_host'))
    port = str(os.getenv('NEURON_PORT', '1521'))
    service_name = str(os.getenv('NEURON_SERVICE_NAME', 'default_service_name'))

    # 연결 정보 출력 (디버깅용, 실제 사용 시 제거)
    print(f"Connecting with: user={user}, host={host}, port={port}, service_name={service_name}")

    # DSN 생성
    dsn = cx_Oracle.makedsn(host, port, service_name=service_name)

    # 데이터베이스 연결
    try:
        connection = cx_Oracle.connect(user=user, password=password, dsn=dsn)
        print("Database connection successful")
    except cx_Oracle.Error as error:
        print(f"Error connecting to Oracle database: {error}")
        return

    # 1건 테스트
    data_1 = generate_test_data(1)
    time_1 = monitor_performance(connection, lambda: insert_test_data(connection, data_1), "1건 테스트", 1)

    # 500건 테스트
    data_500 = generate_test_data(500)
    time_500 = monitor_performance(connection, lambda: insert_test_data(connection, data_500), "500건 테스트", 500)
    
    # 7만2천건 테스트
    data_72k = generate_test_data(72000)
    time_72k = monitor_performance(connection, lambda: insert_test_data(connection, data_72k), "7만2천건 테스트", 72000)
    
    # 결과 비교
    print("\n--- 테스트 결과 비교 ---")
    print(f"1건 처리 시간: {time_1:.2f} 초")
    print(f"500건 처리 시간: {time_500:.2f} 초")
    print(f"7만2천건 처리 시간: {time_72k:.2f} 초")
    print(f"1건 기준 초당 처리 건수: {1 / time_1:.2f}")
    print(f"500건 기준 초당 처리 건수: {500 / time_500:.2f}")
    print(f"7만2천건 기준 초당 처리 건수: {72000 / time_72k:.2f}")
    print(f"1건 테스트 단일 건 처리 시간: {time_1 * 1000:.2f} 밀리초")
    print(f"500건 테스트 단일 건 처리 시간: {(time_500 / 500) * 1000:.2f} 밀리초")
    print(f"7만2천건 테스트 단일 건 처리 시간: {(time_72k / 72000) * 1000:.2f} 밀리초")
    
    connection.close()

if __name__ == "__main__":
    main()