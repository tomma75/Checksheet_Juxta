from flask import render_template, request, jsonify, url_for, send_from_directory, redirect, session, send_file
import logging
from werkzeug.utils import secure_filename, safe_join
from datetime import datetime, time
import os
from pdf2image import convert_from_path
from PIL import Image
import base64
import io
import numpy as np
import socket
from functools import wraps
from PIL import ImageDraw
from ImageProcessor import ImageProcessor
import json
from apscheduler.schedulers.background import BackgroundScheduler
import shutil
import pytz
from SchedulerManager import SchedulerManager

class RouteHandler:
    def __init__(self, app, db_manager_1, db_manager_2, image_processor):
        # 클래스 초기화 메서드
        self.app = app
        self.db_manager_1 = db_manager_1
        self.db_manager_2 = db_manager_2
        self.image_processor = image_processor
        self.settings_path = 'Settings.json'  # settings.json 파일 경로 추가
        
        # app 인스턴스를 직접 전달
        self.scheduler_manager = SchedulerManager(app, db_manager_2)
        
        self.register_routes()

    def register_routes(self):
        routes = [
            ('/', self.login, ['GET', 'POST']),
            ('/login', self.login, ['GET', 'POST']),
            ('/logout', self.logout, ['GET']),
            ('/config', self.send_config, ['GET']),
            ('/get_employee_name', self.get_employee_name, ['POST']),
            ('/save_checked_image', self.save_checked_image, ['POST']),
            ('/checkSheet', self.checkSheet, ['GET']),
            ('/checksheet-history', self.checksheet_history, ['GET']),
            ('/upload_image/<serial_process>', self.upload_image, ['GET']),
            ('/get_product_info', self.get_product_info, ['POST']),
            ('/search_history', self.search_history, ['POST']),
            ('/files/list/<path:directory>', self.list_files, ['GET']),
            ('/files/get/<path:filepath>', self.serve_file, ['GET']),
            ('/network/files/list/<path:directory>', self.list_network_files, ['GET']),
            ('/network/files/get/<path:filepath>', self.get_network_file, ['GET']),
            ('/check_login_status', self.check_login_status, ['GET']),
            ('/save_checkbox_states', self.save_checkbox_states, ['POST']),
            ('/get_checkbox_states', self.get_checkbox_states, ['GET']),
            ('/check_previous_process', self.check_previous_process, ['POST']),
            ('/refresh_session', self.refresh_session, ['POST']),
            # ('/network/files/list/<dept_code>/Checked/<serial_no>/', self.list_network_files, ['GET']),
            # ('/network/files/get/<dept_code>/Checked/<serial_no>/<filename>', self.get_network_file, ['GET']),
            ('/get_settings', self.get_settings, ['GET']),  # 새로운 라우트 추가
            ('/update_and_insert_product_info', self.update_and_insert_product_info, ['POST']),
            ('/check_index_in_dcs_history', self.check_index_in_dcs_history, ['POST']),
            ('/check_dcs_history_status', self.check_dcs_history_status, ['POST']),
            ('/insert_dcs_history',self.insert_dcs_history,['POST'])
        ]

        # 라우트 등록 시 view_func를 데코레이터로 감싸서 등록
        for path, view_func, methods in routes:
            endpoint = view_func.__name__
            self.app.add_url_rule(
                path,
                endpoint=endpoint,
                view_func=view_func,
                methods=methods,
                strict_slashes=False  # URL 끝의 슬래시 유무 무시
            )

        # 404 에러 핸들러 등록
        @self.app.errorhandler(404)
        def not_found_error(error):
            if request.path.startswith('/checksheet-history'):
                return self.checksheet_history()
            return jsonify({
                'error': 'Requested URL not found',
                'url': request.url
            }), 404

        # 등록된 모든 라우트 로깅
        logging.info("Registered routes:")
        for rule in self.app.url_map.iter_rules():
            logging.info(f"Route: {rule.rule} [{', '.join(rule.methods)}] -> {rule.endpoint}")

    def login(self):
        # 로그인 페이지 렌더링
        if 'logged_in' in session and session['logged_in']:
            return redirect(url_for('checkSheet'))
        return render_template('login.html')

    def logout(self):
        # 로그아웃 처리 메서드  
        session.clear()
        return redirect(url_for('login'))

    def get_employee_name(self):
        # 사원번호를 받아 사원 정보를 데이터베이스에서 가져오는 메서드
        employee_id = request.form['employeeId'].strip()
        if not employee_id.isdigit():
            return jsonify({'error': '유효하지 않은 사원번호입니다.'}), 400

        connection = self.db_manager_1.connect()
        cursor = connection.cursor()
        try:
            # SQL 파일 읽기
            with open('.\\sql\\EMP.sql', 'r', encoding='utf-8') as file:
                sql = file.read().format(employee_id=employee_id)
            cursor.execute(sql)
            employee_info = cursor.fetchone()
            if employee_info:
                # 세션 정보 설정
                session['logged_in'] = True
                session['employee_name'] = employee_info[2] + ' ' + employee_info[3]
                session['dept_info'] = employee_info[0] + ' ' + employee_info[1]
                session.modified = True
                logging.info(f"Session after login: {session}")
                return jsonify({'employeeName': session['employee_name'], 'deptInfo': session['dept_info']})
            else:
                return jsonify({'error': '사원번호가 존재하지 않습니다.\n유저 등록 및 조회는 K-Prism에서 가능합니다.'}), 404
        finally:
            cursor.close()
            self.db_manager_1.close()

    def save_checked_image(self):
        """
        체크시트 이미지를 저장하고, 모든 공정이 완료되었을 경우 이미지를 합칩니다.
        
        :return: JSON 응답 객체
        """
        if 'image' not in request.files:
            return jsonify({'error': 'No image part in the request'}), 400

        file = request.files['image']
        serial_no = request.form['serialNo']
        process_code = request.form['processCode']
        deptCode = request.form['deptCode']
        empNo = request.form['empNo']
        indexNo = request.form['indexNo'][:-2]
        indexNo_sfix = request.form['indexNo'][-2:]
        result = 1 if request.form['result'] == 'OK' else 2

        # 파일 이름 생성
        filename = secure_filename(f"{serial_no}_{process_code}.png")
        date_str = datetime.now()
        pc_name = socket.gethostname()
        daily_folder = os.path.join(self.app.config['UPLOAD_FOLDER'], deptCode, 'Checked', serial_no)

        # 일일 폴더 생성
        if not os.path.exists(daily_folder):
            os.makedirs(daily_folder)
        save_path = os.path.join(daily_folder, filename)
        
        db_success = False
        file_success = False
        
        try:
            # 파일 저장 시도
            file.save(save_path)
            if os.path.exists(save_path):
                file_success = True
                
                # DB 저장 시도
                connection = self.db_manager_2.connect()
                cursor = connection.cursor()
                sql_check = """
                                SELECT RENEWAL_D
                                FROM DCS_HISTORY
                                WHERE INDEX_NO=:1 AND INDEX_NO_SFIX=:2
                                AND SERIAL_NO=:3 AND DEPT_CODE=:4
                                AND PROCESS_CODE=:5 AND DATA_ST='A'
                            """
                cursor.execute(sql_check, (indexNo, indexNo_sfix, serial_no, deptCode, process_code))
                row = cursor.fetchone()
                renewal_d_value = row[0] if row else None

                sql_model = """
                    SELECT T951.MODEL FROM TDSC951 T951, TDSC952 T952
                    WHERE T951.PROD_NO = T952.PROD_NO 
                    AND T952.SERIAL_NO =:1
                    """
                cursor.execute(sql_model, (serial_no,))
                row = cursor.fetchone()
                model = row[0] if row else None

                # 04번 공정의 경우 DCS_HISTORY에 레코드가 없을 수 있으므로 MERGE 사용
                if process_code == '04' and deptCode == '3186':
                    sql_merge = """
                        MERGE INTO DCS_HISTORY
                        USING DUAL
                        ON (INDEX_NO = :1 AND INDEX_NO_SFIX = :2 AND SERIAL_NO = :3 
                            AND DEPT_CODE = :4 AND PROCESS_CODE = :5 AND DATA_ST = 'A')
                        WHEN MATCHED THEN
                            UPDATE SET STATUS = :6, EMP_NO = :7, FINISH_D = :8, RENEWAL_BY = :9
                        WHEN NOT MATCHED THEN
                            INSERT (INDEX_NO, INDEX_NO_SFIX, SERIAL_NO, DEPT_CODE, PROCESS_CODE, 
                                    STATUS, EMP_NO, FINISH_D, ENTRY_D, ENTRY_BY, DATA_ST)
                            VALUES (:1, :2, :3, :4, :5, :6, :7, :8, :8, :9, 'A')
                    """
                    params = (indexNo, indexNo_sfix, serial_no, deptCode, process_code, 
                             result, empNo, date_str, pc_name)
                    cursor.execute(sql_merge, params)
                elif renewal_d_value is None and row is not None:
                    sql_update = """
                        UPDATE DCS_HISTORY
                        SET STATUS = :1, EMP_NO = :2, FINISH_D = :3
                        WHERE INDEX_NO = :4 AND INDEX_NO_SFIX = :5 AND SERIAL_NO = :6 AND DEPT_CODE = :7 AND PROCESS_CODE = :8 AND DATA_ST = 'A'
                    """
                    params = (result, empNo, date_str, indexNo, indexNo_sfix, serial_no, deptCode, process_code)
                    cursor.execute(sql_update, params)
                elif row is not None:
                    # RENEWAL_D가 NULL이 아닐 경우
                    sql_update = """
                        UPDATE DCS_HISTORY
                        SET STATUS = :1, EMP_NO = :2, RENEWAL_FINISH_D = :3, RENEWAL_BY = :4
                        WHERE INDEX_NO = :4 AND INDEX_NO_SFIX = :5 AND SERIAL_NO = :6 AND DEPT_CODE = :7 AND PROCESS_CODE = :8 AND DATA_ST = 'A'
                    """
                    params = (result, empNo, date_str, pc_name, indexNo, indexNo_sfix, serial_no, deptCode, process_code)
                    cursor.execute(sql_update, params)

                connection.commit()
                db_success = True
                
                if db_success and file_success:
                    # 모든 공정이 완료되었는지 확인 (부품SET 제외)
                    if self.is_all_process_completed(indexNo, deptCode, serial_no):
                        # Merged 폴더 경로 설정
                        merged_folder = os.path.join(self.app.config['UPLOAD_FOLDER'], deptCode, 'Merged')
                        if not os.path.exists(merged_folder):
                            os.makedirs(merged_folder)
                        
                        # 합쳐질 이미지의 경로 설정 (시리얼 번호로 저장)
                        merged_image_path = os.path.join(merged_folder, f"{serial_no}.png")
                        if deptCode in ['3165','UTA']:
                            # 모든 체크시트 이미지 경로 수집 (부품SET 제외)
                            image_folder = os.path.join(self.app.config['UPLOAD_FOLDER'], deptCode, 'Checked', serial_no)
                            image_files = sorted([
                                os.path.join(image_folder, f) for f in os.listdir(image_folder)
                                if f.startswith(serial_no) and f.endswith('.png') and not f.endswith('_08.png')
                            ])
                            
                            # 이미지 합치기 실행
                            ImageProcessor.merge_checksheet_images_uta(image_files, merged_image_path, target_width=800)
                        elif deptCode in ['3186','JUXTA']:
                            # 모든 체크시트 이미지 경로 수집 (부품SET 제외)
                            image_folder = os.path.join(self.app.config['UPLOAD_FOLDER'], deptCode, 'Checked', serial_no)
                            image_files = sorted([
                                os.path.join(image_folder, f) for f in os.listdir(image_folder)
                                if f.startswith(serial_no) and f.endswith('.png')
                            ])
                            if model != 'VJ77':
                                # 먼저 Checked 폴더에 04번 이미지가 있는지 확인
                                checked_04_path = os.path.join(
                                    self.app.config['UPLOAD_FOLDER'],
                                    deptCode,
                                    'Checked',
                                    serial_no,
                                    f'{serial_no}_04.png'
                                )
                                # Process 폴더의 _0.png 경로
                                process_0_path = os.path.join(
                                    self.app.config['UPLOAD_FOLDER'],
                                    deptCode,
                                    'Process',
                                    serial_no,
                                    f'{serial_no}_0.png'
                                )
                                
                                # Checked에 04번이 있으면 그것을 사용, 없으면 Process의 0번 사용
                                if os.path.exists(checked_04_path):
                                    # 이미 image_files에 포함되어 있으므로 추가 작업 불필요
                                    logging.info(f"Using checked 04 image for merge: {checked_04_path}")
                                elif os.path.exists(process_0_path):
                                    # Process 폴더의 0번 이미지를 맨 앞에 추가
                                    image_files.insert(0, process_0_path)
                                    logging.info(f"Using process 0 image for merge: {process_0_path}")
                                else:
                                    logging.warning(f"Neither checked 04 nor process 0 image found for {serial_no}")
                            # 이미지 합치기 실행
                            ImageProcessor.merge_checksheet_images_juxta(image_files, merged_image_path, target_width=800)
                        elif deptCode in ['3188','NEW SC']:
                            # Process 폴더와 Checked 폴더에서 이미지 수집
                            process_folder = os.path.join(self.app.config['UPLOAD_FOLDER'], deptCode, 'Process', serial_no)
                            checked_folder = os.path.join(self.app.config['UPLOAD_FOLDER'], deptCode, 'Checked', serial_no)
                            
                            # 3188의 특별한 병합 규칙:
                            # 좌: serial_0.png(process), serial_06.png(checked), serial_2.png(process)
                            # 우: serial_09.png(checked)
                            
                            left_images = []  # 왼쪽에 들어갈 이미지들 (순서대로)
                            right_image = None  # 오른쪽에 들어갈 이미지
                            
                            # 0번 이미지 (Process 폴더)
                            img_0 = os.path.join(process_folder, f"{serial_no}_0.png")
                            if os.path.exists(img_0):
                                left_images.append(img_0)
                            else:
                                logging.warning(f"0번 이미지를 찾을 수 없습니다: {img_0}")
                            
                            # 06 공정 이미지 (Checked 폴더)
                            img_06 = os.path.join(checked_folder, f"{serial_no}_06.png")
                            if os.path.exists(img_06):
                                left_images.append(img_06)
                            else:
                                # Checked에 없으면 1번 이미지로 대체 (06 공정은 1번 인덱스 사용)
                                img_1 = os.path.join(checked_folder, f"{serial_no}_1.png")
                                if os.path.exists(img_1):
                                    left_images.append(img_1)
                                else:
                                    # Checked에 없으면 Process에서 찾기
                                    img_1_process = os.path.join(process_folder, f"{serial_no}_1.png")
                                    if os.path.exists(img_1_process):
                                        left_images.append(img_1_process)
                                    else:
                                        logging.warning(f"06 공정 이미지를 찾을 수 없습니다")
                            
                            # 2번 이미지 (Process 폴더)
                            img_2 = os.path.join(process_folder, f"{serial_no}_2.png")
                            if os.path.exists(img_2):
                                left_images.append(img_2)
                            else:
                                logging.warning(f"2번 이미지를 찾을 수 없습니다: {img_2}")
                            
                            # 09 공정 이미지 (Checked 폴더)
                            img_09 = os.path.join(checked_folder, f"{serial_no}_09.png")
                            if os.path.exists(img_09):
                                right_image = img_09
                            else:
                                # Checked에 없으면 3번 이미지로 대체 (09 공정은 3번 인덱스 사용)
                                img_3 = os.path.join(checked_folder, f"{serial_no}_3.png")
                                if os.path.exists(img_3):
                                    right_image = img_3
                                else:
                                    # Checked에 없으면 Process에서 찾기
                                    img_3_process = os.path.join(process_folder, f"{serial_no}_3.png")
                                    if os.path.exists(img_3_process):
                                        right_image = img_3_process
                                    else:
                                        logging.warning(f"09 공정 이미지를 찾을 수 없습니다")
                            
                            # NEW SC 전용 병합 함수 사용
                            if left_images and right_image:
                                ImageProcessor.merge_checksheet_images_newsc(left_images, right_image, merged_image_path)
                                logging.info(f"NEW SC merged images for {serial_no}: Left={[os.path.basename(img) for img in left_images]}, Right={os.path.basename(right_image)}")
                            elif left_images:
                                # 오른쪽 이미지가 없는 경우 왼쪽 이미지들만 세로로 합치기
                                ImageProcessor.merge_checksheet_images_uta(left_images, merged_image_path, target_width=800)
                                logging.info(f"NEW SC merged only left images for {serial_no}")
                            else:
                                logging.error(f"No valid images found to merge for {serial_no}")
                    return jsonify({
                        'success': True,
                        'message': '체크시트가 성공적으로 저장되었습니다.'
                    })
            else:
                return jsonify({
                    'success': False,
                    'message': '이미지 파일 저장에 실패했습니다.',
                    'db_saved': False,
                    'file_saved': False
                }), 500
                
        except Exception as e:
            # 에러 발생 시 롤백 처리
            if 'connection' in locals():
                connection.rollback()
            if file_success:
                try:
                    os.remove(save_path)
                except OSError:
                    pass

            error_message = '데이터베이스 저장 중 오류가 발생했습니다.' if db_success else '이미지 파일 저장 중 오류가 발생했습니다.'
            return jsonify({
                'success': False,
                'message': error_message,
                'db_saved': db_success,
                'file_saved': file_success,
                'error': str(e)
            }), 500
            
        finally:
            if 'cursor' in locals():
                cursor.close()
            if 'connection' in locals():
                connection.close()

    def login_required(f):
        # 로그인 필요 데코레이터
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if 'logged_in' not in session or not session['logged_in']:
                return redirect(url_for('login'))
            return f(*args, **kwargs)
        return decorated_function

    @login_required
    def checkSheet(self):
        # 체크 시트 페이지 렌더링
        if 'employee_name' not in session or 'dept_info' not in session:
            return redirect(url_for('login'))
        employee_name = session.get('employee_name', 'Unknown')
        dept_info = session.get('dept_info', 'Unknown')
        pen_cursor_url = url_for('static', filename='icon/pen-tool.png')
        return render_template('checkSheet.html', employee_name=employee_name, dept_info=dept_info, pen_cursor_url=pen_cursor_url)

    def _find_file_path(self, *paths):
        """여러 경로 중 첫 번째로 존재하는 파일 경로를 반환"""
        for path in paths:
            if os.path.exists(path):
                return path
        return None
    
    @login_required
    def upload_image(self, serial_process):
        parts = serial_process.split('_')
        indexNo, dept, serial, process = parts[:4]
        index = int(parts[-1])
        
        # 부서별 이미지 인덱스 매핑
        if dept == '3188':
            if process == '06':  # 첫 번째 공정 -> 1번 이미지
                index = 1
            elif process == '09':  # 두 번째 공정 -> 3번 이미지
                index = 4
        elif dept == '3186':
            # index는 이미 위에서 계산됨
            pass
        else:
            # 기존 로직 (3165 등)
            if index != 0:
                index = index - 1
        # 체크박스 상태 확인을 위한 DB 조회
        connection = self.db_manager_2.connect()
        cursor = connection.cursor()
        try:
            cursor.execute("""
                SELECT COUNT(*)
                FROM CHECKBOX_STATES
                WHERE SERIAL_NO = :1 
                AND DEPT_CODE = :2 
                AND PROCESS_CODE = :3
                AND DATA_ST = 'A'
            """, (serial, dept, process))
            checkbox_count = cursor.fetchone()[0]
            is_checked_image = checkbox_count > 0
            sql_model = """
                SELECT T951.MODEL FROM TDSC951 T951, TDSC952 T952
                WHERE T951.PROD_NO = T952.PROD_NO 
                AND T952.SERIAL_NO =:1
                """
            cursor.execute(sql_model, (serial,))
            row = cursor.fetchone()
            model = row[0] if row else None
        finally:
            cursor.close()
            connection.close()
        if model == 'VJ77':
            if index != 0 :
                index -= 1
        # 체크 완료된 이미지 경로 확인 (로컬)
        checked_filename = f"{serial}_{process}.png"
        checked_file_path = os.path.join(self.app.config['UPLOAD_FOLDER'], dept, 'Checked', serial, checked_filename)
        network_checked_path = os.path.join(self.app.config['NETWORK_PATH'], dept, 'Checked', serial, checked_filename)

        # Process 파일 경로 확인 (로컬 및 네트워크)
        # 3186 부서의 04번 공정은 항상 _0.png 사용
        if dept == '3186' and process == '04' and model != 'VJ77':
            process_filename = f'{serial}_0.png'
        else:
            process_filename = f'{serial}_{index}.png'
        process_file_path = os.path.join(self.app.config['UPLOAD_FOLDER'], dept, 'Process', serial, process_filename)
        network_process_path = os.path.join(self.app.config['NETWORK_PATH'], dept, 'Process', serial, process_filename)

        # 파일 경로 결정
        file_path = None
        print("@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@000000@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@")
        print(f"@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@{dept},{process}@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@")
        # JUXTA (3186) 04번 프로세스 처리
        # 이미 체크된 이미지가 있으면 그것을 사용, 없으면 Process 폴더에서 가져옴
        if dept == '3186' and process == '04':
            # 먼저 Checked 폴더에 이미 체크된 이미지가 있는지 확인
            if os.path.exists(checked_file_path) or os.path.exists(network_checked_path):
                # 이미 체크된 이미지가 있으면 그것을 사용
                file_path = checked_file_path if os.path.exists(checked_file_path) else network_checked_path
                logging.info(f"Using existing checked image for process 04: {file_path}")
            else:
                # 체크된 이미지가 없으면 Process 폴더에서 원본 이미지 사용
                process_0_filename = f'{serial}_0.png'
                process_0_file_path = os.path.join(self.app.config['UPLOAD_FOLDER'], dept, 'Process', serial, process_0_filename)
                network_process_0_path = os.path.join(self.app.config['NETWORK_PATH'], dept, 'Process', serial, process_0_filename)
                
                if os.path.exists(process_0_file_path):
                    file_path = process_0_file_path
                elif os.path.exists(network_process_0_path):
                    file_path = network_process_0_path
                else:
                    # Process 폴더에도 없으면 일반 프로세스 파일 경로 사용
                    if os.path.exists(process_file_path):
                        file_path = process_file_path
                    elif os.path.exists(network_process_path):
                        file_path = network_process_path
        elif is_checked_image:
            # 체크된 이미지 우선, 없으면 Process 이미지 사용
            file_path = self._find_file_path(checked_file_path, network_checked_path, 
                                            process_file_path, network_process_path)
            if not file_path:
                return jsonify({'error': 'Checked image not found'}), 404
        else:
            # Process 이미지 사용
            file_path = self._find_file_path(process_file_path, network_process_path)
        print("@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@111111@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@")
        print(f"@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@{file_path}@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@")
        def safe_sleep(seconds):
            """import 충돌 방지 sleep 헬퍼"""
            import time
            time.sleep(seconds)
        # file_path가 여전히 None인 경우 Master PDF 처리
        if file_path is None:
            # index가 0이고 Process 파일이 없는 경우 Master PDF 확인
            if dept in ['3186', '3188']:
                master_pdf_path = os.path.join(self.app.config['UPLOAD_FOLDER'], dept, 'Master', f'{serial}_0.pdf')
                network_master_path = os.path.join(self.app.config['NETWORK_PATH'], dept, 'Master', f'{serial}_0.pdf')
            else:
                master_pdf_path = os.path.join(self.app.config['UPLOAD_FOLDER'], dept, 'Master', f'{serial}.pdf')
                network_master_path = os.path.join(self.app.config['NETWORK_PATH'], dept, 'Master', f'{serial}.pdf')
            for attempt in range(3):
                if os.path.exists(master_pdf_path):
                    master_path = master_pdf_path
                    base_folder_ori = self.app.config['UPLOAD_FOLDER']
                    break
                elif os.path.exists(network_master_path):
                    master_path = network_master_path
                    base_folder_ori = self.app.config['NETWORK_PATH']
                    break
                if attempt < 4:
                    print("@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@RRRRRRR@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@")
                    safe_sleep(2)
                else:
                    return jsonify({'error': 'Requested master PDF does not exist.'}), 404

            # Master PDF를 이미지로 변환
            images = convert_from_path(master_path, dpi=150)
            if dept in ['3186', '3188']:
                master_jpg_path = os.path.join(self.app.config['UPLOAD_FOLDER'], dept, 'Master', f'{serial}_0.png')
                images[0].save(master_jpg_path, 'PNG')
            else:
                master_jpg_path = os.path.join(self.app.config['UPLOAD_FOLDER'], dept, 'Master', f'{serial}.png')
                images[0].save(master_jpg_path, 'PNG')
            self.image_processor.convert_pdf_to_process_images(dept, process, serial, base_folder=self.app.config['UPLOAD_FOLDER'], model=model, base_folder_ori=base_folder_ori)
            
            if os.path.exists(process_file_path):
                file_path = process_file_path
            else:
                return jsonify({'error': 'Failed to create process image from master PDF.'}), 500

        if file_path is None or not os.path.exists(file_path):
            logging.error(f'Image not found: {file_path}')
            return jsonify({'error': 'Requested image does not exist.'}), 404

        pil_image = Image.open(file_path)
        if pil_image.mode != 'RGB':
            pil_image = pil_image.convert('RGB')

        if is_checked_image:
            # DB에서 체크박스 위치 불러오기
            connection = self.db_manager_2.connect()
            cursor = connection.cursor()
            try:
                cursor.execute("""
                    SELECT CHECKBOX_INDEX, X_POSITION, Y_POSITION, WIDTH, HEIGHT
                    FROM CHECKBOX_STATES
                    WHERE INDEX_NO = :1 AND INDEX_NO_SFIX = :2 AND SERIAL_NO = :3 AND DEPT_CODE = :4 AND PROCESS_CODE = :5
                    ORDER BY TO_NUMBER(CHECKBOX_INDEX)
                """, (indexNo[:8], indexNo[8:], serial, dept, process))
                checkbox_positions = cursor.fetchall()
            finally:
                cursor.close()
                connection.close()

            draw = ImageDraw.Draw(pil_image)
            merged_boxes = []
            for box in checkbox_positions:
                x, y, width, height = box[1], box[2], box[3], box[4]
                # 먼저 흰색 사각형을 그립니다
                draw.rectangle([x, y, x + width, y + height], fill='white')
                # 그 다음 빨간색 테두리를 그립니다
                draw.rectangle([x, y, x + width, y + height], outline='red')
                merged_boxes.append({
                    'x': x,
                    'y': y,
                    'width': width,
                    'height': height
                })
        else:
            # Process 내의 파일에서 사각형 인식
            numpy_image = np.array(pil_image)
            numpy_image = numpy_image[:, :, [2, 1, 0]]
            # process 코드를 전달하여 체크박스 찾기
            result_pil_image, boxes = self.image_processor.find_checkboxes(numpy_image, process, model=model, dept=dept)
            # 비슷한 위치의 박스를 통합하는 함수
            def merge_similar_boxes(boxes, threshold=20):
                merged_boxes = []
                for box in boxes:
                    if not merged_boxes:
                        merged_boxes.append(box)
                    else:
                        merged = False
                        for i, merged_box in enumerate(merged_boxes):
                            if (abs(box['x'] - merged_box['x']) < threshold and
                                abs(box['y'] - merged_box['y']) < threshold):
                                # 비슷한 위치의 박스를 발견하면 평균값으로 통합
                                merged_boxes[i] = {
                                    'x': (box['x'] + merged_box['x']) // 2,
                                    'y': (box['y'] + merged_box['y']) // 2,
                                    'width': max(box['width'], merged_box['width']),
                                    'height': max(box['height'], merged_box['height'])
                                }
                                merged = True
                                break
                        if not merged:
                            merged_boxes.append(box)
                return merged_boxes
            # 박스 통합 적용
            merged_boxes = merge_similar_boxes(boxes)
            
            pil_image = result_pil_image
        # 이미지 저장   
        img_io = io.BytesIO()
        pil_image.save(img_io, 'PNG', quality=70)
        img_io.seek(0)
        encoded_img_data = base64.b64encode(img_io.getvalue()).decode('utf-8')

        return jsonify({
            'image_url': 'data:image/png;base64,' + encoded_img_data,
            'checkboxes': merged_boxes,
            'is_checked_image': is_checked_image
        })

    @login_required
    def insert_dcs_history(self):
        """
        - FormData로 넘어온 serialNo, processCode, deptCode, empNo, indexNo 등
        - DCS_HISTORY에 MERGE
        - JSON으로 성공/에러 응답
        """
        if request.method == 'POST':
            serial_no = request.form['serialNo']
            process_code = request.form['processCode']
            deptCode = request.form['deptCode']
            empNo = request.form['empNo']
            indexNo = request.form['indexNo'][:-2]
            indexNo_sfix = request.form['indexNo'][-2:]
            date_str = datetime.now()
            pc_name = socket.gethostname()
            if not all([serial_no, process_code, deptCode, empNo, indexNo]):
                return jsonify({'error': '파라미터가 누락되었습니다.'}), 400

            connection = self.db_manager_2.connect()
            cursor = connection.cursor()
            try:
                sql = """
                    MERGE INTO DCS_HISTORY USING dual
                    ON (INDEX_NO = :1 AND INDEX_NO_SFIX = :2 AND SERIAL_NO = :3 AND DEPT_CODE = :4 AND PROCESS_CODE = :5)
                    WHEN MATCHED THEN
                        UPDATE SET EMP_NO = :6, RENEWAL_D = :7, RENEWAL_BY = :8
                    WHEN NOT MATCHED THEN
                        INSERT (INDEX_NO, INDEX_NO_SFIX, SERIAL_NO, DEPT_CODE, PROCESS_CODE, EMP_NO, ENTRY_D, ENTRY_BY, DATA_ST)
                        VALUES (:1, :2, :3, :4, :5, :6, :7, :8, 'A')
                """
                
                params = (indexNo, indexNo_sfix, serial_no, deptCode, process_code, empNo, date_str, pc_name)
                
                cursor.execute(sql, params)
                connection.commit()
                return jsonify({'message': 'DCS_HISTORY 저장(병합) 완료'}), 200
            
            except Exception as e:
                connection.rollback()
                return jsonify({'error': str(e)}), 500
            finally:
                if 'cursor' in locals():
                    cursor.close()
                if 'connection' in locals():
                    connection.close()
        else:
            return jsonify({'error': 'Only POST method is allowed'}), 405

    @login_required
    def get_product_info(self):
        # 제품 정보 가져오기
        logging.info("=== get_product_info called ===")
        if request.method == 'POST':
            index_no_hex = request.form['indexNo'].strip()
            dept_code = request.form.get('deptCode', '')  # HTML에서 전달받은 dept_code
            logging.info(f"Received IndexNo (base 32): {index_no_hex}, DeptCode: '{dept_code}'")
            # 32진수를 10진수로 변환
            index_no_decimal = int(index_no_hex, 32)
            logging.debug(f"Converted IndexNo to Decimal: {index_no_decimal}")
            # 10진수를 문열로 변환
            index_no_str = str(index_no_decimal)
            # 문자열 앞에 0을 채워서 10자리로 만들고 마지막 두 자리를 추출
            index_no = index_no_str.zfill(10)[:-2]
            index_no_sfix = index_no_str[-2:]

            connection = self.db_manager_2.connect()
            cursor = connection.cursor()
            try:
                # SQL 파일 읽기
                with open('.\\sql\\join_prod_info_by_index.sql', 'r', encoding='utf-8') as file:
                    sql = file.read().format(index_no=index_no, index_no_sfix=index_no_sfix)
                cursor.execute(sql)
                product_info = cursor.fetchone()
                if product_info:
                    # 디버깅 로그 추가
                    logging.info(f"Product info fetched - Total columns: {len(product_info)}")
                    logging.info(f"DeptCode received: '{dept_code}'")
                    if len(product_info) > 15:
                        logging.info(f"SEQ field (index 15): {product_info[15]}")
                    logging.info(f"START_NO field (index 9): {product_info[9]}")
                    
                    # dept_code가 3186일 때 SEQ를 construction_No로 사용
                    if dept_code == '3186' or 'JUXTA' in dept_code:
                        construction_no = product_info[15] if len(product_info) > 15 else product_info[9]
                        logging.info(f"Using SEQ for JUXTA: {construction_no}")
                    else:
                        construction_no = product_info[9]  # 기존 START_NO 필드
                        logging.info(f"Using START_NO for non-JUXTA: {construction_no}")
                    
                    return jsonify({
                        'MS_CODE': product_info[10],
                        'Serial_No': product_info[6], 
                        'Index_No': index_no + index_no_sfix,
                        'construction_No': construction_no,
                        'MODEL': product_info[12]  # MODEL 정보 추가
                    })
                else:
                    return jsonify({'error': 'DB에 없는 제품 정보입니다.'}), 404
            finally:
                cursor.close()
                connection.close()

    @login_required
    def search_history(self):
        start_date = request.form.get('startDate')
        end_date = request.form.get('endDate')
        serial_number = request.form.get('serialNumber', '').strip()
        deptCode = request.form.get('deptSelect')
        process_codes_str = request.form.get('processCodes', '')

        logging.info(f"검색 파라미터: serial={serial_number}, dept={deptCode}, process_codes={process_codes_str}")

        # 두 데이터베이스 연결
        connection1 = self.db_manager_1.connect()
        connection2 = self.db_manager_2.connect()
        cursor1 = connection1.cursor()
        cursor2 = connection2.cursor()
        
        try:
            case_statements = []
            process_codes = {code.split(':')[0]: code.split(':')[1] for code in process_codes_str.split(',') if code}
            
            # 먼저 DCS_HISTORY에서 작업자 번호 목록을 가져옴
            emp_no_sql = f"""
            SELECT DISTINCT h.EMP_NO
            FROM DCS_HISTORY h
            WHERE h.DEPT_CODE LIKE :dept_code
            AND h.EMP_NO IS NOT NULL
            """
            cursor2.execute(emp_no_sql, {'dept_code': f"%{deptCode}%"})
            emp_nos = [row[0] for row in cursor2.fetchall()]

            # EMPM에서 작업자 정보를 가져와 딕셔너리로 저장
            emp_info = {}
            if emp_nos:
                emp_list = ",".join(f"'{no}'" for no in emp_nos)
                emp_sql = f"SELECT EMP_NO, EMP_NAMEK FROM EMPM WHERE EMP_NO IN ({emp_list})"
                cursor1.execute(emp_sql)
                emp_info = {row[0]: row[1] for row in cursor1.fetchall()}

            for code, name in process_codes.items():
                case_statements.append(f"MAX(CASE WHEN PROCESS_CODE = '{code}' THEN '{name}' END) AS \"{name}\"")
                case_statements.append(f"MAX(CASE WHEN PROCESS_CODE = '{code}' THEN COALESCE(TO_CHAR(RENEWAL_D, 'Dy, dd Mon yyyy hh24:mi:ss'), TO_CHAR(ENTRY_D, 'Dy, dd Mon yyyy hh24:mi:ss')) END) AS \"{name} 시간\"")
                case_statements.append(f"MAX(CASE WHEN PROCESS_CODE = '{code}' THEN STATUS END) AS \"{name} 상태\"")
                case_statements.append(f"MAX(CASE WHEN PROCESS_CODE = '{code}' THEN h.EMP_NO END) AS \"{name} 작업자 번호\"")

            # 서브쿼리로 날짜 조건에 맞는 시리얼 번호를 먼저 찾습니다
            date_conditions = []
            if start_date:
                date_conditions.append("ENTRY_D >= TO_DATE(:start_date, 'YYYY-MM-DD')")
            if end_date:
                date_conditions.append("ENTRY_D <= TO_DATE(:end_date, 'YYYY-MM-DD') + 1")

            date_where_clause = " AND ".join(date_conditions) if date_conditions else "1=1"
            
            sql = f"""
            WITH FILTERED_SERIALS AS (
                SELECT DISTINCT SERIAL_NO
                FROM DCS_HISTORY
                WHERE DEPT_CODE LIKE :dept_code
                AND {date_where_clause}
                {f"AND SERIAL_NO LIKE :serial_number" if serial_number else ""}
            )
            SELECT h.SERIAL_NO, {', '.join(case_statements)}
            FROM DCS_HISTORY h
            INNER JOIN FILTERED_SERIALS fs ON h.SERIAL_NO = fs.SERIAL_NO
            WHERE h.DEPT_CODE LIKE :dept_code
            GROUP BY h.SERIAL_NO
            """

            params = {'dept_code': f"%{deptCode}%"}
            if start_date:
                params['start_date'] = start_date
            if end_date:
                params['end_date'] = end_date
            if serial_number:
                params['serial_number'] = f"%{serial_number}%"

            cursor2.execute(sql, params)
            results = cursor2.fetchall()
            formatted_results = []
            
            for result in results:
                result_dict = dict(zip([key[0] for key in cursor2.description], result))
                for process in process_codes.values():
                    if result_dict[f"{process} 시간"] is None:
                        result_dict[f"{process} 상태"] = 0
                        result_dict[f"{process} 시간"] = "-"
                        result_dict[f"{process} 작업자 번호"] = "-"
                        result_dict[f"{process} 작업자 이름"] = "-"
                    else:
                        emp_no = result_dict[f"{process} 작업자 번호"]
                        result_dict[f"{process} 작업자 이름"] = emp_info.get(emp_no, "-") if emp_no else "-"
                formatted_results.append(result_dict)
            return jsonify(formatted_results)
        except Exception as e:
            return jsonify({'error': str(e)}), 500
        finally:
            cursor1.close()
            cursor2.close()
            connection1.close()
            connection2.close()

    @login_required
    def checksheet_history(self):
        if 'employee_name' not in session or 'dept_info' not in session:
            return redirect(url_for('login'))
        employee_name = session.get('employee_name', 'Unknown')
        dept_info = session.get('dept_info', 'Unknown')
        return render_template('checksheet-history.html', employee_name=employee_name, dept_info=dept_info)

    @login_required
    def list_files(self, directory):
        """디렉토리 내의 파일 목록을 반환합니다."""
        # 로컬 경로와 네트워크 경로 모두 확인
        local_path = os.path.join(self.app.config['UPLOAD_FOLDER'], directory)
        network_path = os.path.join(self.app.config['NETWORK_PATH'], directory)
        
        try:
            files = set()  # 중복 제거를 위해 set 사용
            
            # 로컬 경로 확인
            if os.path.exists(local_path):
                files.update(os.listdir(local_path))
                
            # 네트워크 경로 확인
            if os.path.exists(network_path):
                files.update(os.listdir(network_path))
                
            return jsonify(list(files))
        except Exception as e:
            return jsonify({'error': str(e)}), 500

    @login_required
    def serve_file(self, filepath):
        """지정된 파일을 클라이언트에 제공합니다."""
        try:
            # 로컬과 네트워크 경로 모두 확인
            local_path = safe_join(self.app.config['UPLOAD_FOLDER'], filepath)
            network_path = safe_join(self.app.config['NETWORK_PATH'], filepath)
            
            # 로컬 경로 먼저 확인
            if os.path.isfile(local_path):
                directory, filename = os.path.split(local_path)
                return send_from_directory(directory, filename)
            
            # 네트워크 경로 확인
            if os.path.isfile(network_path):
                directory, filename = os.path.split(network_path)
                return send_from_directory(directory, filename)
                
            raise FileNotFoundError('The requested file was not found on the server.')
            
        except Exception as e:
            return jsonify({'error': str(e)}), 404

    def send_config(self):
        """ 클라이언트에 설정 정보를 제공하는 엔드포인트 """
        config_data = {
            'uploadFolder': self.app.config['UPLOAD_FOLDER']
        }
        return jsonify(config_data)

    def check_login_status(self):
        """ 로그인 상태 확인 """
        if 'logged_in' in session and session['logged_in']:
            return jsonify({'loggedIn': True})
        return jsonify({'loggedIn': False})

    def save_checkbox_states(self):
        """ 체크박스 상태 저장 """
        data = request.json
        index_no = data['indexNo'][:8]
        index_no_sfix = data['indexNo'][8:]
        serial_no = data['serialNo']
        dept_code = data['deptCode']
        process_code = data['processCode']
        checkbox_states = data['checkboxStates']
        checkbox_positions = data['checkboxPositions']
        pc_name = socket.gethostname()
        # 데이터베이스에 정보 삽입
        connection = self.db_manager_2.connect()
        cursor = connection.cursor()
        # print(checkbox_states)
        # print(checkbox_positions)
        try:
            for index, state in checkbox_states.items():
                position = checkbox_positions[index]
                cursor.execute("""
                    MERGE INTO CHECKBOX_STATES cs
                    USING (SELECT :1 AS INDEX_NO, :2 AS INDEX_NO_SFIX, :3 AS SERIAL_NO, 
                                :4 AS DEPT_CODE, :5 AS PROCESS_CODE, :6 AS CHECKBOX_INDEX FROM DUAL) src
                    ON (cs.INDEX_NO = src.INDEX_NO AND cs.INDEX_NO_SFIX = src.INDEX_NO_SFIX 
                        AND cs.SERIAL_NO = src.SERIAL_NO AND cs.DEPT_CODE = src.DEPT_CODE 
                        AND cs.PROCESS_CODE = src.PROCESS_CODE AND cs.CHECKBOX_INDEX = src.CHECKBOX_INDEX)
                    WHEN MATCHED THEN
                        UPDATE SET cs.STATE = :7, cs.X_POSITION = :8, cs.Y_POSITION = :9, 
                                cs.WIDTH = :10, cs.HEIGHT = :11, cs.RENEWAL_D = CURRENT_TIMESTAMP, cs.RENEWAL_BY = :12
                    WHEN NOT MATCHED THEN
                        INSERT (INDEX_NO, INDEX_NO_SFIX, SERIAL_NO, DEPT_CODE, PROCESS_CODE, CHECKBOX_INDEX, 
                                STATE, X_POSITION, Y_POSITION, WIDTH, HEIGHT, ENTRY_BY, RENEWAL_BY, DATA_ST)
                        VALUES (:1, :2, :3, :4, :5, :6, :7, :8, :9, :10, :11, :12, :12, 'A')
                """, (index_no, index_no_sfix, serial_no, dept_code, process_code, index, 
                    state, position['x'], position['y'], position['width'], position['height'], pc_name))
            # 데이터베이스에 정보 삽입
            connection.commit()
            return jsonify({'message': 'Checkbox states and positions saved successfully'})
        except Exception as e:
            connection.rollback()
            return jsonify({'error': str(e)}), 500
        finally:
            cursor.close()
            connection.close()

    def get_checkbox_states(self):
        """ 체크박스 상태 조회 """
        index_no = request.args.get('indexNo')[:8]
        index_no_sfix = request.args.get('indexNo')[8:]
        serial_no = request.args.get('serialNo')
        dept_code = request.args.get('deptCode')
        process_code = request.args.get('processCode')

        connection = self.db_manager_2.connect()
        cursor = connection.cursor()
        # SQL 쿼리 생성 - Y_POSITION으로 먼저 렬하고, 같은 Y값을 가진 항목들은 X_POSITION으로 정렬
        sql = """
            SELECT CHECKBOX_INDEX, STATE 
            FROM CHECKBOX_STATES
            WHERE INDEX_NO = :1 AND INDEX_NO_SFIX = :2 AND SERIAL_NO = :3 AND DEPT_CODE = :4 AND PROCESS_CODE = :5 AND DATA_ST = 'A'
            ORDER BY TO_NUMBER(CHECKBOX_INDEX)
        """

        try:
            cursor.execute(sql, (index_no, index_no_sfix, serial_no, dept_code, process_code))
            results = cursor.fetchall()
            checkbox_states = {str(row[0]): row[1] for row in results}
            return jsonify(checkbox_states)
        except Exception as e:
            return jsonify({'error': str(e)}), 500
        finally:
            cursor.close()
            connection.close()

    def check_previous_process(self):
        data = request.get_json()
        serial_no = data.get('serialNo')
        current_process = data.get('currentProcessCode')
        dept_code = data.get('deptCode')
        
        # 공정 순서 정의
        # ymfk02 - PRBS0010참조
        dept_process_map = {
            '3165': {  # UTA
                'order': ['08', '06', '11', '15'],
                'skip':  ['08', '06']  # 이전 공정 체크를 스킵할 공정
            },
            '3186': {  # JUXTA
                'order': ['04', '07', '10', '11'],
                'skip':  ['04','07']        # 이전 공정은 이전 공정 체크 안 함
            },
            '3188': {  # NEWSC
                'order' : ['06', '09'],
                'skip' : ['06']
            }
        }

        try:
            # 현재 공정의 인덱스 찾기
            process_order = dept_process_map[dept_code]['order']
            skip_processes = dept_process_map[dept_code]['skip']

            current_index = process_order.index(current_process)
            
            # 부품SET(08)와 단자체결기(06)는 이전 공정 체크 불필요
            if current_process in skip_processes:
                return jsonify({'previousCompleted': True})
                
            # 이전 공정 코드 가져오기
            previous_process = process_order[current_index - 1]
            
            connection = self.db_manager_2.connect()
            cursor = connection.cursor()
            
            # 이전 공정의 완료 상태 확인
            sql = """
                SELECT STATUS 
                FROM DCS_HISTORY
                WHERE SERIAL_NO = :1 
                  AND DEPT_CODE = :2 
                  AND PROCESS_CODE = :3
                  AND DATA_ST = 'A'
            """
            
            cursor.execute(sql, (serial_no, dept_code, previous_process))
            result = cursor.fetchone()
            
            # 이전 공정이 완료되지 않았거나 데이터가 없는 경우
            if not result or result[0] != 1:  # 1은 OK 상태
                return jsonify({'previousCompleted': False})
                
            return jsonify({'previousCompleted': True})
        finally:
            cursor.close()
            connection.close()

    def refresh_session(self):
        if 'logged_in' in session and session['logged_in']:
            session.modified = True
            return jsonify({'valid': True})
        return jsonify({'valid': False})

    @login_required
    def list_network_files(self, directory):
        """네트워크 경로의 파일 목록을 반환합니다."""
        actual_path = os.path.join(self.app.config['NETWORK_PATH'], directory)
        try:
            files = os.listdir(actual_path)
            return jsonify(files)
        except Exception as e:
            return jsonify({'error': str(e)}), 500

    @login_required
    def get_network_file(self, filepath):
        try:
            # 네트워크 경로 구성
            file_path = os.path.join(
                self.app.config['NETWORK_PATH'],
                filepath
            )
            
            if os.path.exists(file_path):
                return send_file(file_path)
            else:
                return jsonify({'error': 'File not found'}), 404
                
        except Exception as e:
            return jsonify({'error': str(e)}), 500

    def is_all_process_completed(self, indexNo, deptCode, serial_no):
        """
        모든 공정이 완료되었는지 확인하는 함수 (부품SET 제외)
        
        :param indexNo: 인덱스 번호
        :param deptCode: 부서 코드
        :param serial_no: 시리얼 번호
        :return: 모든 공정이 완료되었으면 True, 아니면 False
        """

        try:
            connection = self.db_manager_2.connect()
            cursor = connection.cursor()
            
            # 각 필수 공정별 상태 확인
            required_processes = []
            if deptCode == '3165':
                required_processes = ['06','11','15']
            elif deptCode == '3186':
                required_processes = ['07','10','11']
            elif deptCode == '3188' :
                required_processes = ['06', '09']
            else:
                # 그 외 부서코드는 처리 대상 외
                print(f"알 수 없는 부서 코드: {deptCode}, 공정 완료 체크 로직 없음.")
                return True  # 혹은 False
            sql = """
                SELECT PROCESS_CODE, STATUS 
                FROM DCS_HISTORY
                WHERE INDEX_NO = :1 
                  AND SERIAL_NO = :2 
                  AND DEPT_CODE = :3
                  AND PROCESS_CODE = :4
                  AND DATA_ST = 'A'
            """
            
            # 각 필수 공정에 대해 상태 확인
            for process in required_processes:
                cursor.execute(sql, (indexNo, serial_no, deptCode, process))
                result = cursor.fetchone()
                if not result or result[1] != 1:  # 공정이 없거나 STATUS가 1이 아닌 경우
                    return False
                    
            return True  # 모든 필수 공정이 STATUS 1로 확인된 경우
            
        except Exception as e:
            print(f"모든 공정 완료 확인 중 오류 발생: {e}")
            return False
        finally:
            cursor.close()
            connection.close()

    def get_settings(self):
        """설정 파일을 읽어서 반환하는 메서드"""
        try:
            if not os.path.exists(self.settings_path):
                # 설정 파일이 없으면 기본값으로 생성
                default_settings = {
                    "autoCompleteCode": "AAAAAA"
                }
                with open(self.settings_path, 'w', encoding='utf-8') as f:
                    json.dump(default_settings, f, indent=4)
                return jsonify(default_settings)

            with open(self.settings_path, 'r', encoding='utf-8') as f:
                settings = json.load(f)
                return jsonify(settings)
        except Exception as e:
            return jsonify({'error': str(e)}), 500

    def check_serial_in_dcs_history(self, serial_no, process_code):
        """DCS_HISTORY에서 SERIAL_NO와 PROCESS_CODE로 존재 여부를 확인하는 함수"""
        try:
            connection = self.db_manager_2.connect()
            cursor = connection.cursor()
            
            sql = """
                SELECT COUNT(*)
                FROM DCS_HISTORY
                WHERE SERIAL_NO = :1
                  AND PROCESS_CODE = :2
                  AND DATA_ST = 'A'
            """
            cursor.execute(sql, (serial_no, process_code))
            result = cursor.fetchone()
            
            return result[0] > 0
            
        finally:
            cursor.close()
            connection.close()

    @login_required
    def update_and_insert_product_info(self):
        data = request.get_json()
        indexNo = data.get('indexNo')[:-2]
        indexNo_sfix = data.get('indexNo')[-2:]
        serialNo = data.get('serialNo')
        processCode = data.get('processCode')
        dcsData = data.get('dcsData')  # DCS_HISTORY 상태 정보

        # dcsData에서 필요한 정보 추출
        prev_index_no = dcsData.get('indexNo')[:-2]
        prev_index_no_sfix = dcsData.get('indexNo')[-2:]
        
        date_str = datetime.now()
        pc_name = socket.gethostname()
        # 데이터 유효성 검사
        if not all([indexNo, indexNo_sfix, serialNo, processCode]):
            return jsonify({'error': '필수 데이터가 누락되었습니다.'}), 400

        try:
            connection = self.db_manager_2.connect()
            cursor = connection.cursor()

            # 트랜잭션 시작
            connection.begin()

            # DCS_HISTORY 테이블 업데이트: DATA_ST을 'D'로 변경
            update_dcs_history_sql = """
                UPDATE DCS_HISTORY
                SET DATA_ST = 'D'
                WHERE SERIAL_NO = :1 AND PROCESS_CODE = :2
            """
            cursor.execute(update_dcs_history_sql, (serialNo, processCode))

            # CHECKBOX_STATES 테이블 업데이트: DATA_ST을 'D'로 변경
            update_checkbox_states_sql = """
                UPDATE CHECKBOX_STATES
                SET DATA_ST = 'D'
                WHERE SERIAL_NO = :1 AND PROCESS_CODE = :2
            """
            cursor.execute(update_checkbox_states_sql, (serialNo, processCode))

            # 새로운 레코드 삽입 - processCode는 현재 선택된 공정 코드 사용
            insert_dcs_history_sql = """
                INSERT INTO DCS_HISTORY (
                    INDEX_NO, INDEX_NO_SFIX, SERIAL_NO, DEPT_CODE, PROCESS_CODE, STATUS,
                    EMP_NO, PREV_INDEX_NO, PREV_INDEX_NO_SFIX, ENTRY_D, ENTRY_BY
                ) VALUES (
                    :1, :2, :3, :4, :5, :6,
                    :7, :8, :9, :10, :11
                )
            """
            cursor.execute(insert_dcs_history_sql, (
                indexNo, indexNo_sfix, dcsData['serialNo'], dcsData['deptCode'],  # SERIAL_NO, DEPT_CODE
                processCode, dcsData['status'],  # processCode, STATUS
                dcsData['empNo'], dcsData['indexNo'][:-2],  # EMP_NO, PREV_INDEX_NO
                dcsData['indexNo'][-2:], date_str, pc_name  # PREV_INDEX_NO_SFIX, ENTRY_D, ENTRY_BY
            ))

            select_checkbox_states_sql = """
                WITH RANKED_STATES AS (
                    SELECT a.*, 
                           RANK() OVER (
                               PARTITION BY CHECKBOX_INDEX
                               ORDER BY 
                                   CASE WHEN PROCESS_CODE = :1 THEN 0 ELSE 1 END,
                                   TO_NUMBER(INDEX_NO || INDEX_NO_SFIX) DESC
                           ) as RNK
                    FROM CHECKBOX_STATES a
                    WHERE SERIAL_NO = :2
                )
                SELECT 
                    INDEX_NO, INDEX_NO_SFIX, SERIAL_NO, DEPT_CODE, PROCESS_CODE,
                    CHECKBOX_INDEX, STATE,
                    X_POSITION, Y_POSITION, WIDTH, HEIGHT, PREV_INDEX_NO, PREV_INDEX_NO_SFIX, DATA_ST
                FROM RANKED_STATES
                WHERE RNK = 1
                ORDER BY TO_NUMBER(CHECKBOX_INDEX)
            """
            cursor.execute(select_checkbox_states_sql, (processCode, serialNo))
            checkbox_results = cursor.fetchall()  # fetchone() 대신 fetchall() 사용

            # 체크박스 상태 데이터 삽입
            insert_checkbox_states_sql = """
                INSERT INTO CHECKBOX_STATES (
                    INDEX_NO, INDEX_NO_SFIX, SERIAL_NO, DEPT_CODE, PROCESS_CODE,
                    CHECKBOX_INDEX, STATE, X_POSITION, Y_POSITION, WIDTH, HEIGHT,
                    PREV_INDEX_NO, PREV_INDEX_NO_SFIX, ENTRY_D, ENTRY_BY
                ) VALUES (
                    :1, :2, :3, :4, :5,
                    :6, :7, :8, :9, :10, :11,
                    :12, :13, :14, :15
                )
            """
            
            for checkbox_result in checkbox_results:
                cursor.execute(insert_checkbox_states_sql, (
                    indexNo, indexNo_sfix,
                    checkbox_result[2],  # SERIAL_NO
                    checkbox_result[3],  # DEPT_CODE
                    checkbox_result[4],  # PROCESS_CODE
                    checkbox_result[5],  # CHECKBOX_INDEX
                    checkbox_result[6],  # STATE
                    checkbox_result[7],  # X_POSITION
                    checkbox_result[8],  # Y_POSITION
                    checkbox_result[9],  # WIDTH
                    checkbox_result[10], # HEIGHT
                    checkbox_result[0],  # PREV_INDEX_NO (이전 데이터의 INDEX_NO)
                    checkbox_result[1],  # PREV_INDEX_NO_SFIX (이전 데이터의 INDEX_NO_SFIX)
                    date_str,           # ENTRY_D (현재 시간)
                    pc_name             # ENTRY_BY (PC 이름)
                ))

            # 트랜잭션 커밋
            connection.commit()

            return jsonify({'message': '제품 정보가 성공적으로 업데이트되었습니다.'}), 200

        except Exception as e:
            # 트랜잭션 롤백
            connection.rollback()
            logging.error(f"제품 정보 업데이트 중 오류 발생: {e}")
            return jsonify({'error': '제품 정보 업데이트 중 오류가 발생했습니다.'}), 500
        finally:
            cursor.close()
            connection.close()

    def check_index_in_dcs_history(self):
        try:
            data = request.get_json()
            index_no_hex = data.get('indexNo')
            dept_code = data.get('deptCode')
            
            if not index_no_hex or not dept_code:
                return jsonify({'error': '필수 파라미터가 누락되었습니다.'}), 400

            # 32진수를 10진수로 변환
            index_no_decimal = int(index_no_hex, 32)
            index_no_str = str(index_no_decimal)
            index_no = index_no_str.zfill(10)[:-2]
            index_no_sfix = index_no_str[-2:]

            connection = self.db_manager_2.connect()
            cursor = connection.cursor()

            check_sql = """
                SELECT DISTINCT
                    a.INDEX_NO, 
                    a.INDEX_NO_SFIX, 
                    a.SERIAL_NO,
                    b.MS_CODE,
                    a.DATA_ST,
                    c.START_NO
                FROM DCS_HISTORY a
                JOIN TDSC952 c ON a.INDEX_NO = c.INDEX_NO 
                    AND a.INDEX_NO_SFIX = c.INDEX_NO_SFIX
                JOIN TDSC951 b ON c.PROD_NO = b.PROD_NO 
                    AND c.PROD_INST_SHEET_REV_NO = b.PROD_INST_SHEET_REV_NO
                    AND c.PROD_INST_REV_NO = b.PROD_INST_REV_NO
                    AND c.PROD_ITEM_REV_NO = b.PROD_ITEM_REV_NO
                    AND c.ORDER_NO = b.ORDER_NO
                    AND c.ITEM_NO = b.ITEM_NO
                    AND b.CANCEL_D IS NULL
                WHERE a.INDEX_NO = :1 
                    AND a.INDEX_NO_SFIX = :2 
                    AND a.DEPT_CODE = :3
                AND ROWNUM = 1
            """
            cursor.execute(check_sql, (index_no, index_no_sfix, dept_code))
            result = cursor.fetchone()

            if result:
                return jsonify({
                    'exists': True,
                    'productInfo': {
                        'Index_No': result[0] + result[1],
                        'Serial_No': result[2],
                        'MS_CODE': result[3],
                        'DATA_ST': result[4],
                        'construction_No': result[5] if result[5] is not None else '착공번호 없음'
                    }
                })
            else:
                return jsonify({
                    'exists': False,
                    'productInfo': None
                })

        except Exception as e:
            logging.error(f"DCS_HISTORY 조회 중 오류 발생: {str(e)}")
            return jsonify({'error': '데이터베이스 조회 중 오류가 발생했습니다.'}), 500
        finally:
            if cursor:
                cursor.close()
            if connection:
                connection.close()

    @login_required
    def check_dcs_history_status(self):
        try:
            data = request.get_json()
            serialNo = data.get('serialNo')
            processCode = data.get('processCode')

            connection = self.db_manager_2.connect()
            cursor = connection.cursor()

            # DCS_HISTORY 레코드 조회
            select_dcs_history_sql = """
                SELECT INDEX_NO, INDEX_NO_SFIX, SERIAL_NO, DEPT_CODE, PROCESS_CODE, STATUS,
                       EMP_NO, ENTRY_BY, PREV_INDEX_NO, PREV_INDEX_NO_SFIX, DATA_ST
                FROM (
                    SELECT *
                    FROM DCS_HISTORY
                    WHERE SERIAL_NO = :1
                    ORDER BY 
                        CASE WHEN PROCESS_CODE = :2 THEN 0 ELSE 1 END,
                        TO_NUMBER(INDEX_NO || INDEX_NO_SFIX) DESC
                )
                WHERE ROWNUM = 1
            """
            cursor.execute(select_dcs_history_sql, (serialNo, processCode))
            dcs_result = cursor.fetchone()

            if dcs_result:
                return jsonify({
                    'exists': True,
                    'data': {
                        'indexNo': dcs_result[0] + dcs_result[1],  # INDEX_NO + INDEX_NO_SFIX
                        'serialNo': dcs_result[2],
                        'deptCode': dcs_result[3],
                        'processCode': dcs_result[4],
                        'status': dcs_result[5],
                        'empNo': dcs_result[6],
                        'entryBy': dcs_result[7],
                        'prevIndexNo': dcs_result[8],
                        'prevIndexNoSfix': dcs_result[9],
                        'dataSt': dcs_result[10]  # DATA_ST
                    }
                })
            else:
                return jsonify({
                    'exists': False
                })

        except Exception as e:
            logging.error(f"DCS_HISTORY 상태 확인 중 오류 발생: {str(e)}")
            return jsonify({'error': str(e)}), 500





