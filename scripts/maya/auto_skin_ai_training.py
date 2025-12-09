# -*- coding: utf-8 -*-
"""
Auto Skin AI - Training Module

This module demonstrates how to:
1. Export training data from Maya (vertex positions + existing skin weights)
2. Define a neural network architecture for skin weight prediction
3. Train the model
4. Export for use in Maya

goSkinning-style approach:
- Uses vertex position relative to bones
- Considers bone hierarchy and orientation
- Multi-layer perceptron with proper normalization

Usage:
1. In Maya: export_training_data("path/to/data.json")
2. Outside Maya: train_model("path/to/data.json", "path/to/model.pt")
3. In Maya: Use the model with auto_skin_goskinning_style.py
"""

import json
import math

# ====== Part 1: Maya Export Functions ======
# Run these inside Maya to export training data

def export_training_data(output_path, mesh=None, joints=None):
    """
    Export training data from a skinned mesh.
    Call this in Maya with a mesh that has good skin weights.

    output_path: JSON file to write
    mesh: mesh transform name (uses selection if None)
    joints: list of joint names (auto-detect from skinCluster if None)
    """
    import maya.cmds as cmds
    import maya.api.OpenMaya as om2

    # Get mesh from selection if not provided
    if mesh is None:
        sel = cmds.ls(sl=True, type="transform")
        if not sel:
            cmds.error("Please select a mesh or provide mesh name")
            return
        mesh = sel[0]

    # Find skinCluster
    history = cmds.listHistory(mesh) or []
    skin = None
    for h in history:
        if cmds.nodeType(h) == "skinCluster":
            skin = h
            break

    if not skin:
        cmds.error("No skinCluster found on mesh: " + mesh)
        return

    # Get joints from skinCluster if not provided
    if joints is None:
        joints = cmds.skinCluster(skin, q=True, influence=True) or []

    joints_long = [cmds.ls(j, long=True)[0] for j in joints]
    num_joints = len(joints_long)

    print("[Export] Found %d joints" % num_joints)

    # Get joint data (positions, parents, bone vectors)
    joint_data = []
    for j in joints_long:
        pos = cmds.xform(j, q=True, ws=True, t=True)
        parent = cmds.listRelatives(j, parent=True, type="joint", fullPath=True)
        parent_pos = cmds.xform(parent[0], q=True, ws=True, t=True) if parent else pos

        joint_data.append({
            'name': j,
            'position': pos,
            'parent_position': parent_pos
        })

    # Get mesh data
    sel_list = om2.MSelectionList()
    sel_list.add(mesh)
    dag_path = sel_list.getDagPath(0)
    mesh_fn = om2.MFnMesh(dag_path)

    num_verts = mesh_fn.numVertices
    points = mesh_fn.getPoints(om2.MSpace.kWorld)

    print("[Export] Mesh has %d vertices" % num_verts)

    # Extract vertex positions and weights
    samples = []
    for vid in range(num_verts):
        vtx = "%s.vtx[%d]" % (mesh, vid)
        pos = [points[vid].x, points[vid].y, points[vid].z]

        # Get current weights
        weights = []
        for j in joints_long:
            try:
                w = cmds.skinPercent(skin, vtx, transform=j, q=True)
            except:
                w = 0.0
            weights.append(w)

        samples.append({
            'vertex_id': vid,
            'position': pos,
            'weights': weights
        })

    # Build output data
    data = {
        'mesh_name': mesh,
        'num_joints': num_joints,
        'joints': joint_data,
        'num_vertices': num_verts,
        'samples': samples
    }

    # Write JSON
    with open(output_path, 'w') as f:
        json.dump(data, f, indent=2)

    print("[Export] Saved training data to:", output_path)
    print("[Export] %d samples written" % len(samples))


def export_multiple_meshes(output_dir, meshes=None):
    """
    Export training data from multiple meshes.
    Useful for building a diverse training set.
    """
    import maya.cmds as cmds
    import os

    if meshes is None:
        meshes = cmds.ls(sl=True, type="transform")

    if not meshes:
        cmds.error("Please select meshes or provide mesh list")
        return

    for i, mesh in enumerate(meshes):
        output_path = os.path.join(output_dir, "%s_data.json" % mesh.replace("|", "_"))
        try:
            export_training_data(output_path, mesh)
        except Exception as e:
            print("[Export] Failed for %s: %s" % (mesh, str(e)))


# ====== Part 2: Neural Network Definition ======
# This can run outside Maya (just needs PyTorch)

