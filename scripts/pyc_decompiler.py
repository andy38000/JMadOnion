# -*- coding: utf-8 -*-
"""
Python Bytecode Decompiler Tool
支持从十六进制字符串反编译 Python 字节码

使用方法:
1. 将十六进制字符串粘贴到 HEX_DATA 变量
2. 运行脚本
3. 查看输出的 .py 文件

依赖:
    pip install uncompyle6   # Python 2.7 - 3.8
    # 或
    pip install decompyle3   # Python 3.7 - 3.9+
    # 或
    pip install pycdc        # 通用但需要编译
"""

from __future__ import print_function
import sys
import os
import struct
import time
import marshal
import dis
import types

# ============================================================================
# 配置区 - 将十六进制数据粘贴到这里
# ============================================================================

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
"""

# ============================================================================
# 工具函数
# ============================================================================

def hex_to_bytes(hex_string):
    """将十六进制字符串转换为字节"""
    # 移除所有空白字符
    hex_clean = ''.join(hex_string.split())
    
    # 转换为字节
    if sys.version_info[0] >= 3:
        return bytes.fromhex(hex_clean)
    else:
        return hex_clean.decode('hex')


def detect_python_version(data):
    """
    尝试检测字节码的 Python 版本
    通过分析 magic number
    """
    # Python magic numbers (部分)
    MAGIC_NUMBERS = {
        # Python 2.x
        b'\x03\xf3\r\n': '2.7',
        b'\xee\x0c\r\n': '2.7',
        
        # Python 3.x
        b'\x16\r\r\n': '3.2',
        b'\x9e\x0c\r\n': '3.3',
        b'\xee\x0c\r\n': '3.4',
        b'\x17\r\r\n': '3.5',
        b'\x33\r\r\n': '3.6',
        b'\x3e\r\r\n': '3.6',
        b'\x3f\r\r\n': '3.7',
        b'\x42\r\r\n': '3.7',
        b'\x55\r\r\n': '3.8',
        b'\x61\r\r\n': '3.9',
        b'\x6f\r\r\n': '3.10',
        b'\xa7\r\r\n': '3.11',
    }
    
    if len(data) >= 4:
        magic = data[:4]
        for m, version in MAGIC_NUMBERS.items():
            if magic[:2] == m[:2]:
                return version
    
    return "Unknown"


def create_pyc_file(bytecode_data, output_path, python_version=None):
    """
    创建 .pyc 文件
    
    Args:
        bytecode_data: 字节码数据（不含 magic number 头）
        output_path: 输出文件路径
        python_version: Python 版本字符串，如 '2.7', '3.6'
    """
    # 确定 magic number
    if python_version is None:
        # 使用当前 Python 版本
        if sys.version_info[0] >= 3:
            import importlib.util
            magic = importlib.util.MAGIC_NUMBER
        else:
            import imp
            magic = imp.get_magic()
    else:
        # 根据版本选择 magic number
        magic_map = {
            '2.7': b'\x03\xf3\r\n',
            '3.5': b'\x16\r\r\n',
            '3.6': b'\x33\r\r\n',
            '3.7': b'\x42\r\r\n',
            '3.8': b'\x55\r\r\n',
            '3.9': b'\x61\r\r\n',
            '3.10': b'\x6f\r\r\n',
        }
        magic = magic_map.get(python_version, magic_map['3.6'])
    
    with open(output_path, 'wb') as f:
        # 写入 magic number
        f.write(magic)
        
        # 写入时间戳 (Python 3.7+ 有额外字段)
        timestamp = int(time.time())
        f.write(struct.pack('I', timestamp))
        
        if sys.version_info >= (3, 7):
            # Python 3.7+ 有 source size 字段
            f.write(struct.pack('I', 0))
        
        # 写入字节码
        f.write(bytecode_data)
    
    print("Created: {}".format(output_path))


def extract_strings_from_bytecode(data):
    """
    从字节码中提取可读字符串
    """
    strings = []
    
    # 查找连续的可打印 ASCII 字符
    current_string = []
    min_length = 4  # 最小字符串长度
    
    for byte in data:
        if sys.version_info[0] >= 3:
            char = byte
        else:
            char = ord(byte)
        
        # 可打印 ASCII 范围
        if 32 <= char < 127:
            current_string.append(chr(char))
        else:
            if len(current_string) >= min_length:
                s = ''.join(current_string)
                # 过滤掉无意义的字符串
                if not all(c in '0123456789abcdef' for c in s.lower()):
                    strings.append(s)
            current_string = []
    
    # 处理最后一个字符串
    if len(current_string) >= min_length:
        strings.append(''.join(current_string))
    
    return strings


def disassemble_code_object(code_bytes):
    """
    尝试反汇编代码对象
    """
    try:
        # 尝试加载为 marshal 数据
        code = marshal.loads(code_bytes)
        
        print("\n" + "=" * 60)
        print("DISASSEMBLY")
        print("=" * 60)
        
        if hasattr(code, 'co_code'):
            print("\nCode object found!")
            print("  co_name: {}".format(code.co_name if hasattr(code, 'co_name') else 'N/A'))
            print("  co_filename: {}".format(code.co_filename if hasattr(code, 'co_filename') else 'N/A'))
            
            if hasattr(code, 'co_names'):
                print("\n  Names (co_names):")
                for i, name in enumerate(code.co_names):
                    print("    {}: {}".format(i, name))
            
            if hasattr(code, 'co_consts'):
                print("\n  Constants (co_consts):")
                for i, const in enumerate(code.co_consts):
                    if isinstance(const, str):
                        print("    {}: '{}'".format(i, const[:80]))
                    elif const is not None and not isinstance(const, types.CodeType):
                        print("    {}: {}".format(i, const))
            
            print("\n  Disassembly:")
            try:
                dis.dis(code)
            except Exception as e:
                print("  Error during disassembly: {}".format(e))
        
        return code
        
    except Exception as e:
        print("Could not load as marshal data: {}".format(e))
        return None


def try_decompile_with_uncompyle6(pyc_path, output_path):
    """使用 uncompyle6 反编译"""
    try:
        import uncompyle6
        
        with open(output_path, 'w') as f:
            uncompyle6.decompile_file(pyc_path, f)
        
        print("\n✅ Successfully decompiled with uncompyle6!")
        print("Output: {}".format(output_path))
        return True
        
    except ImportError:
        print("\n⚠️  uncompyle6 not installed. Install with: pip install uncompyle6")
        return False
    except Exception as e:
        print("\n❌ uncompyle6 failed: {}".format(e))
        return False


def try_decompile_with_decompyle3(pyc_path, output_path):
    """使用 decompyle3 反编译"""
    try:
        import decompyle3
        
        with open(output_path, 'w') as f:
            decompyle3.decompile_file(pyc_path, f)
        
        print("\n✅ Successfully decompiled with decompyle3!")
        print("Output: {}".format(output_path))
        return True
        
    except ImportError:
        print("\n⚠️  decompyle3 not installed. Install with: pip install decompyle3")
        return False
    except Exception as e:
        print("\n❌ decompyle3 failed: {}".format(e))
        return False


def try_decompile_with_unpyc(pyc_path, output_path):
    """使用 unpyc3 反编译"""
    try:
        import unpyc3
        
        with open(pyc_path, 'rb') as f:
            code = unpyc3.decompile(f)
        
        with open(output_path, 'w') as f:
            f.write(str(code))
        
        print("\n✅ Successfully decompiled with unpyc3!")
        print("Output: {}".format(output_path))
        return True
        
    except ImportError:
        print("\n⚠️  unpyc3 not installed.")
        return False
    except Exception as e:
        print("\n❌ unpyc3 failed: {}".format(e))
        return False


def analyze_bytecode(hex_data):
    """
    分析字节码的主函数
    """
    print("=" * 60)
    print("Python Bytecode Analyzer / Decompiler")
    print("=" * 60)
    
    # 转换十六进制
    try:
        data = hex_to_bytes(hex_data)
        print("\n✅ Converted {} bytes of hex data".format(len(data)))
    except Exception as e:
        print("\n❌ Error converting hex data: {}".format(e))
        return
    
    # 检测 Python 版本
    detected_version = detect_python_version(data)
    print("Detected Python version: {}".format(detected_version))
    print("Current Python version: {}.{}".format(sys.version_info[0], sys.version_info[1]))
    
    # 提取字符串
    print("\n" + "=" * 60)
    print("EXTRACTED STRINGS")
    print("=" * 60)
    
    strings = extract_strings_from_bytecode(data)
    
    # 分类显示
    imports = []
    functions = []
    classes = []
    others = []
    
    for s in strings:
        if s.startswith('import') or 'Import' in s:
            imports.append(s)
        elif s.startswith('def ') or s.endswith('()') or '_' in s:
            functions.append(s)
        elif s[0].isupper() and not ' ' in s:
            classes.append(s)
        else:
            others.append(s)
    
    if imports:
        print("\n📦 Imports/Modules:")
        for s in set(imports):
            print("    {}".format(s))
    
    if classes:
        print("\n📦 Possible Classes/Modules:")
        for s in sorted(set(classes))[:30]:
            print("    {}".format(s))
    
    if functions:
        print("\n🔧 Possible Functions:")
        for s in sorted(set(functions))[:50]:
            print("    {}".format(s))
    
    if others:
        print("\n📝 Other Strings:")
        for s in sorted(set(others))[:30]:
            if len(s) > 3:
                print("    {}".format(s[:60]))
    
    # 保存 .pyc 文件
    output_dir = os.path.dirname(os.path.abspath(__file__))
    pyc_path = os.path.join(output_dir, "decompiled_module.pyc")
    py_path = os.path.join(output_dir, "decompiled_module.py")
    
    # 尝试创建 .pyc 文件
    print("\n" + "=" * 60)
    print("CREATING PYC FILE")
    print("=" * 60)
    
    # 检查数据是否已包含 magic number
    if len(data) > 4:
        # 原始数据可能就是完整的 .pyc 内容
        # 直接保存
        with open(pyc_path, 'wb') as f:
            f.write(data)
        print("Saved raw data to: {}".format(pyc_path))
    
    # 尝试反汇编
    print("\n" + "=" * 60)
    print("ATTEMPTING DISASSEMBLY")
    print("=" * 60)
    
    # 尝试不同偏移位置的 marshal 数据
    offsets_to_try = [0, 4, 8, 12, 16]  # 跳过可能的头部
    
    for offset in offsets_to_try:
        if offset < len(data):
            try:
                code = marshal.loads(data[offset:])
                print("\n✅ Successfully loaded marshal data at offset {}".format(offset))
                disassemble_code_object(data[offset:])
                break
            except Exception:
                continue
    
    # 尝试反编译
    print("\n" + "=" * 60)
    print("ATTEMPTING DECOMPILATION")
    print("=" * 60)
    
    success = False
    
    # 方法 1: uncompyle6
    if not success:
        success = try_decompile_with_uncompyle6(pyc_path, py_path)
    
    # 方法 2: decompyle3
    if not success:
        success = try_decompile_with_decompyle3(pyc_path, py_path)
    
    # 方法 3: unpyc3
    if not success:
        success = try_decompile_with_unpyc(pyc_path, py_path)
    
    if not success:
        print("\n" + "=" * 60)
        print("MANUAL INSTALLATION REQUIRED")
        print("=" * 60)
        print("""
