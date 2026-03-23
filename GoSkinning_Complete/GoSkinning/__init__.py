# -*- coding: utf-8 -*-
"""
GoSkinning - 3ds Max 自动蒙皮插件
版本: 1.0.0
作者: andymen
描述: 基于算法的自动角色蒙皮工具,支持全局蒙皮、局部蒙皮、裙摆蒙皮和面部蒙皮

功能模块:
    - 全局蒙皮: 使用通用算法对整个模型进行自动蒙皮
    - 局部蒙皮: 针对选中顶点进行局部权重计算
    - 裙摆蒙皮: 专门针对裙子等布料的代理蒙皮方案
    - 面部蒙皮: 面部骨骼专用蒙皮算法
    - 后处理: 权重调整、穿模修复、权重优化等
"""

__version__ = "1.0.0"
__author__ = "andymen"
__title__ = "GoSkinning"

from .core import skinning_engine
from .ui import main_window

def launch():
    """启动GoSkinning主窗口"""
    try:
        main_window.show()
    except Exception as e:
        print(f"[GoSkinning] 启动失败: {e}")
        raise

def version():
    """返回版本信息"""
    return __version__
