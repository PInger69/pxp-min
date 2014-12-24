#!/usr/bin/python
from tendo import singleton
from datetime import datetime as dt
from uuid import getnode as getmac
from pxputil import TimedThread
from urlparse import parse_qsl
import camera, constants as c, copy, json, os, psutil, pxp, pxputil as pu, signal, socket, subprocess as sb, time
import sys, shutil, hashlib, re

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

    #these properties define which of the above groups will be logged and whether the log file will written
    LVL            = ALL & ~(SHL|DHL|ECN) #ERR|KLL|MN|TST|PCM|SRC|SRM #print level (32-bit integer)
    LOG            = 0      #whether to log whatever is being printed to file

    def __init__(self):
        super(debugLogger, self).__init__()      
    def setLogLevel(self, level):
        """ set the log level"""
        try:
            self.LVL = int(level)
        except Exception, e:
            pass
    def setLog(self,log):
        """ set whether the log will be written to the file or not"""
        try:
            self.LOG = int(log)
            self.prn(self.DBG,"writing to log file set:")
        except Exception, e:
            pass
    def prn(self, kind, *arguments, **keywords):
        if(not (kind & self.LVL)): #only print one type of event
            return
        # print arguments
        print dt.fromtimestamp(time.time()).strftime("%Y-%m-%d %H:%M:%S.%f"),':',(' '.join(map(str, (arguments)))), '[[written:',self.LOG,']]'
        if(self.LOG):
            try:
                # if the file size is over 1gb, delete it
                logFile = c.logFile
                if(os.path.exists(logFile) and os.stat(logFile).st_size>=(1<<30)):
                    os.remove(logFile)
                with open(logFile,"a") as fp:
                    fp.write(dt.fromtimestamp(time.time()).strftime("%Y-%m-%d %H:%M:%S.%f"))
                    fp.write(' '.join(map(str, (arguments))))
                    fp.write("\n")
            except Exception as e:
                print "[---]prn:",e, sys.exc_traceback.tb_lineno
    #end prn
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
    def __init__(self, hid, priority, dataOnly=False, auto=False, restore=False, backupPath = False, remoteParams = False):
        super(backupEvent, self).__init__()
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
        self.remote = remoteParams
    def cancel(self):
        # event is still copying - send a kill signal to it
        try:
            if(self.status & (self.STAT_START)): #the event didn't finish copying
                self.kill = True
            #end if bkp in tmr
        except Exception as e:
            dbg.prn(dbg.BKP|dbg.ERR,"[---]bkp.start:",e,sys.exc_traceback.tb_lineno)
        #end ifself.done
    #end cancel
    def monitor(self):
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
        if(self.remote):
            # this is a remote event, in order to back it up (or 'sync' it), 
            # the event has to be downloaded and added to the local database (if it doesn't exist yet)
            self.startRemote()
        elif(self.restore):
            self.startRestore()
        else:
            self.startBackup()
    def startBackup(self):
        # get info about the event
        try:
            dbg.prn(dbg.BKP, "starting local backup?????")
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
    def startRemote(self):
        """ start remote sync (copying files from a remote location to local server) """
        # find path to the event.json
        try:
            jsonPath = False
            self.status = self.STAT_START
            dbg.prn(dbg.BKP,"starting remote backup")
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
        return [self.status, self.copied*100/self.total]
    #end statusFull
    def treeCopy(self,src,dst,topLevel = True):
        """ recursively copies a directory tree from src to dst 
            @param (str) src - full path to the source directory
            @param (str) dst - full path to the destination directory
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
    def webCopy(self,url,fileList,dst):
        """ downloads files from the specified url and saves them to the local directory 
        @param (str) url - base url of the server where to download files
        @param (list) fileList - list of files with their path relative to the 'url'
        @param (str) dst - destination directory on the local drive, where to save files
        """
        try:
            # this is the directory where the event will be stored
            fileHome = dst[dst.rfind('/'):]
            dbg.prn(dbg.BKP,"fileHome:",fileHome)
            for item in fileList:
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
    """ backup events manager backupManager """
    def __init__(self):
        super(backupManager, self).__init__()
        self.lastActive = int(time.time())
        self.events = { }  # dictionary of event instances (to be backed up)
        self.completed = { } #dictionary of events that have been backed up
        self.priorities = { } #dictionary of lists of events (i.e. all events are grouped by their priority here)
        self.current = False #hid of the currently executing backup
        self.archivedEvents = False
        # start backup manager process
        tmr['backupmgr'] = TimedThread(self.process,period=3) #
        tmr['autobackp'] = TimedThread(self.autobackup,period=600) #run auto backup once every 10 minutes
    def add(self, hid, priority=0, dataOnly=False,auto = False, restore=False, remoteParams = False):
        """ add an event to the list of events to be backed up """
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
            self.events[hid] = backupEvent(hid, priority, dataOnly, auto, restore, backupPath, remoteParams)
            if(not (priority in self.priorities)): #there are no events with this priority yet - add the priority
                self.priorities[priority] = [ ]
            self.priorities[priority].append(hid) #add event to the list of events with the same priority
        except Exception as e:
            dbg.prn(dbg.BKP|dbg.ERR,"[---]bkpmgr.add: ", e,sys.exc_traceback.tb_lineno)
    def archiveList(self):
        """ get a list of all archived events with their paths """
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
        """ automatically backs up all events to the usb drive (or sd card) """
        try:
            if((int(time.time()) - self.lastActive)<10): #has been idle for less than 10 seconds, wait some more
                # the machine is busy (there's most likely a live game going on) make sure there are no events being backed up right now
                if(self.current): 
                    self.stop(stopAll = True)
                return
            # check if there is a live event
            if(os.path.exists(c.wwwroot+'live')): #there is a live event - wait until it's done to back up
                self.lastActive = int(time.time())
                return
            if(len(self.events)>0): #events are being backed up - wait until that's done to check for new events
                return
            # system is idle
            # get the device that has autobackup folder:
            drives = pu.disk.list()
            backupDrive = False
            # look for which one to back up to
            for drive in drives:
                if(not os.path.exists(drive+backupEvent.autoDir)): #this is not the auto-backup for pxp
                    continue
                backupDrive = drive.decode('UTF-8')
            if(not backupDrive):
                return #did not find an auto-backup device
            # get all events in the system
            elist = pxp._listEvents(showDeleted=False)
            # go through all events that exist and verify that they're identical on the backup device
            for event in elist:
                if(not('datapath' in event)):
                    continue #this event does not have a folder
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
                    self.add(event['hid'],auto=True)
        except Exception as e:
            dbg.prn(dbg.ERR|dbg.BKP,"[---]bkpmgr.autobackup",e,sys.exc_traceback.tb_lineno)
    def list(self,incomplete=False):
        """ lists HIDs of all events that are being backed up 
        @incomplete (bool) - when true, lists all events (including ones being backed up to this encoder, i.e. remote backups and restores)
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
        """ stop copying current event 
            @param bool stopAll - stop copying current event and clear the queue (no other events will be copied)
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
    try:
        dbg.prn(dbg.ECN,"deleteFiles called")
        # if there is a deletion in progress - let it finish
        if (pu.disk.psOn("rm -f") or pu.disk.psOn("rm -rf") or pu.disk.psOn("xargs -0 rm") or not (enc.code & (enc.STAT_READY | enc.STAT_NOCAM))):
            return
        # check how big is the log file
        if(os.stat(c.logFile).st_size>c.maxLogSize):
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

##################################
### pxpservice control classes ###
##################################

class commander:
    """ server command manager """
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
            @param cmd - command to add. command is vertical bar-delimeted with parameters
            @param sync(True) - whether the command is synchronous or not. ASYNC commands will have to reset commander.status manually
            @param bypass(False) - when True, the command will be executed immediately bypassing the queue
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
        """ removes the next command form the queue and executes it """
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
        """ executes a given command """
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
            if(dataParts[0]=='BKP'): #backup event
                backuper.add(hid=dataParts[1],priority=5)
            if(dataParts[0]=='RRE'): #restore event 
                backuper.add(hid=dataParts[1],priority=10,restore=True) #restoring events have higher priority over backups (to prevent restore-backup of the same event)
        except Exception as e:
            dbg.prn(dbg.CMD|dbg.ERR,"[---]cmd._exc", e, sys.exc_traceback.tb_lineno)
            return False
    #end exc
    def _mgr(self):
        """ status manager - periodically checks if the commander status is ready, runs .deq when it is """
        if(self.status):
            return
        # commander is not busy
        self._deq()
    #end mgr
#end commander

class encoderStatus:
    """
    encoder status/configuration class
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
    def statusRead(self):
        """ reads status from the disk into a json dictionary """
        txtStatus = pu.disk.file_get_contents(c.encStatFile)
        jsonStatus = json.loads(txtStatus)
        # self.
    #end statusRead
    def statusSet(self,statusBit,autoWrite=True, overwrite=True):
        """Set a new encoder status code and appropriate status text 
        statusBit - new status of the encoder to set (add or overwrite)
        autoWrite - (optional) write the status to disk right away (default=True)
        overwrite - (optional) overwrite the current status with the new one, if False, status will be added (all statuses are bit-shifted)
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
        """ return the text corresponding to the status code """
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
        statusBit - which bit to unset (set to 0)
        autoWrite - (optional) write the status to disk right away (default=True)
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
        """ writes out current status to disk """
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
    """ base class for an encoder"""
    def __init__(self, ip):
        """ initialize the class 
        @param (str) ip - ip address of the device. used to set/retreive its parameters
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
    def __repr__(self):
        return "<encDevice> ip:{ip} fr:{framerate} br:{bitrate} url:{rtspURL} init:{initialized} on:{isOn}".format(**self.__dict__)
    # create ffmpeg command that captures the rtsp stream
    def buildCapCmd(self, camURL, chkPRT, camMP4, camHLS):
        # if ther's a problem, try adding -rtsp_transport udp before -i
        # liquid image EGO camerea requires -fflags +genpts otherwise you get "first pts value must be set" error
        # return c.ffbin+" -fflags +genpts -rtsp_transport tcp -i "+camURL+" -codec copy -f h264 udp://127.0.0.1:"+chkPRT+" -codec copy -f h264 udp://127.0.0.1:"+camMP4+" -codec copy -f mpegts udp://127.0.0.1:"+camHLS
        return c.ffbin+" -rtsp_transport tcp -i "+camURL+" -codec copy -f h264 udp://127.0.0.1:"+str(chkPRT)+" -codec copy -f h264 udp://127.0.0.1:"+str(camMP4)+" -codec copy -f mpegts udp://127.0.0.1:"+str(camHLS)
    #end encBuildCmd
    def setBitrate(self, bitrate):
        pass
    def setResolution(self, resolution):
        pass
    def setFramerate(self, framerate):
        pass
    def monitor(self):
        pass
    def update(self):
        pass
