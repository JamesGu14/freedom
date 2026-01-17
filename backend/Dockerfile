# 使用基础镜像（包含所有依赖）
FROM quant-platform-backend-base:latest

# 只复制应用代码与脚本（依赖已在 base 镜像中）
COPY app /app/app
COPY scripts /app/scripts

EXPOSE 9000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "9000"]
