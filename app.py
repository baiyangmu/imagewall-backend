from flask import Flask, request, jsonify, send_file
from flask_cors import CORS  # 导入 CORS
from flask import Blueprint
from config import Config
import pymysql
import io
import os
import uuid
from pathlib import Path

app = Flask(__name__)
app.config.from_object(Config)

# 启用 CORS，允许所有来源的请求
CORS(app)
# 创建一个 Blueprint
api = Blueprint('api', __name__, url_prefix='/api')

# ========= 1. 定义文件存储的文件夹 =========
UPLOAD_FOLDER = Path(__file__).parent / 'uploaded_files'
UPLOAD_FOLDER.mkdir(exist_ok=True)  # 如果文件夹不存在，自动创建

# 连接 MySQL 数据库
def get_db_connection():
    connection = pymysql.connect(
        host=Config.MYSQL_HOST,
        user=Config.MYSQL_USER,
        password=Config.MYSQL_PASSWORD,
        database=Config.MYSQL_DB,
        cursorclass=pymysql.cursors.DictCursor  # 使用字典游标
    )
    return connection


# ========= 2. 上传图片接口 (保持接口不变) =========
@api.route('/upload', methods=['POST','OPTIONS'])
def upload_images():
    if request.method == 'OPTIONS':
        return '', 200  # 处理 OPTIONS 请求并返回 200 状态

    if 'files' not in request.files:
        return jsonify({"error": "No files part"}), 400

    files = request.files.getlist('files')  # 获取所有上传的文件
    if not files:
        return jsonify({"error": "No selected files"}), 400

    uploaded_ids = []
    connection = get_db_connection()
    cursor = connection.cursor()

    try:
        for file in files:
            if file.filename == '':
                continue

            # 获取 MIME 类型（真实图像数据仅用于保存到本地文件系统）
            file_data = file.read()
            mime_type = file.mimetype

            # 2.1 保存到本地文件系统
            ext = os.path.splitext(file.filename)[1]  # 取原文件后缀
            unique_name = f"{uuid.uuid4().hex}{ext}"  # 类似 abcd1234... .jpg
            save_path = UPLOAD_FOLDER / unique_name

            with open(save_path, 'wb') as f:
                f.write(file_data)

            # 转成绝对路径或保持相对路径都行
            file_path_str = str(save_path.resolve())

            # 2.2 往数据库插入
            #    - mime_type: 依旧存
            #    - file_path: 存储实际文件路径
            insert_sql = """
                INSERT INTO images (mime_type, file_path)
                VALUES (%s, %s)
            """
            cursor.execute(insert_sql, (mime_type, file_path_str))
            uploaded_ids.append(cursor.lastrowid)

        connection.commit()
    except Exception as e:
        connection.rollback()
        print(f"Error uploading images: {e}")
        return jsonify({"error": "Failed to upload images"}), 500
    finally:
        cursor.close()
        connection.close()

    return jsonify({
        "message": "Images uploaded successfully",
        "uploaded_ids": uploaded_ids
    }), 200


# ========= 3. 获取图片列表 (接口保持不变) =========
@api.route('/images', methods=['GET','OPTIONS'])
def get_images():
    if request.method == 'OPTIONS':
        return '', 200  # 处理 OPTIONS 请求并返回 200 状态

    page = request.args.get('page', 1, type=int)  # 获取页码，默认为1
    per_page = 10  # 每页显示10张图片
    offset = (page - 1) * per_page

    connection = get_db_connection()
    cursor = connection.cursor()
    cursor.execute("""
        SELECT id, created_at
        FROM images
        ORDER BY created_at DESC
        LIMIT %s OFFSET %s
    """, (per_page, offset))
    images = cursor.fetchall()
    cursor.close()
    connection.close()

    # 前端依旧通过 /api/image/<id> 去获取具体图片
    image_list = [
        {
            "id": row['id'],
            "created_at": row['created_at'],
            "src": f"/api/image/{row['id']}"
        }
        for row in images
    ]
    return jsonify({"images": image_list}), 200


# ========= 4. 获取单张图片 (不改接口, 但从文件系统读数据) =========
@api.route('/image/<int:image_id>', methods=['GET','OPTIONS'])
def get_image(image_id):
    if request.method == 'OPTIONS':
        return '', 200  # 处理 OPTIONS 请求并返回 200 状态

    connection = get_db_connection()
    cursor = connection.cursor()
    # 先取出 file_path 和 mime_type
    cursor.execute("""
        SELECT file_path, mime_type
        FROM images
        WHERE id = %s
    """, (image_id,))
    row = cursor.fetchone()
    cursor.close()
    connection.close()

    if row is None:
        return jsonify({"error": "Image not found"}), 404

    file_path = row['file_path']
    mime_type = row['mime_type']

    # 若文件系统里已不存在该文件, 返回404
    if not file_path or not os.path.exists(file_path):
        return jsonify({"error": "File not found"}), 404

    # 通过 send_file 返回本地文件 (和原先从 DB 读 blob 一致的接口)
    return send_file(
        file_path,
        mimetype=mime_type,
        as_attachment=False,
        download_name=f"image_{image_id}"
    )


# ========= 5. 删除图片 (同时删本地文件) =========
@api.route('/image/<int:image_id>', methods=['DELETE','OPTIONS'])
def delete_image(image_id):
    if request.method == 'OPTIONS':
        return '', 200  # 处理 OPTIONS 请求并返回 200 状态

    connection = get_db_connection()
    cursor = connection.cursor()
    cursor.execute("""
        SELECT file_path
        FROM images
        WHERE id = %s
    """, (image_id,))
    row = cursor.fetchone()

    if row is None:
        cursor.close()
        connection.close()
        return jsonify({"error": "Image not found"}), 404

    file_path = row['file_path']

    # 先删除数据库记录
    cursor.execute("DELETE FROM images WHERE id = %s", (image_id,))
    connection.commit()
    cursor.close()
    connection.close()

    # 再尝试删除本地文件
    if file_path and os.path.exists(file_path):
        try:
            os.remove(file_path)
        except OSError:
            pass  # 文件不存在也没关系

    return jsonify({"message": f"Image {image_id} deleted successfully"}), 200


# 注册蓝图，启动应用
app.register_blueprint(api)

if __name__ == '__main__':
    app.run(debug=True)