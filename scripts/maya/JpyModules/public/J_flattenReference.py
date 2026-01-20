# -*- coding: utf-8 -*-
"""
@package public
@brief  将场景中所有 reference 导入为本地并删除命名空间前缀
@author 桔
@version 2.0
@date  2026/01/20

History:
    v2.0 - 优化版本，增加以下改进：
        - 添加 undo 支持
        - 改进嵌套引用处理顺序（从深到浅）
        - 更精确的异常处理
        - 添加进度反馈
        - 模块化代码结构
        - 添加返回值统计
"""

import maya.cmds as cmds


def _get_reference_info(ref_node):
    """
    获取单个引用节点的信息
    
    :param ref_node: 引用节点名称
    :return: (namespace, filepath) 或 None（如果无法获取）
    """
    try:
        ns = cmds.referenceQuery(ref_node, namespace=True)
    except RuntimeError:
        return None
    
    # 移除开头的冒号
    ns = ns.lstrip(':') if ns else ''
    
    try:
        fpath = cmds.referenceQuery(ref_node, filename=True, withoutCopyNumber=True)
    except RuntimeError:
        fpath = ''
    
    return (ns, fpath) if ns else None


def _get_reference_depth(ref_node):
    """
    获取引用的嵌套深度
    
    :param ref_node: 引用节点名称
    :return: 嵌套深度（0 表示顶层引用）
    """
    try:
        parent = cmds.referenceQuery(ref_node, referenceNode=True, parent=True)
        if parent:
            return 1 + _get_reference_depth(parent)
    except RuntimeError:
        pass
    return 0


def _load_reference(ref_node):
    """
    确保引用已加载
    
    :param ref_node: 引用节点名称
    :return: True 如果成功加载或已加载，False 如果失败
    """
    try:
        if not cmds.referenceQuery(ref_node, isLoaded=True):
            cmds.file(loadReference=ref_node)
        return True
    except RuntimeError as e:
        cmds.warning(u'无法加载引用 %s: %s' % (ref_node, str(e)))
        return False


def _import_reference(ref_node):
    """
    导入引用为本地
    
    :param ref_node: 引用节点名称
    :return: True 如果成功，False 如果失败
    """
    try:
        cmds.file(importReference=True, referenceNode=ref_node)
        return True
    except RuntimeError:
        # 尝试解锁后再导入
        try:
            cmds.lockNode(ref_node, lock=False)
            cmds.file(importReference=True, referenceNode=ref_node)
            return True
        except RuntimeError as e:
            cmds.warning(u'导入引用失败 %s: %s' % (ref_node, str(e)))
            return False


def _remove_namespace(ns, remove_nested=True):
    """
    删除命名空间
    
    :param ns: 命名空间名称
    :param remove_nested: 是否同时删除嵌套的子命名空间
    :return: 删除的命名空间数量
    """
    removed_count = 0
    
    if not ns or not cmds.namespace(exists=ns):
        return removed_count
    
    if remove_nested:
        # 获取所有子命名空间并按深度排序（从深到浅）
        try:
            sub_namespaces = cmds.namespaceInfo(
                ':%s' % ns, 
                listOnlyNamespaces=True, 
                recurse=True
            ) or []
        except RuntimeError:
            sub_namespaces = []
        
        # 清理命名空间名称并按深度排序
        sub_ns_cleaned = [s.lstrip(':') for s in sub_namespaces if s]
        sub_ns_sorted = sorted(
            sub_ns_cleaned,
            key=lambda x: x.count(':'),
            reverse=True
        )
        
        # 从最深层开始删除
        for sub_ns in sub_ns_sorted:
            if sub_ns and cmds.namespace(exists=sub_ns):
                try:
                    cmds.namespace(
                        removeNamespace=sub_ns, 
                        mergeNamespaceWithParent=True
                    )
                    removed_count += 1
                    print(u'  已删除子命名空间: %s' % sub_ns)
                except RuntimeError as e:
                    cmds.warning(u'删除子命名空间失败 %s: %s' % (sub_ns, str(e)))
    
    # 删除主命名空间
    try:
        cmds.namespace(removeNamespace=ns, mergeNamespaceWithParent=True)
        removed_count += 1
        print(u'  已删除主命名空间: %s' % ns)
    except RuntimeError as e:
        cmds.warning(u'删除命名空间失败 %s: %s' % (ns, str(e)))
    
    return removed_count


