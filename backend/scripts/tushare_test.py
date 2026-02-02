#!/usr/bin/env python3
"""
最简单的 Tushare 接口测试脚本
调用申万实时行情接口: rt_sw_k
"""
import sys
from pathlib import Path

# 添加 backend 到路径
SCRIPT_ROOT = Path(__file__).resolve().parent
sys.path.append(str(SCRIPT_ROOT.parent))

import tushare as ts
from app.core.config import settings


def main():
    # 初始化 pro_api
    pro = ts.pro_api(settings.tushare_token)
    
    print("=" * 60)
    print("测试申万实时行情接口 (rt_sw_k)")
    print("=" * 60)
    
    # 方式1: 获取全部申万指数实时数据
    print("\n>>> 获取全部申万指数实时数据:")
    try:
        df = pro.rt_sw_k()
        print(f"返回数据条数: {len(df)}")
        print(df.head(10).to_string())
    except Exception as e:
        print(f"错误: {e}")
    
    # 方式2: 获取指定指数实时数据
    print("\n" + "=" * 60)
    print(">>> 获取指定指数(贵金属 801053.SI)实时数据:")
    try:
        df = pro.rt_sw_k(ts_code='801053.SI')
        print(f"返回数据条数: {len(df)}")
        print(df.to_string())
    except Exception as e:
        print(f"错误: {e}")
    
    print("\n" + "=" * 60)
    print("测试完成")


if __name__ == "__main__":
    main()
