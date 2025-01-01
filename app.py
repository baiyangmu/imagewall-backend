from flask import Flask, request, jsonify, send_file, make_response
from flask_cors import CORS
from flask import Blueprint
from config import Config
import pymysql
import io
import os
import uuid
from pathlib import Path
import hashlib

app = Flask(__name__)
app.config.from_object(Config)

CORS(app)
api = Blueprint('api', __name__, url_prefix='/api')

def get_db_connection():
    connection = pymysql.connect(
        host=Config.MYSQL_HOST,
        user=Config.MYSQL_USER,
        password=Config.MYSQL_PASSWORD,
        database=Config.MYSQL_DB,
        cursorclass=pymysql.cursors.DictCursor
    )
    return connection

# 创建本地文件夹(若不存在)
upload_dir = Path(Config.UPLOAD_FOLDER)
upload_dir.mkdir(parents=True, exist_ok=True)

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in Config.ALLOWED_EXTENSIONS

@api.route('/upload', methods=['POST','OPTIONS'])
def upload_images():
    if request.method == 'OPTIONS':
        return '', 200
    
    if 'files' not in request.files:
        return jsonify({"error": "No files part"}), 400

    files = request.files.getlist('files')
    if not files:
        return jsonify({"error": "No selected files"}), 400

    uploaded_ids = []
    connection = get_db_connection()
    cursor = connection.cursor()

    try:
        for file in files:
            if file.filename == '' or not allowed_file(file.filename):
                continue

            mime_type = file.mimetype
            ext = os.path.splitext(file.filename)[1].lower()  # 获取后缀名
            unique_name = f"{uuid.uuid4().hex}{ext}"  # 用uuid生成唯一文件名
            # 实际保存在本地系统的路径
            save_path = os.path.join(Config.UPLOAD_FOLDER, unique_name)
            file.save(save_path)
            
            insert_sql = """
                INSERT INTO images (file_path, mime_type)
                VALUES (%s, %s)
            """
            cursor.execute(insert_sql, (save_path, mime_type))
            uploaded_ids.append(cursor.lastrowid)

        connection.commit()
    except Exception as e:
        connection.rollback()
        print(f"Error uploading images: {e}")
        return jsonify({"error": "Failed to upload images"}), 500
    finally:
        cursor.close()
        connection.close()

    return jsonify({"message": "Images uploaded successfully", "uploaded_ids": uploaded_ids}), 200


@api.route('/images', methods=['GET','OPTIONS'])
def get_images():
    if request.method == 'OPTIONS':
        return '', 200
    
    page = request.args.get('page', 1, type=int)
    per_page = 10
    offset = (page - 1) * per_page

    connection = get_db_connection()
    cursor = connection.cursor()
    cursor.execute("""
        SELECT id, created_at, file_path
        FROM images
        ORDER BY id DESC
        LIMIT %s OFFSET %s
    """, (per_page, offset))
    records = cursor.fetchall()
    cursor.close()
    connection.close()

    image_list = []
    for row in records:
        image_list.append({
            "id": row['id'],
            "created_at": row['created_at'],
            # 这里依旧可以保留 "/api/image/<id>" 给前端使用
            # 或者直接提供 row['file_path'] 让前端访问静态文件
            "src": f"/api/image/{row['id']}"
        })
    
    return jsonify({"images": image_list}), 200


@api.route('/image/<int:image_id>', methods=['GET','OPTIONS'])
def get_image(image_id):
    if request.method == 'OPTIONS':
        return '', 200

    connection = get_db_connection()
    cursor = connection.cursor()
    cursor.execute("""
        SELECT file_path, mime_type
        FROM images
        WHERE id = %s
    """, (image_id,))
    row = cursor.fetchone()
    cursor.close()
    connection.close()

    if not row:
        return jsonify({"error": "Image not found"}), 404

    file_path = row['file_path']
    mime_type = row['mime_type']
    
    print(file_path)

    if not os.path.exists(file_path):
        return jsonify({"error": "File not found"}), 404

    # 计算文件的 ETag（基于文件内容的哈希值）
    with open(file_path, 'rb') as f:
        file_data = f.read()
        etag = hashlib.md5(file_data).hexdigest()

    # 获取请求的 If-None-Match 头
    request_etag = request.headers.get('If-None-Match')

    # 如果 ETag 匹配，返回 304 Not Modified
    if request_etag == etag:
        return '', 304

    # 返回图片数据
    response = make_response(send_file(
        io.BytesIO(file_data),
        mimetype=mime_type,
        as_attachment=False
    ))

    # 添加缓存头
    response.headers['Cache-Control'] = 'public, max-age=2592000'  # 缓存 30 天
    response.headers['ETag'] = etag

    return response


@api.route('/image/<int:image_id>', methods=['DELETE','OPTIONS'])
def delete_image(image_id):
    if request.method == 'OPTIONS':
        return '', 200
    
    connection = get_db_connection()
    cursor = connection.cursor()
    cursor.execute("""
        SELECT file_path
        FROM images
        WHERE id = %s
    """, (image_id,))
    row = cursor.fetchone()
    if not row:
        cursor.close()
        connection.close()
        return jsonify({"error": "Image not found"}), 404

    file_path = row['file_path']
    
    # 删除数据库记录
    cursor.execute("DELETE FROM images WHERE id = %s", (image_id,))
    connection.commit()
    cursor.close()
    connection.close()

    # 同时删除本地文件
    if os.path.exists(file_path):
        try:
            os.remove(file_path)
        except OSError as e:
            print(f"Error deleting file {file_path}: {e}")

    return jsonify({"message": f'Image {image_id} deleted successfully'}), 200


@api.route('/images/all_ids', methods=['GET','OPTIONS'])
def get_all_image_ids():
    if request.method == 'OPTIONS':
        return '', 200
    
    connection = get_db_connection()
    cursor = connection.cursor()
    cursor.execute("SELECT id FROM images ORDER BY id DESC")
    rows = cursor.fetchall()
    cursor.close()
    connection.close()

    return jsonify({"images": rows}), 200


app.register_blueprint(api)

if __name__ == '__main__':
    app.run(debug=True)