# -*- coding: utf-8 -*-
"""
分析 Facial SDK 模块的字节码
"""
from __future__ import print_function
import sys
import os

# 用户提供的完整十六进制数据
HEX_DATA = """
6300 0000 0000 0000 0003 0000 0040 0000
0073 aa00 0000 6400 0064 0100 6c00 006d
0100 5a01 0001 6400 0064 0200 6c02 005a
0200 6400 0064 0200 6c03 005a 0300 6400
0064 0300 6c00 006d 0400 5a04 006d 0500
5a05 0001 6400 0064 0400 6c06 006d 0700
5a07 0001 6400 0064 0200 6c08 006a 0900
5a0a 0064 0000 6402 006c 0b00 5a0b 0064
0000 6402 006c 0c00 5a0c 0064 0000 6402
006c 0d00 5a0d 0064 0500 6600 0064 0600
8400 0083 0000 595a 0e00 6407 0084 0000
5a0f 0064 0800 8400 005a 1000 6402 0053
2809 0000 0069 ffff ffff 2801 0000 0074
0400 0000 636d 6473 4e28 0200 0000 7408
0000 004f 7065 6e4d 6179 6174 0c00 0000
4f70 656e 4d61 7961 416e 696d 2801 0000
0074 0b00 0000 4f72 6465 7265 6444 6963
7474 1000 0000 6661 6369 6361 6c53 646b
4d6f 6475 6c65 6300 0000 0000 0000 0002
0000 0042 0000 0073 ca01 0000 6500 005a
0100 6400 0084 0000 5a02 0064 0100 8400
005a 0300 6402 0084 0000 5a04 0064 0300
8400 005a 0500 6404 0084 0000 5a06 0064
0500 8400 005a 0700 6406 0084 0000 5a08
0064 0700 8400 005a 0900 6408 0084 0000
5a0a 0064 0900 8400 005a 0b00 640a 0084
0000 5a0c 0064 0b00 8400 005a 0d00 640c
0084 0000 5a0e 0064 0d00 8400 005a 0f00
640e 0084 0000 5a10 0064 0f00 8400 005a
1100 6410 0084 0000 5a12 0064 1100 8400
005a 1300 6432 0064 1200 8401 005a 1500
6413 0084 0000 5a16 0064 1400 8400 005a
1700 6415 0084 0000 5a18 0064 1600 8400
005a 1900 6417 0084 0000 5a1a 0064 1800
8400 005a 1b00 6419 0084 0000 5a1c 0064
1a00 8400 005a 1d00 641b 0084 0000 5a1e
0064 1c00 8400 005a 1f00 641d 0084 0000
5a20 0064 1e00 8400 005a 2100 641f 0084
0000 5a22 0064 2000 8400 005a 2300 6421
0084 0000 5a24 0064 2200 8400 005a 2500
6423 0084 0000 5a26 0064 2400 8400 005a
2700 6425 0084 0000 5a28 0064 2600 6427
0084 0100 5a29 0064 3200 6428 0084 0100
5a2a 0064 2900 8400 005a 2b00 642a 0084
0000 5a2c 0064 2b00 8400 005a 2d00 642c
0084 0000 5a2e 0064 2d00 8400 005a 2f00
642e 0084 0000 5a30 0064 2f00 8400 005a
3100 6430 0084 0000 5a32 0064 3100 8400
005a 3300 5253
"""

def hex_to_bytes(hex_string):
    """十六进制转字节"""
    hex_clean = ''.join(hex_string.split())
    if sys.version_info[0] >= 3:
        return bytes.fromhex(hex_clean)
    else:
        return hex_clean.decode('hex')

def extract_strings(data, min_len=4):
    """提取可读字符串"""
    strings = []
    current = []
    
    for b in data:
        if sys.version_info[0] >= 3:
            c = b
        else:
            c = ord(b)
        
        if 32 <= c < 127:
            current.append(chr(c))
        else:
            if len(current) >= min_len:
                strings.append(''.join(current))
            current = []
    
    if len(current) >= min_len:
        strings.append(''.join(current))
    
    return strings

