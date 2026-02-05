# -*- coding: utf-8 -*-
"""
GoSkinning - 3ds Max Auto Skin Script
Use trained model to automatically skin a mesh

Usage:
1. Change model_path below to your trained model
2. Open 3ds Max
3. Select mesh object (no skin modifier yet)
4. Select all bones
5. Run this script
"""

import os
import json
import numpy as np

# ============================================
# SETTINGS - CHANGE THESE
# ============================================
model_path = r"C:\Users\Admin\Desktop\GoSkinning_ML_Training\my_model\skinning_model.pt"
max_influences = 4  # Max bones per vertex
# ============================================

try:
    import pymxs
    from pymxs import runtime as rt
    MAX_OK = True
except:
    MAX_OK = False
    print("ERROR: Run this in 3ds Max!")

try:
    import torch
    TORCH_OK = True
except:
    TORCH_OK = False
    print("ERROR: PyTorch not installed!")
    print("Run in CMD: pip install torch")


def get_mesh_and_bones():
    """Get selected mesh and bones"""
    mesh = None
    bones = []
    
    for obj in rt.selection:
        obj_class = rt.classOf(obj)
        
        # Check if mesh
        if obj_class in [rt.Editable_Poly, rt.Editable_Mesh, rt.PolyMeshObject]:
            mesh = obj
        elif hasattr(obj, 'baseObject'):
            base_class = rt.classOf(obj.baseObject)
            if base_class in [rt.Editable_Poly, rt.Editable_Mesh]:
                mesh = obj
        
        # Check if bone
        if obj_class in [rt.BoneGeometry, rt.Biped_Object, rt.Dummy]:
            bones.append(obj)
        elif 'Bone' in str(obj_class) or 'Bip' in str(obj_class):
            bones.append(obj)
    
    return mesh, bones


def get_vertex_data(mesh):
    """Get vertex positions and normals"""
    vertices = []
    normals = []
    
    num_verts = rt.polyOp.getNumVerts(mesh)
    
    for i in range(1, num_verts + 1):
        pos = rt.polyOp.getVert(mesh, i)
        vertices.append([float(pos.x), float(pos.y), float(pos.z)])
        
        try:
            norm = rt.polyOp.getVertNormal(mesh, i)
            normals.append([float(norm.x), float(norm.y), float(norm.z)])
        except:
            normals.append([0.0, 1.0, 0.0])
    
    return np.array(vertices, dtype=np.float32), np.array(normals, dtype=np.float32)


def get_bone_data(bones):
    """Get bone positions"""
    heads = []
    tails = []
    
    for bone in bones:
        pos = bone.transform.pos
        head = [float(pos.x), float(pos.y), float(pos.z)]
        
        # Get length
        length = 10.0
        try:
            if hasattr(bone, 'length') and bone.length > 0:
                length = float(bone.length)
        except:
            pass
        
        # Get direction
        try:
            axis = rt.normalize(bone.transform.row3)
            tail = [head[0] + float(axis.x) * length,
                    head[1] + float(axis.y) * length,
                    head[2] + float(axis.z) * length]
        except:
            tail = [head[0], head[1] + length, head[2]]
        
        heads.append(head)
        tails.append(tail)
    
    return np.array(heads, dtype=np.float32), np.array(tails, dtype=np.float32)


def predict_weights(model, vertices, normals, bone_heads, bone_tails):
    """Use model to predict skin weights"""
    
    # Normalize data
    all_points = np.concatenate([vertices, bone_heads, bone_tails], axis=0)
    center = (all_points.max(axis=0) + all_points.min(axis=0)) / 2
    scale = (all_points.max(axis=0) - all_points.min(axis=0)).max()
    
    if scale > 0:
        vertices = (vertices - center) / scale
        bone_heads = (bone_heads - center) / scale
        bone_tails = (bone_tails - center) / scale
    
    # Normalize normals
    norm_lengths = np.linalg.norm(normals, axis=1, keepdims=True)
    norm_lengths = np.maximum(norm_lengths, 1e-8)
    normals = normals / norm_lengths
    
    # Build tensors
    vertex_pos = torch.tensor(vertices, dtype=torch.float32).unsqueeze(0)
    vertex_norm = torch.tensor(normals, dtype=torch.float32).unsqueeze(0)
    bone_h = torch.tensor(bone_heads, dtype=torch.float32).unsqueeze(0)
    bone_t = torch.tensor(bone_tails, dtype=torch.float32).unsqueeze(0)
    
    # Build features
    vertex_features = torch.cat([vertex_pos, vertex_norm], dim=-1)
    
    bone_dir = bone_t - bone_h
    bone_dir = bone_dir / (bone_dir.norm(dim=-1, keepdim=True) + 1e-8)
    bone_features = torch.cat([bone_h, bone_t, bone_dir], dim=-1)
    
    # Distances
    distances = torch.cdist(vertex_pos, bone_h)
    
    # Predict
    with torch.no_grad():
        weights, _ = model(vertex_features, bone_features, distances)
    
    return weights.squeeze(0).numpy()