#end encDevice class

class encTeradek(encDevice):
    """ teradek device management class """
    def __init__(self, ip=False):
        if(ip):
            super(encTeradek,self).__init__(ip)
            self.ccBitrate      = True # can change bitrate
            self.ccFramerate    = True # can change framerate
            self.ccResolution   = True # can change resolution
            self.tdSession      = None # reference to the login session on the teradek
    def discover(self, callback):
        """ find any new devices. callback is called when a device is found """
        def discovered(results):
            recs = pu.bonjour.parseRecord(results['txtRecord'])
            output = {}
            # url to the stream, consists of:
            # 'sm' - streaming method/protocol (e.g. rtsp)
            # ipAddr - ip address of the encoder (e.g. 192.168.1.100)
            # strport - port of the stream (e.g. 554)
            # 'sn' - stream name (e.g. stream1)
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
            callback(output)
        #end discovered
        pu.bonjour.discover(regtype="_tdstream._tcp",callback=discovered)
    #end discover
    def getParam(self, response,parameter):
        """ extracts a specified paramater from the response string and gets its value.
            function assumes response in this format:
            VideoInput.Info.1.resolution = 720p60
            VideoEncoder.Settings.1.framerate = 30
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
        """ login to the device and save session """
        url = "http://"+self.ip+"/cgi-bin/api.cgi"
        #attempt to login
        response = pu.io.url(url+"?command=login&user=admin&passwd=admin",timeout=15)
        # get session id
        if(not response):
            return False
        response = response.strip().split('=')
        if(response[0].strip().lower()=='session' and len(response)>1):#login successful
            self.tdSession = response[1].strip() #extract the id
        else:#could not log in - probably someone changed username/password
            return False
    #end login
    def setBitrate(self, bitrate):
        """ bitrate is in kbps """
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
        """ checks parameters of the teradek cube """
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
                self.tdSession = None
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
    """ matrox device management class """
    def __init__(self, ip=False):
        if(ip):
            super(encMatrox,self).__init__(ip)
    def discover(self, callback):
        """ find any new devices. callback is called when a device is found """
        try:
            if(enc.code & enc.STAT_SHUTDOWN):
                return
            #the Search Target for monarch is:
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
                            outputs = {}
                            outputs['ip'] = devIP
                            outputs['type'] = 'mt_monarch'
                            outputs['url'] = params['rtsp_url']
                            outputs['port'] = params['rtsp_port']
                            callback(outputs)
                    except Exception as e: #may fail if the device is invalid or doesn't have required attributes
                        dbg.prn(dbg.MTX|dbg.ERR, "[---]encMatrox.discover",e, sys.exc_traceback.tb_lineno)
                #end for devLoc in monarchs
            #end if monarchs>0
            else:
                dbg.prn(dbg.MTX,"not found any monarchs")
        except Exception as e:
            dbg.prn(dbg.MTX|dbg.ERR,"[---]encMatrox.discover",e, sys.exc_traceback.tb_lineno)
    def getParams(self,ip=False):
        """ gets parameters from a matrox monarch device (using the status page for now, until they release the API)
        """
        params = {
            "rtsp_url"          : False,
            "rtsp_port"         : False,
            "inputResolution"   : False,
            "streamResolution"  : False,
            "streamFramerate"   : False,
            "streamBitrate"     : False
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
        except Exception, e:
            dbg.prn(dbg.MTX|dbg.ERR,"[---]matrox.getParams",e,sys.exc_traceback.tb_lineno)
        dbg.prn(dbg.MTX,params)
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
    def update(self):
        params = self.getParams()
        dbg.prn(dbg.MTX, params, "mt.update")
        if(params):
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
    """ pivothead glasses encoder management class """
    def __init__(self, ip=False):
        if(ip):
            super(encPivothead,self).__init__(ip)
    def discover(self, callback):
        """ find any new devices. callback is called when a device is found """
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
            callback(output)
        #end discovered
        pu.bonjour.discover(regtype="_pxpglass._udp",callback=discovered)
    def update(self):
        self.isCamera = True #when the device is found, assume glasses are present - need to make a more robust verification (change pxpinit.py on the glasses pi)
#end encPivothead

class encSonySNC(encDevice):
    """ Sony SNC device management class """
    def __init__(self, ip=False):
        if(ip):
            super(encSonySNC,self).__init__(ip)
            self.ccBitrate      = True # can change bitrate
    def discover(self, callback):
        """ find any new devices. callback is called when a device is found """
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
                            outputs = {}
                            outputs['ip'] = devIP
                            outputs['type'] = 'sn_snc'
                            outputs['url'] = params['rtsp_url']
                            outputs['port'] = params['rtsp_port']
                            callback(outputs)
                    except Exception as e: #may fail if the device is invalid or doesn't have required attributes
                        dbg.prn(dbg.SNC|dbg.ERR, "[---]encSonySNC.discover",e, sys.exc_traceback.tb_lineno)
                #end for devLoc in devs
            #end if devs>0
            else:
                dbg.prn(dbg.SNC,"not found any SNCs")
        except Exception as e:
            dbg.prn(dbg.SNC|dbg.ERR,"[---]encSonySNC.discover",e, sys.exc_traceback.tb_lineno)
    def getParams(self,ip=False):
        """ gets parameters from a SNC device
        """
        params = {
            "rtsp_url"          : False,
            "rtsp_port"         : False,
            "inputResolution"   : False,
            "streamResolution"  : False,
            "streamFramerate"   : False,
            "streamBitrate"     : False
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
        try:
            result = False
            result = pu.io.url("http://"+self.ip+"/command/camera.cgi?CBR=on")
            result = result and pu.io.url("http://"+self.ip+"/command/camera.cgi?BitRate="+bitrate)
            return result
        except Exception as e:
            dbg.prn(dbg.ERR|dbg.SNC,"[---]snc.setBitrate:", e, sys.exc_traceback.tb_lineno)
        return result
    def setFramerate(self):
        pass
    def setResolution(self):
        pass
    def update(self):
        params = self.getParams()
        # dbg.prn(dbg.SNC, params, "snc.update")
        if(params):
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
#end encSonySNC

class encDebug(encDevice):
    """ a test device class at the moment used for Liquid Image EGO"""
    def __init__(self, ip=False):
        if(ip):
            super(encDebug,self).__init__(ip)
    def buildCapCmd(self, camURL, chkPRT, camMP4, camHLS): #override the function for the EGO camera
        # if ther's a problem, try adding -rtsp_transport udp before -i
        # liquid image EGO camerea requires -fflags +genpts otherwise you get "first pts value must be set" error and won't start ffmpeg
        return c.ffbin+" -fflags +genpts -rtsp_transport tcp -i "+camURL+" -codec copy -f h264 udp://127.0.0.1:"+chkPRT+" -codec copy -f h264 udp://127.0.0.1:"+camMP4+" -codec copy -f mpegts udp://127.0.0.1:"+camHLS
        # return c.ffbin+" -rtsp_transport tcp -i "+camURL+" -codec copy -f h264 udp://127.0.0.1:"+chkPRT+" -codec copy -f h264 udp://127.0.0.1:"+camMP4+" -codec copy -f mpegts udp://127.0.0.1:"+camHLS
    #end encBuildCmd
    def discover(self, callback):
        """ find any new devices. callback is called when a device is found """
        try:
            if(enc.code & enc.STAT_SHUTDOWN):
                return
            devIP = "192.168.42.1"
            response = pu.io.url("http://"+devIP+"/setting/cgi-bin/fd_control_client?func=fd_get_camera_info")
            if(response and response.find('EGO')>0): #found LiquidImage EGO camera
                outputs = {}
                outputs['ip'] = devIP
                outputs['type'] = 'db_tst'
                outputs['url'] = "rtsp://"+devIP+"/AmbaStreamTest"
                outputs['port'] = 554
                callback(outputs)
            else:
                dbg.prn(dbg.TST,"did not find any debug devices")
        except Exception as e:
            dbg.prn(dbg.TST|dbg.ERR,"[---]encDebug.discover",e, sys.exc_traceback.tb_lineno)
    def update(self):
        devIP = "192.168.42.1"
        response = pu.io.url("http://"+devIP+"/setting/cgi-bin/fd_control_client?func=fd_get_camera_info")
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
    """ defines a video source """
    def __init__(self,ip, encType, ports={}, url=False, preview=False):
        """ create a new video source
        @param (str)    ip      - ip address of the source (used for checking if the device is alive)
        @param (dict)   ports   - dictionary of ports used for this source: 
                                    mp4 - udp port where ffmpeg that records mp4 file receives data, 
                                    hls - udp port where m3u8 segmenter receives MPEG-TS data, 
                                    chk - udp port that is used to check whether packets are coming in, 
                                    rtp - port used to connect to the rtsp server (for source validation)
        @param (str)    encType - type of source/encoder (e.g. td_cube, ph_glass, mt_monarch)
        @param (str)    url     - rtsp source url (must specify url or preview)
        @param (str)    preview - url of the preview rtp stream (must specify url or preview)
        """
        try:
            self.isData         = False # video data present (accessible through RTSP)
            self.isUsed         = True  # use this source when starting a live event
            self.isEncoding     = False # set to true when it's being used in a live event
            self.ports          = ports
            self.type           = encType
            self.rtspURL        = False # this is the public (proxied) rtsp URL - a stream that anyone on the network can view
            self.id             = int(time.time()*1000000) #id of each device is gonna be a time stamp in microseconds (only used for creating threads)
            self.ipcheck        = '127.0.0.1' #connect to this ip address to check rtsp - for now this will be simply connecting to the rtsp proxy, constant pinging of the RTSP on the device directly can cause problems
            # add a new device, based on its type
            if(self.type=='td_cube'):
                self.device = encTeradek(ip)
            elif(self.type=='mt_monarch'):
                self.device = encMatrox(ip)
            elif(self.type=='ph_glass'):
                self.device = encPivothead(ip)
            elif(self.type=='sn_snc'):
                self.device = encSonySNC(ip)
            elif(self.type=='db_tst'):
                self.device = encDebug(ip)
            else: #unknown device type specified
                return False
            if(url):
                self.device.rtspURL = url #this is a private url used for getting the video directly form the device
            if(preview):
                self.previewURL = preview
            if(not 'src' in tmr):
                tmr['src']={}
            tmr['src'][self.id] = TimedThread(self.monitor,period=2)
        except Exception as e:
            dbg.prn(dbg.ERR|dbg.SRC, "[---]source.init", e, sys.exc_traceback.tb_lineno)
    #end init
    def __repr__(self):
        return "<source> url:{rtspURL} type:{type} dev:{device}".format(**self.__dict__)
    def buildCapCmd(self):
        return self.device.buildCapCmd(self.rtspURL,self.ports['chk'],self.ports['mp4'],self.ports['hls'])
    def camPortMon(self):
        """ monitor data coming in from the camera - to make sure it's continuously receiving """
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
                    sys.stdout.write('.')
                    try:
                        timeStart = time.time()
                        if(enc.code & enc.STAT_LIVE):
                            # only set encoder status if there is a live event 
                            # to make sure the monitor runs an RTSP check on the stream
                            self.device.isOn=False
                        time.sleep(1) #wait for a second before trying to receive data again
                    except Exception as e:
                        pass
                except Exception as e:
                    dbg.prn(dbg.ERR|dbg.SRC,"[---]camPortMon err: ",e,sys.exc_traceback.tb_lineno)
            #end while
        except Exception as e:
            dbg.prn(dbg.ERR|dbg.SRC,"[---]camportmon err: ", e, sys.exc_traceback.tb_lineno)
    def monitor(self):
        """ monitors the device parameters and sets its parameters accordingly """
        try:
            self.device.update() #get all available parameters
            if(enc.code & enc.STAT_SHUTDOWN):
                return False
            # make sure live555 is running
            urlFilePath = "/tmp/pxp-url-"+str(self.device.ip)
            if(not procMan.pexists(name="live555",devID=self.device.ip)):
                dbg.prn(dbg.SRC,"adding live555 for ", self.device.ip, self.type)
                procMan.padd(name="live555",devID=self.device.ip,cmd="live555ProxyServer -o "+urlFilePath+" "+self.device.rtspURL,keepAlive=True,killIdle=True, forceKill=True)
                self.device.liveStart = time.time()  # record the time of the live555 server start
            live555timeout = time.time()-10 #wait for 10 seconds to restart live555 server
            if(not self.device.isOn and self.device.liveStart<live555timeout):
                dbg.prn(dbg.SRC,"stopping live555")
                procMan.pstop(name="live555",devID=self.device.ip)
            #make sure live555 is up and running and no changes were made to the ip address
            if(os.path.exists(urlFilePath)): #should always exist!!!!
                streamURL = pu.disk.file_get_contents(urlFilePath).strip()
                self.rtspURL = streamURL
                if(enc.busy() and not (enc.code & enc.STAT_STOP) and self.rtspURL != streamURL):
                    dbg.prn(dbg.SRC,"url changed", self.rtspURL, streamURL)
                    #the streaming url changed - update it in the capturing ffmpeg command if the encoder was live already
                    while(procMan.pexists(name='capture', devID = self.device.ip)):
                        dbg.prn(dbg.SRC,"trying to stoppppppppppppppppp")
                        procMan.pstop(name='capture',devID=self.device.ip)
                    camMP4  = str(self.ports['mp4'])
                    camHLS  = str(self.ports['hls'])
                    chkPRT  = str(self.ports['chk'])
                    capCMD  = self.buildCapCmd()
                    procMan.padd(name="capture",devID=self.device.ip,cmd=capCMD, keepAlive=True, killIdle=True, forceKill=True)
                #end if enc.busy and not stop
                #end if stream url changed mid-stream
                # get the port (used to connect to rtsp stream to check its state)
                #the url should be in this format: rtsp://192.168.3.140:8554/proxyStream
                # to get the port:
                # 1) split it by colons: get [rtsp, //192.168.3.140, 8554/proxyStream]
                # 2) take 3rd element and split it by /, get: [8554, proxyStream]
                # 3) return the 8554
                self.ports['rtp'] = int(self.rtspURL.split(':')[2].split('/')[0].strip())
            #end if path.exists
            # check rtsp connectivity if it wasn't checked yet
            if(not self.rtspURL): #no url with rtsp stream is available yet
                return False
            if(not (self.device.isOn and enc.busy())):
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
                    #probably failed because couldn't connect to the rtsp server - no need to worry
                    pass
                # make sure the framerate is ok on this device 
                strdata = data[:2048].lower().strip()
                if(strdata.find('host is down')>-1 or strdata.find('no route to host')>-1):
                    # found a "ghost": this device recently disconnected
                    dbg.prn(dbg.SRC,"RTSP ghost found - device is disconnected")
                    pass
                if(strdata.find('timed out')>-1): #the connection is down (maybe temporarily?), the isOn is already set to false
                    dbg.prn(dbg.SRC,"RTSP timeout - temporarily unreachable?")
                    pass
                #a device is not available (either just connected or it's removed from the system)
                #when connection can't be established or a response does not contain RTSP/1.0 200 OK
                self.device.isOn = (data.find('RTSP/1.0 200 OK')>=0)
            # this is only relevant for medical
            if(self.device.initialized and self.device.ccFramerate and self.device.framerate>=50):
                self.device.setFramerate(self.device.framerate/2) #set resolution to half if it's too high (for tablet rtsp streaming)
            # if(self.device.isOn):
                # self.device.initialized = True
            if(self.device.initialized):
                self.device.initStarted    = int(time.time()*1000) #when device is initialized already, reset the timer
            self.device.initialized = self.device.isOn #if the stream is unreachable, try to re-initialize the device or remove it form the system
        except Exception as e:
            dbg.prn(dbg.ERR|dbg.SRC,"[---]source.monitor", e, sys.exc_traceback.tb_lineno)
            dbg.prn(dbg.ERR|dbg.SRC,"[---dbg---]", self.device.isOn, self.device.liveStart, live555timeout)
            return False
        return True
    #end monitor
    def stopMonitor(self):
        try:
            # stop the monitor
            dbg.prn(dbg.SRC,"stop monitor thread")
            self.isEncoding = False
            if('src' in tmr and self.id in tmr['src']):
                tmr['src'][self.id].kill()
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
    def __init__(self):
        self.allowIP = True  #whether to allow IP streaming sources to be added
        self.mp4Base = 22500 #ffmpeg captures rtsp stream and outputs H.264 stream here
        self.hlsBase = 22600 #ffmpeg captures rtsp stream and outputs MPEG-TS here
        self.chkBase = 22700 #port where a monitor is sitting and checking if packets are arriving, doesn't matter the format
        self.sources = [] #video sources go here
        if(not 'srcmgr' in tmr):
            tmr['srcmgr'] = {}
        tmr['srcmgr']['mgrmon'] = TimedThread(self.monitor, period=3)
        tmr['srcmgr']['discvr'] = TimedThread(self.discover, period=3)
    def addDevice(self, inputs):
        """ adds a source to the list 
        @param (str)    ip      - ip address of the source (used for checking if the device is alive)
        @param (str)    url     - rtsp source url
        @param (str)    encType - type of source/encoder (e.g. td_cube, ph_glass, mt_monarch)
        """
        try:
            if(enc.code & enc.STAT_SHUTDOWN):
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
            idx = len(self.sources)
            #device does not exist yet (just found it)
            #assign ports accordingly
            ports = {
                    "mp4":self.mp4Base+idx,
                    "hls":self.hlsBase+idx,
                    "chk":self.chkBase+idx,
                }
            if('url' in inputs):#the device discovered was the main url device
                ports['rtp'] = int(inputs['port'])
                dev = source(ip=ip,url=inputs['url'],encType=inputs['type'], ports=ports)
            elif('preview' in inputs):#discovered the preview version of the device
                ports['preview'] = int(inputs['preview-port'])
                dev = source(ip=ip,preview=inputs['preview'],encType=inputs['type'], ports=ports)
            if(dev):
                self.sources.append(dev)
                dbg.prn(dbg.SRM,"all sources (devices): ", self.sources)
                return True
        except Exception as e:
            dbg.prn(dbg.SRM|dbg.ERR, "[---]srcMgr.addDevice: ",e, sys.exc_traceback.tb_lineno)
        return False
    #end addDevice
    def discover(self):
        try:
            if(enc.code & enc.STAT_SHUTDOWN):
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
                        del tmr['srcmgr'][s]
                    #remove the devices dictionary
                    del tmr['srcmgr']['devs']
                #end if devs in srcmgr
                return 
            #end if
            # this device IS a master
            self.allowIP = True
            if('srcmgr' in tmr and 'devs' in tmr['srcmgr']):
                return #the devices are already being discovered
            # this is the first time running this method since this device became Master
            # this dictionary will contain threads that look for video sources on the network
            tmr['srcmgr']['devs'] = {}

            encTD = encTeradek()
            encMT = encMatrox()
            encPH = encPivothead()
            encSN = encSonySNC()
            encDB = encDebug()

            tmr['srcmgr']['devs']['td'] = TimedThread(encTD.discover, params=self.addDevice, period=5)
            tmr['srcmgr']['devs']['mt'] = TimedThread(encMT.discover, params=self.addDevice, period=5)
            tmr['srcmgr']['devs']['ph'] = TimedThread(encPH.discover, params=self.addDevice, period=5)
            tmr['srcmgr']['devs']['sn'] = TimedThread(encSN.discover, params=self.addDevice, period=5)
            tmr['srcmgr']['devs']['db'] = TimedThread(encDB.discover, params=self.addDevice, period=5)
        except Exception as e:
            dbg.prn(dbg.ERR|dbg.SRM, "[---]srcMgr.discover: ",e, sys.exc_traceback.tb_lineno)
    #end discover
    def encCapPause(self):
        if(enc.code & enc.STAT_LIVE):
            enc.statusSet(enc.STAT_PAUSED)
            procMan.pstop(name='capture',remove=False)
    def encCapResume(self):
        if(enc.code & enc.STAT_PAUSED):
            procMan.pstart(name='capture')
            enc.statusSet(enc.STAT_LIVE)
    def encCapStart(self):
        """ start encode capture """
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
            for idx in xrange(len(self.sources)):
                if(idx>=len(self.sources)):
                    break
                src = self.sources[idx]
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
                ffmp4Ins +=" -i udp://127.0.0.1:"+camMP4
                # if(len(self.sources)<2):
                #     listSuffix = ""
                #     # there is only one camera - no need to set camIdx for file names
                #     filePrefix = ""
                # else: #multiple cameras - need to identify each file by camIdx
                # always add source indecies - future server versions will deprecate old style file naming
                filePrefix = camIdx.zfill(2)+'hq_' #left-pad the camera index with zeros (easier to sort through segment files and thumbnails later on)
                listSuffix = "_"+camIdx.zfill(2)+'hq' #for normal source, assume it's high quality
                # TODO: add a lq stream for devices with preview

                ffmp4Out +=" -map "+camIdx+" -codec copy "+c.wwwroot+"live/video/main"+listSuffix+".mp4"
                # this is HLS capture (segmenter)
                if (pu.osi.name=='mac'): #mac os
                    segmenters[src.device.ip] = c.segbin+" -p -t 1s -S 1 -B "+filePrefix+"segm_ -i list"+listSuffix+".m3u8 -f "+c.wwwroot+"live/video 127.0.0.1:"+camHLS
                elif(pu.osi.name=='linux'): #linux
                    os.chdir(c.wwwroot+"live/video")
                    segmenters[src.device.ip] = c.segbin+" -d 1 -p "+filePrefix+"segm_ -m list"+filePrefix+".m3u8 -i udp://127.0.0.1:"+camHLS+" -u ./"

                # if(quality=='low' and 'preview' in cameras[src.device.ip]):
                #     camURL = cameras[src.device.ip]['preview']
                # else:
                # this ffmpeg instance captures stream from camera and redirects to mp4 capture and to hls capture
                dbg.prn(dbg.SRM, "capcmd:",src.rtspURL, chkPRT, camMP4, camHLS)
                ffcaps[src.device.ip] = src.buildCapCmd()
                # each camera also needs its own port forwarder
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
                self.sources[idx].isEncoding = True
                # segmenter
                startSuccess = startSuccess and procMan.padd(name="segment",devID=src.device.ip,cmd=segmenters[src.device.ip],forceKill=True)
                # ffmpeg RTSP capture
                startSuccess = startSuccess and procMan.padd(name="capture",devID=src.device.ip,cmd=ffcaps[src.device.ip], keepAlive=True, killIdle=True, forceKill=True)
                # start port checkers for each camera
                tmr['portCHK'][src.device.ip]=TimedThread(self.sources[idx].camPortMon)
            #end for dev in segmenters

            # start mp4 recording to file
            startSuccess = startSuccess and procMan.padd(cmd=ffMP4recorder,name="record",devID="ALL",forceKill=False)
            if(not startSuccess): #the start didn't work, stop the encode
                self.encCapStop() #it will be force-stopped automatically in the stopcap function
        except Exception as e:
            dbg.prn(dbg.ERR|dbg.SRM,"[---]encCapStop: ",e,sys.exc_traceback.tb_lineno)
            self.encCapStop() #it will be force-stopped automatically in the stopcap function
            enc.statusSet(enc.STAT_READY)
    #end encCapStart
    def encCapStop(self,force=False):
        """stops the capture, kills all ffmpeg's and segmenters
        force - (optional) force-kill all the processes - makes stopping process faster
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
                self.sources[idx].isEncoding = False
                ffBlue += " -r 30 -vcodec libx264 -an -f h264 udp://127.0.0.1:"+str(src.ports['mp4'])
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
            os.system("killall -9 live555ProxyServer >/dev/null 2>/dev/null")
        except Exception as e:
            dbg.prn(dbg.SRM|dbg.ERR,"[---]encCapStop: ",e,sys.exc_traceback.tb_lineno)
        if(enc.code & enc.STAT_STOP):
            enc.statusSet(enc.STAT_READY)
    #end encStopCap
    def exists(self, ip):
        """ check if a device with this IP exists already 
        @param (str)    ip  -   ip address of the device to lookup
        @return (int)       -   if the search is successful, return index of the device in the array, if the device is not found return -1
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
        try:
            if(enc.code & enc.STAT_SHUTDOWN):
                return False
            # check if all the devices are on
            sources = copy.deepcopy(self.sources)
            idx = 0
            isCamera = False
            # dbg.prn(dbg.SRM, "mon..................")
            # dbg.prn(dbg.SRM, sources)
            # dbg.prn(dbg.SRM, "..................mon")
            for src in sources:
                now = int(time.time()*1000)
                if (((not src.device.initialized) and (now-src.device.initStarted)>60000) or ((not self.allowIP) and src.device.isIP)): 
                    #could not initialize the device after a minute or the device is an IP streaming device and they are not allowed at the moment
                    dbg.prn(dbg.SRM, "could not init device or IP sources are not allowed - stop monitor")
                    # src.stopMonitor()
                    self.sources[idx].stopMonitor()
                    devIP = src.device.ip
                    dbg.prn(dbg.SRM, "deleting...", self.sources)
                    del self.sources[idx]
                    dbg.prn(dbg.SRM, "deleted ", self.sources)
                    if(not(enc.code & (enc.STAT_LIVE|enc.STAT_PAUSED|enc.STAT_STOP))):
                        procMan.pstop(devID=devIP) #stop all the processes associated with this device
                else:
                    idx+=1
                    isCamera = isCamera or src.device.isCamera
            #end for
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
    def setBitrate(self, bitrate, camID=-1):
        """ change camera/encoder bitrate
        @param (int) bitrate - new bitrate to set
        @param (int) camID - (optional) id of the encoder/camera. if not specified, the bitrate will be set for all cameras
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
        """ creates a dictionary of all the sources 
        @param (bool) autosave - (optional) saves the dictionary in json format to a pre-defined file (default=True)
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
    """ a server object that can be synced """
    enabledUp = False #sync up enabled on this server
    enabledDn = False #sync down enabled - this is irrelevant here, all servers pull events, no pushing needed
    ip        = False
    master    = False #whether this server is a master
    dnCount   = 0 #how many updateInfo requests failed
    def __init__(self, ip):
        self.ip = ip
        # determine whether this server allows sync
        try:
            resp = pu.io.url("http://"+self.ip+"/min/ajax/serverinfo",timeout=5) #if it takes more than 10 seconds to get the server info, the connection is too slow for backup anyway
            if(not resp):
                dbg.prn(dbg.SSV,"bad response from", self.ip,':', resp)
                return
            resp = json.loads(resp)
            self.enabledUp = int(resp['settings']['up'])
            self.enabledDn = int(resp['settings']['dn'])
            self.master = int(resp['master'])
            tmr['srvsync'][self.ip] = TimedThread(self.updateInfo,period=5)
        except Exception as e:
            dbg.prn(dbg.ERR|dbg.SSV,"[---]syncsrv.init:", e, sys.exc_traceback.tb_lineno)
    def cancel(self):
        """ stop the sync """
        pass
    def doneCopy(self):
        """ gets called when download finished """
        pass
    def monitor(self):
        """ monitors sync progress """
        pass
    def syncUp(self):
        """ syncs events from this server to the local server """
        try:
            cfg = pxp._cfgGet(c.wwwroot+"_db/")
            dbg.prn(dbg.SSV,"trying sync")
            if(not cfg):
                return _err("not initialized")
            if(len(cfg)<4): #old encoders won't have the syncLevel by default, this is a workaround
                localSyncLevel = 0
            else:
                localSyncLevel = int(cfg[3])
            customerID = cfg[2]
            # get a list of remove events
            resp = pu.io.url("http://"+self.ip+"/min/ajax/getpastevents",timeout=10)
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
                # self.urlListDn(baseurl="http://"+self.ip,fileList = resp['entries'], dest=c.wwwroot+evt['datapath'])
                # network sync has lower priority than user-initiated sync's, but higher than local backup
                # in order for sync to complete before automatic backup kicks in and tries to back up an event that wasn't synced yet
                backuper.add(hid=hid,priority=1,remoteParams={"url":"http://"+self.ip,"files": resp['entries']})
                toSync +=1
            dbg.prn(dbg.SSV,"TO SYNC: ",toSync)
        except Exception as e:
            dbg.prn(dbg.ERR|dbg.SSV,"[---]syncsrv.syncUp:", e, sys.exc_traceback.tb_lineno, 'ip:',self.ip)
    def statusTxt(self):
        pass
    def stopMon(self):
        try:
            tmr['srvsync'][self.ip].kill()
        except:
            pass
    def updateInfo(self):
        # determine whether this server allows sync
        try:
            resp = pu.io.url("http://"+self.ip+"/min/ajax/serverinfo",timeout=4) #if it takes more than 10 seconds to get the server info, the connection is too slow for backup anyway
            if(not resp): #the server must have gone dark
                self.dnCount +=1
                return
            resp = json.loads(resp)
            self.enabledUp = int(resp['settings']['up'])
            self.enabledDn = int(resp['settings']['dn'])
            self.master = int(resp['master'])
            self.dnCount = 0
        except Exception as e:#something is wrong with the response from the server
            self.dnCount +=1
            dbg.prn(dbg.ERR|dbg.SSV,"[---]syncsrv.init:", e, sys.exc_traceback.tb_lineno)
    #end updateInfo        
