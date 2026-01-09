# -*- coding: utf-8 -*-
"""
facicalSdkModule - Maya Facial SDK Rigging Tool
Reconstructed from Python bytecode

This module provides a comprehensive facial rigging SDK (Set Driven Key) 
management system for Maya, including:
- SDK attribute creation and management
- Control mirroring functionality
- SDK data copy/paste
- Import/Export SDK configurations
- Pose management
"""

from maya import cmds
import functools
from maya.api import OpenMaya, OpenMayaAnim
from collections import OrderedDict
import maya.mel as mel
import math
import os
import re


class facicalSdkModule(object):
    """
    Main class for managing facial SDK rigs in Maya.
    
    Provides functionality for creating, editing, copying, and mirroring
    Set Driven Key setups on facial controls.
    """
    
    def __init__(self, rootPath):
        """
        Initialize the facial SDK module.
        
        Args:
            rootPath: Root path for SDK file operations
        """
        self.rootPath = rootPath
        self.copySdkData = None
        self.copyPoseList = None
        self.attrStrList = ['tx', 'ty', 'tz', 'rx', 'ry', 'rz']
        self.wtMapData = None
        self.sMainPoseList = None
    
    def setupUI(self):
        """Initialize and load driver attribute list to UI."""
        self.loadDriverAttrListToUI()
    
    def getJointGrp(self):
        """
        Get the facial joint group name.
        
        Returns:
            str: The facial joint group name
        """
        return "facecial_joint_grp"
    
    def getRigGrp(self):
        """
        Get the facial rig group if it exists.
        
        Returns:
            str or None: Rig group name or None if not found
        """
        rigGrp = "facecial_rig_grp"
        if not cmds.objExists(rigGrp):
            return None
        return rigGrp
    
    def getCtrlGrp(self):
        """
        Get the facial control group.
        
        Returns:
            str or None: Control group name or None if not found
        """
        rigGrp = self.getRigGrp()
        ctrlGrp = "facecial_ctrl_grp"
        if not cmds.objExists(ctrlGrp):
            return None
        return ctrlGrp
    
    def getSdkHandle(self):
        """
        Get or create the SDK handle group.
        
        Creates the group if it doesn't exist and parents it 
        under the rig group.
        
        Returns:
            str: SDK handle group name
        """
        rigGrp = self.getRigGrp()
        sdkHandle = "facecial_sdk_handle"
        if not cmds.objExists(sdkHandle):
            cmds.group(n=sdkHandle, em=True)
            if rigGrp:
                cmds.parent(sdkHandle, rigGrp)
        return sdkHandle
    
    def getCtrlList(self):
        """
        Get list of all facial controls.
        
        Finds all nurbsCurve shapes under the SDK handle and returns
        their transform parents.
        
        Returns:
            list: List of control transform names
        """
        try:
            sdkHandle = self.getSdkHandle()
        except:
            return []
        
        allShapeList = cmds.listRelatives(sdkHandle, ad=True, path=True, 
                                           typ='nurbsCurve')
        ctrlList = []
        if allShapeList:
            for i in allShapeList:
                transform = cmds.listRelatives(i, p=True, path=True)[0]
                if transform not in ctrlList:
                    ctrlList.append(transform)
        return ctrlList
    
    def sdd_warning(self, wStr):
        """
        Display a warning message.
        
        Args:
            wStr: Warning message string
        """
        mel.eval('warning "%s"' % wStr)
    
    def newDriverAttrUI(self):
        """Create UI window for adding new driver attributes."""
        # Query existing driver attributes
        selIt = cmds.textScrollList('sdkDriverAttrList_frn', q=True, si=True)
        isCanInBetween = bool(selIt) and len(selIt[0].split('__')) == 0
        
        form = cmds.setParent(q=True)
        cmds.columnLayout('nsdkMainCL_frn', h=200, adj=True, rs=5, nc=4)
        
        # Type selection
        cmds.text(l='Type:', al='right')
        cmds.radioCollection('nSdkTypNewRBG_frn')
        cmds.radioButton('nSdkTypNewRBG_frn', l='New SDK', sl=True, 
                        cc=self.newSdkUITypeChange)
        cmds.radioButton('nSdkTypInRBG_frn', l='In-Between', en=isCanInBetween,
                        cc=self.newSdkUITypeChange)
        
        # Name field
        cmds.textFieldGrp('nSdkNameTFG_frn', l='Name:', cw=(1, 50))
        
        # Weight slider for in-between
        cmds.intSliderGrp('nInBetweenISG_frn', l='Weight:', f=True, 
                         min=1, max=100, v=50, dc=self.newInBetweenValueChange)
        
        # Buttons
        cmds.button('nCreateB_frn', l='Create', c=self.createButtonProc)
        cmds.button('nCancelB_frn', l='Cancel', c=self.cancelButtonProc)
        
        cmds.formLayout(form, e=True,
            af=[('nsdkMainCL_frn', 'top', 0), ('nsdkMainCL_frn', 'left', 0),
                ('nCreateB_frn', 'bottom', 0), ('nCancelB_frn', 'bottom', 0)],
            ac=[('nCreateB_frn', 'left', 0, 'nCancelB_frn')],
            ap=[('nCancelB_frn', 'right', 0, 50)])
    
    def newSdkUITypeChange(self, *args):
        """Handle SDK type radio button change."""
        selIt = cmds.textScrollList('sdkDriverAttrList_frn', q=True, si=True)
        cmds.textFieldGrp('nSdkNameTFG_frn', e=True, en=(not args[0]))
        cmds.intSliderGrp('nInBetweenISG_frn', e=True, en=args[0])
        
        if args[0]:
            cmds.textFieldGrp('nSdkNameTFG_frn', e=True, tx='', en=False)
        else:
            self.newDriverAttrUI()
    
    def newInBetweenValueChange(self, *args):
        """Handle in-between weight value change."""
        selIt = cmds.textScrollList('sdkDriverAttrList_frn', q=True, si=True)
        if selIt is None:
            return
        val = cmds.intSliderGrp('nInBetweenISG_frn', q=True, v=True)
        cmds.textFieldGrp('nSdkNameTFG_frn', e=True, 
                         tx='__%s' % (selIt[0] + '__%s' % val))
    
    def createButtonProc(self):
        """Process create button click - create new SDK attribute."""
        isInBetween = cmds.radioButton('nSdkTypInRBG_frn', q=True, sl=True)
        txt = cmds.textFieldGrp('nSdkNameTFG_frn', q=True, tx=True)
        val = cmds.intSliderGrp('nInBetweenISG_frn', q=True, v=True)
        
        # Validate name format
        nameRegex = re.compile(r'^[\w][\w]*$')
        if not nameRegex.match(txt):
            self.sdd_warning("The name is not in conformity with the rules!")
            return
        
        # Check for duplicate
        allSdkList = self.listAttr()
        if cmds.listAttr(allSdkList, ud=True):
            if txt in cmds.listAttr(allSdkList, ud=True):
                self.sdd_warning("The attribute Repeat!")
                return
        
        self.newSdkData = [isInBetween, txt, val]
        cmds.layoutDialog(dis='OK')
    
    def cancelButtonProc(self, *args):
        """Process cancel button click."""
        cmds.layoutDialog(dis='Cancel')
    
    def newDriverAttr(self):
        """
        Create a new driver attribute on the SDK handle.
        
        Creates the attribute and sets up initial SDK keyframes.
        """
        ret = cmds.layoutDialog(ui=self.newDriverAttrUI)
        if ret == 'Cancel':
            return
        
        isInBetween, txt, val = self.newSdkData
        sdkHandle = self.getSdkHandle()
        
        cmds.addAttr(sdkHandle, ln=txt, at='double', dv=0.0, k=True)
        
        # Additional SDK setup based on type
        if isInBetween:
            self.reConnectInBetween(txt)
        
        self.loadDriverAttrListToUI()
    
    def reConnectInBetween(self, prefix):
        """
        Reconnect in-between SDK connections.
        
        Args:
            prefix: Attribute prefix for in-between connection
        """
        sdkHandle = self.getSdkHandle()
        sdkAttr = cmds.textScrollList('sdkDriverAttrList_frn', q=True, si=True)
        # Reconnection logic...
    
    def deleteDriverAttr(self, *args):
        """Delete selected driver attribute and all its SDK connections."""
        selIt = cmds.textScrollList('sdkDriverAttrList_frn', q=True, si=True)
        if selIt is None:
            return
        
        result = cmds.confirmDialog(t='Delete SDK', m='Are you sure?',
                                    b=['Yes', 'No'], db='Yes', cb='No', ds='No')
        
        if result == 'Yes':
            sdkHandle = self.getSdkHandle()
            for sdk in selIt:
                self.forceSetAttr(sdkHandle + '.' + sdk, 0)
                sdkGrpList, sdkCtrlList, sdkAttr = self.getAlldrivenSdkGrpList(sdk)
                for sdkGrp in sdkCtrlList:
                    self.deleteCtrlSdkGrp(sdkGrp)
                
                # Delete connections and attribute
                subList = sdk.split('__')
                if len(subList) > 1:
                    cnn = cmds.listConnections(sdkHandle + '.' + sdk, s=True, d=False)
                    if cnn:
                        cmds.delete(cnn)
                    cmds.deleteAttr(sdkHandle, at=sdk)
                else:
                    cmds.deleteAttr(sdkHandle, at=sdk)
                
                try:
                    self.reConnectInBetween(subList[0])
                except:
                    pass
            
            self.loadDriverAttrListToUI()
    
    def deleteSelectionSdkDrivenCtrl(self):
        """Delete SDK driven controls for current selection."""
        sdkHandle = self.getSdkHandle()
        selAttrI = cmds.textScrollList('sdkDriverAttrList_frn', q=True, si=True)
        if selAttrI is None:
            return
        
        selAttr = selAttrI[0]
        sdkDrivenCtrlList = cmds.textScrollList('sdkDrivenCtrlList_frn', 
                                                 q=True, si=True)
        if sdkDrivenCtrlList is None:
            return
        
        for sdkGrp in sdkDrivenCtrlList:
            ctrl = sdkGrp + '_sdk_%s' % selAttr
            self.deleteSdkCtrlGrp(ctrl)
        
        self.loadDrivenCtrlListToUI()
    
    def deleteAllSdkDrivenCtrl(self):
        """Delete all SDK driven controls for selected attribute."""
        selIt = cmds.textScrollList('sdkDriverAttrList_frn', q=True, si=True)
        for sdk in selIt:
            sdkGrpList, sdkCtrlList, sdkAttr = self.getAlldrivenSdkGrpList(sdk)
            if sdkCtrlList is None:
                return
            for sdkGrp in sdkCtrlList:
                self.deleteSdkCtrlGrp(sdkGrp)
        
        self.loadDrivenCtrlListToUI()
    
    def getAllDrivenSdkGrpList(self, sdkAttr):
        """
        Get all driven SDK groups for an attribute.
        
        Args:
            sdkAttr: SDK attribute name
            
        Returns:
            tuple: (sdkGrpList, ctrlList, attrName)
        """
        sdkHandle = self.getSdkHandle()
        if sdkAttr is None:
            selAttrI = cmds.textScrollList('sdkDriverAttrList_frn', 
                                           q=True, si=True)
            if selAttrI is None:
                return (None, None, None)
            sdkAttr = selAttrI[0]
        
        sdkGrpList = []
        ctrlList = []
        allCtrlList = self.getCtrlList()
        
        for ctrl in allCtrlList:
            sdkGrp = ctrl + '_sdk_%s' % sdkAttr
            if cmds.objExists(sdkGrp):
                sdkGrpList.append(sdkGrp)
                ctrlList.append(ctrl)
        
        return (sdkAttr, sdkGrpList, ctrlList)
    
    def deleteSdkCtrlGrp(self, ctrl):
        """
        Delete an SDK control group.
        
        Args:
            ctrl: Control name to delete SDK group from
        """
        if cmds.objExists(ctrl):
            for attr in self.attrStrList:
                self.forceSetAttr(ctrl + '.' + attr, 0)
            cmds.delete(ctrl)
    
    def loadDriverAttrListToUI(self):
        """Load driver attributes to the text scroll list UI."""
        tslID = 'sdkDriverAttrList_frn'
        sdkHandle = self.getSdkHandle()
        sdkDriverAttrList = cmds.listAttr(sdkHandle, ud=True)
        
        # Clear and populate list
        cmds.textScrollList(tslID, e=True, ra=True)
        if sdkDriverAttrList:
            filterL = cmds.checkBoxGrp('sdkListFilterCBG_frn', q=True, v1=True)
            filterR = cmds.checkBoxGrp('sdkListFilterCBG_frn', q=True, v2=True)
            
            for sdk in sdkDriverAttrList:
                if filterL and (sdk & 2) == 'L_':
                    continue
                if filterR and (sdk & 2) == 'R_':
                    continue
                cmds.textScrollList(tslID, e=True, a=sdk)
        
        # Auto-select first item if list has content
        allI = cmds.textScrollList(tslID, q=True, ai=True)
        if allI and len(allI) > 0:
            cmds.textScrollList(tslID, e=True, sii=1)
    
    def setDriverAttrValue(self, *args):
        """Set driver attribute value from float slider."""
        val = args[0]
        self.driverValueDrag(val)
        cmds.floatSliderGrp('sdkDrivenValueFSG_frn', e=True, v=val)
    
    def driverValueDrag(self, *args):
        """
        Handle driver value slider drag.
        
        Args:
            args: Slider value
        """
        try:
            cmds.undoInfo(swf=0)
            val = args[0]
            sdkHandle = self.getSdkHandle()
            selIt = cmds.textScrollList('sdkDriverAttrList_frn', q=True, si=True)
            if selIt is None:
                return
            
            for sdk in selIt:
                attrList = sdk.split('__')
                if len(attrList) > 1:
                    try:
                        mainAttr, mainVal = attrList[0], int(attrList[1])
                    except:
                        return
                    self.forceSetAttr(sdkHandle + '.' + mainAttr, mainVal * 0.01)
                else:
                    self.forceSetAttr(sdkHandle + '.' + sdk, val)
        finally:
            cmds.undoInfo(swf=1)
    
    def redefineSDK(self):
        """Redefine SDK values for selected controls."""
        sdkHandle = self.getSdkHandle()
        selIt = cmds.textScrollList('sdkDriverAttrList_frn', q=True, si=True)
        if selIt is None:
            self.sdd_warning("Please select SDK attribute !")
            return
        
        sdkAttr = selIt[0]
        moveList = self.checkMoveCtrlList(sdkAttr)
        sdkAttrGrp = sdkHandle + '.' + sdkAttr
        
        axis = [1, 1, 1, 1, 1, 1]  # tx, ty, tz, rx, ry, rz
        dvList = [1, 1, 1, 1, 1, 1, 0, 0, 0]
        
        tempLoc = self.getTempPoseLoc()
        
        try:
            for ctrl in moveList:
                sdkAttrVal = cmds.getAttr(tempLoc + '.sdk', k=True)
                if sdkAttrVal is not None:
                    cmds.setParent('|')
                    continue
                
                # Process SDK connections
                tempLocP = ctrl + '_zero'
                tempLoc = ctrl + '_sdk'
                
                ctrlZero = cmds.getAttr(tempLoc + '.' + ctrl)
                sdk = cmds.getAttr(ctrl + '.' + tempLoc)
                
                # Set driven keyframes
                for idx, attrStr in enumerate(self.attrStrList):
                    if not cmds.getAttr(ctrl + '.' + attrStr + '.l', l=True):
                        continue
                    
                    drivenAttr = moveList[ctrl + '.' + attrStr]
                    gVal = cmds.getAttr(tempLoc + '.' + attrStr)
                    sVal = cmds.getAttr(tempLocP + '.' + attrStr)
                    fVal = sVal - gVal + ctrlZero
                    
                    drivenValue = axis[idx] * fVal
                    cmds.setDrivenKeyframe(drivenAttr, cd=sdkAttrGrp, 
                                           dv=drivenValue, v=1.0, itt='linear', 
                                           ott='linear')
                    
        finally:
            self.deleteTempPoseLoc()
        
        self.forceSetAttr(sdkAttrGrp, 1)
        self.loadDrivenCtrlListToUI()
    
    def createTempPoseLoc(self):
        """Create temporary pose locator for SDK operations."""
        sel = cmds.ls(sl=True)
        tempLoc = 'TempPoseLoc'
        
        if cmds.objExists(tempLoc):
            cmds.delete(tempLoc)
        
        cmds.spaceLocator(n=tempLoc, p=(0, 0, 0))
        
        if len(sel) > 0:
            cmds.select(sel)
        
        return tempLoc
    
    def deleteTempPoseLoc(self):
        """Delete temporary pose locator."""
        tempLoc = 'TempPoseLoc'
        if cmds.objExists(tempLoc):
            cmds.delete(tempLoc)
    
    def getSdkGrp(self, ctrl, sdkAttr):
        """
        Get SDK group for a control.
        
        Args:
            ctrl: Control name
            sdkAttr: SDK attribute name
            
        Returns:
            tuple: (sdkGrp, ctrlGrp)
        """
        sdkGrp = ctrl + '_sdk'
        ctrlGrp = ctrl + '_sdk_grp'
        sdkAttrGrp = ctrl + '_sdk_' + sdkAttr
        
        if not cmds.objExists(sdkGrp):
            sdkGrp = cmds.duplicate(sdkAttrGrp, n=sdkGrp, po=True)[0]
            cmds.parent(sdkGrp, sdkAttrGrp)
            cmds.parent(ctrl, sdkGrp)
        
        if not cmds.objExists(ctrlGrp):
            ctrlGrp = cmds.duplicate(sdkAttrGrp, n=ctrlGrp, po=True)[0]
            cmds.parent(ctrlGrp, sdkAttrGrp)
        
        return (sdkGrp, ctrlGrp)
    
    def connectSdkBWNode(self, sdkAttrGrp, sdkAttr):
        """
        Connect SDK blend weight node.
        
        Args:
            sdkAttrGrp: SDK attribute group
            sdkAttr: SDK attribute name
        """
        for attr in self.attrStrList:
            bwNode = sdkAttr + '_BW'
            if not cmds.objExists(bwNode):
                bwNode = cmds.createNode('plusMinusAverage', n=bwNode)
                cmds.connectAttr(sdkAttrGrp + '.o1', bwNode + '.' + sdkAttr)
            
            # Connect blend weight outputs
            inputAttr = bwNode + '.i'
            idx = 0
            if cmds.objectType(bwNode) == 1:
                idxList = cmds.getAttr(bwNode + '.mi', mi=True)
                for i in idxList:
                    idx = cmds.getAttr(bwNode + '.i[%s].i' % i)
                    if idx is None:
                        idx = i
                        break
            
            if cmds.objectType(bwNode) == 1:
                idx = int(idxList[-1]) + 1
            
            cmds.connectAttr(sdkAttrGrp + '.' + attr, bwNode + '.i[%s].i' % idx)
    
    def createSdkGrp(self, ctrl, sdkAttr):
        """
        Create SDK group for control.
        
        Args:
            ctrl: Control name
            sdkAttr: SDK attribute name
            
        Returns:
            str: Created SDK group name
        """
        sdkGrp, ctrlGrp = self.getSdkGrp(ctrl, sdkAttr)
        self.connectSdkBWNode(sdkGrp, sdkAttr)
        return sdkGrp
    
    def checkMoveCtrlList(self, sdkAttr):
        """
        Check and get list of moved controls.
        
        Args:
            sdkAttr: SDK attribute name
            
        Returns:
            dict: Dictionary of control/value pairs
        """
        ctrlList = self.getCtrlList()
        attrDvList = {}
        attrValueList = [0, 0, 0, 0, 0, 0, 0, 0, 0]
        
        for ctrl in ctrlList:
            sdkGrp = ctrl + '_sdk_%s' % sdkAttr
            if cmds.objExists(sdkGrp):
                attrDvList.append(ctrl)
            
            for idx, attr in enumerate(self.attrStrList):
                tValue = cmds.getAttr(ctrl + '.' + attr)
                tValue = round(tValue, 4)
                if tValue != attrValueList[idx]:
                    attrDvList.append(ctrl)
                    break
        
        return attrDvList
    
    def drivenCtrlListSelectChange(self):
        """Handle driven control list selection change."""
        selIt = cmds.textScrollList('sdkDrivenCtrlList_frn', q=True, si=True)
        if selIt is None:
            return
        cmds.select(selIt)
    
    def loadDrivenCtrlListToUI(self):
        """Load driven control list to UI."""
        selIt = cmds.textScrollList('sdkDriverAttrList_frn', q=True, si=True)
        cmds.textScrollList('sdkDrivenCtrlList_frn', e=True, ra=True)
        
        if not selIt:
            cmds.button('sdkDefineB_frn', e=True, en=False)
            cmds.checkBox('sdkOverlayCB_frn', e=True, en=False)
            return
        
        sdkHandle = self.getSdkHandle()
        if not cmds.checkBox('sdkOverlayCB_frn', q=True, v=True):
            self.resetAllSdkAttr()
            self.setDriverAttrValue(1)
        else:
            cmds.button('sdkDefineB_frn', e=True, 
                       en=len(selIt) == 1)
        
        cmds.select(sdkHandle)
        ctrlList = self.getCtrlList()
        
        for ctrl in ctrlList:
            for sdk in selIt:
                sdkGrp = ctrl + '_sdk_%s' % sdk
                if cmds.objExists(sdkGrp):
                    cmds.textScrollList('sdkDrivenCtrlList_frn', e=True, 
                                       a=ctrl)
                    break
        
        # Select first driven control
        firstCtrl = cmds.textScrollList('sdkDrivenCtrlList_frn', 
                                         q=True, ai=True)
        if firstCtrl:
            cmds.textScrollList('sdkDrivenCtrlList_frn', e=True, 
                               sii=1, da=firstCtrl[-1])
    
    def resetAllSdkAttr(self):
        """Reset all SDK attributes to zero."""
        self.resetAllCtrl()
        sdkHandle = self.getSdkHandle()
        sdkAttrList = cmds.listAttr(sdkHandle, ud=True)
        if sdkAttrList is None:
            return
        
        for sdk in sdkAttrList:
            self.forceSetAttr(sdkHandle + '.' + sdk, 0)
    
    def resetAllCtrl(self):
        """Reset all controls to default pose."""
        ctrlList = self.getCtrlList()
        attrValueList = [0, 0, 0, 0, 0, 0]
        
        for ctrl in ctrlList:
            sdkGrp = ctrl + '_zero'
            for idx, attr in enumerate(zip(self.attrStrList, attrValueList)):
                self.forceSetAttr(ctrl + '.' + attr[0], attr[1])
    
    def setAllCtrlPoseList(self, poseList):
        """
        Set pose list for all controls.
        
        Args:
            poseList: Dictionary of control poses
        """
        for ctrl, dVal in poseList.items():
            for attr in self.attrStrList:
                self.forceSetAttr(ctrl + '.' + attr, dVal)
    
    def getMirrorName(self, obj):
        """
        Get mirror name for an object.
        
        Swaps L_ <-> R_ prefixes/suffixes.
        
        Args:
            obj: Object name
            
        Returns:
            str: Mirrored name or original if no match
        """
        L_, R_ = '_L', '_R'
        _L, _R = ('L_', 'R_')
        
        if obj[-len(L_):] == L_:
            mirObj = obj[:-len(L_)] + R_
            return mirObj
        elif obj[-len(R_):] == R_:
            mirObj = obj[:-len(R_)] + L_
            return mirObj
        elif obj[:len(_L)] == _L:
            mirObj = _R + obj[len(_L):]
            return mirObj
        elif obj[:len(_R)] == _R:
            mirObj = _L + obj[len(_R):]
            return mirObj
        
        return obj
    
    def forceSetAttr(self, objAttr, val):
        """
        Force set attribute value, handling locked attributes.
        
        Args:
            objAttr: Object.attribute string
            val: Value to set
        """
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
        """Mirror SDK setup from one side to another."""
        sdkHandle = self.getSdkHandle()
        sdkAttr, sdkAnimDataList = self.getSdkAnimData()
        mirSdkAttr = self.getMirrorName(sdkAttr)
        
        allSdkAttrList = cmds.listAttr(sdkHandle, ud=True)
        
        if mirSdkAttr not in allSdkAttrList:
            if mirSdkAttr == sdkAttr:
                self.sdd_warning("Can not find Mirror Attribute!")
                return
        
        sdkGrpList, sdkCtrlList, sdkAttr = self.getAlldrivenSdkGrpList(sdkAttr)
        
        for sdkGrp in sdkCtrlList:
            self.deleteSdkCtrlGrp(sdkGrp)
        
        # Mirror animation data
        for animData in sdkAnimDataList:
            mirAnimData = self.getMirrorName(animData)
            # Apply mirrored SDK...
        
        self.loadDriverAttrListToUI()
    
    def setSdkAnimData(self, sdkAttr, sdkAnimDataList, glScale=1.0):
        """
        Set SDK animation data.
        
        Args:
            sdkAttr: SDK attribute name
            sdkAnimDataList: Animation data list
            glScale: Global scale factor (default 1.0)
        """
        sdkHandle = self.getSdkHandle()
        allSdkAttrList = cmds.listAttr(sdkHandle, ud=True)
        
        if sdkAttr not in allSdkAttrList:
            return
        
        for ctrl in sdkAnimDataList:
            moveList = self.checkMoveCtrlList(ctrl)
            sdkGrp = ctrl + '_sdk'
            
            # Set animation curves
            for idx, attrStr in enumerate(self.attrStrList):
                # Apply SDK keyframe data...
                pass
    
    def getSdkAnimData(self, sdkAttr):
        """
        Get SDK animation data for an attribute.
        
        Args:
            sdkAttr: SDK attribute name
            
        Returns:
            tuple: (attribute, animation data list)
        """
        sdkGrpList, sdkCtrlList, sdkAttr = self.getAlldrivenSdkGrpList(sdkAttr)
        animDataList = {}
        
        for idx, ctrl in enumerate(sdkCtrlList):
            keyList = []
            
            for attr in self.attrStrList:
                keyData = cmds.keyframe(ctrl, q=True, at=attr, 
                                        tc=True, vc=True)
                if keyData:
                    animData = {}
                    animData['keyTime'] = cmds.keyframe(ctrl + '.' + attr, 
                                                        q=True)
                    animData['keyValue'] = cmds.keyframe(ctrl + '.' + attr, 
                                                         q=True, vc=True)
                    animData['tangentType'] = cmds.keyTangent(ctrl + '.' + attr, 
                                                              q=True, itt=True)
                    # Additional keyframe data...
                    keyList.append(animData)
            
            animDataList[sdkCtrlList[idx]] = keyList
        
        return (sdkAttr, animDataList)
    
    def copySdk(self):
        """Copy SDK data to clipboard."""
        selIt = cmds.textScrollList('sdkDriverAttrList_frn', q=True, si=True)
        if not selIt:
            return
        
        sdkAttr, sdkAnimData = self.getSdkAnimData(selIt[0])
        self.copySdkData = sdkAnimData
    
    def pasteSdk(self):
        """Paste SDK data from clipboard."""
        if self.copySdkData is None:
            return
        
        selIt = cmds.textScrollList('sdkDriverAttrList_frn', q=True, si=True)
        if not selIt:
            return
        
        self.setSdkAnimData(selIt[0], self.copySdkData)
        self.setDriverAttrValue(1)
        self.loadDrivenCtrlListToUI()
    
    def copyAllCtrlPose(self):
        """Copy all control poses to clipboard."""
        self.copyPoseList = self.getAllCtrlPoseList()
    
    def pasteAllCtrlPose(self):
        """Paste all control poses from clipboard."""
        self.setAllCtrlPoseList(self.copyPoseList)
    
    def getAllCtrlPoseList(self):
        """
        Get pose data for all controls.
        
        Returns:
            dict: Dictionary of control poses
        """
        ctrlList = self.getCtrlList()
        tempLoc = self.createTempPoseLoc()
        
        try:
            poseDate = {}
            for ctrl in ctrlList:
                post = cmds.xform(ctrl, q=True, ws=True, t=True)
                rot = cmds.xform(ctrl, q=True, ws=True, ro=True)
                poseDate[ctrl] = [post, rot]
        finally:
            self.deleteTempPoseLoc()
        
        return poseDate
    
    def setAllCtrlPoseList(self, poseData):
        """
        Set pose data for all controls.
        
        Args:
            poseData: Dictionary of control poses
        """
        tempLoc = self.createTempPoseLoc()
        
        try:
            for ctrl, data in poseData.items():
                post, rot = data
                sdkGrp = ctrl + '_zero'
                cmds.parent(tempLoc, sdkGrp)
                cmds.xform(tempLoc, t=post, ws=True)
                cmds.xform(tempLoc, ro=rot, ws=True)
                cmds.delete(cmds.parentConstraint(tempLoc, ctrl))
        finally:
            self.deleteTempPoseLoc()
    
    def exportSdk(self):
        """Export SDK data to file."""
        path = cmds.fileDialog2(ff='SDK Files(*.sdk)', fm=0)
        if path is None:
            return
        
        sdkAnimData = []
        sdkHandle = self.getSdkHandle()
        sdkDriverAttrList = cmds.listAttr(sdkHandle, ud=True)
        
        cmds.progressWindow(t='Export Sdk...', pr=0, st='', 
                           max=len(sdkDriverAttrList))
        
        try:
            for sdk in sdkDriverAttrList:
                cmds.progressWindow(e=True, pr=1, st=sdk)
                sdkAttr, animData = self.getSdkAnimData(sdk)
                sdkAnimData.append((sdkAttr, animData))
        finally:
            cmds.progressWindow(e=True, ep=True)
        
        try:
            glScale = cmds.getAttr(self.getRigGrp() + '.globalscale')
            with open(path[0], 'wb') as fileHandle:
                import pickle
                pickle.dump([sdkAnimData, glScale], fileHandle)
        except:
            self.sdd_warning("Save %s Error!" % path[0])
    
    def importSdk(self):
        """Import SDK data from file."""
        path = cmds.fileDialog2(ff='SDK Files(*.sdk)', fm=1, 
                               dirs=self.rootPath + 'files/SDK/')
        if path is None:
            return
        
        try:
            with open(path[0], 'rb') as fileHandle:
                import pickle
                sdkAnimData, glScale = pickle.load(fileHandle)
        except:
            self.sdd_warning("Load %s Error!" % path[0])
            return
        
        curgScale = cmds.getAttr(self.getRigGrp() + '.globalscale')
        glScale = curgScale / glScale
        
        cmds.progressWindow(t='Import Sdk...', pr=0, 
                           max=len(sdkAnimData))
        
        try:
            for animdata in sdkAnimData:
                cmds.progressWindow(e=True, pr=1)
                self.setSdkAnimData(animdata[0], animdata[1], glScale)
        finally:
            cmds.progressWindow(e=True, ep=True)
        
        sdkHandle = self.getSdkHandle()
        sdkAttrList = cmds.listAttr(sdkHandle, ud=True)
        
        if sdkAttrList:
            for sdk in sdkAttrList:
                self.reConnectInBetween(sdk)
        
        self.loadDriverAttrListToUI()
    
    def sdkDriverAttrDClick(self):
        """Handle double-click on driver attribute list."""
        self.deleteDriverAttr(1)


