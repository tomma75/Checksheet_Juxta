import cv2
from PIL import Image, ImageDraw
import os
import numpy as np
from pdf2image import convert_from_path

class ImageProcessor:
    @staticmethod
    def find_checkboxes(image, process_code=None, model=None, dept=None):
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
                        if dept in ['3165', 'UTA']:
                            if process_code == '06' and dept in ['3165', 'UTA']:
                                # 제외 영역에 있는 체크박스는 건너뜀
                                if 800 <= x <= image.shape[1] and 200 <= y <= 380:
                                    continue
                            elif process_code == '11' and dept in ['3165', 'UTA']:
                                if 825 <= x <= image.shape[1] and 180 <= y <= 350:
                                    continue
                            elif process_code == '15' and dept in ['3165', 'UTA']:
                                if 850 <= x <= image.shape[1] and 180 <= y <= 310:
                                    continue
                        if dept in ['3186', 'JUXTA']:
                            if process_code == '10' and model == 'VJ77':
                                if 550 <= x <= image.shape[1] and 270 <= y <= 380:
                                    continue
                            elif process_code == '11' and model == 'VJ77':
                                if 0 <= x <= image.shape[1] and 0 <= y <= 500:
                                    continue
                            elif process_code == '11' and model == 'VJ77':
                                if 0 <= x <= image.shape[1] and 0 <= y <= 500:
                                    continue
                            elif process_code == '11' and model != 'VJ77':
                                if 0 <= x <= 50 and 0 <= y <= image.shape[0]:
                                    continue
                            elif process_code == '07' and model != 'VJ77':
                                if 0 <= x <= image.shape[1] and 400 <= y <= 510:
                                    continue
                            elif process_code == '10' and model != 'VJ77':
                                if 0 <= x <= 700 and 80 <= y <= 140:
                                    continue
                    
                        # 내부 영역의 균일성 검사
                        mask = np.zeros(gray.shape, np.uint8)
                        cv2.drawContours(mask, [cnt], 0, 255, -1)
                        mean, stddev = cv2.meanStdDev(gray, mask=mask)
                        
                        # 균일성이 높은 경우만 선택
                        if stddev[0][0] < 40:
                            boxes.append({'x': x, 'y': y, 'width': w, 'height': h})
                            #print(f"체크박스 발견: ({x}, {y}), 크기: {w}x{h}, 균일성: {stddev[0][0]:.2f}, {image.shape[1]},{image.shape[0]},{process_code},{model}")
        
        result_image = Image.fromarray(cv2.cvtColor(image, cv2.COLOR_BGR2RGB))
        draw = ImageDraw.Draw(result_image)
        for box in boxes:
            draw.rectangle([box['x'], box['y'], box['x'] + box['width'], box['y'] + box['height']], outline='red')
        return result_image, boxes

    @staticmethod
    def debug_clustering(image_path, threshold_ratio=0.35, proximity_distance=10):
        """밀집 구간 분석 디버깅"""
        img = cv2.imread(image_path)
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        _, binary = cv2.threshold(gray, 200, 255, cv2.THRESH_BINARY_INV)

        horizontal_projection = np.sum(binary, axis=1)
        row_threshold = img.shape[1] * 255 * threshold_ratio
        detected_lines = np.where(horizontal_projection > row_threshold)[0]

        print("="*60)
        print("🔍 밀집 구간 분석")
        print("="*60)
        print(f"탐지된 행들: {detected_lines}")
        print(f"근접 거리 기준: {proximity_distance}px")

        # 그룹화 과정 상세 추적
        groups = []
        current_group = [detected_lines[0]]

        for i in range(1, len(detected_lines)):
            distance = detected_lines[i] - detected_lines[i-1]
            if distance <= proximity_distance:
                current_group.append(detected_lines[i])
                print(f"  Row {detected_lines[i]} → 그룹에 추가 (거리: {distance}px)")
            else:
                groups.append(current_group)
                print(f"  그룹 완성: {current_group[0]}~{current_group[-1]} (크기: {len(current_group)})")
                current_group = [detected_lines[i]]
                print(f"  Row {detected_lines[i]} → 새 그룹 시작 (거리: {distance}px)")
        
        groups.append(current_group)
        print(f"  마지막 그룹: {current_group[0]}~{current_group[-1]} (크기: {len(current_group)})")

        print(f"\n📊 최종 그룹 분석:")
        for i, group in enumerate(groups):
            front_row = min(group)
            back_row = max(group)
            print(f"  그룹 {i+1}: Row {front_row}~{back_row} → 분할점: {front_row}")

        return groups


    @staticmethod
    def debug_horizontal_projection(image_path, threshold_ratio=0.4):
        """각 행의 픽셀 합계를 그래프로 확인 및 상세 분석"""
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt
        
        img = cv2.imread(image_path)
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        _, binary = cv2.threshold(gray, 200, 255, cv2.THRESH_BINARY_INV)
        
        horizontal_projection = np.sum(binary, axis=1)
        row_threshold = img.shape[1] * 255 * threshold_ratio
        
        # 그래프 생성
        plt.figure(figsize=(15, 10))
        plt.subplot(2, 1, 1)
        plt.plot(horizontal_projection, linewidth=1)
        plt.axhline(y=row_threshold, color='r', linestyle='--', label=f'Threshold: {row_threshold:.1f}')
        plt.title(f'Horizontal Projection Analysis (Threshold Ratio: {threshold_ratio})')
        plt.xlabel('Row Index')
        plt.ylabel('Pixel Sum')
        plt.legend()
        plt.grid(True, alpha=0.3)
        
        # 탐지된 분할선들 표시
        detected_lines = np.where(horizontal_projection > row_threshold)[0]
        if len(detected_lines) > 0:
            plt.scatter(detected_lines, horizontal_projection[detected_lines], 
                    color='red', s=20, alpha=0.7, label='Detected Lines')
        
        # 상위 피크들 분석
        top_n = 10
        top_indices = np.argsort(horizontal_projection)[-top_n:][::-1]
        
        plt.subplot(2, 1, 2)
        plt.bar(range(top_n), horizontal_projection[top_indices])
        plt.axhline(y=row_threshold, color='r', linestyle='--', label=f'Threshold: {row_threshold:.1f}')
        plt.title(f'Top {top_n} Peaks Analysis')
        plt.xlabel('Peak Rank')
        plt.ylabel('Pixel Sum')
        plt.xticks(range(top_n), [f'Row {idx}' for idx in top_indices], rotation=45)
        plt.legend()
        plt.grid(True, alpha=0.3)
        
        plt.tight_layout()
        
        # 파일 저장
        output_path = image_path.replace('.jpg', '_projection_analysis.png').replace('.pdf', '_projection_analysis.png')
        plt.savefig(output_path, dpi=150, bbox_inches='tight')
        plt.close()
        
        # 상세 분석 결과 출력
        print("="*60)
        print(f"📊 Horizontal Projection Analysis Results")
        print("="*60)
        print(f"이미지 크기: {img.shape[1]} x {img.shape[0]}")
        print(f"임계값 비율: {threshold_ratio}")
        print(f"계산된 임계값: {row_threshold:.1f}")
        print(f"최대 픽셀 합계: {np.max(horizontal_projection):,.0f}")
        print(f"평균 픽셀 합계: {np.mean(horizontal_projection):,.0f}")
        
        print(f"\n🎯 탐지된 분할선 정보:")
        print(f"총 탐지된 행 수: {len(detected_lines)}")
        
        if len(detected_lines) > 0:
            # 연속된 행들을 그룹화
            groups = []
            current_group = [detected_lines[0]]
            
            for i in range(1, len(detected_lines)):
                if detected_lines[i] - detected_lines[i-1] <= 5:  # 5픽셀 이내 연속
                    current_group.append(detected_lines[i])
                else:
                    groups.append(current_group)
                    current_group = [detected_lines[i]]
            groups.append(current_group)
            
            print(f"분할 그룹 수: {len(groups)}")
            for i, group in enumerate(groups):
                start_row = group[0]
                end_row = group[-1]
                group_height = len(group)
                avg_intensity = np.mean(horizontal_projection[group])
                print(f"  그룹 {i+1}: Row {start_row:4d}~{end_row:4d} (높이: {group_height:2d}px, 평균강도: {avg_intensity:,.0f})")
        
        print(f"\n📈 상위 10개 피크 분석:")
        for i, idx in enumerate(top_indices):
            above_threshold = "✅" if horizontal_projection[idx] > row_threshold else "❌"
            print(f"  {i+1:2d}. Row {idx:4d}: {horizontal_projection[idx]:8,.0f} {above_threshold}")
        
        # 분할 예상 결과
        if len(detected_lines) > 0:
            # 실제 분할 지점 계산
            split_points = [0]
            for group in groups:
                center = (group[0] + group[-1]) // 2
                split_points.append(center)
            split_points.append(img.shape[0])
            
            print(f"\n✂️  예상 분할 결과:")
            print(f"총 분할 영역 수: {len(split_points)-1}")
            for i in range(len(split_points)-1):
                height = split_points[i+1] - split_points[i]
                print(f"  영역 {i+1}: Row {split_points[i]:4d}~{split_points[i+1]:4d} (높이: {height:3d}px)")
        
        print(f"\n💾 그래프 저장 위치: {output_path}")
        print("="*60)
        
        return {
            'detected_lines': detected_lines,
            'groups': groups if len(detected_lines) > 0 else [],
            'threshold': row_threshold,
            'max_value': np.max(horizontal_projection),
            'top_peaks': [(idx, horizontal_projection[idx]) for idx in top_indices]
        }


    @staticmethod
    def debug_thickness_filtering(image_path, threshold_ratio=0.35, proximity_distance=10, min_group_thickness=5):
        """두께 필터링 과정을 상세히 분석"""
        img = cv2.imread(image_path)
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        _, binary = cv2.threshold(gray, 200, 255, cv2.THRESH_BINARY_INV)

        horizontal_projection = np.sum(binary, axis=1)
        row_threshold = img.shape[1] * 255 * threshold_ratio
        detected_lines = np.where(horizontal_projection > row_threshold)[0]

        # 그룹화
        groups = []
        current_group = [detected_lines[0]]

        for i in range(1, len(detected_lines)):
            if detected_lines[i] - detected_lines[i-1] <= proximity_distance:
                current_group.append(detected_lines[i])
            else:
                groups.append(current_group)
                current_group = [detected_lines[i]]
        groups.append(current_group)

        print("="*60)
        print("🔍 두께 필터링 분석")
        print("="*60)
        print(f"최소 두께 기준: {min_group_thickness}px")
        
        valid_groups = []
        rejected_groups = []
        
        for i, group in enumerate(groups):
            thickness = len(group)
            start_row = min(group)
            end_row = max(group)
            
            if thickness >= min_group_thickness:
                valid_groups.append((start_row, thickness))
                print(f"✅ 그룹 {i+1}: Row {start_row}~{end_row} (두께: {thickness}px) → 분할점: {start_row}")
            else:
                rejected_groups.append((start_row, thickness))
                print(f"❌ 그룹 {i+1}: Row {start_row}~{end_row} (두께: {thickness}px) → 제외됨 (너무 얇음)")
        
        print(f"\n📊 필터링 결과:")
        print(f"유효한 그룹: {len(valid_groups)}개")
        print(f"제외된 그룹: {len(rejected_groups)}개")
        
        if valid_groups:
            print(f"분할점들: {[row for row, _ in valid_groups]}")
        
        return valid_groups, rejected_groups

    @staticmethod
    def split_image_by_horizontal_lines(image_path, base_serial, start_index, 
                                        threshold_ratio=0.4, proximity_distance=10, 
                                        min_row_height=10, min_group_thickness=5, dept=None, model=None):
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
        
        if base_serial is None:
            base_serial = os.path.basename(image_path).split('.')[0]
        
        if start_index is None:
            start_index = 0

        # ImageProcessor.debug_thickness_filtering(image_path, threshold_ratio=0.35, proximity_distance=10, min_group_thickness=min_row_height)
        # ImageProcessor.debug_clustering(image_path)
        # ImageProcessor.debug_horizontal_projection(image_path)
        """
        임계값을 넘는 픽셀 합계가 밀집된 구간을 그룹화하고,
        그룹 두께가 min_group_thickness 이상인 경우에만 분할점으로 사용
        """
        img = cv2.imread(image_path)
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        _, binary = cv2.threshold(gray, 200, 255, cv2.THRESH_BINARY_INV)

        horizontal_projection = np.sum(binary, axis=1)
        row_threshold = img.shape[1] * 255 * threshold_ratio  # 수정: img.shape[1]

        detected_lines = np.where(horizontal_projection > row_threshold)[0]  # 수정: [0] 추가

        # 좌우 마진 찾기 (수직 투영 계산)
        vertical_projection = np.sum(binary, axis=0)
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

        print(f"좌우 마진: left_margin={left_margin}, right_margin={right_margin}")
        margin_width = right_margin - left_margin
        min_split_thickness = max(min_group_thickness, int(margin_width * 0.02))  # 마진 
        print(f"마진 폭: {margin_width}px, 최소 분할 두께: {min_split_thickness}px")
        if len(detected_lines) == 0 or (dept in ['3186', 'JUXTA'] and (start_index == 0 and model != 'VJ77')):
            
            # 전체 이미지를 좌우 마진으로만 크롭
            if left_margin < right_margin:
                cropped = img[0:img.shape[0], left_margin:right_margin + 1]  # 수정: img.shape[0]
                
                if cropped.size > 0:
                    output_filename = f"{base_serial}_{start_index}.png"
                    base_directory = os.path.dirname(os.path.dirname(image_path))
                    process_folder = os.path.join(base_directory, 'Process', base_serial)
                    os.makedirs(process_folder, exist_ok=True)
                    output_path = os.path.join(process_folder, output_filename)

                    cv2.imwrite(output_path, cropped)
                    print(f"저장됨: {output_filename} (전체 이미지, 좌우 마진 적용, 크기: {cropped.shape})")
                    return [output_path]
                else:
                    print("❌ 크롭된 이미지가 비어있습니다.")
                    return [image_path]
            else:
                print("❌ 유효하지 않은 좌우 마진입니다.")
                return [image_path]

        print(f"탐지된 원본 행들: {detected_lines}")

        # 밀집된 행들을 그룹화
        groups = []
        current_group = [detected_lines[0]]  # 수정: detected_lines[0]

        for i in range(1, len(detected_lines)):
            if detected_lines[i] - detected_lines[i-1] <= proximity_distance:
                current_group.append(detected_lines[i])
            else:
                groups.append(current_group)
                current_group = [detected_lines[i]]
        groups.append(current_group)

        print(f"그룹화 결과:")
        for i, group in enumerate(groups):
            thickness = len(group)
            print(f"  그룹 {i+1}: Row {group[0]}~{group[-1]} (두께: {thickness}px)")

        split_rows = []
        for group in groups:
            group_thickness = len(group)
            if group_thickness >= 20 and group_thickness <= 40:
                # 추가 검사: 해당 그룹 영역의 좌우 마진 계산
                group_start = min(group)
                group_end = max(group)
                
                # 그룹 영역의 수직 투영 계산
                group_region = binary[group_start:group_end+1, :]
                group_vertical_projection = np.sum(group_region, axis=0)
                
                # 그룹의 좌우 마진 찾기
                group_left_margin = 0
                group_right_margin = img.shape[1] - 1
                
                # 그룹의 왼쪽 마진
                for i, value in enumerate(group_vertical_projection):
                    if value > 0:
                        group_left_margin = i
                        break
                
                # 그룹의 오른쪽 마진
                for i in range(img.shape[1] - 1, -1, -1):
                    if group_vertical_projection[i] > 0:
                        group_right_margin = i
                        break
                
                # 그룹의 폭 계산
                group_margin_width = group_right_margin - group_left_margin
                
                # 전체 폭과 비교하여 최종 결정
                if group_margin_width >= margin_width * 0.8:  # 전체 폭의 80% 이상
                    front_row = min(group)
                    split_rows.append(front_row)
                    print(f"    ✅ 분할점 추가: {front_row} (두께: {group_thickness}px, 폭: {group_margin_width}px)")
                else:
                    print(f"    ❌ 폭 부족: Row {group[0]}~{group[-1]} (폭: {group_margin_width}px < {margin_width * 0.8}px)")
            else:
                print(f"    ❌ 너무 얇음: Row {group[0]}~{group[-1]} (두께: {group_thickness}px)")
        # 분할점 설정: 이미지 시작(0) + 필터링된 그룹의 앞부분 + 이미지 끝
        split_points = [0] + split_rows + [img.shape[0]]
        split_points = sorted(list(set(split_points)))

        print(f"최종 분할점들: {split_points}")
    
        # 이미지 분할 및 저장
        saved_files = []
        print(f"DEBUG: dept={dept}, model={model}, start_index={start_index}")
        for i in range(len(split_points) - 1):
            y_start = split_points[i]
            y_end = split_points[i + 1]

            if (dept in ['3186', 'JUXTA']) and (i ==1 or i == 2) and (model != 'VJ77'):
                # JUXTA 공정 내전압, 기능검사 제외
                print(f"Skipping segment {i} due to dept condition")
                continue
            elif (dept in ['3186', 'JUXTA']) and (i == 0 or i == 2) and (model == 'VJ77') and start_index == 0:
                # VJ77 모델의 첫 번째 세그먼트는 제외
                print(f"Skipping segment {i} due to model condition")
                continue

            if y_end - y_start > min_row_height and left_margin < right_margin:
                # 좌우 마진을 적용한 크롭
                cropped = img[y_start:y_end, left_margin:right_margin + 1]
                
                if cropped.size > 0:
                    if dept in ['3186', 'JUXTA'] and i>=3 and model != 'VJ77':
                        file_index = start_index + i - 2
                    elif dept in ['3186', 'JUXTA'] and i==1 and model == 'VJ77' and start_index == 0:
                        file_index = start_index + i - 1
                    elif dept == '3188':
                        # 3188 공정은 순차적으로 저장
                        file_index = start_index + i
                    else:
                        file_index = start_index + i
                    output_filename = f"{base_serial}_{file_index}.png"
                    base_directory = os.path.dirname(os.path.dirname(image_path))
                    process_folder = os.path.join(base_directory,'Process', base_serial)
                    os.makedirs(process_folder, exist_ok=True)
                    output_path = os.path.join(process_folder, output_filename)

                    cv2.imwrite(output_path, cropped)
                    saved_files.append(output_path)
                    
                    print(f"저장됨: {output_filename} (Row {y_start}~{y_end}, Col {left_margin}~{right_margin}, 크기: {cropped.shape})")
                else:
                    print(f"빈 이미지를 건너뜁니다: {output_filename}")
            else:
                print(f"유효하지 않은 영역을 건너뜁니다: Row {y_start}~{y_end}")
                
        return saved_files

    @staticmethod
    def merge_checksheet_images_uta(image_paths, output_path, target_width=800):
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

    @staticmethod
    def merge_checksheet_images_juxta(image_paths, output_path, target_width=800):
        """
        - 첫 번째(왼쪽) 이미지는 원본 크기 그대로 사용.
        - 오른쪽 이미지는 여러 장(공정 07,10,11 등)을 세로로 이어붙인 뒤,
        '왼쪽 이미지의 높이'에 맞춰 축소(혹은 확대)한 다음, 좌우로 합친다.
        - 결과적으로, "왼쪽 이미지는 원본 그대로, 오른쪽 이미지는 세로 길이만 왼쪽에 맞춤."
        """

        if not image_paths:
            print("합칠 이미지가 없습니다.")
            return

        # 1) 맨 앞 이미지 = '왼쪽' 기준 이미지
        left_path = image_paths[0]
        right_paths = image_paths[1:]  # 나머지(오른쪽에 붙일 이미지들)

        # (A) 왼쪽 이미지 로드
        try:
            img_left = cv2.imread(left_path, cv2.IMREAD_COLOR)  # shape: (h, w, 3), BGR
            if img_left is None:
                print(f"왼쪽 이미지 로드 실패: {left_path}")
                return
        except Exception as e:
            print(f"왼쪽 이미지 로드 오류: {left_path}, {e}")
            return

        # (B) 오른쪽 이미지 로드
        right_images = []
        for path in right_paths:
            try:
                img_r = cv2.imread(path, cv2.IMREAD_COLOR)
                if img_r is not None:
                    right_images.append(img_r)
                else:
                    print(f"오른쪽 이미지 로드 실패: {path}")
            except Exception as e:
                print(f"오른쪽 이미지 로드 오류: {path}, {e}")

        # 오른쪽에 합칠 이미지가 없다면, 왼쪽만 저장
        if not right_images:
            print("오른쪽에 합칠 이미지가 없어, 왼쪽 단일 이미지만 저장합니다.")
            cv2.imwrite(output_path, img_left)
            print(f"단일 이미지 저장 완료: {output_path}")
            return

        widths = [img.shape[1] for img in right_images]
        max_width = max(widths)

        resized_right_list = []
        for img in right_images:
            h, w, c = img.shape
            if w != max_width:
                scale_factor = max_width / float(w)
                new_h = int(h * scale_factor)
                # 축소/확대에 따른 보간 설정
                if new_h > h:  
                    img_rz = cv2.resize(img, (max_width, new_h), interpolation=cv2.INTER_CUBIC)
                else:
                    img_rz = cv2.resize(img, (max_width, new_h), interpolation=cv2.INTER_AREA)
                resized_right_list.append(img_rz)
            else:
                resized_right_list.append(img)

        # 세로 방향으로 쌓기
        big_right_raw = np.concatenate(resized_right_list, axis=0)

        # (D) 오른쪽 전체를 '왼쪽 이미지 높이'에 맞춰 리사이즈
        h_left, w_left, _ = img_left.shape
        h_right_raw, w_right_raw, _ = big_right_raw.shape

        if h_right_raw != h_left:
            scale_r = h_left / float(h_right_raw)
            new_w_right = int(w_right_raw * scale_r)
            # 축소 vs 확대에 따라 보간 다르게
            if h_left < h_right_raw:
                big_right_resized = cv2.resize(big_right_raw, (new_w_right, h_left), interpolation=cv2.INTER_AREA)
            else:
                big_right_resized = cv2.resize(big_right_raw, (new_w_right, h_left), interpolation=cv2.INTER_CUBIC)
        else:
            big_right_resized = big_right_raw

        # (E) 이제 좌우로 합치기
        merged = np.concatenate((img_left, big_right_resized), axis=1)

        # (F) 저장
        #   - JPG로 저장 시 품질 설정 가능
        #   - PNG로 저장 시 무손실
        ext = os.path.splitext(output_path)[1].lower()
        if ext in [".jpg", ".jpeg"]:
            cv2.imwrite(output_path, merged, [cv2.IMWRITE_JPEG_QUALITY, 95])
        else:
            cv2.imwrite(output_path, merged)

        print(f"[JUXTA] 체크시트 병합 완료: {output_path}")

    @staticmethod
    def merge_checksheet_images_newsc(left_images, right_image, output_path):
        """
        NEW SC/3188 전용 병합 함수
        - 왼쪽: 여러 이미지를 세로로 합침 (0.png, 06.png, 2.png)
        - 오른쪽: 단일 이미지 (09.png)
        - 최종: 좌우로 배치
        """
        if not left_images or not right_image:
            print("병합할 이미지가 부족합니다.")
            return
        
        try:
            # 왼쪽 이미지들 로드 및 세로 병합
            left_cv_images = []
            for path in left_images:
                img = cv2.imread(path, cv2.IMREAD_COLOR)
                if img is not None:
                    left_cv_images.append(img)
                else:
                    print(f"이미지 로드 실패: {path}")
            
            if not left_cv_images:
                print("왼쪽 이미지를 로드할 수 없습니다.")
                return
            
            # 왼쪽 이미지들 너비 통일
            widths = [img.shape[1] for img in left_cv_images]
            max_width = max(widths)
            
            resized_left_list = []
            for img in left_cv_images:
                h, w, c = img.shape
                if w != max_width:
                    scale_factor = max_width / float(w)
                    new_h = int(h * scale_factor)
                    if new_h > h:
                        img_rz = cv2.resize(img, (max_width, new_h), interpolation=cv2.INTER_CUBIC)
                    else:
                        img_rz = cv2.resize(img, (max_width, new_h), interpolation=cv2.INTER_AREA)
                    resized_left_list.append(img_rz)
                else:
                    resized_left_list.append(img)
            
            # 왼쪽 이미지들을 세로로 병합
            merged_left = np.concatenate(resized_left_list, axis=0)
            
            # 오른쪽 이미지 로드
            img_right = cv2.imread(right_image, cv2.IMREAD_COLOR)
            if img_right is None:
                print(f"오른쪽 이미지 로드 실패: {right_image}")
                return
            
            # 오른쪽 이미지를 왼쪽 병합 이미지의 높이에 맞춰 조정
            h_left, w_left, _ = merged_left.shape
            h_right, w_right, _ = img_right.shape
            
            if h_right != h_left:
                scale_r = h_left / float(h_right)
                new_w_right = int(w_right * scale_r)
                if h_left < h_right:
                    img_right_resized = cv2.resize(img_right, (new_w_right, h_left), interpolation=cv2.INTER_AREA)
                else:
                    img_right_resized = cv2.resize(img_right, (new_w_right, h_left), interpolation=cv2.INTER_CUBIC)
            else:
                img_right_resized = img_right
            
            # 좌우로 병합
            merged = np.concatenate((merged_left, img_right_resized), axis=1)
            
            # 저장
            ext = os.path.splitext(output_path)[1].lower()
            if ext in [".jpg", ".jpeg"]:
                cv2.imwrite(output_path, merged, [cv2.IMWRITE_JPEG_QUALITY, 95])
            else:
                cv2.imwrite(output_path, merged)
            
            print(f"[NEW SC] 체크시트 병합 완료: {output_path}")
            
        except Exception as e:
            print(f"[NEW SC] 병합 중 오류 발생: {e}")

    @staticmethod
    def convert_pdf_to_process_images(dept, process, serial, base_folder, model=None, base_folder_ori=None):
        """
        UTA:
        - 기존대로 한 PDF → 전부 split
        JUXTA:
        - PDF 2개 존재, set공정=04(serial_0.pdf), 나머지공정(serial_1.pdf)
        - serial_0.pdf 그대로 출력
        - serial_1.pdf → split_image_by_horizontal_lines
        NEW SC:
        - serial_0.pdf → split, 1번항목만 저장
        - serial_1.pdf → 원본 그대로 사용
        """
        if dept in ['3165', 'UTA']:
            # 먼저 PNG 파일이 이미 있는지 확인
            png_path = os.path.join(base_folder_ori, dept, 'Master', f"{serial}.png")
            pdf_path = os.path.join(base_folder_ori, dept, 'Master', f"{serial}.pdf")
            
            if os.path.exists(png_path):
                # PNG 파일이 이미 있으면 직접 사용
                images = [Image.open(png_path)]
            elif os.path.exists(pdf_path):
                # PDF 파일만 있으면 변환
                images = convert_from_path(pdf_path, dpi=150)
            else:
                raise FileNotFoundError(f"PNG 또는 PDF 파일이 존재하지 않습니다: {serial}")

            # 결과 저장 경로 리스트
            saved_paths = []

            # 1) UTA 처리
            
            # UTA는 n페이지 모두 split
            page_index = 0
            for pil_img in images:
                # 페이지 임시 저장
                page_jpg_path = os.path.join(base_folder, dept, 'Master', f"{serial}.png")
                pil_img.save(page_jpg_path, 'png')
                # split
                splitted = ImageProcessor.split_image_by_horizontal_lines(page_jpg_path, serial, page_index, dept=dept)
                saved_paths.extend(splitted)
                page_index += 1

            return saved_paths

        # 2) JUXTA 처리
        elif dept in ['3186', 'JUXTA']:
            saved_paths = []
        
            # 공정 04: serial_0.pdf 사용 (split하지 않음)
            pdf_path = os.path.join(base_folder_ori, dept, 'Master', f"{serial}_0.pdf")
            if not os.path.exists(pdf_path):
                raise FileNotFoundError(f"PDF가 존재하지 않습니다: {pdf_path}")
            # PDF → PIL 이미지 변환
            images = convert_from_path(pdf_path, dpi=180)
            
            # 첫 번째 페이지만 사용하고 split하지 않음
            if images:
                temp_jpg_path =  os.path.join(base_folder, dept, 'Master', f"{serial}_0.png")
                # 이미지 저장 (split하지 않고 그대로)
                images[0].save(temp_jpg_path, 'PNG')
                splitted = ImageProcessor.split_image_by_horizontal_lines(
                    temp_jpg_path,
                    base_serial=serial,
                    start_index=0,
                    dept=dept,
                    model=model)

            pdf_path = os.path.join(base_folder_ori, dept, 'Master', f"{serial}_1.pdf")
            if not os.path.exists(pdf_path):
                raise FileNotFoundError(f"PDF가 존재하지 않습니다: {pdf_path}")
            # PDF → PIL 이미지 변환
            images = convert_from_path(pdf_path, dpi=180)
            # 이미지를 jpg로 임시 저장한 후 split 적용
            if images:
                temp_jpg_path = os.path.join(base_folder, dept, 'Master', f"{serial}_1.png")
                images[0].save(temp_jpg_path, 'PNG')
                # split 적용 (인덱스 1부터 시작)
                splitted = ImageProcessor.split_image_by_horizontal_lines(
                    temp_jpg_path,
                    base_serial=serial,
                    start_index=1,
                    dept=dept,
                    model=model
                )
                saved_paths.extend(splitted)

            return saved_paths
        # 2) NEWSC 처리
        elif dept in ['3188', 'NEW SC']:
            saved_paths = []
        
            # 첫 번째 PDF 처리 - 분할
            pdf_path = os.path.join(base_folder_ori, dept, 'Master', f"{serial}_0.pdf")
            if not os.path.exists(pdf_path):
                raise FileNotFoundError(f"PDF가 존재하지 않습니다: {pdf_path}")
            # PDF → PIL 이미지 변환
            images = convert_from_path(pdf_path, dpi=180)
            if images:
                temp_jpg_path =  os.path.join(base_folder, dept, 'Master', f"{serial}_0.png")
                # 이미지 저장
                images[0].save(temp_jpg_path, 'PNG')
                # 첫 번째 PDF는 분할하여 0, 1, 2.png 등으로 저장
                splitted = ImageProcessor.split_image_by_horizontal_lines(
                    temp_jpg_path,
                    base_serial=serial,
                    start_index=0,
                    dept=dept,
                    model=model)
                saved_paths.extend(splitted)

            # 두 번째 PDF 처리 - 분할하지 않고 그대로 사용
            pdf_path = os.path.join(base_folder_ori, dept, 'Master', f"{serial}_1.pdf")
            if not os.path.exists(pdf_path):
                raise FileNotFoundError(f"PDF가 존재하지 않습니다: {pdf_path}")
            # PDF → PIL 이미지 변환
            images = convert_from_path(pdf_path, dpi=180)
            if images:
                temp_jpg_path = os.path.join(base_folder, dept, 'Master', f"{serial}_1.png")
                images[0].save(temp_jpg_path, 'PNG')
                # 첫 번째 PDF의 분할 개수를 파악하여 다음 번호로 저장
                next_index = len(saved_paths)  # 첫 번째 PDF에서 생성된 파일 개수
                # 두 번째 PDF는 분할하지 않고 그대로 사용 (start_index를 다음 번호로 설정)
                splitted = ImageProcessor.split_image_by_horizontal_lines(
                    temp_jpg_path,
                    base_serial=serial,
                    start_index=next_index,  # 첫 번째 PDF 분할 개수만큼 시작 인덱스 설정
                    dept=dept,
                    model=model
                )
                saved_paths.extend(splitted)

            return saved_paths

        else:
            raise ValueError(f"지원하지 않는 부서코드: {dept}")

        
