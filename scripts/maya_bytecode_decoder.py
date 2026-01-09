# -*- coding: utf-8 -*-
"""
Maya Bytecode Decoder - 在 Maya 中直接运行
直接粘贴到 Maya Script Editor 运行即可

功能：
1. 从十六进制提取所有字符串（函数名、变量名、模块名等）
2. 分析代码结构
3. 导出为可读格式
"""

from __future__ import print_function
import sys
import os
import marshal
import types

# ============================================================================
# 将完整的十六进制数据粘贴到这里
# ============================================================================

HEX_DATA = """
6300 0000 0000 0000 0003 0000 0040 0000
0073 aa00 0000 6400 0064 0100 6c00 006d
0100 5a01 0001 6400 0064 0200 6c02 005a
"""  # 在这里粘贴完整的十六进制数据


# ============================================================================
# 核心功能
# ============================================================================

def hex_to_bytes(hex_string):
    """十六进制转字节"""
    hex_clean = ''.join(hex_string.split())
    if sys.version_info[0] >= 3:
        return bytes.fromhex(hex_clean)
    else:
        return hex_clean.decode('hex')


def extract_all_strings(data, min_len=3):
    """提取所有可读字符串"""
    strings = []
    current = []
    
    for i, b in enumerate(data):
        if sys.version_info[0] >= 3:
            c = b
        else:
            c = ord(b)
        
        if 32 <= c < 127:
            current.append(chr(c))
        else:
            if len(current) >= min_len:
                s = ''.join(current)
                strings.append(s)
            current = []
    
    if len(current) >= min_len:
        strings.append(''.join(current))
    
    return strings


def categorize_strings(strings):
    """分类字符串"""
    result = {
        'modules': set(),
        'functions': set(),
        'classes': set(),
        'variables': set(),
        'ui_elements': set(),
        'maya_commands': set(),
        'others': set()
    }
    
    maya_cmds = {'select', 'group', 'parent', 'delete', 'duplicate', 'ls', 'objExists',
                 'getAttr', 'setAttr', 'addAttr', 'deleteAttr', 'connectAttr', 
                 'listConnections', 'listRelatives', 'listAttr', 'keyframe',
                 'setDrivenKeyframe', 'skinCluster', 'skinPercent', 'copySkinWeights',
                 'createNode', 'window', 'button', 'text', 'textField', 'checkBox',
                 'optionMenu', 'rowLayout', 'columnLayout', 'frameLayout', 'formLayout',
                 'showWindow', 'deleteUI', 'progressWindow', 'confirmDialog'}
    
    for s in strings:
        s_lower = s.lower()
        
        # UI 元素
        if any(x in s_lower for x in ['_frn', '_btn', '_cb', '_tf', 'layout', 'window']):
            result['ui_elements'].add(s)
        # Maya 命令
        elif s in maya_cmds:
            result['maya_commands'].add(s)
        # 模块/导入
        elif s in ['maya', 'cmds', 'OpenMaya', 'OpenMayaAnim', 'mel', 'math', 'os', 
                   'sys', 'pickle', 'json', 'functools', 'collections']:
            result['modules'].add(s)
        # 函数（小写开头，含下划线或驼峰）
        elif s[0].islower() and ('_' in s or any(c.isupper() for c in s[1:])):
            result['functions'].add(s)
        # 类（大写开头）
        elif s[0].isupper() and s.isidentifier() if hasattr(str, 'isidentifier') else s.replace('_','').isalnum():
            result['classes'].add(s)
        # 变量
        elif s.isidentifier() if hasattr(str, 'isidentifier') else s.replace('_','').isalnum():
            result['variables'].add(s)
        else:
            result['others'].add(s)
    
    return result


def analyze_code_structure(data):
    """尝试分析代码结构"""
    try:
        # 尝试多个偏移量
        for offset in [0, 4, 8, 12, 16]:
            try:
                code = marshal.loads(data[offset:])
                return analyze_code_object(code, "")
            except:
                continue
    except:
        pass
    return None


def analyze_code_object(code, indent=""):
    """递归分析代码对象"""
    info = {
        'name': getattr(code, 'co_name', '<unknown>'),
        'filename': getattr(code, 'co_filename', '<unknown>'),
        'names': list(getattr(code, 'co_names', [])),
        'varnames': list(getattr(code, 'co_varnames', [])),
        'constants': [],
        'nested': []
    }
    
    # 提取常量（排除代码对象）
    if hasattr(code, 'co_consts'):
        for const in code.co_consts:
            if isinstance(const, types.CodeType):
                nested = analyze_code_object(const, indent + "  ")
                info['nested'].append(nested)
            elif const is not None:
                if isinstance(const, str) and len(const) < 200:
                    info['constants'].append(const)
                elif isinstance(const, (int, float)):
                    info['constants'].append(const)
    
    return info


