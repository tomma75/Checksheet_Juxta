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
    
    # SSL 컨텍스트 설정
    ssl_context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    ssl_context.load_cert_chain('server.crt', 'server.key')
    ssl_context.verify_mode = ssl.CERT_OPTIONAL
    ssl_context.check_hostname = False
    
    # SSL 어댑터 설정 (ssl_context 매개변수 제거)
    ssl_adapter = BuiltinSSLAdapter(
        'server.crt', 
        'server.key'
    )
    
    # SSL 컨텍스트 직접 설정
    ssl_adapter.context = ssl_context
    
    server = WSGIServer(('0.0.0.0', 8000), app)
    server.ssl_adapter = ssl_adapter
    
    try:
        logger.logger.info('Server starting on https://0.0.0.0:8000')
        server.start()
    except KeyboardInterrupt:
        server.stop()
        logger.logger.info('Server stopped.')
