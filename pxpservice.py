#!/usr/bin/python
from tendo import singleton
from datetime import datetime as dt
from uuid import getnode as getmac
from pxputil import TimedThread
from urlparse import parse_qsl
from itertools import izip_longest
import camera, constants as c, copy, json, os, psutil, pxp, pxputil as pu, signal, socket, subprocess as sb, time
import glob, sys, shutil, hashlib, re

# big broadcast queue - queue containing all of the sent messages for every client that it was sent to
# in this format:
# bbq = {
# '<clientIP_port>':[{
#       '<request1>':{'ACK':0/1, 'timesSent':<times_sent>, 'lastSent':<last_time_sent>, 'data':<data>},
#       '<request2>':{'ACK':0/1, 'timesSent':<times_sent>, 'lastSent':<last_time_sent>, 'data':<data>}
#   }, <client ref>, <send_next>], 
# '<clientIP_port>':[{
#       '<request1>':{'ACK':0/1, 'timesSent':<times_sent>, 'lastSent':<last_time_sent>, 'data':<data>},
#       '<request2>':{'ACK':0/1, 'timesSent':<times_sent>, 'lastSent':<last_time_sent>, 'data':<data>}
#   }, <client ref>, <send_next>] 
# }

globalBBQ = {}

lastStatus = 0
# when was a kill sig issued
lastKillSig = 0
# when was a start signal issued
lastStartSig = 0
bitENC      =  1 << 0
bitCAM      =  1 << 1
bitSTREAM   =  1 << 2
bitSTART    =  1 << 3

# remote sony cameras available for view:
# rtsp://121.2.70.2/media/video1
# rtsp://121.2.70.9/media/video1

#process manager instance
procMan     = None
#encoder devices found through bonjour
# in this format: 
# encoders = {
#     '192.168.1.153':{
#         'preview'     :'rtsp://192.168.1.153:554/stream1',
#         'preview_port': 554,
#         'url'         :'rtsp://192.168.1.153:554/quickstream', #url for the rtsp stream
#         'url_port'    : 554,      #port for the rtsp stream
#         'on'          : True,     #whether the stream is accessible
#         'enctype'     : 'td_cube' #what kind of encoder this is, teradek cube, matrox monarch etc.
#     }
encoders    = {}

tdSession   = {} # list of teradek session IDs - used for accessing the web API

camMP4base = 22500 #ffmpeg captures rtsp stream and outputs H.264 stream here
camHLSbase = 22600 #ffmpeg captures rtsp stream and outputs MPEG-TS here
chkPRTbase = 22700 #port where a monitor is sitting and checking if packets are arriving, doesn't matter the format
sockInPort = 2232


##########################
# debug printing function#
##########################
class debugLogger(object):
    """debugLogger class used for printing and logging debug information"""
    
    #these constants define log levels/groups
    ALL            = 0xFFFFFFFF #32-bit mask

    CMD            = 1<<0 # commander
    ECN            = 1<<1 # event cleanup function
    ERR            = 1<<2 # error
    BKP            = 1<<3 # backup entry

    ENC            = 1<<4 # encoder (server)
    TDK            = 1<<5 # teradek device
    MTX            = 1<<6 # matrox device
    PVH            = 1<<7 # pivothead device
    SNC            = 1<<8 # sony SNC
    TST            = 1<<9# test device

    SRC            = 1<<10 # video source (encoder/ip camera)
    SRM            = 1<<11 # source manager
    SSV            = 1<<12# SyncSrv
    SMG            = 1<<13# SyncMgr
    KLL            = 1<<14# pxpKiller
    PPC            = 1<<15# proc
    PCM            = 1<<16# proc manager
    DHL            = 1<<17# data handler
    SHL            = 1<<18# socket handler
    BBQ            = 1<<19# BBQ Manager
    DBG            = 1<<20# debugger

    MN             = 1<<21# main function

    #this property defines which of the above groups will be logged 
    LVL            = KLL|ERR|MN|SRC # USE WISELY!! too many groups will cause the log file to grow disproportionately large!
    #whether to log to file as well as to screen
    LOG            = 1 #only enable if you suspect there might be a problem, or for debugging

    def __init__(self):
        super(debugLogger, self).__init__()      
    def setLogLevel(self, level):
        """ set the log level"""
        try:
            self.LVL = int(level)
        except Exception, e:
            pass
    def setLog(self,log):
        """ set whether the log will be written to the file or not 
            Args:
                log(bool): True - write to file and screen, False - only output to screen
        """
        try:
            self.LOG = int(log)
            self.prn(self.DBG,"writing to log file set:",self.LOG)
        except Exception, e:
            pass
    def prn(self, kind, *arguments, **keywords):
        """ Outputs log statements
            Args:
                kind(int): bitmask for the type of log statement
                arguments(list): list of items to print on the same line
                keywords(dict): named arguments (not used here)
            Returns:
                none

        """
        if(not (kind & self.LVL)): #only print one type of event
            return
        # print arguments
        print dt.fromtimestamp(time.time()).strftime("%Y-%m-%d %H:%M:%S.%f"),'(',self._cmdName(kind),'):',(' '.join(map(str, (arguments)))), '[[written:',self.LOG,']]'
        if(self.LOG):
            try:
                # if the file size is over 1gb, delete it
                logFile = c.logFile
                if(os.path.exists(logFile) and os.stat(logFile).st_size>=(1<<30)):
                    os.remove(logFile)
                with open(logFile,"a") as fp:
                    fp.write(dt.fromtimestamp(time.time()).strftime("%Y-%m-%d %H:%M:%S.%f"))
                    fp.write(' '+' '.join(map(str, (arguments))))
                    fp.write("\n")
            except Exception as e:
                print "[---]prn:",e, sys.exc_traceback.tb_lineno
    #end prn
    def _cmdName(self,cmd):
        """ a command lookup dictionary """
        names = {
            self.CMD:"CMD",
            self.ECN:"ECN",
            self.ERR:"ERR",
            self.BKP:"BKP",
            self.ENC:"ENC",
            self.TDK:"TDK",
            self.MTX:"MTX",
            self.PVH:"PVH",
            self.SNC:"SNC",
            self.TST:"TST",
            self.SRC:"SRC",
            self.SRM:"SRM",
            self.SSV:"SSV",
            self.SMG:"SMG",
            self.KLL:"KLL",
            self.PPC:"PPC",
            self.PCM:"PCM",
            self.DHL:"DHL",
            self.SHL:"SHL",
            self.BBQ:"BBQ",
            self.DBG:"DBG",
            self.MN :"MN"
        }
        cmdList = []
        # go through each command and add it to the display list if its bit is set in the user's command
        for item in names:
            if(cmd & item):
                cmdList.append(names[item])
        return (',').join(cmdList)
#end debugLogger class

###################
## event backups ##
###################
class backupEvent(object):
    """event to be backed up"""
    STAT_INIT = 0    #event initialized
    STAT_START= 1<<0 #backup started
    STAT_DONE = 1<<1 #backup done (success)
    STAT_FAIL = 1<<2 #backup done (fail)
    STAT_NOEVT= 1<<3 #event doesn't exist
    STAT_NOBKP= 1<<4 #event was never added to the backup list
    STAT_NODRV= 1<<5 #no drive available for backup
    STAT_NOSPC= 1<<6 #no space on any drives
    autoDir = "/pxp-autobackup/"
    manualDir = "/pxp-backup/"
    def __init__(self, hid, priority, dataOnly=False, auto=False, restore=False, backupPath = False, cloud=False, remoteParams = {}):
        """ Constructor for the event that will be backed up
            Args:
                hid(str): hid of the event (from the database)
                priority(int): priority of the backed up event - events of higher priority will be backed up before events of lower priority
                dataOnly(bool, optional): back up only the metadata (.db file) and thumbnails. default: False
                auto(bool, optoinal): this is an autobackup event - determines the folder name, where to back up the event. default: False
                restore(bool, optional): restoring a backed up event. default: False
                backupPath(str,optional): the path to the backed up event on the backup drive. must be set for restoring events. default: False
                cloud(bool,optional): whether this is a cloud-x-sync
                remoteParams(dict,optional): arguments for x-sync (default: {}):
                    For local network x-sync:
                        files(list): list of relative paths (to every file) to save - directory structure will be preserved.
                        url(str): base url (full url to a file will be url+files[i])
                    For cloud x-sync:
                        id(int,optional): id of the remote event (if it already exists in the cloud). default: 0
                        down(bool, optional): whether this is a x-downlink (downloading cloud event to local encoder) or x-uplink (uploading local event to cloud). id must be set x-downlink. default: False
            Returns:
                none
        """
        # priorities:
        # manual restore: 10
        # manual backup: 5
        # x-sync: 3
        # cloud-x-sync:2
        # autobackup: 0
        super(backupEvent, self).__init__()
        try:
            self.hid = hid
            self.priority = priority
            self.size = 0
            self.copied = 0
            self.total = 1 #in case the status gets requested before copy starts, don't want division by zero
            self.status = self.STAT_INIT
            self.kill = False # flag will force-stop a copy
            self.auto = auto #this is an autobackup
            self.dataOnly = dataOnly #whether to backup data and video or just data
            self.currentFile = False
            self.restore = restore #whether this event is to be restored or backed up
            self.backupPath = backupPath #the path to the event on the backup drive
            self.remote = remoteParams #parameters for x-sync - downloading event files from a remote server
            self.cloud = cloud #whether this event is going to (or from) cloud
        except Exception as e:
            dbg.prn(dbg.BKP|dbg.ERR,"[---]bkp.init:",e,sys.exc_traceback.tb_lineno)
    def cancel(self):
        """ For an event that is still copying - send a kill signal to it """
        try:
            if(self.status & (self.STAT_START)): #the event didn't finish copying
                self.kill = True
            #end if bkp in tmr
        except Exception as e:
            dbg.prn(dbg.BKP|dbg.ERR,"[---]bkp.start:",e,sys.exc_traceback.tb_lineno)
        #end ifself.done
    #end cancel
    def monitor(self):
        """ Monitors the backup progress, updates total copied bytes """
        lastSize = self.copied
        lastBigSize = 0 #bytes copied of the current file at last check
        currentBigSize = 0
        lastFile = self.currentFile
        self.lastBigSize = 0
        try:
            while((self.status==self.STAT_START) and (not self.kill) and (not (enc.code & enc.STAT_SHUTDOWN))):
                time.sleep(5)
                dbg.prn(dbg.BKP,"copied: ", self.copied)
                if(self.currentFile and self.copied==lastSize and self.currentFile==lastFile): #probably copying a large file
                    currentBigSize = os.path.getsize(self.currentFile)
                    self.copied += currentBigSize - lastBigSize
                    lastBigSize = currentBigSize
                    self.lastBigSize = lastBigSize
                else:
                    lastSize = self.copied
                    lastFile = self.currentFile
                    lastBigSize = 0
                lastSize = self.copied
        except Exception as e:
            dbg.prn(dbg.BKP|dbg.ERR,"[---]bkp.monitor:",e,sys.exc_traceback.tb_lineno)
    #end monitor
    def onComplete(self):
        """ event gets called when event is done backing up (or restored) """
        self.currentFile = False
        if(self.copied>=self.total):
            self.status = self.STAT_DONE
        else:
            self.status = self.STAT_FAIL
        try:
            # remove the timer processes
            if(('bkp' in tmr) and (self.hid in tmr['bkp'])):
                tmr['bkp'][self.hid].kill()
                del tmr['bkp'][self.hid]
            if(('bkp' in tmr) and ((self.hid+'-mon') in tmr['bkp'])):
                tmr['bkp'][self.hid+'-mon'].kill()
                del tmr['bkp'][self.hid+'-mon']
            if(('bkp' in tmr) and ((self.hid+'-rst') in tmr['bkp'])):
                tmr['bkp'][self.hid+'-rst'].kill()
                del tmr['bkp'][self.hid+'-rst']
            if(('bkp' in tmr) and ((self.hid+'-rstmon') in tmr['bkp'])):
                tmr['bkp'][self.hid+'-rstmon'].kill()
                del tmr['bkp'][self.hid+'-rstmon']
            if(('bkp' in tmr) and ((self.hid+'-rmt') in tmr['bkp'])):
                tmr['bkp'][self.hid+'-rmt'].kill()
                del tmr['bkp'][self.hid+'-rmt']
            if(('bkp' in tmr) and ((self.hid+'-rmtmon') in tmr['bkp'])):
                tmr['bkp'][self.hid+'-rmtmon'].kill()
                del tmr['bkp'][self.hid+'-rmtmon']
        except Exception as e:
            dbg.prn(dbg.BKP|dbg.ERR,"[---]bkp.onComplete",e,sys.exc_traceback.tb_lineno)
        dbg.prn(dbg.BKP,"------------done backup-------------")
    #end onComplete
    def start(self):
        """ Start the copy procress. Based on initialized arguments, this function will start the proper method (i.e. cloud, x-sync, etc) """
        try:
            if(self.cloud): #this is a cloud-x-sync
                if('down' in self.remote and self.remote['down']):
                    self.startCloudDn() #x-downlink
                else:
                    self.startCloudUp() #x-uplink
            elif(self.remote):
                # this is a remote event, in order to back it up (or x-sync it), 
                # the event has to be downloaded and added to the local database (if it doesn't exist yet)
                self.startRemote()
            elif(self.restore): #restoring a backed up event
                self.startRestore()
            else: #standard run-of-the-mill backup
                self.startBackup()
        except Exception as e:
            dbg.prn(dbg.BKP|dbg.ERR,"[---]bkp.start",e,sys.exc_traceback.tb_lineno)
    def startBackup(self):
        """ Start local backup - to an attached storage. This is called for automatic or manual backups """
        # get info about the event
        try:
            dbg.prn(dbg.BKP, "starting local backup")
            self.status = self.STAT_START
            db = pu.db(c.wwwroot+"_db/pxp_main.db")
            sql = "SELECT * FROM `events` WHERE `hid` LIKE ?"
            db.query(sql,(self.hid,))
            eventData = db.getasc()
            db.close()
            if(len(eventData)<1): #the event doesn't exist - return
                self.status = self.STAT_FAIL | self.STAT_NOEVT
                return False
            dbg.prn(dbg.BKP,"event details:",eventData)
            # path to the event
            originPath = c.wwwroot+eventData[0]['datapath']
            # size of the event
            evtSize = pu.disk.dirSize(originPath)
            self.total = evtSize
            dbg.prn(dbg.BKP,"event size:",evtSize)
            # get a list of all attached devices
            drives = pu.disk.list()
            dbg.prn(dbg.BKP,"found drives:", drives)
            if(len(drives)<1): #no drives
                self.status = self.STAT_NODRV | self.STAT_FAIL
                return
            if(self.auto):
                backupDir = self.autoDir
            else:
                backupDir = self.manualDir
            # look for which one to back up to
            # first check all drives for the backupDir, if it exists, just back up to it (if it has enough space and write permissions)
            backupDrive = False
            for drive in drives:
                if(os.path.exists(drive+backupDir) and os.access(drive,os.W_OK)): #found a drive that has previous backups and write permissions
                    # check space
                    try:
                        driveInfo = pu.disk.stat(humanReadable=False,path=drive)
                        if(driveInfo['free']>evtSize):
                            # there is enough space for backup - use this drive
                            backupDrive = drive
                            break
                    except:
                        pass
                #end if path.exists
            #end for drive in drives
            if(not backupDrive): #no drive found with backup folder, look for any available drive
                # NB: automatic backups are only done to a drive that has pxp-autobackup folder
                # NB: manual backups cannot be done to a drive that has pxp-autobackup folder
                for drive in drives:
                    driveInfo = pu.disk.stat(humanReadable=False,path=drive)
                    if(driveInfo['free']>evtSize and os.access(drive,os.W_OK) and (os.path.exists(drive+self.autoDir) == self.auto)):
                        backupDrive = drive
                        break
                #end for drive in drives
            #end if not backupDrive
            if(backupDrive): #found a backup drive
                dbg.prn(dbg.BKP,"free on ",drive,":",driveInfo['free'])
                outputPath = backupDrive.decode('UTF-8')+backupDir+eventData[0]['datapath']
                pu.disk.mkdir(outputPath) # create the output directory
                # save the event info
                eventString = json.dumps(eventData[0])
                pu.disk.file_set_contents(outputPath+"/event.json",eventString)
                if(not('bkp' in tmr)):
                    tmr['bkp']={ }
                if(not self.dataOnly):
                    # start copying files
                    tmr['bkp'][self.hid]=TimedThread(self.treeCopy,params=(originPath,outputPath))
                    tmr['bkp'][self.hid+'-mon']=TimedThread(self.monitor)
                else:
                    # backup the database
                    shutil.copy(originPath+'/pxp.db',outputPath+'/pxp.db')
                    # backup the thumbnails
                    tmr['bkp'][self.hid]=TimedThread(self.treeCopy,params=(originPath+'/thumbs',outputPath+'/thumbs'))
            else:
                self.status = self.STAT_NODRV | self.STAT_FAIL
        except Exception as e:
            dbg.prn(dbg.BKP|dbg.ERR,"[---]bkp.startBackup:",e,sys.exc_traceback.tb_lineno)
            self.status = self.STAT_FAIL
    #end startBackup
    def startCloudUp(self):
        """ Start cloud backup """
        try:
            dbg.prn(dbg.BKP,"starting cloud backup")
            remote = {"id":0,"down":False} #defaults for remoteParams
            remote.update(self.remote)
            self.status = self.STAT_START
            # get authentication credentials
            cfg = pxp._cfgGet()
            if(not cfg):
                return False #the encoder is not initalized yet most likely
            # check if this is an x-uplink
            # get local event details
            db = pu.db(c.wwwroot+"_db/pxp_main.db")
            sql = "SELECT * FROM `events` WHERE `hid` LIKE ?"
            db.query(sql,(self.hid,))
            eventData = db.getasc()
            db.close()
            if(len(eventData)<1): #this event doesn't exist - return (could happen if SOMEHOW the folder gets deleted at the exact moment this function gets called)
                self.status = self.STAT_FAIL | self.STAT_NOEVT
                return False
            # get the path 
            eventPath = c.wwwroot+eventData[0]['datapath']
            if(not remote['id']): # remote event doesn't exist yet - create it in the cloud
                # get HIDs of teams and league - they're stored in the log table of the event database
                sql = "SELECT `id` FROM `logs` WHERE `type` LIKE 'enc_start'"
                db = pu.db(eventPath + '/pxp.db')
                db.qstr(sql)
                hids = db.getrow()
                db.close()
                hids = hids[0].split(',')
                # now hids contains home team [0], visitor team [1] and league [2] hid's
                # set up a request for creating event in the cloud
                params = {
                    "v0":cfg[1],
                    "v4":cfg[2],
                    "homeTeam":hids[0],
                    "visitorTeam":hids[1],
                    "league":hids[2],
                    "date":dt.fromtimestamp(time.time()).strftime("%Y-%m-%d %H:%M:%S"), #date in YYYY-MM-DD HH:MM:SS format
                    "hid":self.hid
                }
                resp = pu.io.send(c.cloud+"eventSet/ajax",params,jsn=True)
                dbg.prn(dbg.BKP,"eventset response:",resp)
                if(not (resp and 'success' in resp and resp['success'] and 'msg' in resp)):
                    self.status = self.STAT_FAIL
                    return False
                remote['id'] = resp['msg'] #the response message contains id of the newly created cloud event
                self.remote.update(remote) #add passed remote parameters to the default parameters dictionary
                dbg.prn(dbg.BKP,"remote params:",self.remote)
            #end if not remote[id]
            # at this point the event exists in the cloud database
            # get size of the metadata and thumbnails
            metaSize = pu.disk.dirSize(eventPath+'/thumbs')+os.path.getsize(eventPath+'/pxp.db')
            # upload the data file

            if(self.dataOnly): # not uploading segments - move on
                dbg.prn(dbg.BKP,"starting data only cloud backup")
                # start uploading thumbnails and data only
                self.cloudUpCopy(src=eventPath+'/thumbs',cloudID=remote['id'],auth=cfg[1],cust=cfg[2],relPath='/thumbs')
                self.cloudUpCopy(src=eventPath+'/pxp.db',cloudID=remote['id'],auth=cfg[1],cust=cfg[2],relPath='/')
            else:# start uploading entire event (.mp4 files will be excluded automatically)
                dbg.prn(dbg.BKP,"starting full event cloud backup")
                self.cloudUpCopy(src=eventPath,cloudID=remote['id'],auth=cfg[1],cust=cfg[2])

        except Exception as e:
            dbg.prn(dbg.BKP|dbg.ERR,"[---]bkp.startCloud:",e,sys.exc_traceback.tb_lineno)
            self.onComplete()
            self.status = self.STAT_FAIL
    #end startCloud
    def startRemote(self):
        """ Start x-sync: copying files from a remote location on the same network to the local server. """
        # find path to the event.json
        try:
            if(not 'files' in self.remote): #there is no file list to backup passed in the remote parameter
                return False
            dbg.prn(dbg.BKP,"starting remote backup")
            jsonPath = False
            self.status = self.STAT_START
            for entry in self.remote['files']:
                if(entry.find('event.json')>=0):
                    jsonPath = entry
                    break
            if(not jsonPath):#can't find event file - no point to copy data
                self.status = self.STAT_FAIL
                dbg.prn(dbg.BKP,"not found event.json????", self.hid)
                return
            dbg.prn(dbg.BKP,"getting data...")
            # get the event.json file to get event details (to add to the database)
            resp = pu.io.url(self.remote['url']+jsonPath)
            dbg.prn(dbg.BKP,"got: ", resp)
            eventData = json.loads(resp)
            if(not(('hid' in eventData) and ('date' in eventData) and ('homeTeam' in eventData) and ('visitTeam' in eventData) and ('league' in eventData) and ('datapath' in eventData) and ('extra' in eventData))):
                # one of the required fields is missing
                self.status = self.STAT_FAIL
                return
            dbg.prn(dbg.BKP,"prep DB")
            db = pu.db(c.wwwroot+"_db/pxp_main.db")
            sql = "DELETE FROM `events` WHERE `hid` LIKE ?"
            db.query(sql,(eventData['hid'],))
            # add event to the main database
            sql = "INSERT INTO `events` (`hid`,`date`,`homeTeam`,`visitTeam`,`league`,`datapath`,`extra`) VALUES(?,?,?,?,?,?,?)"
            db.query(sql,(eventData['hid'],eventData['date'],eventData['homeTeam'],eventData['visitTeam'],eventData['league'],eventData['datapath'],eventData['extra']))
            db.close()
            # start copying the data
            outputPath = c.wwwroot+eventData['datapath'].rstrip('/')
            dbg.prn(dbg.BKP,"start copy... ", outputPath)

            # save the event info
            if(not('bkp' in tmr)):
                tmr['bkp']={ }
            # start copying files
            tmr['bkp'][self.hid+'-rmt']=TimedThread(self.webCopy,params=(self.remote['url'],self.remote['files'],outputPath))
            tmr['bkp'][self.hid+'-rmtmon']=TimedThread(self.monitor)            
        except Exception as e:
            dbg.prn(dbg.BKP|dbg.ERR,"[---]bkp.startRemote:",e,sys.exc_traceback.tb_lineno)
            self.status = self.STAT_FAIL
    def startRestore(self):
        """ Start restoring a file from a local backup. """
        try:
            self.status = self.STAT_START
            # find event on the backup drive
            if(not (self.backupPath and os.path.exists(self.backupPath+"/event.json"))): #without this file, can't get any details about the event
                self.status = self.STAT_FAIL | self.STAT_NOEVT
                dbg.prn(dbg.BKP,"no event: ", self.backupPath)
                return
            # get event size
            evtSize = pu.disk.dirSize(self.backupPath)
            self.total = evtSize
            # get hdd free space
            hdd = pu.disk.stat(humanReadable=False,path="/")
            if(hdd['free']<evtSize): #not enough free space to restore the event
                self.status = self.STAT_FAIL | self.STAT_NOSPC
                return
            # get event details
            eventString = pu.disk.file_get_contents(self.backupPath+"/event.json")
            eventData = json.loads(eventString)
            if(not(('hid' in eventData) and ('date' in eventData) and ('homeTeam' in eventData) and ('visitTeam' in eventData) and ('league' in eventData) and ('datapath' in eventData) and ('extra' in eventData))):
                # one of the required fields is missing
                self.status = self.STAT_FAIL
                return
            # make sure this event doesn't already exist in the database - simply delete it (if it exists)
            db = pu.db(c.wwwroot+"_db/pxp_main.db")
            sql = "DELETE FROM `events` WHERE `hid` LIKE ?"
            db.query(sql,(eventData['hid'],))
            # add event to the main database
            sql = "INSERT INTO `events` (`hid`,`date`,`homeTeam`,`visitTeam`,`league`,`datapath`,`extra`) VALUES(?,?,?,?,?,?,?)"
            db.query(sql,(eventData['hid'],eventData['date'],eventData['homeTeam'],eventData['visitTeam'],eventData['league'],eventData['datapath'],eventData['extra']))
            db.close()
            # start copying the data
            outputPath = c.wwwroot+eventData['datapath']
            # pu.disk.mkdir(outputPath) # create the output directory
            # save the event info
            if(not('bkp' in tmr)):
                tmr['bkp']={ }
            # start copying files
            tmr['bkp'][self.hid+'-rst']=TimedThread(self.treeCopy,params=(self.backupPath,outputPath))
            tmr['bkp'][self.hid+'-rstmon']=TimedThread(self.monitor)            
        except Exception as e:
            dbg.prn(dbg.BKP|dbg.ERR,"[---]bkp.startRestore:",e,sys.exc_traceback.tb_lineno)
            self.onComplete()
            self.status = self.STAT_FAIL
    #end startRestore
    def statusFull(self):
        """ Returns list with status and progress of the current item:
            [0]: status
            [1]: percent copied
            Statuses:
                STAT_INIT = 0    :event initialized
                STAT_START= 1<<0 :backup started
                STAT_DONE = 1<<1 :backup done (success)
                STAT_FAIL = 1<<2 :backup done (fail)
                STAT_NOEVT= 1<<3 :event doesn't exist
                STAT_NOBKP= 1<<4 :event was never added to the backup list
                STAT_NODRV= 1<<5 :no drive available for backup
                STAT_NOSPC= 1<<6 :no space on any drives
        """
        return [self.status, self.copied*100/self.total]
    #end statusFull
    def treeCopy(self,src,dst,topLevel = True):
        """ recursively copies a directory tree from src to dst 
            Args:
                src(str): full path to the source directory
                dst(str): full path to the destination directory
                topLevel(bool,optional): this is for internal use only - this lets recursion know if finished processing top level directory to call onComplete function. MUST NOT OVERRIDE THIS VALUE.
            Returns:
                none
        """
        try:
            if(self.kill or (enc.code & enc.STAT_SHUTDOWN)):
                self.onComplete()
                return
            if(os.path.isfile(src)): #this is a file
                self.currentFile = dst
                shutil.copy(src,dst) #copy file
                if(hasattr(self,'lastBigSize') and self.lastBigSize>0): #correct for large copy progress file size
                    self.copied -= self.lastBigSize
                    self.lastBigSize = 0
                self.copied += os.path.getsize(src)
            elif(os.path.isdir(src)): #this is a directory
                if(not os.path.exists(dst)):
                    pu.disk.mkdir(dst)
                # get the directory list and go through each item, copying it
                files = os.listdir(src)
                for item in files:
                    if(self.kill or (enc.code & enc.STAT_SHUTDOWN)): #immediately return if force-stop requested
                        return
                    if(item=='.' or item=='..'):
                        continue #skip the nonsensical files
                    self.treeCopy(src+'/'+item, dst+'/'+item, topLevel = False)
        except Exception as e:
            dbg.prn(dbg.BKP|dbg.ERR,"[---]bkpevt.treecopy", e, sys.exc_traceback.tb_lineno)
        if(topLevel):
            self.onComplete()
    # end treeCopy
    def cloudUpCopy(self,src,cloudID,auth,cust,topLevel = True,relPath = ''):
        """ Recursively copy a specified directory (and all subdirectories) to the cloud 
            Args:
                src(str): path to the local file (or directory) to upload
                cloudID(int): id of the event in the cloud
                auth(str): authorization ID
                cust(str): customer HID
                topLevel(bool,optional): this is used for determining when the copy is done. NB: SETTINGS THIS TO FALSE MANUALLY WILL CAUSE THE FUNCTION TO STALL
                relPath(str,optional): Path where to store local file, relative to the current event directory
            Returns:
                none
        """
        try:
            resp = False
            if(self.kill or (enc.code & enc.STAT_SHUTDOWN)):
                self.onComplete()
                return
            if(os.path.isfile(src)): #this is a file
                if(src[-3:].lower()=='mp4'):
                    return #skip mp4 files
                # remove the file name from the relPath
                relPath = relPath[:relPath.rfind('/')]
                # upload the file                
                resp = pu.io.uploadCloud(url=c.cloud+"upload/event/"+str(cloudID)+"/ajax",filePath=src,params={"v0":auth,"v4":cust,"path":relPath})
                resp = json.loads(resp)
                if(not('success' in resp and resp['success'])): #upload failed
                    dbg.prn(dbg.BKP,"cloud upload ", src, "response:",resp)
                    # try uploading again - might want to put this into a while loop with some sort of fail counter limit
                    resp = pu.io.uploadCloud(url=c.cloud+"upload/event/"+str(cloudID)+"/ajax",filePath=src,params={"v0":auth,"v4":cust,"path":relPath})                    
            elif(os.path.isdir(src)): #this is a directory
                # get the directory list and go through each item, uploading it
                files = os.listdir(src)
                for item in files:
                    if(self.kill or (enc.code & enc.STAT_SHUTDOWN)): #immediately return if force-stop requested
                        return
                    if(item=='.' or item=='..' or item=='.DS_Store'):
                        continue #skip the nonsensical files
                    self.cloudUpCopy(src+'/'+item, cloudID,auth,cust, topLevel = False,relPath=relPath+'/'+item)
        except Exception as e:
            dbg.prn(dbg.BKP|dbg.ERR,"[---]bkpevt.cloudUpCopy src:",src,"resp:",resp, e, sys.exc_traceback.tb_lineno)
        if(topLevel):
            self.onComplete()
    def webCopy(self,url,fileList,dst):
        """ Download files from the specified url and saves them to the local directory
            Args:
                url(str) : base url of the server where to download files
                fileList(list) : list of files with their path relative to the 'url'
                dst(str) : destination directory on the local drive, where to save files
            Returns:
                none
        """
        try:
            # this is the directory where the event will be stored
            fileHome = dst[dst.rfind('/'):]
            dbg.prn(dbg.BKP,"fileHome:",fileHome)
            for item in fileList:
                if(self.kill or (enc.code & enc.STAT_SHUTDOWN)):
                    break
                dbg.prn(dbg.BKP,"trying ", item)
                # get full directory path (excluding the file)
                fullDir = dst+item[item.find(fileHome)+len(fileHome):item.rfind('/')]
                dbg.prn(dbg.BKP,"dir", fullDir)
                # make sure the required directory exists
                if(not os.path.exists(fullDir)):
                    pu.disk.mkdir(fullDir)
                # get the file path (relative to the dst)
                fullPath = dst+item[item.find(fileHome)+len(fileHome):]
                dbg.prn(dbg.BKP,"path:",fullPath)
                if(fullPath[-1]=='/'): #this entry simply indicates the directory - it was already created in the previous step, nothing else to do here
                    continue
                # download the file
                if(item.lower().find('.ds_store')>=0): #skip idiotic .ds_store files created by apple
                    continue
                pu.io.urlFile(url=url+item,dst=fullPath)
                if(hasattr(self,'lastBigSize') and self.lastBigSize>0):
                    self.copied -= self.lastBigSize
                    self.lastBigSize = 0
                self.copied += os.path.getsize(fullPath)
            #end for item
        except Exception as e:
            dbg.prn(dbg.BKP|dbg.ERR,"[---]bkpevt.webCopy", e, sys.exc_traceback.tb_lineno)
        self.onComplete()
    #end webCopy
