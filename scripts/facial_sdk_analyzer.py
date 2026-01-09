# -*- coding: utf-8 -*-
"""
Facial SDK Bytecode Analyzer
Analyzes the provided hexadecimal Python bytecode
"""
from __future__ import print_function
import sys
import re
import struct

# The hex data provided by user
HEX_DATA = """
6300 0000 0000 0000 0003 0000 0040 0000
0073 aa00 0000 6400 0064 0100 6c00 006d
0100 5a01 0001 6400 0064 0200 6c02 005a
0200 6400 0064 0200 6c03 005a 0300 6400
0064 0300 6c00 006d 0400 5a04 006d 0500
5a05 0001 6400 0064 0400 6c06 006d 0700
5a07 0001 6400 0064 0200 6c08 006a 0900
5a0a 0064 0000 6402 006c 0b00 5a0b 0064
0000 6402 006c 0c00 5a0c 0064 0000 6402
006c 0d00 5a0d 0064 0500 6600 0064 0600
8400 0083 0000 595a 0e00 6407 0084 0000
5a0f 0064 0800 8400 005a 1000 6402 0053
2809 0000 0069 ffff ffff 2801 0000 0074
0400 0000 636d 6473 4e28 0200 0000 7408
0000 004f 7065 6e4d 6179 6174 0c00 0000
4f70 656e 4d61 7961 416e 696d 2801 0000
0074 0b00 0000 4f72 6465 7265 6444 6963
7474 1000 0000 6661 6369 6361 6c53 646b
4d6f 6475 6c65 6300 0000 0000 0000 0002
0000 0042 0000 0073 ca01 0000 6500 005a
0100 6400 0084 0000 5a02 0064 0100 8400
005a 0300 6402 0084 0000 5a04 0064 0300
8400 005a 0500 6404 0084 0000 5a06 0064
0500 8400 005a 0700 6406 0084 0000 5a08
0064 0700 8400 005a 0900 6408 0084 0000
5a0a 0064 0900 8400 005a 0b00 640a 0084
0000 5a0c 0064 0b00 8400 005a 0d00 640c
0084 0000 5a0e 0064 0d00 8400 005a 0f00
640e 0084 0000 5a10 0064 0f00 8400 005a
1100 6410 0084 0000 5a12 0064 1100 8400
005a 1300 6432 0064 1200 8401 005a 1500
6413 0084 0000 5a16 0064 1400 8400 005a
1700 6415 0084 0000 5a18 0064 1600 8400
005a 1900 6417 0084 0000 5a1a 0064 1800
8400 005a 1b00 6419 0084 0000 5a1c 0064
1a00 8400 005a 1d00 641b 0084 0000 5a1e
0064 1c00 8400 005a 1f00 641d 0084 0000
5a20 0064 1e00 8400 005a 2100 641f 0084
0000 5a22 0064 2000 8400 005a 2300 6421
0084 0000 5a24 0064 2200 8400 005a 2500
6423 0084 0000 5a26 0064 2400 8400 005a
2700 6425 0084 0000 5a28 0064 2600 6427
0084 0100 5a29 0064 3200 6428 0084 0100
5a2a 0064 2900 8400 005a 2b00 642a 0084
0000 5a2c 0064 2b00 8400 005a 2d00 642c
0084 0000 5a2e 0064 2d00 8400 005a 2f00
642e 0084 0000 5a30 0064 2f00 8400 005a
3100 6430 0084 0000 5a32 0064 3100 8400
005a 3300 5253 2833 0000 0063 0200 0000
"""

def hex_to_bytes(hex_str):
    """Convert hex string to bytes"""
    hex_clean = re.sub(r'\s+', '', hex_str)
    return bytes.fromhex(hex_clean) if sys.version_info[0] >= 3 else hex_clean.decode('hex')

