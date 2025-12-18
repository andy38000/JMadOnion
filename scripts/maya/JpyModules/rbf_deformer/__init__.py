# -*- coding: utf-8 -*-
"""
RBF Deformer Package
RBF变形工具包

特性:
- 8种RBF核函数
- OpenMaya 2.0 高性能API
- 4种智能采样方法
- 进度条和撤销支持
- 预设保存/加载
- 预览模式
- BlendShape创建
- 边界顶点锁定
- 变形分析工具

Author: Enhanced Version
Version: 2.0.0
"""

from .rbf_deformer_v2 import (
    create_ui,
    RBFDeformer,
    RBF_METHODS,
    SAMPLING_METHODS,
    MeshVertexOperator,
    VertexSampler,
    BoundaryDetector,
    PresetManager,
    UICallbacks,
)

from .utils import (
    get_mesh_info,
    compare_meshes,
    estimate_optimal_radius,
    estimate_optimal_points,
    auto_detect_parameters,
    create_deformation_heatmap,
    batch_export_deformed_meshes,
    transfer_uv_with_deformation,
    DeformationAnalyzer,
)

from .launcher import run, run_with_auto_params

__version__ = "2.0.0"
__all__ = [
    # 主要接口
    'create_ui',
    'run',
    'run_with_auto_params',
    
    # 核心类
    'RBFDeformer',
    'MeshVertexOperator',
    'VertexSampler',
    'BoundaryDetector',
    'PresetManager',
    
    # 工具函数
    'get_mesh_info',
    'compare_meshes',
    'estimate_optimal_radius',
    'estimate_optimal_points',
    'auto_detect_parameters',
    'create_deformation_heatmap',
    'batch_export_deformed_meshes',
    'transfer_uv_with_deformation',
    'DeformationAnalyzer',
    
    # 常量
    'RBF_METHODS',
    'SAMPLING_METHODS',
]
