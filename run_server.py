from Logger import Logger
from flask import request
import logging
from logging.handlers import RotatingFileHandler
from app import app
import time
import sys

logger = Logger()

@app.before_request
def log_request_info():
    logger.log_access(
        request.remote_addr,
        request.method,
        request.url
    )

@app.errorhandler(Exception)
def handle_error(error):
    logger.log_error(str(error), exc_info=True)
    return "서버 오류가 발생했습니다.", 500

def run_server_with_retry(max_retries=3, retry_delay=5):
    retry_count = 0
    while retry_count < max_retries:
        try:
            logger.logger.info('Starting server...')
            logger.logger.info('Server starting on http://0.0.0.0:80')
            app.run(
                host='0.0.0.0',
                port=80,
                debug=True,
                use_reloader=False  # 자동 재로드 비활성화
            )
            # 정상 종료시 루프 탈출
            break
        except SystemExit as e:
            retry_count += 1
            logger.logger.error(f'Server crashed with SystemExit: {e}. Attempt {retry_count} of {max_retries}')
            if retry_count < max_retries:
                logger.logger.info(f'Restarting server in {retry_delay} seconds...')
                time.sleep(retry_delay)
            else:
                logger.logger.critical('Maximum retry attempts reached. Server shutting down.')
                sys.exit(1)
        except KeyboardInterrupt:
            logger.logger.info('Server stopped by user.')
            break
        except Exception as e:
            retry_count += 1
            logger.logger.error(f'Unexpected error: {str(e)}. Attempt {retry_count} of {max_retries}')
            if retry_count < max_retries:
                logger.logger.info(f'Restarting server in {retry_delay} seconds...')
                time.sleep(retry_delay)
            else:
                logger.logger.critical('Maximum retry attempts reached. Server shutting down.')
                sys.exit(1)

if __name__ == '__main__':
    run_server_with_retry()
