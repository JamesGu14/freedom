#!/bin/bash

# 构建基础镜像脚本
# 当依赖文件（pyproject.toml 或 package.json）更新时，需要重新构建 base 镜像

set -e

echo "🔨 开始构建基础镜像..."

# 构建后端基础镜像
echo "📦 构建后端基础镜像..."
docker build -f backend/Dockerfile.base -t quant-platform-backend-base:latest backend/

# 构建前端基础镜像
echo "📦 构建前端基础镜像..."
docker build -f frontend/Dockerfile.base -t quant-platform-frontend-base:latest frontend/

echo "✅ 基础镜像构建完成！"
echo ""
echo "现在可以使用以下命令构建应用镜像："
echo "  docker-compose build"
echo ""
echo "或者直接启动（会自动构建）："
echo "  docker-compose up"

