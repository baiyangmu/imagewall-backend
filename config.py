# config.py
import os

class Config:
    MYSQL_HOST = 'localhost'  # MySQL 主机地址
    MYSQL_USER = 'root'       # MySQL 用户名
    MYSQL_PASSWORD = 'root'  # MySQL 密码
    MYSQL_DB = 'imagewall'    # 数据库名称
    MYSQL_CURSORCLASS = 'DictCursor'  # 返回字典类型的查询结果
    UPLOAD_FOLDER = './static/images'  # 图片保存的文件夹
    ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}  # 允许的图片格式
