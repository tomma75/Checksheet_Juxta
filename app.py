from flask import Flask
from dotenv import load_dotenv
import os
import ssl

# .env 파일에서 환경 변수 로드하기
load_dotenv()

class FlaskApp:
    def __init__(self):
        self.app = Flask(__name__)
        self.app.secret_key = os.urandom(24)
        self.app.config['SESSION_TYPE'] = 'filesystem'
        self.setup_config()

    def setup_config(self):
        # 환경 변수에서 업로드 폴더 설정
        self.app.config['UPLOAD_FOLDER'] = os.getenv('UPLOAD_FOLDER', './CheckSheet')

    def get_app(self):
        return self.app

# dotenv가 로드된 후 데이터베이스 관리자, 이미지 프로세서 및 라우트 핸들러 가져오기
from DatabaseManager import DatabaseManager
from ImageProcessor import ImageProcessor
from RouteHandler import RouteHandler

def create_app():
    flask_app = FlaskApp().get_app()
    # 환경 변수의 데이터베이스 설정
    ora7_manager = DatabaseManager(
        user=os.getenv('ORA7_USER', 'default_user'),
        password=os.getenv('ORA7_PASSWORD', 'default_password'),
        host=os.getenv('ORA7_HOST', 'default_host'),
        port=os.getenv('ORA7_PORT', '1521'),
        service_name=os.getenv('ORA7_SERVICE_NAME', 'default_service_name')
    )
    neuron_manager = DatabaseManager(
        user=os.getenv('NEURON_USER', 'default_user'),
        password=os.getenv('NEURON_PASSWORD', 'default_password'),
        host=os.getenv('NEURON_HOST', 'default_host'),
        port=os.getenv('NEURON_PORT', '1521'),
        service_name=os.getenv('NEURON_SERVICE_NAME', 'default_service_name')
    )
    image_processor = ImageProcessor()
    route_handler = RouteHandler(flask_app, ora7_manager, neuron_manager, image_processor)
    return flask_app

app = create_app()

if __name__ == '__main__':
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.load_cert_chain('server.crt', 'server.key')
    app.run(host='0.0.0.0', port=5000, ssl_context=context, debug=True)