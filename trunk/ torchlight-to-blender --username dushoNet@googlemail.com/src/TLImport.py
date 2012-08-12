#!BPY

"""
Name: 'OGRE for Torchlight (*.MESH)'
Blender: 2.59 and 2.62
Group: 'Import/Export'
Tooltip: 'Import/Export Torchlight OGRE mesh files'
    
Author: Dusho
"""

__author__ = "Dusho"
__version__ = "0.5 06-Mar-2012"

__bpydoc__ = """\
This script imports Torchlight Ogre models into Blender.

Supported:<br>
    * import/export of basic meshes

Missing:<br>   
    * vertex weights
    * skeletons
    * animations
    * vertex color import/export

Known issues:<br>
    * meshes with skeleton info will loose that info (vertex weights, skeleton link, ...)
     
History:<br>
    * v0.5     (06-Mar-2012) - added material import/export
    * v0.4.1   (29-Feb-2012) - flag for applying transformation, default=true
    * v0.4     (28-Feb-2012) - fixing export when no UV data are present
    * v0.3     (22-Feb-2012) - WIP - started cleaning + using OgreXMLConverter
    * v0.2     (19-Feb-2012) - WIP - working export of geometry and faces
    * v0.1     (18-Feb-2012) - initial 2.59 import code (from .xml)
    * v0.0     (12-Feb-2012) - file created
"""

"""
When importing: (x)-Blender, (x')-Ogre
vectors: x=x', y=-z', z=y'
UVtex: u=u', v = -v'+1

Inner data representation:
MESHDATA:
['sharedgeometry']: {}
    ['positions'] - vectors with [x,y,z]
    ['normals'] - vectors with [x,y,z]
    ['vertexcolors'] - vectors with [r,g,b,a]
    ['texcoordsets'] - integer (number of UV sets)
    ['uvsets'] - vectors with [u,v] * number or UV sets for vertex [[u,v]][[u,v]]...
    ['boneassignments']: {[boneName]} - for every bone name:
        [[vertexNumber], [weight]], [[vertexNumber], [weight]],  ..
['submeshes'][idx]
        [material] - string (material name)
        [faces] - vectors with faces [v1,v2,v3]
        [geometry] - identical to 'sharedgeometry' data content   
['materials']
    [(matID)]: {}
        ['texture path'] - full path to texture file
['skeleton']: {[boneName]} for each bone
        ['name'] - bone name
        ['id'] - bone ID
        ['position'] - bone position [x,y,z]
        ['rotation'] - bone rotation [x,y,z,angle]
        ['parent'] - bone name of parent bone
        ['children'] - list with names if children ([child1, child2, ...])
['boneIDs']: {[bone ID]:[bone Name]} - dictionary with ID to name
    
"""

#from Blender import *
from xml.dom import minidom
import bpy
from mathutils import Vector, Matrix
import math
import os

SHOW_IMPORT_DUMPS = False
SHOW_IMPORT_TRACE = False
# default blender version of script
blender_version = 259

#ogreXMLconverter=None

# makes sure name doesn't exceeds blender naming limits
# also keeps after name (as Torchlight uses names to identify types -boots, chest, ...- with names)
# TODO: this is not needed for Blender 2.62 and above
def GetValidBlenderName(name):
    
    global blender_version
    
    maxChars = 20
    if blender_version>262:
        maxChars = 63
    
    newname = name    
    if(len(name) > maxChars):
        if(name.find("/") >= 0):
            if(name.find("Material") >= 0):
                # replace 'Material' string with only 'Mt'
                newname = name.replace("Material","Mt")
            # check if it's still above 20
            if(len(newname) > maxChars):
                suffix = newname[newname.find("/"):]
                prefix = newname[0:(maxChars+1-len(suffix))]
                newname = prefix + suffix
        else:
            newname = name[0:maxChars+1]            
    if(newname!=name):
        print("WARNING: Name truncated (" + name + " -> " + newname + ")")
            
    return newname

def fileExist(filepath):
    try:
        filein = open(filepath)
        filein.close()
        return True
    except:
        print ("No file: ", filepath)
        return False

def xOpenFile(filename):
    xml_file = open(filename)    
    try:
        xml_doc = minidom.parse(xml_file)
        output = xml_doc
    except:
        print ("File not valid!")
        output = 'None'
    xml_file.close()
    return output

def xCollectFaceData(facedata):
    faces = []
    for face in facedata.childNodes:
        if face.localName == 'face':
            v1 = int(face.getAttributeNode('v1').value)
            v2 = int(face.getAttributeNode('v2').value)
            v3 = int(face.getAttributeNode('v3').value)
            faces.append([v1,v2,v3])
    
    return faces

