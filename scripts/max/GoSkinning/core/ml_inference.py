# -*- coding: utf-8 -*-
"""
ML模型推理模块
用于加载训练好的模型进行自动蒙皮
"""

import os
import numpy as np
from typing import List, Tuple, Optional, Dict

# 尝试导入PyTorch
try:
    import torch
    import torch.nn.functional as F
    TORCH_AVAILABLE = True
except ImportError:
    TORCH_AVAILABLE = False
    print("[MLInference] PyTorch not available")

# 尝试导入3ds Max
try:
    import pymxs
    from pymxs import runtime as rt
    MAX_AVAILABLE = True
except ImportError:
    MAX_AVAILABLE = False


class MLSkinningInference:
    """
    ML蒙皮推理类
    加载训练好的模型进行自动蒙皮权重预测
    """
    
    # 可用的模型列表
    AVAILABLE_MODELS = {
        "general-v4.5": "general_v45.pth",
        "general-v4.0": "general_v40.pth", 
        "local-v3": "local_v3.pth",
        "face-v0": "face_v0.pth",
        "my_model_v1": "my_model_v1.pth",  # 自定义模型
    }
    
    def __init__(self):
        self.model = None
        self.model_name = None
        self.device = 'cpu'
        self.models_dir = self._get_models_dir()
        
    def _get_models_dir(self) -> str:
        """获取模型目录"""
        # 当前文件所在目录的上级的ml/models
        current_dir = os.path.dirname(os.path.abspath(__file__))
        models_dir = os.path.join(current_dir, '..', 'ml', 'models')
        return os.path.abspath(models_dir)
    
    def get_available_models(self) -> List[str]:
        """获取可用的模型列表"""
        available = []
        
        for name, filename in self.AVAILABLE_MODELS.items():
            filepath = os.path.join(self.models_dir, filename)
            if os.path.exists(filepath):
                available.append(name)
        
        # 扫描目录中的其他.pth文件
        if os.path.exists(self.models_dir):
            for f in os.listdir(self.models_dir):
                if f.endswith('.pth') or f.endswith('.pt'):
                    name = f.replace('.pth', '').replace('.pt', '')
                    if name not in available:
                        available.append(name)
        
        # 如果没有任何模型，添加默认选项
        if not available:
            available = ["general-v4.5 (需要训练)"]
        
        return available
    
    def load_model(self, model_name: str) -> bool:
        """
        加载指定的模型
        
        Args:
            model_name: 模型名称
            
        Returns:
            是否成功
        """
        if not TORCH_AVAILABLE:
            print("[MLInference] PyTorch not installed!")
            return False
        
        # 查找模型文件
        model_path = None
        
        # 先在预定义列表中查找
        if model_name in self.AVAILABLE_MODELS:
            model_path = os.path.join(self.models_dir, self.AVAILABLE_MODELS[model_name])
        
        # 直接查找文件名
        if not model_path or not os.path.exists(model_path):
            for ext in ['.pth', '.pt', '']:
                test_path = os.path.join(self.models_dir, model_name + ext)
                if os.path.exists(test_path):
                    model_path = test_path
                    break
        
        if not model_path or not os.path.exists(model_path):
            print(f"[MLInference] Model not found: {model_name}")
            print(f"[MLInference] Searched in: {self.models_dir}")
            return False
        
        try:
            print(f"[MLInference] Loading model: {model_path}")
            
            # 加载模型
            checkpoint = torch.load(model_path, map_location=self.device)
            
            # 检查是否是完整checkpoint还是只有state_dict
            if isinstance(checkpoint, dict) and 'model_state_dict' in checkpoint:
                # 需要创建模型然后加载权重
                from ..ml.models.skinning_net import create_skinning_model
                
                # 根据模型名称确定类型
                if 'local' in model_name.lower():
                    model_type = 'local'
                elif 'face' in model_name.lower():
                    model_type = 'face'
                else:
                    model_type = 'general'
                
                self.model = create_skinning_model(model_type)
                self.model.load_state_dict(checkpoint['model_state_dict'])
            else:
                # 直接是模型或state_dict
                if hasattr(checkpoint, 'eval'):
                    # 是完整模型
                    self.model = checkpoint
                else:
                    # 是state_dict，需要创建模型
                    from ..ml.models.skinning_net import create_skinning_model
                    self.model = create_skinning_model('general')
                    self.model.load_state_dict(checkpoint)
            
            self.model.eval()
            self.model_name = model_name
            
            print(f"[MLInference] Model loaded successfully: {model_name}")
            return True
            
        except Exception as e:
            print(f"[MLInference] Failed to load model: {e}")
            import traceback
            traceback.print_exc()
            return False
    
    def predict_weights(self, 
                        vertices: np.ndarray,
                        normals: np.ndarray,
                        bone_heads: np.ndarray,
                        bone_tails: np.ndarray,
                        max_influences: int = 4) -> np.ndarray:
        """
        预测蒙皮权重
        
        Args:
            vertices: (N, 3) 顶点位置
            normals: (N, 3) 顶点法线
            bone_heads: (num_bones, 3) 骨骼头部位置
            bone_tails: (num_bones, 3) 骨骼尾部位置
            max_influences: 每个顶点最大影响骨骼数
            
        Returns:
            (N, num_bones) 权重矩阵
        """
        if self.model is None:
            print("[MLInference] No model loaded!")
            return None
        
        if not TORCH_AVAILABLE:
            return None
        
        try:
            # 归一化数据
            all_points = np.concatenate([vertices, bone_heads, bone_tails], axis=0)
            center = (all_points.max(axis=0) + all_points.min(axis=0)) / 2
            scale = (all_points.max(axis=0) - all_points.min(axis=0)).max()
            
            if scale > 0:
                vertices_norm = (vertices - center) / scale
                bone_heads_norm = (bone_heads - center) / scale
                bone_tails_norm = (bone_tails - center) / scale
            else:
                vertices_norm = vertices
                bone_heads_norm = bone_heads
                bone_tails_norm = bone_tails
            
            # 归一化法线
            norm_lengths = np.linalg.norm(normals, axis=1, keepdims=True)
            norm_lengths = np.maximum(norm_lengths, 1e-8)
            normals_norm = normals / norm_lengths
            
            # 转换为张量
            vertex_pos = torch.tensor(vertices_norm, dtype=torch.float32).unsqueeze(0)
            vertex_norm = torch.tensor(normals_norm, dtype=torch.float32).unsqueeze(0)
            bone_h = torch.tensor(bone_heads_norm, dtype=torch.float32).unsqueeze(0)
            bone_t = torch.tensor(bone_tails_norm, dtype=torch.float32).unsqueeze(0)
            
            # 构建特征
            vertex_features = torch.cat([vertex_pos, vertex_norm], dim=-1)
            
            bone_dir = bone_t - bone_h
            bone_dir = bone_dir / (bone_dir.norm(dim=-1, keepdim=True) + 1e-8)
            bone_features = torch.cat([bone_h, bone_t, bone_dir], dim=-1)
            
            # 计算距离
            distances = torch.cdist(vertex_pos, bone_h)
            
            # 推理
            with torch.no_grad():
                weights, _ = self.model(vertex_features, bone_features, distances)
            
            weights = weights.squeeze(0).numpy()
            
            # 后处理：保留top-k并归一化
            num_verts, num_bones = weights.shape
            processed_weights = np.zeros_like(weights)
            
            for i in range(num_verts):
                w = weights[i]
                top_indices = np.argsort(w)[::-1][:max_influences]
                top_weights = w[top_indices]
                
                # 过滤小权重
                mask = top_weights > 0.01
                top_indices = top_indices[mask]
                top_weights = top_weights[mask]
                
                if len(top_weights) > 0:
                    top_weights = top_weights / top_weights.sum()
                    processed_weights[i, top_indices] = top_weights
            
            return processed_weights
            
        except Exception as e:
            print(f"[MLInference] Prediction failed: {e}")
            import traceback
            traceback.print_exc()
            return None


