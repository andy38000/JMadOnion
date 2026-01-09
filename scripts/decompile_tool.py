# -*- coding: utf-8 -*-
"""
=======================================================================
Python 字节码反编译工具
=======================================================================

使用方法:

方法1 - 命令行:
    python3 decompile_tool.py input.pyc
    python3 decompile_tool.py hexdata.txt

方法2 - 在代码中粘贴数据:
    1. 将十六进制数据粘贴到下面的 HEX_DATA 变量
    2. 运行: python3 decompile_tool.py

方法3 - 交互式输入:
    python3 decompile_tool.py --interactive

依赖:
    pip install uncompyle6   # Python 2.7 - 3.8
"""

from __future__ import print_function
import sys
import os
import struct
import time

# ============================================================================
# 在这里粘贴完整的十六进制数据
# ============================================================================
HEX_DATA = """

"""
# ============================================================================


def hex_to_bytes(hex_string):
    """十六进制字符串转字节"""
    # 移除所有空白和常见分隔符
    hex_clean = hex_string.replace('\n', '').replace('\r', '').replace(' ', '')
    hex_clean = hex_clean.replace('\t', '').replace('-', '').replace(':', '')
    
    # 确保是偶数长度
    if len(hex_clean) % 2 != 0:
        hex_clean = '0' + hex_clean
    
    if sys.version_info[0] >= 3:
        return bytes.fromhex(hex_clean)
    else:
        return hex_clean.decode('hex')


def extract_strings(data, min_len=4):
    """从字节数据中提取可读字符串"""
    strings = []
    current = []
    
    for b in data:
        c = b if sys.version_info[0] >= 3 else ord(b)
        
        if 32 <= c < 127:
            current.append(chr(c))
        else:
            if len(current) >= min_len:
                strings.append(''.join(current))
            current = []
    
    if len(current) >= min_len:
        strings.append(''.join(current))
    
    return sorted(set(strings))


def create_pyc(bytecode, output_path, py_version='3.7'):
    """创建 .pyc 文件"""
    
    # Magic numbers for different Python versions
    magic_map = {
        '2.7': b'\x03\xf3\r\n',
        '3.5': b'\x16\r\r\n', 
        '3.6': b'\x33\r\r\n',
        '3.7': b'\x42\r\r\n',
        '3.8': b'\x55\r\r\n',
        '3.9': b'\x61\r\r\n',
        '3.10': b'\x6f\r\r\n',
        '3.11': b'\xa7\r\r\n',
    }
    
    magic = magic_map.get(py_version, magic_map['3.7'])
    timestamp = struct.pack('I', int(time.time()))
    source_size = struct.pack('I', 0)
    
    with open(output_path, 'wb') as f:
        f.write(magic)
        f.write(timestamp)
        if py_version >= '3.7':
            f.write(source_size)
        f.write(bytecode)
    
    return output_path


def try_decompile(pyc_path, output_path):
    """尝试反编译 .pyc 文件"""
    
    # 方法 1: uncompyle6
    try:
        import uncompyle6
        with open(output_path, 'w', encoding='utf-8') as f:
            uncompyle6.decompile_file(pyc_path, f)
        return True, "uncompyle6"
    except Exception as e:
        error1 = str(e)
    
    # 方法 2: decompyle3
    try:
        import decompyle3
        with open(output_path, 'w', encoding='utf-8') as f:
            decompyle3.decompile_file(pyc_path, f)
        return True, "decompyle3"
    except ImportError:
        pass
    except Exception as e:
        pass
    
    # 方法 3: pycdc (如果安装了)
    try:
        import subprocess
        result = subprocess.run(['pycdc', pyc_path], capture_output=True, text=True)
        if result.returncode == 0:
            with open(output_path, 'w') as f:
                f.write(result.stdout)
            return True, "pycdc"
    except:
        pass
    
    return False, error1


def analyze_bytecode(data):
    """分析字节码内容"""
    print("\n" + "=" * 60)
    print("📊 字节码分析")
    print("=" * 60)
    print("大小: {} bytes ({:.2f} KB)".format(len(data), len(data)/1024))
    
    # 提取字符串
    strings = extract_strings(data)
    
    # 分类
    categories = {
        '模块/导入': [],
        '类名': [],
        '函数名': [],
        'Maya 相关': [],
        'UI 元素': [],
        '其他': []
    }
    
    known_modules = {'maya', 'cmds', 'OpenMaya', 'OpenMayaAnim', 'mel', 'pymel',
                     'math', 'os', 'sys', 'json', 'pickle', 're', 'functools',
                     'collections', 'OrderedDict', 'numpy', 'scipy'}
    
    for s in strings:
        if s in known_modules:
            categories['模块/导入'].append(s)
        elif s[0].isupper() and '_' not in s and len(s) > 2:
            categories['类名'].append(s)
        elif any(x in s.lower() for x in ['_frn', 'layout', 'button', 'window', 'dialog']):
            categories['UI 元素'].append(s)
        elif any(x in s.lower() for x in ['joint', 'skin', 'ctrl', 'grp', 'sdk', 'rig', 'bind']):
            categories['Maya 相关'].append(s)
        elif s[0].islower() or '_' in s:
            categories['函数名'].append(s)
        else:
            categories['其他'].append(s)
    
    for cat, items in categories.items():
        if items:
            print("\n📌 {} ({}):".format(cat, len(items)))
            for item in sorted(items)[:30]:
                print("    {}".format(item))
            if len(items) > 30:
                print("    ... 还有 {} 个".format(len(items) - 30))
    
    return strings