def flatten_reference_and_drop_all_namespaces(also_nested=True, dry_run=False):
    """
    自动将场景中所有 reference 导入为本地并删除命名空间前缀。
    
    :param also_nested: 是否同时删除子命名空间。
    :param dry_run: 仅打印将要处理的对象，不实际修改。
    :return: dict 包含处理统计信息
        - 'references_found': 检测到的引用数量
        - 'references_imported': 成功导入的引用数量
        - 'namespaces_removed': 删除的命名空间数量
    """
    # 系统保留的引用节点
    SYSTEM_REF_NODES = ('sharedReferenceNode', '_UNKNOWN_REF_NODE_')
    
    # 统计信息
    stats = {
        'references_found': 0,
        'references_imported': 0,
        'namespaces_removed': 0
    }
    
    # 获取所有引用节点（排除系统节点）
    all_ref_nodes = cmds.ls(type='reference') or []
    ref_nodes = [r for r in all_ref_nodes if r not in SYSTEM_REF_NODES]
    
    # 收集引用信息
    items = []
    for ref_node in ref_nodes:
        info = _get_reference_info(ref_node)
        if info:
            ns, fpath = info
            depth = _get_reference_depth(ref_node)
            items.append({
                'ref_node': ref_node,
                'namespace': ns,
                'filepath': fpath,
                'depth': depth
            })
    
    stats['references_found'] = len(items)
    
    if not items:
        cmds.warning(u'场景中没有检测到任何引用或命名空间。')
        return stats
    
    # 按深度排序（从深到浅处理，确保嵌套引用先被处理）
    items.sort(key=lambda x: x['depth'], reverse=True)
    
    # 打印检测结果
    print(u'\n检测到以下引用，将进行导入与命名空间清理：')
    print(u'-' * 60)
    for item in items:
        print(u'  引用节点: %s' % item['ref_node'])
        print(u'  命名空间: %s' % item['namespace'])
        print(u'  文件路径: %s' % item['filepath'])
        print(u'  嵌套深度: %d' % item['depth'])
        print(u'-' * 60)
    
    if dry_run:
        print(u'\n[DRY RUN] 仅预览模式，不执行实际修改。')
        return stats
    
    # 开启 undo chunk，支持一次性撤销
    cmds.undoInfo(openChunk=True, chunkName='FlattenReferences')
    
    try:
        total = len(items)
        for idx, item in enumerate(items):
            ref_node = item['ref_node']
            ns = item['namespace']
            
            print(u'\n[%d/%d] 处理引用: %s' % (idx + 1, total, ref_node))
            
            # 检查引用是否仍然存在（可能已被父引用导入时处理）
            if not cmds.objExists(ref_node):
                print(u'  引用节点已不存在，跳过')
                continue
            
            # 加载引用
            if not _load_reference(ref_node):
                continue
            
            # 导入引用
            if _import_reference(ref_node):
                stats['references_imported'] += 1
                print(u'  已导入引用: %s' % ref_node)
            else:
                continue
            
            # 删除命名空间
            removed = _remove_namespace(ns, remove_nested=also_nested)
            stats['namespaces_removed'] += removed
            
    finally:
        # 关闭 undo chunk
        cmds.undoInfo(closeChunk=True)
    
    # 打印完成信息
    print(u'\n' + u'=' * 60)
    print(u'处理完成！')
    print(u'  检测到引用: %d' % stats['references_found'])
    print(u'  成功导入: %d' % stats['references_imported'])
    print(u'  删除命名空间: %d' % stats['namespaces_removed'])
    print(u'=' * 60)
    print(u'请保存场景为新文件。')
    
    return stats


def clean_orphan_namespaces():
    """
    清理场景中的孤立命名空间（无引用关联的空命名空间）
    
    :return: 删除的命名空间数量
    """
    # 系统保留命名空间
    SYSTEM_NS = ('UI', 'shared')
    
    removed_count = 0
    
    # 获取所有命名空间
    all_ns = cmds.namespaceInfo(listOnlyNamespaces=True, recurse=True) or []
    
    # 按深度排序（从深到浅）
    all_ns_cleaned = [ns.lstrip(':') for ns in all_ns if ns]
    all_ns_sorted = sorted(
        [ns for ns in all_ns_cleaned if ns not in SYSTEM_NS],
        key=lambda x: x.count(':'),
        reverse=True
    )
    
    for ns in all_ns_sorted:
        if not cmds.namespace(exists=ns):
            continue
        
        # 检查命名空间是否为空
        try:
            contents = cmds.namespaceInfo(ns, listNamespace=True) or []
            if not contents:
                cmds.namespace(removeNamespace=ns)
                removed_count += 1
                print(u'已删除空命名空间: %s' % ns)
        except RuntimeError:
            pass
    
    if removed_count:
        print(u'共删除 %d 个孤立命名空间' % removed_count)
    else:
        print(u'没有发现孤立命名空间')
    
    return removed_count


# ========== 使用示例 ==========
if __name__ == '__main__':
    # 自动清理场景中所有引用命名空间：
    # flatten_reference_and_drop_all_namespaces()
    
    # 如果想先预览将会清理哪些引用，而不修改场景，可用：
    # flatten_reference_and_drop_all_namespaces(dry_run=True)
    
    # 清理孤立的空命名空间：
    # clean_orphan_namespaces()
    pass
