from datetime import datetime
import logging
from logging.handlers import RotatingFileHandler
import os

class Logger:
    def __init__(self):
        # 로그 디렉토리 생성
        if not os.path.exists('logs'):
            os.makedirs('logs')
            
        # 메인 로거 설정
        self.logger = logging.getLogger('web_service')
        self.logger.setLevel(logging.INFO)
        
        # 로그 포맷 수정
        formatter = logging.Formatter(
            '%(asctime)s - %(levelname)s - %(message)s'
        )
        
        # 파일 핸들러 설정
        file_handler = RotatingFileHandler(
            'logs/web_service.log', 
            maxBytes=10485760,  # 10MB
            backupCount=5
        )
        file_handler.setFormatter(formatter)
        
        # 스트림 핸들러 설정
        stream_handler = logging.StreamHandler()
        stream_handler.setFormatter(formatter)
        
        self.logger.addHandler(file_handler)
        self.logger.addHandler(stream_handler)

    def log_access(self, remote_addr=None, method=None, url=None, message=""):
        log_message = f"{message}"
        if remote_addr:
            log_message = f"[{remote_addr}] {log_message}"
        if method and url:
            log_message = f"{log_message} {method} {url}"
        
        self.logger.info(log_message)

    def log_error(self, error_message, exc_info=None):
        self.logger.error(error_message, exc_info=exc_info)