def main():
    print("=" * 60)
    print("🔧 Python 字节码反编译工具")
    print("=" * 60)
    
    data = None
    input_source = None
    
    # 检查命令行参数
    if len(sys.argv) > 1:
        arg = sys.argv[1]
        
        if arg == '--interactive':
            print("\n📝 请粘贴十六进制数据 (输入空行结束):")
            lines = []
            while True:
                try:
                    line = input()
                    if not line.strip():
                        break
                    lines.append(line)
                except EOFError:
                    break
            hex_data = '\n'.join(lines)
            data = hex_to_bytes(hex_data)
            input_source = "interactive"
            
        elif os.path.exists(arg):
            if arg.endswith('.pyc'):
                # 直接是 .pyc 文件
                with open(arg, 'rb') as f:
                    data = f.read()
                input_source = arg
            else:
                # 假设是十六进制文本文件
                with open(arg, 'r') as f:
                    hex_data = f.read()
                data = hex_to_bytes(hex_data)
                input_source = arg
        else:
            print("❌ 文件不存在: {}".format(arg))
            return
    
    elif HEX_DATA.strip():
        data = hex_to_bytes(HEX_DATA)
        input_source = "HEX_DATA variable"
    
    else:
        print("""
❌ 没有输入数据!

使用方法:

1. 命令行传入文件:
   python3 decompile_tool.py yourfile.pyc
   python3 decompile_tool.py hexdata.txt

2. 交互式输入:
   python3 decompile_tool.py --interactive

3. 编辑脚本，将十六进制数据粘贴到 HEX_DATA 变量中

""")
        return
    
    print("\n📥 输入源: {}".format(input_source))
    print("📦 数据大小: {} bytes".format(len(data)))
    
    # 分析字节码
    strings = analyze_bytecode(data)
    
    # 保存提取的字符串
    output_dir = os.path.dirname(os.path.abspath(__file__))
    strings_path = os.path.join(output_dir, 'extracted_strings.txt')
    
    with open(strings_path, 'w', encoding='utf-8') as f:
        f.write("# Extracted strings from bytecode\n")
        f.write("# Total: {} strings\n\n".format(len(strings)))
        for s in strings:
            f.write("{}\n".format(s))
    print("\n💾 字符串已保存: {}".format(strings_path))
    
    # 创建 .pyc 文件
    print("\n" + "=" * 60)
    print("🔄 尝试反编译")  
    print("=" * 60)
    
    # 尝试不同的 Python 版本
    versions = ['3.7', '3.6', '2.7', '3.8', '3.9']
    
    for ver in versions:
        pyc_path = os.path.join(output_dir, 'temp_py{}.pyc'.format(ver.replace('.', '')))
        py_path = os.path.join(output_dir, 'decompiled_py{}.py'.format(ver.replace('.', '')))
        
        print("\n尝试 Python {} ...".format(ver))
        
        create_pyc(data, pyc_path, ver)
        success, tool = try_decompile(pyc_path, py_path)
        
        if success:
            print("✅ 成功! 使用: {}".format(tool))
            print("📄 输出文件: {}".format(py_path))
            
            # 显示预览
            with open(py_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            print("\n" + "-" * 60)
            print("预览 (前3000字符):")
            print("-" * 60)
            print(content[:3000])
            if len(content) > 3000:
                print("\n... (完整内容请查看文件)")
            
            # 清理临时文件
            os.remove(pyc_path)
            return
        else:
            print("❌ 失败: {}".format(tool))
            os.remove(pyc_path)
    
    print("\n" + "=" * 60)
    print("⚠️  所有版本都反编译失败")
    print("=" * 60)
    print("""
可能的原因:
1. 字节码不完整 (请确保粘贴完整的十六进制数据)
2. 字节码已加密/混淆
3. 非标准的 Python 字节码格式

建议:
1. 确认数据完整性
2. 尝试使用 pycdc 工具: https://github.com/zrax/pycdc
3. 查看提取的字符串文件了解代码结构
""")


if __name__ == '__main__':
    main()
