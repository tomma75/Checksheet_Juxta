import logging
from logging.handlers import RotatingFileHandler
from waitress import serve
from app import app 

# 로깅 설정
logger = logging.getLogger('waitress')
logger.setLevel(logging.INFO)
handler = RotatingFileHandler('server.log', maxBytes=10240, backupCount=5)
handler.setFormatter(logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s'))
logger.addHandler(handler)

if __name__ == '__main__':
    logger.info('Starting server...')
    serve(app, host='0.0.0.0', port=8000, threads=4)
    logger.info('Server stopped.')