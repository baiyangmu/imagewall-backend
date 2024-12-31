from flask import Flask, request, jsonify, send_file
from flask_cors import CORS  # 导入 CORS
from flask import Blueprint
from config import Config
import pymysql
import io

app = Flask(__name__)
app.config.from_object(Config)

# 启用 CORS，允许所有来源的请求
CORS(app)
# 创建一个 Blueprint
api = Blueprint('api', __name__, url_prefix='/api')

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

            # 获取文件的二进制数据和 MIME 类型
            file_data = file.read()
            mime_type = file.mimetype

            # 将图片数据存储到数据库
            cursor.execute("INSERT INTO images (image_data, mime_type) VALUES (%s, %s)", (file_data, mime_type))
            uploaded_ids.append(cursor.lastrowid)  # 收集已上传的图片 ID

        connection.commit()
    except Exception as e:
        connection.rollback()
        print(f"Error uploading images: {e}")
        return jsonify({"error": "Failed to upload images"}), 500
    finally:
        cursor.close()
        connection.close()

    return jsonify({"message": "Images uploaded successfully", "uploaded_ids": uploaded_ids}), 200



# 2. 获取图片列表
@api.route('/images', methods=['GET','OPTIONS'])
def get_images():
    if request.method == 'OPTIONS':
        return '', 200  # 处理 OPTIONS 请求并返回 200 状态
    page = request.args.get('page', 1, type=int)  # 获取页码，默认为1
    per_page = 10  # 每页显示10张图片
    offset = (page - 1) * per_page

    connection = get_db_connection()
    cursor = connection.cursor()
    cursor.execute("SELECT id, created_at FROM images ORDER BY created_at DESC LIMIT %s OFFSET %s", (per_page, offset))
    images = cursor.fetchall()
    cursor.close()
    connection.close()

    # 格式化数据
    image_list = [{"id": image['id'], "created_at": image['created_at'], "src": f"/api/image/{image['id']}"} for image in images]
    
    return jsonify({"images": image_list}), 200

# 3. 获取单张图片
@api.route('/image/<int:image_id>', methods=['GET','OPTIONS'])
def get_image(image_id):
    if request.method == 'OPTIONS':
        return '', 200  # 处理 OPTIONS 请求并返回 200 状态
    connection = get_db_connection()
    cursor = connection.cursor()
    cursor.execute("SELECT image_data, mime_type FROM images WHERE id = %s", (image_id,))
    image = cursor.fetchone()
    cursor.close()
    connection.close()

    if image is None:
        return jsonify({"error": "Image not found"}), 404  # 更好的错误响应

    image_data = image['image_data']
    mime_type = image['mime_type']

    # 返回图片的二进制数据
    return send_file(
        io.BytesIO(image_data),  # 将二进制数据传递给 BytesIO
        mimetype=mime_type,  # 根据实际图片类型动态调整
        as_attachment=False,  # 设置为 False 以在浏览器中直接显示图片
        download_name=f"image_{image_id}"  # 文件名，不加后缀浏览器可能自动识别
    )

# 4. 删除图片
@api.route('/image/<int:image_id>', methods=['DELETE','OPTIONS'])
def delete_image(image_id):
    if request.method == 'OPTIONS':
        return '', 200  # 处理 OPTIONS 请求并返回 200 状态
    connection = get_db_connection()
    cursor = connection.cursor()
    cursor.execute("SELECT id FROM images WHERE id = %s", (image_id,))
    image = cursor.fetchone()

    if image is None:
        cursor.close()
        connection.close()
        return jsonify({"error": "Image not found"}), 404

    cursor.execute("DELETE FROM images WHERE id = %s", (image_id,))
    connection.commit()
    cursor.close()
    connection.close()

    return jsonify({"message": f"Image {image_id} deleted successfully"}), 200

# 将 api 蓝图注册到应用
app.register_blueprint(api)

if __name__ == '__main__':
    app.run(debug=True)