#end SyncSrv

class SyncManager(object):
    """ manages networked servers: finds pxp servers, checks their options, syncs the events between them """
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
        """ based on all discovered devices makes a decision on whether this server will be master or not """
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
            dbg.prn(dbg.SMG,'found', len(servers), 'the local is', master)
            if(enc.code & enc.STAT_INIT):
                enc.statusSet(enc.STAT_READY,overwrite=False)
        except Exception as e:
            dbg.prn(dbg.SMG|dbg.ERR, "[---]syncmgr.arbitrate:", e, sys.exc_traceback.tb_lineno)
    def discover(self):
        """ discovers any pxp servers on the network """
        if(enc.code & enc.STAT_SHUTDOWN):
            return
        # get customer ID for authentication
        cfg = pxp._cfgGet()
        if(not cfg): 
            return _err("not initialized")
        customerID = cfg[2]
        def discovered(result):
            if(enc.code & enc.STAT_SHUTDOWN):
                return
            if(result['ip'] in pu.io.myIP(allDevs=True)): #found itself - skip
                return
            if(result['ip'] in self.servers): #this server was already discovered
                return
            try:
                srvResponse = ''
                # check if this server is from the same customer
                srvResponse = pu.io.url("http://"+result['ip']+'/min/ajax/auth/',params={'id':customerID})
                if(not srvResponse):
                    dbg.prn(dbg.SMG, 'no server at',result['ip'])
                    return
                resp = json.loads(srvResponse.strip())
                if ('success' in resp and resp['success']):
                    self.servers[result['ip']]=SyncSrv(result['ip'])
                    speak("found "+re.sub('[\.]','.dot.',str(result['ip'][result['ip'].rfind('.')+1:]))+", total "+str(len(self.servers))+" servers, derka derka.")
            except Exception as e:
                # most likely could not process response - that was an old server
                dbg.prn(dbg.ERR|dbg.SMG, "[---]syncmgr.discovered:", e, sys.exc_traceback.tb_lineno)
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
    def servInfo(self):
        """ return server information """
        return [self.isMaster]
    def syncAll(self):
        """ syncs all servers to self """
        try:
            if(enc.code & enc.STAT_SHUTDOWN):
                return
            # make sure local server has sync enabled
            settings = pu.disk.cfgGet(section="sync")
            if(settings['dn']):#down sync enabled on the local server - sync all remote servers
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
def speak(msg):
    os.system("say -v Veena "+str(msg))
    pass
