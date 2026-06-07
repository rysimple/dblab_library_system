import pymysql
from config import Config
from contextlib import contextmanager

class Database:
    def __init__(self):
        self.host = Config.MYSQL_HOST
        self.port = Config.MYSQL_PORT
        self.user = Config.MYSQL_USER
        self.password = Config.MYSQL_PASSWORD
        self.database = Config.MYSQL_DATABASE
    
    @contextmanager
    def get_connection(self):
        """获取数据库连接（自动关闭）"""
        conn = pymysql.connect(
            host=self.host,
            port=self.port,
            user=self.user,
            password=self.password,
            database=self.database,
            charset='utf8mb4',
            cursorclass=pymysql.cursors.DictCursor
        )
        try:
            yield conn
        finally:
            conn.close()
    
    def query(self, sql, params=None):
        """执行查询，返回所有结果"""
        with self.get_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(sql, params)
                return cursor.fetchall()
    
    def query_one(self, sql, params=None):
        """执行查询，返回一条结果"""
        with self.get_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(sql, params)
                return cursor.fetchone()
    
    def execute(self, sql, params=None):
        """执行更新（INSERT/UPDATE/DELETE）"""
        with self.get_connection() as conn:
            with conn.cursor() as cursor:
                affected = cursor.execute(sql, params)
                conn.commit()
                return affected
    
    def call_procedure(self, proc_name, args):
        """调用存储过程，返回输出参数"""
        with self.get_connection() as conn:
            with conn.cursor() as cursor:
                cursor.callproc(proc_name, args)
                conn.commit()
                # 获取输出参数（假设最多3个输出参数）
                cursor.execute(f'SELECT @_{proc_name}_1, @_{proc_name}_2, @_{proc_name}_3')
                result = cursor.fetchone()
                return result
# 创建全局实例
db = Database()