class backupManager(object):
    """ Backup events manager """
    def __init__(self):
        super(backupManager, self).__init__()
        try:
            dbg.prn(dbg.BKP,"backup Manager initialized")
            self.lastActive = int(time.time())
            self.events = { }  # dictionary of event instances (to be backed up)
            self.completed = { } #dictionary of events that have been backed up
            self.priorities = { } #dictionary of lists of events (i.e. all events are grouped by their priority here)
            self.current = False #hid of the currently executing backup
            self.archivedEvents = False
            # start backup manager process
            tmr['backupmgr'] = TimedThread(self.process,period=3) #
            tmr['autobackp'] = TimedThread(self.autobackup,period=20) #run auto backup once every 10 minutes
        except Exception, e:
            dbg.prn(dbg.BKP|dbg.ERR,"bkpmgr.err:",e,sys.exc_traceback.tb_lineno)
    def add(self, hid, priority=0, dataOnly=False, auto = False, restore=False, cloud=False, remoteParams = {}):
        """ Add an event to the list of events to be backed up 
            Args:
                for arguments description, see backupEvent class constructor
            Returns:
                none
        """
        try:
            if(hid in self.events):
                return #skip an event that was already added but not processed yet
            backupPath = False #this will be retrieved here
            if(restore):
                # restoring event, get its path on the backup drive
                if(not self.archivedEvents): #list of archived events wasn't created yet, create a new one
                    self.archivedEvents = self.archiveList()
                if(hid in self.archivedEvents): #check if the event that's being restored is in the list
                    backupPath = self.archivedEvents[hid]['archivePath']
            dbg.prn(dbg.BKP,"backing up event:",hid, priority, dataOnly, auto, restore, backupPath, cloud, remoteParams)
            self.events[hid] = backupEvent(hid, priority, dataOnly, auto, restore, backupPath, cloud, remoteParams)
            dbg.prn(dbg.BKP,"all events to back up:",self.events)
            if(not (priority in self.priorities)): #there are no events with this priority yet - add the priority
                self.priorities[priority] = [ ]
            self.priorities[priority].append(hid) #add event to the list of events with the same priority
        except Exception as e:
            dbg.prn(dbg.BKP|dbg.ERR,"[---]bkpmgr.add: ", e,sys.exc_traceback.tb_lineno)
    def archiveList(self):
        """ Get a list of all archived events with their paths 
            Args:
                none
            Returns:
                (dictionary)
        """
        try:
            drives = pu.disk.list()
            if(len(drives)<1): #no drives available
                dbg.prn(dbg.BKP,"no drives????")
                return {"entries":[]}# there are no events in the list
            self.archivedEvents = { } #clean the list of archived events for whomever needs to access it later
            events = []
            eventDirs = []
            dbg.prn(dbg.BKP,"starting list...")
            for drive in drives:
                if(not(os.path.exists(drive+backupEvent.autoDir) or os.path.exists(drive+backupEvent.manualDir))): #this drive does not have any pxp backups
                    continue
                # this drive contains a backup
                backupDrive = drive.decode('UTF-8')
                autoDirs = []
                manualDirs = []
                autoPath = backupDrive+backupEvent.autoDir
                manuPath = backupDrive+backupEvent.manualDir
                if(os.path.exists(autoPath)):# this drive contains automatic backups
                    autoDirs = os.listdir(autoPath) #get a list of directories (events) here
                if(os.path.exists(manuPath)):# this drive contains manually backed up events
                    manualDirs = os.listdir(manuPath) #get a list of those events
                allDirs = list(autoPath+x for x in autoDirs)
                allDirs.extend(manuPath+x for x in manualDirs if autoPath+x not in allDirs)
                eventDirs += allDirs
            #end for drive in drives
            for eventDir in eventDirs:
                # get info about the events in each directory
                if(not os.path.exists(eventDir+'/event.json')):
                    continue
                try:
                    event = json.loads(pu.disk.file_get_contents(eventDir.encode('UTF-8')+'/event.json'))
                    event['archivePath']=eventDir.encode('UTF-8')
                    evtSize = pu.disk.dirSize(eventDir)
                    event['size']=pu.disk.sizeFmt(evtSize)
                    # check if this event is in the existing events on the hdd
                    event['exists']=os.path.exists(c.wwwroot+event['datapath'])
                    self.archivedEvents[event['hid']]=copy.copy(event) #save for later in case user wants to restore an event
                    events.append(event)
                except Exception as e:
                    dbg.prn(dbg.BKP|dbg.ERR,"[---]bkpmgr.foreventdir:",e,sys.exc_traceback.tb_lineno)
            return events
        except Exception as e:
            dbg.prn(dbg.BKP|dbg.ERR,"[---]bkpmgr.archlist", e, sys.exc_traceback.tb_lineno)
    def autobackup(self):
        """ Automatically back up all events (if there's a drive with pxp-autobackup folder on it)"""
        try:
            if((int(time.time()) - self.lastActive)<10): #has been idle for less than 10 seconds, wait some more
                dbg.prn(dbg.BKP,"busy... idle for:",(int(time.time())-self.lastActive))
                # the machine is busy (there's most likely a live game going on) make sure there are no events being backed up right now
                if(self.current): 
                    self.stop(stopAll = True)
                return
            # check if there is a live event
            if(enc.busy()): #there is a live event - wait until it's done in order to start the back up
                self.lastActive = int(time.time())
                return
            if(len(self.events)>0): #events are being backed up - wait until that's done to check for new events
                dbg.prn(dbg.BKP,"already backing up...",len(self.events))
                return
            #######################################
            # local backup checks

            # get the device that has autobackup folder:
            drives = pu.disk.list()
            backupDrive = False
            # look for which one to use for back up
            for drive in drives:
                if(not os.path.exists(drive+backupEvent.autoDir)): #this is not the auto-backup for pxp
                    continue
                backupDrive = drive.decode('UTF-8') #decoding is required for drives that may have odd mount points (e.g. cyrillic letters in the directory name)
            #########################################
            # cloud backup checks
            
            # get all cloud events
            settings = pu.disk.cfgGet(section="uploads")
            if('autoupload' in settings and int(settings['autoupload'])): #automatic cloud upload is enabled
                cloudList = self.getCloudEvents()
                dbg.prn(dbg.BKP, "cloud events:",cloudList)
            else:
                dbg.prn(dbg.BKP, "cloud upload disabled")
                cloudList = False #automatic upload is disabled
                if(not backupDrive): 
                    return #did not find an auto-backup device - nothing to do if not backing up locally or to cloud

            # get all events in the system
            elist = pxp._listEvents(showDeleted=False)
            # go through all events that exist and verify that they're identical on the backup device
            for event in elist:
                if(not('datapath' in event)):
                    continue #this event does not have a folder with video/tags - nothing to do here
                #### local backup ####
                if(backupDrive):
                    # see if this event exists on the backup device
                    if(os.path.exists(backupDrive+backupEvent.autoDir+event['datapath'])):
                        # the event was already backed up
                        # check for differences in video (simple size check - less io operations)
                        vidSize = pu.disk.dirSize(c.wwwroot+event['datapath']+'/video')
                        bkpSize = pu.disk.dirSize(backupDrive+backupEvent.autoDir+event['datapath']+'/video')
                        if(bkpSize!=vidSize): #there's a mismatch in the video - backup the whole event again
                            self.add(hid=event['hid'],auto=True)
                        else:
                            # the video is identical, check data file
                            oldDb = backupDrive+backupEvent.autoDir+event['datapath']+'/pxp.db'
                            newDb = c.wwwroot+event['datapath']+'/pxp.db'
                            md5old = hashlib.md5(open(oldDb, 'rb').read()).hexdigest()
                            md5new = hashlib.md5(open(newDb, 'rb').read()).hexdigest()
                            if(md5old!=md5new): #the database is different - back up the new database
                                self.add(hid=event['hid'],dataOnly=True,auto=True)
                    else: #this event doesn't exist on the backup drive - back it up
                        dbg.prn(dbg.BKP,"event doesn't exist", event)
                        self.add(hid=event['hid'],auto=True)
                #end if backupDrive
                if(not type(cloudList) is dict):
                    # could not get cloud events: either no internet connection, 
                    # or this device is deactivated, or the customer is deactivated
                    # or uploading to cloud is disabled
                    continue 
                #### cloud backup ####
                # check if this event exists in the cloud
                if(event['hid'] in cloudList): #the event exists in the cloud, verify its checksum and number of segments (that's what's being uploaded)
                    # count segments in the local event
                    segs = len(glob.glob(c.wwwroot+event['name']+'/video/*.ts'))
                    # get md5 checksum of the local .db
                    md5local = hashlib.md5(open(c.wwwroot+event['name']+'/pxp.db', 'rb').read()).hexdigest()
                    cfg = pxp._cfgGet()
                    if(not cfg): 
                        return False #the encoder is not initalized yet most likely (???) - if got to this point, the encoder HAS TO BE initialized!!
                    try:
                        # get details about remote event
                        response = pu.io.url(c.cloud+"ajEvent/ajax",params={"v0":cfg[1],"v4":cfg[2],"id":cloudList[event['hid']]['id']})
                        if(not response): #connection error
                            dbg.prn(dbg.BKP,"could not get info about cloud event:",cloudList[event['hid']]['id'])
                            continue
                        data = json.loads(response)
                        data = data['entries']
                        dbg.prn(dbg.BKP,"NUM SEGS>>>>>>> remote:",data['segs'],', local:',segs)
                        # TODO 
                        # -add a check to see if each segment's md5 matches
                        # -add resume: i.e. only upload segments that are partially or not uploaded to cloud. 
                        #  do not do full re-upload if 1 segment is missing
                        if(int(data['segs'])!=segs): #number of segments is different - upload the video file
                            self.add(hid=event['hid'], priority=2, cloud=True, remoteParams={'id':cloudList[event['hid']]['id']})
                        elif(data['md5']!=md5local): #video is the same, meteadata is different - upload just metadata
                            self.add(hid=event['hid'], priority=2, cloud=True, remoteParams={'id':cloudList[event['hid']]['id']}, dataOnly=True)
                    except Exception, e:
                        dbg.prn(dbg.ERR|dbg.BKP,"[---]autobackup.url:",response,e,sys.exc_traceback.tb_lineno)
                else: #this event doesn't exist in the cloud yet - upload it (video and metedata)
                    self.add(hid=event['hid'], priority=2, cloud=True)

            #end for event in elist
        except Exception as e:
            dbg.prn(dbg.ERR|dbg.BKP,"[---]bkpmgr.autobackup",e,sys.exc_traceback.tb_lineno)
    # get a list of all events in the cloud
    def getCloudEvents(self):
        """ Retreive all events from the cloud that this user has access to. 
            Args:
                none
            Returns:
                (dictionary)
        """
        # send a request with authorization id for this customer
        try:
            response = False
            cfg = pxp._cfgGet()
            if(not cfg):
                return False #the encoder is not initalized yet most likely - nothing to do here
            response = pu.io.url(c.cloud+"ajEvents/ajax",params={"v0":cfg[1],"v4":cfg[2]})
            if(not response):
                return False #cloud not available
            data = json.loads(response)
            if('success' in data and data['success'] and 'entries' in data):
                # entries contains a list of past events. convert them into hid:{....} format (dictionary)
                events = {}
                for evt in data['entries']:
                    events[evt['hid']]=evt
                return events
            dbg.prn(dbg.BKP|dbg.ERR,"bkpmgr.getCloudEvents: corrupt response ", data)
            return False #response was corrupt
        except Exception as e:
            dbg.prn(dbg.BKP|dbg.ERR,"[---]bkpmgr.getCloudEvents: ", e, sys.exc_traceback.tb_lineno, response)
        return False
    #end getCloudEvents

    def list(self,incomplete=False):
        """ List HIDs of all events that are being backed up currently. Does not include events being copied to cloud or remote backups or restores, unless specified otherwise.
            Args:
                incomplete(bool): when true, lists all events (including ones being backed up to this encoder, i.e. remote backups and restores, cloud uploads)
            Returns:
                (list): HIDs of events that are in the backup/restore queue
        """
        try:
            result = []
            events = copy.deepcopy(self.events)
            for hid in events:
                if(not(events[hid].remote or events[hid].restore) or incomplete):
                    result.append(hid)
        except Exception as e:
            dbg.prn(dbg.ERR|dbg.BKP,"[---]bkpmgr.list",e,sys.exc_traceback.tb_lineno)
        return result

    def process(self):
        """ Process the queue - start a backup according to priority, if there's nothing backed up at the moment, remove completed backups """
        try:
            if(len(self.priorities)<=0 or (enc.code & enc.STAT_SHUTDOWN)): 
                #there are no events in the queue or the server is being shut down
                return
            # there are events in the queue
            # find event with highest priority
            priorities = copy.deepcopy(self.priorities)
            maxPriority = 0
            for priority in priorities:
                maxPriority = max(priority,maxPriority)
            if (not self.current): #there is no event being processed right now
                # get the next available event and start backing it up
                self.current = self.priorities[maxPriority][0]
                dbg.prn(dbg.BKP,"current:",self.events[self.current])
                self.events[self.current].start()
            # if got here, means there are events to back up (or being backed up)
            # check to see if the event is done copying
            if (self.current and self.events[self.current].status & (backupEvent.STAT_DONE | backupEvent.STAT_FAIL)): #event is done (or failed)
                self.completed[self.current] = copy.deepcopy(self.events[self.current]) #add event to the completed dictionary
                self.stop() #this will also remove event from the events[] dictionary
            
            if (self.current and (self.events[self.current].priority<maxPriority)):
                #found an event with higher priority than the one being copied right now - stop current copy
                self.stop()
        except Exception as e:
            dbg.prn(dbg.ERR|dbg.BKP, "[---]bkpmgr.process",e,sys.exc_traceback.tb_lineno)
    def status(self,hid):
        """ Returns list with current event status
            Args:
                hid(str): HID of the event whose status to check
            Returns:
                (list):
                    if event is in the list, result is same as statusFull()
                    if event is not in the list:
                        [0]: whether the event backup failed
                        [1]: 0
        """
        try:
            if(hid and hid in self.events):
                return self.events[hid].statusFull()
            if(hid and hid in self.completed):
                return self.completed[hid].statusFull()
        except Exception as e:
            dbg.prn(dbg.ERR|dbg.BKP,"[---]bkp.status:",e,sys.exc_traceback.tb_lineno)
        # this event was never backed up
        dbg.prn(dbg.ERR,"no status for ", hid)
        return [backupEvent.STAT_FAIL|backupEvent.STAT_NOBKP,0]
    def stop(self, stopAll = False):
        """ Stop copying current event
            Args:
                stopAll(bool): stop copying current event and clear the queue (no other events will be copied)
            Returns:
                none
        """
        try:
            hid = self.current
            if (hid and (hid in self.events)):#there is an event being copied right now (or just finished)
                priority = self.events[hid].priority #get its priority (to remove later from the list of priorities)
                self.events[hid].cancel() #stop the copy, if it's still running
                del self.events[hid] #remove event from the events dictionary
                self.priorities[priority].remove(hid) #remove the event from priorities list
                if(len(self.priorities[priority])<=0): #there are no other events with this priority - remove it from the dictionary
                    del self.priorities[priority]
                self.current = False #no current events at the moment
            if(stopAll): #user requested to stop all events - simply clear the queues
                self.events = { }
                self.priorities = { }
        except Exception as e:
            dbg.prn(dbg.ERR|dbg.BKP,"[---]bkpmgr.stop",e,sys.exc_traceback.tb_lineno)
