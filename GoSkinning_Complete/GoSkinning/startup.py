# -*- coding: utf-8 -*-
"""
GoSkinning 启动脚本
在3ds Max中运行此脚本以启动插件
"""

def main():
    """主入口函数"""
    try:
        from GoSkinning import launch
        launch()
    except ImportError as e:
        print(f"[GoSkinning] 导入失败: {e}")
        print("[GoSkinning] 请确保GoSkinning文件夹在Python路径中")
        raise
    except Exception as e:
        print(f"[GoSkinning] 启动失败: {e}")
        raise


if __name__ == "__main__":
    main()
