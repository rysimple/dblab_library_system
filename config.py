class Config:
    # MySQL 配置
    MYSQL_HOST = 'localhost'
    MYSQL_PORT = 3306
    MYSQL_USER = 'root'
    MYSQL_PASSWORD = '040713'  # 我的数据库密码
    MYSQL_DATABASE = 'library_system'
    
    # Flask 配置
    SECRET_KEY = 'library_system_secret_key'
    DEBUG = True
    
    # Session 配置
    SESSION_PERMANENT = False
    SESSION_COOKIE_NAME = 'library_session'

class DevelopmentConfig(Config):
    DEBUG = True

class ProductionConfig(Config):
    DEBUG = False

config = {
    'development': DevelopmentConfig,
    'production': ProductionConfig,
    'default': DevelopmentConfig
}