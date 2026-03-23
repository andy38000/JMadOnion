# -*- coding: utf-8 -*-
"""
骨骼工具模块
提供骨骼相关的实用功能
"""

from typing import List, Dict, Optional, Tuple, Set

try:
    import pymxs
    from pymxs import runtime as rt
    MAX_AVAILABLE = True
except ImportError:
    MAX_AVAILABLE = False


class BoneUtils:
    """骨骼工具类"""
    
    @staticmethod
    def get_all_bones() -> List:
        """获取场景中所有骨骼"""
        if not MAX_AVAILABLE:
            return []
        
        bones = []
        for obj in rt.objects:
            if BoneUtils.is_bone(obj):
                bones.append(obj)
        return bones
    
    @staticmethod
    def is_bone(obj) -> bool:
        """判断对象是否是骨骼"""
        if not MAX_AVAILABLE:
            return False
        
        bone_classes = [
            rt.BoneGeometry,
            rt.Biped_Object,
            rt.Dummy,
        ]
        
        obj_class = rt.classOf(obj)
        
        # 检查基本骨骼类型
        if obj_class in bone_classes:
            return True
        
        # 检查CAT骨骼
        class_name = str(obj_class)
        if 'CATBone' in class_name or 'HubObject' in class_name:
            return True
        
        # 检查是否有骨骼相关属性
        if hasattr(obj, 'boneEnable'):
            return True
        
        return False
    
    @staticmethod
    def get_bone_hierarchy(root_bone) -> Dict:
        """
        获取骨骼层级结构
        
        Returns:
            {bone: [children]} 字典
        """
        if not MAX_AVAILABLE:
            return {}
        
        hierarchy = {}
        
        def traverse(bone):
            children = []
            for child in bone.children:
                if BoneUtils.is_bone(child):
                    children.append(child)
                    traverse(child)
            hierarchy[bone] = children
        
        traverse(root_bone)
        return hierarchy
    
    @staticmethod
    def get_bone_chain(start_bone, end_bone) -> List:
        """
        获取两个骨骼之间的骨骼链
        """
        if not MAX_AVAILABLE:
            return []
        
        chain = []
        current = end_bone
        
        while current is not None:
            chain.append(current)
            if current == start_bone:
                break
            current = current.parent
        
        chain.reverse()
        return chain
    
    @staticmethod
    def get_bone_position(bone) -> Tuple[float, float, float]:
        """获取骨骼位置"""
        if not MAX_AVAILABLE:
            return (0.0, 0.0, 0.0)
        
        try:
            pos = bone.transform.pos
            return (pos.x, pos.y, pos.z)
        except:
            return (0.0, 0.0, 0.0)
    
    @staticmethod
    def get_bone_length(bone) -> float:
        """获取骨骼长度"""
        if not MAX_AVAILABLE:
            return 0.0
        
        try:
            if hasattr(bone, 'length'):
                return bone.length
            elif hasattr(bone, 'width'):
                return bone.width
            else:
                # 估算长度
                if bone.children.count > 0:
                    child_pos = BoneUtils.get_bone_position(bone.children[0])
                    bone_pos = BoneUtils.get_bone_position(bone)
                    dx = child_pos[0] - bone_pos[0]
                    dy = child_pos[1] - bone_pos[1]
                    dz = child_pos[2] - bone_pos[2]
                    return (dx*dx + dy*dy + dz*dz) ** 0.5
                return 10.0  # 默认长度
        except:
            return 10.0
    
    @staticmethod
    def get_selected_bones() -> List:
        """获取选中的骨骼"""
        if not MAX_AVAILABLE:
            return []
        
        bones = []
        for obj in rt.selection:
            if BoneUtils.is_bone(obj):
                bones.append(obj)
        return bones
    
    @staticmethod
    def select_bones(bones: List):
        """选择指定的骨骼"""
        if not MAX_AVAILABLE:
            return
        
        rt.select(bones)
    
    @staticmethod
    def find_root_bone(bones: List):
        """从骨骼列表中找到根骨骼"""
        if not MAX_AVAILABLE or not bones:
            return None
        
        for bone in bones:
            parent = bone.parent
            # 如果父对象不是骨骼或不在列表中
            if parent is None or not BoneUtils.is_bone(parent) or parent not in bones:
                return bone
        
        return bones[0] if bones else None
    
    @staticmethod
    def sort_bones_by_hierarchy(bones: List) -> List:
        """按层级顺序排序骨骼(从根到叶)"""
        if not MAX_AVAILABLE or not bones:
            return bones
        
        def get_depth(bone, bone_set: Set) -> int:
            depth = 0
            current = bone
            while current is not None:
                if current.parent in bone_set:
                    depth += 1
                    current = current.parent
                else:
                    break
            return depth
        
        bone_set = set(bones)
        bone_depths = [(bone, get_depth(bone, bone_set)) for bone in bones]
        bone_depths.sort(key=lambda x: x[1])
        
        return [bone for bone, _ in bone_depths]
    
    @staticmethod
    def filter_face_bones(bones: List) -> List:
        """过滤出面部骨骼(基于名称)"""
        face_keywords = [
            'head', 'jaw', 'eye', 'brow', 'lip', 'cheek', 'nose', 'tongue',
            'mouth', 'eyelid', 'ear', 'face', 'facial',
            # 中文关键词
            '头', '下巴', '眼', '眉', '唇', '脸', '鼻', '舌', '嘴', '耳'
        ]
        
        face_bones = []
        for bone in bones:
            name_lower = bone.name.lower()
            for keyword in face_keywords:
                if keyword.lower() in name_lower:
                    face_bones.append(bone)
                    break
        
        return face_bones
    
    @staticmethod
    def filter_body_bones(bones: List) -> List:
        """过滤出身体骨骼(排除面部)"""
        face_bones = set(BoneUtils.filter_face_bones(bones))
        return [bone for bone in bones if bone not in face_bones]
    
    @staticmethod
    def get_biped_bones() -> Dict[str, List]:
        """获取Biped骨骼分类"""
        if not MAX_AVAILABLE:
            return {}
        
        result = {
            'spine': [],
            'left_arm': [],
            'right_arm': [],
            'left_leg': [],
            'right_leg': [],
            'head': [],
            'other': []
        }
        
        for obj in rt.objects:
            if rt.classOf(obj) == rt.Biped_Object:
                name_lower = obj.name.lower()
                
                if 'spine' in name_lower or 'pelvis' in name_lower:
                    result['spine'].append(obj)
                elif 'l ' in name_lower or ' l' in name_lower or name_lower.startswith('l'):
                    if 'arm' in name_lower or 'hand' in name_lower or 'finger' in name_lower:
                        result['left_arm'].append(obj)
                    elif 'leg' in name_lower or 'foot' in name_lower or 'toe' in name_lower:
                        result['left_leg'].append(obj)
                elif 'r ' in name_lower or ' r' in name_lower or name_lower.startswith('r'):
                    if 'arm' in name_lower or 'hand' in name_lower or 'finger' in name_lower:
                        result['right_arm'].append(obj)
                    elif 'leg' in name_lower or 'foot' in name_lower or 'toe' in name_lower:
                        result['right_leg'].append(obj)
                elif 'head' in name_lower or 'neck' in name_lower:
                    result['head'].append(obj)
                else:
                    result['other'].append(obj)
        
        return result