To decompile Python bytecode, install one of these tools:

For Python 2.7 - 3.8:
    pip install uncompyle6

For Python 3.7+:
    pip install decompyle3

Then run this script again, or manually:
    uncompyle6 decompiled_module.pyc > output.py
    # or
    decompyle3 decompiled_module.pyc > output.py
""")
    
    # 显示文件位置
    print("\n" + "=" * 60)
    print("OUTPUT FILES")
    print("=" * 60)
    print("PYC file: {}".format(pyc_path))
    if os.path.exists(py_path):
        print("PY file:  {}".format(py_path))
        print("\nDecompiled source preview:")
        print("-" * 40)
        with open(py_path, 'r') as f:
            content = f.read()
            print(content[:2000])
            if len(content) > 2000:
                print("\n... (truncated, see full file)")


# ============================================================================
# 直接从十六进制字符串提取信息的简化函数
# ============================================================================

def quick_analyze(hex_data):
    """快速分析，只提取字符串，不需要额外依赖"""
    print("=" * 60)
    print("Quick Bytecode String Extractor")
    print("=" * 60)
    
    data = hex_to_bytes(hex_data)
    strings = extract_strings_from_bytecode(data)
    
    print("\nExtracted {} strings:\n".format(len(strings)))
    
    for s in sorted(set(strings)):
        if len(s) >= 4:
            print("  {}".format(s))
    
    return strings


# ============================================================================
# Main
# ============================================================================

if __name__ == '__main__':
    # 如果直接运行，分析 HEX_DATA
    if len(sys.argv) > 1:
        # 从文件读取
        with open(sys.argv[1], 'r') as f:
            hex_data = f.read()
        analyze_bytecode(hex_data)
    else:
        # 使用内置数据
        if HEX_DATA.strip():
            analyze_bytecode(HEX_DATA)
        else:
            print("Please paste hex data into the HEX_DATA variable and run again.")
            print("Or provide a file path as argument: python pyc_decompiler.py hexfile.txt")