#recursively kills threads in the ttObj
def pxpTTKiller(ttObj={},name=False):
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
        os.system("killall -9 live555ProxyServer 2>/dev/null &")
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

# kick the watchdog on each tablet (to make sure the socket does not get reset)
def kickDoge():
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
    """ process class 
    @param str cmd        - execute this command to start the process
    @param str name       - process nickname (e.g. segmenter)
    @param str devID      - device id associated with this process (e.g. encoder IP address)
    @param bool keepAlive - restart the process if it's dead
    @param bool killIdle  - kill the process if it's idle
    @param bool forceKill - whether to force-kill the process when killing it (e.g. send SIGKILL instead of SIGINT)
    """
    def __init__(self,cmd,name,devID,keepAlive=False,killIdle=False,forceKill=False):
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
    def __del__(self):
        self._cleanup()
    def __repr__(self):
        return "<proc> {name} {dev} ...{cmd}... {keepalive} {forcekill} {killidle}".format(**self.__dict__)
    def start(self):
        """ starts a process (executes the command assigned to this process) """
        try:
            if(self.off): #the process is stopping, it should not restart
                return False
            # start the process
            if(self.name=='capturez'):#display output in the terminal
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
        """ stops the process 
            @param (bool) async - whether to stop this event in the background (default: True)
            @param (bool) force - force-stop the process if true
            @param (bool) end   - permanently end the process (no possibility of restart)
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
        """ stops the process and immediately restarts it """
        self.stop(async=False) #wait till the command stops
        self.start()
    def _cleanup(self):
        dbg.prn(dbg.PPC, "proc", self.name, "cleanup")
        for thread in self.threads:
            try:#remove any running threads
                dbg.prn(dbg.PPC, "clean ",thread)
                self.threads[thread].kill()
            except Exception as e:
                dbg.prn(dbg.ERR|dbg.PPC, "[---]proc._cleanup",self.name, thread,e)
                pass
    def _monitor(self):
        try:
            # monitor the process health
            self.alive = psOnID(pid=self.pid) #check if the process is alive
            self.cpu = pu.disk.getCPU(pid=self.pid) #get cpu usage
        except Exception as e:
            dbg.prn(dbg.PPC|dbg.ERR,"[---]proc._monitor: ",e,sys.exc_traceback.tb_lineno)
    def _manager(self):
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
    """ process management class """
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
        """ determine whether a process is alive 
        @param (str) name - name of the process
        @param (str) devID - id of the device this process belongs to. if unspecified, return the first process matching the name (default: False)
        """
        procs = self.procs.copy()
        for idx in procs:
            proc = procs[idx]
            if(proc.name==name):
                if(not devID or proc.dev==devID): #either devID matches or devID wasn't specified - just kill processes matching the name
                    return proc.alive
        return False
    def padd(self,cmd,name,devID,keepAlive=False,killIdle=False,forceKill=False):
        """ Add a new process (command) to the process manager and try to start it

        Args:
            cmd (str): command to execute in the terminal
            name (str): what to name the process for later reference
            devID (str): associate the process with this device ID (usually IP address)
            keepAlive (bool,optional): keep the process alive (i.e. if it dies, restart it)
            killIdle (bool,optional): kill if this process stalls (low cpu usage or gets zombiefied)
            forceKill (bool,optional): when stopping this process, force-kill it right away

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
            self.procs[idx] = proc(cmd,name,devID,keepAlive,killIdle,forceKill)
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
    # remove process from the list 
    def premove(self,procidx):
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
    # start a specified process (usually used for resuming an existing process)
    def pstart(self,name,devID=False):
        procs = self.procs.copy()
        for idx in procs:
            proc = procs[idx]
            if(proc.name==name):
                if(not devID or proc.dev==devID): #either devID matches or devID wasn't specified - just start all processes matching the name
                    proc.start()
    def _stopwait(self,idx):
        """ waits until the process is stopped, then removes it"""
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
#end gap
# arr = [0,1,3,5,10]
# nextGap = gap(arr,0,count(arr)-1)