def xCollectVertexData(data):
    vertexdata = {}
    vertices = []
    normals = []
    vertexcolors = []
    
    for vb in data.childNodes:
        if vb.localName == 'vertexbuffer':
            if vb.hasAttribute('positions'):
                for vertex in vb.getElementsByTagName('vertex'):
                    for vp in vertex.childNodes:
                        if vp.localName == 'position':
                            x = float(vp.getAttributeNode('x').value)
                            y = -float(vp.getAttributeNode('z').value)
                            z = float(vp.getAttributeNode('y').value)
                            vertices.append([x,y,z])
                vertexdata['positions'] = vertices            
            
            if vb.hasAttribute('normals'):
                for vertex in vb.getElementsByTagName('vertex'):
                    for vn in vertex.childNodes:
                        if vn.localName == 'normal':
                            x = float(vn.getAttributeNode('x').value)
                            y = -float(vn.getAttributeNode('z').value)
                            z = float(vn.getAttributeNode('y').value)
                            normals.append([x,y,z])
                vertexdata['normals'] = normals                
            
            if vb.hasAttribute('colours_diffuse'):
                for vertex in vb.getElementsByTagName('vertex'):
                    for vcd in vertex.childNodes:
                        if vcd.localName == 'colour_diffuse':
                            rgba = vcd.getAttributeNode('value').value
                            r = float(rgba.split()[0])
                            g = float(rgba.split()[1])
                            b = float(rgba.split()[2])
                            a = float(rgba.split()[3])
                            vertexcolors.append([r,g,b,a])
                vertexdata['vertexcolors'] = vertexcolors
            
            if vb.hasAttribute('texture_coord_dimensions_0'):
                texcosets = int(vb.getAttributeNode('texture_coords').value)
                vertexdata['texcoordsets'] = texcosets
                uvcoordset = []
                for vertex in vb.getElementsByTagName('vertex'):
                    uvcoords = []
                    for vt in vertex.childNodes:
                        if vt.localName == 'texcoord':
                            u = float(vt.getAttributeNode('u').value)
                            v = -float(vt.getAttributeNode('v').value)+1.0
                            uvcoords.append([u,v])
                                
                    if len(uvcoords) > 0:
                        uvcoordset.append(uvcoords)
                vertexdata['uvsets'] = uvcoordset                
                        
    return vertexdata

def xCollectMeshData(meshData, xmldoc, meshname, dirname):
    #global has_skeleton
    #meshData = {}
    faceslist = []
    subMeshData = []
    allObjs = []
    isSharedGeometry = False
    sharedGeom = []
    
    # collect shared geometry    
    if(len(xmldoc.getElementsByTagName('sharedgeometry')) > 0):
        for subnodes in xmldoc.getElementsByTagName('sharedgeometry'):
            meshData['sharedgeometry'] = xCollectVertexData(subnodes)
        for subnodes in xmldoc.getElementsByTagName('sharedgeometry'):
            meshData['sharedgeometry']['boneassignments'] = xCollectBoneAssignments(meshData, xmldoc)
            
    # collect submeshes data       
    for submeshes in xmldoc.getElementsByTagName('submeshes'):
        for submesh in submeshes.childNodes:
            if submesh.localName == 'submesh':
                material = str(submesh.getAttributeNode('material').value)
                # to avoid Blender naming limit problems
                material = GetValidBlenderName(material)
                sm = {}
                sm['material']=material
                for subnodes in submesh.childNodes:
                    if subnodes.localName == 'faces':
                        facescount = int(subnodes.getAttributeNode('count').value)                        
                        sm['faces']=xCollectFaceData(subnodes)
                    
                        if len(xCollectFaceData(subnodes)) != facescount:
                            print ("FacesCount doesn't match!")
                            break 
                    
                    if (subnodes.localName == 'geometry'):
                        vertexcount = int(subnodes.getAttributeNode('vertexcount').value)
                        sm['geometry']=xCollectVertexData(subnodes)
                                                                   
                    if subnodes.localName == 'boneassignments':
                         sm['geometry']['boneassignments']=xCollectBoneAssignments(meshData, xmldoc)
#                        sm.append(collectBoneAssignments(subnodes))    
#                        sm['boneassignments']=
                        
                subMeshData.append(sm)
                
    meshData['submeshes']=subMeshData
            
    return meshData

