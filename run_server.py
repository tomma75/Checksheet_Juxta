from Logger import Logger
from flask import request
import logging
from logging.handlers import RotatingFileHandler
from app import app
import ssl
from cheroot.wsgi import Server as WSGIServer
from cheroot.ssl.builtin import BuiltinSSLAdapter

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

if __name__ == '__main__':
    logger.logger.info('Starting server...')
    
    # SSL 설정
    ssl_adapter = BuiltinSSLAdapter('server.crt', 'server.key')
    
    # HTTPS 서버 설정
    server = WSGIServer(('0.0.0.0', 8000), app)
    server.ssl_adapter = ssl_adapter
    
    try:
        logger.logger.info('Server starting on https://0.0.0.0:8000')
        server.start()
    except KeyboardInterrupt:
        server.stop()
        logger.logger.info('Server stopped.')
