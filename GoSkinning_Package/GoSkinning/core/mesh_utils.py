# -*- coding: utf-8 -*-
"""
网格工具模块
提供网格相关的实用功能
"""

from typing import List, Dict, Optional, Tuple, Set

try:
    import pymxs
    from pymxs import runtime as rt
    MAX_AVAILABLE = True
except ImportError:
    MAX_AVAILABLE = False


class MeshUtils:
    """网格工具类"""
    
    @staticmethod
    def get_selected_mesh():
        """获取选中的网格对象"""
        if not MAX_AVAILABLE:
            return None
        
        if rt.selection.count == 0:
            return None
        
        obj = rt.selection[0]
        if MeshUtils.is_mesh(obj):
            return obj
        return None
    
    @staticmethod
    def is_mesh(obj) -> bool:
        """判断对象是否是网格"""
        if not MAX_AVAILABLE:
            return False
        
        mesh_classes = [
            rt.Editable_Poly,
            rt.Editable_Mesh,
            rt.PolyMeshObject,
        ]
        
        obj_class = rt.classOf(obj)
        if obj_class in mesh_classes:
            return True
        
        # 检查基对象
        if hasattr(obj, 'baseObject'):
            base_class = rt.classOf(obj.baseObject)
            if base_class in mesh_classes:
                return True
        
        return False
    
    @staticmethod
    def get_vertex_count(mesh_obj) -> int:
        """获取顶点数量"""
        if not MAX_AVAILABLE:
            return 0
        
        try:
            if rt.classOf(mesh_obj) == rt.Editable_Poly or rt.classOf(mesh_obj.baseObject) == rt.Editable_Poly:
                return rt.polyOp.getNumVerts(mesh_obj)
            else:
                return rt.meshOp.getNumVerts(mesh_obj)
        except:
            return 0
    
    @staticmethod
    def get_vertex_position(mesh_obj, vertex_index: int) -> Tuple[float, float, float]:
        """获取顶点位置"""
        if not MAX_AVAILABLE:
            return (0.0, 0.0, 0.0)
        
        try:
            if rt.classOf(mesh_obj) == rt.Editable_Poly or rt.classOf(mesh_obj.baseObject) == rt.Editable_Poly:
                pos = rt.polyOp.getVert(mesh_obj, vertex_index)
            else:
                pos = rt.meshOp.getVert(mesh_obj, vertex_index)
            return (pos.x, pos.y, pos.z)
        except:
            return (0.0, 0.0, 0.0)
    
    @staticmethod
    def get_all_vertex_positions(mesh_obj) -> List[Tuple[float, float, float]]:
        """获取所有顶点位置"""
        if not MAX_AVAILABLE:
            return []
        
        positions = []
        num_verts = MeshUtils.get_vertex_count(mesh_obj)
        
        for i in range(1, num_verts + 1):
            pos = MeshUtils.get_vertex_position(mesh_obj, i)
            positions.append(pos)
        
        return positions
    
    @staticmethod
    def get_selected_vertices(mesh_obj) -> List[int]:
        """获取选中的顶点索引"""
        if not MAX_AVAILABLE:
            return []
        
        try:
            # 需要在子对象模式下
            if rt.classOf(mesh_obj) == rt.Editable_Poly or rt.classOf(mesh_obj.baseObject) == rt.Editable_Poly:
                vert_sel = rt.polyOp.getVertSelection(mesh_obj)
            else:
                vert_sel = rt.getVertSelection(mesh_obj)
            
            # 转换BitArray为列表
            indices = []
            num_verts = MeshUtils.get_vertex_count(mesh_obj)
            for i in range(1, num_verts + 1):
                if vert_sel[i]:
                    indices.append(i)
            return indices
        except:
            return []
    
    @staticmethod
    def set_vertex_selection(mesh_obj, vertex_indices: List[int]):
        """设置顶点选择"""
        if not MAX_AVAILABLE:
            return
        
        try:
            # 创建BitArray
            bit_array = rt.BitArray()
            for idx in vertex_indices:
                rt.append(bit_array, idx)
            
            if rt.classOf(mesh_obj) == rt.Editable_Poly or rt.classOf(mesh_obj.baseObject) == rt.Editable_Poly:
                rt.polyOp.setVertSelection(mesh_obj, bit_array)
            else:
                rt.setVertSelection(mesh_obj, bit_array)
        except Exception as e:
            print(f"[MeshUtils] 设置顶点选择失败: {e}")
    
    @staticmethod
    def get_face_count(mesh_obj) -> int:
        """获取面数量"""
        if not MAX_AVAILABLE:
            return 0
        
        try:
            if rt.classOf(mesh_obj) == rt.Editable_Poly or rt.classOf(mesh_obj.baseObject) == rt.Editable_Poly:
                return rt.polyOp.getNumFaces(mesh_obj)
            else:
                return rt.meshOp.getNumFaces(mesh_obj)
        except:
            return 0
    
    @staticmethod
    def get_face_vertices(mesh_obj, face_index: int) -> List[int]:
        """获取面的顶点索引"""
        if not MAX_AVAILABLE:
            return []
        
        try:
            if rt.classOf(mesh_obj) == rt.Editable_Poly or rt.classOf(mesh_obj.baseObject) == rt.Editable_Poly:
                verts = rt.polyOp.getFaceVerts(mesh_obj, face_index)
            else:
                verts = rt.getFace(mesh_obj, face_index)
            return list(verts)
        except:
            return []
    
    @staticmethod
    def get_vertex_adjacency(mesh_obj) -> Dict[int, List[int]]:
        """
        获取顶点邻接关系
        Returns: {vertex_index: [adjacent_vertex_indices]}
        """
        if not MAX_AVAILABLE:
            return {}
        
        adjacency = {}
        num_verts = MeshUtils.get_vertex_count(mesh_obj)
        num_faces = MeshUtils.get_face_count(mesh_obj)
        
        # 初始化
        for i in range(1, num_verts + 1):
            adjacency[i] = set()
        
        # 遍历所有面,建立邻接关系
        for face_idx in range(1, num_faces + 1):
            face_verts = MeshUtils.get_face_vertices(mesh_obj, face_idx)
            
            # 同一个面上的顶点互为邻居
            for i, v1 in enumerate(face_verts):
                for j, v2 in enumerate(face_verts):
                    if i != j:
                        adjacency[v1].add(v2)
        
        # 转换set为list
        return {k: list(v) for k, v in adjacency.items()}
    
    @staticmethod
    def get_bounding_box(mesh_obj) -> Tuple[Tuple[float, float, float], Tuple[float, float, float]]:
        """
        获取网格的包围盒
        Returns: (min_point, max_point)
        """
        if not MAX_AVAILABLE:
            return ((0, 0, 0), (0, 0, 0))
        
        positions = MeshUtils.get_all_vertex_positions(mesh_obj)
        if not positions:
            return ((0, 0, 0), (0, 0, 0))
        
        min_x = min(p[0] for p in positions)
        min_y = min(p[1] for p in positions)
        min_z = min(p[2] for p in positions)
        max_x = max(p[0] for p in positions)
        max_y = max(p[1] for p in positions)
        max_z = max(p[2] for p in positions)
        
        return ((min_x, min_y, min_z), (max_x, max_y, max_z))
    
    @staticmethod
    def get_vertices_in_region(mesh_obj, 
                                min_point: Tuple[float, float, float],
                                max_point: Tuple[float, float, float]) -> List[int]:
        """获取指定区域内的顶点"""
        if not MAX_AVAILABLE:
            return []
        
        vertices = []
        num_verts = MeshUtils.get_vertex_count(mesh_obj)
        
        for i in range(1, num_verts + 1):
            pos = MeshUtils.get_vertex_position(mesh_obj, i)
            if (min_point[0] <= pos[0] <= max_point[0] and
                min_point[1] <= pos[1] <= max_point[1] and
                min_point[2] <= pos[2] <= max_point[2]):
                vertices.append(i)
        
        return vertices
    
    @staticmethod
    def get_skin_modifier(mesh_obj):
        """获取网格的Skin修改器"""
        if not MAX_AVAILABLE:
            return None
        
        try:
            for mod in mesh_obj.modifiers:
                if rt.classOf(mod) == rt.Skin:
                    return mod
        except:
            pass
        return None
    
    @staticmethod
    def has_skin_modifier(mesh_obj) -> bool:
        """检查网格是否有Skin修改器"""
        return MeshUtils.get_skin_modifier(mesh_obj) is not None
    
    @staticmethod
    def get_vertex_weights(mesh_obj, vertex_index: int) -> List[Tuple[str, float]]:
        """
        获取顶点的权重信息
        Returns: [(bone_name, weight), ...]
        """
        if not MAX_AVAILABLE:
            return []
        
        skin_mod = MeshUtils.get_skin_modifier(mesh_obj)
        if not skin_mod:
            return []
        
        try:
            weights = []
            num_weights = rt.skinOps.getVertexWeightCount(skin_mod, vertex_index)
            
            for i in range(1, num_weights + 1):
                bone_id = rt.skinOps.getVertexWeightBoneID(skin_mod, vertex_index, i)
                weight = rt.skinOps.getVertexWeight(skin_mod, vertex_index, i)
                bone_name = rt.skinOps.getBoneName(skin_mod, bone_id, 0)
                weights.append((bone_name, weight))
            
            return weights
        except:
            return []
    
    @staticmethod
    def copy_mesh(mesh_obj, name: Optional[str] = None):
        """复制网格对象"""
        if not MAX_AVAILABLE:
            return None
        
        try:
            copy = rt.copy(mesh_obj)
            if name:
                copy.name = name
            return copy
        except:
            return None
    
    @staticmethod
    def simplify_mesh(mesh_obj, target_percent: float = 50.0):
        """
        简化网格
        Args:
            target_percent: 目标顶点百分比 (0-100)
        """
        if not MAX_AVAILABLE:
            return None
        
        try:
            pro_opt = rt.ProOptimizer()
            rt.addModifier(mesh_obj, pro_opt)
            pro_opt.vertexPercent = target_percent
            rt.collapseStack(mesh_obj)
            return mesh_obj
        except:
            return None
