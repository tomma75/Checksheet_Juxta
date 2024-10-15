from flask import render_template, request, jsonify, url_for, send_from_directory, redirect, session
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


class RouteHandler:
    def __init__(self, app, db_manager_1, db_manager_2, image_processor):
        # 클래스 초기화 메서드
        self.app = app
        self.db_manager_1 = db_manager_1
        self.db_manager_2 = db_manager_2
        self.image_processor = image_processor
        self.register_routes()

    def register_routes(self):
        # 라우트 등록 메서드
        self.app.route('/config', methods=['GET'])(self.send_config)
        self.app.route('/', methods=['GET', 'POST'])(self.login)
        self.app.route('/login', methods=['GET', 'POST'])(self.login)
        self.app.route('/logout')(self.logout)
        self.app.route('/get_employee_name', methods=['POST'])(self.get_employee_name)
        self.app.route('/save_checked_image', methods=['POST'])(self.save_checked_image)
        self.app.route('/checkSheet')(self.checkSheet)
        # self.app.route('/mount-label')(self.mount_label)
        self.app.route('/upload_image/<serial_process>', methods=['GET'])(self.upload_image)
        self.app.route('/get_product_info', methods=['POST'])(self.get_product_info)
        self.app.route('/search_history', methods=['POST'])(self.search_history)
        self.app.route('/checksheet-history')(self.checksheet_history)
        self.app.route('/files/list/<path:directory>')(self.list_files)
        self.app.route('/files/get/<path:filepath>')(self.serve_file)
        self.app.route('/check_login_status', methods=['GET'])(self.check_login_status)
        # self.app.route('/save_mount_label_image', methods=['POST'])(self.save_mount_label_image)
        self.app.route('/save_checkbox_states', methods=['POST'])(self.save_checkbox_states)
        self.app.route('/get_checkbox_states', methods=['GET'])(self.get_checkbox_states)

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
                return jsonify({'error': 'DB에 없는 사원번호입니다.'}), 404
        finally:
            cursor.close()
            self.db_manager_1.close()

    def save_checked_image(self):
        # 체크된 이미지 저장 메서드
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
        file.save(save_path)

        if os.path.exists(save_path):
            # 데이터베이스에 정보 삽입
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

            # SQL 바인드 파라미터를 위치 기반으로 정의
            params = (indexNo, indexNo_sfix, serial_no, deptCode, process_code, result, empNo, date_str, pc_name)

            try:
                cursor.execute(sql, params)
                connection.commit()
                return jsonify({'message': f'Image successfully saved at {save_path} and data recorded in database'})
            except Exception as e:
                connection.rollback()
                logging.error("Failed to insert image data into database", exc_info=True)
                try:
                    os.remove(save_path)  # 파일 삭제 시도
                    logging.info(f"Removed failed upload file at {save_path}")
                except OSError as os_error:
                    logging.error(f"Failed to remove file at {save_path}: {os_error}")
                return jsonify({'error': str(e)}), 500
            finally:
                cursor.close()
                connection.close()

        return jsonify({'message': f'Image successfully saved at {save_path}'})

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

        # 체크 완료된 이미지 경로 확인
        checked_filename = f"{indexNo}_{serial}_{process}.png"
        checked_file_path = os.path.join(self.app.config['UPLOAD_FOLDER'], dept, 'Checked', serial, checked_filename)

        if os.path.exists(checked_file_path):
            # 체크 완료된 이미지 경로 확인
            file_path = checked_file_path
            is_checked_image = True
        else:
            # Process 내의 파일에서 사각형 인식
            directory = os.path.join(self.app.config['UPLOAD_FOLDER'], dept, 'Process', serial)
            os.makedirs(directory, exist_ok=True)
            filename = f'{serial}_{index}.png'
            file_path = os.path.join(directory, filename)
            is_checked_image = False

            if index == 0 and not os.path.exists(file_path):
                master_pdf_path = os.path.join(self.app.config['UPLOAD_FOLDER'], dept, 'Master', f'{serial}.pdf')
                if os.path.exists(master_pdf_path):
                    images = convert_from_path(master_pdf_path, dpi=150)
                    master_jpg_path = os.path.join(self.app.config['UPLOAD_FOLDER'], dept, 'Master', f'{serial}.jpg')
                    images[0].save(master_jpg_path, 'JPEG')
                    self.image_processor.split_image_by_horizontal_lines(master_jpg_path)
                else:
                    return jsonify({'error': 'Requested master PDF does not exist.'}), 404

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
            result_pil_image, boxes = self.image_processor.find_checkboxes(numpy_image)
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
            # 10진수를 문자열로 변환
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
        # 검색 기록 조회
        start_date = request.form.get('startDate')
        end_date = request.form.get('endDate')
        serial_number = request.form.get('serialNumber', '').strip()
        deptCode = request.form.get('deptSelect')
        process_codes_str = request.form.get('processCodes', '')

        connection = self.db_manager_2.connect()
        cursor = connection.cursor()
        try:
            case_statements = []
            process_codes = {code.split(':')[0]: code.split(':')[1] for code in process_codes_str.split(',') if code}
            for code, name in process_codes.items():
                case_statements.append(f"MAX(CASE WHEN PROCESS_CODE = '{code}' THEN '{name}' END) AS \"{name}\"")
                case_statements.append(f"MAX(CASE WHEN PROCESS_CODE = '{code}' THEN COALESCE(TO_CHAR(RENEWAL_D, 'Dy, dd Mon yyyy hh24:mi:ss'), TO_CHAR(ENTRY_D, 'Dy, dd Mon yyyy hh24:mi:ss')) END) AS \"{name} 시간\"")
                case_statements.append(f"MAX(CASE WHEN PROCESS_CODE = '{code}' THEN STATUS END) AS \"{name} 상태\"")
                case_statements.append(f"MAX(CASE WHEN PROCESS_CODE = '{code}' THEN EMP_NO END) AS \"{name} 작업자 번호\"")

            where_clauses = ["DEPT_CODE LIKE :dept_code"]  # 부서 코드로 필터링
            params = {'dept_code': f"%{deptCode}%"}  # 부서 코드 매개변수 설정

            # 날짜 필터가 제공되면 조건부로 추가
            if start_date:
                where_clauses.append("ENTRY_D >= TO_DATE(:start_date, 'YYYY-MM-DD')")
                params['start_date'] = start_date
            if end_date:
                where_clauses.append("ENTRY_D <= TO_DATE(:end_date, 'YYYY-MM-DD')")
                params['end_date'] = end_date
            if serial_number:
                where_clauses.append("SERIAL_NO LIKE :serial_number")
                params['serial_number'] = f"%{serial_number}%"  # Serial number 필터링
            # SQL 쿼리 생성 
            sql = f"""
            SELECT SERIAL_NO, {', '.join(case_statements)}
            FROM DCS_HISTORY
            WHERE {' AND '.join(where_clauses)}
            GROUP BY SERIAL_NO
            """

            cursor.execute(sql, params)
            results = cursor.fetchall()
            formatted_results = []
            for result in results:
                result_dict = dict(zip([key[0] for key in cursor.description], result))
                for process in process_codes.values():
                    if result_dict[f"{process} 시간"] is None:
                        result_dict[f"{process} 상태"] = 0
                        result_dict[f"{process} 시간"] = "-"
                        result_dict[f"{process} 작업자 번호"] = "-"
                formatted_results.append(result_dict)
            return jsonify(formatted_results)
        except Exception as e:
            return jsonify({'error': str(e)}), 500
        finally:
            cursor.close()
            connection.close()

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
        """지정된 파일을 클라이언트에 제공합니다."""
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
        # SQL 쿼리 생성
        sql = """
            SELECT CHECKBOX_INDEX, STATE 
            FROM CHECKBOX_STATES 
            WHERE INDEX_NO = :1 AND INDEX_NO_SFIX = :2 AND SERIAL_NO = :3 AND DEPT_CODE = :4 AND PROCESS_CODE = :5
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