# attempts to kill a process based on PID (sends SIGKILL, equivalent to -9)
# @param (int) pid - process ID
# @param (int) pgid - process group ID
# @param (obj) ref - reference to the Popen process (used to .communicate() - should prevent zombies)
# @param (int) timeout - timeout in seconds how long to try and kill the process
# @param (bool) force - whether to force exit a process (sends KILL - non-catchable, non-ignorable kill)
def psKill(pid=0,pgid=0,ref=False,timeout=4,force=False):
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

# checks if a process is active based on pid
def psOnID(pid=0,pgid=0):
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

# adds message for a client to the BBQ
# client - id of the client (ip + port)
# msg - message to send
# c - reference to the client variable (used to add them to the queue for the first time)
def addMsg(client,msg,c=False):
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
                if(dataParts[0]=='RMF' or dataParts[0]=='RMD' or dataParts[0]=='BTR' or dataParts[0]=='BKP' or dataParts[0]=='RRE'):
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
                    return syncMgr.servInfo()
                if(dataParts[0]=='CML'): # camera list
                    return srcMgr.toJSON()
                if(dataParts[0]=='LBP'): # list events that are in the process of backing up (do not yet fully exist on local machine)
                    return backuper.list()
                if(len(dataParts)<2):
                    dataParts[1]=False
                if(dataParts[0]=='CPS'): # copy status request
                    nobroadcast = True
                    return backuper.status(dataParts[1])
                if(dataParts[0]=='LVL'): # set log level
                    dbg.setLogLevel(dataParts[1])
                if(dataParts[0]=='LOG'): # set logging to file on/off
                    dbg.setLog(dataParts[1])
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

# set encoder status

#make sure there is only 1 instance of this script running
# me = singleton.SingleInstance()
dbg = debugLogger()
procs = pu.disk.psGet("pxpservice.py")
if(len(procs)>0 and not (os.getpid() in procs)):
    dbg.prn(dbg.MN, "ps on!!")
    exit()
else:
    dbg.prn(dbg.MN, procs)
    dbg.prn(dbg.MN, "ps off!!")
tmr = {}
enc = encoderStatus()
encControl = commander() #encoder control commands go through here (start/stop/pause/resume)

dbg.prn(dbg.MN,"---APP START--")
procMan = procmgr()
try:
    # remove old encoders from the list, the file will be re-created when the service finds encoders
    os.remove(c.devCamList)
except:
    pass
os.system("killall -9 live555ProxyServer 2>/dev/null &") #make sure there's no other proxy server
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

srcMgr = sourceManager()

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
dbg.prn(dbg.MN,"main...")
if __name__=='__main__':
    try:
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