def xCollectMaterialData(meshData, materialFile, folder):
    try:
        filein = open(materialFile)
    except:
        print ("Material: File", materialFile, "not found!")
        return 'None' 
    data = filein.readlines()
    filein.close()
    MaterialDic = {}
    
    count = 0
    for line in data:
        if "material" in line:
            MaterialName = line.split()[1]
            # to avoid Blender naming limit problems
            MaterialName = GetValidBlenderName(MaterialName)
            MaterialDic[MaterialName] = []
            count = 0
        if "{" in line:
            count += 1
        if  count > 0:
            MaterialDic[MaterialName].append(line)
        if "}" in line:
            count -= 1
    allMaterials = {}
    #print(MaterialDic)
    for Material in MaterialDic.keys():
        count = 0
        matDict = {}
        allMaterials[Material] = matDict   
        if SHOW_IMPORT_TRACE:     
            print ("Materialname: ", Material)
        for line in MaterialDic[Material]:
            #if "texture_unit" in line:
                #allMaterials[Material] = ""
                #count = 0
            if "{" in line:
                count+=1
            # texture
            if (count > 0) and ("texture " in line):
                file = os.path.join(folder, (line.split()[1]))                        
                if(not os.path.isfile(file)):
                    # just force to use .dds if there isn't file specified in material file
                    file = os.path.join(folder, os.path.splitext((line.split()[1]))[0] + ".dds")
                matDict['texture'] = file
            # ambient color
            if(count>0) and ("ambient" in line):
                lineSplit = line.split()
                if len(lineSplit)>=4:
                    r=float(lineSplit[1])
                    g=float(lineSplit[2])
                    b=float(lineSplit[3])
                    matDict['ambient'] = [r,g,b]
            # diffuse color        
            if(count>0) and ("diffuse" in line):
                lineSplit = line.split()
                if len(lineSplit)>=4:
                    r=float(lineSplit[1])
                    g=float(lineSplit[2])
                    b=float(lineSplit[3])
                    matDict['diffuse'] = [r,g,b]
                    
            # specular color        
            if(count>0) and ("specular" in line):
                lineSplit = line.split()
                if len(lineSplit)>=4:
                    r=float(lineSplit[1])
                    g=float(lineSplit[2])
                    b=float(lineSplit[3])
                    matDict['specular'] = [r,g,b]
                    
            # emissive color        
            if(count>0) and ("emissive" in line):
                lineSplit = line.split()
                if len(lineSplit)>=4:
                    r=float(lineSplit[1])
                    g=float(lineSplit[2])
                    b=float(lineSplit[3])
                    matDict['emissive'] = [r,g,b]
                                    
            if "}" in line:
                count-=1
    
    # store it into meshData
    meshData['materials']= allMaterials
    if SHOW_IMPORT_TRACE:
        print("allMaterials: %s" % allMaterials)
    #return Textures

#def xCollectIDToBoneData(xmldoc):
#    
#    dicIDToBone = {}
#
#    for bones in xmldoc.getElementsByTagName('bones'):
#    
#        for bone in bones.childNodes:
#            if bone.localName == 'bone':
#                boneName = str(bone.getAttributeNode('name').value)
#                boneID = int(bone.getAttributeNode('id').value)
#                dicIDToBone[str(boneID)] = boneName
#                
#    return dicIDToBone

def xCollectBoneAssignments(meshData, xmldoc):
    boneIDtoName = meshData['boneIDs']
    
    VertexGroups = {}
    for vg in xmldoc.childNodes:
        if vg.localName == 'vertexboneassignment':
            VG = str(vg.getAttributeNode('boneindex').value)
            if VG in boneIDtoName.keys():
                VGNew = boneIDtoName[VG]
            else:
                VGNew = VG
            if VGNew not in VertexGroups.keys():
                VertexGroups[VGNew] = []
                
    for vg in xmldoc.childNodes:
        if vg.localName == 'vertexboneassignment':
            
            VG = str(vg.getAttributeNode('boneindex').value)
            if VG in boneIDtoName.keys():
                VGNew = boneIDtoName[VG]
            else:
                VGNew = VG
            verti = int(vg.getAttributeNode('vertexindex').value)
            weight = float(vg.getAttributeNode('weight').value)
            
            VertexGroups[VGNew].append([verti,weight])
            
    return VertexGroups
    

def xGetSkeletonLink(xmldoc, folder):
    skeletonFile = "None"
    if(len(xmldoc.getElementsByTagName("skeletonlink")) > 0):
        # get the skeleton link of the mesh
        skeleton_link = xmldoc.getElementsByTagName("skeletonlink")[0]
        skeletonFile = os.path.join(folder, skeleton_link.getAttribute("name"))
        # check for existence of skeleton file
        if fileExist(skeletonFile)==False:
            skeletonFile = "None"
        
    return skeletonFile

#def xCollectBoneData(meshData, xDoc, name, folder):
def xCollectBoneData(meshData, xDoc):
    OGRE_Bones = {}
    BoneIDToName = {}
    meshData['skeleton'] = OGRE_Bones
    meshData['boneIDs']= BoneIDToName
        
    for bones in xDoc.getElementsByTagName('bones'):    
        for bone in bones.childNodes:
            OGRE_Bone = {}
            if bone.localName == 'bone':
                boneName = str(bone.getAttributeNode('name').value)
                boneID = int(bone.getAttributeNode('id').value)
                OGRE_Bone['name'] = boneName
                OGRE_Bone['id'] = boneID
                BoneIDToName[str(boneID)] = boneName
                            
                for b in bone.childNodes:
                    if b.localName == 'position':
                        x = float(b.getAttributeNode('x').value)
                        y = float(b.getAttributeNode('y').value)
                        z = float(b.getAttributeNode('z').value)
                        OGRE_Bone['position'] = [x,y,z]
                    if b.localName == 'rotation':
                        angle = float(b.getAttributeNode('angle').value)
                        axis = b.childNodes[1]
                        axisx = float(axis.getAttributeNode('x').value)
                        axisy = float(axis.getAttributeNode('y').value)
                        axisz = float(axis.getAttributeNode('z').value)
                        OGRE_Bone['rotation'] = [axisx,axisy,axisz,angle]
                
                OGRE_Bones[boneName] = OGRE_Bone
                    
    for bonehierarchy in xDoc.getElementsByTagName('bonehierarchy'):
        for boneparent in bonehierarchy.childNodes:
            if boneparent.localName == 'boneparent':
                Bone = str(boneparent.getAttributeNode('bone').value)
                Parent = str(boneparent.getAttributeNode('parent').value)
                OGRE_Bones[Bone]['parent'] = Parent
        
    #update Ogre bones with list of children
    calcBoneChildren(OGRE_Bones)
    
    #helper bones
    calcHelperBones(OGRE_Bones)
    calcZeroBones(OGRE_Bones)
    
    #update Ogre bones with head positions
    calcBoneHeadPositions(OGRE_Bones)
    
    #update Ogre bones with rotation matrices
    calcBoneRotations(OGRE_Bones)

    return OGRE_Bones