##################
## delete files ##
##################
rmFiles     = []
rmDirs      = []
FNULL       = open(os.devnull,"w") #for dumping all cmd output using Popen()
def deleteFiles():
    """ Deletes folders and files from the rmDirs and rmFiles lists.
        TODO: convert this into its own class instead of a function with a global variable.
    """
    try:
        dbg.prn(dbg.ECN,"deleteFiles called")
        # if there is a deletion in progress - let it finish
        if (pu.disk.psOn("rm -f") or pu.disk.psOn("rm -rf") or pu.disk.psOn("xargs -0 rm") or not (enc.code & (enc.STAT_READY | enc.STAT_NOCAM))):
            return
        # check how big is the log file
        if(os.path.exists(c.logFile) and (os.stat(c.logFile).st_size>c.maxLogSize)):
            #the file is too big - leave only last 500k lines in there (should be about 40-50mb)
            os.system("cat -n 500000 "+c.logFile+" > "+c.logFile)
        # first, take care of the old session files (>1 day) should take no more than a couple of seconds
        os.system("find "+c.sessdir+" -mtime +1 -type f -print0 | xargs -0 rm 2>/dev/null &")
        dbg.prn(dbg.ECN,"delete files: ",rmFiles)
        # delete individual files
        while(len(rmFiles)>0):
            # grab the first file from the array
            fileToRm = rmFiles[0]
            # make sure it wasn't deleted already
            if(os.path.exists(fileToRm)):
                os.system("rm -f "+fileToRm)
                #remove 1 file at a time
                return
            # remove deleted file from the list
            rmFiles.pop(0)
        #when all files are deleted, remove directories
        while(len(rmDirs)>0):
            # grab the first file from the array
            dirToRm = rmDirs[0]
            # make sure it wasn't deleted already
            if(os.path.exists(dirToRm)):
                os.system("rm -rf "+dirToRm)
                #remove 1 file at a time
                return
            # remove deleted directory from the list
            rmDirs.pop(0)
    except Exception as e:
        dbg.prn(dbg.ERR|dbg.ECN,"[---]deleteFiles", e, sys.exc_traceback.tb_lineno)
#end deleteFiles

# deleting old events
def removeOldEvents():
    """ Goes through events that were marked as deleted and adds them to the list of paths to be removed by deleteFiles() """
    dbg.prn(dbg.ECN,"removeOldEvents called")
    if(len(rmDirs)>0 or not (enc.code & (enc.STAT_READY | enc.STAT_NOCAM))):
        #either already deleting some events or encoder is being shut down
        return
    try:
        # delete any undeleted directories
        # get a list of deleted events
        oldevents = pxp._listEvents(onlyDeleted = True)
        dbg.prn(dbg.ECN,"old events:",oldevents)
        if (len(oldevents)>0):
            for event in oldevents:
                if(not 'datapath' in event):
                    continue
                # make sure directory path is not corrupted
                if(event['datapath'].find("/")>=0 or len(event['datapath'])<3):
                    continue
                # check if it exists
                if(os.path.exists(c.wwwroot+event['datapath'])):
                    #add to the list of directories to be removed
                    rmDirs.append(c.wwwroot+event['datapath'])
                    break #delete only 1 folder at a time
            #for event in oldevents
        #if oldevents>0
    except:
        pass
#end removeOldEvents
######################
## end delete files ##
######################
def oldLiveCleanup():
    """ In some cases (loss of power, abrupt disconnect, or a fatal crash) a live folder may still exist even if there is no live event. This function will perform some post-live cleanup to ensure everything is ready for a new live event. """
    try:
        if(os.path.exists(c.wwwroot+'live')): #there was a live event that didn't stop properly, maybe due to a powerloss
            pxp.encstop() #stop that event and rename the folder according to the event standards
            # TODO: perhaps do some error checking here - if the powerloss occurred, might have to repair the MP4 file: 
            # 0 check if the mp4 file is corrupt (one ffmpeg call can tell you that)
            # 1 delete the original mp4, 
            # 2 assemble all the .ts segments into one big .TS file 
            # 3 convert it to a new mp4
    except Exception as e:
        dbg.prn(dbg.ECN|dbg.ERR,"[---]oldLiveCleanup:",e,sys.exc_traceback.tb_lineno)
##################################
### pxpservice control classes ###
##################################

class commander:
    """ Server command manager """
    q = [] #queue of the commands to be executed
    status = 0 # 0 - ready, 1 - busy
    def __init__(self):
        #start command manager
        try:
            # add to the tmr[] dictionary so that when the script is stopping, it can be done faster
            if(not 'commander' in tmr):
                tmr['commander']=[]
            tmr['commander'].append(TimedThread(self._mgr,period=0.3))
        except Exception as e:
            dbg.prn(dbg.CMD|dbg.ERR,"[---]commander init fail??????? ", e)
    def enq(self, cmd, sync=True, bypass=False):
        """ adds a command to the queue 
            Args:
                cmd(str) - command to add. command is vertical bar-delimeted with parameters
                sync(bool,optional) - whether the command is synchronous or not. ASYNC commands will have to reset commander status manually. default: True
                bypass(bool,optional) - when True, the command will be executed immediately bypassing the queue. default: False
        """
        statAfter = 0 if sync else 1
        if(bypass):#execute command right away, bypassing the queue
            # calling exc directly will not affect the commander status,
            # enqueued commands will keep executing in proper order
            # |0 added at the end to keep number of parameters consistent with other functions
            self._exc(cmd+'|0') 
        else:
            self.q.append(cmd+'|'+str(statAfter))
    #end enq
    def _deq(self):
        """ Removes the next command form the queue and executes it """
        if(len(self.q)>0):
            self.status = 1 #set status to busy (to make sure only 1 command is executing at a time)
            cmd = self.q[0] #get the command
            del self.q[0] #remove it from the queue
            # do whatever it's supposed to do:
            self._exc(cmd=cmd)
            # last bit of the command is the autoset status
            self.status = int(cmd.split('|')[-1]) #set the status to 0 (ready) if it's a synchronous command
    #end deq
    def _exc(self,cmd):
        """ Executes a given command """
        try:
            dbg.prn(dbg.CMD,"executing: ", cmd)
            dataParts = cmd.split('|')
            if(dataParts[0]=='STR'): #start encode
                srcMgr.encCapStart()
            if(dataParts[0]=='STP'): #stop encode
                srcMgr.encCapStop()
            if(dataParts[0]=='PSE'): #pause encode
                srcMgr.encCapPause()
            if(dataParts[0]=='RSM'): #resume encode
                srcMgr.encCapResume()
            if(dataParts[0]=='RMF' and len(dataParts)>2): #remove file
                rmFiles.append(dataParts[1])
            if(dataParts[0]=='RMD' and len(dataParts)>2): #remove directory
                rmDirs.append(dataParts[1])
            if(dataParts[0]=='BTR' and len(dataParts)>3): #change bitrate
                # data is in format BTR|<bitrate>|<camID>
                srcMgr.setBitrate(dataParts[1],dataParts[2])
            if(dataParts[0]=='BKP'): #manual backup event
                backuper.add(hid=dataParts[1],priority=5)
            if(dataParts[0]=='RRE'): #restore event 
                backuper.add(hid=dataParts[1],priority=10,restore=True) #restoring events have higher priority over backups (to prevent restore-backup of the same event)
            if(dataParts[0]=='LVL'): # set log level
                dbg.setLogLevel(dataParts[1])
            if(dataParts[0]=='LOG'): # set logging to file on/off
                dbg.setLog(dataParts[1])
        except Exception as e:
            dbg.prn(dbg.CMD|dbg.ERR,"[---]cmd._exc", e, sys.exc_traceback.tb_lineno)
            return False
    #end exc
    def _mgr(self):
        """ Status manager - periodically checks if the commander status is ready, runs .deq when it is """
        if(self.status):
            return
        # commander is not busy
        self._deq()
    #end mgr
#end commander

class encoderStatus:
    """ Encoder status management class
    """
    code = 0 #encoder status code
    status = 'unknown'
    lastWritten = 0  #last status code that was written to file (to make sure we don't write same thing over and over)
    #pre-defined status codes
    STAT_UNKNOWN        = 0
    STAT_INIT           = 1<<0 #encoder is initializing (pxpservice just started)
    STAT_CAM_LOADING    = 1<<1 #the camera is initializing (searching for teradek cube's or matrox monarch's)
    STAT_READY          = 1<<2 #encoder is ready to start an event
    STAT_LIVE           = 1<<3 #there is a live event
    STAT_SHUTDOWN       = 1<<4 #encoder is shutting down
    STAT_PAUSED         = 1<<5 #the live event is paused
    STAT_STOP           = 1<<6 #live event is stopping
    STAT_START          = 1<<7 #live event starting
    STAT_NOCAM          = 1<<8 #no camera found

    def __init__(self):
        import inspect
        self.statusSet(self.STAT_INIT)
    def busy(self):
        """ returns true when encoder is busy (i.e. live, starting a live event or still stopping a live event) """
        return self.code & (self.STAT_LIVE | self.STAT_START | self.STAT_STOP | self.STAT_PAUSED)
    def statusSet(self,statusBit,autoWrite=True, overwrite=True):
        """Set a new encoder status code and appropriate status text 
            Args:
                statusBit(int): new status of the encoder to set (add or overwrite)
                autoWrite(bool,optional): write the status to disk right away. default: True
                overwrite(bool,optional): overwrite the current status with the new one, if False, status will be added (bitwise OR). default: True
            Returns:
                none
        """
        try:
            import inspect
            dbgLastStatus = self.code
            if(overwrite):
                self.code = statusBit
            else:
                self.code = self.code | statusBit
            self.status = self.statusTxt(self.code)
            if(dbgLastStatus!=self.code): #only output if status changed
                dbg.prn(dbg.ENC,"status: ",self.status,' ',bin(self.code))
            if(autoWrite):
                self.statusWrite()
        except Exception as e:
            dbg.prn(dbg.ERR|dbg.ENC,"[---]enc.statusSet",e, sys.exc_traceback.tb_lineno)
    #end status
    def statusTxt(self, statusCode):
        """ Get the text corresponding to the status code 
            Args:
                statusCode(int): status code to convert to text
            Returns:
                (str): text status
        """
        if(statusCode & self.STAT_SHUTDOWN):
            return 'shutting down'
        if(statusCode & self.STAT_INIT):
            return 'initializing'
        if(statusCode & self.STAT_CAM_LOADING):
            return 'loading camera'
        if(statusCode & self.STAT_NOCAM):
            return 'no camera'
        if(statusCode & self.STAT_PAUSED):
            return 'paused'
        if(statusCode & self.STAT_STOP):
            return 'stopping'
        if(statusCode & self.STAT_START):
            return 'starting'
        if(statusCode & self.STAT_READY):
            return 'ready'
        if(statusCode & self.STAT_LIVE):
            return 'live'
        return 'unknown'
    #end statusTxt

    def statusUnset(self,statusBit, autoWrite = True):
        """Resets the status bit 
            Args:
                statusBit(int): which bit to unset (set to 0)
                autoWrite(bool, optional): write the status to disk right away. default:True
            Returns:
                none
        """
        try:
            self.code = self.code & ~statusBit
            self.status = self.statusTxt(self.code)
            dbg.prn(dbg.ENC,"status: ",self.status,bin(self.code))
            if(autoWrite):
                self.statusWrite()
        except Exception as e:
            dbg.prn(dbg.ERR|dbg.ENC,"[---]enc.statusUnset",e, sys.exc_traceback.tb_lineno)
    #end statusUnset
    def statusWrite(self):
        """ Write current status to disk in json format. """
        # this function is executed automatically (initialized at the bottom of this file), simply records current pxp status in a file
        # the text status is saved simply as 'status' and the numeric status code is saved as 'statuscode'
        # replace() is to make sure that if status has \ or ', it won't break the command and give invalid status
        # os.system("echo '"+json.dumps({"status":self.status.replace("\"","\\\""), "code":self.code})+"' > "+c.encStatFile)
        if(self.lastWritten==self.code):
            return #this status was already written - do nothing
        try:
            with open(c.encStatFile,"wb") as f:
                f.write(json.dumps({"status":self.status.replace("\"","\\\""), "code":self.code}))
            self.lastWritten = self.code
        except:
            pass
    #end statusWrite
#end encoderStatus class

##############################
### encoder device classes ###
##############################

class encDevice(object):
    """ Template class for an encoder device. """
    def __init__(self, ip):
        """ initialize the class 
            Args:
                ip(str): ip address of the device. used to set/retreive its parameters
        """
        self.bitrate        = "n/a"
        self.ccBitrate      = False # can change bitrate
        self.ccFramerate    = False # can change framerate
        self.ccResolution   = False # can change resolution
        self.framerate      = "n/a"
        self.resolution     = "n/a"
        self.ip             = ip
        self.isCamera       = False # the camera is attached
        self.isOn           = False # RTSP stream is accessible
        self.liveStart      = 0     # time of last live555 start attempt
        self.initialized    = False # will be set to true when all parameters of the device are retrieved
        self.initStarted    = int(time.time()*1000) # for timing out the initialization procedure if it stalls for too long
        self.rtspURL        = False # url of the RTP/RTSP stream on the encoder device
        self.isIP           = True  # this is an ip-streaming device (by default). only a few select devices will be set as non-ip (has to be forced manually)
        self.alarm          = False # whther this device has alarm triggered (or a list of which alarms are triggered if there is more than 1)
        self.almCooldown    = 0     # time.time() in seconds when alarm will be re-armed: after an alarm is triggered, there is a period (_almCoolTime) during which it cannot be triggered again
        self._almCoolTime   = 10    # constant - maximum alarm cooldown period in seconds
    def __repr__(self):
        return "<encDevice> ip:{ip} fr:{framerate} br:{bitrate} url:{rtspURL} init:{initialized} on:{isOn}".format(**self.__dict__)
    def alarmChk(self):
        """ to implement in device-specific class """
        pass
    def buildCapCmd(self, camURL, chkPRT, camMP4, camHLS):
        """ Create ffmpeg command that will capture the rtsp stream and redirect it accordingly. Can override in device-specific class
            Args:
                camURL(str): URL to the rtsp stream of the camera
                chkPRT(int): port used for monitoring the video - H.264 packets are sent here
                camMP4(int): ffmpeg that records mp4 file is listening on this port
                camHLS(int): mediastreamsegmenter listens on this port (ffmpeg will forward MPEG-TS packets here)
            Returns:
                (str): the full command
        """
        # if ther's a problem, try adding -rtsp_transport udp before -i
        # liquid image EGO camerea requires -fflags +genpts (to generate its own pts) otherwise you get "first pts value must be set" error
        # return c.ffbin+" -fflags +genpts -rtsp_transport tcp -i "+camURL+" -codec copy -f h264 udp://127.0.0.1:"+chkPRT+" -codec copy -f h264 udp://127.0.0.1:"+camMP4+" -codec copy -f mpegts udp://127.0.0.1:"+camHLS
        return c.ffbin+" -fflags +igndts -rtsp_transport udp -i "+camURL+" -fflags +igndts -codec copy -f h264 udp://127.0.0.1:"+str(chkPRT)+" -fflags +igndts -codec copy -f mpegts udp://127.0.0.1:"+str(camMP4)+" -fflags +igndts -codec copy -f mpegts udp://127.0.0.1:"+str(camHLS)
    #end encBuildCmd
    def discover(self):
        """ To implement in device-specific class """
        pass
    def setBitrate(self, bitrate):
        """ To implement in device-specific class """
        pass
    def setResolution(self, resolution):
        """ To implement in device-specific class """
        pass
    def setFramerate(self, framerate):
        """ To implement in device-specific class """
        pass
    def monitor(self):
        """ To implement in device-specific class """
        pass
    def update(self):
        """ To implement in device-specific class """
        pass
#end encDevice class

