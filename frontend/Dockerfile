# 使用基础镜像（包含所有依赖）
FROM quant-platform-frontend-base:latest

# 只复制应用代码（依赖已在 base 镜像中）
COPY . /app

EXPOSE 3000

CMD ["npm", "run", "dev"]