def calcBoneChildren(BonesData):
    for bone in BonesData.keys():
        childlist = []
        for key in BonesData.keys():
            if 'parent' in BonesData[key]:
                parent = BonesData[key]['parent']
                if parent == bone:
                    childlist.append(key)
        BonesData[bone]['children'] = childlist

def calcHelperBones(BonesData):
    count = 0
    helperBones = {}
    for bone in BonesData.keys():
        if (len(BonesData[bone]['children']) == 0) or (len(BonesData[bone]['children']) > 1):
            HelperBone = {}            
            HelperBone['position'] = [0.2,0.0,0.0]
            HelperBone['parent'] = bone
            HelperBone['rotation'] = [1.0,0.0,0.0,0.0]
            HelperBone['flag'] = 'helper'
            HelperBone['name'] = 'Helper'+str(count)
            HelperBone['children'] = []
            helperBones['Helper'+str(count)] = HelperBone
            count+=1
    for hBone in helperBones.keys():
        BonesData[hBone] = helperBones[hBone]
    
def calcZeroBones(BonesData):
    zeroBones = {}
    for bone in BonesData.keys():
        pos = BonesData[bone]['position']
        if (math.sqrt(pos[0]**2+pos[1]**2+pos[2]**2)) == 0:
            ZeroBone = {}
            ZeroBone['position'] = [0.2,0.0,0.0]
            ZeroBone['rotation'] = [1.0,0.0,0.0,0.0]
            if 'parent' in BonesData[bone]:
                ZeroBone['parent'] = BonesData[bone]['parent']
            ZeroBone['flag'] = 'zerobone'
            ZeroBone['name'] = 'Zero'+bone 
            ZeroBone['children'] = []           
            zeroBones['Zero'+bone] = ZeroBone
            if 'parent' in BonesData[bone]:
                BonesData[BonesData[bone]['parent']]['children'].append('Zero'+bone)
    for hBone in zeroBones.keys():
        BonesData[hBone] = zeroBones[hBone]

def calcBoneHeadPositions(BonesData):
    
    for key in BonesData.keys():
        
        start = 0        
        thisbone = key
        posh = BonesData[key]['position']
        #print ("SetBonesASPositions: bone=%s, org. position=%s" % (key, posh))
        while start == 0:
            if 'parent' in BonesData[thisbone]:
                parentbone = BonesData[thisbone]['parent']
                prot = BonesData[parentbone]['rotation']
                ppos = BonesData[parentbone]['position']            
                
                #protmat = RotationMatrix(math.degrees(prot[3]),3,'r',Vector(prot[0],prot[1],prot[2])).invert()
                protmat = Matrix.Rotation(prot[3],3,Vector([prot[0],prot[1],prot[2]])).inverted()
                #print ("SetBonesASPositions: bone=%s, protmat=%s" % (key, protmat))
                #print(protmat)
                #newposh = protmat * Vector([posh[0],posh[1],posh[2]]) 
                #newposh =  protmat * Vector([posh[2],posh[1],posh[0]]) #02
                newposh =  protmat.transposed() * Vector([posh[0],posh[1],posh[2]]) #03
                #print ("SetBonesASPositions: bone=%s, newposh=%s" % (key, newposh))
                positionh = VectorSum(ppos,newposh)
            
                posh = positionh
                
                thisbone = parentbone
            else:
                start = 1
        
        BonesData[key]['posHAS'] = posh
        #print ("SetBonesASPositions: bone=%s, posHAS=%s" % (key, posh))

