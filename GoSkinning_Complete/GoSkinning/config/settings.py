# -*- coding: utf-8 -*-
"""
GoSkinning 配置管理
"""

import json
import os
from typing import Optional, Dict, Any
from dataclasses import dataclass, asdict, field


@dataclass
class AlgorithmSettings:
    """算法设置"""
    # 通用设置
    max_influences: int = 4
    weight_threshold: float = 0.01
    normalize_weights: bool = True
    smooth_iterations: int = 2
    
    # 包络体设置
    use_envelope: bool = True
    envelope_falloff: float = 1.0
    inner_radius_scale: float = 1.0
    outer_radius_scale: float = 1.0
    
    # 热扩散设置
    heat_iterations: int = 50
    heat_conductivity: float = 1.0
    
    # 测地距离设置
    use_geodesic: bool = False
    geodesic_falloff: float = 2.0


@dataclass
class UISettings:
    """界面设置"""
    window_width: int = 380
    window_height: int = 700
    show_heatmap: bool = False
    auto_update_preview: bool = True
    language: str = "zh_CN"
    theme: str = "dark"


@dataclass
class IOSettings:
    """输入输出设置"""
    default_export_path: str = ""
    export_format: str = "json"
    auto_backup: bool = True
    backup_count: int = 5


@dataclass 
class Settings:
    """GoSkinning 全局设置"""
    algorithm: AlgorithmSettings = field(default_factory=AlgorithmSettings)
    ui: UISettings = field(default_factory=UISettings)
    io: IOSettings = field(default_factory=IOSettings)
    
    # 最近使用的模型
    recent_models: list = field(default_factory=list)
    
    # 自定义预设
    presets: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            'algorithm': asdict(self.algorithm),
            'ui': asdict(self.ui),
            'io': asdict(self.io),
            'recent_models': self.recent_models,
            'presets': self.presets
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Settings':
        """从字典创建"""
        settings = cls()
        
        if 'algorithm' in data:
            settings.algorithm = AlgorithmSettings(**data['algorithm'])
        if 'ui' in data:
            settings.ui = UISettings(**data['ui'])
        if 'io' in data:
            settings.io = IOSettings(**data['io'])
        if 'recent_models' in data:
            settings.recent_models = data['recent_models']
        if 'presets' in data:
            settings.presets = data['presets']
        
        return settings
    
    def add_preset(self, name: str, preset_data: Dict[str, Any]):
        """添加预设"""
        self.presets[name] = preset_data
    
    def remove_preset(self, name: str):
        """移除预设"""
        if name in self.presets:
            del self.presets[name]
    
    def apply_preset(self, name: str):
        """应用预设"""
        if name not in self.presets:
            return False
        
        preset = self.presets[name]
        
        # 应用算法设置
        if 'algorithm' in preset:
            for key, value in preset['algorithm'].items():
                if hasattr(self.algorithm, key):
                    setattr(self.algorithm, key, value)
        
        return True
    
    def add_recent_model(self, model_name: str, max_count: int = 10):
        """添加到最近模型列表"""
        if model_name in self.recent_models:
            self.recent_models.remove(model_name)
        
        self.recent_models.insert(0, model_name)
        
        # 限制数量
        while len(self.recent_models) > max_count:
            self.recent_models.pop()


# 配置文件路径
def _get_config_path() -> str:
    """获取配置文件路径"""
    # 尝试获取3ds Max用户目录
    try:
        import pymxs
        from pymxs import runtime as rt
        user_dir = rt.getDir(rt.Name("userScripts"))
        return os.path.join(user_dir, "GoSkinning", "settings.json")
    except:
        # 使用用户目录
        home = os.path.expanduser("~")
        return os.path.join(home, ".goskinning", "settings.json")


# 全局设置实例
_settings: Optional[Settings] = None


def get_settings() -> Settings:
    """获取全局设置"""
    global _settings
    if _settings is None:
        _settings = load_settings()
    return _settings


def save_settings(settings: Optional[Settings] = None) -> bool:
    """
    保存设置到文件
    
    Args:
        settings: 要保存的设置,如果为None则保存全局设置
        
    Returns:
        是否成功
    """
    global _settings
    
    if settings is None:
        settings = _settings
    
    if settings is None:
        return False
    
    try:
        config_path = _get_config_path()
        
        # 确保目录存在
        config_dir = os.path.dirname(config_path)
        if not os.path.exists(config_dir):
            os.makedirs(config_dir)
        
        # 保存到文件
        with open(config_path, 'w', encoding='utf-8') as f:
            json.dump(settings.to_dict(), f, indent=2, ensure_ascii=False)
        
        print(f"[Settings] 配置已保存: {config_path}")
        return True
        
    except Exception as e:
        print(f"[Settings] 保存配置失败: {e}")
        return False


def load_settings() -> Settings:
    """
    从文件加载设置
    
    Returns:
        Settings实例
    """
    try:
        config_path = _get_config_path()
        
        if os.path.exists(config_path):
            with open(config_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            settings = Settings.from_dict(data)
            print(f"[Settings] 配置已加载: {config_path}")
            return settings
        
    except Exception as e:
        print(f"[Settings] 加载配置失败: {e}")
    
    # 返回默认设置
    return Settings()


def reset_settings() -> Settings:
    """重置为默认设置"""
    global _settings
    _settings = Settings()
    save_settings(_settings)
    return _settings


# 预定义的预设
DEFAULT_PRESETS = {
    "快速": {
        "algorithm": {
            "max_influences": 2,
            "smooth_iterations": 1,
            "use_envelope": True
        }
    },
    "标准": {
        "algorithm": {
            "max_influences": 4,
            "smooth_iterations": 2,
            "use_envelope": True
        }
    },
    "高质量": {
        "algorithm": {
            "max_influences": 6,
            "smooth_iterations": 5,
            "use_envelope": True,
            "use_geodesic": True
        }
    },
    "面部专用": {
        "algorithm": {
            "max_influences": 8,
            "smooth_iterations": 3,
            "weight_threshold": 0.005,
            "envelope_falloff": 0.5
        }
    }
}


def init_default_presets():
    """初始化默认预设"""
    settings = get_settings()
    
    for name, preset in DEFAULT_PRESETS.items():
        if name not in settings.presets:
            settings.add_preset(name, preset)
    
    save_settings(settings)