class encTeradek(encDevice):
    """ Teradek device management class """
    def __init__(self, ip=False):
        if(ip):
            super(encTeradek,self).__init__(ip)
            self.ccBitrate      = True # can change bitrate
            self.ccFramerate    = True # can change framerate
            self.ccResolution   = True # can change resolution
            self.tdSession      = None # reference to the login session on the teradek
    def discover(self, callback):
        """ Find any new devices using bonjour protocol. 
            Args:
                callback(function): called when a device is found 
            Returns:
                none
        """
        def discovered(results):
            recs = pu.bonjour.parseRecord(results['txtRecord'])
            output = {}
            # url to the stream, consists of:
            # 'sm' - streaming method/protocol (e.g. rtsp)
            # ipAddr - ip address of the encoder (e.g. 192.168.1.100)
            # strport - port of the stream (e.g. 554)
            # 'sn' - stream name (e.g. stream1)
            if(recs['sm']=='TDS'): #teradek direct streaming - proprietary protocol, ignore it
                return
            if(not 'sn' in recs): #this happens for Teradek Clip
                recs['sn']='stream1'
            streamURL = recs['sm'].lower()+'://'+results['ip']+":"+str(results['port'])+'/'+recs['sn']
            # check if this is a preview or a full rez stream
            if(recs['sn'].lower().find('quickview')>=0):# this is a preview stream
                output['preview']=streamURL
                output['preview-port']=results['port']
            else:
                output['url']=streamURL
                output['port'] = results['port']
            output['ip'] = results['ip']
            output['type'] = "td_cube"
            output['devClass'] = encTeradek
            callback(output)
        #end discovered
        pu.bonjour.discover(regtype="_tdstream._tcp",callback=discovered)
    #end discover
    def getParam(self, response,parameter):
        """ Extracts a specified paramater from the response string and gets its value.
            Args:
                response(str): text response from a request
                    function assumes response in this format:
                    VideoInput.Info.1.resolution = 720p60
                    VideoEncoder.Settings.1.framerate = 30
                parameter(str): property name to extract (e.g. 'resolution')
            Returns:
                (str): value of the property

        """
        try:
            lines = response.split("\n")
            if(len(lines)<1 or not(isinstance(lines,list))):
                return False #wrong response type
            for line in lines:
                parts = line.split("=")
                # make sure the line is in the format: SETTING = VALUE
                if(len(parts)<2 or not(isinstance(parts,list))):
                    continue
                # this line appears to have the right format
                # make sure the setting name is in the right format
                nameparts = parts[0].split('.')
                if(len(nameparts)<2 or not(isinstance(nameparts,list))):
                    continue
                # correct name format, check if this is the parameter we're looking for
                if(nameparts[-1].strip().lower()==parameter.lower().strip()):
                    # found the right parameter, return its value
                    return parts[1].strip() #make sure there is no empty space around the result
            #end for line in lines
            return False #if could not find the right parameter or its value is missing, return false
        except:
            return False
    #end tdGetParam
    def login(self):
        """ Login to the TD device and save session 
            Args:
                none
            Returns:
                (bool): whether the command was succssful
        """
        url = "http://"+self.ip+"/cgi-bin/api.cgi"
        #attempt to login
        response = pu.io.url(url+"?command=login&user=admin&passwd=admin",timeout=15)
        # get session id
        if(not response):
            return False
        response = response.strip().split('=')
        if(response[0].strip().lower()=='session' and len(response)>1):#login successful
            self.tdSession = response[1].strip() #extract the id
            return True
        # else:#could not log in - probably someone changed username/password
        return False

    #end login
    def setBitrate(self, bitrate):
        """ Set teradek bitrate is in kbps 
            Args:
                bitrate(int): new bitrate in kbps
            Returns:
                none
        """
        try:
            dbg.prn(dbg.TDK,"tdSetBitrate")
            url = "http://"+self.ip+"/cgi-bin/api.cgi"
            if(not self.tdSession):
                self.login()
            #end if not tdSession
            dbg.prn(dbg.TDK,"logged in: ", self.tdSession)
            url +="?session="+self.tdSession
            # bitrate for teradek should be in bps not in kbps:
            bitrate = bitrate * 1000
            dbg.prn(dbg.TDK,"NEW BITRATE:.....................................", bitrate)
            setcmd = "&VideoEncoder.Settings.1.bitrate="+str(bitrate)
            savecmd = "&q=VideoEncoder.Settings.1.bitrate"

            dbg.prn(dbg.TDK,"setting...")
            answer = False
            while(not answer):
                answer = pu.io.url(url+"&command=set"+setcmd,timeout=10)
            dbg.prn(dbg.TDK,answer)
            # apply settings
            dbg.prn(dbg.TDK,"applying...")
            answer = False
            while(not answer):
                answer = pu.io.url(url+"&command=apply"+savecmd,timeout=10)
                dbg.prn(dbg.TDK,answer)
            dbg.prn(dbg.TDK,answer)
            # save the settings
            dbg.prn(dbg.TDK,"saving...")
            answer = False
            while(not answer):
                answer = pu.io.url(url+"&command=save"+savecmd,timeout=10)
            dbg.prn(dbg.TDK,answer)
        except Exception as e:
            dbg.prn(dbg.TDK|dbg.ERR,"[---]encTeradek.setBitrate:", e, sys.exc_traceback.tb_lineno)
    #end setBitrate
    def setFramerate(self, framerate):
        """ Set teradek frame rate is in fps
            Args:
                framerate(int): new frame rate in fps
            Returns:
                (bool): whether the command was successful
        """
        try:
            url = "http://"+self.ip+"/cgi-bin/api.cgi"
            if(not self.tdSession):
                self.login()
            #end if not tdSession
            dbg.prn(dbg.TDK, "logged in: ", self.tdSession)
            #######################################
            # try to get existing framerate first #
            #######################################
            # get all settings
            url +="?session="+self.tdSession
            newrate = False
            for rate in self.allrates:    #allrates are in descending order
                if(int(rate)<=framerate): #found the first framerate that will work without problems
                    newrate = rate
                    break
            if(not newrate):
                return False
            dbg.prn(dbg.TDK, "NEW RATE:.....................................", newrate)
            setcmd = "&VideoEncoder.Settings.1.framerate="+str(newrate)
            savecmd = "&q=VideoEncoder.Settings.1.framerate"
            if(self.nativerate):#currently native frame rate is set - need to reset it manually
                setcmd +="&VideoEncoder.Settings.1.use_native_framerate=0"
                savecmd = "&q=VideoEncoder.Settings.1.use_native_framerate"
            # set the frame rate
            dbg.prn(dbg.TDK, "setting...")
            answer = False
            attempts = 0
            while((not answer) and attempts<3):
                answer = pu.io.url(url+"&command=set"+setcmd,timeout=10)
                attempts +=1
            if(not answer):
                return False
            dbg.prn(dbg.TDK, answer)
            # apply settings
            dbg.prn(dbg.TDK, "applying...")
            answer = False
            attempts = 0
            while((not answer) and attempts<3):
                answer = pu.io.url(url+"&command=apply"+savecmd,timeout=10)
                attempts +=1
            if(not answer):
                return False
            dbg.prn(dbg.TDK, answer)
            # save the settings
            dbg.prn(dbg.TDK, "saving...")
            answer = False
            attempts = 0
            while((not answer) and attempts<3):
                answer = pu.io.url(url+"&command=save"+savecmd,timeout=10)
                attempts +=1
            if(not answer):
                return False
            dbg.prn(dbg.TDK, answer)
            return True
        except Exception as e:
            dbg.prn(dbg.TDK|dbg.ERR, "[---]encTeradek.setFramerate:", e, sys.exc_traceback.tb_lineno)
        return False
    #end setFramerate
    def update(self):
        """ Requests encoding parameters of the teradek cube and updates local class properties"""
        try:
            if(enc.code & enc.STAT_SHUTDOWN): #exit immediately if there's a shutdown going on
                return
            if(not self.tdSession):#did not login before, try to login
                self.login()
            if(not self.tdSession):#could not log in to the device - most likely it's gone from the network, set its status to off
                self.isOn = False
                return False
            #end if dev not in tdSession
            url = "http://"+self.ip+"/cgi-bin/api.cgi?session="+self.tdSession
            url2= "&command=get&q=VideoInput.Info.1.resolution&q=VideoEncoder.Settings.1.framerate&q=VideoEncoder.Settings.1.bitrate&q=VideoEncoder.Settings.1.use_native_framerate&q=VideoInput.Capabilities.1.framerates"
            response = pu.io.url(url+url2, timeout=15)
            if(not response): #didn't get a response - timeout?
                dbg.prn(dbg.TDK, "no response from: ",url+url2)
                self.tdSession = None #this will cause if(self.tdSession) to fail on the next run of update(), which will cause RTSP to be restarted, and if it can't, the device will be removed from the system
                return False
            self.resolution = self.getParam(response,'resolution')
            self.framerate = int(self.getParam(response,'framerate'))
            bitrate = self.getParam(response,'bitrate') #this is in bps
            self.nativerate = self.getParam(response,'use_native_framerate')
            self.allrates  = self.getParam(response,'framerates').split(',')
            self.isCamera = self.resolution and not (self.resolution.strip().lower()=='vidloss' or self.resolution.strip().lower()=='unknown')
            if(not self.isCamera):
                self.resolution = 'n/a'
            if(bitrate):#convert bitrate to kbps
                try:
                    intBitrate = int(bitrate)
                    intBitrate = int(intBitrate / 1000)
                except:
                    intBitrate = 0
            # set bitrate for the settings page
            self.bitrate = intBitrate
        except Exception as e:
            dbg.prn(dbg.TDK|dbg.ERR, "[---]td.update:",e,sys.exc_traceback.tb_lineno)
    #end update
#end encTeradek class

class encMatrox(encDevice):
    """ Matrox device management class """
    def __init__(self, ip=False):
        if(ip):
            super(encMatrox,self).__init__(ip)
    def discover(self, callback):
        """ Find any new devices using SSDP. 
            Args:
                callback(function): called when a device is found 
            Returns:
                none
        """
        try:
            if(enc.code & enc.STAT_SHUTDOWN):
                return
            #to find ALL ssdp devices simply enter ssdp:all as the target
            monarchs  = pu.ssdp.discover(text="monarch",case=False,field='st')
            if(len(monarchs)>0):
                dbg.prn(dbg.MTX, "found:",monarchs)
                # found at least one monarch 
                for devLoc in monarchs:
                    try:
                        dev = monarchs[devLoc]
                        devIP, devPT = self.parseURI(dev.location)
                        if(not devIP): #did not get ip address of the device
                            continue
                        params = self.getParams(devIP) #get all the parameters from the monarch's page
                        if(params and params['rtsp_url'] and params['rtsp_port']):
                            output = {}
                            output['ip'] = devIP
                            output['type'] = 'mt_monarch'
                            output['url'] = params['rtsp_url']
                            output['port'] = params['rtsp_port']
                            output['devClass'] = encMatrox
                            callback(output)
                    except Exception as e: #may fail if the device is invalid or doesn't have required attributes
                        dbg.prn(dbg.MTX|dbg.ERR, "[---]encMatrox.discover",e, sys.exc_traceback.tb_lineno)
                #end for devLoc in monarchs
            #end if monarchs>0
            else:
                # dbg.prn(dbg.MTX,"not found any monarchs")
                pass
        except Exception as e:
            dbg.prn(dbg.MTX|dbg.ERR,"[---]encMatrox.discover",e, sys.exc_traceback.tb_lineno)
    def getParams(self,ip=False):
        """ Gets parameters from a matrox monarch device (using the status page for now, until they release the API)
        """
        params = {
            "rtsp_url"          : False,
            "rtsp_port"         : False,
            "inputResolution"   : False,
            "streamResolution"  : False,
            "streamFramerate"   : False,
            "streamBitrate"     : False,
            "connection"        : False #whether there is connection with this device at all
        }
        if(not ip):
            ip = self.ip
        try:
            ####################
            #  new API is here #
            ####################
            # make sure the device has RTSP enabled
            # this should be admin:admin@192.168..... but seems like that's not necessary, plus python doesn't like those URLs
            status = pu.io.url('http://'+ip+'/Monarch/syncconnect/sdk.aspx?command=GetStatus',timeout=10)
            dbg.prn(dbg.MTX,"GetStatus:",status)
            if(status):
                status = status.lower()
                # extract RECORD status
                statRec = status[status.find('record')+7:status.find('stream')-1]
                # extract STREAM status
                statStr = status[status.find('stream')+7:status.find('name')-1]
                # get stream parameters
                # 1st is streaming mode (RTMP or RTSP or DISABLED), 
                # 2nd is streaming status (ON, READY or DISABLED)
                streamParams = statStr.split(',') 
                isRTSP = streamParams[0]=='rtsp'
                if(not isRTSP): #if it's not rtsp mode, stop any streaming and/or recording that's going on and set device to RTSP mode
                    pu.io.url('http://'+ip+'/Monarch/syncconnect/sdk.aspx?command=StopStreamingAndRecording',timeout=10) #if in streaming & recording mode
                    time.sleep(1)
                    pu.io.url('http://'+ip+'/Monarch/syncconnect/sdk.aspx?command=StopStreaming',timeout=10) #if in streaming mode only (RTMP)
                    time.sleep(1)
                    pu.io.url('http://'+ip+'/Monarch/syncconnect/sdk.aspx?command=StopRecording',timeout=10) #if in recording mode only
                    time.sleep(1)
                    pu.io.url('http://'+ip+'/Monarch/syncconnect/sdk.aspx?command=SetRTSP,Stream1,8554',timeout=10) 
                    time.sleep(1)
            # get RTSP parameters
            status = pu.io.url('http://'+ip+'/Monarch/syncconnect/sdk.aspx?command=GetRTSP',timeout=10)
            dbg.prn(dbg.MTX,"GetRTSP:",status)
            if(status and status !='FAILED'):
                rtspParams = status.split(',')
                if(len(rtspParams)>2):
                    params['rtsp_url']=rtspParams[0]
                    params['rtsp_port']=rtspParams[2]
            # get bitrate
            status = pu.io.url('http://'+ip+'/Monarch/syncconnect/sdk.aspx?command=GetStreamingVideoDataRate',timeout=10)
            dbg.prn(dbg.MTX,"GetStreamingVideoDataRate:",status)
            if(status):
                rtspParams = status.split(':')
                if(len(rtspParams)>1):
                    params['streamBitrate']=rtspParams[1]
            #####################
            #  old code is here #
            #####################
            # # for now the only way to extract this information is using the monarch home page (no login required for this one)
            # # when they provide API, then we can use that
            mtPage = pu.io.url("http://"+ip+"/Monarch", timeout=10)
            if(not mtPage):
                return False #could not connect to the monarch page
            # ########### get rtsp url ###########
            # resPos = mtPage.find("ctl00_MainContent_RTSPStreamLabelC2") #this is the id of the label containing video input
            # if(resPos>0):#found the video input label, find where the actual text is
            #     posStart = mtPage.find('>',resPos)+1
            # else:
            #     posStart = -1
            # # find end position
            # if(posStart>0):
            #     posStop = mtPage.find('<',posStart)
            # else:
            #     posStop = -1
            # #now we should have the start and end position for the resolution        
            # if((posStart>0) and (posStop>0) and (posStop>posStart)):
            #     rtspURL = mtPage[posStart:posStop] #either this is blank or it has the url
            #     if(len(rtspURL)>10 and rtspURL.startswith("rtsp://")):
            #         # got the url
            #         params['rtsp_url']=rtspURL
            #         # extract the port
            #         ip, port = self.parseURI(rtspURL)
            #         params['rtsp_port']=port
            # #end if posStart>0
            # ########### end rtsp url ###########
            # ########### get video input ###########
            resPos = mtPage.find("ctl00_MainContent_VideoInputLabel") #this is the id of the label containing video input
            if(resPos>0):#found the video input label, find where the actual text is
                posStart = mtPage.find('>',resPos)+1
            else:
                posStart = -1
            # find end position
            if(posStart>0):        
                posStop = mtPage.find('<',posStart)
            else:
                posStop = -1
            #now we should have the start and end position for the resolution        
            if((posStart>0) and (posStop>0) and (posStop>posStart)):
                inRes = mtPage[posStart:posStop] #either contains "No Video Input" or something to the effect of "1920x1080p, 60 fps"
                if((inRes.find(",")>0) and (inRes.find("fps")>0)): # video source present
                    # get resolution
                    resParts = inRes.lower().strip().split(',')
                    # now first part contains the resolution (e.g. 1280x720p)
                    resolution = resParts[0].strip().split('x')
                    if(len(resolution)>1):
                        resolution = resolution[1].strip() # now contains "720p"
                    else:
                        resolution = False
                    # get framerate
                    framerate = resParts[1].strip().split('fps')
                    if(len(framerate)>1):
                        framerate = framerate[0].strip()
                    else:
                        framerate = False
                    if(resolution and framerate):
                        params['inputResolution'] = resolution+framerate # e.g. 1080i60
                #end if inRes contains ',' and 'fps'
            #end if posStart>0
            ########### end get video input ###########
            # ########### get stream settings ###########
            # pos = mtPage.find("ctl00_MainContent_StreamSettingsLabel")
            # if(pos>0):
            #     posStart = mtPage.find('>',pos)+1
            # else:
            #     posStart = -1
            # if(posStart>0):        
            #     posStop = mtPage.find('<',posStart)
            # else:
            #     posStop = -1
            # if(posStart>0 and posStop>0 and posStop>posStart):
            #     streamText = mtPage[posStart:posStop] #e.g. 1280x720p, 30 fps, 2000 kb/s; 192 kb/s audio; RTSP
            #     if((streamText.find(',')>0) and (streamText.find('fps')>0) and (len(streamText.split(','))>2)): #stream information contains at least resolution and frame rate
            #         parts = streamText.split(',')
            #         # resolution is in the first part of the text
            #         resolution = parts[0].strip().split('x')
            #         if(len(resolution)>1):
            #             resolution = resolution[1].strip() #now contains "720p"
            #         else:
            #             resolution = False
            #         # get framerate - in the second part
            #         framerate = parts[1].strip().split('fps')
            #         if(len(framerate)>1):
            #             framerate = framerate[0].strip() #contains "30"
            #         else:
            #             framerate = False
            #         # get bitrate            
            #         bitrate = parts[2].strip().split("kb") #it will contain kbps or kb/s
            #         if(len(bitrate)>1):
            #             bitrate = bitrate[0].strip()
            #         else:
            #             bitrate = False
            #         params["streamResolution"] = resolution;
            #         params["streamFramerate"]  = framerate;
            #         params["streamBitrate"]    = bitrate;
            # #end if posStart>0
            # ########### end stream settings ###########
            params["connection"] = True 
        except Exception, e:
            dbg.prn(dbg.MTX|dbg.ERR,"[---]matrox.getParams",e,sys.exc_traceback.tb_lineno)
        dbg.prn(dbg.MTX,params)
        return params
    def parseURI(self,url):
        """ Extracts ip address and port from a uri.
        the url is usually in this format: "http://X.X.X.X:PORT/"
        e.g. from http://192.168.1.103:5953/
        will return 192.168.1.103 and 5953
        """
        addr  = ""
        parts = []
        ip    = False
        parts = url.split('/')
        #extract ip address with port
        if(len(parts)>2):
            addr = parts[2] #this contains X.X.X.X:PORT
        else:
            addr = parts[0] #it is possible the mtURL is "X.X.X.X:PORT/" (no http), then parts[0] will still be X.X.X.X:PORT
        # extract the ip address 
        addr = addr.split(':')
        if(len(addr)>1):
            ip = addr[0]
            port = addr[1]
        else:
            ip = False
            port = False
        return ip, port
    def update(self):
        """ Get new device parameters, or set them as false if request fails
            Args:
                none
            Returns:
                none
        """

        params = self.getParams()
        dbg.prn(dbg.MTX, params, "mt.update")
        if(params and params['connection']):
            self.resolution = params['inputResolution']
            self.isCamera = self.resolution!=False
            self.bitrate = params['streamBitrate']
            self.framerate = params['streamFramerate']
            self.rtspURL = params['rtsp_url']
        else:
            self.isOn = False
            self.isCamera = False
            self.resolution = False
            self.bitrate = False
            self.framerate = False
            self.rtspURL = False
            self.initialized = False
#end encMatrox

class encPivothead(encDevice):
    """ Pivothead glasses encoder management class """
    def __init__(self, ip=False):
        if(ip):
            super(encPivothead,self).__init__(ip)
    def discover(self, callback):
        """ Find any new devices using bonjour protocol. 
            Args:
                callback(function): called when a device is found 
            Returns:
                none
        """
        def discovered(results):
            recs = pu.bonjour.parseRecord(results['txtRecord'])
            output = {}
            # url to the stream, consists of:
            # recs['sm'] - streaming method/protocol (e.g. rtsp)
            # ipAddr - ip address of the encoder (e.g. 192.168.1.100)
            # strport - port of the stream (e.g. 554)
            # recs['sn'] - stream name (e.g. stream1)
            streamURL = recs['sm'].lower()+'://'+results['ip']+":"+str(results['port'])+'/'+recs['sn']
            output['url']=streamURL
            output['port'] = results['port']
            output['ip'] = results['ip']
            output['type'] = "ph_glass"
            output['devClass'] = encPivothead
            callback(output)
        #end discovered
        pu.bonjour.discover(regtype="_pxpglass._udp",callback=discovered)
    def update(self):
        """ Ping the device (to ensure it's still on the network)
            Args:
                none
            Returns:
                none
        """
        self.isOn = pu.io.ping(self.ip)
        self.isCamera = self.isOn #when the device is found, assume glasses are present - need to make a more robust verification (change pxpinit.py on the glasses pi)
#end encPivothead

class encSonySNC(encDevice):
    """ Sony SNC device management class """
    def __init__(self, ip=False):
        if(ip):
            super(encSonySNC,self).__init__(ip)
            self.ccBitrate      = True # can change bitrate
    def alarmChk(self):
        """ Determine if this camera has alarm triggered """
        try:
            if(time.time()<self.almCooldown):
                dbg.prn(dbg.SNC,"alarm cooling down",(self.almCooldown-time.time()),"s left")
                return
            # ensure it's in CBR mode and set the bitrate
            response = pu.io.url("http://"+self.ip+"/command/inquiry.cgi?inq=sensor",username='admin',password='admin')
            dbg.prn(dbg.SNC,"snc.alarm:",response)
            if(not response):
                self.alarm = False
                return
            # parse response in the URL format: name0=value&name1=value&name2=value
            params = dict(parse_qsl(response))
            self.alarm = ('PresenceSensorStatus' in params) and (int(params['PresenceSensorStatus']))
            if(self.alarm):
                self.almCooldown = time.time()+self._almCoolTime #set cooldown period for the alarm to make sure it doesn't triggered repeatedly in a short period
                dbg.prn(dbg.SNC,"!!!!!!!!!!!!!!!!!!!ALARM!!!!!!!!!!!!!!!!!!!!!!!!",self.ip, "time:",time.time(),"stop:",self.almCooldown)
                # if(enc.busy()):#encoding a live event - trigger a tag in a separate thread to ensure this function doesn't freeze
                    # tmr['misc'].append(TimedThread(pxp.taglive,params=("alarm","alarm")))
            else:
                dbg.prn(dbg.SNC,"****************no alarm*******************",self.ip)
        except Exception as e:
            self.alarm = False
            dbg.prn(dbg.ERR|dbg.SNC,"[---]snc.alarmChk:", e, sys.exc_traceback.tb_lineno, "( resp : ",response,')')
        
    def discover(self, callback):
        """ Find any new devices using bonjour protocol. 
            Args:
                callback(function): called when a device is found 
            Returns:
                none
        """
        try:
            if(enc.code & enc.STAT_SHUTDOWN):
                return
            #to find ALL ssdp devices simply enter ssdp:all as the target
            devs  = pu.ssdp.discover(text="SNC",field='server',case=True)
            if(len(devs)>0):
                dbg.prn(dbg.SNC, "found:",devs)
                # found at least one monarch 
                for devLoc in devs:
                    try:
                        dev = devs[devLoc]
                        devIP, devPT = self.parseURI(dev.location)
                        if(not devIP): #did not get ip address of the device
                            continue
                        params = self.getParams(devIP) #get all the parameters from the monarch's page
                        if(params and params['rtsp_url'] and params['rtsp_port']):
                            output = {}
                            output['ip'] = devIP
                            output['type'] = 'sn_snc'
                            output['url'] = params['rtsp_url']
                            output['port'] = params['rtsp_port']
                            output['devClass'] = encSonySNC
                            callback(output)
                    except Exception as e: #may fail if the device is invalid or doesn't have required attributes
                        dbg.prn(dbg.SNC|dbg.ERR, "[---]encSonySNC.discover",e, sys.exc_traceback.tb_lineno)
                #end for devLoc in devs
            #end if devs>0
            else:
                # dbg.prn(dbg.SNC,"not found any SNCs")
                pass
        except Exception as e:
            dbg.prn(dbg.SNC|dbg.ERR,"[---]encSonySNC.discover",e, sys.exc_traceback.tb_lineno)
    def getParams(self,ip=False):
        """ Gets new parameters from a SNC device
            Args:
                ip(str): ip address of the device (if using on a class without instantiating)
            Returns:
                (dictionary): any parameters that were acquired
        """
        params = {
            "rtsp_url"          : False,
            "rtsp_port"         : False,
            "inputResolution"   : False,
            "streamResolution"  : False,
            "streamFramerate"   : False,
            "streamBitrate"     : False,
            "connection"        : False #whether there is connection with this device at all
        }

        if(not ip):
            ip = self.ip
        try:
            params['rtsp_url']='rtsp://'+ip+'/media/video1'
            status = pu.io.url('http://'+ip+'/command/inquiry.cgi?inq=camera',timeout=10)
            # cbr    : VBRMode1: 'standard', 'CBR1': 'on', 'AutoRateCtrl1': 'off', bitrate is in 'BitRate1'
            # vbr nomax: VBRMode1: 'standard', 'CBR1': 'off', 'AutoRateCtrl1': 'off', bitrate is in 'VBRBitrateMax1'
            # vbr max: VBRMode1: 'bitratelimit', 'CBR1': 'off', 'AutoRateCtrl1': 'off', bitrate is in 'VBRBitrateMax1'
            # adaptive: VBRMode1: 'bitratelimit', 'CBR1': 'off', 'AutoRateCtrl1': 'on', bitrate is in 'AutoRateCtrlBitrateMax1'
            if(status):
                rtspParams = dict(parse_qsl(status))
                if(len(rtspParams)>1):
                    params['streamBitrate']=rtspParams['VBRBitrateMax1'] #for VBR mode, the max allowed bitrate, use max allowed bitrate
                    if(rtspParams['VBRMode1']=='standard' and rtspParams['CBR1']=='on'): #this is CBR mode - bitrate is fixed
                        params['streamBitrate']=rtspParams['BitRate1']
                    if(rtspParams['VBRMode1']=='bitratelimit' and rtspParams['AutoRateCtrl1']=='on'): #this is adaptive mode, the max bitrate is defined in another variable
                        params['streamBitrate']=rtspParams['AutoRateCtrlBitrateMax1']
                    res = rtspParams['ImageSize1'].split(',')
                    params['inputResolution']=res[1]+'p'+rtspParams['FrameRate1']
                    params['streamResolution']=res[1]+'p'
                    params['streamFramerate']=rtspParams['FrameRate1']
                    params['rtsp_port']=int(rtspParams['RTSPPort'])
                    params['connection']=True
        except Exception as e:
            dbg.prn(dbg.SNC|dbg.ERR,"[---]encSonySNC.getParams",e,sys.exc_traceback.tb_lineno)
        return params
    def parseURI(self,url):
        """extracts ip address and port from a uri.
        the url is usually in this format: "http://X.X.X.X:PORT/"
        e.g. from http://192.168.1.103:5953/
        will return 192.168.1.103 and 5953
        """
        addr  = ""
        parts = []
        ip    = False
        parts = url.split('/')
        #extract ip address with port
        if(len(parts)>2):
            addr = parts[2] #this contains X.X.X.X:PORT
        else:
            addr = parts[0] #it is possible the mtURL is "X.X.X.X:PORT/" (no http), then parts[0] will still be X.X.X.X:PORT
        # extract the ip address 
        addr = addr.split(':')
        if(len(addr)>1):
            ip = addr[0]
            port = addr[1]
        else:
            ip = False
            port = False
        return ip, port
    def setBitrate(self,bitrate):
        """ Set device bitrate is in kbps 
            Args:
                bitrate(int): new bitrate in kbps
            Returns:
                (str): response from the url request
        """
        try:
            result = False
            dbg.prn(dbg.SNC,"snc.setbitrate:",bitrate, self.ip)
            # ensure it's in CBR mode and set the bitrate
            result = pu.io.url("http://"+self.ip+"/command/camera.cgi?CBR1=on&BitRate1="+str(bitrate),username='admin',password='admin')
            return result
        except Exception as e:
            dbg.prn(dbg.ERR|dbg.SNC,"[---]snc.setBitrate:", e, sys.exc_traceback.tb_lineno)
        return result
    def setFramerate(self,framerate):
        """ Set device frame rate is in fps 
            Args:
                framerate(int): new frame rate in fps
            Returns:
                (str): response from the url request
        """
        try:
            result = False
            dbg.prn(dbg.SNC,"snc.setframerate:",framerate, self.ip)
            # set the framerate (page uses basic authentication)
            result = pu.io.url("http://"+self.ip+"/command/camera.cgi?FrameRate1="+str(framerate),username='admin',password='admin')
            return result
        except Exception as e:
            dbg.prn(dbg.ERR|dbg.SNC,"[---]snc.setFramerate:", e, sys.exc_traceback.tb_lineno)
        return result
    def update(self):
        """ Requests encoding parameters of the device and updates local class properties"""
        # get the device parameters
        params = self.getParams()
        # dbg.prn(dbg.SNC, params, "snc.update")
        if(params and params['connection']):
            self.resolution = params['inputResolution']
            self.isCamera = self.resolution!=False
            self.bitrate = params['streamBitrate']
            self.framerate = params['streamFramerate']
            self.rtspURL = params['rtsp_url']
        else:
            dbg.prn(dbg.SNC,"update FAIL!")
            self.isOn = False
            self.isCamera = False
            self.resolution = False
            self.bitrate = False
            self.framerate = False
            self.rtspURL = False
            self.initialized = False