# 全局实例
_inference_instance: Optional[MLSkinningInference] = None

def get_inference() -> MLSkinningInference:
    """获取推理实例"""
    global _inference_instance
    if _inference_instance is None:
        _inference_instance = MLSkinningInference()
    return _inference_instance


def ml_auto_skin(mesh_obj, bones: List, model_name: str = "general-v4.5", 
                 max_influences: int = 4, progress_callback=None) -> bool:
    """
    使用ML模型自动蒙皮
    
    Args:
        mesh_obj: 3ds Max网格对象
        bones: 骨骼列表
        model_name: 模型名称
        max_influences: 最大影响骨骼数
        progress_callback: 进度回调函数
        
    Returns:
        是否成功
    """
    if not MAX_AVAILABLE:
        print("[MLSkin] 3ds Max not available")
        return False
    
    if not TORCH_AVAILABLE:
        print("[MLSkin] PyTorch not available")
        return False
    
    inference = get_inference()
    
    # 加载模型
    if progress_callback:
        progress_callback(0.1, "加载模型...")
    
    if not inference.load_model(model_name):
        print(f"[MLSkin] Failed to load model: {model_name}")
        return False
    
    # 获取顶点数据
    if progress_callback:
        progress_callback(0.2, "获取顶点数据...")
    
    vertices = []
    normals = []
    
    num_verts = rt.polyOp.getNumVerts(mesh_obj)
    for i in range(1, num_verts + 1):
        pos = rt.polyOp.getVert(mesh_obj, i)
        vertices.append([float(pos.x), float(pos.y), float(pos.z)])
        
        try:
            norm = rt.polyOp.getVertNormal(mesh_obj, i)
            normals.append([float(norm.x), float(norm.y), float(norm.z)])
        except:
            normals.append([0.0, 1.0, 0.0])
    
    vertices = np.array(vertices, dtype=np.float32)
    normals = np.array(normals, dtype=np.float32)
    
    # 获取骨骼数据
    if progress_callback:
        progress_callback(0.3, "获取骨骼数据...")
    
    bone_heads = []
    bone_tails = []
    
    for bone in bones:
        pos = bone.transform.pos
        head = [float(pos.x), float(pos.y), float(pos.z)]
        
        length = 10.0
        try:
            if hasattr(bone, 'length') and bone.length > 0:
                length = float(bone.length)
        except:
            pass
        
        try:
            axis = rt.normalize(bone.transform.row3)
            tail = [head[0] + float(axis.x) * length,
                    head[1] + float(axis.y) * length,
                    head[2] + float(axis.z) * length]
        except:
            tail = [head[0], head[1] + length, head[2]]
        
        bone_heads.append(head)
        bone_tails.append(tail)
    
    bone_heads = np.array(bone_heads, dtype=np.float32)
    bone_tails = np.array(bone_tails, dtype=np.float32)
    
    # 预测权重
    if progress_callback:
        progress_callback(0.5, "预测权重...")
    
    weights = inference.predict_weights(vertices, normals, bone_heads, bone_tails, max_influences)
    
    if weights is None:
        return False
    
    # 应用Skin修改器
    if progress_callback:
        progress_callback(0.7, "应用蒙皮...")
    
    # 添加Skin修改器
    skin_mod = rt.Skin()
    rt.addModifier(mesh_obj, skin_mod)
    
    # 添加骨骼
    for bone in bones:
        rt.skinOps.addBone(skin_mod, bone, 0)
    
    rt.completeRedraw()
    
    # 应用权重
    num_verts = weights.shape[0]
    for v_idx in range(num_verts):
        if progress_callback and v_idx % 500 == 0:
            prog = 0.7 + 0.25 * (v_idx / num_verts)
            progress_callback(prog, f"应用权重 {v_idx}/{num_verts}...")
        
        vert_weights = weights[v_idx]
        
        # 获取非零权重
        nonzero = np.where(vert_weights > 0.001)[0]
        
        if len(nonzero) == 0:
            continue
        
        bone_array = rt.Array()
        weight_array = rt.Array()
        
        for bi in nonzero:
            rt.append(bone_array, int(bi) + 1)
            rt.append(weight_array, float(vert_weights[bi]))
        
        try:
            rt.skinOps.setVertexWeights(skin_mod, v_idx + 1, bone_array, weight_array)
        except:
            pass
    
    if progress_callback:
        progress_callback(1.0, "完成!")
    
    return True
