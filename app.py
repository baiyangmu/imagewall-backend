from flask import Flask, request, jsonify, send_file, make_response
from flask_cors import CORS
from flask import Blueprint
from config import Config
import os
# ensure mydb wrapper will find the bundled shared library when running the
# app directly. mydb_wrapper allows overriding via LIBMYDB_PATH env var.
if "LIBMYDB_PATH" not in os.environ:
    guessed_lib = os.path.abspath(os.path.join(os.path.dirname(__file__), "bin", "libmydb.so"))
    os.environ["LIBMYDB_PATH"] = guessed_lib
from mydb_wrapper import MyDB
import io
import uuid
from pathlib import Path
import hashlib

app = Flask(__name__)
app.config.from_object(Config)

CORS(app)
api = Blueprint('api', __name__, url_prefix='/api')

def get_db_connection():
    # placeholder kept for compatibility; not used when using MyDB wrapper
    raise RuntimeError("MySQL connection is disabled; using internal mydb backend")

# 创建本地文件夹(若不存在)
upload_dir = Path(Config.UPLOAD_FOLDER)
upload_dir.mkdir(parents=True, exist_ok=True)

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in Config.ALLOWED_EXTENSIONS


def ensure_images_table(db):
    """
    Ensure the DB is using the `images` table. If the table does not exist,
    create it and switch to it.
    """
    try:
        rc, out = db.execute("use images")
    except Exception:
        # if execute raises, give up silently (higher level code will handle errors)
        return

    # if the engine reports table not found, create it then try again
    if rc != 0 or (isinstance(out, str) and "Table not found" in out):
        create_sql = (
            "create table images (id int, file_path string, mime_type string, created_at timestamp)"
        )
        try:
            db.execute(create_sql)
        except Exception:
            pass
        try:
            db.execute("use images")
        except Exception:
            pass

@api.route('/upload', methods=['POST','OPTIONS'])
def upload_images():
    if request.method == 'OPTIONS':
        return '', 200
    
    if 'files' not in request.files:
        return jsonify({"error": "No files part"}), 400

    files = request.files.getlist('files')
    if not files:
        return jsonify({"error": "No selected files"}), 400

    # use mydb wrapper
    DB_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), "test.db"))
    db = MyDB(DB_PATH)
    ensure_images_table(db)
    uploaded_ids = []
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
            
            # insert via mydb: note the engine expects space-separated values
            # caller must ensure file_path contains no spaces; otherwise encode it
            # we use a simple id generation: get max id + 1
            rc, j = db.execute_json("select id from images order by id desc limit 1 offset 0")
            if rc == 0 and j and j.get("rows"):
                try:
                    last = int(j["rows"][0].get("id", 0))
                except Exception:
                    last = 0
            else:
                last = 0
            new_id = last + 1
            created_at = int(__import__("time").time())
            insert_sql = f"insert into images {new_id} {save_path} {mime_type} {created_at}"
            rc, _ = db.execute(insert_sql)
            if rc == 0:
                uploaded_ids.append(new_id)
        return jsonify({"message": "Images uploaded successfully", "uploaded_ids": uploaded_ids}), 200
    except Exception as e:
        print(f"Error uploading images: {e}")
        return jsonify({"error": "Failed to upload images"}), 500
    finally:
        try:
            db.close()
        except Exception:
            pass


@api.route('/images', methods=['GET','OPTIONS'])
def get_images():
    if request.method == 'OPTIONS':
        return '', 200
    
    page = request.args.get('page', 1, type=int)
    per_page = 10
    offset = (page - 1) * per_page

    DB_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), "test.db"))
    db = MyDB(DB_PATH)
    ensure_images_table(db)
    try:
        sql = f"select id, created_at, file_path from images order by id desc limit {per_page} offset {offset}"
        rc, parsed = db.execute_json(sql)
        if rc != 0 or parsed is None:
            return jsonify({"images": []}), 200
        rows = parsed.get("rows", [])
        image_list = []
        for r in rows:
            image_list.append({
                "id": r.get("id"),
                "created_at": r.get("created_at"),
                "src": f"/api/image/{r.get('id')}"
            })
        return jsonify({"images": image_list}), 200
    finally:
        db.close()


@api.route('/image/<int:image_id>', methods=['GET','OPTIONS'])
def get_image(image_id):
    if request.method == 'OPTIONS':
        return '', 200
    DB_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), "test.db"))
    db = MyDB(DB_PATH)
    ensure_images_table(db)
    try:
        rc, parsed = db.execute_json(f"select file_path, mime_type from images where id = {image_id}")
        if rc != 0 or parsed is None:
            return jsonify({"error": "Image not found"}), 404
        rows = parsed.get("rows", [])
        if not rows:
            return jsonify({"error": "Image not found"}), 404
        file_path = rows[0].get("file_path")
        mime_type = rows[0].get("mime_type")
    finally:
        try:
            db.close()
        except Exception:
            pass

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
    
    DB_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), "bin", "test.db"))
    db = MyDB(DB_PATH)
    ensure_images_table(db)
    try:
        rc, parsed = db.execute_json(f"select file_path from images where id = {image_id}")
        if rc != 0 or parsed is None:
            return jsonify({"error": "Image not found"}), 404
        rows = parsed.get("rows", [])
        if not rows:
            return jsonify({"error": "Image not found"}), 404
        file_path = rows[0].get("file_path")
        # delete record
        db.execute(f"delete from images where id = {image_id}")
        # delete file
        if os.path.exists(file_path):
            try:
                os.remove(file_path)
            except OSError as e:
                print(f"Error deleting file {file_path}: {e}")
        return jsonify({"message": f'Image {image_id} deleted successfully'}), 200
    finally:
        db.close()


@api.route('/images/all_ids', methods=['GET','OPTIONS'])
def get_all_image_ids():
    if request.method == 'OPTIONS':
        return '', 200
    
    DB_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), "test.db"))
    db = MyDB(DB_PATH)
    ensure_images_table(db)
    try:
        rc, parsed = db.execute_json("select id from images order by id desc")
        if rc != 0 or parsed is None:
            return jsonify({"images": []}), 200
        return jsonify({"images": parsed.get("rows", [])}), 200
    finally:
        db.close()


app.register_blueprint(api)

if __name__ == '__main__':
    app.run(debug=True)