#end encSonySNC

class encDebug(encDevice):
    """ A test device class: at the moment used for Liquid Image EGO"""
    def __init__(self, ip=False):
        if(ip):
            super(encDebug,self).__init__(ip)
    def buildCapCmd(self, camURL, chkPRT, camMP4, camHLS): 
        """ Overrides encDevice's method: EGO produces inconsistent PTS, so it requires ffmpeg to generate its own PTS """
        # if ther's a problem, try adding -rtsp_transport udp before -i
        # liquid image EGO camerea requires -fflags +genpts otherwise you get "first pts value must be set" error and won't start ffmpeg
        return c.ffbin+" -fflags +genpts+igndts -rtsp_transport tcp -i "+camURL+" -codec copy -f h264 udp://127.0.0.1:"+chkPRT+" -codec copy -f mpegts udp://127.0.0.1:"+camMP4+" -codec copy -f mpegts udp://127.0.0.1:"+camHLS
        # return c.ffbin+" -rtsp_transport tcp -i "+camURL+" -codec copy -f h264 udp://127.0.0.1:"+chkPRT+" -codec copy -f h264 udp://127.0.0.1:"+camMP4+" -codec copy -f mpegts udp://127.0.0.1:"+camHLS
    #end encBuildCmd
    def discover(self, callback):
        """ Find any new devices using bonjour protocol. 
            Args:
                callback(function): called when a device is found 
            Returns:
                none
        """
        try:
            if(enc.code & enc.STAT_SHUTDOWN):
                return
            devIP = "192.168.42.1"
            response = pu.io.url("http://"+devIP+"/setting/cgi-bin/fd_control_client?func=fd_get_camera_info",timeout=5)
            if(response and response.find('EGO')>0): #found LiquidImage EGO camera
                output = {}
                output['ip'] = devIP
                output['type'] = 'db_tst'
                output['url'] = "rtsp://"+devIP+"/AmbaStreamTest"
                output['port'] = 554
                output['devClass'] = encDebug
                callback(output)
            else:
                # dbg.prn(dbg.TST,"not found any debug devices")
                pass
        except Exception as e:
            dbg.prn(dbg.TST|dbg.ERR,"[---]encDebug.discover",e, sys.exc_traceback.tb_lineno)
    def update(self):
        """ Requests encoding parameters of the device and updates local class properties, sets them to false if unable to retreive the parameters """
        devIP = "192.168.42.1"
        response = pu.io.url("http://"+devIP+"/setting/cgi-bin/fd_control_client?func=fd_get_camera_info",timeout=5)
        if(response and response.find('EGO')>0): 
            self.resolution = "240p30"
            self.isCamera = True
            self.bitrate = "700"
            self.framerate = "30"
            self.rtspURL = "rtsp://"+devIP+"/AmbaStreamTest"
        else:#did not find liquid image camera - probably went offline
            self.isOn = False
            self.isCamera = False
            self.resolution = False
            self.bitrate = False
            self.framerate = False
            self.rtspURL = False
            self.initialized = False
#end encDebug


class source:
    """ A wrapper for a video source (this contains the reference to the video device instance) """
    def __init__(self,ip, encType, ports={}, url=False, preview=False, devClass=False):
        """ create a new video source
            Args:
                ip(str)       : ip address of the source (used for checking if the device is alive)
                ports(dict)   : dictionary of ports used for this source: 
                          mp4 : udp port where ffmpeg that records mp4 file receives data, 
                          hls : udp port where m3u8 segmenter receives MPEG-TS data, 
                          chk : udp port that is used to check whether packets are coming in, 
                          rtp : port used to connect to the rtsp server (for source validation)
                encType(str)  : type of source/encoder (e.g. td_cube, ph_glass, mt_monarch)
                url(str)      : rtsp source url (must specify url or preview)
                preview(str)  : url of the preview rtp stream (must specify url or preview)
        """
        try:
            self.isEncoding     = False # set to true when it's being used in a live event
            self.ports          = ports
            self.type           = encType
            self.rtspURL        = False # this is the public (proxied) rtsp URL - a stream that anyone on the network can view
            self.id             = int(time.time()*1000000) #id of each device is gonna be a time stamp in microseconds (only used for creating threads)
            self.ipcheck        = '127.0.0.1' #connect to this ip address to check rtsp - for now this will be simply connecting to the rtsp proxy, constant pinging of the RTSP on the device directly can cause problems
            self.urlFilePath    = False
            # add a new device, based on its type
            if(not devClass):
                return False
            self.device = devClass(ip)
            self.urlFilePath = "/tmp/pxp-url-"+str(self.device.ip) #this file will contain the url to the proxied RTSP (after running live555proxy)
            self.listFile = False #this will contain the name of the .m3u8 file (not full path)
            if(url):
                self.device.rtspURL = url #this is a private url used for getting the video directly form the device
            if(preview):
                self.previewURL = preview
            if(not 'src' in tmr):
                tmr['src']={}
            # monitor the stream
            tmr['src'][self.id] = TimedThread(self.monitor,period=3)
            # monitor alarms 
            tmr['src'][str(self.id)+'alarm'] = TimedThread(self.device.alarmChk,period=2)
            # monitor device parameters
            tmr['src'][str(self.id)+'param'] = TimedThread(self.device.update,period=5)

        except Exception as e:
            dbg.prn(dbg.ERR|dbg.SRC, "[---]source.init", e, sys.exc_traceback.tb_lineno)
    #end init
    def __repr__(self):
        # prints a string representation of the class object)
        return "<source> url:{rtspURL} type:{type} dev:{device}".format(**self.__dict__)
    def buildCapCmd(self):
        """ creates an ffmpeg capture command for this source using device's buildCapCmd method """
        return self.device.buildCapCmd(self.rtspURL,self.ports['chk'],self.ports['mp4'],self.ports['hls'])
    def camPortMon(self):
        """ monitor data coming in from the camera (during live) - to make sure it's continuously receiving """
        try:
            dbg.prn(dbg.SRC,"starting camportmon for ", self)
            host = '127.0.0.1'          #local ip address
            sIN = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP) #Create a socket object
            portIn = self.ports['chk']
            sIN.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            err = True
            while (err and not (enc.code & enc.STAT_SHUTDOWN)):
                try:
                    sIN.bind((host, portIn)) #Bind to the port
                    err = False
                except:
                    time.sleep(1)
                    err = True
            #end while err
            dbg.prn(dbg.SRC,".............bound.................", self.isEncoding)
            sIN.setblocking(0)
            sIN.settimeout(0.5)
            timeStart = time.time()
            while ((enc.code & (enc.STAT_LIVE | enc.STAT_START | enc.STAT_PAUSED)) and self.isEncoding):
                try:
                    if((enc.code & enc.STAT_PAUSED)): #the encoder is paused - do not check anything
                        time.sleep(0.2) #reduce the cpu load
                        continue
                    data, addr = sIN.recvfrom(65535)
                    if(len(data)<=0):
                        continue
                    #pxp status should be 'live' at this point
                    if((enc.code & enc.STAT_START) and (time.time()-timeStart)>2):
                        enc.statusSet(enc.STAT_LIVE,autoWrite=False)
                except socket.error, msg:
                    # only gets here if the connection is refused or interrupted
                    # sys.stdout.write('.')
                    print '^.^'
                    try:
                        timeStart = time.time()
                        if(enc.code & enc.STAT_LIVE):
                            # only set encoder status if there is a live event 
                            # to make sure the monitor runs an RTSP check on the stream
                            self.device.isOn=False
                            # start file monitor to add EXT-X-DISCONTINUITY
                            if(not(str(self.id)+'_filemon' in tmr['src'])):
                                tmr['src'][str(self.id)+'_filemon'] = TimedThread(self.fileSegMon)
                        time.sleep(1) #wait for a second before trying to receive data again
                    except Exception as e:
                        pass
                except Exception as e:
                    dbg.prn(dbg.ERR|dbg.SRC,"[---]camPortMon err: ",e,sys.exc_traceback.tb_lineno)
            #end while
        except Exception as e:
            dbg.prn(dbg.ERR|dbg.SRC,"[---]camportmon err: ", e, sys.exc_traceback.tb_lineno)
    def fileSegMon(self):
        """ monitors m3u8 file when video stopped unexpectedly. once the video resumes, it'll add the EXT-X-DISCONTINUITY flag """
        def getLastSeg(fPath):
            try:
                # get last few lines of the file (no need to iterate through the entire file)
                p = sb.Popen(['tail', fPath], stdout=sb.PIPE, stderr=sb.PIPE)
                lines, err = p.communicate()
                lastNum = 0
                lastLine = 'zz'
                # print lines, err
                # go through the last few lines of the file and get the number of the last segment
                for line in lines.split("\n"):
                    if (re.search('segm',line) and re.search('[0-9]+', line)):
                        lastLine = line
                        try:
                            # this line contains the segment name
                            lastNum = int(re.search('[0-9]+', line[3:]).group())
                        except Exception as e:#could not extract number from the line (something wrong???)
                            pass
                #end for line in lines.split
                return lastNum
            except Exception as e:
                return 0
        try:
            # set the path to the playlist (m3u8 file)
            listPath = c.wwwroot+'live/video/'+self.listFile
            dbg.prn(dbg.SRC,"^^^^^^FILE SEG MON^^^^^^ file:",listPath,' exists?',os.path.exists(listPath))
            if(not os.path.exists(listPath)):#the file does not exist - can happen here if the camera got disconnected before any segments came in
                dbg.prn(dbg.SRC,"no listPath????????")
                return 

            lastNum = getLastSeg(listPath)
            dbg.prn(dbg.SRC,"last seg:",lastNum)
            while(lastNum==getLastSeg(listPath) and not (enc.code & enc.STAT_SHUTDOWN)): #wait until the file changes (means the video resumed)
                time.sleep(0.4)
            dbg.prn(dbg.SRC,"got new segment!")
            os.system("echo '#EXT-X-DISCONTINUITY' >> "+listPath)
            tmr['src'][str(self.id)+'_filemon'].kill()
            del tmr['src'][str(self.id)+'_filemon']
        except Exception as e:
            print "------fileSegMon:",e,sys.exc_traceback
    #end fileSegMon
    def monitor(self):
        """ monitors the (actual) device parameters and sets source (i.e. wrapper) parameters accordingly """
        try:
            if(enc.code & enc.STAT_SHUTDOWN):
                self.stopMonitor()
                return False
            # ensure there's a live555 proxy running for this device - this statement is executed once, when the device is just added
            if(self.device.rtspURL and not procMan.pexists(name="live555",devID=self.device.ip)): #there is no live555 associated with this device
                self.startProxy()

            live555timeout = time.time()-10 #wait for 10 seconds to restart live555 server if it stalls
            
            # stop live555 to restart it later in an attempt to recover a stalled/stopped stream
            if(not self.device.isOn and self.device.liveStart<live555timeout): 
                # timeout reached - there was no stream - restart live555
                # usually this will happen if the ip address or port on the device changed, 
                # restarting live555 will set it up with those new parameters and get the stream going
                dbg.prn(dbg.SRC,"stopping live555")
                procMan.pstop(name="live555",devID=self.device.ip)
            # if live555 proxy is running, it'll have an rtsp url - this block will get that url
            oldURL = self.rtspURL
            self.setRTSPurl()
            if (not self.rtspURL):
                self.device.initialized = False
                return #there is nothing to do beyond this point without an RTSP url
            #make sure live555 is up and running and no changes were made to the ip address
            if(enc.busy() and not (enc.code & enc.STAT_STOP) and self.rtspURL != oldURL):
                # there is an encode going on
                # RTSP (proxied url) changed - most likey because live555 was restarted - need to update settings with this url
                dbg.prn(dbg.SRC,"url changed", self.rtspURL, oldURL)
                speak("rtsp url changed")
                #update RTSP url in the capturing ffmpeg command if the encoder was live already
                while(procMan.pexists(name='capture', devID = self.device.ip)):
                    #try to stop and wait untill the process is gone 
                    # NB: could stall here if the process refuses to exit or if it's not forced to exit
                    dbg.prn(dbg.SRC,"trying to stoppppppppppppppppp")
                    procMan.pstop(name='capture',devID=self.device.ip)
                capCMD  = self.buildCapCmd() #this will create the capture command (it's individual based on the type of device)
                # start the ffmpeg process
                procMan.padd(name="capture",devID=self.device.ip,cmd=capCMD, keepAlive=True, killIdle=True, forceKill=True, threshold=5)
            #end if enc.busy and not stop and stream url changed mid-stream
            
            # get the port (used to connect to rtsp stream to check its state)
            # the url should be in this format: rtsp://192.168.3.140:8554/proxyStream
            # to get the port:
            # 1) split it by colons: get [rtsp, //192.168.3.140, 8554/proxyStream]
            # 2) take 3rd element and split it by /, get: [8554, proxyStream]
            # 3) return the 8554
            # this port is used for a 'telnet' connection to the server (in the next step)
            self.ports['rtp'] = int(self.rtspURL.split(':')[2].split('/')[0].strip())
            #end if path.exists
            # check rtsp connectivity if it wasn't checked yet
            if(self.rtspURL and not(self.device.isOn and enc.busy())):# stream wasn't flagged as OK yet
                # send a rtsp DESCRIBE command to check if the streaming server is ok
                msg = "DESCRIBE "+self.rtspURL+" RTSP/1.0\r\nCSeq: 2\r\nAccept: application/sdp\r\nUser-Agent: Python MJPEG Client\r\n\r\n"""
                s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                s.settimeout(2)
                try:
                    s.connect((self.ipcheck, self.ports['rtp']))
                    s.send(msg)
                    data = s.recv(65535)
                except Exception as e:
                    data = str(e)
                    dbg.prn(dbg.SRC|dbg.ERR,"[---]source.monitor err: ",e,self.ipcheck,self.ports["rtp"])
                #close the socket
                try:
                    s.close()
                except:
                    #probably failed because couldn't connect to the rtsp server - no need to worry, this error will be handled in the next step
                    pass
                # dbg.prn(dbg.SRC,"RTSP check for ",self.rtspURL,":",data[:200])
                strdata = data[:2048].lower().strip()
                if(strdata.find('host is down')>-1 or strdata.find('no route to host')>-1):
                    # found a "ghost": this device recently disconnected from the network
                    dbg.prn(dbg.SRC,"RTSP ghost found - device is disconnected")
                    pass
                if(strdata.find('timed out')>-1): #the connection is down (maybe temporarily?)
                    dbg.prn(dbg.SRC,"RTSP timeout - temporarily unreachable?")
                    pass
                #a device is not available (either just connected or it's removed from the system)
                #when connection can't be established or a response does not contain RTSP/1.0 200 OK
                self.device.isOn = (data.find('RTSP/1.0 200 OK')>=0)

            # this next IF cuts the framerate in half if it's 50p or 60p
            # most iPads (as of Aug. 2014) can't handle decoding that framerate (coming by RTSP) using ffmpeg 
            # it will decode about 30-50% slower which will create a noticeable (and growing) lag
            # this is only relevant for medical (or any other system that gets direct RTSP stream)
            # maybe now this is irrelevant and can be removed?
            # if(self.device.initialized and self.device.ccFramerate and self.device.framerate>=50):
            #     self.device.setFramerate(self.device.framerate/2) #set resolution to half if it's too high (for tablet rtsp streaming)

            #when device is initialized already, reset the timer - this timer is used to kill the device if it didn't initialize in a certain amount of time
            if(self.device.initialized):
                self.device.initStarted    = int(time.time()*1000) 

            # device is only considered initialized if the stream is on
            # if the stream is unreachable, this will cause device to be re-initialized 
            # or to be removed form the system (if it doesn't start in time) in the sourceManager monitor
            self.device.initialized = self.device.isOn 
        except Exception as e:
            dbg.prn(dbg.ERR|dbg.SRC,"[---]source.monitor", e, sys.exc_traceback.tb_lineno)
            dbg.prn(dbg.ERR|dbg.SRC,"[---dbg---]", self.device.isOn, self.device.liveStart, live555timeout)
            return False
        return True
    #end monitor
    def setRTSPurl(self):
        """ Sets local rtsp url by getting it from the live555 proxy """
        try:
            if(os.path.exists(self.urlFilePath)): #should always exist!!!!
                # in the modified version of live555 the proxied rtsp stream url is stored in a text file, get it
                streamURL = pu.disk.file_get_contents(self.urlFilePath).strip()
                if(not self.rtspURL): #url wasn't set before
                    self.rtspURL = streamURL            
        except Exception as e:
            dbg.prn(dbg.ERR|dbg.SRC,"[---]source.setRTSPurl", e, sys.exc_traceback.tb_lineno)
    def startProxy(self):
        """ Starts the live555  RTSP proxy for this source """
        try:
            dbg.prn(dbg.SRC,"adding live555 for ", self.device.ip, self.type)
            #start live555 process for this device
            procMan.padd(name="live555",devID=self.device.ip,cmd=c.approot+"live555 -o "+self.urlFilePath+" -p "+str(self.ports['rts'])+" "+self.device.rtspURL,keepAlive=True,killIdle=True, forceKill=True)
            # record the time of the live555 server start - will be used in the next step to determine when live555 should be restarted
            self.device.liveStart = time.time()
        except Exception as e:
            dbg.prn(dbg.ERR|dbg.SRC,"[---]source.startProxy", e, sys.exc_traceback.tb_lineno)
    def stopMonitor(self):
        """ Stop monitor and RTSP proxy""" 
        try:
            # stop the monitor
            dbg.prn(dbg.SRC,"stop monitor thread (and other related threads)")
            self.isEncoding = False
            if('src' in tmr and self.id in tmr['src']):
                tmr['src'][self.id].kill()
                tmr['src'][str(self.id)+'alarm'].kill()
                tmr['src'][str(self.id)+'param'].kill()
            dbg.prn(dbg.SRC,"stopping camportmon thread")
            if('portCHK' in tmr and self.id in tmr['portCHK']):
                dbg.prn(dbg.SRC,"encoding: ", self.isEncoding)
                tmr['portCHK'][self.id].kill()                
            dbg.prn(dbg.SRC,"stopping live555")
            # stop the processes associated with this device
            procMan.pstop(name="live555",devID=self.id)
            dbg.prn(dbg.SRC,"done stopping")
        except Exception as e:
            dbg.prn(dbg.ERR|dbg.SRC,"[---]source.stopMonitor", e, sys.exc_traceback.tb_lineno)
#end source class

