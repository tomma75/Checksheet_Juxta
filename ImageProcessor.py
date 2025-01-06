import cv2
from PIL import Image, ImageDraw
import os
import numpy as np

class ImageProcessor:
    @staticmethod
    def find_checkboxes(image, process_code=None):
        gray = cv2.cvtColor(image, cv2.COLOR_RGB2GRAY)
        blurred = cv2.GaussianBlur(gray, (3, 3), 0)
        edges = cv2.Canny(blurred, 50, 150)
        contours, _ = cv2.findContours(edges, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)
        
        boxes = []
        for cnt in contours:
            approx = cv2.approxPolyDP(cnt, 0.04 * cv2.arcLength(cnt, True), True)
            if len(approx) == 4:
                x, y, w, h = cv2.boundingRect(approx)
                aspect_ratio = float(w) / h
                if 0.9 <= aspect_ratio <= 1.13:  # 정사각형에 가까운 비율
                    # 작은 사각형만 선택 (예: 10x10 ~ 30x30 픽셀)
                    if 7 <= w <= 25 and 7 <= h <= 25:
                        # 단자체결기 공정(06)일 경우 제외 영역 체크
                        if process_code == '06':
                            # 제외 영역에 있는 체크박스는 건너뜀
                            if 800 <= x <= image.shape[1] and 200 <= y <= 380:
                                continue
                        
                        # 내부 영역의 균일성 검사
                        mask = np.zeros(gray.shape, np.uint8)
                        cv2.drawContours(mask, [cnt], 0, 255, -1)
                        mean, stddev = cv2.meanStdDev(gray, mask=mask)
                        
                        # 균일성이 높은 경우만 선택
                        if stddev[0][0] < 40:
                            boxes.append({'x': x, 'y': y, 'width': w, 'height': h})
        
        result_image = Image.fromarray(cv2.cvtColor(image, cv2.COLOR_BGR2RGB))
        draw = ImageDraw.Draw(result_image)
        for box in boxes:
            draw.rectangle([box['x'], box['y'], box['x'] + box['width'], box['y'] + box['height']], outline='red')
        return result_image, boxes

    @staticmethod
    def split_image_by_horizontal_lines(image_path, threshold=200, min_row_height=10):
        """
        이미지에서 수평선을 기준으로 이미지를 분할합니다.
        
        :param image_path: 이미지를 분할할 이미지 파일의 경로
        :param threshold: 수평선 검출을 위한 임계값
        :param min_row_height: 최소 행 높이
        :return: 분할된 이미지들의 경로 리스트
        """
        # 이미지 로드
        img = cv2.imread(image_path, cv2.IMREAD_COLOR)
        if img is None:
            print(f"이미지를 불러올 수 없습니다: {image_path}")
            return []

        # 회색조로 변환
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

        # 임계값을 적용하여 이진화
        _, binary = cv2.threshold(gray, threshold, 255, cv2.THRESH_BINARY_INV)

        # 수평 투영을 통해 각 행의 픽셀값 합계를 구함
        horizontal_projection = np.sum(binary, axis=1)

        # 수직 투영을 통해 각 열의 픽셀값 합계를 구함
        vertical_projection = np.sum(binary, axis=0)

        # 회색 행(분할선)을 식별하기 위한 기준 설정
        row_threshold = img.shape[1] * 255 * 0.5

        # 분할선(회색 행)의 위치를 찾는다
        split_positions = []
        in_gray_area = False
        start_position = 0

        # 수평 투영된 값에 대해 반복하며 회색 행을 찾는다
        for i, value in enumerate(horizontal_projection):
            if value > row_threshold and not in_gray_area:
                # 회색 영역의 시작
                in_gray_area = True
                start_position = i
            elif value <= row_threshold and in_gray_area:
                # 회색 영역의 끝
                if (i - start_position) >= min_row_height:
                    # 충분히 높은 행만 분할선으로 취급
                    split_positions.append(start_position)
                in_gray_area = False

        if in_gray_area and (len(horizontal_projection) - start_position) >= min_row_height:
            # 마지막 회색 행을 추가
            split_positions.append(start_position)

        # 좌우 여백(검정 세로선)의 위치를 찾는다
        left_margin = 0
        right_margin = img.shape[1] - 1

        # 왼쪽 마진 찾기 (왼쪽에서 오른쪽으로 탐색)
        for i, value in enumerate(vertical_projection):
            if value > 0:  # 검정 픽셀이 있는 경우
                left_margin = i
                break

        # 오른쪽 마진 찾기 (오른쪽에서 왼쪽으로 탐색)
        for i in range(img.shape[1] - 1, -1, -1):
            if vertical_projection[i] > 0:  # 검정 픽셀이 있는 경우
                right_margin = i
                break

        print(f"최종 마진: left_margin={left_margin}, right_margin={right_margin}")

        # 이미지 분할 및 저장 로직
        cropped_images = []
        start = 0
        split_positions.append(img.shape[0])

        for end in split_positions:
            if start < end and left_margin < right_margin:
                cropped = img[start:end, left_margin:right_margin]
                if cropped.size > 0:
                    cropped_images.append(cropped)
            else:
                print(f"유효하지 않은 크롭 영역: start={start}, end={end}, left_margin={left_margin}, right_margin={right_margin}")
            start = end

        # 이미지 저장 로직
        base_directory = os.path.dirname(os.path.dirname(image_path))
        serial_directory = os.path.join(base_directory, 'process')
        serial = os.path.basename(image_path).split('.')[0]

        saved_paths = []
        for index, cropped_image in enumerate(cropped_images):
            if cropped_image.size > 0:
                serial_directory_path = os.path.join(serial_directory, serial)
                if not os.path.exists(serial_directory_path):
                    os.makedirs(serial_directory_path)
                path = os.path.join(serial_directory_path, f'{serial}_{index}.png')
                cv2.imwrite(path, cropped_image)
                saved_paths.append(path)
            else:
                print(f"빈 이미지를 건너뜁니다: index {index}")

        return saved_paths

    @staticmethod
    def merge_checksheet_images(image_paths, output_path, target_width=800):
        """
        모든 체크시트 이미지를 하나의 이미지로 세로로 합칩니다.
        
        :param image_paths: 합칠 이미지들의 경로 리스트
        :param output_path: 합쳐진 이미지를 저장할 경로
        :param target_width: 모든 이미지의 동일한 너비
        """
        images = []
        # 이미지 불러오기 및 크기 조정
        for path in image_paths:
            try:
                img = Image.open(path)
                # 비율을 유지하며 높비를 target_width로 조정
                aspect_ratio = target_width / img.width
                new_height = int(img.height * aspect_ratio)
                img = img.resize((target_width, new_height), Image.LANCZOS)
                images.append(img)
            except Exception as e:
                print(f"이미지를 불러오는 중 오류 발생: {path}, 오류: {e}")

        if not images:
            print("합칠 이미지가 없습니다.")
            return

        # 모든 이미지의 총 너이 계산
        total_height = sum(img.height for img in images)
        # 합쳐질 이미지의 크기 설정
        merged_image = Image.new('RGB', (target_width, total_height))

        # 이미지 순서대로 합치기
        current_y = 0
        for img in images:
            merged_image.paste(img, (0, current_y))
            current_y += img.height

        # 합쳐진 이미지 저장
        merged_image.save(output_path)
        print(f"체크시트가 성공적으로 합쳐졌습니다: {output_path}")
