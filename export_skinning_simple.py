# -*- coding: utf-8 -*-
"""
3ds Max Skinning Data Export - Simple Version
Simply change the output_folder path below and run

Usage:
1. Open your skinned character in 3ds Max
2. Select the skinned mesh (not the bones!)
3. Change output_folder below to your path
4. Run this script: MAXScript -> Run Script
"""

import json
import os

# ============================================
# CHANGE THIS PATH TO YOUR SAVE LOCATION
# ============================================
output_folder = r"D:\training_data\train"
# ============================================

try:
    import pymxs
    from pymxs import runtime as rt
except ImportError:
    print("ERROR: This script must be run inside 3ds Max!")
    raise

def export_mesh():
    print("\n" + "="*50)
    print("  GoSkinning Training Data Export")
    print("="*50)
    
    # Check selection
    if rt.selection.count == 0:
        print("ERROR: No object selected!")
        print("Please select a skinned mesh first.")
        rt.messageBox("Please select a skinned mesh!", title="Error")
        return
    
    mesh_obj = rt.selection[0]
    print(f"\nSelected: {mesh_obj.name}")
    
    # Find Skin modifier
    skin_mod = None
    try:
        for mod in mesh_obj.modifiers:
            if rt.classOf(mod) == rt.Skin:
                skin_mod = mod
                break
    except:
        pass
    
    if not skin_mod:
        print("ERROR: No Skin modifier found!")
        print("The selected object must have a Skin modifier.")
        rt.messageBox("No Skin modifier found on selected object!", title="Error")
        return
    
    print(f"Found Skin modifier: {skin_mod.name}")
    
    # Get vertex count
    num_verts = rt.skinOps.getNumberVertices(skin_mod)
    print(f"Vertices: {num_verts}")
    
    # Get bone count
    num_bones = rt.skinOps.getNumberBones(skin_mod)
    print(f"Bones: {num_bones}")
    
    # ============ Get Vertices ============
    print("\nExporting vertices...")
    vertices = []
    normals = []
    
    for i in range(1, num_verts + 1):
        try:
            # Try to get vertex position
            pos = rt.polyOp.getVert(mesh_obj, i)
            vertices.append([float(pos.x), float(pos.y), float(pos.z)])
        except:
            try:
                pos = rt.meshOp.getVert(mesh_obj, i)
                vertices.append([float(pos.x), float(pos.y), float(pos.z)])
            except:
                vertices.append([0.0, 0.0, 0.0])
        
        normals.append([0.0, 1.0, 0.0])
        
        if i % 2000 == 0:
            print(f"  Vertices: {i}/{num_verts}")
    
    print(f"  Done: {len(vertices)} vertices")
    
    # ============ Get Bones ============
    print("\nExporting bones...")
    bones = []
    
    for i in range(1, num_bones + 1):
        bone_name = rt.skinOps.getBoneName(skin_mod, i, 0)
        bone_node = rt.getNodeByName(bone_name)
        
        if bone_node:
            pos = bone_node.transform.pos
            head = [float(pos.x), float(pos.y), float(pos.z)]
            
            # Get bone length
            length = 10.0
            try:
                if hasattr(bone_node, 'length') and bone_node.length > 0:
                    length = float(bone_node.length)
            except:
                pass
            
            # Bone direction
            try:
                axis = rt.normalize(bone_node.transform.row3)
                tail = [head[0] + float(axis.x) * length,
                        head[1] + float(axis.y) * length,
                        head[2] + float(axis.z) * length]
            except:
                tail = [head[0], head[1] + length, head[2]]
            
            # Parent
            parent = None
            try:
                if bone_node.parent:
                    parent = str(bone_node.parent.name)
            except:
                pass
            
            bones.append({
                "name": str(bone_name),
                "head": head,
                "tail": tail,
                "parent": parent
            })
        else:
            bones.append({
                "name": str(bone_name),
                "head": [0.0, float(i) * 10.0, 0.0],
                "tail": [0.0, float(i) * 10.0 + 10.0, 0.0],
                "parent": None
            })
    
    print(f"  Done: {len(bones)} bones")
    
    # ============ Get Weights ============
    print("\nExporting weights...")
    weights = []
    
    for v_idx in range(1, num_verts + 1):
        vert_weights = []
        
        try:
            num_weights = rt.skinOps.getVertexWeightCount(skin_mod, v_idx)
            
            for w_idx in range(1, num_weights + 1):
                bone_id = rt.skinOps.getVertexWeightBoneID(skin_mod, v_idx, w_idx)
                weight = rt.skinOps.getVertexWeight(skin_mod, v_idx, w_idx)
                
                if weight > 0.001:
                    vert_weights.append([int(bone_id) - 1, float(weight)])
        except:
            pass
        
        weights.append(vert_weights)
        
        if v_idx % 2000 == 0:
            print(f"  Weights: {v_idx}/{num_verts}")
    
    print(f"  Done: {len(weights)} weight sets")
    
    # ============ Save File ============
    print("\nSaving file...")
    
    # Create folder if not exists
    if not os.path.exists(output_folder):
        os.makedirs(output_folder)
        print(f"  Created folder: {output_folder}")
    
    # Build data
    data = {
        "mesh_name": str(mesh_obj.name),
        "vertices": vertices,
        "normals": normals,
        "faces": [],
        "bones": bones,
        "weights": weights
    }
    
    # Save
    filename = str(mesh_obj.name).replace(" ", "_").replace(":", "_") + ".json"
    filepath = os.path.join(output_folder, filename)
    
    with open(filepath, 'w', encoding='utf-8') as f:
        json.dump(data, f)
    
    print(f"\n{'='*50}")
    print(f"  EXPORT COMPLETE!")
    print(f"{'='*50}")
    print(f"  File: {filepath}")
    print(f"  Vertices: {len(vertices)}")
    print(f"  Bones: {len(bones)}")
    print(f"{'='*50}\n")
    
    rt.messageBox(f"Export complete!\n\nFile: {filepath}\nVertices: {len(vertices)}\nBones: {len(bones)}", 
                  title="Success")

# Run
print("\nStarting export...")
print(f"Output folder: {output_folder}")
export_mesh()