def create_skin_weight_model():
    """
    Create the neural network for skin weight prediction.

    Architecture similar to goSkinning:
    - Input: vertex features (position + bone distances + bone directions)
    - Hidden: multiple fully connected layers with ReLU
    - Output: weight per joint (softmax normalized)
    """
    try:
        import torch
        import torch.nn as nn
    except ImportError:
        print("PyTorch not available")
        return None

    class SkinWeightPredictor(nn.Module):
        """
        Neural network for predicting skin weights.

        Features per vertex:
        - Normalized position (3)
        - Per-joint: distance to bone (1), bone direction dot product (1), 
          relative position (3) = 5 per joint

        Total input: 3 + num_joints * 5
        """

        def __init__(self, num_joints, hidden_dims=[512, 256, 128]):
            super(SkinWeightPredictor, self).__init__()

            # Input size: position(3) + per_joint_features(5 * num_joints)
            input_dim = 3 + num_joints * 5

            layers = []
            prev_dim = input_dim

            for h_dim in hidden_dims:
                layers.extend([
                    nn.Linear(prev_dim, h_dim),
                    nn.LayerNorm(h_dim),
                    nn.ReLU(),
                    nn.Dropout(0.1)
                ])
                prev_dim = h_dim

            # Output layer (no activation, softmax applied during inference)
            layers.append(nn.Linear(prev_dim, num_joints))

            self.net = nn.Sequential(*layers)
            self.num_joints = num_joints

        def forward(self, x):
            """Forward pass. Returns raw logits."""
            return self.net(x)

        def predict(self, x):
            """Predict normalized weights."""
            logits = self.forward(x)
            return torch.softmax(logits, dim=-1)

    return SkinWeightPredictor


# ====== Part 3: Feature Extraction ======

def compute_features(positions, joint_data):
    """
    Compute input features for the neural network.

    positions: list of [x, y, z] vertex positions
    joint_data: list of dicts with 'position', 'parent_position'

    Returns: feature matrix [num_verts, feature_dim]
    """
    import numpy as np

    num_verts = len(positions)
    num_joints = len(joint_data)

    # Normalize positions to unit bounding box
    positions = np.array(positions)
    pos_min = positions.min(axis=0)
    pos_max = positions.max(axis=0)
    pos_range = pos_max - pos_min
    pos_range[pos_range < 1e-6] = 1.0
    positions_norm = (positions - pos_min) / pos_range

    features = []

    for vid in range(num_verts):
        pos = positions[vid]
        pos_norm = positions_norm[vid]

        feat = list(pos_norm)  # Normalized position [3]

        for jd in joint_data:
            j_pos = np.array(jd['position'])
            p_pos = np.array(jd['parent_position'])

            # Bone vector
            bone_vec = j_pos - p_pos
            bone_len = np.linalg.norm(bone_vec)
            if bone_len > 1e-6:
                bone_dir = bone_vec / bone_len
            else:
                bone_dir = np.array([0, 1, 0])
                bone_len = 1.0

            # Distance from vertex to bone segment
            v_pos = np.array(pos)
            ap = v_pos - p_pos
            ab = j_pos - p_pos
            ab_len_sq = np.dot(ab, ab)

            if ab_len_sq > 1e-10:
                t = max(0, min(1, np.dot(ap, ab) / ab_len_sq))
                closest = p_pos + t * ab
            else:
                closest = p_pos

            dist = np.linalg.norm(v_pos - closest)

            # Normalize distance by mesh scale
            dist_norm = dist / (pos_range.max() + 1e-6)

            # Direction from closest point to vertex
            to_vertex = v_pos - closest
            to_vertex_len = np.linalg.norm(to_vertex)
            if to_vertex_len > 1e-6:
                to_vertex = to_vertex / to_vertex_len
            else:
                to_vertex = np.array([0, 0, 0])

            # Dot product with bone direction
            dot = np.dot(to_vertex, bone_dir)

            # Relative position along bone
            if bone_len > 1e-6:
                along_bone = np.dot(ap, bone_dir) / bone_len
            else:
                along_bone = 0.0

            # Features for this joint
            feat.append(dist_norm)
            feat.append(dot)
            feat.extend(to_vertex.tolist())

        features.append(feat)

    return np.array(features, dtype=np.float32)


# ====== Part 4: Training Loop ======