class sourceManager:
    """ Discovers, monitors and managers all the video sources (a.k.a. wrappers for devices) """
    def __init__(self,devList):
        """ Initializes the source manager
            Args:
                devList(dict): dictionary of all enabled sources
        """
        self.allowIP = True  #whether to allow IP streaming sources to be added
        self.mp4Base = 22500 #ffmpeg captures rtsp stream and outputs H.264 stream here
        self.hlsBase = 22600 #ffmpeg captures rtsp stream and outputs MPEG-TS here
        self.chkBase = 22700 #port where a monitor is sitting and checking if packets are arriving, doesn't matter the format
        self.rtpBase = 8500  #rtsp proxy port - when live555 starts, it will try to run on this port, if that doesn't work, i'll try +1 port and so on
        self.sources = [] #video sources go here
        self.devList = devList
        if(not 'srcmgr' in tmr):
            tmr['srcmgr'] = {}
        tmr['srcmgr']['mgrmon'] = TimedThread(self.monitor, period=3)
        tmr['srcmgr']['discvr'] = TimedThread(self.discovererManage, period=3)
    def alarms(self):
        """ return an array of devices that have alarms set off 
            Args:
                none
            Returns:
                (list): names of sources that have alarms triggered.
        """
        sources = copy.deepcopy(self.sources)
        alarms = []
        idx = 0
        for src in sources:
            if src.device.alarm:
                alarms.append("s_"+str(idx).zfill(2)) #the s_ prefix is generated in pxp.py
            idx+=1
        return alarms
    def addDevice(self, inputs):
        """ Adds a source to the source list
            Args:
                inputs (dict): the list of parameters required for each source:
                        ip (str) : ip address of the source (used for checking if the device is alive)
                        url (str) : rtsp source url
                        port (int): rtsp port
                        type (str) : type of source/encoder (e.g. td_cube, ph_glass, mt_monarch, etc.)
                        devClass (class) : reference to the class of the device (for initialization)
            Returns:
                bool : True if success, False otherwise
        """
        try:
            if((enc.code & enc.STAT_SHUTDOWN) or enc.busy()):#do not add new cameras during live event
                return False
            if(len(self.sources)>c.maxSources): #do not add more than maximum allowed sources in the system
                return False
            sources = copy.deepcopy(self.sources)
            if(not((('url' in inputs) or ('preview' in inputs)) and ('ip' in inputs))):
                #neither url nor preview was specified or ip wasn't specified - can't do anything with this encoder
                return False
            ip = inputs['ip']
            idx = self.exists(ip)
            if(idx>=0): 
                #this device already exists in the list
                #must've re-discovered it, or discovered another streaming server on it (e.g. preview)
                if('url' in inputs): #update url (in case it's changed)
                    self.sources[idx].device.rtspURL = inputs['url']
                    # self.sources[idx].device.ports['rtp'] = int(inputs['port'])
                elif('preview' in inputs):
                    self.sources[idx].previewURL = inputs['preview']
                    self.sources[idx].ports['preview'] = int(inputs['preview-port'])
                if('port' in inputs):#update the ports as well (may have changed)
                    self.sources[idx].ports['rtp'] = inputs['port']
                return True
            #end if idx>=0
            # discovered a new streaming device
            idx = self.nextIdx()
            #device does not exist yet (just found it)
            #assign ports accordingly
            ports = {
                    "mp4":self.mp4Base+idx,
                    "hls":self.hlsBase+idx,
                    "chk":self.chkBase+idx,
                    "rts":self.rtpBase+(idx*100) #each camera has 100 rtsp/rtp proxy ports - in case it needs to restart the live555 instance and it doesn't have a proxy port available, it can increment it
                }
            if('url' in inputs):#the device discovered was the main url device
                ports['rtp'] = int(inputs['port'])
                dev = source(ip=ip,url=inputs['url'],encType=inputs['type'], ports=ports, devClass=inputs['devClass'])
            elif('preview' in inputs):#discovered the preview version of the device
                ports['preview'] = int(inputs['preview-port'])
                dev = source(ip=ip,preview=inputs['preview'],encType=inputs['type'], ports=ports, devClass=inputs['devClass'])
            if(dev):
                dev.idx = idx
                self.sources.append(dev)
                dbg.prn(dbg.SRM,"all sources (devices): ", self.sources)
                return True
        except Exception as e:
            dbg.prn(dbg.SRM|dbg.ERR, "[---]srcMgr.addDevice: ",e, sys.exc_traceback.tb_lineno)
        return False
    #end addDevice
    def discovererManage(self):
        """ Starts device discoverers if the current server is master or stops them if it's not """
        try:
            if(enc.code & enc.STAT_SHUTDOWN):
                tmr['srcmgr']['discvr'].kill() #stop discovererManager()
                return #encoder is shutting down - nothing to do here
            if(not syncMgr.isMaster):#only master can get IP streams, and this device isn't master
                self.allowIP = False
                if('srcmgr' in tmr and 'devs' in tmr['srcmgr']):
                    # remove any existing IP sources and stop looking for them
                    devs = tmr['srcmgr']['devs'].copy()
                    # remove every available source from the dictionary
                    for s in devs:
                        dbg.prn(dbg.SRM, "trying to remove",s)
                        tmr['srcmgr']['devs'][s].kill()
                        del tmr['srcmgr']['devs'][s]
                    #remove the devices dictionary
                    del tmr['srcmgr']['devs']
                #end if devs in srcmgr
                return 
            #end if
            # this device IS a master
            self.allowIP = True
            if('srcmgr' in tmr and 'devs' in tmr['srcmgr']):
                return #the discoverers were started already
            
            # this is the first time running this method since this device became Master
            # this dictionary will contain threads that look for video sources on the network
            tmr['srcmgr']['devs'] = {}
            # start discovering all known devices
            for devName in self.devList:
                dev = self.devList[devName]['class']()
                tmr['srcmgr']['devs'][devName] = TimedThread(dev.discover, params=self.addDevice, period=5)
        except Exception as e:
            dbg.prn(dbg.ERR|dbg.SRM, "[---]srcMgr.discover: ",e, sys.exc_traceback.tb_lineno)
    #end discover
    def encCapPause(self):
        """ Pause a live stream """
        if(enc.code & enc.STAT_LIVE):
            enc.statusSet(enc.STAT_PAUSED)
            procMan.pstop(name='capture',remove=False)
    def encCapResume(self):
        """ Resume a paused live stream """
        if(enc.code & enc.STAT_PAUSED):
            procMan.pstart(name='capture')
            enc.statusSet(enc.STAT_LIVE)
    def encCapStart(self):
        """ Start live stream """
        dbg.prn(dbg.SRM, "cap start")
        try:
            if(not (enc.code & enc.STAT_READY)): #tried to start a stream that's already started or when there are no cameras
                return False
            enc.statusSet(enc.STAT_START)            
            # make sure ffmpeg's and segmenters are off:
            os.system("killall -9 "+c.segname+" 2>/dev/null")
            os.system("killall -9 "+c.ffname+" 2>/dev/null")
            # cmd = "cd /var/www/html/events/live/video && /usr/bin/mediastreamsegmenter -d 1 -p segm_ -m list.m3u8 -i udp://127.0.0.1:22200 -u ./"
            # sb.Popen(cmd.split(' '),stderr=FNULL,stdout=FNULL)
            # ffstreamIns = []
            # part of ffmpeg command that has all the inputs (e.g. -i 127.0.0.1:2210 -i 127.0.0.1:2211)
            ffmp4Ins = c.ffbin+" -y"
            # part of ffmpeg command that has all the outs (e.g. -map 0 out0.mp4 -map 1 out1.mp4)
            ffmp4Out = ""
            # individual HLS segmenter commands (can't use one segmenter to segment multiple streams)
            segmenters = {}
            # individual ffmpeg instances to capture each camera (this way if one fails, the rest continue working)
            ffcaps = {}
            streamid = 0
            # old versions of the app do not dynamically read urls, the url (events/live/list.m3u8) is hard-coded (why?!!)
            # and thus with multicam (or single camera but new server) setup it will not work
            # for backwards compatibility, use first camera as "the only" camera available for streaming 
            # and create a soft link to the first list_XX.m3u8
            oldSupportSuffix = -1
            # go through each source and set up the streaming/capturing services
            for idx in xrange(len(self.sources)):
                if(idx>=len(self.sources)): #would only go here if number of sources changed during iteration. there are checks to prevent this
                    break
                src = self.sources[idx]
                if(not(src.device.isCamera and src.device.isOn)):#skip devices that do not have a video stream available
                    continue
                # # each camera has its own ffmpeg running it, otherwise if 1 camera goes down, all go down with it
                # if('format' in cameras[devID] and 'devID'=='blackmagic'): #format is explicitly specified for this camera (usually for blackmagic)
                #   ffstreamIn = c.ffbin+" -y -f "+cameras[devID]['format']+" -i "+cameras[devID]['url']
                #   ffstreamIn += " -codec copy -f h264 udp://127.0.0.1:221"+str(streamid)
                #   ffstreamIn += " -codec copy -f mpegts udp://127.0.0.1:220"+str(streamid)
                #   ffstreamIns.append(ffstreamIn)
                # for saving multiple mp4 files, one ffmpeg instance can accomplish that
                camIdx  = str(idx)
                camMP4  = str(src.ports['mp4']) #ffmpeg captures rtsp from camera and outputs h.264 stream to this port
                camHLS  = str(src.ports['hls']) #ffmpeg captures rtsp form camera and outputs MPEG-TS to this port
                chkPRT  = str(src.ports['chk']) #port where a monitor is sitting and checking if packets are arriving, doesn't matter the format
                ffmp4Ins +=" -fflags +igndts -i udp://127.0.0.1:"+camMP4
                # if(len(self.sources)<2):
                #     listSuffix = ""
                #     # there is only one camera - no need to set camIdx for file names
                #     filePrefix = ""
                # else: #multiple cameras - need to identify each file by camIdx
                # always add source indecies - future server versions will deprecate old style file naming
                filePrefix = camIdx.zfill(2)+'hq_' #left-pad the camera index with zeros (easier to sort through segment files and thumbnails later on)
                listSuffix = "_"+camIdx.zfill(2)+'hq' #for normal source, assume it's high quality
                # backward-compatibility for old ipad app versions
                if(oldSupportSuffix<1):
                    oldSupportSuffix = listSuffix

                self.sources[idx].listFile = 'list'+listSuffix+'.m3u8'
                # TODO: add a lq stream for devices with preview
                ffmp4Out +=" -map "+camIdx+" -fflags +igndts -codec copy -bsf:a aac_adtstoasc "+c.wwwroot+"live/video/main"+listSuffix+".mp4"
                # this is HLS capture (segmenter)
                if (pu.osi.name=='mac'): #mac os
                    segmenters[src.device.ip] = c.segbin+" -p -t 1s -S 1 -B "+filePrefix+"segm_ -i "+self.sources[idx].listFile+" -f "+c.wwwroot+"live/video 127.0.0.1:"+camHLS
                elif(pu.osi.name=='linux'): #linux
                    os.chdir(c.wwwroot+"live/video")
                    segmenters[src.device.ip] = c.segbin+" -d 1 -p "+filePrefix+"segm_ -m list"+filePrefix+".m3u8 -i udp://127.0.0.1:"+camHLS+" -u ./"

                # this ffmpeg instance captures stream from camera and redirects to mp4 capture and to hls capture
                dbg.prn(dbg.SRM, "capcmd:",src.rtspURL, chkPRT, camMP4, camHLS)
                ffcaps[src.device.ip] = src.buildCapCmd()
                self.sources[idx].isEncoding = True
            #end for device in cameras
            # this command will start a single ffmpeg instance to record to multiple mp4 files from multiple sources
            ffMP4recorder = ffmp4Ins+ffmp4Out

            # start the HLS segmenters and rtsp/rtmp captures
            startSuccess = True
            tmr['portCHK'] = {}
            for idx in xrange(len(self.sources)):
                if(idx>=len(self.sources)):
                    break
                src = self.sources[idx]
                if(not src.isEncoding):
                    continue
                # segmenter
                startSuccess = startSuccess and procMan.padd(name="segment",devID=src.device.ip,cmd=segmenters[src.device.ip],forceKill=True)
                # ffmpeg RTSP capture
                startSuccess = startSuccess and procMan.padd(name="capture",devID=src.device.ip,cmd=ffcaps[src.device.ip], keepAlive=True, killIdle=True, forceKill=True, threshold=5)
                # start port checkers for each camera
                tmr['portCHK'][src.device.ip]=TimedThread(self.sources[idx].camPortMon)
            #end for dev in segmenters

            # start mp4 recording to file
            startSuccess = startSuccess and procMan.padd(cmd=ffMP4recorder,name="record",devID="ALL",forceKill=False)
            if(not startSuccess): #the start didn't work, stop the encode
                self.encCapStop() #it will be force-stopped automatically in the stopcap function
            # for backwards compatibility (with older app versions) add list.m3u8
            os.system("ln -s "+c.wwwroot+"live/video/list"+oldSupportSuffix+".m3u8 "+c.wwwroot+"live/video/list.m3u8 >/dev/null 2>/dev/null")
        except Exception as e:
            dbg.prn(dbg.ERR|dbg.SRM,"[---]encCapStop: ",e,sys.exc_traceback.tb_lineno)
            self.encCapStop() #it will be force-stopped automatically in the stopcap function
            enc.statusSet(enc.STAT_READY)
    #end encCapStart
    def encCapStop(self,force=False):
        """ Stops live stream, kill all ffmpeg's and segmenters
            Args:
                force (bool,optional) : force-kill all the processes - makes stopping process faster
        """
        try:
            dbg.prn(dbg.SRM,"stopping capture... force:",force)
            if(enc.code & enc.STAT_STOP): #already stopping
                return False
            if(not(enc.code & (enc.STAT_LIVE | enc.STAT_PAUSED))):
                force = True #the encode didn't finish starting or didn't start properly - force shut down everything
            if(not (enc.code & enc.STAT_SHUTDOWN)): #set the status to stopping (unless the script is being shut down then it should stay at shutting down)
                enc.statusSet(enc.STAT_STOP)
            # stop all captures
            dbg.prn(dbg.SRM,"stopping segment and capture")
            # this is used for forwarding blue screen (without it the mp4 file will be corrupt)
            ffBlue = c.ffbin+" -loop 1 -y -re -i "+c.approot+"bluescreen.jpg"
            # stop the segmenters and ffmpeg stream capture for all cameras
            procMan.pstop(name="segment")
            procMan.pstop(name="capture")
            # build the bluescreen forwarder command
            for idx in xrange(len(self.sources)):
                if(idx>=len(self.sources)):
                    break
                src = self.sources[idx]
                if(not src.isEncoding):
                    continue
                self.sources[idx].isEncoding = False
                ffBlue += " -r 30 -vcodec libx264 -an -f mpegts udp://127.0.0.1:"+str(src.ports['mp4'])
            #end while
            timeout = 20 #how many seconds to wait for process before force-stopping it
            timeStart = time.time() #start the timeout timer to make sure the process doesn't hang here
            # wait for ffmpeg and hls processes to stop
            while((procMan.palive("capture") or procMan.palive("segment")) and (not (enc.code & enc.STAT_SHUTDOWN)) and (time.time()-timeStart)<timeout):
                time.sleep(1)
            if((time.time()-timeStart)>=timeout):#timeout reached
                if(procMan.palive("capture")): #force-stop the capture ffmpeg
                    procMan.pstop(name="capture",force=True)
                if(procMan.palive("segment")): #force-stop the segmenter
                    procMan.pstop(name="segment",force=True)
            dbg.prn(dbg.SRM,"stopped, forwarding the bluescreen")

            # to stop mp4 recorder need to push blue screen to that ffmpeg first, otherwise udp stalls and ffmpeg produces a broken MP4 file
            procMan.padd(cmd=ffBlue, name="blue", devID="ALL", keepAlive=True, killIdle = True, forceKill=True)
            time.sleep(5)
            timeStart = time.time()
            while(((time.time()-timeStart)<timeout) and not procMan.palive(name="blue")):
                time.sleep(1)
            # now we can stop the mp4 recording ffmpeg
            dbg.prn(dbg.SRM,"stopping mp4 recorder")
            procMan.pstop(name='record',force=force)
            timeStart = time.time()
            # wait for the recorder to stop, then kill blue screen forward
            while(procMan.pexists("record") and not (enc.code & enc.STAT_SHUTDOWN) and (time.time()-timeStart)<timeout):
                time.sleep(1)
            if((time.time()-timeStart)>=timeout):#timeout reached
                procMan.pstop(name='record', force=True)
            dbg.prn(dbg.SRM,"mp4 record stopped--")
            # kill the blue screen ffmpeg process
            procMan.pstop(name='blue')
            timeStart = time.time()
            while(procMan.palive("blue") and not (enc.code & enc.STAT_SHUTDOWN) and (time.time()-timeStart)<timeout): #wait for bluescreen ffmpeg to stop
                time.sleep(1)
            if((time.time()-timeStart)>=timeout):#timeout reached
                procMan.pstop(name='blue', force=True)
            dbg.prn(dbg.SRM,"bluescreen stopped")
            # stop the live555 (for good measure)
            os.system("killall -9 live555 >/dev/null 2>/dev/null")
        except Exception as e:
            dbg.prn(dbg.SRM|dbg.ERR,"[---]encCapStop: ",e,sys.exc_traceback.tb_lineno)
        dbg.prn(dbg.SRM,"stopping DONE! current status:",enc.code)
        if(enc.code & enc.STAT_STOP):
            enc.statusSet(enc.STAT_READY)
    #end encStopCap
    def exists(self, ip):
        """ Check if a device with this IP exists already 
            Args:
                ip (str) :   ip address of the device to lookup
            Returns:
                (int): if the search is successful, return index of the device in the array, if the device is not found return -1
        """
        try:
            sources = copy.deepcopy(self.sources)
            idx = 0
            for src in sources:
                if(ip==src.device.ip):
                    return idx
                idx +=1
        except Exception as e:
            dbg.prn(dbg.SRM|dbg.ERR, "[---]sources.exists:",e,sys.exc_traceback.tb_lineno)
        return -1
    #end exists
    def monitor(self):
        """ Monitor the source to make sure it starts properly or gets removed from the list if it can't. """
        try:
            if(enc.code & enc.STAT_SHUTDOWN):
                return False
            # check if all the devices are on
            sources = copy.deepcopy(self.sources)
            idx = 0
            isCamera = False
            # time (in ms) to wait for a device to initialize before removing it.
            # i.e. if a device didn't initialize in this time, it will be removed from the list
            initTimeout = 20000 
            for src in sources:
                now = int(time.time()*1000)
                if (((not src.device.initialized) and (now-src.device.initStarted)>initTimeout) or ((not self.allowIP) and src.device.isIP)): 
                    # could not initialize the device or the device is an IP streaming device and they are not allowed at the moment
                    if(not enc.busy()):
                        # do not touch this device during a live event
                        dbg.prn(dbg.SRM, "could not init device or IP sources are not allowed - stop monitor")
                        # src.stopMonitor()
                        self.sources[idx].stopMonitor()
                        devIP = src.device.ip
                        dbg.prn(dbg.SRM, "deleting...", self.sources)
                        del self.sources[idx]
                        dbg.prn(dbg.SRM, "deleted ", self.sources)
                        if(not(enc.code & (enc.STAT_LIVE|enc.STAT_PAUSED|enc.STAT_STOP))):
                            procMan.pstop(devID=devIP) #stop all the processes associated with this device
                    #end if not busy
                else:
                    idx+=1
                    isCamera = isCamera or src.device.isCamera
                #end if not inited...else

            #end for src in sources
            if(not isCamera):# no cameras on any encoders
                # set status bit to NO CAMERA - this will need to be done on per-camera basis (not for the entire encoder)
                enc.statusSet(enc.STAT_NOCAM,overwrite=(enc.code & enc.STAT_READY)>0)
            else:
                if((enc.code==enc.STAT_NOCAM) or enc.code & (enc.STAT_INIT | enc.STAT_CAM_LOADING)):
                    #status was set to NOCAM (or it was the initialization procedure), when camera returns it should be reset to ready
                    enc.statusSet(enc.STAT_READY)
                elif(enc.code & enc.STAT_NOCAM):#encoder status was something else (e.g. live + nocam) now simply remove the nocam flag
                    enc.statusUnset(enc.STAT_NOCAM)
            # self.toJSON()
        except Exception as e:
            dbg.prn(dbg.ERR|dbg.SRM, "[---]srcmgr.monitor:",e, sys.exc_traceback.tb_lineno)
    #end monitor
    def nextIdx(self):
        """ Finds next available camera index """
        if(len(self.sources)<1): #there are no sources yet - first index will be zero
            return 0 
        sources = self.sources[:] #copy of list
        # get indecies of all sources
        indecies = []
        for src in sources:
            indecies.append(src.idx)
        # sort them (to make sure lowest index is at the start)
        indecies.sort()
        # look for 'gaps', that will be the next available index: e.g. in a list of [0,1,3] there's a gap at index 2, the index will be set to 2
        # or a 'gap' can be at the beginning: [1,2,3] has a gap at index 0.
        # if there are no gaps, it will return the next highest integer, from a list [0,1,2] will return 3
        found = -1
        for idx in xrange(len(indecies)):
            if (idx!=indecies[idx]):
                found = idx
                break
        if (found<0):#did not find a 'gap', get the next largest value
            found = indecies[-1]+1
        return found
    def setBitrate(self, bitrate, camID=-1):
        """ Change camera/encoder bitrate
            Args:
                bitrate(int): new bitrate to set
                camID(int, optional): id of the encoder/camera. if not specified, the bitrate will be set for all cameras
            Returns:
                none
        """
        try:
            sources = copy.deepcopy(self.sources)
            #go through all sources looking for the specific source id
            for src in sources:
                if(src.device.ccBitrate and (src.id==camID or int(camID)<0)): #this device allows changing bitrate, found the right camera or setting bitrate for all the cameras
                    src.device.setBitrate(int(bitrate))
        except Exception as e:
            dbg.prn(dbg.ERR|dbg.SRM, "[---]mgr.setBitrate",e,sys.exc_traceback.tb_lineno)
    #end setBitrate
    def toJSON(self):
        """ Creates a dictionary of all the sources and returns it
            Args:
                autosave(bool,optional): saves the dictionary in json format to a pre-defined file.default:True
            Return:
                (dictionary): indecies are camera IPs.
        """
        try:
            sources = copy.deepcopy(self.sources)
            validDevs = {}
            for src in sources:
                validDevs[src.device.ip] = {
                    "url"           :   src.rtspURL,
                    "resolution"    :   src.device.resolution,
                    "bitrate"       :   src.device.bitrate,
                    "ccBitrate"     :   src.device.ccBitrate,
                    "framerate"     :   src.device.framerate,
                    "deviceURL"     :   src.device.rtspURL,
                    "type"          :   src.type,
                    "cameraPresent" :   src.device.isCamera,
                    "on"            :   src.device.isOn
                }
            return validDevs
        except Exception as e:
            dbg.prn(dbg.ERR|dbg.SRM, "[---]srcmgr.toJSON", e, sys.exc_traceback.tb_lineno)
        return {}
    #end toJSON
