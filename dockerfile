# 使用 Python 3.11 作为基础镜像
FROM python:3.11-slim

# 设置工作目录
WORKDIR /app

# 将 requirements.txt 文件复制到容器中
COPY requirements.txt .

# 安装依赖
RUN pip install --no-cache-dir -r requirements.txt

# 将应用程序代码复制到容器中
COPY . .

# 设置 Flask 的环境变量
ENV FLASK_APP=app.py
ENV FLASK_RUN_HOST=0.0.0.0

# 暴露端口 5000
EXPOSE 5000

# 启动 Flask 服务
CMD ["flask", "run"]
