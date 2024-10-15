import logging
from logging.handlers import RotatingFileHandler
from app import app
import ssl
from cheroot.wsgi import Server as WSGIServer
from cheroot.ssl.builtin import BuiltinSSLAdapter

# 로깅 설정
logger = logging.getLogger('server')
logger.setLevel(logging.INFO)
handler = RotatingFileHandler('server.log', maxBytes=10240, backupCount=5)
handler.setFormatter(logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s'))
logger.addHandler(handler)

if __name__ == '__main__':
    logger.info('Starting server...')
    
    # SSL 설정
    ssl_adapter = BuiltinSSLAdapter('server.crt', 'server.key')
    
    # HTTPS 서버 설정
    server = WSGIServer(('0.0.0.0', 8000), app)
    server.ssl_adapter = ssl_adapter
    
    try:
        logger.info('Server starting on https://0.0.0.0:8000')
        server.start()
    except KeyboardInterrupt:
        server.stop()
    
    logger.info('Server stopped.')