def calcBoneRotations(BonesDic):
    
    objDic =  {}
    scn = bpy.context.scene
    #scn = Scene.GetCurrent()
    for bone in BonesDic.keys():
        #obj = Object.New('Empty',bone)
        obj = bpy.data.objects.new(bone, None)
        objDic[bone] = obj
        scn.objects.link(obj)
    #print(bpy.data.objects)
    for bone in BonesDic.keys():
        if 'parent' in BonesDic[bone]:
            #Parent = Object.Get(BonesDic[bone]['parent'])
            #print(BonesDic[bone]['parent'])
            Parent = objDic.get(BonesDic[bone]['parent'])
            object = objDic.get(bone)
            object.parent = Parent
            #Parent.makeParent([object])
        
    for bone in BonesDic.keys():
        obj = objDic.get(bone)
        rot = BonesDic[bone]['rotation']
        loc = BonesDic[bone]['position']
        #print ("CreateEmptys:bone=%s, rot=%s" % (bone, rot))
        #print ("CreateEmptys:bone=%s, loc=%s" % (bone, loc))
        euler = Matrix.Rotation(rot[3],3,Vector([rot[0],-rot[2],rot[1]])).to_euler()
        obj.location = [loc[0],-loc[2],loc[1]]
        #print ("CreateEmptys:bone=%s, euler=%s" % (bone, euler))
        #print ("CreateEmptys:bone=%s, obj.rotation_euler=%s" % (bone,[math.radians(euler[0]),math.radians(euler[1]),math.radians(euler[2])]))
        #obj.rotation_euler = [math.radians(euler[0]),math.radians(euler[1]),math.radians(euler[2])]
        #print ("CreateEmptys:bone=%s, obj.rotation_euler=%s" % (bone,[euler[0],euler[1],euler[2]])) # 02
        obj.rotation_euler = [euler[0],euler[1],euler[2]] # 02
    #Redraw()
    scn.update()
    
    for bone in BonesDic.keys():
        obj = objDic.get(bone)
        # TODO: need to get rotation matrix out of objects rotation
        #loc, rot, scale = obj.matrix_local.decompose()
        loc, rot, scale = obj.matrix_world.decompose() #02
        rotmatAS = rot.to_matrix()
        #print(rotmatAS)
#        obj.rotation_quaternion.
#        rotmatAS = Matrix(.matrix_local..getMatrix().rotationPart()
        BonesDic[bone]['rotmatAS'] = rotmatAS
        #print ("CreateEmptys:bone=%s, rotmatAS=%s" % (bone, rotmatAS))
        
    
    for bone in BonesDic.keys():
        obj = objDic.get(bone)
        scn.objects.unlink(obj)
        del obj

def VectorSum(vec1,vec2):
    vecout = [0,0,0]
    vecout[0] = vec1[0]+vec2[0]
    vecout[1] = vec1[1]+vec2[1]
    vecout[2] = vec1[2]+vec2[2]
    
    return vecout

def calcBoneLength(vec):
    return math.sqrt(vec[0]**2+vec[1]**2+vec[2]**2)
               
def bCreateMesh(meshData, folder, name, materialFile, filepath):
    
    if 'skeleton' in meshData:
        bCreateSkeleton(meshData, name)
    # from collected data create all sub meshes
    subObjs = bCreateSubMeshes(meshData)
    # skin submeshes
    #bSkinMesh(subObjs)
    
    # temporarily select all imported objects
    for subOb in subObjs:
        subOb.select = True
    
    if SHOW_IMPORT_DUMPS:
        importDump = filepath + "IDump"  
        fileWr = open(importDump, 'w') 
        fileWr.write(str(meshData))    
        fileWr.close() 

#def createRig(amt, boneTable):
##    # Create armature and object
##    bpy.ops.object.add(
##        type='ARMATURE', 
##        enter_editmode=True,
##        location=origin)
##    ob = bpy.context.object
##    ob.show_x_ray = True
##    ob.name = name
##    amt = ob.data
##    amt.name = name+'Amt'
##    amt.show_axes = True
# 
#    # Create bones
#    bpy.ops.object.mode_set(mode='EDIT')
#    for (bname, pname, vector) in boneTable:        
#        bone = amt.edit_bones.new(bname)
#        if pname:
#            parent = amt.edit_bones[pname]
#            bone.parent = parent
#            bone.head = parent.tail
#            bone.use_connect = False
#            (trans, rot, scale) = parent.matrix.decompose()
#        else:
#            bone.head = (0,0,0)
#            rot = Matrix.Translation((0,0,0))    # identity matrix
#        bone.tail = rot * Vector(vector) + bone.head
#    bpy.ops.object.mode_set(mode='OBJECT')
#    #return ob

def vec_roll_to_mat3(vec, roll):
    target = mathutils.Vector((0,1,0))
    nor = vec.normalized()
    axis = target.cross(nor)
    if axis.dot(axis) > 0.0000000001: # this seems to be the problem for some bones, no idea how to fix
        axis.normalize()
        theta = target.angle(nor)
        bMatrix = mathutils.Matrix.Rotation(theta, 3, axis)
    else:
        updown = 1 if target.dot(nor) > 0 else -1
        bMatrix = mathutils.Matrix.Scale(updown, 3)
        
        # C code:
        #bMatrix[0][0]=updown; bMatrix[1][0]=0.0;    bMatrix[2][0]=0.0;
        #bMatrix[0][1]=0.0;    bMatrix[1][1]=updown; bMatrix[2][1]=0.0;
        #bMatrix[0][2]=0.0;    bMatrix[1][2]=0.0;    bMatrix[2][2]=1.0;
        bMatrix[2][2] = 1.0
        
    rMatrix = mathutils.Matrix.Rotation(roll, 3, nor)
    mat = rMatrix * bMatrix
    return mat

def mat3_to_vec_roll(mat):
    vec = mat.col[1]
    vecmat = vec_roll_to_mat3(mat.col[1], 0)
    vecmatinv = vecmat.inverted()
    rollmat = vecmatinv * mat
    roll = math.atan2(rollmat[0][2], rollmat[2][2])
    return vec, roll
    
def bCreateSkeleton(meshData, name):
    
