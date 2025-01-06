from flask import render_template, request, jsonify, url_for, send_from_directory, redirect, session, send_file
import logging
from werkzeug.utils import secure_filename, safe_join
from datetime import datetime
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

class RouteHandler:
    def __init__(self, app, db_manager_1, db_manager_2, image_processor):
        # 클래스 초기화 메서드
        self.app = app
        self.db_manager_1 = db_manager_1
        self.db_manager_2 = db_manager_2
        self.image_processor = image_processor
        self.settings_path = 'Settings.json'  # settings.json 파일 경로 추가
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
            ('/check_login_status', self.check_login_status, ['GET']),
            ('/save_checkbox_states', self.save_checkbox_states, ['POST']),
            ('/get_checkbox_states', self.get_checkbox_states, ['GET']),
            ('/check_previous_process', self.check_previous_process, ['POST']),
            ('/refresh_session', self.refresh_session, ['POST']),
            ('/network/files/list/<dept_code>/Checked/<serial_no>/', self.list_network_files, ['GET']),
            ('/network/files/get/<dept_code>/Checked/<serial_no>/<filename>', self.get_network_file, ['GET']),
            ('/get_settings', self.get_settings, ['GET']),  # 새로운 라우트 추가
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
        filename = secure_filename(f"{request.form['indexNo']}_{serial_no}_{process_code}.png")
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
                
                sql = """
                    MERGE INTO DCS_HISTORY USING dual
                    ON (INDEX_NO = :1 AND INDEX_NO_SFIX = :2 AND SERIAL_NO = :3 AND DEPT_CODE = :4 AND PROCESS_CODE = :5)
                    WHEN MATCHED THEN
                        UPDATE SET STATUS = :6, EMP_NO = :7, RENEWAL_D = :8, RENEWAL_BY = :9
                    WHEN NOT MATCHED THEN
                        INSERT (INDEX_NO, INDEX_NO_SFIX, SERIAL_NO, DEPT_CODE, PROCESS_CODE, STATUS, EMP_NO, ENTRY_D, ENTRY_BY)
                        VALUES (:1, :2, :3, :4, :5, :6, :7, :8, :9)
                """
                
                params = (indexNo, indexNo_sfix, serial_no, deptCode, process_code, result, empNo, date_str, pc_name)
                
                cursor.execute(sql, params)
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
                        
                        # 모든 체크시트 이미지 경로 수집 (부품SET 제외)
                        image_folder = os.path.join(self.app.config['UPLOAD_FOLDER'], deptCode, 'Checked', serial_no)
                        image_files = sorted([
                            os.path.join(image_folder, f) for f in os.listdir(image_folder)
                            if f.startswith(indexNo) and f.endswith('.png') and not f.endswith('08.png')
                        ])
                        
                        # 이미지 합치기 실행
                        ImageProcessor.merge_checksheet_images(image_files, merged_image_path, target_width=800)
                        
                        try:
                            # Checked 폴더의 이미지 삭제
                            checked_folder = os.path.join(self.app.config['UPLOAD_FOLDER'], deptCode, 'Checked', serial_no)
                            if os.path.exists(checked_folder):
                                for file in os.listdir(checked_folder):
                                    file_path = os.path.join(checked_folder, file)
                                    os.remove(file_path)
                                os.rmdir(checked_folder)  # 빈 폴더 삭제
                            
                            # Process 폴더의 이미지 삭제
                            process_folder = os.path.join(self.app.config['UPLOAD_FOLDER'], deptCode, 'Process', serial_no)
                            if os.path.exists(process_folder):
                                for file in os.listdir(process_folder):
                                    file_path = os.path.join(process_folder, file)
                                    os.remove(file_path)
                                os.rmdir(process_folder)  # 빈 폴더 삭제
                            
                        except Exception as e:
                            logging.error(f"이미지 삭제 중 오류 발생: {str(e)}")
                            # 이미지 삭제 실패해도 저장 성공 메시지는 반환
                        
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

    # @login_required
    # def mount_label(self):
    #     # 마운트 라벨 페이지 렌더링
    #     if 'employee_name' not in session or 'dept_info' not in session:
    #         return redirect(url_for('login'))
    #     employee_name = session.get('employee_name', 'Unknown')
    #     dept_info = session.get('dept_info', 'Unknown')
    #     pen_cursor_url = url_for('static', filename='icon/pen-tool.png')
    #     return render_template('mount-label.html', employee_name=employee_name, dept_info=dept_info, pen_cursor_url=pen_cursor_url)

    @login_required
    def upload_image(self, serial_process):
        parts = serial_process.split('_')
        indexNo, dept, serial, process = parts[:4]
        index = int(parts[-1])
        if index != 0:
            index = int(parts[-1]) - 1
        
        # 체크 완료된 이미지 경로 확인 (로컬)
        checked_filename = f"{indexNo}_{serial}_{process}.png"
        checked_file_path = os.path.join(self.app.config['UPLOAD_FOLDER'], dept, 'Checked', serial, checked_filename)
        network_checked_path = os.path.join(self.app.config['NETWORK_PATH'], dept, 'Checked', serial, checked_filename)

        # Process 파일 경로 확인 (로컬 및 네트워크)
        process_filename = f'{serial}_{index}.png'
        process_file_path = os.path.join(self.app.config['UPLOAD_FOLDER'], dept, 'Process', serial, process_filename)
        network_process_path = os.path.join(self.app.config['NETWORK_PATH'], dept, 'Process', serial, process_filename)

        # Master 파일 경로 확인 (로컬 및 네트워크)
        master_pdf_path = os.path.join(self.app.config['UPLOAD_FOLDER'], dept, 'Master', f'{serial}.pdf')
        network_master_path = os.path.join(self.app.config['NETWORK_PATH'], dept, 'Master', f'{serial}.pdf')

        # 체크 완료된 이미지 확인
        if os.path.exists(checked_file_path):
            file_path = checked_file_path
            is_checked_image = True
        elif os.path.exists(network_checked_path):
            file_path = network_checked_path
            is_checked_image = True
        else:
            is_checked_image = False
            # Process 파일 확인
            if os.path.exists(process_file_path):
                file_path = process_file_path
            elif os.path.exists(network_process_path):
                file_path = network_process_path
            else:
                # index가 0이고 Process 파일이 없는 경우 Master PDF 확인
                if index == 0:
                    if os.path.exists(master_pdf_path):
                        master_path = master_pdf_path
                    elif os.path.exists(network_master_path):
                        master_path = network_master_path
                    else:
                        return jsonify({'error': 'Requested master PDF does not exist.'}), 404

                    # Master PDF를 이미지로 변환
                    images = convert_from_path(master_path, dpi=150)
                    master_jpg_path = os.path.join(self.app.config['UPLOAD_FOLDER'], dept, 'Master', f'{serial}.jpg')
                    images[0].save(master_jpg_path, 'JPEG')
                    self.image_processor.split_image_by_horizontal_lines(master_jpg_path)
                    
                    # 변환 후 Process 파일 다시 확인
                    if os.path.exists(process_file_path):
                        file_path = process_file_path
                    else:
                        return jsonify({'error': 'Failed to create process image from master PDF.'}), 500
                else:
                    return jsonify({'error': 'Requested image does not exist.'}), 404

        if not os.path.exists(file_path):
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
            result_pil_image, boxes = self.image_processor.find_checkboxes(numpy_image, process)
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
    def get_product_info(self):
        # 제품 정보 가져오기
        logging.debug("get_product_info called")
        if request.method == 'POST':
            index_no_hex = request.form['indexNo'].strip()
            logging.debug(f"Received IndexNo (base 32): {index_no_hex}")
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
                    return jsonify({
                        'MS_CODE': product_info[10],
                        'Serial_No': product_info[6], 
                        'Index_No': index_no + index_no_sfix
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
        actual_path = os.path.join(self.app.config['UPLOAD_FOLDER'], directory)
        try:
            files = os.listdir(actual_path)
            return jsonify(files)
        except Exception as e:
            return jsonify({'error': str(e)}), 500

    @login_required
    def serve_file(self, filepath):
        """지정된 파일을 클라이언트에 제공합다."""
        # 네트워크 저장 경로
        network_path = self.app.config['UPLOAD_FOLDER']

        # 파일 경로 안전 검증
        try:
            # safe_join을 사용하여 경로를 안전하게 결합하고, 해당 경로에 대한 접근을 확인합니다.
            safe_file_path = safe_join(network_path, filepath)
            if not os.path.isfile(safe_file_path):
                raise FileNotFoundError('The requested file was not found on the server.')

            # 파일 이름 추출 및 send_from_directory를 사용하여 파일 제공
            directory, filename = os.path.split(safe_file_path)
            return send_from_directory(directory, filename)
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

    # def save_mount_label_image(self):
    #     """ 마운트 라벨 이미지 저장 """ 
    #     if 'image' not in request.files:
    #         return jsonify({'error': 'No image part in the request'}), 400
    #     # 파일 저장
    #     file = request.files['image']
    #     serial_no = request.form['serialNo']
    #     process_code = request.form['processCode']
    #     deptCode = request.form['deptCode']
    #     empNo = request.form['empNo']
    #     indexNo = request.form['indexNo'][:-2]
    #     indexNo_sfix = request.form['indexNo'][-2:]
    #     # 파일 이름 생성
    #     filename = f"{indexNo}{indexNo_sfix}_{serial_no}_{process_code}.png"
    #     # 날짜 문자열 생성
    #     date_str = datetime.now().strftime('%Y-%m-%d')
    #     pc_name = socket.gethostname()
    #     # 일일 폴더 생성
    #     daily_folder = os.path.join(self.app.config['UPLOAD_FOLDER'], deptCode, 'MountLabel', serial_no)
    #     # 일일 폴더 존재 여부 확인 및 생성
    #     if not os.path.exists(daily_folder):
    #         os.makedirs(daily_folder)
    #     save_path = os.path.join(daily_folder, filename)
    #     file.save(save_path)
    #     # 이미지 저장 경로 반환
    #     if os.path.exists(save_path):
    #         # 데이터베이스에 정보 삽입
    #         connection = self.db_manager_2.connect()
    #         cursor = connection.cursor()
    #         # SQL 쿼리 생성
    #         sql = """
    #             MERGE INTO DCS_HISTORY USING dual
    #             ON (INDEX_NO = :1 AND INDEX_NO_SFIX = :2 AND SERIAL_NO = :3 AND DEPT_CODE = :4 AND PROCESS_CODE = :5)
    #             WHEN MATCHED THEN
    #                 UPDATE SET STATUS = :6, EMP_NO = :7, RENEWAL_D = :8, RENEWAL_BY = :9
    #             WHEN NOT MATCHED THEN
    #                 INSERT (INDEX_NO, INDEX_NO_SFIX, SERIAL_NO, DEPT_CODE, PROCESS_CODE, STATUS, EMP_NO, ENTRY_D, ENTRY_BY)
    #                 VALUES (:1, :2, :3, :4, :5, :6, :7, :8, :9)
    #         """
    #         params = (indexNo, indexNo_sfix, serial_no, deptCode, process_code, 1, empNo, date_str, pc_name)
    #         # 데이터베이스에 정보 삽입
    #         try:
    #             cursor.execute(sql, params)
    #             connection.commit()
    #             return jsonify({
    #                 'message': f'Image successfully saved at {save_path} and data recorded in database',
    #                 'imagePath': f'/files/get/{deptCode}/MountLabel/{date_str}/{serial_no}/{filename}'
    #             })
    #         except Exception as e:
    #             connection.rollback()
    #             logging.error("Failed to insert image data into database", exc_info=True)
    #             try:
    #                 os.remove(save_path)
    #                 logging.info(f"Removed failed upload file at {save_path}")
    #             except OSError as os_error:
    #                 logging.error(f"Failed to remove file at {save_path}: {os_error}")
    #             return jsonify({'error': str(e)}), 500
    #         finally:
    #             cursor.close()
    #             connection.close()
    #     # 이미지 저장 경로 반환 
    #     return jsonify({
    #         'message': f'Image successfully saved at {save_path}',
    #         'imagePath': f'/files/get/{deptCode}/MountLabel/{date_str}/{serial_no}/{filename}'
    #     })

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
                                STATE, X_POSITION, Y_POSITION, WIDTH, HEIGHT, ENTRY_BY, RENEWAL_BY)
                        VALUES (:1, :2, :3, :4, :5, :6, :7, :8, :9, :10, :11, :12, :12)
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
            WHERE INDEX_NO = :1 AND INDEX_NO_SFIX = :2 AND SERIAL_NO = :3 AND DEPT_CODE = :4 AND PROCESS_CODE = :5
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
        barcode_hex = data.get('serialNo')
        current_process = data.get('currentProcessCode')
        dept_code = data.get('deptCode')
        
        # 32진수를 10진수로 변환
        try:
            index_no_decimal = int(barcode_hex, 32)
        except ValueError:
            return jsonify({'error': '유효하지 않은 바코드 형식입니다.', 'previousCompleted': False}), 400
        
        # 10진수를 문자열로 변환하고 앞의 8자리와 뒤의 2자리로 리
        index_no_str = str(index_no_decimal).zfill(10)
        index_no = index_no_str[:8]
        index_no_sfix = index_no_str[8:]
        
        # 공정 순서 정의
        process_order = ['08', '06', '11', '15']  # 부품SET, 단자체결기, 조립, 출하검사 순서
        
        try:
            # 현재 공정의 인덱스 찾기
            current_index = process_order.index(current_process)
            
            # 부품SET(08)와 단자체결기(06)는 이전 공정 체크 불필요
            if current_process in ['08', '06']:
                return jsonify({'previousCompleted': True})
                
            # 이전 공정 코드 가져오기
            previous_process = process_order[current_index - 1]
            
            connection = self.db_manager_2.connect()
            cursor = connection.cursor()
            
            # 이전 공정의 완료 상태 확인
            sql = """
                SELECT STATUS 
                FROM DCS_HISTORY 
                WHERE INDEX_NO = :1 
                  AND INDEX_NO_SFIX = :2 
                  AND DEPT_CODE = :3 
                  AND PROCESS_CODE = :4
            """
            
            cursor.execute(sql, (index_no, index_no_sfix, dept_code, previous_process))
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
    def list_network_files(self, dept_code, serial_no):
        try:
            if not serial_no:
                return jsonify({'error': '시리얼 번호가 필요합니다.'}), 400

            network_path = os.path.join(self.app.config['NETWORK_PATH'], dept_code, 'Checked', serial_no)
            
            if not os.path.exists(network_path):
                return jsonify([])

            files = [f for f in os.listdir(network_path) if os.path.isfile(os.path.join(network_path, f))]
            return jsonify(files)

        except Exception as e:
            logging.error(f"네트워크 파일 목록 조회 중 오류 발생: {str(e)}")
            return jsonify({'error': str(e)}), 500

    @login_required
    def get_network_file(self, dept_code, serial_no, filename):
        try:
            # 네트워크 경로 구성
            file_path = os.path.join(
                self.app.config['NETWORK_PATH'],
                dept_code,
                'Checked',
                serial_no,
                filename
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
        process_order = ['06', '11', '15']  # 부품SET 제외 후 공정 순서
        try:
            connection = self.db_manager_2.connect()
            cursor = connection.cursor()
            
            # 각 필수 공정별 상태 확인
            completed_processes = {}
            sql = """
                SELECT PROCESS_CODE, STATUS 
                FROM DCS_HISTORY 
                WHERE INDEX_NO = :1 
                  AND SERIAL_NO = :2 
                  AND DEPT_CODE = :3
                  AND PROCESS_CODE = :4
            """
            
            # 각 필수 공정에 대해 상태 확인
            for process in process_order:
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