#end sourceManager class

##########################
## network sync classes ##
##########################

class SyncSrv(object):
    """ A server object that can be synced """
    enabledUp = False #sync up enabled on this server
    enabledDn = False #sync down enabled - this is irrelevant here, all servers pull events, no pushing needed
    ip        = False
    master    = False #whether this server is a master
    dnCount   = 0 #how many updateInfo requests failed
    def __init__(self, ip):
        self.ip = ip
        try:
            self.updateInfo()
            tmr['srvsync'][self.ip] = TimedThread(self.updateInfo,period=5)
        except Exception as e:
            dbg.prn(dbg.ERR|dbg.SSV,"[---]syncsrv.init:", e, sys.exc_traceback.tb_lineno)
    def cancel(self):
        """ TO IMPLEMENT: stop the sync """
        pass
    def doneCopy(self):
        """ gets called when download finished """
        pass
    def monitor(self):
        """ monitors sync progress """
        pass
    def syncUp(self):
        """ Syncs events from this instance of (remote) server to the local server """
        try:
            cfg = pxp._cfgGet(c.wwwroot+"_db/")
            dbg.prn(dbg.SSV,"trying sync")
            if(not cfg): #probably this server is not initialized
                return False
            if(len(cfg)<4): #old encoders won't have the syncLevel by default, this is a workaround
                localSyncLevel = 0
            else:
                localSyncLevel = int(cfg[3])
            customerID = cfg[2]
            # get a list of remove events
            resp = pu.io.url("http://"+self.ip+"/min/ajax/getpastevents",timeout=10)
            if(not resp):#remote server went down or something happened to the network
                return False
            data = json.loads(resp)
            eventsRm = data['events']
            if(not(type(eventsRm) is list)):
                dbg.prn(dbg.SSV,"invalid response sync:",resp)
                return #the response was not a list - there's nothing to do with this encoder
            # see if this encoder was synced to cloud more recently than the local encoder
            # get this encoder's sync level

            resp = pu.io.url("http://"+self.ip+"/min/ajax/synclevel",timeout=5)
            data = json.loads(resp)
            remoteSyncLevel = int(data['level'])
            if(remoteSyncLevel>localSyncLevel):
                # the remote encoder has higher sync level than local encoder - sync local to cloud
                pxp._syncEnc() #syncing to cloud requires only authentication number, it's added in the syncEnc()

            # POSSIBLE OPTION:
            # x-sync between encoders:
            # just get the data from the other encoder and replace it on the local one 
            # since the synclevel on remote is higher, we can just replace the local data

            # NB: do not delete events marked as deleted=1 from database - so they don't re-sync after being deleted on local encoder

            # get a list of local events
            localList = pxp._listEvents(showDeleted=False)
            # convert list of local events to a dictionary with HID as the key
            eventsLc = {}
            for evt in localList:
                eventsLc[evt['hid']] = evt
            sizeLimit = 5<<20 #==5Mb. if the remote event is bigger than local by this amount, then sync everything
            # compare two lists (sizes and md5 checksums)
            toSync = 0
            for evt in eventsRm:
                hid = evt['hid']
                if('live' in evt):
                    continue #do not sync live events - will cause a mess!
                if(not (hid in eventsLc) or (evt['size']>(eventsLc[hid]['size']+(sizeLimit)))): 
                    # either this event doesn't exist on the local server, or there's at least sizeLimit difference
                    # do a full sync: (meta)data+video
                    # request a full directory of the event in json format (to download)
                    resp = json.loads(pu.io.url("http://"+self.ip+"/min/ajax/evtsynclist",params={"event":hid,"full":1}).strip())
                elif(evt['md5'] != eventsLc[hid]['md5']):
                    # metadata in this event changed - do a metadata-only sync
                    resp = json.loads(pu.io.url("http://"+self.ip+"/min/ajax/evtsynclist",params={"event":hid,"full":0}).strip())
                else:
                    # this event was not changed - do nothing
                    continue
                if(resp and 'entries' in resp):
                    # self.urlListDn(baseurl="http://"+self.ip,fileList = resp['entries'], dest=c.wwwroot+evt['datapath'])
                    # network sync has lower priority than user-initiated sync's, but higher than local backup
                    # in order for sync to complete before automatic backup kicks in and tries to back up an event that wasn't synced yet
                    backuper.add(hid=hid,priority=3,remoteParams={"url":"http://"+self.ip,"files": resp['entries']})
                    toSync +=1
                else:
                    dbg.prn(dbg.SSV,"invalid response from ",self.ip,": ",resp)
            dbg.prn(dbg.SSV,"TO SYNC: ",toSync)
        except Exception as e:
            dbg.prn(dbg.ERR|dbg.SSV,"[---]syncsrv.syncUp:", e, sys.exc_traceback.tb_lineno, 'ip:',self.ip)
    def statusTxt(self):
        pass
    def stopMon(self):
        """ Stops the monitor """
        try:
            tmr['srvsync'][self.ip].kill()
        except:
            pass
    def updateInfo(self):
        """ Determine whether this server allows sync - reads the settings file and updates local properties """
        try:
            resp = pu.io.url("http://"+self.ip+"/min/ajax/serverinfo",timeout=4) #if it takes more than 10 seconds to get the server info, the connection is too slow for backup anyway
            if(not resp): #the server must have gone dark
                self.dnCount +=1
                return
            resp = json.loads(resp)
            if('settings' in resp and 'up' in resp['settings']):
                self.enabledUp = int(resp['settings']['up'])
            if('settings' in resp and 'dn' in resp['settings']):
                self.enabledDn = int(resp['settings']['dn'])
            if('master' in resp):
                self.master = int(resp['master'])
            if('down' in resp):
                self.dnCount +=1
            else:
                self.dnCount = 0
        except Exception as e:#something is wrong with the response from the server
            self.dnCount +=1
            dbg.prn(dbg.ERR|dbg.SSV,"[---]syncsrv.init:", e, sys.exc_traceback.tb_lineno)
    #end updateInfo        
#end SyncSrv

class SyncManager(object):
    """ Manages networked servers: finds pxp servers, checks their options, syncs the events between them """
    servers = {} #dictionary of syncable servers
    enabledUp = False #this is irrelevant for current server, it will pull new info from other servers, not push anything
    enabledDn = False
    isMaster = False
    def __init__(self):
        super(SyncManager, self).__init__()
        # start discovering as soon as the system is up
        if(not 'srvsync' in tmr):
            tmr['srvsync'] = {}
        tmr['srvsync']['mgr'] = TimedThread(self.discover,period=10)
        tmr['srvsync']['snc'] = TimedThread(self.syncAll,period=30)
        tmr['srvsync']['mon'] = TimedThread(self.monitor,period=5)
        self.startTime = time.time()
    def arbitrate(self):
        """ Based on all discovered devices makes a decision on whether this server will be master or not """
        try:
            if(enc.code & (enc.STAT_START | enc.STAT_LIVE | enc.STAT_PAUSED)): 
                # there is a live event on this encoder - it must be master already
                # even if it's not, that means another master already has a live event as well - cannot re-arbitrate during live event
                return
            dbg.prn(dbg.SMG,"arbitrating")
            servers = self.servers.keys() #list of remote servers
            masterPresent = False
            highestIP = pu.io.myIP() #start from itself assuming it's highest IP
            for srvIP in servers: #go through each server and check if it's a master
                masterPresent = masterPresent or ((srvIP in self.servers) and self.servers[srvIP].master)
                highestIP = max(highestIP, srvIP)
            #local device will be a master if there are no other masters on the network, 
            # and local device has highest string-value-IP of all other servers OR it was elected as a master previously
            self.isMaster = (not masterPresent) and ((highestIP in pu.io.myIP(allDevs = True)) or self.isMaster)
            master = 'master' if self.isMaster else 'not master'
            dbg.prn(dbg.SMG,'found:',servers,'(', (len(servers)+1), ') the local is', master)
            if(enc.code & enc.STAT_INIT):
                enc.statusSet(enc.STAT_READY,overwrite=False)
        except Exception as e:
            dbg.prn(dbg.SMG|dbg.ERR, "[---]syncmgr.arbitrate:", e, sys.exc_traceback.tb_lineno)
    def compareVersion(self,ver1,ver2="1.0.13"):
        """ Compares two versions (in dot-delimeted string format)

        Args:
            ver1 (str): version number to compare. e.g. 1.0.9
            ver2 (str, optional): pre-defined version number being compared. default: 1.0.13
        
        Returns:
            int:    1  if ver1>ver2
                    0  if they are equal
                    -1 if ver1<ver2
        """
        # compares 2 groups (i.e. in 1.0.10a 1, 0, 10a are groups)
        def cmpGroup(grp1,grp2):
            # extract a number from each group
            n1 = re.sub('[^0-9]+','',grp1)
            n2 = re.sub('[^0-9]+','',grp2)
            # extract non-numeric part of the group (e.g. 'c' from 3c)
            s1 = re.sub('[0-9]+','',grp1)
            s2 = re.sub('[0-9]+','',grp2)
            # make sure empty strings are counted as zero
            n1 = 0 if (not n1) else n1
            n2 = 0 if (not n2) else n2
            # take the difference
            diff = min(max(int(n1)-int(n2),-1),1)
            if(diff):
                return diff #the numbers are different - return the result
            # so far the groups are the same - compare the non-numeric parts
            return 1 if (s1>s2) else -1 if(s2<s1) else 0
        #end cmpGroup
        result = 0
        # compare version
        arr1  = re.sub('[^0-9\.]+','',ver1).split('.') #e.g. ['1','2','11'] for version 1.2.11
        arr2  = re.sub('[^0-9\.]+','',ver2).split('.')  #e.g. ['1','0','13'] for version 1.0.13
        # go through each tuple and compare the numbers
        for g1, g2 in izip_longest(arr1,arr2,fillvalue='0'): # creates a list of tuples, e.g.: [('1','1'), ('0','2'), ('13','11')]
            result = cmpGroup(g1,g2) if(not result) else result
        return result
    #end compareVersion

    def discover(self):
        """ Discovers any pxp servers on the network using bonjour protocol. """
        if(enc.code & enc.STAT_SHUTDOWN):
            return False
        # get customer ID for authentication
        cfg = pxp._cfgGet()
        if(not cfg): 
            dbg.prn(dbg.SMG|dbg.ERR,"syncmgr.discover: not initialized")
            return False
        customerID = cfg[2]
        self.discoveredRunning = False
        def discovered(result):
            if(enc.code & enc.STAT_SHUTDOWN):
                return
            if(result['ip'] in pu.io.myIP(allDevs=True)): #found itself - skip
                return
            if(result['ip'] in self.servers): #this server was already discovered
                return
            try:
                if(self.discoveredRunning): #to prevent multiple versions of discovered() running at the same time - don't need to add multiple copies of the same remote server
                    return
                self.discoveredRunning = True
                srvResponse = ''
                # check version first (older versions don't support sync)
                srvResponse = pu.io.url("http://"+result['ip']+'/min/ajax/version')
                if(not srvResponse):
                    dbg.prn(dbg.SMG, 'no server at',result['ip'])
                    self.discoveredRunning = False
                    return
                resp = json.loads(srvResponse.strip())
                if(not 'version' in resp):
                    dbg.prn(dbg.SMG, 'old server at',result['ip'])
                    self.discoveredRunning = False
                    return
                if(self.compareVersion(resp['version'])<0):
                    dbg.prn(dbg.SMG, 'old server at',result['ip'],'version:',resp['version'])
                    self.discoveredRunning = False
                    return
                dbg.prn(dbg.SMG,"server version: ",resp['version'])
                # check if this server is from the same customer
                srvResponse = pu.io.url("http://"+result['ip']+'/min/ajax/auth/{"id":"'+customerID+'"}')
                if(not srvResponse):
                    dbg.prn(dbg.SMG, 'no server at',result['ip'])
                    self.discoveredRunning = False
                    return
                resp = json.loads(srvResponse.strip())
                if ('success' in resp and resp['success']):
                    self.servers[result['ip']]=SyncSrv(result['ip'])
                    speak("found "+re.sub('[\.]','.dot.',str(result['ip'][result['ip'].rfind('.')+1:]))+", total "+str(len(self.servers)+1)+" servers, derka derka.")
                else:
                    dbg.prn(dbg.SMG,"server not added (wrong customer):",result['ip'])
            except Exception as e:
                # most likely could not process response - that was an old server
                dbg.prn(dbg.ERR|dbg.SMG, "[---]syncmgr.discovered:", e, sys.exc_traceback.tb_lineno, "response:",srvResponse)
            self.discoveredRunning = False
        #end discovered
        pu.bonjour.discover(regtype="_pxp._udp",callback=discovered)
        if((time.time()-self.startTime)>30):
            # the server had at least 30 seconds to discover other devices
            # perform the arbitration
            TimedThread(self.arbitrate)
        else:
            dbg.prn(dbg.SMG, "waiting to arbitrate, ", time.time(), self.startTime)
    #end discover
    # monitors encoders
    def monitor(self):
        """ Monitor the servers and remove dead ones
            Args:
                none
            Returns:
                none
        """
        try:
            servers = self.servers.keys() #list of remote servers
            for srvIP in servers:
                if(srvIP in self.servers):
                    if(self.servers[srvIP].dnCount>2):
                        speak("encoder "+srvIP+" is down")
                        #this server was down for a while - remove it from the list of known servers
                        self.servers[srvIP].stopMon()
                        del self.servers[srvIP]
            #end for srv in servers
        except Exception as e:
            dbg.prn(dbg.ERR|dbg.SMG,"[---]syncmgr.monitor",e,sys.exc_traceback.tb_lineno)
    #end monitor
    def syncAll(self):
        """ Syncs all remote servers to self """
        try:
            if(enc.code & enc.STAT_SHUTDOWN):
                return
            # make sure local server has sync enabled
            settings = pu.disk.cfgGet(section="sync")
            if('dn' in settings and int(settings['dn'])):#down sync enabled on the local server - sync all remote servers
                servers = self.servers.keys() #list of remote servers
                for srvIP in servers:
                    if(srvIP in self.servers and self.servers[srvIP].enabledUp and not(enc.code & (enc.STAT_SHUTDOWN | enc.STAT_LIVE | enc.STAT_PAUSED))):
                        self.servers[srvIP].syncUp()
                #end for srv in servers
            #end if sync.dn
        except Exception as e:
            dbg.prn(dbg.ERR|dbg.SMG, "[---]syncmgr.syncAll:", e, sys.exc_traceback.tb_lineno)
    #end syncAll
#end SyncManager

#######################
## utility functions ##
#######################
def serverInfo():
    """ Gets basic server info
        Args:
            none
        Returns:
            (dictionary): 
                master(bool): whether this server is master
                alarms(list): list of device names that triggered an alarm
    """
    return {"master":syncMgr.isMaster,"alarms":srcMgr.alarms()}
def speak(msg):
    """ speaks passed text (only on 192.168.3.100 ip address)"""
    if(pu.io.myIP()=='192.168.3.100'):
        os.system("say -v Veena "+str(msg))
def pxpTTKiller(ttObj={},name=False):
    """ Recursively kills threads in the ttObj """
    dbg.prn(dbg.KLL,"pxpkill: ",name,"...")
    if(type(ttObj) is dict): #the object is a dictionary - go through each element (thread) and kill it
        if(len(ttObj)<1):
            return
        while(len(ttObj)>0):
            key, val = ttObj.popitem()
            pxpTTKiller(val, key)
    elif(type(ttObj) is list): #the object is a list - go through each element (thread) and kill it
        if(len(ttObj)<1):
            return
        for tt in ttObj:
            pxpTTKiller(tt,name)
    else:#the object is a thread object - call the kill function on it
        try:
            ttObj.kill()
            dbg.prn(dbg.KLL, "...killed")
        except Exception as e:
            dbg.prn(dbg.KLL|dbg.ERR, "[---]TTKiller:",e,sys.exc_traceback)
        return

def pxpCleanup(signal=False, frame=False):
    """ Stops all threads and removes them prior to stopping the pxpservice """
    global procMan
    try:
        dbg.prn(dbg.KLL,"terminating services...")
        if(enc.code & (enc.STAT_LIVE | enc.STAT_PAUSED)):
            dbg.prn(dbg.KLL,"stopping live event")
            srcMgr.encCapStop(force=True)
        enc.statusSet(enc.STAT_SHUTDOWN)
        dbg.prn(dbg.KLL,"stopping timers...")
        pxpTTKiller(tmr,"tmr")
        # make sure live555 isn't running
        os.system("killall -9 live555 2>/dev/null &")
        dbg.prn(dbg.KLL,"procMan cleanup... ")
        try:
            if(procMan):
                procMan.pstop(name="live555", async=False)
                del procMan
        except:
            pass
        dbg.prn(dbg.KLL,"terminated!")
    except Exception as e:
        dbg.prn(dbg.KLL|dbg.ERR,"[---]pxpCleanup FAIL?!!!!?!?!", e, sys.exc_traceback.tb_lineno)
#end pxpCleanup

def kickDoge():
    """ Kick the watchdog on each tablet (to make sure the socket does not get reset) """
    # simply add the message to the queue of each tablet
    BBQcopy = copy.deepcopy(globalBBQ)
    for client in BBQcopy:
        if(client[:10]=='127.0.0.1_'):
            return #no doge-kicking on local host
        # client entry in the BBQ list
        clnInfo = BBQcopy[client]
        # commands sent to this client that were not ACK'ed
        myCMDs = clnInfo[0]
        # kick the watchdog only if the queue is empty
        if(len(myCMDs)<=0):
            addMsg(client,"doge")
#end kickDoge


def bbqManage():
    """ Manages socket message queue """
    global globalBBQ, lastStatus
    # get encoder status
    newStatus = enc.code #int(pu.disk.file_get_contents("/tmp/pxpstreamstatus")) #contains status code
    sendStatus = False
    if(newStatus != lastStatus):
        sendStatus = newStatus #encState(pxpStatus)
    lastStatus = newStatus
    now = int(time.time()*1000) #current time in milliseconds
    # go through each sent command and if it wasn't ACK'd in 3 seconds, send it again
    BBQcopy = copy.deepcopy(globalBBQ)
    try:
        for client in BBQcopy:
            try:
                # client entry in the BBQ list
                clnInfo = BBQcopy[client]
                # commands sent to this client that were not ACK'ed
                myCMDs = copy.deepcopy(clnInfo[0])
                if(sendStatus):
                    # globalBBQ[client][1].sendLine(json.dumps({'actions':{'event':'live','status':sendStatus}}))
                    addMsg(client,json.dumps({'actions':{'event':'live','status':sendStatus}}))
                for cmdID in myCMDs:
                    if(globalBBQ[client][2]):
                        # re-send the request
                        globalBBQ[client][1].send(myCMDs[cmdID]['data'])
                        # last sent would be now
                        globalBBQ[client][0][cmdID]['lastSent']=now
                        # increment number of times the request was sent
                        globalBBQ[client][0][cmdID]['timesSent']+=1
                        globalBBQ[client][2]=False
                        break #send only 1 command at a time - sending multiple commands in a short period of time causes collisions                
                    #if sendCmd
                    if(myCMDs[cmdID]['ACK']):
                        # this command was ack'ed - remove it from the queue and send the next one
                        del globalBBQ[client][0][cmdID]
                        globalBBQ[client][2]=True
                    #if (cmd ACK'ed)
                    # remove stale commands
                    # if(globalBBQ[client][0][cmdID]['timesSent']>5):
                    #     # requests that have been sent over 5 times need to be deleted
                    #     del globalBBQ[client][0][cmdID]
                        # if a client did not respond, remove the client
                #for cmd in client
            except Exception as e:
                dbg.prn(dbg.ERR|dbg.BBQ,'[---]bbqManager',e,sys.exc_traceback.tb_lineno)
        #for client in globalBBQ
    except Exception as e:
        dbg.prn(dbg.ERR|dbg.BBQ,'[---]bbqManager',e,sys.exc_traceback.tb_lineno)
#end bbqManage