#    obj = Object.New('Armature',name)
#    arm = Armature.New(name)
#    obj.link(arm)
#    scn.link(obj)
    if 'skeleton' not in meshData:
        return
    bonesData = meshData['skeleton']

    # create Armature
    amt = bpy.data.armatures.new(name)
    rig = bpy.data.objects.new(name, amt)
    #rig.location = origin
    rig.show_x_ray = True
    #amt.show_names = True
    # Link object to scene
    scn = bpy.context.scene
    scn.objects.link(rig)
    scn.objects.active = rig
    scn.update()
    
#    boneTable1 = [
#        ('Base', None, (1,0,0)),
#        ('Mid', 'Base', (1,0,0)),
#        ('Tip', 'Mid', (0,0,1))
#    ]
#    bent = createRig(amt, boneTable1)
    
    bpy.ops.object.mode_set(mode='EDIT')
    for bone in bonesData.keys():
        boneData = bonesData[bone]
        boneName = boneData['name']
        
        children = boneData['children']
        boneObj = amt.edit_bones.new(boneName)
        #boneObj.head = boneData['posHAS']
        #headPos = boneData['posHAS']
        headPos = boneData['posHAS']
        tailVector = 0.2
        if len(children)==1:
            tailVector=calcBoneLength(bonesData[children[0]]['position'])
        
        #boneObj.head = Vector([headPos[0],-headPos[2],headPos[1]])
        #boneObj.tail = Vector([headPos[0],-headPos[2],headPos[1] + tailVector]) 
        
        
        #print("bCreateSkeleton: bone=%s, boneObj.head=%s" % (bone, boneObj.head)) 
        #print("bCreateSkeleton: bone=%s, boneObj.tail=%s" % (bone, boneObj.tail)) 
        #boneObj.matrix =   
        rotmat = boneData['rotmatAS']
        #print(rotmat[1].to_tuple())
        #boneObj.matrix = Matrix(rotmat[1],rotmat[0],rotmat[2])
        r0 = [rotmat[0].x] + [rotmat[0].y] + [rotmat[0].z]
        r1 = [rotmat[1].x] + [rotmat[1].y] + [rotmat[1].z]
        r2 = [rotmat[2].x] + [rotmat[2].y] + [rotmat[2].z]
        
        boneRotMatrix = Matrix((r1,r0,r2))
        
        #pos = Vector([headPos[0],-headPos[2],headPos[1]])
        #axis, roll = mat3_to_vec_roll(boneRotMatrix.to_3x3())
                
        #boneObj.head = pos
        #boneObj.tail = pos + axis
        #boneObj.roll = roll

        #print("bCreateSkeleton: bone=%s, newrotmat=%s" % (bone, Matrix((r1,r0,r2))))
        #print(r1)
        #mtx = Matrix.to_3x3()Translation(boneObj.head) # Matrix((r1,r0,r2)) 
        #boneObj.transform(Matrix((r1,r0,r2)))
        #print("bCreateSkeleton: bone=%s, matrix_before=%s" % (bone, boneObj.matrix))
        #boneObj.use_local_location = False
        #boneObj.transform(Matrix((r1,r0,r2)) , False, False) 
        #print("bCreateSkeleton: bone=%s, matrix_after=%s" % (bone, boneObj.matrix))
        boneObj.head = Vector([0,0,0])
        #boneObj.tail = Vector([0,0,tailVector])
        boneObj.tail = Vector([0,tailVector,0])
        #matx = Matrix.Translation(Vector([headPos[0],-headPos[2],headPos[1]]))
        
        boneObj.transform( boneRotMatrix)
        boneObj.translate(Vector([headPos[0],-headPos[2],headPos[1]]))
        #boneObj.translate(Vector([headPos[0],-headPos[2],headPos[1]]))
        #boneObj.head = Vector([headPos[0],-headPos[2],headPos[1]])
        #boneObj.tail = Vector([headPos[0],-headPos[2],headPos[1]]) + (Vector([0,0, tailVector])  * Matrix((r1,r0,r2))) 
        
        #amt.bones[bone] = boneObj
        #amt.update_tag(refresh)
        
    # only after all bones are created we can link parents    
    for bone in bonesData.keys():
        boneData = bonesData[bone]
        parent = None
        if 'parent' in boneData.keys():
            parent = boneData['parent']
            # get bone obj
            boneData = bonesData[bone]
            boneName = boneData['name']
            boneObj = amt.edit_bones[boneName]        
            boneObj.parent = amt.edit_bones[parent]
    
    # need to refresh armature before removing bones
    bpy.ops.object.mode_set(mode='OBJECT')
    bpy.ops.object.mode_set(mode='EDIT')
    
    # delete helper/zero bones
    for bone in amt.bones.keys():
        #print("keys of bone=%s" % bonesData[bone].keys())
        if 'flag' in bonesData[bone].keys():                      
            #print ("deleting bone=%s" % bone)          
            bpy.context.object.data.edit_bones.remove(amt.edit_bones[bone])            
    
#    for bone in arm.bones.keys():
#        if BonesDic[bone].has_key('flag'):
#            arm.makeEditable()
#            del arm.bones[bone]
#            arm.update()
            
    bpy.ops.object.mode_set(mode='OBJECT')
