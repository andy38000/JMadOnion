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
        print("[GoSkinning] Import failed: " + str(e))
        print("[GoSkinning] Make sure GoSkinning folder is in Python path")
        raise
    except Exception as e:
        print("[GoSkinning] Launch failed: " + str(e))
        raise


if __name__ == "__main__":
    main()
