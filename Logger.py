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
        
        # 접속 로그 설정
        access_handler = RotatingFileHandler(
            'logs/access.log',
            maxBytes=10485760,  # 10MB
            backupCount=10,
            encoding='utf-8'
        )
        access_handler.setFormatter(logging.Formatter(
            '%(asctime)s - %(remote_addr)s - %(method)s %(url)s - %(message)s'
        ))
        
        # 에러 로그 설정
        error_handler = RotatingFileHandler(
            'logs/error.log',
            maxBytes=10485760,  # 10MB
            backupCount=10,
            encoding='utf-8'
        )
        error_handler.setFormatter(logging.Formatter(
            '%(asctime)s - %(levelname)s - %(message)s\n%(exc_info)s'
        ))
        error_handler.setLevel(logging.ERROR)
        
        self.logger.addHandler(access_handler)
        self.logger.addHandler(error_handler)

    def log_access(self, remote_addr, method, url, message=""):
        extra = {
            'remote_addr': remote_addr,
            'method': method,
            'url': url
        }
        self.logger.info(message, extra=extra)

    def log_error(self, error_message, exc_info=None):
        self.logger.error(error_message, exc_info=exc_info)