# 基础镜像使用说明

## 概述

为了加速 Docker 构建过程，项目使用了基础镜像（base images）策略：
- **后端基础镜像**：包含 Python 环境和所有 Python 依赖
- **前端基础镜像**：包含 Node.js 环境和所有 npm 依赖

当只更新应用代码时，可以跳过依赖安装步骤，大幅提升构建速度。

## 首次使用

1. **构建基础镜像**（只需执行一次，或当依赖文件更新时）：
```bash
./scripts/build-base-images.sh
```

2. **构建并启动应用**：
```bash
docker-compose up --build
```
如需停止并清理容器：
```bash
./scripts/compose-down.sh
```

## 日常开发流程

### 场景 1：只更新了应用代码（最常见）

直接使用 docker-compose，会自动使用已构建的 base 镜像：
```bash
docker-compose up --build
```

### 场景 2：更新了依赖文件

如果修改了 `backend/pyproject.toml` 或 `frontend/package.json`，需要重新构建 base 镜像：

```bash
# 1. 重新构建 base 镜像
./scripts/build-base-images.sh

# 2. 构建并启动应用
docker-compose up --build
```

## 镜像命名

- 后端基础镜像：`quant-platform-backend-base:latest`
- 前端基础镜像：`quant-platform-frontend-base:latest`

## 验证基础镜像

查看已构建的基础镜像：
```bash
docker images | grep quant-platform
```

## 清理

如果需要清理基础镜像（例如重新开始）：
```bash
docker rmi quant-platform-backend-base:latest
docker rmi quant-platform-frontend-base:latest
```