def print_analysis(info, indent=""):
    """打印分析结果"""
    if info is None:
        return
    
    print("{}📦 {}".format(indent, info['name']))
    
    if info['names']:
        print("{}  Names: {}".format(indent, ', '.join(info['names'][:20])))
    
    if info['varnames']:
        print("{}  Variables: {}".format(indent, ', '.join(info['varnames'][:20])))
    
    if info['constants']:
        print("{}  Constants: {}".format(indent, info['constants'][:10]))
    
    for nested in info['nested']:
        print_analysis(nested, indent + "  ")


def decode_bytecode(hex_data=None):
    """
    主函数 - 解码字节码
    
    用法：
        decode_bytecode()  # 使用 HEX_DATA 变量中的数据
        decode_bytecode("6300 0000...")  # 直接传入十六进制字符串
    """
    if hex_data is None:
        hex_data = HEX_DATA
    
    if not hex_data.strip():
        print("❌ 请将十六进制数据粘贴到 HEX_DATA 变量中")
        return
    
    print("=" * 60)
    print("🔍 Python Bytecode Decoder")
    print("=" * 60)
    
    # 转换
    try:
        data = hex_to_bytes(hex_data)
        print("\n✅ 转换了 {} 字节的数据".format(len(data)))
    except Exception as e:
        print("\n❌ 转换错误: {}".format(e))
        return
    
    # 提取字符串
    print("\n" + "=" * 60)
    print("📝 提取的字符串")
    print("=" * 60)
    
    strings = extract_all_strings(data)
    categories = categorize_strings(strings)
    
    print("\n🔌 模块/导入 ({}):".format(len(categories['modules'])))
    for s in sorted(categories['modules']):
        print("    import {}".format(s))
    
    print("\n🔧 函数 ({}):".format(len(categories['functions'])))
    for s in sorted(categories['functions'])[:40]:
        print("    def {}()".format(s))
    if len(categories['functions']) > 40:
        print("    ... 还有 {} 个".format(len(categories['functions']) - 40))
    
    print("\n📦 类/类型 ({}):".format(len(categories['classes'])))
    for s in sorted(categories['classes'])[:20]:
        print("    class {}".format(s))
    
    print("\n🖥️ UI 元素 ({}):".format(len(categories['ui_elements'])))
    for s in sorted(categories['ui_elements'])[:20]:
        print("    {}".format(s))
    
    print("\n🎮 Maya 命令 ({}):".format(len(categories['maya_commands'])))
    for s in sorted(categories['maya_commands']):
        print("    cmds.{}()".format(s))
    
    # 分析代码结构
    print("\n" + "=" * 60)
    print("📊 代码结构分析")
    print("=" * 60)
    
    structure = analyze_code_structure(data)
    if structure:
        print_analysis(structure)
    else:
        print("无法解析代码结构（可能需要正确的 Python 版本）")
    
    # 保存提取结果
    output_path = os.path.join(os.path.dirname(__file__) or '.', 'bytecode_analysis.txt')
    
    with open(output_path, 'w') as f:
        f.write("# Bytecode Analysis Result\n")
        f.write("# Generated by Maya Bytecode Decoder\n\n")
        
        f.write("## Modules\n")
        for s in sorted(categories['modules']):
            f.write("import {}\n".format(s))
        
        f.write("\n## Functions\n")
        for s in sorted(categories['functions']):
            f.write("def {}(): pass\n".format(s))
        
        f.write("\n## Classes\n")
        for s in sorted(categories['classes']):
            f.write("class {}: pass\n".format(s))
        
        f.write("\n## All Strings\n")
        for s in sorted(set(strings)):
            if len(s) >= 4:
                f.write("# {}\n".format(s))
    
    print("\n" + "=" * 60)
    print("💾 结果已保存到: {}".format(output_path))
    print("=" * 60)
    
    return categories


# ============================================================================
# 快速分析函数（可直接调用）
# ============================================================================

def quick_strings(hex_data):
    """快速提取字符串"""
    data = hex_to_bytes(hex_data)
    return sorted(set(extract_all_strings(data)))


# ============================================================================
# 直接运行
# ============================================================================

if __name__ == '__main__':
    decode_bytecode()