def main():
    print("=" * 70)
    print("Facial SDK Module - Bytecode Analysis")
    print("=" * 70)
    
    # 转换数据
    data = hex_to_bytes(HEX_DATA)
    print("\n📦 数据大小: {} bytes".format(len(data)))
    
    # 提取字符串
    strings = extract_strings(data)
    unique_strings = sorted(set(strings))
    
    print("\n" + "=" * 70)
    print("📝 提取的标识符 ({} 个)".format(len(unique_strings)))
    print("=" * 70)
    
    # 分类
    modules = []
    functions = []
    ui_elements = []
    maya_names = []
    others = []
    
    for s in unique_strings:
        sl = s.lower()
        
        if s in ['cmds', 'OpenMaya', 'OpenMayaAnim', 'OrderedDict', 'mel', 'math', 'os', 'functools']:
            modules.append(s)
        elif any(x in sl for x in ['_frn', 'layout', 'button', 'text', 'checkbox', 'dialog']):
            ui_elements.append(s)
        elif any(x in sl for x in ['facecial', 'sdk', 'ctrl', 'grp', 'joint', 'rig', 'driver', 'driven']):
            maya_names.append(s)
        elif s[0].islower() and len(s) > 5:
            functions.append(s)
        else:
            others.append(s)
    
    print("\n🔌 导入的模块:")
    for s in modules:
        print("    import {}".format(s))
    
    print("\n🎭 Maya 面部绑定相关:")
    for s in sorted(maya_names):
        print("    {}".format(s))
    
    print("\n🔧 函数/方法:")
    for s in sorted(functions):
        print("    def {}()".format(s))
    
    print("\n🖥️ UI 元素:")
    for s in sorted(ui_elements)[:20]:
        print("    {}".format(s))
    
    print("\n📋 其他字符串:")
    for s in sorted(others)[:30]:
        if len(s) >= 4:
            print("    {}".format(s))
    
    # 保存 .pyc 文件用于进一步分析
    pyc_path = os.path.join(os.path.dirname(__file__) or '.', 'facial_sdk.pyc')
    
    # 添加 Python 3 的 magic number
    import struct
    import time
    
    magic = b'\x42\x0d\r\n'  # Python 3.7
    timestamp = struct.pack('I', int(time.time()))
    source_size = struct.pack('I', 0)
    
    with open(pyc_path, 'wb') as f:
        f.write(magic)
        f.write(timestamp)
        f.write(source_size)
        f.write(data)
    
    print("\n" + "=" * 70)
    print("💾 已保存 .pyc 文件: {}".format(pyc_path))
    print("=" * 70)
    
    # 尝试使用 uncompyle6 反编译
    print("\n🔄 尝试反编译...")
    
    try:
        import uncompyle6
        import io
        
        py_path = os.path.join(os.path.dirname(__file__) or '.', 'facial_sdk_decompiled.py')
        
        with open(py_path, 'w') as f:
            try:
                uncompyle6.decompile_file(pyc_path, f)
                print("✅ 反编译成功!")
                print("📄 输出文件: {}".format(py_path))
                
                # 显示前100行
                with open(py_path, 'r') as rf:
                    content = rf.read()
                    print("\n" + "=" * 70)
                    print("📖 反编译代码预览 (前2000字符):")
                    print("=" * 70)
                    print(content[:2000])
                    if len(content) > 2000:
                        print("\n... (更多内容请查看完整文件)")
                        
            except Exception as e:
                print("❌ 反编译失败: {}".format(e))
                print("\n这可能是由于:")
                print("  1. 字节码版本与当前 Python 版本不匹配")
                print("  2. 字节码数据不完整")
                print("  3. 使用了混淆或加密")
                
    except ImportError:
        print("⚠️  uncompyle6 未安装")
        print("    请运行: pip install uncompyle6")

if __name__ == '__main__':
    main()