#    for (bname, pname, vector) in boneTable:        
#        bone = amt.edit_bones.new(bname)
#        if pname:
#            parent = amt.edit_bones[pname]
#            bone.parent = parent
#            bone.head = parent.tail
#            bone.use_connect = False
#            (trans, rot, scale) = parent.matrix.decompose()
#        else:
#            bone.head = (0,0,0)
#            rot = Matrix.Translation((0,0,0))    # identity matrix
#        bone.tail = rot * Vector(vector) + bone.head
#    bpy.ops.object.mode_set(mode='OBJECT')

def bCreateSubMeshes(meshData):
    
    allObjects = []
    submeshes = meshData['submeshes']
    
    for i in range(len(submeshes)):
        subMeshData = submeshes[i]
        subMeshName = subMeshData['material']        
        # Create mesh and object
        me = bpy.data.meshes.new(subMeshName)
        ob = bpy.data.objects.new(subMeshName, me)        
        # Link object to scene
        scn = bpy.context.scene
        scn.objects.link(ob)
        scn.objects.active = ob
        scn.update()
        # check for submesh geometry, or take the shared one
        if 'geometry' in subMeshData.keys():
            geometry = subMeshData['geometry']            
        else:
            geometry = meshData['sharedgeometry']            
          

        verts = geometry['positions'] 
        faces = subMeshData['faces']     
        # mesh vertices and faces   
        me.from_pydata(verts, [], faces) 
        # mesh normals
        c = 0
        for v in me.vertices:
            if 'normals' in geometry.keys():
                normals = geometry['normals']
                v.normal = Vector((normals[c][0],normals[c][1],normals[c][2]))
                c+=1
        # smooth        
        
        for f in me.faces:
            f.use_smooth = True        
              
        hasTexture = False
        # material for the submesh
        # Create image texture from image.         
        if subMeshName in meshData['materials']:            
            matInfo = meshData['materials'][subMeshName] # material data
            if 'texture' in matInfo:
                texturePath = matInfo['texture']
                if texturePath:
                    hasTexture = True
                    tex = bpy.data.textures.new('ColorTex', type = 'IMAGE')
                    tex.image = bpy.data.images.load(texturePath)
                    tex.use_alpha = True
         
            # Create shadeless material and MTex
            mat = bpy.data.materials.new(subMeshName)
            # ambient
            if 'ambient' in matInfo:
                mat.ambient = matInfo['ambient'][0]
            # diffuse
            if 'diffuse' in matInfo:
                mat.diffuse_color = matInfo['diffuse']
            # specular
            if 'specular' in matInfo:
                mat.specular_color = matInfo['specular']
            # emmisive
            if 'emissive' in matInfo:
                mat.emit = matInfo['emissive'][0]
            mat.use_shadeless = True
            mtex = mat.texture_slots.add()
            if hasTexture:
                mtex.texture = tex
            mtex.texture_coords = 'UV'
            mtex.use_map_color_diffuse = True 
            
            # add material to object
            ob.data.materials.append(mat)
            #print(me.uv_textures[0].data.values()[0].image)       
            
        # texture coordinates
        if 'texcoordsets' in geometry:
            for j in range(geometry['texcoordsets']):                
                uvLayer = me.uv_textures.new('UVLayer'+str(j))
                
                me.uv_textures.active = uvLayer
            
                for f in me.faces:    
                    if 'uvsets' in geometry:
                        uvco1sets = geometry['uvsets'][f.vertices[0]]
                        uvco2sets = geometry['uvsets'][f.vertices[1]]
                        uvco3sets = geometry['uvsets'][f.vertices[2]]
                        uvco1 = Vector((uvco1sets[j][0],uvco1sets[j][1]))
                        uvco2 = Vector((uvco2sets[j][0],uvco2sets[j][1]))
                        uvco3 = Vector((uvco3sets[j][0],uvco3sets[j][1]))
                        uvLayer.data[f.index].uv = (uvco1,uvco2,uvco3)
                        if hasTexture:
                            # this will link image to faces
                            uvLayer.data[f.index].image=tex.image
                            #uvLayer.data[f.index].use_image=True
                        
        # this probably doesn't work
        # vertex colors               
        if 'vertexcolors' in geometry:
            me.vertex_colors = True        
            vcolors = geometry['vertexcolors']        
            for f in me.faces:
                for k,v in enumerate(f.v):
                    col = f.col[k]
                    vcol = vcolors[k]
                    col.r = int(vcol[0]*255)
                    col.g = int(vcol[1]*255)
                    col.b = int(vcol[2]*255)
                    col.a = int(vcol[3]*255)
        
        bpy.ops.object.editmode_toggle()
        bpy.ops.mesh.faces_shade_smooth()
        bpy.ops.object.editmode_toggle()
        # Update mesh with new data
        me.update(calc_edges=True)
        
        allObjects.append(ob)
        
    # forced view mode with textures
    bpy.context.scene.game_settings.material_mode = 'GLSL'
    areas = bpy.context.screen.areas
    for area in areas:
        if area.type == 'VIEW_3D':
            area.spaces.active.viewport_shade='TEXTURED'
    
    return allObjects
        