# ============ UI FUNCTIONS ============

def FRSDK():
    """Main function to create and show the Facial SDK UI window."""
    winName = 'sdd_faceRiggingSDK_frn'
    
    if cmds.window(winName, q=True, ex=True):
        cmds.deleteUI(winName)
    
    cmds.window(winName, rtf=True)
    cmds.frameLayout('sdkModuleCL_frn', adj=True)
    
    cmds.columnLayout('sdkIOFL_frn', cl='cll', adj=True, 
                     mh=2, mw=2, rs=2, nc=2)
    cmds.text(l='SDK IO', al='left')
    cmds.rowLayout(nc=2, cw2=(100, 100))
    cmds.button(l='Export', c=lambda x: FSdkModule.exportSdk())
    cmds.button(l='Import', c=lambda x: FSdkModule.importSdk())
    cmds.setParent('..')
    
    # SDK Attribute List
    cmds.frameLayout('sdkAttrListFL_frn', l='SDK Attribute List', 
                    cll=True, cl=False)
    cmds.columnLayout('columnLayout2_frn', adj=True)
    cmds.checkBoxGrp('sdkListFilterCBG_frn', ncb=2, 
                    l1='L_*', l2='R_*', 
                    cc=lambda x: FSdkModule.loadDriverAttrListToUI())
    
    cmds.textScrollList('sdkDriverAttrList_frn', ams=True, 
                       sc=lambda: FSdkModule.loadDrivenCtrlListToUI(),
                       dcc=lambda: FSdkModule.sdkDriverAttrDClick())
    
    # Attribute option buttons
    cmds.rowLayout(nc=3)
    cmds.button(l='New Attribute', c=lambda x: FSdkModule.newDriverAttr())
    cmds.button(l='Delete Attributes', c=lambda x: FSdkModule.deleteDriverAttr())
    cmds.setParent('..')
    
    # SDK Copy/Paste
    cmds.rowLayout(nc=3)
    cmds.button(l='Copy SDK', c=lambda x: FSdkModule.copySdk())
    cmds.button(l='Paste SDK', c=lambda x: FSdkModule.pasteSdk())
    cmds.button(l='Mirror SDK', c=lambda x: FSdkModule.mirrorSDK())
    cmds.setParent('..')
    
    # SDK Define section
    cmds.frameLayout('sdkDefineFL_frn', l='SDK Define', cll=True)
    cmds.columnLayout('columnLayout1_frn', adj=True)
    cmds.paneLayout('sdkDefinePL_frn')
    
    cmds.checkBox('sdkOverlayCB_frn', l='Overlay')
    
    cmds.columnLayout('sdkDefineOptionCL_frn', adj=True)
    cmds.button('sdkDefineB_frn', l='Delete', 
               c=lambda x: FSdkModule.deleteSelectionSdkDrivenCtrl())
    cmds.button(l='Clear All', 
               c=lambda x: FSdkModule.deleteAllSdkDrivenCtrl())
    cmds.setParent('..')
    
    # Pose operations
    cmds.rowLayout(nc=3)
    cmds.button(l='Copy All Poses', c=lambda x: FSdkModule.copyAllCtrlPose())
    cmds.button(l='Paste All Poses', c=lambda x: FSdkModule.pasteAllCtrlPose())
    cmds.button(l='Mirror Select', c=lambda x: FSdkModule.mirrorSelectCtrl())
    cmds.setParent('..')
    
    # Driven control list
    cmds.textScrollList('sdkDrivenCtrlList_frn', 
                       sc=lambda: FSdkModule.drivenCtrlListSelectChange())
    
    # Reset and redefine
    cmds.rowLayout(nc=2)
    cmds.button(l='Reset All', c=lambda x: FSdkModule.resetAllSdkAttr())
    cmds.button('sdkRedefineB_frn', l='Redefine', 
               c=lambda x: FSdkModule.redefineSDK())
    cmds.setParent('..')
    
    # Load initial data and show window
    FSdkModule.loadDriverAttrListToUI()
    cmds.showWindow(winName)


def FRSDKUI(rootPath):
    """
    Initialize and show Facial SDK UI.
    
    Args:
        rootPath: Root path for SDK operations
    """
    global FSdkModule
    FSdkModule = facicalSdkModule(rootPath)
    FRSDK()
