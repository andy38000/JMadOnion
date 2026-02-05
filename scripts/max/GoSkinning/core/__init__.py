# -*- coding: utf-8 -*-
"""
GoSkinning 核心模块
包含蒙皮引擎和权重计算算法
"""

from .skinning_engine import SkinningEngine
from .weight_calculator import WeightCalculator
from .bone_utils import BoneUtils
from .mesh_utils import MeshUtils

# ML推理模块
try:
    from .ml_inference import MLSkinningInference, get_inference, ml_auto_skin
    ML_AVAILABLE = True
except ImportError:
    ML_AVAILABLE = False

__all__ = ['SkinningEngine', 'WeightCalculator', 'BoneUtils', 'MeshUtils', 
           'MLSkinningInference', 'get_inference', 'ml_auto_skin']