def load(operator, context, filepath,       
         ogreXMLconverter=None,
         keep_xml=False,):
    
    global blender_version
    
    blender_version = bpy.app.version[0]*100 + bpy.app.version[1]
        
    print("loading...")
    print(str(filepath))    
    
    #meshfilename = os.path.split(filepath)[1].lower()      
    #name = "mesh"
    #files = []
    #materialFile = "None"
        
    filepath = filepath.lower()
    pathMeshXml = filepath  
    # get the mesh as .xml file
    if (".mesh" in filepath):
        if (".xml" not in filepath):
            os.system('%s "%s"' % (ogreXMLconverter, filepath))
            pathMeshXml = filepath + ".xml"
    else:
        return('CANCELLED')
    
    folder = os.path.split(filepath)[0]    
    nameDotMeshDotXml = os.path.split(pathMeshXml)[1].lower()
    nameDotMesh = os.path.splitext(nameDotMeshDotXml)[0]
    onlyName = os.path.splitext(nameDotMesh)[0] 
                
    # material
    nameDotMaterial = onlyName + ".material"
    pathMaterial = os.path.join(folder, nameDotMaterial)
    if fileExist(pathMaterial)==False:
        # search directory for .material    
        for filename in os.listdir(folder):
            if ".material" in filename:
                # material file
                pathMaterial = os.path.join(folder, filename)
    
    # try to parse xml file
    xDocMeshData = xOpenFile(pathMeshXml)
    
    meshData = {}
    if xDocMeshData != "None":
        # skeleton data
        # get the mesh as .xml file
        skeletonFile = xGetSkeletonLink(xDocMeshData, folder)
        # there is valid skeleton link and existing file
        if(skeletonFile!="None"):
            skeletonFileXml = skeletonFile + ".xml"
            # if there isn't .xml file yet, convert the skeleton file
            if(fileExist(skeletonFileXml)==False):
                os.system('%s "%s"' % (ogreXMLconverter, skeletonFile))                
            # parse .xml skeleton file
            xDocSkeletonData = xOpenFile(skeletonFileXml)    
            if xDocSkeletonData != "None":
                xCollectBoneData(meshData, xDocSkeletonData)
        
        # collect mesh data
        print("collecting mesh data...")
        xCollectMeshData(meshData, xDocMeshData, onlyName, folder)    
        xCollectMaterialData(meshData, pathMaterial, folder)
        
        # after collecting is done, start creating stuff
#        # create skeleton
#        bCreateSkeleton(meshData, onlyName)
        # create a mesh from parsed data
        bCreateMesh(meshData, folder, onlyName, pathMaterial, pathMeshXml)
        if not keep_xml:
            # cleanup by deleting the XML file we created
            os.unlink("%s" % pathMeshXml)
            
    if SHOW_IMPORT_TRACE:
        print("folder: %s" % folder)
        print("nameDotMesh: %s" % nameDotMesh)
        print("nameDotMeshDotXml: %s" % nameDotMeshDotXml)
        print("onlyName: %s" % onlyName)
        print("nameDotMaterial: %s" % nameDotMaterial)
        print("pathMaterial: %s" % pathMaterial)    
        print("ogreXMLconverter: %s" % ogreXMLconverter)
        
#    if(ogreXMLconverter is not None):
#        # convert MESH and SKELETON file to MESH.XML and SKELETON.XML respectively
#        for filename in os.listdir(folder):
#            # we're going to do string comparisons. assume lower case to simplify code
#            filename = os.path.join(folder, filename.lower())
#            # process .mesh and .skeleton files while skipping .xml files
#            if (".mesh" in filename) and (".xml" not in filename):
#                os.system('%s "%s"' % (ogreXMLconverter, filename))
#            
#    # get all the filenames in the chosen directory, put in list and sort it
#    for filename in os.listdir(folder):
#        # we're going to do string comparisons. assume lower case to simplify code
#        filename = filename.lower()
#        # process .mesh and .skeleton files while skipping .xml files
#        if ".skeleton.xml" in filename:
#            files.append(os.path.join(folder, filename))
#        elif (".mesh.xml" in filename) and (meshfilename in filename):
#            print (meshfilename)
#            # get the name of the MESH file without extension. Use this base name to name our imported object
#            name = filename.split('.')[0]
#            # to avoid Blender naming limit problems
#            name = GetValidBlenderName(name)
#            # put MESH file on top of the file list
#            files.insert(0, os.path.join(folder, filename))
#        elif ".material" in filename:
#            # material file
#            materialFile = os.path.join(folder, filename)
#
#    # now that we have a list of files, process them
#    filename = files[0]
#    
#    #filename = filepath.lower()
#    # import the mesh
#    if (".mesh" in filename):
#        mesh_data = xOpenFile(filename)
#        if mesh_data != "None":
#            #CreateSkeleton(mesh_data, folder, name)
#            CreateMesh(mesh_data, folder, name, materialFile, filepath)
#            if not keep_xml:
#                # cleanup by deleting the XML file we created
#                os.unlink("%s" % filename)
    
    print("done.")
    return {'FINISHED'}
