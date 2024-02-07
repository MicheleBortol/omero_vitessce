#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
This script can be used with python 3.6

This script creates a download slot with links to the given image objects. Directory structure is orientated
on the omero project-dataset-image structure.
@author Susanne Kunis
<a href="mailto:sinukesus@gmail.com">sinukesus@gmail.com"</a>
@version 0.1.0

"""
import os
import sys
import random
import string
import omero
from omero.rtypes import rstring, rlong,robject,unwrap
import time
import omero.scripts as scripts
from omero.gateway import BlitzGateway
import datetime
import re
import subprocess
from pathlib import Path

import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import formatdate
import json
import glob


#-------------------------------------------------
#------------ Configuration ----------------------
#-------------------------------------------------

# Directory for links that the nginx server also has access to
OPENLINK_DIR= "/openlink"

# name of nginx website
SERVER_NAME = "ADDRESS"

# name of nginx location
NGINX_LOCATION= '/openlink'

# email originator
ADMIN_EMAIL = "ADMIN_EMAIL"

# length of hash string used in the openlink url
LENGTH_HASH = 12

# Fix Path for use in Docker, set to None to skip
NEW_PATH_PREFIX = "PATH_TO_THE_VOLUME_WITH_THE_OMERO_DATA_DIRECTORY"
OMERO_DIR = "/OMERO/"

#--------------------------------------------------


# OMERO.script GUI elements
PARAM_DATATYPE = "Data_Type"
PARAM_ID = "IDs"
PARAM_SLOTS="Choose existing OpenLink"
PARAM_ADD_TO_SLOT="Add to existing OpenLink"
PARAM_SLOT_NAME="OpenLink Name"
PARAM_ATTACH="Add attachments"

# email server IP adress
SMTP_IP = '127.0.0.1'

URL = "https://%s%s"%(SERVER_NAME,NGINX_LOCATION)

OPENLINK_PATTERN='rn_*_'
GET_SLOTNAME_PATTERN = '^rn_[A-Z,0-9]+_\d+_(.+)'
CURL_FILE="batch_download.curl"
CONTENT_FILE="content.json"
CURL_PATTERN='create-dirs\n output="%s%s%s"\n continue-at -\n url="%s/%s/%s"'

# k option only for testing! Remove in production!!!
CMD = "curl -sk %s/%s/%s | curl -K-"

MAX_PATHLENGTH = 200 # max pathlength in windows:256

# dict of {'<userID>':{'images':<list_of_imageIds>,'email':<mail>}} for mail notification
NOTIFICATION_LIST={}

def fix_path_for_docker(path):
    # Replaces the OMERO_DIR in the container with the path on the host
    path = str(path).replace(OMERO_DIR, NEW_PATH_PREFIX)
    return Path(path)

def revert_path(path):
    # Replaces the path on the host with the OMERO_DIR
    path = str(path).replace(NEW_PATH_PREFIX, OMERO_DIR)
    return Path(path)

def get_realpath(path):
    # return target of symlink
    return Path(path).resolve().as_posix()

def get_omero_paths(client):
    resources = client.sf.sharedResources()
    repos = resources.repositories()
    managed_repo_dir = None
    orig_repo_dir = None
    for desc in repos.descriptions:
        if "ManagedRepository".lower() in desc.name.val.lower():
            managed_repo_dir = desc.path.val + desc.name.val
        if "OMERO".lower() in desc.name.val.lower():
            orig_repo_dir = desc.path.val + desc.name.val

    # if the repo paths could not be identify, check custom configurations from config of omero
    if not managed_repo_dir:
        managed_repo_dir=client.sf.getConfigService().getConfigValue("omero.managed.dir");
    if not orig_repo_dir:
        orig_repo_dir=client.sf.getConfigService().getConfigValue("omero.data.dir");

    # catching empty paths
    if not managed_repo_dir:
        print("ERROR: no specification was found for managed repository path. Please check path of type Managed under \n >>omero fs repos \n or the value of omero.managed.dir under\n >>omero config get")
        return None,None

    if not orig_repo_dir:
        print("ERROR: no specification was found for omero repository path. Please check path of type Public under \n >>omero fs repos \n or the value of omero.data.dir under\n >>omero config get")
        return None,None

    if managed_repo_dir and not managed_repo_dir.endswith('/'):
        managed_repo_dir = managed_repo_dir + '/'
    if orig_repo_dir:
        orig_repo_dir = orig_repo_dir + '/Files/'

    managed_repo_dir=get_realpath(managed_repo_dir)
    orig_repo_dir=get_realpath(orig_repo_dir)

    if not os.path.exists(managed_repo_dir):
        managed_repo_dir = None
    if not os.path.exists(orig_repo_dir):
        orig_repo_dir = None

    return managed_repo_dir,orig_repo_dir

# returning file paths in qiven directory and all subdirs
def get_file_paths(directory, file_paths):
    for f in glob.iglob("%s/*"%directory,recursive=True):
        if os.path.isdir(f):
            file_paths=get_file_paths(f, file_paths)
        else:
            file_paths.append(f)

    return file_paths



def addToCurlFile(base,hashName):
    curlFile = os.path.join(base,CURL_FILE)
    contentFile = os.path.join(base,CONTENT_FILE)
    fileList = get_file_paths(base,[])
    accessAreaName = parseAccessAreaNames(hashName)
    try:
        tFile = open(curlFile,'w')
        for file in fileList:
            if os.path.basename(file)==os.path.basename(contentFile):
                continue
            if not os.path.basename(file)==os.path.basename(curlFile):
                relPath=os.path.relpath(file, base)
                relPath=relPath.replace('\\','/')
                if len(relPath) > MAX_PATHLENGTH:
                    print("ATTENTION: pathlength is in the critical range! This could generate download issues for %s"%relPath)

            # replace whitespaces
                entry = CURL_PATTERN %(accessAreaName,os.sep,relPath,URL,
                                       hashName.replace(" ","%20"),relPath.replace(" ","%20"))
                tFile.write(entry)
                tFile.write("\n")
        tFile.flush()
    finally:
        tFile.close()


# get location of sources in managed rep
# TODO: filenames with special characters makes problems
def getOriginalFile(imageObj):
    fileset = imageObj.getFileset()

    for origFile in fileset.listFiles():
        #print(origFile.__dict__)
        name = origFile.getName()
        path = origFile.getPath()

    return path, name



def writeDictContent(path):
    global CONTENT_DICT
    f = open(path, "w")
    json.dump(CONTENT_DICT,f)
    f.close()

def loadDictContent(path):
    global CONTENT_DICT
    old_path = revert_path(path)
    print(path)
    print(old_path)
    if os.path.exists(old_path):
        f = open(old_path, "r")
        CONTENT_DICT = json.load(f)
        f.close()
    else:
        print("OpenLink content file doesn't exist")
        CONTENT_DICT={}


def existsInDictContent(path,id):
    global CONTENT_DICT
    if not CONTENT_DICT:
        return False

    if CONTENT_DICT.get(path) is not None and CONTENT_DICT.get(path)==id:
        return True
    return False


def getContentFromDictById(id):
    global CONTENT_DICT
    if not CONTENT_DICT:
        return False
    paths = [k for k,v in CONTENT_DICT.items() if v == id]

    return paths

def addToDictContent(path,id):
    global CONTENT_DICT
    CONTENT_DICT.update({path:id})

def createObjectDir(type,ppath,object,name):
    """ Create directory of <name> in <ppath> and add this information with object id to dict content.
    Normally <name> is the name of the given object.
    If the directory still exists, but was created from a different object, append object id to the name of the dir.

    RETURN: absolute path of created dir"""

    path=os.path.join(ppath,name)
    if not os.path.exists(path):
        try:
            os.mkdir(path)
            addToDictContent(path,object.getId())
            return path
        except:
            print("ERROR: Cannot create directory for %s: %s in %s (possible problems:length of name, usage of /\:*?''<>|)"%(type,name,ppath))
            return None
    else:
        # check if existing object is the same
        if not existsInDictContent(path,object.getId()):
            # check if there is another name for this object
            existing_paths=getContentFromDictById(object.getId())
            if len(existing_paths) == 0:
                # create alternativ name (append id)
                alter_dir_name = "%s_%s"%(object.getName(),object.getId())
                return createObjectDir(type,ppath,object,alter_dir_name)
            else:
                return existing_paths[0]
    return path

def getPath(image, slot):
    """
    Generate directory structure like in omero (project/dataset/) for given <image> in directory <slot> if it not exist.
    RETURN: absolute path to dataset
    """
    datasetObj=image.getParent()
    projectObj=datasetObj.getParent()

    linkDir=slot

    if projectObj is not None:
        linkDir = createObjectDir("P",linkDir,projectObj,projectObj.getName())

    if linkDir is not None:
        linkDir = createObjectDir("D",linkDir,datasetObj,datasetObj.getName())

    return linkDir


def userIsOwner(conn,userName, id):
    image = conn.getObject('Image',id)
    if image.getOwnerOmeName()==userName:
        return True
    return False


def isAllowedToShareData(conn,userID):
    '''
    Test if user is owner of the current group and the group permission is not private
    :param conn:
    :param userID:
    :return:
    '''
    group = conn.getGroupFromContext()
    print("# Current group: %s"%group.getName())
    # if current group is a private group -> return false
    group_perms = group.getDetails().getPermissions()
    perm_string = str(group_perms)
    permission_names = {
        'rw----': 'PRIVATE',
        'rwr---': 'READ-ONLY',
        'rwra--': 'READ-ANNOTATE',
        'rwrw--': 'READ-WRITE'}
    print ("# Group Permission: %s (%s)" % (permission_names[perm_string], perm_string))
    if permission_names[perm_string]== permission_names['rw----']:
        print("\nThis is a private group -> you can only create an OpenLink of data owned by yourself!\n")
        return False

    # check if given user is also an owner of this group
    owners, members = group.groupSummary()
    for own in owners:
        if userID == own.getId():
            return True

    return False


def getFilesetPath(conn,id):
    image = conn.getObject('Image',id)
    # this will include pre-FS data IF images were archived on import
    # specifically count Fileset files
    file_count = image.countFilesetFiles()
    # list files
    filePaths=[]
    fName=""
    if file_count > 0:
        if file_count > 1:
            for orig_file in image.getImportedImageFiles():
                path = orig_file.getPath()
                filePaths.append(path)
        else:
            path,fName = getOriginalFile(image)
            filePaths.append(path)

    filesetPath = os.path.commonprefix(filePaths)

    return filesetPath,fName


def checkLinks(src,targetDir,name,linkNames, linkTarget, id):
    """
   check link parameters
   :param src: path that should be linked
   :param targetDir: dir where the link should be created
   :param name: name of link
   :param linkNames: path/name of links
   :param linkTarget: target that should be linked
   :param id: id of object that should be named with link
   :return:
   """

    dest = os.path.join(targetDir,name)
    if src not in linkTarget:
        if dest not in linkNames:
            #("accept : %s"%name)
            linkNames.append(dest)
            linkTarget.append(src)
        else:#rename
            fName,extension = os.path.splitext(name)
            name = "%s_%s%s"%(fName,id,extension)
            print("# rename : %s [new: %s]"%(fName,name))
            linkNames,linkTarget=checkLinks(src,targetDir,name,linkNames,linkTarget,id)
    else: #src still exists
        if dest not in linkNames:#ignore
            print("# ignore %s (src exists, dest not)"%name)
            pass
        else: #ignore
            print("# ignore %s (src exists, dest exists)"%name)
            pass

    return linkNames,linkTarget


def createSymlinks(linkNames, linkTarget):
    if linkNames is not None and len(linkNames)>0:
        for (src, dest) in zip(linkTarget,linkNames):
            #print("# create link: %s ->\n\t%s"%(dest,src))
            try:
                if NEW_PATH_PREFIX:
                    src = fix_path_for_docker(src) # Get the path on the host
                os.symlink(src, dest)
            except FileExistsError:
                print("# skip:: Link still exists: ",src)

def addAttachment(obj,tdir):
    global ORIGINAL_REP
    if tdir is not None:
        for ann in obj.listAnnotations():
            if isinstance(ann,omero.gateway.FileAnnotationWrapper):
                print("# Annotation File ID:", ann.getFile().getId(),ann.getFile().getName())
                #TODO: link - if file still exists - skip
                carg="find %s -name %s"%(ORIGINAL_REP,ann.getFile().getId())
                paths = [line[0:] for line in subprocess.check_output(carg, shell=True).splitlines()]
                if len(paths)>1:
                    print("# ATTENTION: file annotation target is not unique: %s --> use first match"%("\n".join(paths)))

                linkNames=[]
                linkNames.append(os.path.join(tdir,ann.getFile().getName()))
                linkTarget=[]
                linkTarget.append(str(paths[0].decode('utf-8')))
                createSymlinks(linkNames,linkTarget)


def addToNotifyList(user, image_ID):
    userID=user.getId() # Initialises also the proxy object for simpleMarshal
    dic = user.simpleMarshal()
    if 'email' in dic and dic['email']:
        userEmail = dic['email']

    # Validate with a regular expression. Not perfect but it will do
    match= re.match("^[a-zA-Z0-9._%-]+@[a-zA-Z0-9._%-]+.[a-zA-Z]{2,6}$",
                    userEmail)
    if match:
        global NOTIFICATION_LIST
        if len(NOTIFICATION_LIST)==0:
            NOTIFICATION_LIST={userID:{'images':[image_ID],'email':userEmail}}
        else:
            # user available?
            if userID in NOTIFICATION_LIST and NOTIFICATION_LIST[userID]:
                if NOTIFICATION_LIST[userID]['images']:
                    NOTIFICATION_LIST[userID]['images'].append(image_ID)
                else:
                    NOTIFICATION_LIST[userID]={'images':[image_ID],'email':userEmail}
            else:
                NOTIFICATION_LIST.update({userID:{'images':[image_ID],'email':userEmail}})


def get_owner_of_data(conn, image):
    return image.getDetails().getOwner()


def addImages(conn,slot,images,user,addAttachments, allowedToShare,targetDir=None):
    linkNames=[]
    linkTarget=[]
    userName = user.getName()
    global MANAGED_REP

    # proof images
    for image in images:
        user_is_owner = userIsOwner(conn,userName,image.id)
        # share data
        share = allowedToShare or user_is_owner
        if share:
            if not targetDir:
                targetDir= getPath(image,slot)
                # failed path
                if not targetDir:
                    continue

            src_filesetPath,src_fName=getFilesetPath(conn,image.id)

            # add tp linkNames and linkTarget list
            if src_filesetPath:
                if image.countFilesetFiles()>1:
                    name , extension = os.path.splitext(image.getName())
                    src = os.path.join(MANAGED_REP,src_filesetPath)
                    linkNames,linkTarget=checkLinks(src,targetDir,name,linkNames,linkTarget,image.id)

                else:
                    src = os.path.join(os.path.join(MANAGED_REP,src_filesetPath),src_fName)
                    linkNames,linkTarget=checkLinks(src,targetDir,src_fName,linkNames,linkTarget,image.id)

                # if data owned by others - owner of this data should be notify
                if not user_is_owner and allowedToShare:
                    addToNotifyList(get_owner_of_data(conn,image),image.id)
            else:
                print("# ATTENTION: No raw file or fileset available")

            # add available attachments if required
            if addAttachments:
                addAttachment(image,targetDir)
        else:
            print("# ATTENTION: You are not allowed to share image: %s"%image.getId())


    # create links from proof images
    createSymlinks(linkNames,linkTarget)




def addDatasets(conn,slot, datasets,user,addAttachments,allowedToShare,targetDir=None):
    for dataset in datasets:
        # check if parent project dir still exists
        if not targetDir:
            projectObj=dataset.getParent()
            if projectObj is not None:
                linkDir = createObjectDir("P",slot,projectObj,projectObj.getName())
            else:
                linkDir = slot
        else:
            linkDir = targetDir

        if linkDir is not None:
            linkDir=createObjectDir("D",linkDir,dataset,dataset.getName())

            if addAttachments:
                addAttachment(dataset,linkDir)

            addImages(conn,slot,dataset.listChildren(),user,addAttachments,allowedToShare,linkDir)





def addProjects(conn,slot,projects,user,addAttachments,allowedToShare):
    for project in projects:
        linkDir=createObjectDir("P",slot,project,project.getName())
        if linkDir is not None:
            if addAttachments:
                addAttachment(project,linkDir)

            addDatasets(conn,slot,project.listChildren(),user,addAttachments,allowedToShare,linkDir)

def getRandomString(n):
    # generating random strings
    res = ''.join(random.choices(string.ascii_uppercase +
                                 string.digits, k = n))
    return res

def generateHashName(user,n,accessAreaName):
    hashName = "%s_%s_%s_%s"%("rn",getRandomString(n),user.getId(),accessAreaName)
    return hashName


def createAreaName():
    date = datetime.datetime.now()
    timeStr = date.strftime("%Y-%m-%d_%H-%M-%S")

    return timeStr

def generateNewAccessArea(user,accessAreaName):
    hashName = generateHashName(user,LENGTH_HASH,accessAreaName)

    while os.path.exists(os.path.join(OPENLINK_DIR,hashName)):
        hashName = generateHashName(user,LENGTH_HASH,accessAreaName)

    accessAreaPath = os.path.join(OPENLINK_DIR,hashName)
    os.mkdir(accessAreaPath)

    return accessAreaPath,hashName


def email_results(conn, imageIDs,email,smtpObj):
    """
    E-mail the result to the user.

    @param conn:    The BlitzGateway connection
    @param results: Dict of (imageId,text_result) pairs
    @param report:  The results report
    @param params:  The script parameters
    """
    sharerName=conn.getUser().getName()
    msg = MIMEMultipart()
    msg['From'] = ADMIN_EMAIL
    msg['To'] = email
    msg['Date'] = formatdate(localtime=True)
    msg['Subject'] = '[OMERO Share] your data was shared'
    msg.attach(MIMEText("""Your data was shared by %s.

    List of shared image ID's:

    %s

    """ % (sharerName,"\n".join(str(v) for v in imageIDs))))
    smtpObj.sendmail(ADMIN_EMAIL, [email], msg.as_string())
    return

def notifyMembers(conn):
    '''
    Notify owner of the data if they was shared by group owner
    :return:
    '''
    global NOTIFICATION_LIST

    if len(NOTIFICATION_LIST)==0:
        return
    else:
        start=time.time()
        smtpObj = smtplib.SMTP(SMTP_IP)

        for key, value in NOTIFICATION_LIST.items():
            print("# Send Notification to %s"%value['email'])
            email_results(conn,value['images'],value['email'],smtpObj)
        smtpObj.quit()
        print('# Notification via mail took %.2f seconds' % (time.time()-start))


def addObjToAccessArea(conn,params,availableSlots=None,paths=None):
    """
    add selected object and its content to a slot on OPENLINK_DIR as link to sources on ManagedRepository
    :param paths:
    :param availableSlots:
    :param conn:
    :param params:
    :return:
    """

    # init Notifationlist
    global NOTIFICATION_LIST
    NOTIFICATION_LIST={}

    # can not owned data be shared?
    allowedToShare=isAllowedToShareData(conn,conn.getUser().getId())

    # get available slot path or create a new slot directory
    accessAreaPath=None
    if params.get(PARAM_ADD_TO_SLOT) and paths and len(paths)>0:
        index = availableSlots.index(params.get(PARAM_SLOTS))
        accessAreaPath = paths[index]
        hashName = os.path.basename(accessAreaPath)
        slotName = parseAccessAreaNames(hashName)
    else:
        # create a new slot
        slotName = params.get(PARAM_SLOT_NAME)
        if not slotName:
            slotName=createAreaName()
        accessAreaPath,hashName=generateNewAccessArea(conn.getUser(),slotName)

    addAttachments=False
    if params.get(PARAM_ATTACH):
        addAttachments=True


    destObjs=None
    if params.get(PARAM_ID) is not None:
        destObjs = conn.getObjects(params.get(PARAM_DATATYPE), params.get(PARAM_ID))
        destType = params.get(PARAM_DATATYPE)


    # parse json with object ids available in this area to dict
    contentFileName = "%s/%s"%(accessAreaPath,CONTENT_FILE)
    loadDictContent(contentFileName)

    if destObjs is None:
        return None,"ERROR: Given objects not available"
    if destType is None:
        return None,"ERROR: Can't identify selected object. Please select Projects, Datasets or Images"
    elif destType=='Project':
        addProjects(conn,accessAreaPath,destObjs,conn.getUser(),addAttachments,allowedToShare)
    elif destType =='Dataset':
        addDatasets(conn,accessAreaPath,destObjs,conn.getUser(),addAttachments,allowedToShare)
    elif destType == 'Image':
        addImages(conn,accessAreaPath,destObjs,conn.getUser(),addAttachments,allowedToShare)

    addToCurlFile(accessAreaPath,hashName)
    writeDictContent(contentFileName)
    url = "%s/%s/"%(URL,hashName)
    cmd = CMD%(URL,hashName.replace(" ","%20"),CURL_FILE)

    print("\n-----------------------------------------------------\n")
    print("URL: \n%s\n"%url)
    print("Batch download: copy the following line between the hashes into your cmd:\n### ")
    print(cmd)
    print("###\n")


    notifyMembers(conn)
    return "Create OpenLink:  %s. After reload you can find URL and batch download command listed under OpenLink in the right hand pane"%slotName


def parseAccessAreaNames(p):
    try:
        name = re.search(GET_SLOTNAME_PATTERN, p).group(1)
    except AttributeError:
        name = None # apply your error handling
        print("## ERROR ## at parse OpenLink names")
    return name


def getAreasOfUser(id):
    values = []
    p="%s/%s%s_*"%(OPENLINK_DIR,OPENLINK_PATTERN,id)
    values = glob.glob(p)

    return values



def getAvailableSlots(conn):
    """
    get all slots for current user (OPENLINK_DIR/rn_<RN>_<userid>_<accessAreaName>/;
    :param conn:
    :return:
    """
    values = None
    try:
        user = conn.getUser()
        userName = user.getName()
        slotParentDir=None
        if os.path.exists(OPENLINK_DIR):
            slotParentDir=getAreasOfUser(str(user.getId()))

        if not slotParentDir or len(slotParentDir)==0:
            return ['No OpenLinks available for %s'% userName],[]

        # get slotNames
        values=[]
        paths=[]
        for p in slotParentDir:
            areaName = parseAccessAreaNames(os.path.basename(p))
            if areaName:
                timestamp=os.path.getctime(p)
                dt = datetime.datetime.fromtimestamp(timestamp)
                thisDate=dt.strftime("%d %b %Y (%I:%M:%S %p)")
                values.append("%s [created %s]"%(areaName,thisDate))
                paths.append(p)
    except Exception as e:
        values = ['Error parsing OpenLink for %s'% userName]

        exc_type, exc_obj, exc_tb = sys.exc_info()
        print('## ERROR ##: while reading OpenLink : %s\n %s %s'%(str(e),exc_type, exc_tb.tb_lineno))

    if len(values)==0:
        values = ['No OpenLink found for %s'% userName]

    return values,paths


def run_script():
    """
    The main entry point of the script, as called by the client via the
    scripting service, passing the required parameters.
    """

    client = omero.client()
    client.createSession()
    conn = omero.gateway.BlitzGateway(client_obj=client)
    conn.SERVICE_OPTS.setOmeroGroup(-1)
    availableSlotsNames,paths = getAvailableSlots(conn)
    client.closeSession()

    dataTypes = [rstring('Project'),rstring('Dataset'),rstring('Image')]

    client = scripts.client(
        'Create_OpenLink.py',
        """Add selected objects and all subordinate objects to a new or existing OpenLink area. After the creation of the OpenLink section is completed, you will find a link under the right tab OpenLink after a REFRESH of your omero.web content.

        *** NOTE: ***
        You can only add data that belongs to you to your OpenLink area OR as group owner of a NON-PRIVATE group you can also use data from other members (the owner of the data will be notify by mail).
        
        
        """,
        scripts.String(PARAM_DATATYPE,optional=False, grouping="1",
                       description="Choose source of objects",
                       values=dataTypes),
        scripts.List(PARAM_ID, optional=False, grouping="2",
                     description="List of Image IDs to process").ofType(rlong(0)),
        scripts.String(PARAM_SLOT_NAME, optional=True,grouping="3",
                       description="Create new OpenLink area with given name. If nothing is specified, the current date is used."),
        scripts.Bool(PARAM_ADD_TO_SLOT,grouping="4",
                     description="Add data to an existing OpenLink area",default=False),
        scripts.String(PARAM_SLOTS,optional=True,grouping="4.1",
                       description="Choose available OpenLink area",
                       values=availableSlotsNames),
        scripts.Bool(PARAM_ATTACH,grouping="5",
                     description="Link all file attachments of selected and subordinate objects",default=True),


        namespaces=[omero.constants.namespaces.NSDYNAMIC],
        version="1.0.0",
        authors=["Susanne Kunis", "CellNanOs"],
        institutions=["University of Osnabrueck"],
        contact="sinukesus@gmail.com",
    )  # noqa

    try:
        params = client.getInputs(unwrap=True)
        if os.path.exists(OPENLINK_DIR):
            conn = BlitzGateway(client_obj=client)
            mrep,orep=get_omero_paths(client)

            global MANAGED_REP
            global ORIGINAL_REP

            if mrep:
                MANAGED_REP = mrep
            if orep:
                ORIGINAL_REP = orep
            # call main script, return the dest project
            message = addObjToAccessArea(conn,params,availableSlotsNames,paths)
            client.setOutput("Message", rstring(message))
        else:
            client.setOutput("ERROR",rstring("No such OpenLink directory: %s"%OPENLINK_DIR))
    finally:
        client.closeSession()


if __name__ == "__main__":
    run_script()
