import cx_Oracle
import time
import random
from datetime import datetime, timedelta
from dotenv import load_dotenv
import os
from concurrent.futures import ThreadPoolExecutor, as_completed

def single_record_update(connection):
    cursor = connection.cursor()
    index_no = f"{random.randint(1000000, 9999999)}"
    index_no_sfix = f"{random.randint(10, 99)}"
    sql = """
    UPDATE DCS_HISTORY 
    SET STATUS = :1
    WHERE INDEX_NO = :2 AND INDEX_NO_SFIX = :3
    """
    start_time = time.time()
    cursor.execute(sql, (random.choice([1, 2]), index_no, index_no_sfix))
    connection.commit()
    end_time = time.time()
    cursor.close()
    return end_time - start_time

def concurrent_updates(connection, num_updates):
    with ThreadPoolExecutor(max_workers=15) as executor:
        futures = [executor.submit(single_record_update, connection) for _ in range(num_updates)]
        results = [future.result() for future in as_completed(futures)]
    return results

def bulk_update(connection, num_records):
    cursor = connection.cursor()
    data = [(random.choice([1, 2]), f"{random.randint(1000000, 9999999)}", f"{random.randint(10, 99)}") for _ in range(num_records)]
    sql = """
    UPDATE DCS_HISTORY 
    SET STATUS = :1
    WHERE INDEX_NO = :2 AND INDEX_NO_SFIX = :3
    """
    start_time = time.time()
    cursor.executemany(sql, data)
    connection.commit()
    end_time = time.time()
    cursor.close()
    return end_time - start_time

def run_performance_tests(connection):
    print("\n--- 성능 테스트 결과 ---")

    # a. 단일 레코드 업데이트
    single_update_time = single_record_update(connection)
    print(f"a. 단일 레코드 업데이트: {single_update_time * 1000:.2f}ms")

    # b. 동시 업데이트 요청
    concurrent_update_times = concurrent_updates(connection, 15)
    print(f"b. 동시 업데이트 요청 (15개):")
    print(f"   평균 시간: {sum(concurrent_update_times) / len(concurrent_update_times) * 1000:.2f}ms")
    print(f"   최대 시간: {max(concurrent_update_times) * 1000:.2f}ms")

    # c. 대량 데이터 업데이트
    bulk_size = 72000
    bulk_update_time = bulk_update(connection, bulk_size)
    print(f"c. 대량 데이터 업데이트 ({bulk_size}건): {bulk_update_time:.2f}초")

    print("\n--- 검증 결과 ---")
    print(f"a. 단일 레코드 업데이트: {'통과' if single_update_time < 0.2 else '실패'}")
    print(f"b. 동시 업데이트 요청: {'통과' if max(concurrent_update_times) < 0.5 else '실패'}")
    print("c. 대량 데이터 업데이트:")
    time_limit = 3
    result = bulk_update(connection, bulk_size)
    print(f"   {bulk_size}건: {'통과' if result < time_limit else '실패'} ({result:.2f}초)")

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

    # 성능 테스트 실행
    run_performance_tests(connection)
    
    connection.close()

if __name__ == "__main__":
    main()