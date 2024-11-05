from datetime import datetime
import logging
from logging.handlers import RotatingFileHandler
import os

class Logger:
    def __init__(self, log_dir='logs'):
        self.log_dir = log_dir
        if not os.path.exists(log_dir):
            os.makedirs(log_dir)

        # 웹 서비스 로거 설정
        self.logger = logging.getLogger('web_service')
        self.logger.setLevel(logging.INFO)

        # 로그 포맷 수정 - remote_addr 제거
        formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )

        # 파일 핸들러 설정
        log_file = os.path.join(log_dir, f'web_service_{datetime.now().strftime("%Y%m%d")}.log')
        file_handler = RotatingFileHandler(
            log_file,
            maxBytes=10*1024*1024,  # 10MB
            backupCount=5
        )
        file_handler.setFormatter(formatter)
        self.logger.addHandler(file_handler)

        # 콘솔 핸들러 설정
        console_handler = logging.StreamHandler()
        console_handler.setFormatter(formatter)
        self.logger.addHandler(console_handler)

    def log_error(self, error_message, exc_info=False):
        self.logger.error(error_message, exc_info=exc_info)

    def log_info(self, message):
        self.logger.info(message)

    def log_warning(self, message):
        self.logger.warning(message)

    def log_debug(self, message):
        self.logger.debug(message)