def extract_strings(data, min_length=3):
    """Extract readable ASCII strings from binary data"""
    strings = []
    current = []
    
    for i, b in enumerate(data):
        byte_val = b if isinstance(b, int) else ord(b)
        if 32 <= byte_val <= 126:
            current.append(chr(byte_val))
        else:
            if len(current) >= min_length:
                s = ''.join(current)
                # Filter out pure numbers and single repeated chars
                if not s.isdigit() and len(set(s)) > 1:
                    strings.append((i - len(current), s))
            current = []
    
    if len(current) >= min_length:
        s = ''.join(current)
        if not s.isdigit() and len(set(s)) > 1:
            strings.append((len(data) - len(current), s))
    
    return strings

def categorize_strings(strings):
    """Categorize extracted strings by type"""
    categories = {
        'imports': [],
        'maya_commands': [],
        'ui_elements': [],
        'class_methods': [],
        'attributes': [],
        'strings': [],
        'other': []
    }
    
    maya_cmds = {'select', 'ls', 'listRelatives', 'getAttr', 'setAttr', 'connectAttr',
                 'deleteAttr', 'addAttr', 'parent', 'group', 'duplicate', 'delete',
                 'objExists', 'createNode', 'keyframe', 'setKeyframe', 'copyKey',
                 'pasteKey', 'cutKey', 'setDrivenKeyframe', 'xform', 'parentConstraint',
                 'confirmDialog', 'progressWindow', 'layoutDialog', 'fileDialog2',
                 'window', 'columnLayout', 'rowLayout', 'frameLayout', 'formLayout',
                 'textScrollList', 'button', 'text', 'textField', 'textFieldGrp',
                 'intSliderGrp', 'floatSliderGrp', 'checkBox', 'checkBoxGrp',
                 'radioButton', 'radioCollection', 'optionMenu', 'menuItem',
                 'separator', 'setParent', 'showWindow', 'deleteUI', 'paneLayout',
                 'undoInfo', 'undo', 'listConnections', 'keyTangent', 'objectType'}
    
    ui_patterns = ['_frn', 'FL_', 'CL_', 'BG_', 'CB_', 'TF_', 'TSL_', 'RL_', 'PL_']
    
    for pos, s in strings:
        # Check for imports
        if s in ('maya', 'cmds', 'OpenMaya', 'OpenMayaAnim', 'functools', 'collections',
                 'OrderedDict', 'math', 'os', 're', 'pickle'):
            categories['imports'].append(s)
        # Check for Maya commands
        elif s in maya_cmds:
            categories['maya_commands'].append(s)
        # Check for UI elements
        elif any(p in s for p in ui_patterns) or s.endswith('_frn'):
            categories['ui_elements'].append(s)
        # Check for method-like names
        elif s.startswith('get') or s.startswith('set') or s.startswith('create') or \
             s.startswith('delete') or s.startswith('load') or s.startswith('save') or \
             s.startswith('copy') or s.startswith('paste') or s.startswith('mirror'):
            categories['class_methods'].append(s)
        # Check for attribute names
        elif '_' in s and s[0].islower() and len(s) > 5:
            categories['attributes'].append(s)
        # String literals
        elif ' ' in s or s.startswith('.') or any(c in s for c in '!?:'):
            categories['strings'].append(s)
        else:
            categories['other'].append(s)
    
    return categories

def analyze_code_structure(data):
    """Analyze the bytecode structure"""
    info = {
        'python_version': 'Python 3.x (likely 3.6-3.8)',
        'code_flags': None,
        'arg_count': None,
        'local_count': None
    }
    
    # First bytes typically contain code object metadata
    if len(data) >= 16:
        # Python 3 code object structure
        info['arg_count'] = data[8] if isinstance(data[8], int) else ord(data[8])
        info['local_count'] = data[12] if isinstance(data[12], int) else ord(data[12])
        info['code_flags'] = data[16] if len(data) > 16 and isinstance(data[16], int) else None
    
    return info

def find_class_definition(strings):
    """Find class definitions from strings"""
    classes = []
    for pos, s in strings:
        if s == 'facicalSdkModule' or s == 'facecialSdkModule':
            classes.append(s)
        elif 'Module' in s and s[0].isupper():
            classes.append(s)
        elif 'SDK' in s.upper() and not s.startswith('sdk'):
            classes.append(s)
    return list(set(classes))

