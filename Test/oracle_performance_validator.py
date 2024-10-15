import cx_Oracle
import time
import random
from dotenv import load_dotenv
import os
from concurrent.futures import ThreadPoolExecutor, as_completed

def single_record_select(connection):
    cursor = connection.cursor()
    index_no = f"{random.randint(1000000, 9999999)}"
    index_no_sfix = f"{random.randint(10, 99)}"
    sql = """
    SELECT * FROM DCS_HISTORY 
    WHERE INDEX_NO = :1 AND INDEX_NO_SFIX = :2
    """
    start_time = time.time()
    cursor.execute(sql, (index_no, index_no_sfix))
    result = cursor.fetchone()
    end_time = time.time()
    cursor.close()
    return end_time - start_time

def bulk_select(connection, num_records):
    cursor = connection.cursor()
    sql = """
    SELECT * FROM DCS_HISTORY 
    WHERE ROWNUM <= :1
    """
    start_time = time.time()
    cursor.execute(sql, (num_records,))
    results = cursor.fetchall()
    end_time = time.time()
    cursor.close()
    return end_time - start_time

def run_performance_tests(connection):
    print("\n--- 성능 테스트 결과 ---")

    # a. 특정 기간 조회
    single_select_time = single_record_select(connection)
    print(f"a. 특정 기간 조회: {single_select_time * 1000:.2f}ms")

    # b. 전체 기간 조회
    bulk_select_time = bulk_select(connection, 72000)
    print(f"b. 전체 기간 조회 (72000건): {bulk_select_time:.2f}초")

    print("\n--- 검증 결과 ---")
    print(f"a. 특정 기간 조회: {'통과' if single_select_time < 0.2 else '실패'}")
    print(f"b. 전체 기간 조회: {'통과' if bulk_select_time < 2 else '실패'}")

def main():
    load_dotenv()

    user = str(os.getenv('NEURON_USER', 'default_user'))
    password = str(os.getenv('NEURON_PASSWORD', 'default_password'))
    host = str(os.getenv('NEURON_HOST', 'default_host'))
    port = str(os.getenv('NEURON_PORT', '1521'))
    service_name = str(os.getenv('NEURON_SERVICE_NAME', 'default_service_name'))

    print(f"연결 정보: user={user}, host={host}, port={port}, service_name={service_name}")

    dsn = cx_Oracle.makedsn(host, port, service_name=service_name)

    try:
        connection = cx_Oracle.connect(user=user, password=password, dsn=dsn)
        print("데이터베이스 연결 성공")
    except cx_Oracle.Error as error:
        print(f"Oracle 데이터베이스 연결 오류: {error}")
        return

    run_performance_tests(connection)
    
    connection.close()

if __name__ == "__main__":
    main()