from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.events import EVENT_JOB_EXECUTED, EVENT_JOB_ERROR
from flask import current_app
import pytz
import os
import shutil
import logging
from datetime import datetime, timedelta
import atexit
import json

class SchedulerManager:
    _instance = None
    _initialized = False
    _previous_serials = set()  # 이전 실행의 시리얼 번호를 저장하기 위한 클래스 변수
    _serial_file_path = 'previous_serials.json'  # 시리얼 번호를 저장할 파일 경로

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self, app, db_manager_2):
        if self._initialized:
            return

        # 로깅 설정 먼저 초기화
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )
        self.logger = logging.getLogger('SchedulerManager')
        self.logger.info("SchedulerManager 초기화 중...")  # 로깅 초기화 후 사용

        self.app = app
        self.db_manager_2 = db_manager_2

        self.logger.info("로깅 설정 완료")  # 추가된 디버깅 출력

        # 스케줄러 설정
        self.scheduler = BackgroundScheduler(
            timezone=pytz.timezone('Asia/Seoul'),
            job_defaults={'coalesce': True, 'max_instances': 1}
        )

        self.scheduler.add_listener(self._job_listener, EVENT_JOB_EXECUTED | EVENT_JOB_ERROR)

        # Flask 앱 컨텍스트 내에서 작업 설정
        with self.app.app_context():
            self.setup_jobs()

        atexit.register(self.shutdown)

        # 이전 시리얼 번호 로드
        self._load_previous_serials()

        self._initialized = True

    def _job_listener(self, event):
        if event.exception:
            self.logger.error(f'작업 실행 중 오류 발생: {event.exception}')
        else:
            self.logger.info(f'작업이 성공적으로 실행됨: {event.job_id}')

    def setup_jobs(self):
        try:
            if self.scheduler.running:
                self.logger.warning("스케줄러가 이미 실행 중입니다.")
                return

            self.scheduler.add_job(
                func=self._run_with_context,
                trigger='cron',
                hour=6,  # 매일 오전 6시에 실행
                minute=0,  # 매일 오전 6시에 실행
                id='cleanup_job',
                name='Daily Cleanup Job',
                misfire_grace_time=3600,  # 1시간의 유예 시간 설정
                replace_existing=True
            )
            self.scheduler.start()
            self.logger.info(f"스케줄러가 시작되었습니다. 다음 실행 시간: {self.get_next_run_time()}")
            print("스케줄러 시작됨")

        except Exception as e:
            self.logger.error(f"스케줄러 설정 중 오류 발생: {str(e)}")
            raise
            
    def get_next_run_time(self):
        """다음 실행 시간을 반환합니다."""
        job = self.scheduler.get_job('cleanup_job')
        if job:
            return job.next_run_time
        return None

    def _load_previous_serials(self):
        """저장된 시리얼 번호를 파일에서 로드합니다."""
        try:
            if os.path.exists(self._serial_file_path):
                with open(self._serial_file_path, 'r') as f:
                    data = json.load(f)
                    self._previous_serials = set(data.get('serials', []))
                self.logger.info(f"이전 시리얼 번호 로드 완료: {len(self._previous_serials)}개")
            else:
                self.logger.info("이전 시리얼 번호 파일이 없습니다.")
        except Exception as e:
            self.logger.error(f"시리얼 번호 로드 중 오류 발생: {str(e)}")
            self._previous_serials = set()

    def _save_previous_serials(self, serials):
        """시리얼 번호를 파일에 저장합니다."""
        try:
            with open(self._serial_file_path, 'w') as f:
                json.dump({'serials': list(serials)}, f)
            self.logger.info(f"시리얼 번호 저장 완료: {len(serials)}개")
        except Exception as e:
            self.logger.error(f"시리얼 번호 저장 중 오류 발생: {str(e)}")

    def get_target_serials(self):
        """SAP DB에서 대상이 되는 Serial 번호 리스트를 가져옵니다."""
        try:
            with self.db_manager_2.connect() as connection:
                with connection.cursor() as cursor:
                    select_sql = """
                    SELECT --LIKP.VBELN AS Delivery_Document,
                    LIKP.WADAT AS Actual_Goods_Issue_Date,
                    LIPS.POSNR AS Delivery_Item,
                    LIPS.MATNR AS Material,
                    VBAP.VBELN AS Sales_Order,
                    VBAP.POSNR AS Sales_Order_Item,
                    VBAP.KWMENG AS Ordered_Quantity,
                    TDSJ201.FINISH_D,
                    TDSJ201.ORDER_NO,
                    TDSJ201.ITEM_NO,
                    TDSJ201.SERIAL_NO,
                    TDSJ201.FINISH_QTY,
                    VBAP.VBELN || VBAP.POSEX AS ORDER_NO_16
                    FROM sap.LIKP LIKP, sap.LIPS LIPS, sap.VBAP VBAP, sap.TDSJ201 TDSJ201
                    WHERE LIKP.VBELN = LIPS.VBELN
                    AND LIPS.VGBEL = VBAP.VBELN
                    AND LIKP.WADAT IS NOT NULL
                    AND VBAP.VBELN = TDSJ201.ORDER_NO
                    AND LPAD (VBAP.POSNR, 6, '0') = TDSJ201.ITEM_NO
                    AND (
                        LIPS.MATNR LIKE 'UT%'
                        OR LIPS.MATNR LIKE 'UP%'
                        OR LIPS.MATNR LIKE 'UM%'
                    )
                    AND LIKP.WADAT BETWEEN '20241101' AND TO_CHAR(SYSDATE, 'YYYYMMDD')
                    """
                    cursor.execute(select_sql)
                    results = cursor.fetchall()
                    
                    # Serial 번호 리스트 추출 및 None 제거
                    current_serials = set(row[9] for row in results if row[9] is not None)
                    
                    # 새로운 시리얼 번호만 추출 (이전에 처리하지 않은 것들)
                    new_serials = current_serials - self._previous_serials
                    
                    # 현재 시리얼 목록을 이전 시리얼로 저장 (파일에도 저장)
                    self._previous_serials = current_serials
                    self._save_previous_serials(current_serials)
                    
                    self.logger.info(f"전체 시리얼 수: {len(current_serials)}, 새로운 시리얼 수: {len(new_serials)}")
                    return list(new_serials)
                    
        except Exception as e:
            self.logger.error(f"Serial 번호 조회 중 오류 발생: {str(e)}")
            return []
        
    def _run_with_context(self):
        """Flask 앱 컨텍스트 내에서 작업을 실행하는 래퍼 함수"""
        with self.app.app_context():
            try:
                self.cleanup_processed_files()
            except Exception as e:
                self.logger.error(f"스케줄러 작업 중 예외 발생: {str(e)}")

    def cleanup_processed_files(self):
        """매일 오전 6시에 실행되어 새로 추가된 Serial 번호에 해당하는
        Checked와 Process 폴더의 파일들을 삭제합니다."""
        current_time = datetime.now()
        self.logger.info(f"파일 정리 작업을 시작합니다... (시작 시간: {current_time})")
        print(f"cleanup_processed_files 함수 호출됨 - {current_time}")

        try:
            # SAP DB에서 새로운 Serial 번호 리스트 조회
            target_serials = self.get_target_serials()
            if not target_serials:
                self.logger.info("새로운 삭제 대상 Serial 번호가 없습니다.")
                return

            self.logger.info(f"처리할 새로운 시리얼 수: {len(target_serials)}")
                
            # 업로드 폴더와 네트워크 경로 확인
            upload_folder = self.app.config.get('UPLOAD_FOLDER')
            network_path = self.app.config.get('NETWORK_PATH')

            if not upload_folder:
                self.logger.error("UPLOAD_FOLDER가 설정되지 않았습니다.")
                return
            if not network_path:
                self.logger.error("NETWORK_PATH가 설정되지 않았습니다.")
                return

            # 모든 부서 코드에 대해 처리
            for dept_code in os.listdir(upload_folder):
                dept_path = os.path.join(upload_folder, dept_code)
                if not os.path.isdir(dept_path):
                    continue

                # 각 Serial 번호에 대해 처리
                for serial_no in target_serials:
                    if serial_no is None:
                        self.logger.warning("Serial 번호가 None입니다.")
                        continue

                    # Merged 폴더에서 해당 시리얼의 PNG 파일 확인
                    local_merged_path = os.path.join(dept_path, 'Merged')
                    network_merged_path = os.path.join(network_path, dept_code, 'Merged')
                    
                    # PNG 파일 존재 여부 확인
                    has_png_local = False
                    has_png_network = False
                    
                    if os.path.exists(local_merged_path):
                        has_png_local = os.path.exists(os.path.join(local_merged_path, f"{serial_no}.png"))
                        
                    if os.path.exists(network_merged_path):
                        has_png_network = os.path.exists(os.path.join(network_merged_path, f"{serial_no}.png"))
                    
                    # PNG 파일이 없는 경우 건너뛰기
                    if not (has_png_local or has_png_network):
                        self.logger.info(f"시리얼 {serial_no}의 PNG 파일이 Merged 폴더에 없어 삭제를 건너뜁니다.")
                        continue

                    # PNG 파일이 있는 경우에만 Checked와 Process 폴더 삭제
                    # 로컬 Checked 폴더 삭제
                    local_checked_path = os.path.join(dept_path, 'Checked', serial_no)
                    if os.path.exists(local_checked_path):
                        shutil.rmtree(local_checked_path)
                        self.logger.info(f"로컬 Checked 폴더 삭제: {local_checked_path}")
                        
                    # 로컬 Process 폴더 삭제
                    local_process_path = os.path.join(dept_path, 'Process', serial_no)
                    if os.path.exists(local_process_path):
                        shutil.rmtree(local_process_path)
                        self.logger.info(f"로컬 Process 폴더 삭제: {local_process_path}")
                        
                    # 서버 Checked 폴더 삭제
                    network_checked_path = os.path.join(
                        network_path,
                        dept_code,
                        'Checked',
                        serial_no
                    )
                    if os.path.exists(network_checked_path):
                        shutil.rmtree(network_checked_path)
                        self.logger.info(f"서버 Checked 폴더 삭제: {network_checked_path}")
                        
                    # 서버 Process 폴더 삭제
                    network_process_path = os.path.join(
                        network_path,
                        dept_code,
                        'Process',
                        serial_no
                    )
                    if os.path.exists(network_process_path):
                        shutil.rmtree(network_process_path)
                        self.logger.info(f"서버 Process 폴더 삭제: {network_process_path}")
                            
            self.logger.info(f"파일 정리 작업이 완료되었습니다. 시간: {datetime.now()}")
            print("파일 정리 작업 완료")
            
        except Exception as e:
            self.logger.error(f"파일 정리 작업 중 오류 발생: {str(e)}")
            print(f"파일 정리 작업 중 오류 발생: {str(e)}")
            
    def shutdown(self):
        """스케줄러 종료 시 현재 시리얼 목록을 저장합니다."""
        if self.scheduler.running:
            self.logger.info("스케줄러를 종료합니다.")
            # 현재 시리얼 목록 저장
            self._save_previous_serials(self._previous_serials)
            self.scheduler.shutdown(wait=False)