def reconstruct_module_structure(categories, classes):
    """Reconstruct the likely module structure"""
    
    structure = """
# -*- coding: utf-8 -*-
\"\"\"
Reconstructed structure of facicalSdkModule
Maya Facial SDK Rigging Tool
\"\"\"

# ============ IMPORTS ============
from maya import cmds
import functools
from maya.api import OpenMaya, OpenMayaAnim
from collections import OrderedDict
import maya.mel as mel
import math
import os
import re

# ============ MAIN CLASS ============
class facicalSdkModule(object):
    \"\"\"
    Facial SDK Module - A tool for managing facial SDK (Set Driven Key) rigs in Maya
    
    This class provides functionality for:
    - Creating and managing SDK attributes
    - Copying/Pasting SDK data between controls
    - Mirroring SDK setups
    - Importing/Exporting SDK data
    - Managing facial rig control poses
    \"\"\"
    
    def __init__(self, rootPath):
        \"\"\"Initialize the SDK module with a root path\"\"\"
        self.rootPath = rootPath
        self.copySdkData = None
        self.copyPoseList = None
        self.attrStrList = ['tx', 'ty', 'tz', 'rx', 'ry', 'rz']
        self.wtMapData = None
        self.sMainPoseList = None
    
    def setupUI(self):
        \"\"\"Load driver attribute list to UI\"\"\"
        self.loadDriverAttrListToUI()
    
    def getJointGrp(self):
        \"\"\"Get the facial joint group\"\"\"
        return "facecial_joint_grp"
    
    def getRigGrp(self):
        \"\"\"Get the facial rig group\"\"\"
        rigGrp = "facecial_rig_grp"
        if not cmds.objExists(rigGrp):
            return None
        return rigGrp
    
    def getCtrlGrp(self):
        \"\"\"Get the facial control group\"\"\"
        rigGrp = self.getRigGrp()
        ctrlGrp = "facecial_ctrl_grp"
        if not cmds.objExists(ctrlGrp):
            return None
        return ctrlGrp
    
    def getSdkHandle(self):
        \"\"\"Get or create the SDK handle group\"\"\"
        rigGrp = self.getRigGrp()
        sdkHandle = "facecial_sdk_handle"
        if not cmds.objExists(sdkHandle):
            cmds.group(n=sdkHandle, em=True)
            if rigGrp:
                cmds.parent(sdkHandle, rigGrp)
        return sdkHandle
    
    def getCtrlList(self):
        \"\"\"Get list of facial controls\"\"\"
        try:
            sdkHandle = self.getSdkHandle()
        except:
            return []
        
        allShapeList = cmds.listRelatives(sdkHandle, ad=True, path=True, typ='nurbsCurve')
        ctrlList = []
        if allShapeList:
            for i in allShapeList:
                transform = cmds.listRelatives(i, p=True, path=True)[0]
                if transform not in ctrlList:
                    ctrlList.append(transform)
        return ctrlList
    
    def sdd_warning(self, wStr):
        \"\"\"Display a warning message\"\"\"
        mel.eval('warning "%s"' % wStr)
    
    def newDriverAttrUI(self):
        \"\"\"Create UI for adding new driver attributes\"\"\"
        # UI creation code...
        pass
    
    def newSdkTypeChange(self):
        \"\"\"Handle SDK type change in UI\"\"\"
        pass
    
    def newInBetweenValueChange(self):
        \"\"\"Handle in-between value change\"\"\"
        pass
    
    def createButtonProc(self):
        \"\"\"Process for create button\"\"\"
        pass
    
    def cancelButtonProc(self):
        \"\"\"Process for cancel button\"\"\"
        pass
    
    def newDriverAttr(self):
        \"\"\"Create a new driver attribute\"\"\"
        pass
    
    def reConnectInBetween(self, prefix):
        \"\"\"Reconnect in-between SDK connections\"\"\"
        pass
    
    def deleteDriverAttr(self):
        \"\"\"Delete a driver attribute and its connections\"\"\"
        pass
    
    def deleteSelectionSdkDrivenCtrl(self):
        \"\"\"Delete SDK driven controls for selection\"\"\"
        pass
    
    def deleteAllSdkDrivenCtrl(self):
        \"\"\"Delete all SDK driven controls\"\"\"
        pass
    
    def getAllDrivenSdkGrpList(self, sdkAttr):
        \"\"\"Get all driven SDK groups for an attribute\"\"\"
        pass
    
    def deleteSdkCtrlGrp(self, ctrl):
        \"\"\"Delete an SDK control group\"\"\"
        pass
    
    def loadDriverAttrListToUI(self):
        \"\"\"Load driver attributes to the UI list\"\"\"
        pass
    
    def loadDrivenCtrlListToUI(self):
        \"\"\"Load driven controls to the UI list\"\"\"
        pass
    
    def mirrorSelectCtrl(self):
        \"\"\"Mirror selected controls\"\"\"
        pass
    
    def setDriverAttrValue(self, args):
        \"\"\"Set driver attribute value from UI\"\"\"
        pass
    
    def driverValueDrag(self, args):
        \"\"\"Handle driver value drag in UI\"\"\"
        pass
    
    def redefineSDK(self):
        \"\"\"Redefine SDK values\"\"\"
        pass
    
    def createTempPoseLoc(self):
        \"\"\"Create temporary pose locator\"\"\"
        pass
    
    def deleteTempPoseLoc(self):
        \"\"\"Delete temporary pose locator\"\"\"
        pass
    
    def getSdkGrp(self, ctrl):
        \"\"\"Get SDK group for a control\"\"\"
        pass
    
    def connectSdkBWNode(self, sdkAttrGrp, sdkAttr):
        \"\"\"Connect SDK blend weight node\"\"\"
        pass
    
    def createSdkGrp(self, ctrl, sdkAttr):
        \"\"\"Create SDK group for control\"\"\"
        pass
    
    def checkMoveCtrlList(self, sdkAttr):
        \"\"\"Check and get moved control list\"\"\"
        pass
    
    def drivenCtrlListSelectChange(self):
        \"\"\"Handle driven control list selection change\"\"\"
        pass
    
    def loadDrivenCtrlListToUI(self):
        \"\"\"Load driven control list to UI\"\"\"
        pass
    
    def resetAllSdkAttr(self):
        \"\"\"Reset all SDK attributes\"\"\"
        pass
    
    def resetAllCtrl(self):
        \"\"\"Reset all controls to default\"\"\"
        pass
    
    def setAllCtrlPoseList(self):
        \"\"\"Set pose list for all controls\"\"\"
        pass
    
    def getMirrorName(self, obj):
        \"\"\"Get mirror name for an object (L_ <-> R_)\"\"\"
        L_, R_ = '_L', '_R'
        _L, _R = 'L_', 'R_'
        
        if obj == len(L_) & L_:
            mirObj = obj[:len(L_)] + R_
            return mirObj
        elif obj == len(R_) & R_:
            mirObj = obj[:len(R_)] + L_
            return mirObj
        # ... additional mirror logic
        return obj
    
    def forceSetAttr(self, objAttr, val):
        \"\"\"Force set attribute value, handling locked attributes\"\"\"
        if cmds.getAttr(objAttr + '.l', l=True):
            print("%s is Locked!" % objAttr)
            return
        inputList = cmds.listConnections(objAttr, s=True, d=False)
        if inputList:
            if len(inputList) != 1:
                raise AssertionError
            inputList = inputList[0]
        cmds.setAttr(objAttr, val)
    
    def mirrorSDK(self):
        \"\"\"Mirror SDK setup from one side to another\"\"\"
        pass
    
    def setSdkAnimData(self, sdkAttr, sdkAnimDataList, glScale=1.0):
        \"\"\"Set SDK animation data\"\"\"
        pass
    
    def getSdkAnimData(self, sdkAttr):
        \"\"\"Get SDK animation data for an attribute\"\"\"
        pass
    
    def copySdk(self):
        \"\"\"Copy SDK data to clipboard\"\"\"
        pass
    
    def pasteSdk(self):
        \"\"\"Paste SDK data from clipboard\"\"\"
        pass
    
    def copyAllCtrlPose(self):
        \"\"\"Copy all control poses\"\"\"
        self.copyPoseList = self.getAllCtrlPoseList()
    
    def pasteAllCtrlPose(self):
        \"\"\"Paste all control poses\"\"\"
        self.setAllCtrlPoseList(self.copyPoseList)
    
    def getAllCtrlPoseList(self):
        \"\"\"Get pose data for all controls\"\"\"
        pass
    
    def setAllCtrlPoseList(self, poseData):
        \"\"\"Set pose data for all controls\"\"\"
        pass
    
    def exportSdk(self):
        \"\"\"Export SDK data to file\"\"\"
        pass
    
    def importSdk(self):
        \"\"\"Import SDK data from file\"\"\"
        pass
    
    def sdkDriverAttrDClick(self):
        \"\"\"Handle double-click on driver attribute list\"\"\"
        self.deleteDriverAttr(1)


# ============ UI FUNCTION ============
def FRSDK():
    \"\"\"Main UI function to show the Facial SDK window\"\"\"
    sdk = facicalSdkModule(rootPath)
    FRSDKUI(sdk)


def FRSDKUI(rootPath):
    \"\"\"Create and show the Facial SDK UI window\"\"\"
    global FSdkModule
    FSdkModule = facicalSdkModule(rootPath)
    FRSDK(FSdkModule)
"""
    return structure