def apply_skin(mesh, bones, weights):
    """Apply skin modifier with weights"""
    
    # Add Skin modifier
    skin_mod = rt.Skin()
    rt.addModifier(mesh, skin_mod)
    
    # Add bones
    for bone in bones:
        rt.skinOps.addBone(skin_mod, bone, 0)
    
    # Wait for update
    rt.completeRedraw()
    
    # Apply weights
    num_verts = weights.shape[0]
    num_bones = weights.shape[1]
    
    print(f"Applying weights to {num_verts} vertices...")
    
    for v_idx in range(num_verts):
        vert_weights = weights[v_idx]
        
        # Get top k weights
        top_indices = np.argsort(vert_weights)[::-1][:max_influences]
        top_weights = vert_weights[top_indices]
        
        # Filter small weights
        mask = top_weights > 0.01
        top_indices = top_indices[mask]
        top_weights = top_weights[mask]
        
        if len(top_weights) == 0:
            continue
        
        # Normalize
        top_weights = top_weights / top_weights.sum()
        
        # Apply
        bone_array = rt.Array()
        weight_array = rt.Array()
        
        for bi, w in zip(top_indices, top_weights):
            rt.append(bone_array, int(bi) + 1)  # 1-indexed
            rt.append(weight_array, float(w))
        
        try:
            rt.skinOps.setVertexWeights(skin_mod, v_idx + 1, bone_array, weight_array)
        except Exception as e:
            pass
        
        if (v_idx + 1) % 1000 == 0:
            print(f"  Progress: {v_idx + 1}/{num_verts}")
    
    print("Done!")


def main():
    if not MAX_OK:
        print("Must run in 3ds Max!")
        return
    
    if not TORCH_OK:
        rt.messageBox("PyTorch not installed!\n\nRun in CMD:\npip install torch", title="Error")
        return
    
    # Check model file
    if not os.path.exists(model_path):
        rt.messageBox(f"Model not found:\n{model_path}\n\nPlease check the path.", title="Error")
        return
    
    # Get selection
    mesh, bones = get_mesh_and_bones()
    
    if not mesh:
        rt.messageBox("Please select a mesh object!", title="Error")
        return
    
    if not bones:
        rt.messageBox("Please select bone objects!", title="Error")
        return
    
    print(f"\n{'='*50}")
    print(f"  GoSkinning Auto Skin")
    print(f"{'='*50}")
    print(f"Mesh: {mesh.name}")
    print(f"Bones: {len(bones)}")
    print(f"Model: {model_path}")
    print(f"{'='*50}\n")
    
    # Load model
    print("Loading model...")
    model = torch.jit.load(model_path)
    model.eval()
    
    # Get data
    print("Getting mesh data...")
    vertices, normals = get_vertex_data(mesh)
    print(f"  Vertices: {len(vertices)}")
    
    print("Getting bone data...")
    bone_heads, bone_tails = get_bone_data(bones)
    print(f"  Bones: {len(bone_heads)}")
    
    # Predict
    print("Predicting weights...")
    weights = predict_weights(model, vertices, normals, bone_heads, bone_tails)
    print(f"  Weights shape: {weights.shape}")
    
    # Apply
    print("Applying skin...")
    apply_skin(mesh, bones, weights)
    
    print(f"\n{'='*50}")
    print(f"  COMPLETE!")
    print(f"{'='*50}\n")
    
    rt.messageBox(f"Auto skin complete!\n\nMesh: {mesh.name}\nVertices: {len(vertices)}\nBones: {len(bones)}", 
                  title="Success")


# Run
if MAX_OK:
    main()
