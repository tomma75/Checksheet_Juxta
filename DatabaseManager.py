import cx_Oracle
import logging
import os


class DatabaseManager:
    _client_initialized = False  # 클래스 변수로 초기화 상태 추적
    
    def __init__(self, user, password, host, port, service_name):
        self.user = user
        self.password = password
        self.host = host
        self.port = port
        self.service_name = service_name
        self.dsn = None
        
        # 클래스 전체에서 한 번만 초기화
        if not DatabaseManager._client_initialized:
            self._init_oracle_client()
            DatabaseManager._client_initialized = True
            
        self._create_dsn()

    def _init_oracle_client(self):
        try:
            # Oracle 클라이언트 초기화
            oracle_client_path = "/opt/instantclient_21_13"
            if not os.path.exists(oracle_client_path):
                raise Exception(f"Oracle client path not found: {oracle_client_path}")
                
            cx_Oracle.init_oracle_client(lib_dir=oracle_client_path)
            logging.info("Oracle client initialized successfully")
        except Exception as e:
            logging.error(f"Failed to initialize Oracle client: {str(e)}")
            raise

    def _create_dsn(self):
        try:
            # DSN 생성
            self.dsn = cx_Oracle.makedsn(
                self.host,
                self.port,
                service_name=self.service_name
            )
            logging.info(f"Created DSN: {self.dsn}")
        except Exception as e:
            logging.error(f"Failed to create DSN: {str(e)}")
            raise

    def connect(self):
        try:
            logging.info(f"Attempting to connect to database with DSN: {self.dsn}")
            connection = cx_Oracle.connect(
                user=self.user,
                password=self.password,
                dsn=self.dsn
            )
            logging.info("Database connection successful")
            return connection
        except cx_Oracle.Error as e:
            error_msg = f"Database connection error: {str(e)}"
            logging.error(error_msg)
            # 연결 정보 로깅 (실제 운영 환경에서는 비밀번호 제외)
            logging.debug(f"Connection details: host={self.host}, port={self.port}, "
                         f"service_name={self.service_name}, user={self.user}")
            raise

    def close(self):
        try:
            if hasattr(self, 'connection') and self.connection:
                self.connection.close()
                logging.info("Database connection closed")
        except Exception as e:
            logging.error(f"Error closing database connection: {str(e)}")
