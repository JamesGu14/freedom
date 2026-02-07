#!/usr/bin/env python3
"""
最简单的 Tushare 接口测试脚本
调用申万实时行情接口: rt_sw_k
"""
import logging
import sys
from pathlib import Path

# 添加 backend 到路径
SCRIPT_ROOT = Path(__file__).resolve().parent
sys.path.append(str(SCRIPT_ROOT.parent))

import tushare as ts
from app.core.config import settings

logger = logging.getLogger(__name__)


def main():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s - %(message)s",
    )
    # 初始化 pro_api
    pro = ts.pro_api(settings.tushare_token)

    logger.info("=" * 60)
    logger.info("测试申万实时行情接口 (rt_sw_k)")
    logger.info("=" * 60)

    # 方式1: 获取全部申万指数实时数据
    logger.info(">>> 获取全部申万指数实时数据")
    try:
        df = pro.rt_sw_k()
        logger.info("返回数据条数: %s", len(df))
        logger.info("\n%s", df.head(10).to_string())
    except Exception as e:
        logger.exception("获取全部申万指数实时数据失败: %s", e)

    # 方式2: 获取指定指数实时数据
    logger.info("=" * 60)
    logger.info(">>> 获取指定指数(贵金属 801053.SI)实时数据")
    try:
        df = pro.rt_sw_k(ts_code="801053.SI")
        logger.info("返回数据条数: %s", len(df))
        logger.info("\n%s", df.to_string())
    except Exception as e:
        logger.exception("获取指定指数实时数据失败: %s", e)

    logger.info("=" * 60)
    logger.info("测试完成")


if __name__ == "__main__":
    main()
