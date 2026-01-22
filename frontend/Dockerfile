# 使用基础镜像（包含所有依赖）
FROM quant-platform-frontend-base:latest

# 只复制应用代码（依赖已在 base 镜像中）
COPY . /app

ARG NEXT_PUBLIC_API_BASE_URL=/freedom/api
ENV NEXT_PUBLIC_API_BASE_URL=${NEXT_PUBLIC_API_BASE_URL}

RUN npm run build

EXPOSE 3000

CMD ["npm", "run", "start"]
