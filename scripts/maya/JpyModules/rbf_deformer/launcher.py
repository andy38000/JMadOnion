# -*- coding: utf-8 -*-
"""
RBF Deformer Launcher
启动器脚本

兼容 Maya 2018+ (Python 2.7 / Python 3.x)

在Maya中运行此脚本即可启动RBF换装变形工具

用法:
    # 方法1: 直接导入并运行
    from rbf_deformer import create_ui
    create_ui()
    
    # 方法2: 运行启动器
    from rbf_deformer import launcher
    launcher.run()

Author: Enhanced Version
Version: 2.0.0
"""

from __future__ import print_function, division, absolute_import

import sys
import os


def setup_path():
    """设置Python路径"""
    # 获取当前文件所在目录
    current_dir = os.path.dirname(os.path.abspath(__file__))
    parent_dir = os.path.dirname(current_dir)
    
    # 添加到Python路径
    if parent_dir not in sys.path:
        sys.path.insert(0, parent_dir)


def check_dependencies():
    """检查依赖项"""
    missing = []
    
    try:
        import numpy
    except ImportError:
        missing.append('numpy')
    
    try:
        import scipy
    except ImportError:
        missing.append('scipy')
    
    if missing:
        print("[错误] 缺少以下依赖项: {0}".format(', '.join(missing)))
        print("请使用以下命令安装:")
        print("  pip install {0}".format(' '.join(missing)))
        return False
    
    return True


def run():
    """启动RBF变形工具"""
    # 设置路径
    setup_path()
    
    # 检查依赖
    if not check_dependencies():
        return None
    
    # 导入并启动
    try:
        from rbf_deformer.rbf_deformer_v2 import create_ui
        return create_ui()
    except ImportError as e:
        print("[错误] 导入失败: {0}".format(e))
        
        # 尝试相对导入
        try:
            from .rbf_deformer_v2 import create_ui
            return create_ui()
        except ImportError as e2:
            print("[错误] 相对导入也失败: {0}".format(e2))
            return None


def run_with_auto_params():
    """启动工具并自动检测参数"""
    window = run()
    
    if window:
        from maya import cmds
        
        # 如果有选中的对象，尝试自动加载
        selected = cmds.ls(sl=True, type='transform')
        
        if len(selected) >= 2:
            # 假设前两个是源和目标
            cmds.textFieldButtonGrp("sourceModelField", e=True, text=selected[0])
            cmds.textFieldButtonGrp("targetModelField", e=True, text=selected[1])
            
            # 剩余的作为批量模型
            if len(selected) > 2:
                cmds.textScrollList("batchModelList", e=True, removeAll=True)
                for mesh in selected[2:]:
                    cmds.textScrollList("batchModelList", e=True, append=mesh)
            
            # 自动检测参数
            try:
                from .utils import auto_detect_parameters
                params = auto_detect_parameters(selected[0], selected[1])
                
                if params:
                    cmds.floatSliderGrp("radiusSlider", e=True, value=params['radius'])
                    cmds.intSliderGrp("pointsSlider", e=True, value=params['max_points'])
                    print("[自动检测] 推荐半径: {0:.2f}, 采样点数: {1}".format(
                        params['radius'], params['max_points']))
            except Exception as e:
                print("[警告] 自动检测参数失败: {0}".format(e))
    
    return window


# 如果直接运行此文件
if __name__ == '__main__':
    run()
