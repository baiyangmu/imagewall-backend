# config.py
import os

class Config:
    MYSQL_HOST = '172.26.94.166'  # MySQL 主机地址
    MYSQL_USER = 'imagewall'       # MySQL 用户名
    MYSQL_PASSWORD = 'ysfsbym22A123456a,./'  # MySQL 密码
    MYSQL_DB = 'imagewall'    # 数据库名称
    MYSQL_CURSORCLASS = 'DictCursor'  # 返回字典类型的查询结果
    
    # 本地调试使用相对路径 "./static/images"
    # 生产环境可改成 "/var/imagewall/images" 或其他绝对路径
    UPLOAD_FOLDER = '/var/imagewall/images'  
    

    # 允许的图片类型
    ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}  