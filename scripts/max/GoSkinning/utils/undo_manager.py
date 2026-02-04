# -*- coding: utf-8 -*-
"""
撤销管理器
管理蒙皮操作的撤销/重做
"""

from typing import List, Dict, Optional, Any, Callable
from dataclasses import dataclass, field
from datetime import datetime
import copy

try:
    import pymxs
    from pymxs import runtime as rt
    MAX_AVAILABLE = True
except ImportError:
    MAX_AVAILABLE = False


@dataclass
class UndoState:
    """撤销状态"""
    timestamp: datetime
    description: str
    mesh_name: str
    weights: List[List[tuple]]  # 顶点权重数据
    bone_names: List[str]
    additional_data: Dict[str, Any] = field(default_factory=dict)


class UndoManager:
    """
    撤销管理器
    支持多级撤销和重做
    """
    
    def __init__(self, max_history: int = 20):
        self.max_history = max_history
        self.undo_stack: List[UndoState] = []
        self.redo_stack: List[UndoState] = []
        self._enabled = True
    
    def enable(self):
        """启用撤销功能"""
        self._enabled = True
    
    def disable(self):
        """禁用撤销功能"""
        self._enabled = False
    
    def is_enabled(self) -> bool:
        """检查撤销功能是否启用"""
        return self._enabled
    
    def save_state(self, mesh_obj, description: str = ""):
        """
        保存当前状态到撤销栈
        
        Args:
            mesh_obj: 网格对象
            description: 操作描述
        """
        if not self._enabled:
            return
        
        if not MAX_AVAILABLE:
            return
        
        try:
            # 获取Skin修改器
            skin_mod = None
            for mod in mesh_obj.modifiers:
                if rt.classOf(mod) == rt.Skin:
                    skin_mod = mod
                    break
            
            if not skin_mod:
                return
            
            # 获取骨骼名称
            num_bones = rt.skinOps.getNumberBones(skin_mod)
            bone_names = []
            for i in range(1, num_bones + 1):
                name = rt.skinOps.getBoneName(skin_mod, i, 0)
                bone_names.append(name)
            
            # 获取权重数据
            num_verts = rt.skinOps.getNumberVertices(skin_mod)
            weights = []
            
            for v_idx in range(1, num_verts + 1):
                vert_weights = []
                num_weights = rt.skinOps.getVertexWeightCount(skin_mod, v_idx)
                
                for w_idx in range(1, num_weights + 1):
                    bone_id = rt.skinOps.getVertexWeightBoneID(skin_mod, v_idx, w_idx)
                    weight = rt.skinOps.getVertexWeight(skin_mod, v_idx, w_idx)
                    vert_weights.append((bone_id, weight))
                
                weights.append(vert_weights)
            
            # 创建状态
            state = UndoState(
                timestamp=datetime.now(),
                description=description,
                mesh_name=mesh_obj.name,
                weights=weights,
                bone_names=bone_names
            )
            
            # 添加到撤销栈
            self.undo_stack.append(state)
            
            # 清空重做栈
            self.redo_stack.clear()
            
            # 限制历史记录数量
            while len(self.undo_stack) > self.max_history:
                self.undo_stack.pop(0)
                
        except Exception as e:
            print(f"[UndoManager] 保存状态失败: {e}")
    
    def undo(self, mesh_obj) -> bool:
        """
        撤销到上一个状态
        
        Returns:
            是否成功
        """
        if not self._enabled or not self.undo_stack:
            return False
        
        if not MAX_AVAILABLE:
            return False
        
        try:
            # 保存当前状态到重做栈
            current_state = self._capture_current_state(mesh_obj)
            if current_state:
                self.redo_stack.append(current_state)
            
            # 恢复上一个状态
            state = self.undo_stack.pop()
            self._restore_state(mesh_obj, state)
            
            print(f"[UndoManager] 撤销: {state.description}")
            return True
            
        except Exception as e:
            print(f"[UndoManager] 撤销失败: {e}")
            return False
    
    def redo(self, mesh_obj) -> bool:
        """
        重做到下一个状态
        
        Returns:
            是否成功
        """
        if not self._enabled or not self.redo_stack:
            return False
        
        if not MAX_AVAILABLE:
            return False
        
        try:
            # 保存当前状态到撤销栈
            current_state = self._capture_current_state(mesh_obj)
            if current_state:
                self.undo_stack.append(current_state)
            
            # 恢复重做状态
            state = self.redo_stack.pop()
            self._restore_state(mesh_obj, state)
            
            print(f"[UndoManager] 重做: {state.description}")
            return True
            
        except Exception as e:
            print(f"[UndoManager] 重做失败: {e}")
            return False
    
    def _capture_current_state(self, mesh_obj) -> Optional[UndoState]:
        """捕获当前状态"""
        try:
            skin_mod = None
            for mod in mesh_obj.modifiers:
                if rt.classOf(mod) == rt.Skin:
                    skin_mod = mod
                    break
            
            if not skin_mod:
                return None
            
            num_bones = rt.skinOps.getNumberBones(skin_mod)
            bone_names = []
            for i in range(1, num_bones + 1):
                name = rt.skinOps.getBoneName(skin_mod, i, 0)
                bone_names.append(name)
            
            num_verts = rt.skinOps.getNumberVertices(skin_mod)
            weights = []
            
            for v_idx in range(1, num_verts + 1):
                vert_weights = []
                num_weights = rt.skinOps.getVertexWeightCount(skin_mod, v_idx)
                
                for w_idx in range(1, num_weights + 1):
                    bone_id = rt.skinOps.getVertexWeightBoneID(skin_mod, v_idx, w_idx)
                    weight = rt.skinOps.getVertexWeight(skin_mod, v_idx, w_idx)
                    vert_weights.append((bone_id, weight))
                
                weights.append(vert_weights)
            
            return UndoState(
                timestamp=datetime.now(),
                description="当前状态",
                mesh_name=mesh_obj.name,
                weights=weights,
                bone_names=bone_names
            )
            
        except Exception as e:
            print(f"[UndoManager] 捕获状态失败: {e}")
            return None
    
    def _restore_state(self, mesh_obj, state: UndoState):
        """恢复状态"""
        skin_mod = None
        for mod in mesh_obj.modifiers:
            if rt.classOf(mod) == rt.Skin:
                skin_mod = mod
                break
        
        if not skin_mod:
            return
        
        # 建立骨骼名称到ID的映射
        bone_name_to_id = {}
        num_bones = rt.skinOps.getNumberBones(skin_mod)
        for i in range(1, num_bones + 1):
            name = rt.skinOps.getBoneName(skin_mod, i, 0)
            bone_name_to_id[name] = i
        
        # 建立状态骨骼ID到当前骨骼ID的映射
        state_to_current = {}
        for i, name in enumerate(state.bone_names):
            if name in bone_name_to_id:
                state_to_current[i + 1] = bone_name_to_id[name]
        
        # 恢复权重
        for v_idx, vert_weights in enumerate(state.weights):
            bone_ids = []
            weights = []
            
            for bone_id, weight in vert_weights:
                if bone_id in state_to_current:
                    bone_ids.append(state_to_current[bone_id])
                    weights.append(weight)
            
            if bone_ids and weights:
                bone_array = rt.Array()
                weight_array = rt.Array()
                
                for bid, w in zip(bone_ids, weights):
                    rt.append(bone_array, bid)
                    rt.append(weight_array, w)
                
                rt.skinOps.setVertexWeights(skin_mod, v_idx + 1, bone_array, weight_array)
    
    def can_undo(self) -> bool:
        """检查是否可以撤销"""
        return self._enabled and len(self.undo_stack) > 0
    
    def can_redo(self) -> bool:
        """检查是否可以重做"""
        return self._enabled and len(self.redo_stack) > 0
    
    def get_undo_description(self) -> str:
        """获取下一个撤销操作的描述"""
        if self.undo_stack:
            return self.undo_stack[-1].description
        return ""
    
    def get_redo_description(self) -> str:
        """获取下一个重做操作的描述"""
        if self.redo_stack:
            return self.redo_stack[-1].description
        return ""
    
    def clear(self):
        """清空所有历史记录"""
        self.undo_stack.clear()
        self.redo_stack.clear()
    
    def get_history(self) -> List[str]:
        """获取历史记录列表"""
        history = []
        for state in self.undo_stack:
            history.append(f"{state.timestamp.strftime('%H:%M:%S')} - {state.description}")
        return history


# 全局撤销管理器实例
_undo_manager: Optional[UndoManager] = None

def get_undo_manager() -> UndoManager:
    """获取全局撤销管理器"""
    global _undo_manager
    if _undo_manager is None:
        _undo_manager = UndoManager()
    return _undo_manager