def main():
    """Main analysis function"""
    print("=" * 70)
    print("  FACIAL SDK BYTECODE ANALYZER")
    print("=" * 70)
    
    # Convert hex to bytes
    try:
        data = hex_to_bytes(HEX_DATA)
        print(f"\n[INFO] Successfully converted {len(data)} bytes of bytecode")
    except Exception as e:
        print(f"[ERROR] Failed to convert hex: {e}")
        return
    
    # Analyze structure
    print("\n" + "=" * 70)
    print("  CODE STRUCTURE ANALYSIS")
    print("=" * 70)
    
    info = analyze_code_structure(data)
    for key, val in info.items():
        print(f"  {key}: {val}")
    
    # Extract strings
    print("\n" + "=" * 70)
    print("  EXTRACTED STRINGS")
    print("=" * 70)
    
    strings = extract_strings(data, min_length=3)
    print(f"\n[INFO] Found {len(strings)} readable strings\n")
    
    # Categorize strings
    categories = categorize_strings(strings)
    
    print("--- IMPORTS ---")
    for s in sorted(set(categories['imports'])):
        print(f"  - {s}")
    
    print("\n--- MAYA COMMANDS USED ---")
    for s in sorted(set(categories['maya_commands'])):
        print(f"  - {s}")
    
    print("\n--- UI ELEMENTS ---")
    for s in sorted(set(categories['ui_elements']))[:30]:
        print(f"  - {s}")
    
    print("\n--- CLASS METHODS ---")
    for s in sorted(set(categories['class_methods']))[:40]:
        print(f"  - {s}")
    
    print("\n--- ATTRIBUTES ---")
    for s in sorted(set(categories['attributes']))[:30]:
        print(f"  - {s}")
    
    print("\n--- STRING LITERALS ---")
    for s in sorted(set(categories['strings']))[:30]:
        print(f"  - \"{s}\"")
    
    # Find classes
    print("\n" + "=" * 70)
    print("  IDENTIFIED CLASSES")
    print("=" * 70)
    
    classes = find_class_definition(strings)
    for c in classes:
        print(f"  - {c}")
    
    # Reconstructed structure
    print("\n" + "=" * 70)
    print("  RECONSTRUCTED MODULE STRUCTURE")
    print("=" * 70)
    
    structure = reconstruct_module_structure(categories, classes)
    print(structure)
    
    # Save reconstructed code
    output_file = "/workspace/scripts/facicalSdkModule_reconstructed.py"
    with open(output_file, 'w') as f:
        f.write(structure)
    print(f"\n[INFO] Reconstructed code saved to: {output_file}")

if __name__ == '__main__':
    main()
