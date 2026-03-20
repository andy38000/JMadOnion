# -*- coding: utf-8 -*-
"""
GoSkinning Maya - 完整版自动蒙皮插件
功能与 3ds Max 版本一致

功能模块:
    - 全局蒙皮: 对整个模型进行自动蒙皮
    - 局部蒙皮: 针对选中顶点进行局部权重计算
    - 裙摆蒙皮: 裙子等布料的代理蒙皮
    - 面部蒙皮: 面部骨骼专用蒙皮
"""

import os
import sys
import math
import maya.cmds as cmds
import maya.mel as mel
import numpy as np

# PyTorch
try:
    import torch
    TORCH_AVAILABLE = True
except ImportError:
    TORCH_AVAILABLE = False

# 脚本路径
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
MODEL_DIR = os.path.join(SCRIPT_DIR, 'models')
ML_TRAINING_DIR = os.path.join(os.path.dirname(SCRIPT_DIR), 'ML_Training')

# 添加训练代码路径
if ML_TRAINING_DIR not in sys.path:
    sys.path.insert(0, ML_TRAINING_DIR)


class GoSkinningMaya:
    """GoSkinning Maya 主类"""
    
    WINDOW_NAME = 'goSkinningMayaWindow'
    WINDOW_TITLE = 'GoSkinning Maya v1.0'
    
    def __init__(self):
        self.model = None
        self.model_name = None
        
    def get_available_models(self):
        """获取可用的模型列表"""
        models = []
        
        # 默认算法
        models.append('distance-based (距离算法)')
        models.append('heat-diffusion (热扩散)')
        
        # 扫描模型文件夹
        if os.path.exists(MODEL_DIR):
            for f in os.listdir(MODEL_DIR):
                if f.endswith('.pth') or f.endswith('.pt'):
                    name = f.replace('.pth', '').replace('.pt', '')
                    models.append(name + ' (ML)')
        
        if not any('ML' in m for m in models):
            models.append('-- 无ML模型,请先训练 --')
        
        return models
    
    def load_ml_model(self, model_name):
        """加载ML模型"""
        if not TORCH_AVAILABLE:
            cmds.warning('PyTorch 未安装!')
            return None
        
        model_file = model_name.replace(' (ML)', '') + '.pth'
        model_path = os.path.join(MODEL_DIR, model_file)
        
        if not os.path.exists(model_path):
            model_file = model_name.replace(' (ML)', '') + '.pt'
            model_path = os.path.join(MODEL_DIR, model_file)
        
        if not os.path.exists(model_path):
            cmds.warning('模型文件不存在: ' + model_path)
            return None
        
        try:
            from models.skinning_net import create_skinning_model
            
            model = create_skinning_model('general')
            checkpoint = torch.load(model_path, map_location='cpu')
            
            if 'model_state_dict' in checkpoint:
                model.load_state_dict(checkpoint['model_state_dict'])
            else:
                model.load_state_dict(checkpoint)
            
            model.eval()
            print('[GoSkinning] 模型已加载: ' + model_name)
            return model
            
        except Exception as e:
            cmds.warning('加载模型失败: ' + str(e))
            return None
    
    def get_mesh_data(self, mesh):
        """获取网格顶点数据"""
        num_verts = cmds.polyEvaluate(mesh, vertex=True)
        
        vertices = []
        normals = []
        
        for i in range(num_verts):
            pos = cmds.xform('{}.vtx[{}]'.format(mesh, i), q=True, ws=True, t=True)
            vertices.append(pos)
            
            try:
                norm = cmds.polyNormalPerVertex('{}.vtx[{}]'.format(mesh, i), q=True, xyz=True)
                normals.append(norm[:3] if norm else [0, 1, 0])
            except:
                normals.append([0, 1, 0])
        
        return np.array(vertices, dtype=np.float32), np.array(normals, dtype=np.float32)
    
    def get_joint_data(self, joints):
        """获取骨骼数据"""
        bone_heads = []
        bone_tails = []
        
        for joint in joints:
            head = cmds.xform(joint, q=True, ws=True, t=True)
            
            children = cmds.listRelatives(joint, children=True, type='joint')
            if children:
                tail = cmds.xform(children[0], q=True, ws=True, t=True)
            else:
                tail = [head[0] + 10, head[1], head[2]]
            
            bone_heads.append(head)
            bone_tails.append(tail)
        
        return np.array(bone_heads, dtype=np.float32), np.array(bone_tails, dtype=np.float32)
    
    def predict_ml_weights(self, model, vertices, normals, bone_heads, bone_tails, max_influences=4):
        """ML模型预测权重"""
        # 归一化
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
        
        # 法线归一化
        norm_len = np.linalg.norm(normals, axis=1, keepdims=True)
        norm_len = np.maximum(norm_len, 1e-8)
        normals_norm = normals / norm_len
        
        # 转张量
        v_pos = torch.tensor(vertices_norm, dtype=torch.float32).unsqueeze(0)
        v_norm = torch.tensor(normals_norm, dtype=torch.float32).unsqueeze(0)
        b_h = torch.tensor(bone_heads_norm, dtype=torch.float32).unsqueeze(0)
        b_t = torch.tensor(bone_tails_norm, dtype=torch.float32).unsqueeze(0)
        
        # 特征
        vertex_features = torch.cat([v_pos, v_norm], dim=-1)
        bone_dir = b_t - b_h
        bone_dir = bone_dir / (bone_dir.norm(dim=-1, keepdim=True) + 1e-8)
        bone_features = torch.cat([b_h, b_t, bone_dir], dim=-1)
        distances = torch.cdist(v_pos, b_h)
        
        # 推理
        with torch.no_grad():
            weights, _ = model(vertex_features, bone_features, distances)
        
        weights = weights.squeeze(0).numpy()
        
        # 后处理
        num_verts, num_bones = weights.shape
        result = np.zeros_like(weights)
        
        for i in range(num_verts):
            w = weights[i]
            top_idx = np.argsort(w)[::-1][:max_influences]
            top_w = w[top_idx]
            mask = top_w > 0.01
            top_idx = top_idx[mask]
            top_w = top_w[mask]
            if len(top_w) > 0:
                top_w = top_w / top_w.sum()
                result[i, top_idx] = top_w
        
        return result
    
    def calculate_distance_weights(self, vertices, bone_heads, bone_tails, max_influences=4):
        """距离算法计算权重"""
        num_verts = len(vertices)
        num_bones = len(bone_heads)
        weights = np.zeros((num_verts, num_bones), dtype=np.float32)
        
        # 显示进度条
        cmds.progressWindow(title='计算权重',
                           progress=0,
                           status='计算距离权重: 0/{}'.format(num_verts),
                           isInterruptable=True,
                           maxValue=num_verts)
        
        try:
            for v_idx in range(num_verts):
                # 检查取消
                if cmds.progressWindow(query=True, isCancelled=True):
                    break
                
                # 更新进度
                if v_idx % 200 == 0:
                    cmds.progressWindow(edit=True,
                                       progress=v_idx,
                                       status='计算距离权重: {}/{}'.format(v_idx, num_verts))
                
                pos = vertices[v_idx]
                distances = []
                
                for b_idx in range(num_bones):
                    head = bone_heads[b_idx]
                    tail = bone_tails[b_idx]
                    
                    # 点到线段距离
                    d = self.point_to_segment_distance(pos, head, tail)
                    distances.append((d, b_idx))
                
                distances.sort()
                closest = distances[:max_influences]
                
                total = 0
                w_list = []
                for dist, b_idx in closest:
                    w = 1.0 / (dist + 0.001)
                    w_list.append((b_idx, w))
                    total += w
                
                if total > 0:
                    for b_idx, w in w_list:
                        weights[v_idx, b_idx] = w / total
        finally:
            cmds.progressWindow(endProgress=True)
        
        return weights
    
    def point_to_segment_distance(self, point, seg_start, seg_end):
        """计算点到线段的距离"""
        p = np.array(point)
        a = np.array(seg_start)
        b = np.array(seg_end)
        
        ab = b - a
        ap = p - a
        
        ab_len_sq = np.dot(ab, ab)
        if ab_len_sq < 1e-8:
            return np.linalg.norm(ap)
        
        t = max(0, min(1, np.dot(ap, ab) / ab_len_sq))
        closest = a + t * ab
        
        return np.linalg.norm(p - closest)
    
    def apply_weights(self, mesh, joints, weights):
        """应用权重到网格"""
        # 删除已有skinCluster
        history = cmds.listHistory(mesh, pruneDagObjects=True) or []
        for sc in cmds.ls(history, type='skinCluster') or []:
            cmds.delete(sc)
        
        # 创建skinCluster
        skin_cluster = cmds.skinCluster(joints, mesh,
                                         toSelectedBones=True,
                                         bindMethod=0,
                                         skinMethod=0,
                                         normalizeWeights=1)[0]
        
        num_verts = weights.shape[0]
        
        # 显示进度条
        cmds.progressWindow(title='GoSkinning',
                           progress=0,
                           status='应用权重: 0/{}'.format(num_verts),
                           isInterruptable=True,
                           maxValue=num_verts)
        
        try:
            for v_idx in range(num_verts):
                # 检查是否取消
                if cmds.progressWindow(query=True, isCancelled=True):
                    print('[GoSkinning] 用户取消操作')
                    break
                
                # 更新进度条
                if v_idx % 100 == 0:
                    cmds.progressWindow(edit=True, 
                                       progress=v_idx,
                                       status='应用权重: {}/{}'.format(v_idx, num_verts))
                
                vert_weights = weights[v_idx]
                transform_value = []
                
                for b_idx in range(len(joints)):
                    w = float(vert_weights[b_idx])  # 转换为Python float
                    if w > 0.001:
                        transform_value.append((joints[b_idx], w))
                
                if transform_value:
                    cmds.skinPercent(skin_cluster, '{}.vtx[{}]'.format(mesh, v_idx),
                                    transformValue=transform_value)
        finally:
            # 关闭进度条
            cmds.progressWindow(endProgress=True)
        
        return skin_cluster
    
    def do_global_skin(self, mesh, root_joint, model_name, max_influences, merge_mesh):
        """执行全局蒙皮（从根骨骼获取所有骨骼）"""
        # 获取所有骨骼
        all_joints = cmds.listRelatives(root_joint, allDescendents=True, type='joint') or []
        all_joints.append(root_joint)
        all_joints = sorted(list(set(all_joints)))
        
        return self.do_global_skin_with_joints(mesh, all_joints, model_name, max_influences, merge_mesh)
    
    def do_global_skin_with_joints(self, mesh, all_joints, model_name, max_influences, merge_mesh):
        """执行全局蒙皮（指定骨骼列表）"""
        print('[GoSkinning] ========== 全局蒙皮 ==========')
        print('[GoSkinning] 网格: ' + mesh)
        print('[GoSkinning] 算法: ' + model_name)
        print('[GoSkinning] 骨骼数: ' + str(len(all_joints)))
        
        # 显示进度条 - 准备阶段
        cmds.progressWindow(title='GoSkinning - ' + mesh,
                           progress=0,
                           status='准备数据...',
                           isInterruptable=False,
                           maxValue=100)
        
        try:
            # 获取顶点数据
            cmds.progressWindow(edit=True, progress=10, status='获取顶点数据...')
            print('[GoSkinning] 获取顶点数据...')
            vertices, normals = self.get_mesh_data(mesh)
            print('[GoSkinning] 顶点数: ' + str(len(vertices)))
            
            # 获取骨骼数据
            cmds.progressWindow(edit=True, progress=20, status='获取骨骼数据...')
            print('[GoSkinning] 获取骨骼数据...')
            bone_heads, bone_tails = self.get_joint_data(all_joints)
            
            # 计算权重
            cmds.progressWindow(edit=True, progress=30, status='计算权重...')
            if '(ML)' in model_name:
                print('[GoSkinning] 使用ML模型计算权重...')
                cmds.progressWindow(edit=True, status='加载ML模型...')
                model = self.load_ml_model(model_name)
                if model is None:
                    cmds.warning('ML模型加载失败,切换到距离算法')
                    cmds.progressWindow(edit=True, progress=40, status='计算距离权重...')
                    weights = self.calculate_distance_weights(vertices, bone_heads, bone_tails, max_influences)
                else:
                    cmds.progressWindow(edit=True, progress=40, status='ML预测权重...')
                    weights = self.predict_ml_weights(model, vertices, normals, bone_heads, bone_tails, max_influences)
            else:
                print('[GoSkinning] 使用距离算法计算权重...')
                cmds.progressWindow(edit=True, progress=40, status='计算距离权重...')
                weights = self.calculate_distance_weights(vertices, bone_heads, bone_tails, max_influences)
            
            cmds.progressWindow(edit=True, progress=60, status='权重计算完成')
            
        finally:
            cmds.progressWindow(endProgress=True)
        
        # 应用权重 (有自己的进度条)
        print('[GoSkinning] 应用权重...')
        self.apply_weights(mesh, all_joints, weights)
        
        print('[GoSkinning] ========== 完成 ==========')
        cmds.select(mesh)
        
        return True
    
    def show_ui(self):
        """显示UI"""
        if cmds.window(self.WINDOW_NAME, exists=True):
            cmds.deleteUI(self.WINDOW_NAME)
        
        window = cmds.window(self.WINDOW_NAME, title=self.WINDOW_TITLE, 
                            widthHeight=(450, 500), sizeable=True)
        
        # 主布局
        main_layout = cmds.columnLayout(adjustableColumn=True)
        
        # 标题
        cmds.text(label='GoSkinning Maya', font='boldLabelFont', height=35, 
                 backgroundColor=[0.2, 0.2, 0.2])
        cmds.separator(height=5, style='none')
        
        # Tab布局
        tabs = cmds.tabLayout()
        
        # ========== 全局蒙皮 Tab ==========
        global_tab = cmds.columnLayout(adjustableColumn=True, rowSpacing=8, 
                                       columnOffset=['both', 10])
        
        cmds.separator(height=10, style='none')
        cmds.text(label='全局蒙皮 - 对整个模型自动计算权重', align='left')
        cmds.separator(height=10)
        
        # 算法模型
        cmds.text(label='算法模型:', align='left')
        self.model_menu = cmds.optionMenu(width=420)
        for m in self.get_available_models():
            cmds.menuItem(label=m)
        
        cmds.separator(height=5, style='none')
        
        # 合并网格选项
        self.merge_mesh_cb = cmds.checkBox(label='合并网格', value=False)
        
        cmds.separator(height=15)
        
        # 智能获取按钮
        cmds.button(label='智能获取 (同时选择网格和骨骼后点击)', height=30,
                   backgroundColor=[0.25, 0.35, 0.45],
                   command=lambda x: self.smart_get_selection())
        
        cmds.separator(height=10, style='none')
        
        # 网格选择
        cmds.text(label='目标网格:', align='left')
        mesh_row = cmds.rowLayout(numberOfColumns=2, columnWidth2=(340, 70))
        self.mesh_field = cmds.textField(width=335)
        cmds.button(label='获取', width=65, 
                   command=lambda x: self.get_selected_mesh())
        cmds.setParent('..')
        
        cmds.separator(height=5, style='none')
        
        # 骨骼选择
        cmds.text(label='根骨骼:', align='left')
        joint_row = cmds.rowLayout(numberOfColumns=2, columnWidth2=(340, 70))
        self.joint_field = cmds.textField(width=335)
        cmds.button(label='获取', width=65,
                   command=lambda x: self.get_selected_joint())
        cmds.setParent('..')
        
        cmds.separator(height=5, style='none')
        
        # 最大影响数
        cmds.text(label='最大影响骨骼数:', align='left')
        self.max_influences_slider = cmds.intSliderGrp(field=True, 
                                                        minValue=1, maxValue=8, 
                                                        value=4, width=420)
        
        cmds.separator(height=20)
        
        # 执行按钮
        cmds.button(label='全局蒙皮', height=45, 
                   backgroundColor=[0.3, 0.5, 0.3],
                   command=lambda x: self.execute_global_skin())
        
        cmds.setParent('..')
        
        # ========== 局部蒙皮 Tab ==========
        local_tab = cmds.columnLayout(adjustableColumn=True, rowSpacing=8,
                                      columnOffset=['both', 10])
        
        cmds.separator(height=10, style='none')
        cmds.text(label='局部蒙皮 - 对选中顶点重新计算权重', align='left')
        cmds.separator(height=10)
        
        cmds.text(label='算法模型:', align='left')
        self.local_model_menu = cmds.optionMenu(width=420)
        for m in self.get_available_models():
            cmds.menuItem(label=m)
        
        cmds.separator(height=15)
        
        cmds.text(label='选中顶点后点击下方按钮:', align='left')
        
        cmds.separator(height=10)
        
        cmds.button(label='局部蒙皮', height=45,
                   backgroundColor=[0.3, 0.4, 0.5],
                   command=lambda x: self.execute_local_skin())
        
        cmds.setParent('..')
        
        # ========== 裙摆蒙皮 Tab ==========
        skirt_tab = cmds.columnLayout(adjustableColumn=True, rowSpacing=8,
                                      columnOffset=['both', 10])
        
        cmds.separator(height=10, style='none')
        cmds.text(label='裙摆蒙皮 - 裙子/披风等布料专用', align='left')
        cmds.separator(height=10)
        
        cmds.text(label='代理骨骼:', align='left')
        skirt_row = cmds.rowLayout(numberOfColumns=2, columnWidth2=(340, 70))
        self.skirt_joint_field = cmds.textField(width=335)
        cmds.button(label='获取', width=65,
                   command=lambda x: self.get_selected_joint_for_skirt())
        cmds.setParent('..')
        
        cmds.separator(height=10)
        
        cmds.button(label='裙摆蒙皮', height=45,
                   backgroundColor=[0.5, 0.3, 0.4],
                   command=lambda x: self.execute_skirt_skin())
        
        cmds.setParent('..')
        
        # ========== 面部蒙皮 Tab ==========
        face_tab = cmds.columnLayout(adjustableColumn=True, rowSpacing=8,
                                     columnOffset=['both', 10])
        
        cmds.separator(height=10, style='none')
        cmds.text(label='面部蒙皮 - 面部骨骼专用算法', align='left')
        cmds.separator(height=10)
        
        cmds.text(label='算法模型:', align='left')
        self.face_model_menu = cmds.optionMenu(width=420)
        cmds.menuItem(label='face-v0 (默认)')
        for m in self.get_available_models():
            if 'face' in m.lower():
                cmds.menuItem(label=m)
        
        cmds.separator(height=10)
        
        cmds.button(label='面部蒙皮', height=45,
                   backgroundColor=[0.4, 0.4, 0.3],
                   command=lambda x: self.execute_face_skin())
        
        cmds.setParent('..')
        
        # 设置Tab标签
        cmds.tabLayout(tabs, edit=True, 
                      tabLabel=[(global_tab, '全局蒙皮'),
                               (local_tab, '局部蒙皮'),
                               (skirt_tab, '裙摆蒙皮'),
                               (face_tab, '面部蒙皮')])
        
        cmds.setParent(main_layout)
        
        # 底部信息
        cmds.separator(height=10)
        cmds.text(label='提示: 将训练好的.pth模型放入 Maya_Plugin/models/ 文件夹',
                 font='smallObliqueLabelFont')
        
        cmds.showWindow(window)
    
    def smart_get_selection(self):
        """智能获取 - 自动分离网格和骨骼"""
        sel = cmds.ls(selection=True, long=True)
        
        if not sel:
            cmds.warning('请先选择网格和骨骼!')
            return
        
        print('[GoSkinning] ========== 智能获取 ==========')
        print('[GoSkinning] 选中 {} 个对象'.format(len(sel)))
        
        meshes = []
        joints = []
        
        for obj in sel:
            short_name = obj.split('|')[-1]
            obj_type = cmds.objectType(obj)
            
            # 检查是否是joint
            if obj_type == 'joint':
                joints.append(short_name)
                print('[GoSkinning]   骨骼: {}'.format(short_name))
            else:
                # 检查是否有mesh shape
                shapes = cmds.listRelatives(obj, shapes=True, type='mesh')
                if shapes:
                    meshes.append(short_name)
                    print('[GoSkinning]   网格: {}'.format(short_name))
        
        # 设置网格
        if meshes:
            meshes = list(dict.fromkeys(meshes))  # 去重
            cmds.textField(self.mesh_field, edit=True, text=','.join(meshes))
            print('[GoSkinning] >>> 网格: {}'.format(','.join(meshes)))
        
        # 设置骨骼
        if joints:
            joints = list(dict.fromkeys(joints))  # 去重
            cmds.textField(self.joint_field, edit=True, text=','.join(joints))
            # 计算总骨骼数
            all_joints = set(joints)
            for j in joints:
                children = cmds.listRelatives(j, allDescendents=True, type='joint') or []
                all_joints.update([c.split('|')[-1] for c in children])
            print('[GoSkinning] >>> 骨骼: {} (共 {} 个)'.format(','.join(joints), len(all_joints)))
        
        print('[GoSkinning] ========== 完成 ==========')
        
        if meshes and joints:
            print('[GoSkinning] 成功获取 {} 个网格, {} 个骨骼根节点'.format(len(meshes), len(joints)))
        elif not meshes:
            cmds.warning('未找到网格!')
        elif not joints:
            cmds.warning('未找到骨骼!')
    
    def get_selected_mesh(self):
        """获取选中的网格（支持多选）"""
        # 获取所有选中的对象
        sel = cmds.ls(selection=True, long=True)
        print('[GoSkinning] 选中对象: {}'.format(sel))
        
        meshes = []
        for obj in sel:
            # 获取短名称
            short_name = obj.split('|')[-1]
            
            # 检查是否是mesh的transform
            shapes = cmds.listRelatives(obj, shapes=True, type='mesh', fullPath=True)
            if shapes:
                meshes.append(short_name)
                print('[GoSkinning]   - 网格: {}'.format(short_name))
            else:
                # 也检查对象本身是否是mesh shape
                if cmds.objectType(obj) == 'mesh':
                    parent = cmds.listRelatives(obj, parent=True)
                    if parent:
                        meshes.append(parent[0])
                        print('[GoSkinning]   - 网格(从shape): {}'.format(parent[0]))
        
        if meshes:
            # 去重
            meshes = list(dict.fromkeys(meshes))
            # 多个网格用逗号分隔
            result = ','.join(meshes)
            cmds.textField(self.mesh_field, edit=True, text=result)
            print('[GoSkinning] === 已选择 {} 个网格: {} ==='.format(len(meshes), result))
        else:
            cmds.warning('未找到网格对象! 请确保选择的是网格(mesh)而不是骨骼')
    
    def get_selected_joint(self):
        """获取选中的骨骼（支持多选，自动获取所有子骨骼）"""
        # 获取所有选中的joint
        sel = cmds.ls(selection=True, type='joint', long=True)
        print('[GoSkinning] 选中骨骼: {}'.format(sel))
        
        if sel:
            # 获取短名称
            short_names = [j.split('|')[-1] for j in sel]
            
            if len(short_names) > 1:
                # 多个骨骼
                result = ','.join(short_names)
                cmds.textField(self.joint_field, edit=True, text=result)
                print('[GoSkinning] === 已选择 {} 个骨骼 ==='.format(len(short_names)))
            else:
                # 单个骨骼，作为根骨骼
                cmds.textField(self.joint_field, edit=True, text=short_names[0])
                # 计算子骨骼数量
                children = cmds.listRelatives(sel[0], allDescendents=True, type='joint') or []
                total = len(children) + 1
                print('[GoSkinning] === 已选择根骨骼: {} (包含 {} 个子骨骼) ==='.format(short_names[0], total))
        else:
            cmds.warning('未找到骨骼! 请确保选择的是骨骼(joint)')
    
    def get_selected_joint_for_skirt(self):
        """获取裙摆骨骼"""
        sel = cmds.ls(selection=True, type='joint')
        if sel:
            cmds.textField(self.skirt_joint_field, edit=True, text=sel[0])
        else:
            cmds.warning('请先选择一个骨骼')
    
    def execute_global_skin(self):
        """执行全局蒙皮"""
        mesh_text = cmds.textField(self.mesh_field, query=True, text=True)
        joint_text = cmds.textField(self.joint_field, query=True, text=True)
        model_name = cmds.optionMenu(self.model_menu, query=True, value=True)
        max_influences = cmds.intSliderGrp(self.max_influences_slider, query=True, value=True)
        merge_mesh = cmds.checkBox(self.merge_mesh_cb, query=True, value=True)
        
        if not mesh_text:
            cmds.warning('请指定目标网格!')
            return
        
        if not joint_text:
            cmds.warning('请指定骨骼!')
            return
        
        if '--' in model_name:
            cmds.warning('请先训练ML模型或选择其他算法!')
            return
        
        # 解析多个网格
        meshes = [m.strip() for m in mesh_text.split(',') if m.strip()]
        
        # 解析骨骼
        joints_input = [j.strip() for j in joint_text.split(',') if j.strip()]
        
        # 收集所有骨骼
        all_joints = []
        for joint in joints_input:
            if cmds.objExists(joint) and cmds.objectType(joint) == 'joint':
                all_joints.append(joint)
                # 获取所有子骨骼
                children = cmds.listRelatives(joint, allDescendents=True, type='joint') or []
                all_joints.extend(children)
        
        # 去重并排序
        all_joints = sorted(list(set(all_joints)))
        
        if not all_joints:
            cmds.warning('未找到有效骨骼!')
            return
        
        print('[GoSkinning] 将处理 {} 个网格, {} 个骨骼'.format(len(meshes), len(all_joints)))
        
        try:
            success_count = 0
            for mesh in meshes:
                if cmds.objExists(mesh):
                    print('[GoSkinning] 处理网格: ' + mesh)
                    self.do_global_skin_with_joints(mesh, all_joints, model_name, max_influences, merge_mesh)
                    success_count += 1
                else:
                    print('[GoSkinning] 网格不存在: ' + mesh)
            
            cmds.confirmDialog(title='完成', 
                              message='全局蒙皮完成!\n处理了 {} 个网格'.format(success_count), 
                              button=['OK'])
        except Exception as e:
            import traceback
            traceback.print_exc()
            cmds.confirmDialog(title='错误', message='蒙皮失败: ' + str(e), button=['OK'])
    
    def execute_local_skin(self):
        """执行局部蒙皮"""
        cmds.warning('局部蒙皮功能开发中...')
    
    def execute_skirt_skin(self):
        """执行裙摆蒙皮"""
        cmds.warning('裙摆蒙皮功能开发中...')
    
    def execute_face_skin(self):
        """执行面部蒙皮"""
        cmds.warning('面部蒙皮功能开发中...')


# 全局实例
_goskinning_instance = None

def show_ui():
    """显示GoSkinning UI"""
    global _goskinning_instance
    if _goskinning_instance is None:
        _goskinning_instance = GoSkinningMaya()
    _goskinning_instance.show_ui()


# 直接运行
if __name__ == '__main__':
    show_ui()