def train_model(data_path, output_path, epochs=100, batch_size=256, lr=0.001):
    """
    Train the skin weight prediction model.

    data_path: JSON file from export_training_data
    output_path: where to save the trained model (.pt file)
    """
    try:
        import torch
        import torch.nn as nn
        import torch.optim as optim
        from torch.utils.data import DataLoader, TensorDataset
        import numpy as np
    except ImportError:
        print("PyTorch and NumPy required for training")
        return

    # Load data
    print("[Train] Loading data from:", data_path)
    with open(data_path, 'r') as f:
        data = json.load(f)

    num_joints = data['num_joints']
    joint_data = data['joints']
    samples = data['samples']

    print("[Train] %d joints, %d samples" % (num_joints, len(samples)))

    # Extract positions and weights
    positions = [s['position'] for s in samples]
    weights = np.array([s['weights'] for s in samples], dtype=np.float32)

    # Compute features
    print("[Train] Computing features...")
    features = compute_features(positions, joint_data)
    print("[Train] Feature shape:", features.shape)

    # Create dataset
    X = torch.tensor(features, dtype=torch.float32)
    Y = torch.tensor(weights, dtype=torch.float32)

    dataset = TensorDataset(X, Y)
    loader = DataLoader(dataset, batch_size=batch_size, shuffle=True)

    # Create model
    ModelClass = create_skin_weight_model()
    model = ModelClass(num_joints)
    print("[Train] Model created")

    # Loss and optimizer
    # Use KL divergence since weights are probabilities
    criterion = nn.KLDivLoss(reduction='batchmean')
    optimizer = optim.Adam(model.parameters(), lr=lr)
    scheduler = optim.lr_scheduler.ReduceLROnPlateau(optimizer, patience=10, factor=0.5)

    # Training loop
    print("[Train] Starting training for %d epochs..." % epochs)
    model.train()

    best_loss = float('inf')
    for epoch in range(epochs):
        total_loss = 0.0
        num_batches = 0

        for batch_x, batch_y in loader:
            optimizer.zero_grad()

            # Forward
            logits = model(batch_x)
            log_probs = torch.log_softmax(logits, dim=-1)

            # Target must be probabilities (already normalized)
            loss = criterion(log_probs, batch_y)

            # Backward
            loss.backward()
            optimizer.step()

            total_loss += loss.item()
            num_batches += 1

        avg_loss = total_loss / num_batches
        scheduler.step(avg_loss)

        if (epoch + 1) % 10 == 0:
            print("[Train] Epoch %d/%d, Loss: %.6f" % (epoch + 1, epochs, avg_loss))

        if avg_loss < best_loss:
            best_loss = avg_loss

    print("[Train] Training complete. Best loss: %.6f" % best_loss)

    # Save model
    model.eval()

    # Save as TorchScript for use in Maya
    print("[Train] Saving model to:", output_path)

    # We need to save with example input for tracing
    example_input = torch.randn(1, features.shape[1])
    traced = torch.jit.trace(model, example_input)
    traced.save(output_path)

    # Also save metadata
    meta_path = output_path.replace('.pt', '_meta.json')
    meta = {
        'num_joints': num_joints,
        'feature_dim': features.shape[1],
        'joint_names': [jd['name'] for jd in joint_data]
    }
    with open(meta_path, 'w') as f:
        json.dump(meta, f, indent=2)

    print("[Train] Saved metadata to:", meta_path)
    print("[Train] Done!")


# ====== Part 5: Inference in Maya ======

class SkinWeightInference:
    """
    Class for running inference in Maya.
    Load once, predict many times.
    """

    def __init__(self, model_path):
        """
        Initialize with trained model.

        model_path: path to .pt file
        """
        import torch

        self.model = torch.jit.load(model_path, map_location='cpu')
        self.model.eval()

        # Load metadata
        meta_path = model_path.replace('.pt', '_meta.json')
        try:
            with open(meta_path, 'r') as f:
                self.meta = json.load(f)
        except:
            self.meta = {}

        self.num_joints = self.meta.get('num_joints', None)
        print("[Inference] Loaded model from:", model_path)

    def predict(self, positions, joint_data):
        """
        Predict skin weights for vertices.

        positions: list of [x, y, z]
        joint_data: list of dicts with 'position', 'parent_position'

        Returns: weights [num_verts, num_joints]
        """
        import torch
        import numpy as np

        features = compute_features(positions, joint_data)
        X = torch.tensor(features, dtype=torch.float32)

        with torch.no_grad():
            logits = self.model(X)
            weights = torch.softmax(logits, dim=-1)

        return weights.numpy().tolist()


# ====== Usage Examples ======

"""
WORKFLOW:

1. EXPORT DATA (in Maya):
   
   import auto_skin_ai_training as train
   train.export_training_data("C:/skin_data/character01.json")


2. TRAIN MODEL (outside Maya, or Maya with PyTorch):
   
   import auto_skin_ai_training as train
   train.train_model(
       "C:/skin_data/character01.json",
       "C:/ai_models/skin_model.pt",
       epochs=200
   )


3. USE MODEL (in Maya):
   
   # Option A: Use with auto_skin_goskinning_style.py
   # Set USE_TORCH=True and MODEL_PATH to your model
   
   # Option B: Direct inference
   import auto_skin_ai_training as train
   
   predictor = train.SkinWeightInference("C:/ai_models/skin_model.pt")
   weights = predictor.predict(vertex_positions, joint_data)


TIPS FOR BETTER RESULTS:

1. Train on multiple characters with good hand-painted weights
2. Include variety: thin/thick limbs, different poses
3. More epochs (500+) often helps
4. Use data augmentation (mirror characters, scale)
5. Separate models for body/face/hands can improve quality
"""


if __name__ == "__main__":
    print("Auto Skin AI Training Module")
    print("See docstring for usage examples.")