class proc:
    """ Processor class - manages a specified process (starts, restarts, stops) """
    def __init__(self,cmd,name,devID,keepAlive=False,killIdle=False,forceKill=False,threshold=0):
        """ Initializes the process
            Args:
                cmd(str)        - execute this command to start the process
                name(str)       - process nickname (e.g. segmenter)
                devID(str)      - device id associated with this process (e.g. encoder IP address)
                keepAlive(bool,optional) - restart the process if it's dead. default: False
                killIdle(bool,optional)  - kill the process if it's idle. default: False
                forceKill(bool,optional) - whether to force-kill the process when killing it (e.g. send SIGKILL instead of SIGINT). default: False
                threshold(int,optional) - number of seconds to wait before declaring the process as idle
        """
        self.cmd       = cmd
        self.name      = name
        self.dev       = devID
        self.keepalive = keepAlive
        self.killidle  = killIdle 
        self.forcekill = forceKill
        self.pid       = False    # until the process starts - pid is false
        self.ref       = False    # process reference is also false until it's started
        self.alive     = False    # whether this process is alive or not
        self.cpu       = 0        # cpu usage
        self.run       = False    # process will be killed when this is set to False
        self.killcount = 0        # number of times the process was attempted to stop
        self.threads   = {}       # any timers/timed threads will be stored here - easier to kill when class is destroyed
        self.off       = False    # will be set to true when process is required to stop
        self.threads['manager'] = TimedThread(self._manager,period=10)
        self.threshold = threshold
        self.startIdle = 0 #time when process became idle
    def __del__(self):
        self._cleanup()
    def __repr__(self):
        return "<proc> {name} {dev} ...{cmd}... {keepalive} {forcekill} {killidle}".format(**self.__dict__)
    def start(self):
        """ Starts a process (executes the command assigned to this process) """
        try:
            if(self.off): #the process is stopping, it should not restart
                return False
            # start the process
            if(self.name=='capturez'):#display output in the terminal #DEBUG ONLY#
                ps = sb.Popen(self.cmd.split(' '))
            else:#hide output for all other ffmpeg's/processes
                ps = sb.Popen(self.cmd.split(' '),stderr=FNULL,stdout=FNULL)
            # get its pid
            self.pid=ps.pid
            # dbg.prn(dbg.PPC,"starting: ", self.name, self.pid, "force:", self.forcekill)
            # get the reference to the object (for communicating/killing it later)
            self.ref=ps
            #set these 2 variables to make sure it doesn't get killed by the next manager run
            self.threads[ps.pid]=TimedThread(self._monitor,period=1.5)
            self.alive=True
            self.cpu=100
            self.run = True
            return True
        except Exception as e:
            dbg.prn(dbg.ERR|dbg.PPC,"[---]proc.start: ",e,sys.exc_traceback.tb_lineno)
            return False
    def stop(self,async=True,force=False,end=False):
        """ Stops the running process
            Args:
                async(bool,optional): whether to stop this event in the background. default: True
                force(bool,optional): force-stop the process if true. default: False
                end(bool,optional): permanently end the process (no possibility of restart). default: False
            Returns:
                none
        """
        # dbg.prn(dbg.PPC, "stopping: ", self.name, self.pid, "force:", (force or self.forcekill))
        self.off = end
        self.run = False
        try:
            if(self.off):
                self.threads['manager'].kill()
        except Exception as e:
            dbg.prn(dbg.PPC|dbg.ERR, "[---]proc.stop:",e,sys.exc_traceback.tb_lineno)
        if(force):
            self.forcekill = True
        if(async):
            TimedThread(self._killer)
        else:
            self._killer()
    def restart(self):
        """ Stops the process and immediately restarts it """
        self.stop(async=False) #wait till the command stops
        self.start()
    def _cleanup(self):
        """ Stops the process and removes any running threads"""
        dbg.prn(dbg.PPC, "proc", self.name, "cleanup")
        for thread in self.threads:
            try:#remove any running threads
                dbg.prn(dbg.PPC, "clean ",thread)
                self.threads[thread].kill()
            except Exception as e:
                dbg.prn(dbg.ERR|dbg.PPC, "[---]proc._cleanup",self.name, thread,e)
                pass
    def _monitor(self):
        """ Monitor the process: get its cpu usage, running state """
        try:
            self.alive = psOnID(pid=self.pid) #check if the process is alive
            self.cpu = pu.disk.getCPU(pid=self.pid) #get cpu usage
            if(self.cpu>=0.1):
                self.startIdle = 0 #reset idle timer if the process becomes active
            if((self.cpu<0.1) and (self.threshold>0) and ((not self.startIdle) or (time.time()-self.startIdle)<self.threshold)): #cpu is idle and user set a threshold - need to wait before declaring process as idle
                 #process has recently become idle
                    self.cpu = 1 #fake the cpu usage for an idle process until threshold is reached
                    if(not self.startIdle):
                        self.startIdle = time.time()        
        except Exception as e:
            dbg.prn(dbg.PPC|dbg.ERR,"[---]proc._monitor: ",e,sys.exc_traceback.tb_lineno)
    def _manager(self):
        """ Manage the process: start it if required, restart, stop when idle, etc. """
        if(enc.code & enc.STAT_SHUTDOWN):
            self._cleanup()
        elif(self.run and not self.alive): 
            #this process is not alive, but should be - start it
            self._killer() #stop all the threads (to make sure there's nothing left over when the process re-starts)
            self.start()
        elif(self.run and self.alive and self.cpu<0.1 and self.killidle and self.keepalive):
            #this process is alive but idle and has to be restarted when idle
            self.restart()
        elif(self.run and self.alive and self.cpu<0.1 and self.killidle):
            #this process is idle and has to be stopped (but not restarted)
            self.stop()
    def _killer(self):
        """ Kills the specified process """
        try:
            while psOnID(pid=self.pid):
                if(self.killcount>2): #the process didn't die after 3 attempts - force kill next time
                    self.forcekill = True
                self.killcount += 1
                #try to kill it
                psKill(pid=self.pid,ref=self.ref, force=self.forcekill)
                time.sleep(5) #wait for 1 second between kill attempts
            #end while psOn
            #now the process is dead, kill any associated threads (e.g. monitor, manager)
            if(self.pid in self.threads):
                self.threads[self.pid].kill()
                del self.threads[self.pid]
            self.alive = False
            self.cpu = 0
            self.killcount = 0
            return True
        except Exception as e:
            if(sys and sys.exc_traceback and sys.exc_traceback.tb_lineno):
                errline = sys.exc_traceback.tb_lineno
            else:
                errline = ""
            dbg.prn(dbg.PPC|dbg.ERR,"[---]proc._killer: ",e,errline)
#end class proc

class procmgr:
    """ Process management class """
    def __init__(self):
        self.procs = {} #processes in the system
    def dbgprint(self):
        procs = self.procs.copy()
        if(len(procs)>0):
            dbg.prn(dbg.PCM,"----------------------------------")
            for idx in procs:
                dbg.prn(dbg.PCM,procs[idx].name, procs[idx].alive, procs[idx].cpu, procs[idx].pid, procs[idx].keepalive, procs[idx].run, procs[idx].dev)
            dbg.prn(dbg.PCM,"----------------------------------")
    def palive(self,name,devID=False):
        """ Determine whether a process is alive 
            Args:
                name(str): name of the process
                devID(str,optional): id of the device this process belongs to. if unspecified, return the first process matching the name (default: False)
            Returns:
                (bool): whether the process is alive
        """
        procs = self.procs.copy()
        for idx in procs:
            proc = procs[idx]
            if(proc.name==name):
                if(not devID or proc.dev==devID): #either devID matches or devID wasn't specified - just kill processes matching the name
                    return proc.alive
        return False
    def padd(self,cmd,name,devID,keepAlive=False,killIdle=False,forceKill=False,threshold=0):
        """ Add a new process (command) to the process manager and try to start it
            Args:
                cmd (str): command to execute in the terminal
                name (str): what to name the process for later reference
                devID (str): associate the process with this device ID (usually IP address)
                keepAlive (bool,optional): keep the process alive (i.e. if it dies, restart it)
                killIdle (bool,optional): kill if this process stalls (low cpu usage or gets zombiefied)
                forceKill (bool,optional): when stopping this process, force-kill it right away. default: False
                threshol (int,optional): number of seconds to wait before declaring the process as idle

            Returns:
                bool: True if the command was started successfully, False if an error occurred 
        """
        try:
            idx = 0 #the index of the new process
            procs = self.procs.copy()
            #find the next available index
            for pidx in procs:
                if(pidx>=idx):
                    idx = pidx+1
            self.procs[idx] = proc(cmd,name,devID,keepAlive,killIdle,forceKill,threshold)
            dbg.prn(dbg.PCM, " added:::::::::::::::: ",idx, self.procs[idx])
            # start the process as soon as it's added
            if(self.procs[idx].start()):
                return True
            #could not start stream - no need to add it to the list
            del self.procs[idx]
            return False
        except Exception as e:
            dbg.prn(dbg.PCM|dbg.ERR, "[---]padd:",e)
            return False
    #end padd
    def pexists(self,name,devID=False):
        """ Determine whether a process exists (stopped, idle, but present in the list)
        Args:
            name (str): name of the process
            devID (str, optional): id of the device this process belongs to. if unspecified, return the first process matching the name. default: False

        Returns:
            bool: True if the specified process exists, False otherwise.
        """
        procs = self.procs.copy()
        for idx in procs:
            proc = procs[idx]
            if(proc.name==name):
                if(not devID or proc.dev==devID): #either devID matches or devID wasn't specified - just kill processes matching the name
                    return True
        return False
    #end pexists
    def premove(self,procidx):
        """ Remove process from the processes list """
        if(procidx in self.procs):
            del self.procs[procidx]
    #end premove
    # stop a specified process
    def pstop(self,name=False, devID=False,force=False,remove=True,async=True,restart=False):
        """ Stop a specified process. NB: either name or devID must be specified.

        Args:
            name (str, optional): name of the process to stop. if unspecified, all processes from specified device will be stopped. default:False
            devID (str, optional): id of the device this process belongs to. if unspecified, stop the process with this name on every device. default: False
            force (bool, optional): force-kill the process. default: False
            remove (bool, optional): remove this process from the process manager's list. default: True

        Returns:
            None
        """
        import inspect
        if(not (name or devID)): #can't stop a process when neither name nor devID were specified
            return
        dbg.prn(dbg.PCM, "killer hierarchy:",inspect.stack()[1][3])
        procs = self.procs.copy()
        for idx in procs:
            proc = procs[idx]
            if(((not name) or (proc.name==name)) and ((not devID) or (proc.dev==devID))):
                if(restart):
                    proc.restart()#this operation is synchronous
                else:#just stop the process
                    proc.stop(async=async,force=force, end=remove) #if removing the process, do not allow it to be restarted
                    if(remove): #only delete the process from the list if user specifically requested it
                        if(not 'killers' in tmr):
                            tmr['killers'] = []
                        tmr['killers'].append(TimedThread(self._stopwait,(idx,)))
                #end if restart...else
            #end if name or devID
    def pstart(self,name,devID=False):
        """ Start a specified process (usually used for resuming an existing process) """
        procs = self.procs.copy()
        for idx in procs:
            proc = procs[idx]
            if(proc.name==name):
                if(not devID or proc.dev==devID): #either devID matches or devID wasn't specified - just start all processes matching the name
                    proc.start()
    def _stopwait(self,idx):
        """ Waits until the process is stopped, then removes it"""
        while(psOnID(self.procs[idx].pid)):
            time.sleep(1)
        del self.procs[idx]
    def __del__(self):
        try:
            for idx in self.procs:
                self.procs[idx].stop()
                del self.procs[idx]
        except:
            pass
#end procmgr CLASS

#finds a gap in the sorted list of integers
# this algorithm is slower than sequential search for arrays of size < 8
# def gap(arr,first,last):
#     if(len(arr)<1)
#         return 0
#     if(first>=last):
#         if(first>=arr[first]):
#             return last+1
#         return last    
#     med = (last+first)>>1 #faster than divide by 2
#     if(med<arr[med]):
#         return gap(arr,first,med)
#     return gap(arr,med+1,last)
# end gap
# arr = [0,1,3,5,10]
# nextGap = gap(arr,0,count(arr)-1)


def psKill(pid=0,pgid=0,ref=False,timeout=4,force=False):
    """ attempts to kill a process based on PID (sends SIGKILL, equivalent to -9)
        Args:
            pid(int,optional) - process ID (either PID or PGID must be specified)
            pgid(int,optional) - process group ID
            ref(obj,optional) - reference to the Popen process (used to .communicate() - should prevent zombies)
            timeout(int,optional) - timeout in seconds how long to try and kill the process
            force(bool,optional) - whether to force exit a process (sends KILL - non-catchable, non-ignorable kill)
    """
    if(not(pid or pgid)):
        return #one must be specified 
    #this function is required to enable proper .communicate with ref - in case it stalls, it doesn't hang entire function
    def comm(ref):
        try:
            # ref.communicate('q')
            ref.communicate('')
        except:
            pass
    # timeout += time.time()
    #continue trying to kill it until it's dead or timeout reached
    # while(psOnID(pid=pid,pgid=pgid) and ((timeout-time.time())>0)):
    try:
        if(ref):#this is the proper way to stop a process opened with Popen
            if(force):
                ref.kill()
            else:
                os.system("kill -15 "+str(pid))
            if(not 'comm' in tmr):
                tmr['comm'] = {}
            tmr['comm'][pid] = TimedThread(comm,(ref,)) #same as ref.communicate(), but it won't cause a problem if communicate() stalls
            # if(not force):
                # time.sleep(2)
        else:#no reference was specified - just send the signal to the pid
            if(force): #forcing a quit - send kill (-9)
                sigToSend = signal.SIGKILL
            else:#gentle quit, sigint
                sigToSend = signal.SIGINT
            if(pgid):#for group kills, signal needs to be sent to the entire group (parent+children) otherwise there will be zombies
                os.killpg(pgid, sigToSend)
            elif(pid):
                os.kill(pid,sigToSend)
        # time.sleep(1)
    except Exception as e:
        dbg.prn(dbg.PCM|dbg.ERR,"kill err::::::::::::::::::",e,sys.exc_traceback.tb_lineno)

def psOnID(pid=0,pgid=0):
    """ Checks if a process is active based on pid (or gid)
        Args:
            pid(int,optional): process id. default: 0. NB: one of pid or pgid must be specified.
            pgid(int,optional): process group id. default: 0. NB: one of pid or pgid must be specified.
    """
    try:
        if(pid):
            p = psutil.Process(pid)
        else:#need to change this to look for all processes with this pgid
            p = psutil.Process(pgid)
        try:#for python 2.7.2 psutil.status is a method
            pstatus = p.status()
        except:#in python v2.7.5 or greater the psutil.status is a property, not a method
            pstatus = p.status
        psOn = p.is_running() and pstatus != psutil.STATUS_ZOMBIE
        return psOn
    except:
        return False
    # cmd = "kill -0 "+str(pid) #"ps -A | pgrep "+process+" > /dev/null"
    # #result of the cmd is 0 if it was successful (i.e. the process exists)
    # return os.system(cmd)==0

def addMsg(client,msg,c=False):
    """ Adds message for a client to the BBQ
        Args:
            client(str): id of the client (ip + port)
            msg(str): message to send
            c(obj): reference to the client variable (used to add them to the queue for the first time)
        Returns:
            none
    """    
    global globalBBQ
    # get timestamp for every broadcast
    timestamp = int(time.time()*1000)
    # add him to the BBQ if he's not there already
    if(c and not client in globalBBQ):
        globalBBQ[client] = [{},c,True]
    # send the data to the client - do this in the BBQ manager
    # globalBBQ[client][1].sendLine(str(timestamp)+"|"+msg)
    # add the data to the BBQ for this client
    globalBBQ[client][0][timestamp]={'ACK':0,'timesSent':0,'lastSent':(timestamp-3000),'data':str(timestamp)+"|"+msg}

def DataHandler(data,addr):
    """ Processs the data received from the socket. Executes the command or passes it to the commander.
        Commands available so far:
            RMF - remove file
            RMD - remove directory

            BKP - backup event (manual request)
            RRE - restore event 
            CPS - request status of the backup or restore copy process
            LBP - list events that are being backed up
            LBE - list events that were backed up

            LOG - set writing on/off
            LVL - set log level

            CML - get camera list
            SNF - get server info

            ACK - command acknowledgement receipt (used for socket communication)

            BTR - change bitrate
            
            PSE - pause live encode
            RSM - resume live encode
            STP - stop live encode 
            STR - start live encode
        Args:
            data(str): string received from the socket
            addr(list): client address (ip,port)
        Returns:
            (bool): whether the command was processed successfully
    """
    try:
        # client IP address
        senderIP = str(addr[0])
        # client port
        senderPT = str(addr[1])
        dbg.prn(dbg.DHL,"............... BBQ GOT: ",data,' FROM ',senderIP,':',senderPT)
        #if it was a command, it'll be split into segments by vertical bars
        dataParts = data.split('|')
        # if(senderIP!="127.0.0.1"):
            # dbgLog("got data: "+data+" from: "+senderIP)
        if(len(dataParts)>0):
            # this is a service request
            if(senderIP=="127.0.0.1"):
                nobroadcast = False #local server allows broadcasting
                # these actions can only be sent from the local server - do not broadcast these
                if(dataParts[0]=='RMF' or dataParts[0]=='RMD' or dataParts[0]=='BTR' or dataParts[0]=='BKP' or dataParts[0]=='RRE' or dataParts[0]=='LVL' or dataParts[0]=='LOG'):
                    # remove file, remove directory, set bitrate or backup event - these don't need to go to the commander queue - they're non-blocking and independent of one another
                    nobroadcast = True
                    encControl.enq(data,bypass=True)
                if(dataParts[0]=='STR' or dataParts[0]=='STP' or dataParts[0]=='PSE' or dataParts[0]=='RSM'):
                    #start encode, stop encode, pause encode, resume encode
                    nobroadcast = True
                    encControl.enq(data)
                if(dataParts[0]=='LBE'): #list events that are backed up on external storage (available for restore)
                    return backuper.archiveList()
                if(dataParts[0]=='SNF'):# server info
                    return serverInfo()
                if(dataParts[0]=='CML'): # camera list
                    return srcMgr.toJSON()
                if(dataParts[0]=='LBP'): # list events that are in the process of backing up (do not yet fully exist on local machine)
                    return backuper.list()
                if(len(dataParts)<2):
                    dataParts[1]=False
                if(dataParts[0]=='CPS'): # copy status request
                    nobroadcast = True
                    return backuper.status(dataParts[1])
            #end if sender=127.0.0.1
            if(dataParts[0]=='ACK'): # acknowledgement of message receipt
                nobroadcast = True
                cmdID = dataParts[1].strip() #the ack's come in format ACK|<message_id>
                # broadcast acknowledgment received - remove that request from the queue of sent events
                try:
                    # del globalBBQ[senderIP+"_"+senderPT][0][int(cmdID)]
                    globalBBQ[senderIP+"_"+senderPT][0][int(cmdID)]['ACK']=1
                except Exception as e:
                    pass
                return False          
        #if len(dataParts)>0
        ###########################################
        #             broadcasting                #
        ###########################################
        if(nobroadcast or senderIP!="127.0.0.1"): #only local host can broadcast messages
            return False
        BBQcopy = copy.deepcopy(globalBBQ)
        for clientID in BBQcopy:
            try:
                # add message to the queue (and send it)
                addMsg(clientID,data)
            except Exception as e:
                pass
        return False
    except:
        pass
    return False

def SockHandler(sock,addr):
    """ Listens for connections from specified sockets"""
    try:
        while 1:
            data = sock.recv(4096)
            if not data:#exit when client disconnects
                break
            # got some data
            result = DataHandler(data,addr)
            if(result or (type(result) is dict) or (type(result) is list)):
                try:
                    rspString = json.dumps(result)
                except Exception as e:
                    dbg.prn(dbg.SHL|dbg.ERR, "[---]sockhandler",e)
                    rspString = result
                sock.send(rspString)
            # clientsock.send(msg)
        #client disconnected
    except Exception as e:
        dbg.prn(dbg.ERR|dbg.SHL, "[---]SockHandler,", e, sys.exc_traceback.tb_lineno)
    clientID = str(addr[0])+"_"+str(addr[1])
    try:
        del globalBBQ[clientID]
    except Exception as e:
        pass
    dbg.prn(dbg.SHL,"disconnected: ",clientID)
    sock.close()
    try:
        #remove the client from the timers (to prevent memory overflows)
        clientID = str(addr[0])+"_"+str(addr[1])
        if(clientID in tmr['clients']):
            del tmr['clients'][clientID]
    except:
        pass
####################################################################################

# devices that will be discovered on this system
devEnabled = {
     "td":{ #teradek cube
         "class":encTeradek
    }
    # ,"mt":{ #matrox monarch
    #     "class":encMatrox
    # }
    # ,"ph":{ #pivothead
    #     "class":encPivothead
    # }
    ,"sn":{ #sony SNC
        "class":encSonySNC
    }
    # ,"db":{
    #     "class":encDebug
    # }
}
tmr = {}
tmr['misc'] = [] #contains miscellaneous threads (that might have been killed already or still alive but useless)
# initialize logging class
dbg = debugLogger()
if __name__=='__main__': # will enter here only when executing this file (if it is included from another process, this IF condition will be false)
    try:
        # ensure there's only 1 instance of this script running
        procs = pu.disk.psGet("pxpservice.py")
        enc = False
        if(len(procs)>1):#this instance isn't the only one of this script
            dbg.prn(dbg.MN, "this script is already running")
            sys.exit()
        else:
            dbg.prn(dbg.MN, procs)
            dbg.prn(dbg.MN, "first instance of pxpservice")
        enc = encoderStatus()
        encControl = commander() #encoder control commands go through here (start/stop/pause/resume)

        dbg.prn(dbg.MN,"---APP START--")
        procMan = procmgr()
        try:
            # remove old encoders from the list, the file will be re-created when the service finds encoders
            os.remove(c.devCamList)
        except:
            pass
        os.system("killall -9 live555 2>/dev/null &") #make sure there's no other proxy server
        os.system("killall -9 "+c.segname+" 2>/dev/null")
        os.system("killall -9 "+c.ffname+" 2>/dev/null")
        # set up messages(tags) queue manager
        # this manages all socket communication (e.g. broadcasting new tags, sennds start/stop/pause/resume messages to tablets)
        tmr['BBQ']          = TimedThread(bbqManage,period=0.1)

        # start a watchdog timer
        # sends a periodic 'kick' to the watchdoge on the clients - to make sure socket is still alive
        tmr['dogeKick']     = TimedThread(kickDoge,period=30)

        # register pxp on bonjour service
        tmr['bonjour']      = TimedThread(pu.bonjour.publish,params=("_pxp._udp",pu.io.myName()+' - '+ hex(getmac())[2:],80),period=10)

        syncMgr = SyncManager()

        srcMgr = sourceManager(devEnabled)

        # start deleter timer (deletes files that are not needed/old/etc.)
        tmr['delFiles']     = TimedThread(deleteFiles,period=5)

        tmr['cleanupEvts']  = TimedThread(removeOldEvents,period=10)
        #start the threads for forwarding the blue screen to udp ports (will not forward if everything is working properly)


        #register what happens on ^C:
        signal.signal(signal.SIGINT, pxpCleanup)
        tmr['dbgprint']     = TimedThread(procMan.dbgprint,period=5)
        # writes out the pxp encoder status to file (for others to use)
        tmr['pxpStatusSet'] = TimedThread(enc.statusWrite,period=0.5)
        # when clients connect, their threads will sit here:
        tmr['clients']      = {}

        backuper = backupManager()
        # clean up any left-over live events (if user yanked the power cord)
        oldLiveCleanup()

        dbg.prn(dbg.MN,"main...")
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        dbg.prn(dbg.MN,"got socket.")
        s.bind(("127.0.0.1",sockInPort))
        dbg.prn(dbg.MN,"bind")
        s.listen(2)
        dbg.prn(dbg.MN,"listen")
        appRunning = True
        while appRunning:
            try:
                # dbg.prn(dbg.MN,"LISTENING ON "+str(sockInPort))
                sock, addr = s.accept()
                #will get here as soon as there's a connection
                clientID = str(addr[0])+"_"+str(addr[1])
                # dbg.prn(dbg.MN,"connected: "+clientID)
                #add new client to the list
                globalBBQ[clientID] = [{},sock,True]
                #client connected:
                tmr['clients'][clientID] = TimedThread(SockHandler, (sock, addr))
            except KeyboardInterrupt:
                pxpCleanup()
                appRunning = False
                break
            except Exception as e:
                appRunning = False
                break
                pass
    except Exception as e:
        pxpCleanup()
        appRunning = False
        dbg.prn(dbg.ERR|dbg.MN, "MAIN ERRRRR????????? ",e)
    dbg.prn(dbg.MN,'---APP STOP---')
#emd if main