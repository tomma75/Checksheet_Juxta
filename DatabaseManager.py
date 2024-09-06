import cx_Oracle
import os


class DatabaseManager:
    def __init__(self, user, password, host, port, service_name):
        self.user = user
        self.password = password
        self.host = host
        self.port = port
        self.service_name = service_name
        self.dsn = None
        self.connection = None

    def connect(self):
        location = r'.\\instantclient_21_7'
        os.environ["PATH"] = location + ";" + os.environ["PATH"]
        self.dsn = cx_Oracle.makedsn(self.host, self.port, service_name=self.service_name)
        self.connection = cx_Oracle.connect(user=self.user, password=self.password, dsn=self.dsn)
        return self.connection

    def close(self):
        if self.connection:
            self.connection.close()
