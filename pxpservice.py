#!/usr/bin/python
#import sys;sys.path.append(r'/Applications/eclipse/plugins/org.python.pydev_4.1.0.201505270003/pysrc')
#import pydevd;
#from __future__ import division, print_function, absolute_import, unicode_literals
from datetime import datetime as dt
from uuid import getnode as getmac
from pxputil import TimedThread
from urlparse import parse_qsl
from itertools import izip_longest
import camera, constants as c, copy, json, os, psutil, pxp, pxputil as pu, signal, socket, subprocess as sb, time
import glob, sys, shutil, hashlib, re
import pprint as pp
import pxpmisc
import threading
import time
import sqlite3
from test.test_socket import try_address
import pxphelper
from types import NoneType
import serial
from serial.serialutil import SerialException
from __builtin__ import True
import telnetlib

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

sockCmd = 0
devaddingnow = False # indicates that addDevice() is entered 

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

camMP4base = 22500 #ffmpeg captures rtsp stream and outputs H.264 stream
camHLSbase = 22600 #ffmpeg captures rtsp stream and outputs MPEG-TS here
chkPRTbase = 22700 #port where a monitor is sitting and checking if packets are arriving, doesn't matter the format
sockInPort = 2232

pxpworker = []

def cleanup_pxp_workers():
    # cleanup pxpworker if everything is done ------------------
    global pxpworker
    doneCount = 0
    for w in pxpworker:
        if (w.done):
            doneCount += 1
    if (len(pxpworker)>0 and len(pxpworker)==doneCount):
        pxpworker = []
    return doneCount

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
    TST            = 1<<9 # test device

    SRC            = 1<<10 # video source (encoder/ip camera)
    SRM            = 1<<11 # source manager
    SSV            = 1<<12 # SyncSrv
    SMG            = 1<<13 # SyncMgr
    KLL            = 1<<14 # pxpKiller
    PPC            = 1<<15 # proc
    PCM            = 1<<16 # proc manager
    DHL            = 1<<17 # data handler
    SHL            = 1<<18 # socket handler
    BBQ            = 1<<19 # BBQ Manager
    DBG            = 1<<20 # debugger
    RRE            = 1<<21 # restore events

    MN             = 1<<21 # main function
    AXS            = 1<<22 # Axis Camera
    PXP            = 1<<23 # PXP Log
    FIX            = 1<<24 # MP4 repair
    MDB            = 1<<25 # SQLMDB
    DLT            = 1<<26 # Delta Camera
    IPC            = 1<<27 # generic IP Camera

    #this property defines which of the above groups will be logged
    #KLL|ERR|MN|SRC|PCM|PPC
    LVL            = KLL|ERR|MN # |SRC|PCM|PPC # USE WISELY!! too many groups will cause the log file to grow disproportionately large!
    #whether to log to file as well as to screen
    LOG            = 1 #only enable if you suspect there might be a problem, or for debugging

    def __init__(self):
        super(debugLogger, self).__init__()   
#         self.db_levels = ['ppc','pcm','srm','src','dbg','enc']
#         for db_level in self.db_levels:
#             pass
        self.mvlogfiles()        
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
                if(kind & self.PXP):
                    pu.mdbg.log((''.join(map(str, (arguments)))))
            except Exception as e:
                print "[---]prn:",e, sys.exc_info()[-1].tb_lineno
    def mvlogfiles(self):
        try:
            import os.path
            oldfn1 = dt.fromtimestamp(time.time()).strftime("%Y-%m-%d_%H_%M_%S_%f_") + "pxpservice.txt"
            oldfn2 = dt.fromtimestamp(time.time()).strftime("%Y-%m-%d_%H_%M_%S_%f_") + "mypxp.txt"
            if (os.path.exists(c.logFile)):
                cmd = 'mv ' + c.logFile + ' ' + c.wwwroot + "_db/" + oldfn1
                os.system(cmd)
            if (os.path.exists(c.tmpLogFile)):            
                cmd = 'mv ' + c.tmpLogFile + ' ' + c.wwwroot + "_db/" + oldfn2
                os.system(cmd)
        except Exception as e:
            pass
    def log(self, kind, *arguments, **keywords):
        # print arguments
        if(not (kind & self.LVL)): #only print one type of event
            return
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
                print "[---]log:",e, sys.exc_info()[-1].tb_lineno
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
            self.RRE:"RRE",
            self.MN :"MN",
            self.AXS:"AXS",
            self.PXP:"PXP",
            self.MDB:"MDB",
            self.DLT:"DLT",
            self.IPC:"IPC"
        }
        cmdList = []
        # go through each command and add it to the display list if its bit is set in the user's command
        for item in names:
            if(cmd & item):
                cmdList.append(names[item])
        return (',').join(cmdList)
    def setcmdlevel(self,cmds):
        names = {
        "CMD":self.CMD,
        "ECN":self.ECN,
        "ERR":self.ERR,
        "BKP":self.BKP,
        "ENC":self.ENC,
        "TDK":self.TDK,
        "MTX":self.MTX,
        "PVH":self.PVH,
        "SNC":self.SNC,
        "TST":self.TST,
        "SRC":self.SRC,
        "SRM":self.SRM,
        "SSV":self.SSV,
        "SMG":self.SMG,
        "KLL":self.KLL,
        "PPC":self.PPC,
        "PCM":self.PCM,
        "DHL":self.DHL,
        "SHL":self.SHL,
        "BBQ":self.BBQ,
        "DBG":self.DBG,
        "RRE":self.RRE,
        "MN": self.MN ,
        "AXS":self.AXS,
        "PXP":self.PXP, 
        "MDB":self.MDB,
        "DLT":self.DLT,
        "IPC":self.IPC
        }
        level = 0
        if (cmds != ''):
            for cmd in cmds.split('|'):
                if (cmd in names):
                    level |= names[cmd]
            self.setLogLevel(level)
            self.prn(self.MN, "debug level set to:", cmds)
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
            dbg.prn(dbg.BKP|dbg.ERR,"[---]bkp.init:",e,sys.exc_info()[-1].tb_lineno)
    def cancel(self):
        """ For an event that is still copying - send a kill signal to it """
        try:
            if(self.status & (self.STAT_START)): #the event didn't finish copying
                self.kill = True
            #end if bkp in tmr
        except Exception as e:
            dbg.prn(dbg.BKP|dbg.ERR,"[---]bkp.start:",e,sys.exc_info()[-1].tb_lineno)
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
                dbg.prn(dbg.BKP,"copied:{} file:{}".format(self.copied, self.currentFile))
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
            dbg.prn(dbg.BKP|dbg.ERR,"[---]bkp.monitor:",e,sys.exc_info()[-1].tb_lineno)
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
            dbg.prn(dbg.BKP|dbg.ERR,"[---]bkp.onComplete",e,sys.exc_info()[-1].tb_lineno)
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
            dbg.prn(dbg.BKP|dbg.ERR,"[---]bkp.start",e,sys.exc_info()[-1].tb_lineno)
    def startBackup(self):
        """ Start local backup - to an attached storage. This is called for automatic or manual backups """
        # get info about the event
        try:
            dbg.prn(dbg.BKP, "starting local backup")
            self.status = self.STAT_START
            
            # STEP1 -- Read all of events from the local database and store them into eventData
            db = pu.db(c.wwwroot+"_db/pxp_main.db")
            sql = "SELECT * FROM `events` WHERE `hid` LIKE ?"
            db.query(sql,(self.hid,))
            eventData = db.getasc()
            db.close()
            
            # STEP2 -- Get the total size of the eventData for sanity check if there's event that it can backup
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
            eventData[0]['evt_size'] = evtSize  # jchoi: for restore, dirSize takes too much time to read and it failed to restore. Adding this info can help.
            
            
            # STEP3 -- Is there any backup drive attached to this machine???
            # get a list of all attached devices
            drives = pu.disk.list()
            dbg.prn(dbg.BKP,"found drives:", drives)
            if(len(drives)<1): #no drives
                drives = pu.disk.list(dbg_print=True)
                self.status = self.STAT_NODRV | self.STAT_FAIL
                return
            if(self.auto):
                backupDir = self.autoDir
            else:
                backupDir = self.manualDir
            # look for which one to back up to
            # first check all drives for the backupDir, if it exists, just back up to it (if it has enough space and write permissions)
            self.backupDrive = False
            for drive in drives:
                if(os.path.exists(drive+backupDir) and os.access(drive,os.W_OK)): #found a drive that has previous backups and write permissions
                    # check space
                    try:
                        driveInfo = pu.disk.stat(humanReadable=False,path=drive)
                        if(driveInfo['free']>evtSize):
                            # there is enough space for backup - use this drive
                            self.backupDrive = drive
                            break
                    except:
                        pass
                #end if path.exists
            #end for drive in drives
            if(not self.backupDrive): #no drive found with backup folder, look for any available drive
                # NB: automatic backups are only done to a drive that has pxp-autobackup folder
                # NB: manual backups cannot be done to a drive that has pxp-autobackup folder
                for drive in drives:
                    driveInfo = pu.disk.stat(humanReadable=False,path=drive)
                    if(driveInfo['free']>evtSize and os.access(drive,os.W_OK) and (os.path.exists(drive+self.autoDir) == self.auto)):
                        self.backupDrive = drive
                        break
                #end for drive in drives
            #end if not backupDrive

            if(self.backupDrive): #found a backup drive
                pu.disk.file_set_contents(c.curUsbDrv, self.backupDrive)
                dbg.prn(dbg.BKP,"free on ",drive,":",driveInfo['free'])
                outputPath = self.backupDrive.decode('UTF-8')+backupDir+eventData[0]['datapath']
                pu.disk.mkdir(outputPath) # create the output directory
                # save the event info
                eventString = json.dumps(eventData[0])
                eventString = eventString.replace(': null',': ""') #jchoi: null cannot be loaded in python. changed to '' string 
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
            dbg.prn(dbg.BKP|dbg.ERR,"[---]bkp.startBackup:",e,sys.exc_info()[-1].tb_lineno)
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
            dbg.prn(dbg.BKP|dbg.ERR,"[---]bkp.startCloud:",e,sys.exc_info()[-1].tb_lineno)
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
            dbg.prn(dbg.BKP|dbg.ERR,"[---]bkp.startRemote:",e,sys.exc_info()[-1].tb_lineno)
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
            dbg.prn(dbg.BKP|dbg.ERR,"[---]bkp.startRestore:",e,sys.exc_info()[-1].tb_lineno)
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
                src_basename = os.path.basename(src)
                dst_basename = os.path.basename(dst)
                
                if os.path.islink(src):
                    linkto = os.readlink(src)
                    try:
                        os.symlink(linkto, dst)
                    except Exception as ecopy:
                        dbg.prn(dbg.BKP,"[---] bkpevt.symbolic_copy skipped (reason:{}), linkto:{} dst:{} src:{} ... passed".format(ecopy, linkto, dst, src))
                        pass
                else:
                    try:
                        if (os.path.getsize(src)!=os.path.getsize(dst)):
                            shutil.copy(src,dst)
                            pu.mdbg.log("bkpevt.copy src:{} dst:{}".format(src_basename, dst_basename))
                        else:
                            pu.mdbg.log("bkpevt.copy skipped due to same size, src:{} dst:{}".format(src_basename, dst_basename))
                    except:
                        shutil.copy(src,dst)
                        pu.mdbg.log("bkpevt.copy src:{} dst:{}".format(src_basename, dst_basename))
                                    
                # org -- shutil.copy(src,dst) #copy file
                
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
            dbg.prn(dbg.BKP|dbg.ERR,"[---]bkpevt.treecopy", e, sys.exc_info()[-1].tb_lineno)
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
            dbg.prn(dbg.BKP|dbg.ERR,"[---]bkpevt.cloudUpCopy src:",src,"resp:",resp, e, sys.exc_info()[-1].tb_lineno)
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
                try:
                    if (not os.path.islink(fullPath)):
                        self.copied += os.path.getsize(fullPath)
                    else:
                        dbg.prn(dbg.BKP,"path:{0} is skipped due to symbolic link".format(fullPath))
                        self.copied += 46
                        pass
                except:
                    pass
            #end for item
        except Exception as e:
            dbg.prn(dbg.BKP|dbg.ERR,"[---]bkpevt.webCopy", e, sys.exc_info()[-1].tb_lineno)
        self.onComplete()
    #end webCopy
    def restoreEvent(self):
        pass
    
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
            self.mounststat = 0
            self.ejectProgressCount = 0
            self.backupDrive = False
            self.ejectInProgress = False
            # start backup manager process
            tmr['backupmgr'] = TimedThread(self.process,period=3) #
            tmr['autobackp'] = TimedThread(self.autobackup,period=20) #run auto backup once every 10 minutes
        except Exception, e:
            dbg.prn(dbg.BKP|dbg.ERR,"bkpmgr.err:",e,sys.exc_info()[-1].tb_lineno)
    def add(self, hid, priority=0, dataOnly=False, auto = False, restore=False, cloud=False, remoteParams = {}):
        """ Add an event to the list of events to be backed up 
            Args:
                for arguments description, see backupEvent class constructor
            Returns:
                none
        """
        try:
            dbg.prn(dbg.BKP,"add-->", hid)
            if(hid in self.events):
                return #skip an event that was already added but not processed yet
            backupPath = False #this will be retrieved here
            if(restore):
                # restoring event, get its path on the backup drive
                if(not self.archivedEvents): #list of archived events wasn't created yet, create a new one
                    self.archivedEvents = self.archiveList()
                if(hid in self.archivedEvents): #check if the event that's being restored is in the list
                    backupPath = self.archivedEvents[hid]['archivePath']

            dbg.prn(dbg.BKP,"add backing up event:",hid, priority, dataOnly, auto, restore, backupPath, cloud, remoteParams)
            self.events[hid] = backupEvent(hid, priority, dataOnly, auto, restore, backupPath, cloud, remoteParams)

            if(not (priority in self.priorities)): #there are no events with this priority yet - add the priority
                self.priorities[priority] = [ ]
            self.priorities[priority].append(hid) #add event to the list of events with the same priority
        except Exception as e:
            dbg.prn(dbg.BKP|dbg.ERR,"[---]bkpmgr.add: ", e,sys.exc_info()[-1].tb_lineno)
    def archiveList(self):
        """ Get a list of all archived events with their paths 
            Args:
                none
            Returns:
                (dictionary)
        """
        try:
            dbg.prn(dbg.BKP,"archiveList-->")
            drives = pu.disk.list()
            if(len(drives)<1): #no drives available
                drives = pu.disk.list(dbg_print=True)
                dbg.prn(dbg.BKP,"no drives????:{}".format(drives))
                return {"entries":[]}# there are no events in the list
            self.archivedEvents = { } #clean the list of archived events for whomever needs to access it later
            events = []
            eventDirs = []
            dbg.prn(dbg.BKP,"starting list...")
            for drive in drives:
                if(not(os.path.exists(drive+backupEvent.autoDir) or os.path.exists(drive+backupEvent.manualDir))): #this drive does not have any pxp backups
                    dbg.prn(dbg.BKP,"starting list...{} {}".format(drive+backupEvent.autoDir, drive+backupEvent.manualDir))
                    continue
                # this drive contains a backup
                self.backupDrive = drive.decode('UTF-8')
                autoDirs = []
                manualDirs = []
                autoPath = self.backupDrive+backupEvent.autoDir
                manuPath = self.backupDrive+backupEvent.manualDir
                if(os.path.exists(autoPath)):# this drive contains automatic backups
                    autoDirs = os.listdir(autoPath) #get a list of directories (events) here
                if(os.path.exists(manuPath)):# this drive contains manually backed up events
                    manualDirs = os.listdir(manuPath) #get a list of those events
                allDirs = list(autoPath+x for x in autoDirs)
                allDirs.extend(manuPath+x for x in manualDirs if autoPath+x not in allDirs)
                eventDirs += allDirs
                dbg.prn(dbg.BKP,"starting list...{}".format(eventDirs))
            #end for drive in drives
            for eventDir in eventDirs:
                # get info about the events in each directory
                dbg.prn(dbg.BKP,"eventDir list...{}".format(eventDir))
                if(not os.path.exists(eventDir+'/event.json')):
                    continue
                try:
                    event = json.loads(pu.disk.file_get_contents(eventDir.encode('UTF-8')+'/event.json'))
                    event['archivePath']=eventDir.encode('UTF-8')
                    if ('evt_size' in event): #JCHOI:To prevent getting folder size, we use save info while backup was doing.
                        evtSize = event['evt_size']
                    else:
                        evtSize = pu.disk.dirSize(eventDir, dbg_print=True)
                        #time.sleep(30) #<<----------- if dirSize() takes too long, it will return NOTING...!!!
                    event['size']=pu.disk.sizeFmt(evtSize)
                    # check if this event is in the existing events on the hdd
                    event['exists']=os.path.exists(c.wwwroot+event['datapath'])
                    self.archivedEvents[event['hid']]=copy.copy(event) #save for later in case user wants to restore an event
                    events.append(event)
                except Exception as e:
                    dbg.prn(dbg.BKP|dbg.ERR,"[---]bkpmgr.for_eventdir:",e,sys.exc_info()[-1].tb_lineno)
            return events
        except Exception as e:
            dbg.prn(dbg.BKP|dbg.ERR,"[---]bkpmgr.archlist", e, sys.exc_info()[-1].tb_lineno)
    def autobackup(self):
        """ Automatically back up all events (if there's a drive with pxp-autobackup folder on it)"""
        try:
            #dbg.prn(dbg.BKP,"autobackup-->")
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
            self.backupDrive = False
            # look for which one to use for back up
            for drive in drives:
                if(not os.path.exists(drive+backupEvent.autoDir)): #this is not the auto-backup for pxp
                    continue
                self.backupDrive = drive.decode('UTF-8') #decoding is required for drives that may have odd mount points (e.g. cyrillic letters in the directory name)
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
                if(not self.backupDrive): 
                    return #did not find an auto-backup device - nothing to do if not backing up locally or to cloud

            # get all events in the system
            elist = pxp._listEvents(showDeleted=False)
            # go through all events that exist and verify that they're identical on the backup device
            for event in elist:
                if(not('datapath' in event)):
                    continue #this event does not have a folder with video/tags - nothing to do here
                #### local backup ####
                if(self.backupDrive):
                    # see if this event exists on the backup device
                    if(os.path.exists(self.backupDrive+backupEvent.autoDir+event['datapath'])):
                        # the event was already backed up
                        # check for differences in video (simple size check - less io operations)
                        vidSize = pu.disk.dirSize(c.wwwroot+event['datapath']+'/video')
                        bkpSize = pu.disk.dirSize(self.backupDrive+backupEvent.autoDir+event['datapath']+'/video')
                        if(bkpSize!=vidSize): #there's a mismatch in the video - backup the whole event again
                            self.add(hid=event['hid'],auto=True)
                        else:
                            # the video is identical, check data file
                            oldDb = self.backupDrive+backupEvent.autoDir+event['datapath']+'/pxp.db'
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
                        dbg.prn(dbg.ERR|dbg.BKP,"[---]autobackup.url:",response,e,sys.exc_info()[-1].tb_lineno)
                else: #this event doesn't exist in the cloud yet - upload it (video and metedata)
                    self.add(hid=event['hid'], priority=2, cloud=True)

            #end for event in elist
        except Exception as e:
            dbg.prn(dbg.ERR|dbg.BKP,"[---]bkpmgr.autobackup",e,sys.exc_info()[-1].tb_lineno)
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
            dbg.prn(dbg.BKP,"getCloudEvents-->")
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
            dbg.prn(dbg.BKP|dbg.ERR,"[---]bkpmgr.getCloudEvents: ", e, sys.exc_info()[-1].tb_lineno, response)
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
            #dbg.prn(dbg.BKP,"list-->")
            result = []
            events = copy.deepcopy(self.events)
            for hid in events:
                if(not(events[hid].remote or events[hid].restore) or incomplete):
                    result.append(hid)
        except Exception as e:
            dbg.prn(dbg.ERR|dbg.BKP,"[---]bkpmgr.list",e,sys.exc_info()[-1].tb_lineno)
        return result
    def process(self):
        """ Process the queue - start a backup according to priority, if there's nothing backed up at the moment, remove completed backups """
        try:
            #dbg.prn(dbg.BKP,"process-->")
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
            dbg.prn(dbg.ERR|dbg.BKP, "[---]bkpmgr.process",e,sys.exc_info()[-1].tb_lineno)
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
            dbg.prn(dbg.ERR|dbg.BKP,"[---]bkp.status:",e,sys.exc_info()[-1].tb_lineno)
        # this event was never backed up
        dbg.prn(dbg.ERR,"no status for ", hid)
        return [backupEvent.STAT_FAIL|backupEvent.STAT_NOBKP,0]
    def get_status(self):
        result = {}
        try:
            for hid in self.events:
                result[hid] = self.events[hid].statusFull()
            for hid in self.completed:
                result[hid] = self.completed[hid].statusFull()
        except Exception as e:
            dbg.prn(dbg.ERR|dbg.BKP,"[---]bkp.get_status:",e,sys.exc_info()[-1].tb_lineno)
        return result
    def get_status2(self):
        result = {}
        try:
            for hid in self.events:
                status = self.events[hid].statusFull()
                if (status[0]!=36): # STAT_NODRV + STAT_FAIL
                    result[hid] = self.events[hid].statusFull()
            for hid in self.completed:
                status = self.completed[hid].statusFull()
                if (status[0]!=36):
                    if (not hid in result):
                        result[hid] = self.completed[hid].statusFull()
        except Exception as e:
            dbg.prn(dbg.ERR|dbg.BKP,"[---]bkp.get_status2:",e,sys.exc_info()[-1].tb_lineno)
        return result
    def stop(self, stopAll = False):
        """ Stop copying current event
            Args:
                stopAll(bool): stop copying current event and clear the queue (no other events will be copied)
            Returns:
                none
        """
        try:
            dbg.prn(dbg.BKP,"stop-->")
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
            dbg.prn(dbg.ERR|dbg.BKP,"[---]bkpmgr.stop",e,sys.exc_info()[-1].tb_lineno)
    def ejectStatus(self):
        self.ejectProgressCount += 1
        return self.mounststat
    def unmountUsbDrive(self, cmd):
        import subprocess
        process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        out,err = process.communicate()
        return out, err
    def ejectDrive(self):
        try:            
            if (self.mounststat==1):
                self.ejectProgressCount = 0
                self.ejectInProgress = False
            if (self.ejectInProgress):
                pu.mdbg.log("----> USB DRIVE EJECT IN PROGRESS  STATUS-->{0}  {1}".format(self.backupDrive, self.mounststat))
                return
            self.ejectInProgress = True
            self.mounststat = 0
            self.ejectProgressCount = 0
            self.backupDrive = pu.disk.file_get_contents(c.curUsbDrv)    
            pu.mdbg.log("----> USB DRIVE EJECT STARTED-->{0}".format(self.backupDrive))
            #self.backupDrive = self.backupDrive.replace(' ', '\ ')        
            import subprocess
            #os.system('diskutil eject /Volumes/NO\ NAME')
            out = ''
            err = ''
            if (self.backupDrive):
                out,err = self.unmountUsbDrive(["diskutil", "eject", self.backupDrive])
                if (err.find("failed")>=0):
                    self.mounststat = 2
                    out1,err1 = self.unmountUsbDrive(["diskutil", "unmount", self.backupDrive])
                    pu.mdbg.log("----> USB DRIVE EJECT TRY 2 drv:{0} out:{1} err:{2}".format(self.backupDrive, out1, err1))
                    if (err1.find("failed")==0):
                        self.mounststat = 1
                        os.system('rm ' + c.curUsbDrv)
                    else:
                        out1,err1 = self.unmountUsbDrive(["diskutil", "unmount", "force", self.backupDrive])
                        pu.mdbg.log("----> USB DRIVE EJECT TRY 3 drv:{0} out:{1} err:{2}".format(self.backupDrive, out1, err1))
                        if (err1.find("failed")==0):
                            self.mounststat = 1
                            os.system('rm ' + c.curUsbDrv)
                        else:
                            os.system('diskutil eject ' + self.backupDrive)
                else:
                    self.mounststat = 1
                    os.system('rm ' + c.curUsbDrv)
                self.ejectInProgress = False
            else:
                self.mounststat = 0
                self.ejectInProgress = False
            pu.mdbg.log("----> USB DRIVE EJECT DONE--->drv:{0} | out:{1} | err:{2} | mounted:{3}".format(self.backupDrive, out, err, self.mounststat))
        except Exception as e:
            pu.mdbg.log("[---]  USB DRIVE EJECT STATUS-->drv:{0} | err:{1} | mounted:{2}".format(self.backupDrive, e, self.mounststat))
            self.ejectInProgress = False
            self.ejectProgressCount = 0
    def checkusbthere(self):
        try:
            drives = pu.disk.list()
            if(len(drives)<1): #no drives
                if (pu.pxpconfig.ShowUsbDriveMessage()):
                    drives = pu.disk.list(dbg_print=True)
                    dbg.prn(dbg.BKP,"checkusbthere-->not found any drives: {}".format(drives))
                return False
            for drive in drives:
                if(os.access(drive,os.W_OK)): #found a drive that has previous backups and write permissions
                    try:
                        driveInfo = pu.disk.stat(humanReadable=False,path=drive)
                        if(driveInfo['free']>1000000):
                            dbg.prn(dbg.BKP,"checkusbthere-->found drive:", drive)
                            self.backupDrive = drive
                            pu.disk.file_set_contents(c.curUsbDrv, self.backupDrive)
                            return True
                        else:
                            dbg.prn(dbg.BKP,"checkusbthere-->found drive:{0} but not enough disk space (less than 1MB)".format(drive))
                    except:
                        pass
            return False
        except Exception as e:
            dbg.prn(dbg.BKP,"[---]checkusbthere-->", e)
            return False
        
#####################################
# MP4 Restore from Transport Streams                
#####################################

def doExportEvent(event_path, camid, vq):
    result = {}
#     if(enc.code & enc.STAT_LIVE):
#         pu.mdbg.log("Cannot continue due to live event in progress...")
#         result['success'] = False
#         return result
    if (export_event.add(event_path.strip(), camid.strip(), vq.lower().strip())):
        export_event.run()
        result['success'] = True
    else:
        result['success'] = False
    return result

def doMP4Fix(event_path, camid, vq):
    result = {}
    if(enc.code & enc.STAT_LIVE):
        pu.mdbg.log("Cannot continue due to live event in progress...")
        result['success'] = False
        return result
    if (mp4builder.add(event_path.strip(), camid.strip(), vq.lower().strip())):
        mp4builder.run()
        result['success'] = True
    else:
        result['success'] = False
    return result
    #pxpTTKiller(pxpmisc.tmr_misc)

class mp4fix(object):
    def __init__(self):
        pass
    def doMP4Fix(self, event_path, camid, vq):
    #         if (self.vq=="*"):
    #             self.vq = ['hq', 'lq']
    #         else:
    #             self.vq = [vq]
    #         if (self.camid=="*"):
    #             self.camid = []
    #             for i in xrange(4):
    #                 self.camid.append(str(i).zfill(2))
    #         else:
    #             self.camid = [camid]  
        mp4builder = pxpmisc.MP4Rebuilder()
        mp4builder.add('2015-12-15_10-56-07_e293d70b661c18032d1b5efe7b206f1f67c8da01_local', "00", "hq")
        mp4builder.add('2015-12-15_10-56-07_e293d70b661c18032d1b5efe7b206f1f67c8da01_local', "00", "lq")
        mp4builder.run()
        time.sleep(60)
        pxpTTKiller(pxpmisc.tmr_misc)
    #         pxpCleanup()
    #         appRunning = False
    #         exit()    
    pass


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
        dbg.prn(dbg.ECN, "delete files: ", rmFiles)
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
        dbg.prn(dbg.ERR|dbg.ECN,"[---]deleteFiles", e, sys.exc_info()[-1].tb_lineno)

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
##################
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
        dbg.prn(dbg.ECN|dbg.ERR,"[---]oldLiveCleanup:",e,sys.exc_info()[-1].tb_lineno)

####################################################
############ pxpservice control classes ############
####################################################

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
            dbg.prn(dbg.DBG,"executing: ", cmd)
            dataParts = cmd.split('|')
            if(dataParts[0]=='STR' and len(dataParts)>=2): #start encode
                srcMgr.encCapStart(dataParts[1])
            if(dataParts[0]=='STK' and len(dataParts)>=2): # write duration
                pu.mdbg.log("check status starting ======> {}".format(dataParts[1]))
                srcMgr.checkStat(dataParts[1])
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
            if(dataParts[0]=='VIT' and len(dataParts)>3): #change bitrate
                # data is in format VIT|<video_input_type>|<camID>
                srcMgr.setVideoInputType(dataParts[1],dataParts[2])
            if(dataParts[0]=='BTR' and len(dataParts)>3): #change bitrate
                # data is in format BTR|<bitrate>|<camID>
                srcMgr.setBitrate(dataParts[1],dataParts[2])
            if(dataParts[0]=='BKP'): #manual backup event
                backuper.add(hid=dataParts[1],priority=5)
            if(dataParts[0]=='RRE'): #restore event 
                backuper.add(hid=dataParts[1],priority=10,restore=True) #restoring events have higher priority over backups (to prevent restore-backup of the same event)
#             if(dataParts[0]=='FIX' and len(dataParts)>2): # rebuild (fix) mp4
#                 return doMP4Fix(dataParts[1], dataParts[2], dataParts[3]) # event_path, camid, vq
            if(dataParts[0]=='LVL'): # set log level
                dbg.setLogLevel(dataParts[1])
            if(dataParts[0]=='LOG'): # set logging to file on/off
                if (len(dataParts)>=2):
                    dbg.setLog(dataParts[1])
        except Exception as e:
            dbg.prn(dbg.CMD|dbg.ERR,"[---]cmd._exc", e, sys.exc_info()[-1].tb_lineno)
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

class rtmpmgr:
    STAT_RTMP_UNKNOWN        = 0
    STAT_RTMP_INITIALIZED    = 1<<0 #RTMP is initializing (pxpservice just started)
    STAT_RTMP_READY          = 1<<1 #RTMP is ready to start an event
    STAT_RTMP_STOPPED        = 1<<2 #live event is stopping
    STAT_RTMP_STARTED        = 1<<3 #live event starting
    STAT_RTMP_NOCAM          = 1<<4 #no camera found
    status = "unknown"
    code = 0
    lastWritten = 0  #last status code that was written to file (to make sure we don't write same thing over and over)
    rtmp_stat = {}
    def __init__(self):
        self.rtmp_cast = {} # rtmp in the system
        self.max_rate = 2048 # K
        self.bufsize = 6000  # K
        self.gopinterval = 50 # seconds 
        code = self.STAT_RTMP_INITIALIZED
        status = self.statusTxt(code)
        self.rtmp_stat["00"] = status
        
    def test_rtmp(self):
        # ffmpeg -re -i main.mp4 -vcodec libx264 -preset veryfast -maxrate 2048k -bufsize 6000k -pix_fmt yuv420p -g 50 -acodec libmp3lame -b:a 128k -ac 2 -ar 44100 -f flv "rtmp://fso.dca.16FC7.kappacdn.net/2016FC7/default/pxp_stream?q2AQk11cirtoT8Rv&adbe-live-event=playxplay"
        mp4_file = "main.mp4" 
        rtmp_node = '"rtmp://fso.dca.16FC7.kappacdn.net/2016FC7/default/pxp_stream?q2AQk11cirtoT8Rv&adbe-live-event=playxplay"'   
        rtmp_streaming = c.ffbin+" -re -i " + mp4_file +" -vcodec libx264 -preset veryfast -maxrate 2048k -bufsize 6000k -pix_fmt yuv420p -g 50 -acodec libmp3lame -b:a 128k -ac 2 -ar 44100 -f flv " + rtmp_node

    def stop(self, src):
        procMan.pstop(name="RTMP_cast_"+src)
        code = self.STAT_RTMP_STOPPED
        status = self.statusTxt(code)
        self.rtmp_stat[src] = status           
    
    def get_rtmp_cast(self, src, svr_node):
        src = 'rtsp://192.168.2.194/media/video1'
        pp = '"rtmp://fso.dca.16FC7.kappacdn.net/2016FC7/default/pxp_stream?q2AQk11cirtoT8Rv&adbe-live-event=playxplay"'
        ffcmd = 'ffmpeg -i ' + src + ' -vcodec libx264 -preset veryfast -maxrate 2048k -bufsize 6000k -pix_fmt yuv420p -g 50 -acodec libmp3lame -b:a 128k -ac 2 -ar 44100 -f flv ' 
        ffcmd += '"'+ svr_node + '"'
        if (not self.busy()):
            procMan.padd(name="RTMP_cast_"+src, devID=src, cmd=ffcmd, keepAlive=True, killIdle=True, forceKill=True, threshold=5)
            code = self.STAT_RTMP_STARTED
            status = self.statusTxt(code)
            self.rtmp_stat[src] = status
        return ffcmd

    def busy(self):
        return self.code & (self.STAT_RTMP_STARTED)

    def statusSet(self,statusBit,autoWrite=True):
        try:
            self.code = statusBit
            self.status = self.statusTxt(self.code)
            if(autoWrite):
                self.statusWrite()
        except Exception as e:
            dbg.prn(dbg.ERR|dbg.ENC,"[---]rtmp.statusSet",e, sys.exc_info()[-1].tb_lineno)

    def statusTxt(self, statusCode):
        if(statusCode & self.STAT_RTMP_INITIALIZED):
            return 'initialized'
        if(statusCode & self.STAT_RTMP_NOCAM):
            return 'no camera'
        if(statusCode & self.STAT_RTMP_STOPPED):
            return 'stopped'
        if(statusCode & self.STAT_RTMP_STARTED):
            return 'started'
        if(statusCode & self.STAT_RTMP_READY):
            return 'ready'
        return 'unknown'

    def statusUnset(self,statusBit, autoWrite = True):
        try:
            self.code = self.code & ~statusBit
            self.status = self.statusTxt(self.code)
            if(autoWrite):
                self.statusWrite()
        except Exception as e:
            dbg.prn(dbg.ERR|dbg.ENC,"[---]rtmpmgr.statusUnset",e, sys.exc_info()[-1].tb_lineno)

    def statusWrite(self):
        if(self.lastWritten==self.code):
            return
        try:
            with open(c.rtmpStatFile,"wb") as f:
                f.write(json.dumps({"status":self.status.replace("\"","\\\""), "code":self.code}))
            self.lastWritten = self.code
        except:
            pass

    def get_rtmp_stat(self):
        try:
            rtmp_stat = { "00": "stopped" }
            return self.rtmp_stat
        except Exception as e:
            dbg.prn(dbg.ERR|dbg.SRM, "[---]rtmpmgr.get_rtmp_stat", e, sys.exc_info()[-1].tb_lineno)
        return {}           

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
            
            if (statusBit==self.STAT_READY):
                x = 0    
                
            self.status = self.statusTxt(self.code)
            if(dbgLastStatus!=self.code): #only output if status changed
                dbg.prn(dbg.ENC,"enc_status: {:14s} {:016b}  written:{}".format(self.status, self.code, autoWrite))
                #dbg.prn(dbg.ENC,"status: ",self.status,' ',bin(self.code))
            if(autoWrite):
                self.statusWrite()
        except Exception as e:
            dbg.prn(dbg.ERR|dbg.ENC,"[---]enc.statusSet",e, sys.exc_info()[-1].tb_lineno)
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
            dbg.prn(dbg.ERR|dbg.ENC,"[---]enc.statusUnset",e, sys.exc_info()[-1].tb_lineno)
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

class appGlobal:
    _instance = None
    #-------------------------------    
    mainip = False
    #-------------------------------
    srcLen = 0
    launchedLive555Len = 0
    launchedCaptureLen = 0
    launchedSegmentLen = 0
    launchedRecorderLen = 0
    live555FailCount = 0
    captureFailCount = 0
    segmentFailCount = 0
    recordFailCount = 0
    #-------------------------------
    def __init__(self):
        pass
    def __new__(cls, *args, **kwargs):
        if not cls._instance:
            cls._instance = super(appGlobal, cls).__new__(cls, *args, **kwargs)
        return cls._instance
    def IsVideoStartSuccessfully(self):
        return True if self.srcLen == self.launchedLive555Len else False
    def IsCaptureStartSuccessfully(self):
        return True if self.IsVideoStartSuccessfully() and (self.srcLen==self.launchedCaptureLen) else False
    def IsEventStartSuccessfully(self):
        try:
            reclen = self.srcLen
            if (srcMgr.EVERY_RECS!=1):
                reclen = self.srcLen/srcMgr.EVERY_RECS
                if ((self.srcLen%srcMgr.EVERY_RECS)>0):
                    reclen += 1
        except:
            pass
        return True if self.IsCaptureStartSuccessfully() and (self.launchedRecorderLen==reclen) and (self.launchedCaptureLen==self.launchedSegmentLen)else False
    def updateVideoSourceCount(self, n):
        self.srcLen = n
    def updateFeedCount(self, n):
        self.launchedLive555Len = n
    def updateCaptureCount(self, n):
        self.launchedCaptureLen = n
    def updateRecorderCount(self, n):
        self.launchedRecorderLen = n
    def updateSegmentCount(self, n):
        self.launchedSegmentLen = n
    def updateMainIP(self,ip):
        self.mainip = ip
    def ResetFailCount(self):
        self.live555FailCount = 0
        self.captureFailCount = 0
        self.segmentFailCount = 0
        self.recordFailCount = 0

##############################
### encoder device classes ###
##############################

class proxydevice(object):
    """ Represents either serial device or telnet. (Only for Delta encoder for now)
    """
    def __init__(self, name="usbserial", dev=False, ip=False):
        """ initialize the class 
            Args:
                dev(serail device): 
        """
        self.serialport = dev
        self.dev_name = name
        self.dt_params = {'IP':False, 'MAC':False, 'FMT':False, 
                          'GEC':False, 'GVB':False, 'IMO':False, 'OCR':False, 'OIF':False, 'ORS':False, 
                          'ESM':False, 'EGL':False, 'ELI':False, 'EHI':False, 'ELP':False, 'EHP':False, 'EPF':False, 
                          'IAA':False, 'IMA':False,
                          'ILA':False, 'ILM':False, 'ILG':False,
                          'VTP':False, 'VCF':False, 'VIT':False ,'VCL':False, 'VDL':False, 'VFD':False,
                          'AMO':False, 'AIS':False, 'ACF':False, 'ACB':False 
                          }
        self.ip = ip
    def __repr__(self):
        return "<proxydevice> name:{dev_name}  serialport:{serialport}".format(**self.__dict__)
    def cmd_value(self, cmd):
        """ cmd should be the one which can return integer value. dt_params should also be filled before call this. 
            It is used with check_cmd in encDelta in most cases.
            Args:
                cmd(str): Delta command like (i.e 'VIT', 'IMO' etc...) 
            Returns:
                resp(integer): returns integer value in cached data. (0 returns if not found or inappropriate cases) 
        """
        try:
            cmdValue = self.dt_params[cmd.strip()]
            z=cmdValue.strip().split("=")
            if (len(z)>1):
                return int(z[1])
        except:
            return 0
        return 0

class encDevice(object):
    """ Template class for an encoder device. """
    def __init__(self, ip, vq, uid=False, pwd=False, realm=False, mac=False):
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
        self.vidquality     = vq
        self.serial         = False
        self.username       = uid   # 'root'    for now it is only for AXIS cam
        self.password       = pwd   # 'admin'   for now it is only for AXIS cam
        self.realm          = realm # "AXIS_ACCC8E0271D1"
        self.mac            = mac
        self.model          = False
        self.vit            = 0     # video input type (for Delta) 
        self.baseRTSPURL    = False
        self.dev_mp4path    = ""
        self.cur_evtpath    = "" # device mp4 recording need to know where it needs to move mp4 files.
    def __repr__(self):
        return "<encDevice> ip:{ip} mac:{mac} vq:{vidquality} uid:{username} pwd:{password} realm:{realm} fr:{framerate} br:{bitrate} url:{rtspURL} init:{initialized} on:{isOn}".format(**self.__dict__)
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
        #return c.ffbin+" -fflags +genpts -rtsp_transport tcp -i "+camURL+" -codec copy -f h264 udp://127.0.0.1:"+str(chkPRT)+" -codec libx264 -preset veryfast -maxrate 2048k -bufsize 6000k udp://127.0.0.1:"+str(camMP4)+" -codec copy -f mpegts udp://127.0.0.1:"+str(camHLS)
        mp4conf = pu.pxpconfig.capture_mp4_conf()
        if (mp4conf == "" or len(mp4conf)<10):
            mp4conf = "-codec copy -f mpegts"
        cap_conf = pu.pxpconfig.capture_conf()
        if (cap_conf == "" or len(cap_conf)<=5):
            cap_conf = c.fifo_size
        #------------------------------------------------------
        protocol = "udp"
        latency = ""    
        if (pu.pxpconfig.use_tcp()):
            protocol = "tcp"
            latency = " -tune zerolatency"
        mp4entry = " udp://127.0.0.1:"
        if (pu.pxpconfig.use_mp4tcp()):
            mp4entry = " tcp://127.0.0.1:"
        capcmd = c.ffbin+" -i " + camURL + latency \
                + " -fflags +igndts -codec copy -f h264 udp://127.0.0.1:" + str(chkPRT) \
                + " -fflags +igndts " + mp4conf + mp4entry + str(camMP4) \
                + " -fflags +igndts -codec copy -f mpegts udp://127.0.0.1:" + str(camHLS) #+ cap_conf

#        capcmd = c.ffbin+" -fflags +igndts -rtsp_transport " + protocol + " -i " + camURL + latency \
#                 + " -fflags +igndts -codec copy -f h264 udp://127.0.0.1:" + str(chkPRT) \
#                 + " -fflags +igndts " + mp4conf + mp4entry + str(camMP4) \
#                 + " -fflags +igndts -codec copy -f mpegts udp://127.0.0.1:" + str(camHLS) + cap_conf
        # AXIS 4K
        #capcmd = c.ffbin+" -fflags +genpts -rtsp_transport " + protocol + " -i " + camURL + latency \
        #        + " -fflags +genpts -codec copy -f h264 udp://127.0.0.1:" + str(chkPRT) \
        #        + " -fflags +genpts " + mp4conf + mp4entry + str(camMP4) \
        #        + " -fflags +genpts -codec copy -f mpegts udp://127.0.0.1:" + str(camHLS) + cap_conf
        # Delta Only        
#         capcmd = "/Users/dev/works/cpp/ffmpeg/ffmpeg -fflags +igndts -rtsp_transport " + protocol + " -i " + camURL \
#                 + " -fflags +igndts -codec copy -map 0:v -f mpegts udp://127.0.0.1:" + str(chkPRT) \
#                 + " -fflags +igndts -codec copy -map 0:v -f mpegts " + mp4entry + str(camMP4) \
#                 + " -fflags +igndts -codec copy -map 0:v" \
#                 + " -vf drawtext=\"fontfile=/Library/Fonts/Arial.ttf: timecode='00\:00\:00\:00':r=24.976:x=10:y=10:fontsize=62:fontcolor=lightgreen: box=1: boxcolor=0x00000099\"" \
#                 + " -f mpegts" \
#                 + "     -c:v libx264 -preset ultrafast -tune zerolatency -r 29 -s 720x480 -pix_fmt yuv420p -b:v 1000k -minrate 1000k -maxrate 1000k -bufsize 1835k" \
#                 + "     -x264opts keyint=50:bframes=0:ratetol=1.0:ref=1 -profile main -level 3.1" \
#                 + "     -c:a copy" \
#                 + " udp://127.0.0.1:" + str(camHLS) + "?pkt_size=1316"
        return capcmd
    def discover(self):
        """ To implement in device-specific class """
        pass
    def setVideoInputType(self, vit):
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
    def setCred(self, uid, pwd, realm=False):
        self.username = uid
        self.password = pwd
        self.realm = realm
    def setModel(self, xmlurl, modelToFind, keyName):
        try:
            modelname = False                    
            serial = False    
            doc = pu.io.xmlurl(xmlurl, timeout=10)
            if (doc):
                isModel = False
                for el in doc.iter():
                    #------------
                    # orig
                    #------------
#                     if (el.text.upper().find(modelToFind)<0):
#                         continue    
#                     else:
#                         isModel = True
#                         break
                    if (el.text == None):
                        continue
                    elif (el.text.upper().find(modelToFind)<0):
                        continue
                    else:
                        isModel = True
                        break
                if (isModel):
                    serialnumber = doc.find('./{urn:schemas-upnp-org:device-1-0}device/{urn:schemas-upnp-org:device-1-0}serialNumber')
                    serial = serialnumber.text 
                    # modelName or modelDescription or friendlyName
                    model = doc.find('./{urn:schemas-upnp-org:device-1-0}device/{urn:schemas-upnp-org:device-1-0}'+keyName)
                    modelname = model.text 
            return serial, modelname
        except Exception as e: 
            dbg.prn(dbg.ENC|dbg.ERR, "[---]setModel",e, sys.exc_info()[-1].tb_lineno)
            serial = False
            modelname = False
            return serial, modelname
    def updatedb(self):
        try:
            success = False

            if (isinstance(self.bitrate, str) and self.bitrate.find('n/a')>=0):
                self.bitrate = 0
            if (isinstance(self.framerate, str) and self.framerate.find('n/a')>=0):
                self.framerate = 0            
            # type conversion !!!
            if (isinstance(self.bitrate, str)):
                self.framerate = int(self.bitrate)
            if (isinstance(self.framerate, str)):
                self.framerate = int(self.framerate)

            url = self.rtspURL
            #url = url.replace('?','\?')
            

            db = pu.db(c.wwwroot+"_db/pxp_main.db")
            sql = "SELECT * FROM `camsettings` WHERE `ip`=? AND `vq`=?"
            success = db.query(sql,(self.ip, self.vidquality))
            if(success and len(db.getasc())>0):
                sql = "UPDATE `camsettings` SET `mac`=?, `bitrate`=?, `framerate`=?, `name`=?, `rtspurl`=? WHERE `ip`=?  AND `vq`=?"
                success = db.query(sql,(self.mac, self.bitrate, self.framerate, self.model, url, self.ip, self.vidquality))
            else:
                sql = "INSERT INTO `camsettings` (`mac`, `name`, `ip`, `vq`, `bitrate`, `framerate`, `rtspurl`) VALUES(?,?,?,?,?,?,?)"
                success = db.query(sql, (self.mac, self.model, self.ip, self.vidquality, self.bitrate, self.framerate, url))
            db.close()
            return success
        except Exception as e:
            dbg.prn(dbg.AXS|dbg.ERR, "[---]enc.updatedb",e, sys.exc_info()[-1].tb_lineno)
            return False
    def getcamdb(self):
        bitrate = 0
        framerate = 0
        try:
            success = False
            db = pu.db(c.wwwroot+"_db/pxp_main.db")
            sql = "SELECT * FROM `camsettings` WHERE `ip`=? AND `vq`=?"
            success = db.query(sql,(self.ip, self.vidquality))
            camsettings = db.getasc()
            if(success and len(camsettings)>0):
                for camsetting in camsettings:
                    ip = camsetting['ip']
                    vq = camsetting['vq']
                    bitrate = camsetting['bitrate']
                    framerate = camsetting['framerate']
            db.close()
            return bitrate, framerate
        except Exception as e:
            dbg.prn(dbg.AXS|dbg.ERR, "[---]enc.getcamdb",e, sys.exc_info()[-1].tb_lineno)
            return bitrate, framerate
    def startRec(self):
        pass        
    def stopRec(self):
        pass        
    def setRecordPath(self, mp4_path="", evt_path=""):
        self.dev_mp4path = mp4_path
        self.cur_evtpath = evt_path
        pass

class encIPcam(encDevice):
    """
    Generic IP camera class:
    Currently it supports only manually configured camera. For this to be used all of camera settings should be configured 
    from the camera admin page. All of necessary parameters of camera such as IP, MAC, stream URL should be provided 
    from the configuration file (pxpconfig). When the number of camera is zero, it is regarded as no camera found. 
    (ipc_count, ipc_ILA1, ipc_MAC1 etc)
    """
    def __init__(self, ip=False, vq="HQ", uid=False, pwd=False, realm=False, mac=False):
        """
        Read all of camera parameters from the pxpconfig and load into the config params for immitating camera discovery.
        Inputs:
            ip(str): camera IP
            vq(str): "HQ" or "LQ"
            uid(str): user id (not used)
            pwd(str): password (not used)
            realm(str): camera commnication realm (not used)
            mac(str): MAC address separated by ':'
        Returns:
            None
        """
        self.ccBitrate = False # can change bitrate
        self.model = "IPCam"
        self.manual_search_try_count = 0
        self.ipcam_device_list = []
        self.findingInProgress = False
        self.IPCamConfig = {}
        self.camIndex = False
        if(ip):
            super(encIPcam,self).__init__(ip, vq, uid=uid, pwd=pwd, realm=realm, mac=mac)
            ipcam_count = pu.pxpconfig.ipcam_conf(cmd='count')
            for i in range(ipcam_count):
                self.IPCamConfig['MAC'] = pu.pxpconfig.ipcam_conf(i+1,'MAC')
                self.IPCamConfig['IP']  = pu.pxpconfig.ipcam_conf(i+1,'ILA')
                self.IPCamConfig['URI'] = pu.pxpconfig.ipcam_conf(i+1,'URI')    
                if (ip==self.IPCamConfig['IP'].strip()):
                    self.camIndex = i
                    break
            if (0<=self.camIndex and self.camIndex<ipcam_count):    
                self.IPCamConfig['MASK']    = pu.pxpconfig.ipcam_conf(0,'ILM')
                self.IPCamConfig['GATEWAY'] = pu.pxpconfig.ipcam_conf(0,'ILG')        
                self.IPCamConfig['RES']     = pu.pxpconfig.ipcam_conf(0,'RES')        
    def find_manually(self):
        # Limit to apply setting after the discovery begins: max 6 times
        if (self.manual_search_try_count > 5):
            return self.ipcam_device_list
        # Inialize the device list...
        self.ipcam_device_list = []
        ipcam_found = {}
        self.manual_search_try_count += 1
        try:
            # Read the network params from the config file and apply them.
            ipcam_count = pu.pxpconfig.ipcam_conf(cmd='count')
            for i in range(ipcam_count):
                ipcam_found = {}
                ipcam_found['MAC']     = pu.pxpconfig.ipcam_conf(i+1, 'MAC')
                ipcam_found['IP']      = pu.pxpconfig.ipcam_conf(i+1, 'ILA')
                ipcam_found['URI']     = pu.pxpconfig.ipcam_conf(i+1, 'URI')
                ipcam_found['MASK']    = pu.pxpconfig.ipcam_conf(0, 'ILM')
                ipcam_found['GATEWAY'] = pu.pxpconfig.ipcam_conf(0, 'ILG')        
                # Add this device into device list so discovery can use this.
                already_found = False
                for d in self.ipcam_device_list:
                    if ('MAC' in d and d['MAC'] == ipcam_found['MAC']):
                        already_found = True
                if (not already_found and len(ipcam_found)>0):
                    self.ipcam_device_list.append(ipcam_found)
                # Final message dump for clarification.
                dbg.prn(dbg.IPC, "-->ipc.find_ipcam_manually...index:{}".format(i))
                time.sleep(2)
        except Exception as e:
            if (self.manual_search_try_count<0):
                self.manual_search_try_count -= 1
            dbg.prn(dbg.IPC|dbg.ERR, "[---]ipc.find_ipcam_manually error:", e, sys.exc_info()[-1].tb_lineno)
        return self.ipcam_device_list
    def discover(self, callback): # 'self' is not defined until it hits __init__, do not use self.XXX class attributes
        """ Find any new devices using bonjour protocol. 
            Args:
                callback(function): called when a device is found 
            Returns:
                none
            Automatic discovery is not supported for this camera and only manual setting will be used.
            This is just an place holder to 
        """
        try:
            if(enc.code & enc.STAT_SHUTDOWN):
                return
            if(enc.code & enc.STAT_LIVE):
                dbg.prn(dbg.IPC, "encIPCam.discovery is disabled due to live mode...")
                return
            if (self.findingInProgress):
                dbg.prn(dbg.IPC, "ipc.find_ipcam: skipped...")
                return
            self.findingInProgress = True
            self.manual_search = pu.pxpconfig.ipcam_conf(cmd='count') > 0
            if (self.manual_search):
                dev_found = self.find_manually()
                dbg.prn(dbg.IPC, "encIPCam.discovering...with manual settings...cam_count:{}".format(len(dev_found)))
                if (dev_found and len(dev_found)>0):
                    for found in dev_found:
                        ipcam_MAC = found['MAC']
                        serial_no = ""       # 071D3F0D8D4D
                        modelname = "ipcam"  # IPD-D41C02-BS series     
                        devIP = found['IP'] 
                        if(not devIP): # did not get ip address of the device
                            continue
                        params = self.getParams(devIP) # not used, get all the parameters from the IPcam's home page
                        if(found['IP'] and found['MAC']):
                            output = {}
                            output['ip'] = devIP
                            output['type'] = 'dc_enc'
                            output['port'] = 554
                            output['url'] = "rtsp://"+found['URI'] # "rtsp://"+devIP+"/stream1"
                            output['devClass'] = encIPcam
                            output['vid-quality'] = 'HQ'
                            output['username'] = False 
                            output['password'] = False 
                            output['realm'] = False
                            output['mac'] = found['MAC'] 
                            output['model'] = "IPCam" + "." + output['vid-quality'] + "." + devIP
                            callback(output)
            self.findingInProgress = False
        except Exception as e:
            dbg.prn(dbg.IPC|dbg.ERR,"[---]encIPcam.discover",e, sys.exc_info()[-1].tb_lineno)
    def getParams(self,ip=False, vq='HQ'):
        """ Gets new parameters from a generic IP device
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
        try:
            if ('IP' in self.IPCamConfig and 'URI' in self.IPCamConfig):
                if(not ip):
                    ip = self.IPCamConfig['IP']
                params['rtsp_url'] = self.IPCamConfig['URI']
                rtsp_ip, rtsp_port = self.parseURI(params['rtsp_url'])
                params['streamBitrate'] = 1000
                params['rtsp_port'] = rtsp_port
                params['connection'] = True
                if ('RES' in self.IPCamConfig and self.IPCamConfig['RES'].find("x")>=0):
                    params['inputResolution'] = self.IPCamConfig['RES'].split("x")[1]
                else:
                    params['inputResolution'] = "1080?p25"
                if ('RES' in self.IPCamConfig and self.IPCamConfig['RES'].find("p")>=0):
                    params['streamResolution'] = self.IPCamConfig['RES'].split("p")[1]
                else:
                    params['streamResolution'] = "25?"
        except Exception as e:
            dbg.prn(dbg.IPC|dbg.ERR,"[---]encIPCam.getParams",e,sys.exc_info()[-1].tb_lineno)
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
        try:
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
        except Exception as e:
            dbg.prn(dbg.IPC|dbg.ERR,"[---]encIPCam.parseURI",e,sys.exc_info()[-1].tb_lineno)
        return ip, port
    def setVideoInputType(self, vit):
        self.vit = vit
    def setBitrate(self,bitrate):
        """ Set device bitrate is in kbps 
            Args:
                bitrate(int): new bitrate in kbps
            Returns:
                (str): response from the url request
        """
        try:
            result = False
            dbg.prn(dbg.IPC,"IPC.setbitrate: Cannot change: bitrate:{} ip:{}".format(bitrate, self.ip))
            return result
        except Exception as e:
            dbg.prn(dbg.ERR|dbg.IPC,"[---]IPC.setBitrate:", e, sys.exc_info()[-1].tb_lineno)
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
            dbg.prn(dbg.IPC,"IPC.setframerate: framerate:{} ip:{} vq:{}".format(framerate, self.ip, self.vidquality))
            return result
        except Exception as e:
            dbg.prn(dbg.ERR|dbg.IPC,"[---]IPC.setFramerate:", e, sys.exc_info()[-1].tb_lineno)
        return result
    def update(self):
        """ Requests encoding parameters of the device and updates local class properties"""
        # get the device parameters
        try:
            if(enc.code & enc.STAT_SHUTDOWN): #exit immediately if there's a shutdown going on
                return
            params = self.getParams(vq=self.vidquality)
            # dbg.prn(dbg.IPC, params, "IPC.update")
            if(params and params['connection']):
                self.resolution = params['inputResolution']
                self.isCamera = self.resolution!=False
                self.bitrate = params['streamBitrate']
                self.framerate = params['streamFramerate']
                self.rtspURL = params['rtsp_url']
            else:
                dbg.prn(dbg.IPC,"update FAIL!")
                self.isOn = False
                self.isCamera = False
                self.resolution = False
                self.bitrate = False
                self.framerate = False
                self.rtspURL = False
                self.initialized = False
        except Exception as e:
            dbg.prn(dbg.IPC|dbg.ERR,"[---]encIPcam.update",e, sys.exc_info()[-1].tb_lineno)
    def startRec(self):
        pass        
    def stopRec(self):
        pass        
            
class encAxis(encDevice):
    def __init__(self, ip=False, vq="HQ", uid=False, pwd=False, realm=False, mac=False):
        super(encAxis,self).__init__(ip, vq, uid="root", pwd="admin", realm=realm, mac=mac)               
        if(ip):
            self.ccBitrate = True
            self.model = "AXIS"            
    def discoverBonjour(self, callback):
        def discovered(results):
            recs = pu.bonjour.parseRecord(results['txtRecord'])
            output = {}
            if(recs['sm']=='AXS'):
                return
            if(not 'sn' in recs): #this happens for Teradek Clip
                recs['sn']='media'
            streamURL = recs['sm'].lower()+'://'+results['ip']+":"+str(results['port'])+'/'+recs['sn']
            # check if this is a preview or a full rez stream
            if(recs['sn'].lower().find('quickview')>=0):# this is a preview stream
                output['preview']=streamURL
                output['preview-port']=results['port']
                output['vid-quality'] = 'LQ'
            else:
                output['url']=streamURL
                output['port'] = results['port']
                output['vid-quality'] = 'HQ'
            output['ip'] = results['ip']
            output['type'] = "td_cube"
            output['devClass'] = encTeradek
            callback(output)        
        pu.bonjour.discover(regtype="_axis-video._tcp", callback=discovered)
    def discover(self, callback): # Axis
        try:
            if(enc.code & enc.STAT_SHUTDOWN):
                return
            global sockCmd
            global devaddingnow
            dbg.prn(dbg.AXS, "-->Start looking for AXIS camera.....")
            
            #to find ALL ssdp devices simply enter ssdp:all as the target
            devs  = pu.ssdp.discover(text="Portable SDK",field='server',case=True) # why Portable SDK??!!
            if(len(devs)>0):
                for devLoc in devs:
                    try:
                        dev = devs[devLoc]                               
                        self.serial, self.model = self.setModel(dev.location, 'AXIS', 'modelName')
                        if (self.serial):
                            self.realm = 'AXIS_' + self.serial
                            
                        if (pu.mdbg.checkscf(sockCmd, pu.SCF_SHOWBONJ)):
                            dbg.prn(dbg.AXS, "-->AXIS:recs-->{0}".format(dev))
                            
                        devIP, devPT = self.parseURI(dev.location)
                        if(not devIP): #did not get ip address of the device
                            continue
                        params = self.getParams(devIP) #get all the parameters from axis camera
                        if(params and params['rtsp_url'] and params['rtsp_port']):
                            output = {}
                            output['ip'] = devIP
                            output['type'] = 'sn_axis'
                            output['url'] = params['rtsp_url']
                            output['port'] = params['rtsp_port']
                            output['devClass'] = encAxis
                            output['vid-quality'] = 'HQ'
                            output['username'] = 'root'
                            output['password'] = 'admin'
                            output['realm'] = self.realm
                            output['mac'] = params['MACAddress']

                            if (not pu.pxpconfig.virtual_lq_enabled()):
                                output['model'] = self.model + "." + output['vid-quality'] + "." + output['ip']
                                callback(output)
                            else:
                                for i in xrange(2):
                                    iter1=5
                                    while (devaddingnow and iter1>=0):
                                        time.sleep(200)
                                        iter1 -= 1                                                                                                                           
                                    if (i==0):
                                        output['model'] = self.model + "." + output['vid-quality']
                                        callback(output)
                                        # prepare fake LQ cam URL for the next addition
                                        # rtsp://root:admin@192.168.2.102:554/axis-media/media.amp?videocodec=jpeg&resolution=640x480&date=1&clock=1&text=1
                                        lowq_port = output['port']
                                        lowq_url = "rtsp://" + devIP + ":" + str(output['port']) + "/axis-media/media.amp?videocodec=h264&resolution=640x480&date=0&clock=0&text=0"
                                        if 'url' in output:
                                            del output['url']  
                                        if 'port' in output:
                                            del output['port']  
                                        output['preview']=lowq_url
                                        output['preview-port']=lowq_port
                                        output['vid-quality'] = 'LQ'
                                    else:
                                        output['model'] = self.model + "." + output['vid-quality'] + "." + output['ip']
                                        callback(output)
                                # for xrange(2)
                            # WantFakeLQ
                    except Exception as e: #may fail if the device is invalid or doesn't have required attributes
                        dbg.prn(dbg.AXS|dbg.ERR, "[---]encAXIS.discover",e, sys.exc_info()[-1].tb_lineno)
#            else:
#                dbg.prn(dbg.AXS|dbg.ERR, "encAXIS.NOT FOUND")
        except Exception as e:
            dbg.prn(dbg.AXS|dbg.ERR,"[---]encAXIS.discover",e, sys.exc_info()[-1].tb_lineno)
    def getSerial(self, usn):
        try:
            s = ''
            i = usn.find('::') # get serial number
            if ((i-1)>=0):
                for c in usn[i-1::-1]:
                    if (c.isalnum()):
                        s += c
                    else:
                        break
                return s[::-1]
            return False
        except Exception as e:
            dbg.prn(dbg.AXS|dbg.ERR,"[---]encAXIS.getSerial",e, sys.exc_info()[-1].tb_lineno)
            return False        
    def getParams(self,ip=False,realm=False): # Axis
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
            params['rtsp_url']='rtsp://'+ip+'/axis-media/media.amp?videocodec=h264'
            rtspParams = pu.io.dgturl('http://'+ip+'/axis-cgi/view/param.cgi?action=list&group=Network.RTSP',timeout=10, username=self.username, password=self.password, realm=self.realm)
            if(rtspParams):
                if(len(rtspParams)>=1):
                    params['rtsp_port']=int(rtspParams['root.Network.RTSP.Port'])
                    rtspParams = pu.io.dgturl('http://'+ip+'/axis-cgi/view/param.cgi?action=list&group=Image.I0',timeout=10, username=self.username, password=self.password, realm=self.realm)
                    if(rtspParams):
                        if(len(rtspParams)>1):
                            res = rtspParams['root.Image.I0.Appearance.Resolution'].split('x')
                            if (self.username): # login required
                                if(rtspParams['root.Image.I0.RateControl.Mode']=='cbr'): # cbr/vbr mode??
                                    params['streamBitrate']=rtspParams['root.Image.I0.RateControl.TargetBitrate']
                                else:
                                    params['streamBitrate']=rtspParams['root.Image.I0.RateControl.MaxBitrate'] #for VBR mode, the max allowed bitrate, use max allowed bitrate
                                if (rtspParams['root.Image.I0.Stream.FPS']!="0"):
                                    params['streamFramerate']=rtspParams['root.Image.I0.Stream.FPS']
                                else:
                                    params['streamFramerate']="30"
                                ethParams = pu.io.dgturl('http://'+ip+'/axis-cgi/view/param.cgi?action=list&group=Network.eth0',timeout=10, username=self.username, password=self.password, realm=self.realm)
                                if(len(ethParams)>=1):
                                    params['MACAddress'] = ethParams['root.Network.eth0.MACAddress']
                            else: #login not required
                                params['streamFramerate']="30"
                            params['inputResolution']=res[1]+'p'+params['streamFramerate']
                            params['streamResolution']=res[1]+'p'                                
                            params['connection']=True
        except Exception as e:
            dbg.prn(dbg.AXS|dbg.ERR,"[---]encAxis.getParams", e, sys.exc_info()[-1].tb_lineno)
        return params
    def parseURI(self,url):
        """AXIS extracts ip address and port from a uri.
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
    def setVideoInputType(self, vit):
        self.vit = 0
    def setBitrate(self,bitrate):
        result = True
        # bypassed by request from Ivan
        if (pu.pxpconfig.IgnoreVideoSettings()):
            dbg.prn(dbg.AXS,"axs -- setBitrate BYBASSED")
            return True
        try:
            if (self.ccBitrate):
                self.bitrate = bitrate # kbps i.e 2000, 5000
                self.updatedb()  
                dbg.prn(dbg.AXS,"axis.setbitrate:", bitrate, self.ip)
            return result
        except Exception as e:
            dbg.prn(dbg.ERR|dbg.AXS,"[---]axis.setBitrate:", e, sys.exc_info()[-1].tb_lineno)
            result = False
        return result
    def setFramerate(self,framerate):
        result = True
        # bypassed by request from Ivan
        if (pu.pxpconfig.IgnoreVideoSettings()):
            dbg.prn(dbg.TDK,"axs -- setFramerate BYBASSED")
            return True
        try:
            if (self.ccFramerate):
                self.framerate = framerate
                self.updatedb()  
                dbg.prn(dbg.AXS,"axis.setframerate:",framerate, self.ip)
            return result
        except Exception as e:
            dbg.prn(dbg.ERR|dbg.AXS,"[---]axis.setFramerate:", e, sys.exc_info()[-1].tb_lineno)
            result = False
        return result
    def update(self):
        """ AXIS Requests encoding parameters of the device and updates local class properties"""
        if(enc.code & enc.STAT_SHUTDOWN): #exit immediately if there's a shutdown going on
            return
        # get the device parameters
        params = self.getParams()
        # dbg.prn(dbg.AXS, params, "AXIS.update")
        if(params and params['connection']):
            self.resolution = params['inputResolution']
            self.isCamera = self.resolution!=False
            self.bitrate = params['streamBitrate']
            self.framerate = params['streamFramerate']
            self.rtspURL = params['rtsp_url']
        else:
            dbg.prn(dbg.AXS,"update FAIL!")
            self.isOn = False
            self.isCamera = False
            self.resolution = False
            self.bitrate = False
            self.framerate = False
            self.rtspURL = False
            self.initialized = False
    def startRec(self):
        pass        
    def stopRec(self):
        pass        
    
class encTeradek(encDevice):
    """ Teradek device management class """
    def __init__(self, ip=False, vq="HQ", uid=False, pwd=False, realm=False, mac=False):
        if(ip):
            super(encTeradek,self).__init__(ip, vq, uid=uid, pwd=pwd, realm=realm, mac=mac)
            self.ccBitrate      = True # can change bitrate
            self.ccFramerate    = True # can change framerate
            self.ccResolution   = True # can change resolution
            self.tdSession      = None # reference to the login session on the teradek
            self.model = "TERADEK"
    def discover(self, callback):
        """ Find any new devices using bonjour protocol. 
            Args:
                callback(function): called when a device is found 
            Returns:
                none
        """
        if (pu.mdbg.checkscf(sockCmd, pu.SCF_SHOWBONJ)):
            dbg.prn(dbg.MN, "-->Start looking for TDK camera.....")
        def discovered(results):
            global sockCmd
            global devaddingnow

            if (pu.mdbg.checkscf(sockCmd, pu.SCF_SHOWBONJ)):
                dbg.prn(dbg.MN, "--> TDK camera found.....")

            recs = pu.bonjour.parseRecord(results['txtRecord'])
            if (pu.mdbg.checkscf(sockCmd, pu.SCF_SHOWBONJ)):
                dbg.prn(dbg.MN,"-->Teradek:recs-->{}".format(results))
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
                if (not pu.pxpconfig.virtual_lq_enabled()):
                    dbg.prn(dbg.MN,"-->Teradek: LQ disabled")
                    return
                output['preview']=streamURL
                output['preview-port']=results['port']
                output['vid-quality'] = 'LQ'
            else:
                output['url']=streamURL
                output['port'] = results['port']
                output['vid-quality'] = 'HQ'
            output['ip'] = results['ip']
            output['type'] = "td_cube"
            output['devClass'] = encTeradek
            output['username'] = False
            output['password'] = False
            output['realm'] = False
            output['mac'] = False
            output['model'] = 'TERADEK.' + output['vid-quality'] + "." + output['ip']
            if (pu.mdbg.checkscf(sockCmd, pu.SCF_SHOWBONJ)):
                dbg.prn(dbg.MN, "TDK output:", output)
            iter1=5
            while (devaddingnow and iter1>=0):
                time.sleep(200)
                iter1 -= 1
            callback(output) #addDevice
        #end discovered
        pu.bonjour.discover(regtype="_tdstream._tcp", callback=discovered)
    #end discover
    def getParam(self, response,parameter,dbg1=False):
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
            if (not lines):
                dbg.prn(dbg.MN, "split failed")
            if (dbg1):
                dbg.prn(dbg.MN, response)
            if(len(lines)<1 or not(isinstance(lines,list))):
                return False #wrong response type
            for line in lines:
                if (line==''):
                    continue
                parts = line.split("=")
                if (dbg1):
                    dbg.prn(dbg.MN, "parts:{}".format(parts))
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
            dbg.prn(dbg.MN, "[---]encTeradek.getParam:", e, sys.exc_info()[-1].tb_lineno)
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
        self.username = "admin"
        self.password = "admin"
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
    def getmac(self):
        # http://172.18.2.101/cgi-bin/api.cgi?command=get&q=System.Info.Product&q=Network.Interfaces.Eth0.macaddress
        try:
            if (not self.ip):
                return ""
            url = "http://"+self.ip+"/cgi-bin/api.cgi"
            if(not self.tdSession):
                self.login()
            dbg.prn(dbg.TDK, "getmac-->ip:{} session:{}".format(self.ip, self.tdSession))
            curl = url
            if (self.tdSession):
                curl = url + "?session="+str(self.tdSession)
            url = curl
            dbg.prn(dbg.TDK, "getmac:.....................................")
            setcmd = "&q=System.Info.Product&q=Network.Interfaces.Eth0.macaddress"
            # set the frame rate
            dbg.prn(dbg.TDK, "getting...mac")
            answer = False
            attempts = 0
            while((not answer) and attempts<3):
                cmd = url+"&command=get"+setcmd
                answer = pu.io.url(cmd, timeout=10)
                attempts +=1
                dbg.prn(dbg.TDK, "TDK-->macurl=", cmd)
            if(not answer):
                return False
            if (len(answer)>20):
                ans = answer
                x = self.getParam(answer, 'macaddress', dbg1=False)
                answer = x
            return answer
        except Exception as e:
            dbg.prn(dbg.TDK|dbg.ERR, "[---]encTeradek.getmac:", e, sys.exc_info()[-1].tb_lineno)
            return False
        return False
    def setVideoInputType(self, vit):
        self.vit = 0
    def setBitrate(self, bitrate):
        """ Set teradek bitrate is in kbps 
            Args:
                bitrate(int): new bitrate in kbps
            Returns:
                none
        """
        try:
            # bypassed by request from Ivan
            if (pu.pxpconfig.IgnoreVideoSettings()):
                dbg.prn(dbg.TDK,"td -- SetBitrate BYBASSED")
                return
        
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
            iter1=5
            answer = False
            while(not answer and iter1>=0):
                answer = pu.io.url(url+"&command=set"+setcmd,timeout=10)
                iter1 -= 1
            dbg.prn(dbg.TDK,answer)
            # apply settings
            dbg.prn(dbg.TDK,"applying...")
            iter1=5
            answer = False
            while(not answer and iter1>=0):
                answer = pu.io.url(url+"&command=apply"+savecmd,timeout=10)
                iter1 -= 1
            dbg.prn(dbg.TDK,answer)
            # save the settings
            dbg.prn(dbg.TDK,"saving...")
            iter1=5
            answer = False
            while(not answer and iter1>=0):
                answer = pu.io.url(url+"&command=save"+savecmd,timeout=10)
                iter1 -= 1
            dbg.prn(dbg.TDK,answer)
            self.updatedb()  
            dbg.prn(dbg.TDK,"td_cube.setbitrate:", bitrate, self.ip)            
        except Exception as e:
            dbg.prn(dbg.TDK|dbg.ERR,"[---]encTeradek.setBitrate:", e, sys.exc_info()[-1].tb_lineno)
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
            # bypassed by request from Ivan
            if (pu.pxpconfig.IgnoreVideoSettings()):
                dbg.prn(dbg.TDK,"td -- setFramerate BYBASSED")
                return True
            
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
            dbg.prn(dbg.TDK|dbg.ERR, "[---]encTeradek.setFramerate:", e, sys.exc_info()[-1].tb_lineno)
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
            macurl = "&command=get&q=Network" 
            response = pu.io.url(url+macurl, timeout=15)
            if (response):
                self.mac = self.getParam(response,'macaddress')
            else:
                self.mac = False
            
            url2= "&command=get&q=VideoInput.Info.1.resolution&q=VideoEncoder.Settings.1.framerate&q=VideoEncoder.Settings.1.bitrate&q=VideoEncoder.Settings.1.use_native_framerate&q=VideoInput.Capabilities.1.framerates"
            tdk_url = url+url2
            response = pu.io.url(tdk_url, timeout=15)
            if(not response): #didn't get a response - timeout?
                dbg.prn(dbg.TDK, "no response from: ",url+url2)
                self.tdSession = None #this will cause if(self.tdSession) to fail on the next run of update(), which will cause RTSP to be restarted, and if it can't, the device will be removed from the system
                return False
            self.resolution = self.getParam(response,'resolution')
            self.framerate = int(self.getParam(response,'framerate'))
            bitrate = self.getParam(response,'bitrate') #this is in bps
            self.nativerate = self.getParam(response,'use_native_framerate')
            res = self.getParam(response,'framerates')
            if (res):
                self.allrates  = res.split(',')
            self.isCamera = self.resolution and not (self.resolution.strip().lower()=='vidloss' or self.resolution.strip().lower()=='unknown')
            if(not self.isCamera):
                self.resolution = 'n/a'
            intBitrate = 0
            if(bitrate):#convert bitrate to kbps
                try:
                    intBitrate = int(bitrate)
                    intBitrate = int(intBitrate / 1000)
                except:
                    intBitrate = 0
            # set bitrate for the settings page
            self.bitrate = intBitrate
            if (pu.mdbg.checkscf(sockCmd, pu.SCF_SHOWBONJ)):
                dbg.prn(dbg.MN, "-->TDK:recs_parsed-->ip:{}.{} bitrate:{} framerate:{} resolution:{}".format(self.ip, self.vidquality, self.bitrate, self.framerate, self.resolution))
        except Exception as e:
            dbg.prn(dbg.TDK|dbg.ERR, "[---]td.update:",e,sys.exc_info()[-1].tb_lineno)
    def startRec(self):
        pass        
    def stopRec(self):
        pass        

class encDelta(encDevice):
    """ Delta 4480E SD/HD Encoder device management class
        proxydevice class is always comes together to complete the functiionalities.
    """
    def __init__(self, ip=False, vq="HQ", uid=False, pwd=False, realm=False, mac=False):
        try:
            super(encDelta,self).__init__(ip, vq, uid=uid, pwd=pwd, realm=realm, mac=mac)
            self.delta = serial.Serial()
            self.dev_name = "/dev/cu.usbserial"
            self.serport = 1
            self.ccBitrate      = True # can change bitrate
            self.ccFramerate    = False # can change framerate
            self.ccResolution   = False # can change resolution
            self.tdSession      = None # reference to the login session on the teradek
            self.model = "Delta"
            self.dt_params = {}
            self.avformat = ["Not Locked","720x480i29","720x576i25","1280x720p50","1280x720p59","1280x720p60","1920x1080i25","1920x1080i29",
                             "1920x1080i30","1920x1080p25","1920x1080p29","1920x1080p30","1920x1080p50","1920x1080p59","1920x1080p60",
                             "640x480p60","800x600p60","1024x768p60","1280x1024p60"]
            self.findingInProgress = False
            self.manual_search = True
            self.manual_search_try_count = 0
            self.delta_device_list = []
            self.dev = False
        except Exception as e:
            dbg.prn(dbg.DLT|dbg.ERR, "[---]dt.__init__:",e,sys.exc_info()[-1].tb_lineno)
    def set_dtparams(self, params):
        for v in params:
            self.dt_params[v] = params[v] 
    def telnet_cmd(self, ip, cmd=False):
        """
        Once the given telnet command is executed, it updates self.dt_params 
            Args:
                ip(str): ip formatted in string
                cmd(str): Delta encoder command
            Returns:
                success(bool): returns False or True 
        """
        success = False
        try:
            if (ip):
                tn = telnetlib.Telnet(ip) # use telnet interface to retrieve the params
                time.sleep(0.3)
                ans = tn.read_until("OK>")
                if (not cmd):
                    tn.write("GST\r\n")
                else:
                    tn.write(cmd.strip()+"\r\n")
                time.sleep(0.3)
                ans = tn.read_very_eager()
                if (ans.find("OK>")>0):
                    tmp_params = ans.strip().split("\r\n")
                    for param in tmp_params:
                        if (param.find("=")>=0):
                            k = param.strip().split("=")[0]
                            if (not k in self.dt_params):
                                self.dt_params[k] = param # update self.dt_params
                elif (ans.find("E1>")>=0 or ans.find("E0>")>=0 or ans.find("E2>")>=0):
                    success = False
                tn.close()
                return True
        except Exception as e:
            dbg.prn(dbg.DLT|dbg.ERR, "[---] dt.telnet_cmd err:{} at {}".format(e, sys.exc_info()[-1].tb_lineno))
        return success
    def readresp(self, dev=False):
        """ read command response from the serial port device (telnet never use this method) 
            Args:
                dev(serial.Serial): usb serial device
            Returns:
                s(str): returned string from the device 
        """
        if (not dev):
            return ''
        try:
            #dbg.prn(dbg.MN, "dt.readresp started")
            s = ''
            count = 0
            while count<10:
                bytesToRead = dev.inWaiting()
                if (bytesToRead>0):
                    count = 0
                    z = dev.read(bytesToRead)
                    s += z
                    if (s.find("OK>")>=0 or z==''):
                        break
                else:
                    count += 1
                    time.sleep(0.2)
                    #dbg.prn(dbg.MN, "dt.readresp count:", count)
            if (count>=10):
                dbg.prn(dbg.MN, "dt.readresp timeout err:", dev)
            return s
        except (serial.SerialException, Exception) as e:
            dbg.prn(dbg.DLT|dbg.ERR, "[---] dt.readresp err:{} at {}".format(e, sys.exc_info()[-1].tb_lineno))
            return False
        return True
    def telnet_sendcmd(self, ip, cmd):
        resp = []
        sleep_time1 = 0.1
        sleep_time2 = 0.2
        for i in range(3):
            tn = telnetlib.Telnet(ip) 
            time.sleep(sleep_time1)
            ans = tn.read_until("OK>")
            tn.write(cmd+"\r\n")
            time.sleep(sleep_time2)
            ans = tn.read_very_eager() # "\r\nIMA=00:0f:5b:04:60:6b\r\nOK>"
            resp = ans.strip().split("\r\n")    
            tn.close()
            if (resp[0]!=''):
#                 if (i>0):
#                     dbg.prn(dbg.DLT, "dt.telnet_sendcmd try success...{} ip:{} cmd:{} resp:{}".format(i, ip, cmd, resp))
                return resp    
            else:
                sleep_time1 += 0.2
                sleep_time2 += 0.2
#                 dbg.prn(dbg.DLT, "[-->] dt.telnet_sendcmd try again...{} ip:{} cmd:{} resp:{}".format(i, ip, cmd, resp))
                time.sleep(0.2)
        dbg.prn(dbg.DLT, "[-->] dt.telnet_sendcmd error... ip:{} cmd:{} resp:{}".format(ip, cmd, resp))
        return resp
    def sendcmd(self, dev, cmd, multiline=False):
        """ send given command to usb serial device  
            Args:
                dev(proxydevice or serial.Serial): serial device
                cmd(str): delta command
                multiline(bool): response can have multiple lines 
            Returns:
                resp(str): returned string from the device 
        """
        resp = []
        try:
            if (self.manual_search):
                if (not dev):
                    ip = self.ip
                else:
                    ip = dev.ip
                if (not ip):
                    return resp
                if (cmd.find('VIT=')>=0): # debug only
                    dbg.prn(dbg.DLT, "[VIT sending...]")
                resp = self.telnet_sendcmd(ip, cmd)
            else:
                if (type(dev)!=serial.serialposix.Serial):
                    serialport = dev.serialport
                else:
                    serialport = dev
                serialport.write(cmd+"\r\n")
                resp = self.readresp(serialport).strip().split("\r\n")    # "\r\nIMA=0\r\nOK>"
            # process command response....    
            if (resp[0]==''):
                dbg.prn(dbg.DLT, "[-->] dt.sendcmd error cmd:{} resp:{} dev:{}".format(cmd, resp, dev))
                return resp[0] # error
            setcmd = cmd.split("=")
            if (resp[len(resp)-1][0]=='E'):
                self.dt_params[setcmd[0]] = resp[len(resp)-1] # error
                dbg.prn(dbg.DLT, "[-->] dt.sendcmd error cmd:{} resp:{} dev:{}".format(cmd, resp, dev))
                return resp[len(resp)-1]
            if (resp[len(resp)-1]=="OK>"):
                pass
            if (multiline):
                s = ""
                for i in xrange(len(resp)-1):
                    s += resp[i]
                    s += "\r\n"
                return s.strip()    
        except (serial.SerialException, Exception) as e:
            dbg.prn(dbg.DLT, "[---] dt.sendcmd cmd:{} resp:{} dev:{} err:{} at:{}".format(cmd, resp, dev, e, sys.exc_info()[-1].tb_lineno))
        return resp[0]
    def updatecmd(self,dev,cmd):
        """ Update dt_params in proxydevice by reading the param from the device.  
            Args:
                dev(proxydevice): usb serial device
                cmd(str): delta command 
            Returns:
                boolean(result): True or False (success/fail in sending command) 
        """
        try:
            setcmd = cmd.split("=")
            if (setcmd[0]=='MAC' or setcmd[0]=='IP'):
                if (len(setcmd)>1):
                    dev.dt_params[setcmd[0]] = setcmd[1]
                return True
            ans = self.sendcmd(dev,setcmd[0])
            if (dev.dt_params[setcmd[0]] != ans):
                dev.dt_params[setcmd[0]] = ans
                if (self.manual_search):
                    resp = self.sendcmd(dev, cmd)
                else:
                    resp = self.sendcmd(dev.serialport, cmd)
                if (cmd.find("=")>0): # send set command i.e OCR=3000
                    if (resp.find("OK>",0)>=0):
                        return True
                elif (len(resp.split("="))==2): # read param as response i.e IMA=00:0f:5b:04:60:6b
                    return True
            else:
                return True
        except (serial.SerialException, Exception) as e:
            dbg.prn(dbg.DLT|dbg.ERR, "[---] dt.updatecmd cmd:{} dev:{} err:{} at:{}".format(cmd, dev, e, sys.exc_info()[-1].tb_lineno))
        return False
    def closePort(self,dev):
        try:
            if (not self.manual_search):
                dev.close()
        except:
            pass
    def check_cmd(self,dev,cmd):
        """
        Retruns given command value (response) from the device
        """
        if (not self.updatecmd(dev, cmd)): 
            dbg.prn(dbg.DLT|dbg.ERR, "dt.check_cmd error in ",cmd)
        else: # success
            return dev.cmd_value(cmd)
        return 0
    def parse_resp(self, cmd):
        """
        Get any value from the command response as string
        """
        if (cmd and len(cmd)>0 and cmd.find("=")>=0):
            scmd = cmd.strip().split("=")
            if (len(scmd)>1):
                return scmd[1]
        return cmd
    def parse_int_resp(self, cmd):
        """
        Get integer value from the command response
        """
        if (cmd and len(cmd)>0 and cmd.find("=")>=0):
            scmd = cmd.strip().split("=")
            if (len(scmd)>1):
                return int(scmd[1])
        return 0
    def parse_dtparam(self, cmd):
        if (cmd and len(cmd)>0 and cmd in self.dt_params):
            cmd = self.dt_params[cmd]
            return self.parse_int_resp(cmd)
        return 0
    def check_delta_stat(self, dev, VIT_auto_change=False):
        """
        Check if video feed is connected to the device. it checks if it is SDI or DVI first.
        It fills up FMT key in params. (resolution/fps)
        """
        try:
            is_valid = True
            if (not self.manual_search):
                is_valid = dev and dev.serialport 
            if (is_valid):
                elspsed_time = time.time()
                """
                The desired input is selected using the VIDEO INPUT.TYPE (VIT) command. If VIT=0,
                the CVBS/SDI input interface is selected. VIT=0 works in conjunction with the VIDEO
                INPUT (VCT) command, if VCT=0 CVBS is selected, VCT=1 selects SDI and VCT=2
                will make the unit Auto detect wheather the incoming video is CVBS or SDI. If VIT=1,
                the DVI input interface is selected.
                For test purposes, the user can select a test pattern in place of a live video input by
                setting VIT=2 to select the test pattern. The resolution of the test pattern is selected by
                the VIDEO INPUT.TEST PATTERN (VTP) command. See Table 2-1 for the list of
                supported VTP resolutions.                
                """
                #---------------------------------------------------------------------
                VIT_resp = self.check_cmd(dev,'VIT')
                VCL_resp = self.check_cmd(dev,'VCL')
                VDL_resp = self.check_cmd(dev,'VDL')
                if (VCL_resp==1): # CVBS/SDI LOCK Reports whether the CVBS/SDI input is connected and locked, 0 = Not Locked 1 = Locked
                    v = self.check_cmd(dev,'VCF')
                    if (v != 0): # CVBS/SDI FORMAT Reports the detected video resolution and frame rate
                        dev.dt_params['FMT'] = self.avformat[v]
                    else:
                        v = self.check_cmd(dev,'VTP') # video test pattern resolution
                        if (v > 0): 
                            dev.dt_params['FMT'] = self.avformat[v]
                    if (VIT_auto_change and self.vit == 3): 
                        self.sendcmd(dev, 'VIT=0') # change to SDI if DVI was used
                else:
                    if (VDL_resp==0): # DVI LOCK, 0 = Not Locked 1 = Locked
                        v = self.check_cmd(dev,'VTP')                          
                        if (v > 0): 
                            dev.dt_params['FMT']=self.avformat[v]
                        else:
                            dev.dt_params['FMT']="000x000p00"
                    else:
                        v = self.check_cmd(dev,'VFD')                         
                        if (v > 0): # VIDEO TEST PATTERN resolution and frame rate
                            dev.dt_params['FMT']=self.avformat[v]
                            if (VIT_auto_change and self.vit != 3): 
                                self.sendcmd(dev, 'VIT=3') # change to DVI if DVI was not used
                self.vit = self.check_cmd(dev,'VIT')
                elspsed_time = time.time() - elspsed_time
                dbg.prn(dbg.DLT, "dt.check_delta_stat: IP:{} VIT:{} VCL:{} VDL:{} elspsed_time:{} [secs]".format(dev.dt_params['IP'], self.vit, VCL_resp, VDL_resp, elspsed_time))
        except (serial.SerialException, Exception) as e:
            dbg.prn(dbg.DLT, "[---] dt.check_delta_stat err:{} at:{}".format(e, sys.exc_info()[-1].tb_lineno))
    def is_valid_ip(self, ip):
        if (not ip or ip.find("0.0.0.0")>=0):
            return False
        main_ip = appg.mainip.split(".")
        if (len(main_ip)<3):
            return False
        else:
            if (ip.find(main_ip[0])<0 or ip.find(main_ip[1])<0):
                return False
        return True
    def setRecommandedSettings(self, dev, IMO_cmd='IMO=1'):
        """ Update Delta device with recommanded settings. (Networks, Audio, TTY, Encoder, Test Pattern)
            Manual setting need to disable DHCP. 
            Args:
                dev(proxydevice): serial device
                IMO_cmd(str): use DHCP (0:fixed, 1:dhcp) 
            Returns:
                None 
        """
        # Recommanded Default Encoder Settings from Delta --------------------------------------------------
        # Change Slice Mode to full frame.
        # ESM - VIDEO ENCODE: SLICE MODE                 = 0 (FULL FRAME)
        # Change GOP Size to 60
        # EGL - VIDEO ENCODE: GOP LENGTH                 = 60
        # I-Frame Min Quant to 10
        # ELI - VIDEO ENCODE: I-FRAME MIN QUANT          = 10
        # I-Frame Max Quant to 36
        # EHI - VIDEO ENCODE: I-FRAME MAX QUANT          = 36
        # P-Frame Min Quant to 10
        # ELP - VIDEO ENCODE: P-FRAME MIN QUANT          = 10
        # P-Frame Max Quant to 36
        # EHP - VIDEO ENCODE: P-FRAME MAX QUANT          = 36
        try:
            if (self.manual_search):
                is_valid = True
                IMO_cmd = 'IMO=0'
            else:
                is_valid = dev and dev.serialport
            elspsed_time = time.time()
            if (is_valid):
                # Network settings
                if (not self.updatecmd(dev, IMO_cmd)):     # IMO  MODE  0=FIXED  1=DHCP (make this first so it cam re-new the ip while it is processing...)
                    dbg.prn(dbg.DLT, "dt.setRecommandedSettings error in IMO")
                if (not self.updatecmd(dev, "OCR=2000")):  # OCR  STREAM BITRATE (KBPS) 64 to 20000 (*6000)
                    dbg.prn(dbg.DLT, "dt.setRecommandedSettings error in OCR")
                if (not self.updatecmd(dev, "OIF=2")):     # OIF  INTERFACE     *0 = ETHERNET TS  1 = ETHERNET RTP  2 = ETHERNET RTP/RTSP]
                    dbg.prn(dbg.DLT, "dt.setRecommandedSettings error in OIF")
                if (not self.updatecmd(dev, "ORS=1")):     # ORS  REMOTE IP STREAM   0 = Disable *1 = Enable
                    dbg.prn(dbg.DLT, "dt.setRecommandedSettings error in ORS")
                # Audio Setting
                if (not self.updatecmd(dev, "AMO=3")):     # AMO AUDIO MODE *0 = OFF 1 = LEFT 2 = RIGHT 3 = BOTH
                    dbg.prn(dbg.DLT, "dt.setRecommandedSettings error in AMO")
                if (not self.updatecmd(dev, "AIS=2")):     # AIS INPUT SOURCE *0 = ANALOG INPUT 1 = TEST TONE 2 = SDI INPUT
                    dbg.prn(dbg.DLT, "dt.setRecommandedSettings error in AIS")
                if (not self.updatecmd(dev, "ACF=1")):     # ACF COMPRESSION FORMAT *0 = MPEG1 LAYER2  1 = ADPCM
                    dbg.prn(dbg.DLT, "dt.setRecommandedSettings error in ACF")
                if (not self.updatecmd(dev, "ACB=1")):     # ACB MPEG-1 LAYER 2 BIT RATE Total Rate when AMO=3 is: 128 kbps if ACB=0 192 kbps if ACB=1 384 kbps if ACB=2 *0 = 64 kbit/s 1 = 96 kbit/s 2 = 192 kbit/s
                    dbg.prn(dbg.DLT, "dt.setRecommandedSettings error in ACB")
                # TTY settings
                if (not self.updatecmd(dev, 'GEC=0')):  # CONTROL ECHO      *0 = Disable (No echo) 1 = Enable (Echo received characters)
                    dbg.prn(dbg.DLT, "dt.setRecommandedSettings error in GEC")
                if (not self.updatecmd(dev, 'GVB=0')):  # CONTROL VERBOSE   *0 = Disable (Quiet) 1 = Enable (Verbose)
                    dbg.prn(dbg.DLT, "dt.setRecommandedSettings error in GVB")
                # Encoder settings
                if (not self.updatecmd(dev, "EPF=1")):     # VIDEO PROFILE (H.264 only) *0 = Baseline Profile, 1 = Main Profile, 2 = High Profile 
                    dbg.prn(dbg.DLT, "dt.setRecommandedSettings error in EPF")
                if (not self.updatecmd(dev, "ESM=0")):     # SLICE MODE = 0 (FULL FRAME)
                    dbg.prn(dbg.DLT, "dt.setRecommandedSettings error in ESM")
                if (not self.updatecmd(dev, "EGL=60")):     # GOP Size to 60
                    dbg.prn(dbg.DLT, "dt.setRecommandedSettings error in EGL")
                if (not self.updatecmd(dev, "ELI=10")):     # I-Frame Min Quant to 10
                    dbg.prn(dbg.DLT, "dt.setRecommandedSettings error in ELI")
                if (not self.updatecmd(dev, "EHI=36")):     # I-Frame Max Quant to 36
                    dbg.prn(dbg.DLT, "dt.setRecommandedSettings error in EHI")
                if (not self.updatecmd(dev, "ELP=10")):     # P-FRAME MIN QUANT to 10
                    dbg.prn(dbg.DLT, "dt.setRecommandedSettings error in ELP")
                if (not self.updatecmd(dev, "EHP=36")):     # P-FRAME MAX QUANT to 36
                    dbg.prn(dbg.DLT, "dt.setRecommandedSettings error in EHP")
                # Test Pattern
#                 if (not self.updatecmd(dev, "VTP=5")):      # Test Pattern 720p60
#                     dbg.prn(dbg.DLT, "dt.setRecommandedSettings error in VTP")
                elspsed_time = time.time() - elspsed_time
                dbg.prn(dbg.DLT, "dt.setRecommandedSettings setting elspsed_time:{} [secs]".format(elspsed_time))
        except (serial.SerialException, Exception) as e:
            dbg.prn(dbg.DLT, "[---] dt.setRecommandedSettings dev:{} err:{} at:{}".format(dev, e, sys.exc_info()[-1].tb_lineno))
    def find_delta_manually(self):
        """
        This process assumes all of Delta encoder device(s) are ready to configure already before it runs this code.
        Without knowing the proper Delta encoder IP, following code cannot be run properly.
        This method ensures all of network parameters are configured properly and configure the device if is is not configured.
        Args:
            none 
        Returns:
            delta_found(list): all of devices found 
        """
        # Limit to apply setting after the discovery begins: max 6 times
        if (self.manual_search_try_count > 5):
            return self.delta_device_list
        # Inialize the device list...
        self.delta_device_list = []
        delta_found = {}
        self.manual_search_try_count += 1
        try:
            # Read the network params from the config file and apply them.
            delta_count = pu.pxpconfig.delta_conf(cmd='count')
            for i in range(delta_count):
                delta_found = {}
                mac_addr = pu.pxpconfig.delta_conf(i+1, 'MAC')
                delta_ip = pu.pxpconfig.delta_conf(i+1, 'ILA')
                delta_mask = pu.pxpconfig.delta_conf(0, 'ILM')
                delta_gateway = pu.pxpconfig.delta_conf(0, 'ILG')        
                # create telnet device 
                delta_found[mac_addr] = proxydevice(name='telnet', ip=delta_ip) # telnet device IP setting 
                delta_found['DEV'] = delta_found[mac_addr] 
                delta_found['MAC'] = mac_addr
                self.dt_params['MAC'] = mac_addr
                self.updatecmd(delta_found[mac_addr], "IP=" + delta_ip) 
                # fill self.dt_params ...
                self.telnet_cmd(ip=delta_ip)
                config_ILM = 'ILM='+delta_mask
                config_ILG = 'ILG='+delta_gateway
                config_ILA = 'ILA='+delta_ip
                config_IMA = 'IMA='+mac_addr
                config_IMO = "IMO=0"
                ILM_resp = ''
                ILG_resp = ''
                ILA_resp = ''
                ILA_resp = ''
                IMO_resp = ''
                # Check all of network parameters from the encoder and see it is already configured in the config file.
                IST_resp = self.sendcmd(delta_found[mac_addr], 'IST', multiline=True)
                found = 0
                for ist in IST_resp.split("\r\n"):
                    dbg.prn(dbg.DLT, "-->IST_resp:", ist)
                    if (ist==config_ILM):
                        found += 1
                    if (ist==config_ILG):
                        found += 1
                    if (ist==config_ILA):
                        found += 1
                    if (ist==config_IMO):
                        found += 1
                    if (ist==config_IMA):
                        found += 1
                if (found<5):
                    # encodeer is not set as expected, so apply the settings for now
                    ILM_resp = self.sendcmd(delta_found[mac_addr], config_ILM)    # set MASK
                    ILG_resp = self.sendcmd(delta_found[mac_addr], config_ILG)    # set GATEWAY
                    ILA_resp = self.sendcmd(delta_found[mac_addr], config_ILA)    # set IP address
                    IMO_resp = self.sendcmd(delta_found[mac_addr],'IMO=0')        # disable DHCP
                #-----------------------------------------------------            
                # Now we need to apply the required settings to stream the HLS video 
                self.setRecommandedSettings(delta_found[mac_addr])
                # Ensure updating MAC in dt_params 
                self.updatecmd(delta_found[mac_addr], "MAC="+mac_addr)
                # Check video connectivty. Mainly for VIT, VCL,VDL checking...
                self.check_delta_stat(delta_found[mac_addr])
                # Update the device parameters 
                self.getParams(ip=delta_found[mac_addr].dt_params['IP'])
                # Add this device into device list so discovery can use this.
                already_found = False
                for d in self.delta_device_list:
                    if ('MAC' in d and d['MAC'] == delta_found['MAC']):
                        already_found = True
                if (not already_found and len(delta_found)>0):
                    self.delta_device_list.append(delta_found)
                # Final message dump for clarification.
                dbg.prn(dbg.DLT, "-->dt.find_delta_manually...{}: IMO:{} ILA:{} MAC:{} ILM:{} ILG:{}".format(i, IMO_resp, ILA_resp, mac_addr, ILM_resp, ILG_resp))
                time.sleep(2) # prevent too frequent discovery happened. (sometimes this causes spawning 2 same proc)
        except Exception as e:
            if (self.manual_search_try_count<0):
                self.manual_search_try_count -= 1
            dbg.prn(dbg.DLT|dbg.ERR, "[---]dt.find_delta_manually error:", e, sys.exc_info()[-1].tb_lineno)
        return self.delta_device_list
    def find_delta(self):
        """ Find any new Delta devices using serial port check and create the delta_found list. It also set the recommanded encoder settings.
            Once the dt_params are filled, it must close the serial port.
            Args:
                none 
            Returns:
                delta_found(list): all of devices found 
        """
        import serial.tools.list_ports
        c = serial.tools.list_ports.comports()      
        delta_device_list = []
        delta_found = {}
        for i in xrange(len(c)):
            try:
                #usb device detected and check if it is serial device
                if (c[i].vid>0 and c[i].pid>0):
                    delta_found = {}
                    dbg.prn(dbg.DLT, "dt.find_delta trying...{}".format(c[i].device))
                    dev = serial.Serial()
                    dev.port = c[i].device
                    dev.baudrate = 9600                   # baud rate
                    dev.bytesize = serial.EIGHTBITS       # bits per bytes
                    dev.parity = serial.PARITY_NONE       # parity check: no parity
                    dev.stopbits = serial.STOPBITS_ONE    # stop bits
                    dev.timeout = 1                       # non-block read
                    dev.xonxoff = False                   # disable software flow control
                    dev.rtscts = False                    # disable hardware (RTS/CTS) flow control
                    dev.dsrdtr = False                    # disable hardware (DSR/DTR) flow control
                    dev.writeTimeout = 2                  # timeout for write
                    # make sure serial port is not taken by anyone
                    # try tty port
#                     dev_tty = c[i].device.replace("cu.", "tty.") 
#                     dev.port = dev_tty
#                     if (not dev.isOpen()):
#                         dev.open()
#                     dev.close()
                    # try cu port...again
                    dev.port = c[i].device
                    dev.open()
                    if dev.isOpen():
                        dev.flushInput()                 # flush input buffer, discarding all its contents
                        dev.flushOutput()                # flush output buffer, aborting current output and discard all that is in buffer
                        # set default settings (GEC,GVB,Encoder setting)
                            # GVR  VERSION INFO Displays software and PLD versions and build dates / times
                            # GDN  DEVICE NAME  Up to 64 Characters (*Device Name)
                            # IDF  SET DEFAULTS  Sets NETWORK parameters to the default settings
                            # GEC  CONTROL ECHO      *0 = Disable (No echo) 1 = Enable (Echo received characters)
                            # GVB  CONTROL VERBOSE   *0 = Disable (Quiet) 1 = Enable (Verbose)
                            # OCR  STREAM BITRATE (KBPS) 64 to 20000 (*6000)
                            # OIF  INTERFACE     *0 = ETHERNET TS  1 = ETHERNET RTP  2 = ETHERNET RTP/RTSP]
                            # ORS  REMOTE IP STREAM   0 = Disable *1 = Enable
                            # IMA  MAC ADDRESS
                            # IMO  MODE  0=FIXED  1=DHCP
                            # IAA  ASSIGNED ADDRESS (by DHCP)
                            # IAM  ASSIGNED SUBNET  X.X.X.X; where X = 0 - 255 (*255.0.0.0)
                            # IAG  ASSIGNED GATEWAY X.X.X.X; where X = 0 - 255 (*10.10.0.1)
                        resp = self.sendcmd(dev,'IMA')   # get MAC address
                        if (resp!=''):
                            mac=re.compile(r'([A-z0-9: -:\r\n\t>]*)([=][ ]*)(([0-9a-fA-F][0-9a-fA-F]:){5}([0-9a-fA-F][0-9a-fA-F]))', re.I)
                            g=mac.match(resp)
                            if ((g!=None) and (not self.mac)):
                                mac_addr = g.group(3)                            
                                delta_found['MAC'] = mac_addr
                                delta_found[mac_addr] = proxydevice(c[i].device, dev) # should be MAC
                                self.updatecmd(delta_found[mac_addr], "MAC="+mac_addr)
                                self.setRecommandedSettings(delta_found[mac_addr])
                                resp = self.sendcmd(delta_found[mac_addr],'IAA')   # get IP address
                                dbg.prn(dbg.DLT, "dt.find_delta IP:{} MAC:{} SVR_IP:{}".format(resp.split("=")[1], mac_addr, appg.mainip))
                                self.updatecmd(delta_found[mac_addr], "IP="+resp.split("=")[1]) 
                                self.check_delta_stat(delta_found[mac_addr])
                                if (pu.mdbg.checkscf(sockCmd, pu.SCF_SHOWBONJ)):
                                    dbg.prn(dbg.MN, "-->DELTA:Network settings-->\r\n", self.sendcmd(dev,"IST", True))
                                dbg.prn(dbg.DLT, "-->DELTA:serial device recs-->", delta_found[mac_addr].dt_params)
                                self.getParams(ip=delta_found[mac_addr].dt_params['IP'])
                                if (not self.is_valid_ip(resp.split("=")[1])):
                                    delta_found = False
                                else:
                                    if (not self.manual_search):
                                        # For some reason, DHCP in Delta encoder sometimes not started immediately, so this will kick the process in.
                                        self.sendcmd(delta_found[mac_addr], 'IMO=0')
                                        time.sleep(2)
                                        self.sendcmd(delta_found[mac_addr], 'IMO=1')
                                        time.sleep(2)
                                        dbg.prn(dbg.DLT, "-->DELTA: toggle IMO for starting...")
                        else: # IMA not respond
                            dbg.prn(dbg.DLT, "[-->] dt.find_delta: IMA not respond:", c[i].device)
                        dev.close()
                    else:
                        dbg.prn(dbg.DLT, "[-->] dt.find_delta: cannot open...", c[i].device)
                already_found = False
                for d in delta_device_list:
                    if ('MAC' in d and d['MAC'] == delta_found['MAC']):
                        already_found = True
                if (not already_found and len(delta_found)>0):
                    delta_device_list.append(delta_found)
            except (serial.SerialException, Exception) as e:
                dbg.prn(dbg.DLT|dbg.ERR, "[---]dt.find_delta error, check next one...:", e, sys.exc_info()[-1].tb_lineno)
                self.closePort(dev)
        return delta_device_list
    def discover(self, callback):
        """ Find any new devices using serial port or telnet access 
            Args:
                callback(function): called when a device is found 
            Returns:
                none
        """
        global devaddingnow
        try:
            if(enc.code & enc.STAT_SHUTDOWN):
                return
            if(enc.code & enc.STAT_LIVE):
                dbg.prn(dbg.DLT, "encDelta.discovery is disabled due to live mode...")
                return
            if (self.findingInProgress):
                dbg.prn(dbg.DLT, "dt.find_delta: skipped...")
                return
            self.findingInProgress = True
            self.manual_search = pu.pxpconfig.delta_conf(cmd='count') > 0
            if (self.manual_search):
                dev_found = self.find_delta_manually()
                dbg.prn(dbg.DLT, "encDelta.discovering...APPLYING MANUAL SETTINGS")
            else:
                dev_found = self.find_delta()
                dbg.prn(dbg.DLT, "encDelta.discovering...AUTOMATIC DISCOVERY")
            if (dev_found and len(dev_found)>0):
                for found in dev_found:
                    #delta = dev_found[found]
                    delta_MAC = found['MAC']
                    delta = found[delta_MAC]
                    try:
                        if (pu.mdbg.checkscf(sockCmd, pu.SCF_SHOWBONJ)):
                            dbg.prn(dbg.MN, "-->DELTA:recs-->", delta)
                        serial_no = "" 
                        modelname = "delta"       
                        self.set_dtparams(delta.dt_params)          
                        devIP = delta.dt_params['IP'] 
                        devPT = 0
                        if(not devIP): # did not get ip address of the device
                            continue
                        params = self.getParams(devIP) # not used, get all the parameters from the Delta's home page
                        if(delta.dt_params and delta.dt_params['IP'] and delta.dt_params['MAC']):
                            output = {}
                            output['ip'] = devIP
                            output['type'] = 'dt_enc'
                            output['url'] = "rtsp://"+devIP+"/stream1"
                            output['port'] = False
                            output['devClass'] = encDelta
                            output['vid-quality'] = 'HQ'
                            output['username'] = False 
                            output['password'] = False 
                            output['realm'] = False
                            output['mac'] = delta.dt_params['MAC'] 
                            output['model'] = "delta" + "." + output['vid-quality'] + "." + devIP
                            output['serialport'] = delta.dt_params
                            output['delta_dev'] = delta
                            callback(output)
#                             if (not pu.pxpconfig.virtual_lq_enabled()):
#                                 output['model'] = modelname + "." + output['vid-quality'] + "." + devIP
#                                 callback(output)
#                             else:
#                                 for i in xrange(2):
#                                     iter1=5
#                                     while (devaddingnow and iter1>=0):
#                                         time.sleep(200)
#                                         iter1 -= 1                                                                                                                           
#                                     if (i==0):
#                                         output['model'] = modelname + "." + output['vid-quality'] + "." + devIP
#                                         callback(output)
#                                         # prepare fake LQ cam URL
#                                         params = self.getParams(devIP, vq='LQ') #get all the parameters from the SONY's page
#                                         lowq_port = output['port']
#                                         lowq_url = params['rtsp_url'] #.replace('video1', 'video2')
#                                         if 'url' in output:
#                                             del output['url']  
#                                         if 'port' in output:
#                                             del output['port']  
#                                         output['preview']=lowq_url
#                                         output['preview-port']=lowq_port
#                                         output['vid-quality'] = 'LQ'
#                                     else:
#                                         output['model'] = modelname + "." + output['vid-quality'] + "." + devIP
#                                         callback(output)
                                    #end if i
                                #end for xrange(2)
                        #end if param                                    
                    except Exception as e: #may fail if the device is invalid or doesn't have required attributes
                        dbg.prn(dbg.SNC|dbg.ERR, "[---]encDelta.discover",e, sys.exc_info()[-1].tb_lineno)
                        self.findingInProgress = False
            else:
                dbg.prn(dbg.DLT, "None of Delta device is found.  dev_found:{}".format(dev_found))
        except Exception as e:
            dbg.prn(dbg.DLT|dbg.ERR, "[---]dt.discover:",e,sys.exc_info()[-1].tb_lineno)
            self.findingInProgress = False
        self.findingInProgress = False
    def getParams(self,ip=False, vq='HQ'):
        params = {
            "rtsp_url"          : False,
            "rtsp_port"         : False,
            "inputResolution"   : False,
            "streamResolution"  : False,
            "streamFramerate"   : False,
            "streamBitrate"     : False,
            "connection"        : False #whether there is connection with this device at all
        }
        try:
            if (not ip):
                ip = self.ip
            if (ip):
                tn = telnetlib.Telnet(ip) # use telnet interface to retrieve the params
                time.sleep(0.3)
                ans = tn.read_until("OK>")
                tn.write("GST\r\n")
                time.sleep(0.1)
                ans = tn.read_until("OK>")
                tmp_params = ans.strip().split("\r\n")
                for param in tmp_params:
                    if (param.find("=")>=0):
                        k = param.strip().split("=")[0]
                        if (k in self.dt_params):
                            self.dt_params[k] = param # update self.dt_params
                tn.close()
                VCL_value = 0
                VDL_value = 0
                if (self.dev):
                    self.check_delta_stat(self.dev, VIT_auto_change=True)
                else:
                    VCL_resp = self.telnet_sendcmd(ip, 'VCL')
                    VDL_resp = self.telnet_sendcmd(ip, 'VDL')
                    if (len(VCL_resp)>=1):
                        VCL_value = self.parse_int_resp(VCL_resp[0])
                    if (len(VDL_resp)>=1):
                        VDL_value = self.parse_int_resp(VDL_resp[0])
                #---------------------------------------------
                params['rtsp_url']='rtsp://'+ip+'/stream1'
                params['mac'] = False
                params['username'] = False
                params['password'] = False
                params['streamBitrate'] = "2000"
                if ('OCR' in self.dt_params and self.dt_params['OCR']!=False):
                    params['streamBitrate']=str(self.dt_params['OCR'].strip().split("=")[1])
                params['inputResolution']="721p31"
                params['streamResolution']="777"+'p'
                params['streamFramerate']="31"
                if ('FMT' in self.dt_params and self.dt_params['FMT']!=False):
                    if ('FMT' in self.dt_params and self.dt_params['FMT'] and self.dt_params['FMT'].find('x')>0):
                        params['inputResolution'] = self.dt_params['FMT'].split("x")[1] # "1920x720p30" --> "720p30"
                        if (self.dt_params['FMT'].find("p")>=0):
                            z = self.dt_params['FMT'].split("p")
                        if (self.dt_params['FMT'].find("i")>=0):
                            z = self.dt_params['FMT'].split("i")
                        params['streamResolution'] = z[0] # "720"+'p'
                        params['streamFramerate'] = z[1]  # "30"
                    else:
                        params['inputResolution'] = self.dt_params['FMT']
                params['vit'] = 0
                if ('VIT' in self.dt_params):
                    #vit_str = ["CVBS/SDI Auto Detect", "CVBS", "SDI", "DVI", "Test Pattern"]
                    params['vit'] = self.parse_dtparam('VIT')
                params['rtsp_port']=False
                params['connection']=True
            if ('FMT' in self.dt_params):
                dbg.prn(dbg.DLT, "dt.getParams ip:{} VIT:{} FMT:{} VCL:{} VDL:{} dt_params_len:{} mac:{}".format(ip, self.dt_params['VIT'], self.dt_params['FMT'], VCL_value, VDL_value, len(self.dt_params), self.dt_params['MAC']))
            else:
                dbg.prn(dbg.DLT, "dt.getParams ip:{} VIT:{} VCL:{} VDL:{} dt_params_len:{} mac:{}".format(ip, self.dt_params['VIT'], VCL_value, VDL_value, len(self.dt_params), self.dt_params['MAC']))
        except Exception as e:
            dbg.prn(dbg.DLT|dbg.ERR, "[---]dt.getParams:",e,sys.exc_info()[-1].tb_lineno)
        return params
    def getmac(self):
        try:
            if ('MAC' in self.dt_params):
                return self.dt_params['MAC']
        except Exception as e:
            dbg.prn(dbg.DLT|dbg.ERR, "[---]dt.getmac:",e,sys.exc_info()[-1].tb_lineno)
    def setVideoInputType(self, vit):
        """
        Set video input type (mainly to select SDI or DVI(HDMI) source)
        Args:
            vit(integer): 0:Auto, 1:CVBS, 2:SDI, 3:DVI, 4:Test Pattern 
        Returns:
            None        
        """
        try:
            if ('MAC' in self.dt_params and 'VIT' in self.dt_params and 'delta_dev' in self.dt_params): 
                dev = self.dt_params['delta_dev']
                self.sendcmd(dev, 'VIT='+str(vit))
                vit_str = ["CVBS/SDI Auto Detect", "CVBS", "SDI", "DVI", "Test Pattern"]
                for i in range(5):
                    dbg.prn(dbg.DLT, "dt.setVideoInputType[{}]:set to {}******************".format(self.ip, vit_str[vit]))
        except Exception as e:
            dbg.prn(dbg.DLT|dbg.ERR, "[---]dt.setVideoInputType:",e,sys.exc_info()[-1].tb_lineno)
            pass
    def setBitrate(self, bitrate):
        """
        Set bitrate in Delta encoder
        Args:
            bitrate(integer): 1000 base interger value. (i.e 1000,2000...) 
        Returns:
            None        
        """
        try:
            # At this moment, discovery already find the device IP, so now we can use telnet freely...
            tn = telnetlib.Telnet(self.ip)
            time.sleep(0.3)
            ans = tn.read_until("OK>")            
            tn.write("GST\r\n") # get all of params from the device
            time.sleep(0.3)
            ans = tn.read_until("OK>")
            params = ans.strip().split("\r\n")
            bitrate_set = False
            for param in params:
                if (param.find("OCR")>=0):
                    OCR = self.parse_resp(param)
                    if (OCR != bitrate):
                        tn.write("OCR="+str(bitrate).strip()+"\r\n") # update bitrate...
                        time.sleep(0.3)
                        ans = tn.read_until("OK>")
                        for i in range(10):
                            dbg.prn(dbg.DLT, "dt.setBitrate[{}]:set to {}******************".format(self.ip, str(bitrate)))
                        bitrate_set = True
                        break
            tn.close()
            if (not bitrate_set):
                dbg.prn(dbg.DLT, "Cannot set dt.bitrate to {}  params:{}".format(bitrate, params))
        except Exception as e:
            dbg.prn(dbg.DLT|dbg.ERR, "[---]dt.setBitrate:",e,sys.exc_info()[-1].tb_lineno)
    def setFramerate(self, framerate):
        try:
            pass
        except Exception as e:
            dbg.prn(dbg.DLT|dbg.ERR, "[---]dt.setFramerate:",e,sys.exc_info()[-1].tb_lineno)
    def update(self):
        try:
            if(enc.code & enc.STAT_SHUTDOWN): #exit immediately if there's a shutdown going on
                return
            params = self.getParams(vq=self.vidquality)
            if(params and params['connection']):
                self.resolution = params['inputResolution']
                self.isCamera = self.resolution!=False
                self.bitrate = params['streamBitrate']
                self.framerate = params['streamFramerate']
                self.rtspURL = params['rtsp_url']
                self.vit = params['vit']
            else:
                dbg.prn(dbg.DLT,"update FAIL!")
                self.isOn = False
                self.isCamera = False
                self.resolution = False
                self.bitrate = False
                self.framerate = False
                self.rtspURL = False
                self.initialized = False
                self.vit = 0
        except Exception as e:
            dbg.prn(dbg.DLT|dbg.ERR, "[---]dt.update:",e,sys.exc_info()[-1].tb_lineno)
    
class encMatrox(encDevice):
    """ Matrox device management class """
    def __init__(self, ip=False, vq="HQ", uid=False, pwd=False, realm=False, mac=False, isHDX=False):
        #encDevice.__init__(self, ip, vq, uid, pwd, realm, mac)
        if(ip):
            super(encMatrox,self).__init__(ip, vq, uid=uid, pwd=pwd, realm=realm, mac=mac)
        self.model = "MATROX"
        self.isHDX = isHDX
        self.ENC1 = False
        self.ENC2 = False
        self.RTSPStarted = False
    def discover(self, callback):
        """ Find any new devices using SSDP. 
            Args:
                callback(function): called when a device is found 
            Returns:
                none
        """
        global devaddingnow
        try:
            if(enc.code & enc.STAT_SHUTDOWN):
                return
            dbg.prn(dbg.MTX, "encMatrox.discovering...")
            #to find ALL ssdp devices simply enter ssdp:all as the target
            monarchs  = pu.ssdp.discover(text="monarch",case=False,field='st')
            if(len(monarchs)>0):
                dbg.prn(dbg.MTX, "found:",monarchs)
                # found at least one monarch 
                for devLoc in monarchs:
                    try:
                        dev = monarchs[devLoc]
                        if (dev.st.find('MonarchHDXUpnpDevice')>0):
                            self.isHDX = True
                            dbg.prn(dbg.MTX, "encMatrox.HDX found...{}".format(devLoc))
                        else:
                            self.isHDX = False
                            dbg.prn(dbg.MTX, "encMatrox.HD found...{}".format(devLoc))
                        serial, modelname = self.setModel(dev.location, 'MATROX', 'modelName')
                        self.model = modelname
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
                            output['vid-quality'] = 'HQ'
                            output['username'] = False
                            output['password'] = False
                            output['realm'] = False
                            output['mac'] = False
                            if (not self.isHDX):
                                output['model'] = modelname + "." + output['vid-quality'] + "." + devIP     
                                iter1=5
                                while (devaddingnow and iter1>=0):
                                    time.sleep(200)
                                    iter1 -= 1                                                                                                                                                      
                                callback(output)
                            else:
                                if (not pu.pxpconfig.virtual_lq_enabled()):
                                    output['model'] = modelname + "." + output['vid-quality'] + "." + devIP     
                                    iter1=5
                                    while (devaddingnow and iter1>=0):
                                        time.sleep(200)
                                        iter1 -= 1                                                                                                                                                      
                                    callback(output)
                                else:
                                    for i in xrange(2):
                                        iter1=5
                                        while (devaddingnow and iter1>=0):
                                            time.sleep(200)
                                            iter1 -= 1                                                                                                                           
                                        if (i==0):
                                            params = self.getParams(devIP, "LQ")
                                            output['preview']="rtsp://"+devIP+":7070/Preview" # rtsp://192.168.5.108:7070/Preview, HDX preview fixed
                                            output['preview-port']=7070
                                            output['vid-quality'] = "LQ"
                                            output['model'] = modelname + "." + output['vid-quality'] + "." + devIP
                                            # prepare fake LQ cam URL
                                            if 'url' in output:
                                                del output['url']  
                                            if 'port' in output:
                                                del output['port']  
                                            callback(output)
                                        else:
                                            params = self.getParams(devIP, "HQ")
                                            if 'preview' in output:
                                                del output['preview']  
                                            if 'preview-port' in output:
                                                del output['preview-port']  
                                            output['url'] = params['rtsp_url']
                                            output['port'] = params['rtsp_port']
                                            output['devClass'] = encMatrox
                                            output['vid-quality'] = "HQ"
                                            output['model'] = modelname + "." + output['vid-quality'] + "." + devIP
                                            callback(output)
                                        #end if i
                                    #end for xrange(2)
                    except Exception as e: #may fail if the device is invalid or doesn't have required attributes
                        dbg.prn(dbg.MTX|dbg.ERR, "[---]encMatrox.discover",e, sys.exc_info()[-1].tb_lineno)
                #end for devLoc in monarchs
            #end if monarchs>0
            else:
                dbg.prn(dbg.MTX,"not found any monarchs")
                pass
        except Exception as e:
            dbg.prn(dbg.MTX|dbg.ERR,"[---]encMatrox.discover",e, sys.exc_info()[-1].tb_lineno)
    def restart_HDX(self, encIP, encoder=1):
        """ start HDX device
            Args:
                encIP(striing): device ip
                encoder(int): must be 1 or 2
            Returns:
                boolean: show if it is successfully sent.
        """
        try:
            #pu.io.url('http://'+self.ip+'/Monarch/syncconnect/sdk.aspx?command=StopEncoder1',timeout=10, username="admin", password="admin")
            result = 'FAILED'
            if (encIP):
                result = pu.io.url('http://'+encIP+'/Monarch/syncconnect/sdk.aspx?command=StartEncoder'+str(encoder), timeout=10, username="admin", password="admin")
                dbg.prn(dbg.MTX,"StartEncoder{}-result:{}".format(encoder, result))
            return result == 'SUCCESS'
        except:
            pass
        return False
    def getSpanValue(self, src_page=False, span_id=False):
        """
        parse the html page to extract the useful information - usually for Monarch HDX...
        """
        valueFound = False
        try:
            resPos = src_page.find(span_id) # <span id="ctl00_MainContent_E1RTSPStreamLabelC2">rtsp://192.168.5.108:8554/Stream1</span>
            if (resPos>0):
                posStart = src_page.find('>',resPos)+1
                if (posStart>0):
                    posStop = src_page.find('<',resPos)
                    if (posStop>0):
                        if((posStart>0) and (posStop>0) and (posStop>posStart)):
                            valueFound = src_page[posStart:posStop].strip()
        except Exception as e:
            dbg.prn(dbg.MTX|dbg.ERR,"[---]matrox.getSpanValue:",e,sys.exc_info()[-1].tb_lineno)
        return valueFound
    def getKeyValueDict(self, kv_list=False, status=False): # status: {ENC1:RTSP,READY,ENC2:NONE,DISABLED,NAME:Monarch HDX}
        """
        Convert status result to dictionary
        """
        kv_dict = {}
        kv_ans = {}
        for i in xrange(len(kv_list)):
            kv_dict[kv_list[i]] = -1
            kv_ans[kv_list[i]] = ''
        #kv_list = ['ENC1:', 'ENC2:', 'NAME:']
        #kv_dict = {'ENC1:':-1, 'ENC2:':-1, 'NAME:':-1}
        #kv_ans = {'ENC1:':'', 'ENC2:':'', 'NAME:':''}
        try:
            for k in kv_list:
                found = status.find(k)
                if (found>0):
                    kv_dict[k]=found
                elif (found==0):
                    kv_dict[k]=found
                else:            
                    kv_dict[k]=-1
            for i in xrange(len(kv_list)):
                if (i == (len(kv_list)-1)): # last one
                    start_pos = kv_dict[kv_list[i]]
                    stop_pos = len(status)
                else:
                    start_pos = kv_dict[kv_list[i]]
                    stop_pos = kv_dict[kv_list[i+1]]-1 # remove comma
                if (start_pos<stop_pos):
                    kv_ans[kv_list[i]] = status[start_pos+len(kv_list[i]):stop_pos]
        except Exception as e:
            dbg.prn(dbg.MTX|dbg.ERR,"[---]matrox.getKeyValueDict:",e,sys.exc_info()[-1].tb_lineno)
        return kv_ans
    def getParams(self,ip=False, vq='HQ'):
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
            if (self.isHDX):
                status = pu.io.url('http://'+ip+'/Monarch/syncconnect/sdk.aspx?command=GetStatus',timeout=10, username="admin", password="admin")
            else:
                status = pu.io.url('http://'+ip+'/Monarch/syncconnect/sdk.aspx?command=GetStatus',timeout=10)
            dbg.prn(dbg.MTX,"GetStatus-{}:{}".format(self.model, status))
            if(status):
                if (status=="FAILED"):
                    return params
                if (status.find('name:monarch hdx')>=0):
                    self.isHDX = True
                if (status=="SUCCESS"):
                    pass
                elif (self.isHDX):
                    hdx_stat = self.getKeyValueDict(['ENC1:', 'ENC2:', 'NAME:'], status)
                    if ('ENC1:' in hdx_stat and 'ENC2:' in hdx_stat):
                            self.ENC1 = (hdx_stat['ENC1:'].find('RTSP')>=0)
                            enc1_stat = hdx_stat['ENC1:'].split(',')
                            if (len(enc1_stat)>1):
                                self.RTSPStarted = enc1_stat[1]=='ON'
                            self.ENC2 = (hdx_stat['ENC2:'].find("RECORD")>=0)
                            if (len(enc1_stat)>1 and enc1_stat[1]=='READY'): # HDX is not streaming in first boot
                                self.restart_HDX(ip)
                    else:
                        self.ENC1 = False
                        self.ENC2 = False
                    dbg.prn(dbg.MTX,"HDX:{} ENC1:{} ENC2:{} hdx_stat:{}".format(self.isHDX, self.ENC1, self.ENC2, hdx_stat))
                else:
                    hd_stat = self.getKeyValueDict(['RECORD:', 'STREAM:', 'NAME:'], status) #RECORD:READY,STREAM:RTSP,ON,NAME:MHD-00
                    streamParams = status.split(',') 
                    status = status.lower()
                    # extract RECORD status
                    statRec = status[status.find('record')+7:status.find('stream')-1]
                    # extract STREAM status
                    statStr = status[status.find('stream')+7:status.find('name')-1]
                    # get stream parameters
                    # 1st is streaming mode (RTMP or RTSP or DISABLED), 
                    # 2nd is streaming status (ON, READY or DISABLED)
                    streamParams = statStr.split(',') 
#                    isRTSP = streamParams[0]=='rtsp'
#                     if(not isRTSP): #if it's not rtsp mode, stop any streaming and/or recording that's going on and set device to RTSP mode
#                         pu.io.url('http://'+ip+'/Monarch/syncconnect/sdk.aspx?command=StopStreamingAndRecording',timeout=10) #if in streaming & recording mode
#                         time.sleep(1)
#                         pu.io.url('http://'+ip+'/Monarch/syncconnect/sdk.aspx?command=StopStreaming',timeout=10) #if in streaming mode only (RTMP)
#                         time.sleep(1)
#                         pu.io.url('http://'+ip+'/Monarch/syncconnect/sdk.aspx?command=StopRecording',timeout=10) #if in recording mode only
#                         time.sleep(1)
#                         pu.io.url('http://'+ip+'/Monarch/syncconnect/sdk.aspx?command=SetRTSP,Stream1,8554',timeout=10) 
#                         time.sleep(1)
                    # get RTSP parameters
                if (not self.isHDX):
                    status = pu.io.url('http://'+ip+'/Monarch/syncconnect/sdk.aspx?command=GetRTSP',timeout=10)
                    dbg.prn(dbg.MTX,"GetRTSP:",status)
                    if(status and status !='FAILED'):
                        rtspParams = status.split(',')
                        if(len(rtspParams)>2):
                            params['rtsp_url']=rtspParams[0]
                            params['rtsp_port']=rtspParams[2]
                    #-------------------------------------------------
                    # get bitrate - disabled due to recording mode
                    #-------------------------------------------------
#                     status = pu.io.url('http://'+ip+'/Monarch/syncconnect/sdk.aspx?command=GetStreamingVideoDataRate',timeout=10)
#                     dbg.prn(dbg.MTX,"GetStreamingVideoDataRate:",status)
#                     if(status):
#                         rtspParams = status.split(':')
#                         if(len(rtspParams)>1):
#                             params['streamBitrate']=rtspParams[1]
                    params['streamBitrate']=''
                    
            #####################
            #  old code is here #
            #####################
            # # for now the only way to extract this information is using the monarch home page (no login required for this one)
            # # when they provide API, then we can use that
            if (self.isHDX):
                mtPage = pu.io.url("http://"+ip+"/Monarch", timeout=10, username="admin", password="admin")
            else:
                mtPage = pu.io.url("http://"+ip+"/Monarch", timeout=10)
            if(not mtPage):
                return False #could not connect to the monarch page
            
            # check if it is HDX or HD
            if (self.isHDX):
                device_name =  self.getSpanValue(mtPage, "ctl00_MainContent_DeviceNameLabel")
                video_input =  self.getSpanValue(mtPage, "ctl00_MainContent_VideoInputLabel")         # <span id="ctl00_MainContent_VideoInputLabel">1920x1080i, 29.97 fps (HDMI)</span>
                rtsp_setting = self.getSpanValue(mtPage, "ctl00_MainContent_E1RTSPStreamLabelC2")     # <span id="ctl00_MainContent_E1RTSPStreamLabelC2">rtsp://192.168.5.108:8554/Stream1</span>
                enc1_setting = self.getSpanValue(mtPage, "ctl00_MainContent_Encoder1SettingsLabel")   # <span id="ctl00_MainContent_Encoder1SettingsLabel">1280x720p, 30/25 fps, 10000 kb/s; </span>
                rec_media = self.getSpanValue(mtPage, "ctl00_MainContent_E1RecordMediaLabel")         # <span id="ctl00_MainContent_E1RecordMediaLabel">USB1, no drive present</span>
                if (rtsp_setting):
                    params['rtsp_url'] = rtsp_setting
                    from urlparse import urlparse
                    params['rtsp_port'] = urlparse(rtsp_setting).port
                    if (vq=="LQ"):
                        params['rtsp_url'] = "rtsp://"+ip+":7070/Preview"
                        params['rtsp_port'] = 7070
                else:
                    dbg.prn(dbg.MTX,"monarch rtsp_setting is not avaialble-{}".format(mtPage))
                if (vq=="LQ"):
                    params['streamResolution'] = "320x180i"
                    params['streamBitrate'] = "0.5"
                    params['streamFramerate'] = "30"
                    params['inputResolution'] = "180i30" # 320x180
                    params["connection"] = True
                    return params 
                if (video_input):
                    if((video_input.find(",")>0) and (video_input.find("fps")>0)): # video source present
                        # get resolution
                        resParts = video_input.lower().strip().split(',')
                        # now first part contains the resolution (e.g. 1280x720p)
                        params['streamResolution'] = resParts[0]
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
                        if (framerate=='29.97'):
                            framerate = '30'
                        params['streamFramerate'] = framerate
                        if(resolution and framerate):
                            params['inputResolution'] = resolution+framerate # e.g. 1080i60
                else:
                    dbg.prn(dbg.MTX,"monarch video_input is not avaialble-{}".format(mtPage))
                if (enc1_setting):
                    bitrate = enc1_setting.split(',')[2].strip()
                    if (bitrate):
                        params['streamBitrate'] = bitrate.split(' ')[0]
                else:
                    dbg.prn(dbg.MTX,"monarch enc1_setting is not avaialble-{}".format(mtPage))
                if (rec_media and (self.ENC2)):
                    self.dev_mp4path = rec_media # something like "//192.168.5.115:/Users/dev/recordings/av1"
                    dbg.prn(dbg.MTX, "record_path:{}".format(self.dev_mp4path))
                params["connection"] = True
                return params 
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
            resPos = mtPage.find("ctl00_MainContent_RecordMediaLabel") #this is the id of the label containing record path
            if(resPos>0):#found the record path, find where the actual text is
                posStart = mtPage.find(',',resPos)+1
            else:
                posStart = -1
            # find end position
            if(posStart>0):        
                posStop = mtPage.find('<',posStart)
            else:
                posStop = -1
            if((posStart>0) and (posStop>0) and (posStop>posStart)):
                self.dev_mp4path = mtPage[posStart:posStop].strip() #either contains "//192.168.5.115:/Users/dev/recordings/av1"
            dbg.prn(dbg.MTX, "record_path:{}".format(self.dev_mp4path))
            
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
                    params['streamResolution'] = resParts[0]
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
                    params['streamFramerate'] = framerate
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
            dbg.prn(dbg.MTX|dbg.ERR,"[---]matrox.getParams",e,sys.exc_info()[-1].tb_lineno)
        dbg.prn(dbg.MTX,"mtx:{} params-->{}".format(params['rtsp_url'], params))
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
        params = self.getParams(ip=self.ip, vq=self.vidquality)
        dbg.prn(dbg.MTX, "mt.{}.update:{}".format(self.vidquality, params))
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
    def startRec(self):
        """
        Monarch doesn't automatically start the stream until it is configured from the XML (which needs XML loading from the web-server)
        For this, it needs to start manually every time it needs to.
        """
        try:
            if (self.ip):
                if (self.isHDX):
                    if (not self.RTSPStarted):
                        self.restart_HDX(self.ip)
                    #pu.io.url('http://'+self.ip+'/Monarch/syncconnect/sdk.aspx?command=StartBothEncoders',timeout=10, username="admin", password="admin")
                else:
                    pu.io.url('http://'+self.ip+'/Monarch/syncconnect/sdk.aspx?command=StartRecording',timeout=10)
                dbg.prn(dbg.MTX, "=============> Matrox.START:{} recpath:{}".format(self.model,self.dev_mp4path))
        except:
            pass        
    def stopRec(self):
        try:
            if (self.ip):
                if (self.isHDX):
                    # ENC1 is not stoppped on purpose!
                    if (self.ENC2):
                        pu.io.url('http://'+self.ip+'/Monarch/syncconnect/sdk.aspx?command=StopEncoder2',timeout=10, username="admin", password="admin")
                    #pu.io.url('http://'+self.ip+'/Monarch/syncconnect/sdk.aspx?command=StopBothEncoders',timeout=10, username="admin", password="admin")
                else:
                    pu.io.url('http://'+self.ip+'/Monarch/syncconnect/sdk.aspx?command=StopRecording',timeout=10)
                dbg.prn(dbg.MTX, "=============> Matrox.STOP:{} recpath:{}".format(self.model,self.dev_mp4path))
        except:
            pass        
    def setRecordPath(self, mp4path=""):
        # //192.168.5.115:/Users/dev/recordings/av1
        try:
            self.dev_mp4path = mp4path
            status = pu.io.url('http://'+self.ip+'/Monarch/syncconnect/sdk.aspx?command=SetRecordFileName',timeout=10, username="admin", password="admin")
            dbg.prn(dbg.MTX, "encMatrox.setRecordPath:{}".format(status))
        except:
            pass
    def collect_mp4(self, vid_path):
        # RECORD FILENAME://192.168.5.115:/Users/dev/recordings/av1
#         for i in xrange(3):
#             self.dev_mp4path = pu.io.url('http://'+self.ip+'/Monarch/syncconnect/sdk.aspx?command=GetRecordFileName',timeout=10)
#             if (self.dev_mp4path=="SUCCESS"):
#                 dbg.prn(dbg.MTX, "************************************************************")
#                 dbg.prn(dbg.MTX, "*** encMatrox.collect_mp4: MATROX ERROR --- retrying...{}".format(i))
#                 dbg.prn(dbg.MTX, "************************************************************")
#                 time.sleep(1)
#             else:
#                 pass
#         dbg.prn(dbg.MTX, "encMatrox.collect_mp4:{}".format(self.dev_mp4path))
        try:
            if (self.dev_mp4path and (self.dev_mp4path!="")):
                w = self.dev_mp4path.split("/")
                if (len(w)>0):
                    s = w[len(w)-1]
                    if (not os.path.exists(vid_path + s)):
                        os.system("mkdir " + vid_path + "/" + s)
                    cmd = "mv /Users/dev/recordings/" + s + "*.mp4 " + vid_path + "/" + s
                    os.system(cmd)
                    dbg.prn(dbg.MTX, "encMatrox.collect_mp4::move all of files->{}".format(cmd))
        except:
            pass
        return True
    def postproc(self, srcidx, vq, vid_path):
        """
        Caoncat the all of mp4 files created from the Monarch devices:
        """
#         self.dev_mp4path = pu.io.url('http://'+self.ip+'/Monarch/syncconnect/sdk.aspx?command=GetRecordFileName',timeout=10, username="admin", password="admin")
#         dbg.prn(dbg.MTX, "encMatrox.postproc:{}".format(self.dev_mp4path))
        try:
            if (self.dev_mp4path and (self.dev_mp4path!="")):
                w = self.dev_mp4path.split("/")
                if (len(w)>0):
                    s = w[len(w)-1]
                    mp4files = glob.glob(vid_path + "/" + s + "/" + s + "*.mp4")
                    mp4files.sort(key=os.path.getmtime)
                    arg = '# concat mp4\n'
                    for f in mp4files:
                        arg += "file " + "'" + f + "'" + "\n"
                    if (len(mp4files)>0):
                        pu.disk.file_set_contents(vid_path + "/" + s + "/mp4_" + s + ".txt", arg)
                        #ffmpeg -f concat -i mp4.txt -c copy -y all.mp4
                        cmd = c.ffbin + " -f concat -i " + vid_path + "/" + s + "/mp4_" + s + ".txt -c copy -y " + vid_path + "/" + s + "/all_" + s + ".mp4"
                        os.system(cmd)  
                        dbg.prn(dbg.MTX, "encMatrox.postproc::concat->{}".format(cmd))
                    cmd = "mv " + vid_path + "/" + s + "/all_" + s + ".mp4 " + vid_path + "/" + vq + "_" + str(srcidx).zfill(2)
                    os.system(cmd)
        except:
            pass
        return cmd
    def hdx_stat(self, ip=False, encoder=1, status='READY'):
        """ check if rtsp streaming is on progress by using GetStatus API
            Args:
                ip(striing): device ip
                encoder(int): must be 1 or 2
                status(string): 'READY' or 'ON' or 'DISABLED'
            Returns:
                boolean: to show if the streaming is on progress
        """
        try:
            if (self.isHDX and ip):
                stat = False
                status = pu.io.url('http://'+ip+'/Monarch/syncconnect/sdk.aspx?command=GetStatus',timeout=10, username="admin", password="admin")
                dbg.prn(dbg.MTX,"GetStatus2-{}:{}".format(self.model, status))
                if(status):
                    hdx_stat = self.getKeyValueDict(status)
                    if ('ENC1:' in hdx_stat and 'ENC2:' in hdx_stat):
                            self.ENC1 = hdx_stat['ENC1:'].find('RTSP')>=0
                            enc1_stat = hdx_stat['ENC1:'].split(',')
                            if (len(enc1_stat)>1):
                                stat = enc1_stat[1]==status
                            self.ENC2 = hdx_stat['ENC2:']!='NONE,DISABLED'
                    else:
                        self.ENC1 = False
                        self.ENC2 = False
                self.RTSPStarted = stat                 
                return stat
        except:
            pass
        return False  
    
class encPivothead(encDevice):
    """ Pivothead glasses encoder management class """
    def __init__(self, ip=False, vq="HQ", uid=False, pwd=False, realm=False, mac=False):
        if(ip):
            super(encPivothead,self).__init__(ip, vq, uid=uid, pwd=pwd, realm=realm, mac=mac)
            self.model = "Pivothead"

    def discover(self, callback):
        """ Find any new devices using bonjour protocol. 
            Args:
                callback(function): called when a device is found 
            Returns:
                none
        """
        def discovered(results):
            global devaddingnow            
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
            output['vid-quality'] = 'HQ'
            output['username'] = False
            output['password'] = False
            output['realm'] = False
            output['mac'] = False      
            output['model'] = 'PIVOTHAED'   
            iter1=5
            while (devaddingnow and iter1>=0):
                time.sleep(200)
                iter1 -= 1                                                                                                                                                 
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
    def startRec(self):
        pass        
    def stopRec(self):
        pass        

class encSonySNC(encDevice):
    """ Sony SNC device management class """
    def __init__(self, ip=False, vq="HQ", uid=False, pwd=False, realm=False, mac=False):
        if(ip):
            super(encSonySNC,self).__init__(ip, vq, uid=uid, pwd=pwd, realm=realm, mac=mac)
            self.ccBitrate      = True # can change bitrate
            self.model = "SONY"
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
            dbg.prn(dbg.ERR|dbg.SNC,"[---]snc.alarmChk:", e, sys.exc_info()[-1].tb_lineno, "( resp : ",response,')')
    def discover(self, callback): # 'self' is not defined until it hits __init__, do not use self.XXX class attributes
        """ Find any new devices using bonjour protocol. 
            Args:
                callback(function): called when a device is found 
            Returns:
                none
        """
        try:
            global sockCmd
            global devaddingnow            
            if(enc.code & enc.STAT_SHUTDOWN):
                return
            if (pu.mdbg.checkscf(sockCmd, pu.SCF_SHOWBONJ)):
                dbg.prn(dbg.MN, "-->Start looking for SONY camera.....")
            #to find ALL ssdp devices simply enter ssdp:all as the target
            devs  = pu.ssdp.discover(text="SNC",field='server',case=True)
            if(len(devs)>0):
                # found at least one monarch 
                for devLoc in devs:
                    try:
                        dev = devs[devLoc]
                        if (pu.mdbg.checkscf(sockCmd, pu.SCF_SHOWBONJ)):
                            dbg.prn(dbg.MN, "-->SONY:recs-->", dev)
                            
                        dev = devs[devLoc]
                        serial, modelname = self.setModel(dev.location, 'SONY', 'modelName')                      
                            
                        devIP, devPT = self.parseURI(dev.location)
                        if(not devIP): #did not get ip address of the device
                            continue
                        params = self.getParams(devIP) #get all the parameters from the SONY's page
                        if(params and params['rtsp_url'] and params['rtsp_port']):
                            output = {}
                            output['ip'] = devIP
                            output['type'] = 'sn_snc'
                            output['url'] = params['rtsp_url']
                            output['port'] = params['rtsp_port']
                            output['devClass'] = encSonySNC
                            output['vid-quality'] = 'HQ'
                            output['username'] = params['username'] 
                            output['password'] = params['password'] 
                            output['realm'] = False
                            output['mac'] = params['mac']
                            if (not pu.pxpconfig.virtual_lq_enabled()):
                                output['model'] = modelname + "." + output['vid-quality'] + "." + devIP
                                callback(output)
                            else:
                                for i in xrange(2):
                                    iter1=5
                                    while (devaddingnow and iter1>=0):
                                        time.sleep(200)
                                        iter1 -= 1                                                                                                                           
                                    if (i==0):
                                        output['model'] = modelname + "." + output['vid-quality'] + "." + devIP
                                        callback(output)
                                        # prepare fake LQ cam URL
                                        params = self.getParams(devIP, vq='LQ') #get all the parameters from the SONY's page
                                        lowq_port = output['port']
                                        lowq_url = params['rtsp_url'] #.replace('video1', 'video2')
                                        if 'url' in output:
                                            del output['url']  
                                        if 'port' in output:
                                            del output['port']  
                                        output['preview']=lowq_url
                                        output['preview-port']=lowq_port
                                        output['vid-quality'] = 'LQ'
                                    else:
                                        output['model'] = modelname + "." + output['vid-quality'] + "." + devIP
                                        callback(output)
                                    #end if i
                                #end for xrange(2)
                        #end if param                                    
                    except Exception as e: #may fail if the device is invalid or doesn't have required attributes
                        dbg.prn(dbg.SNC|dbg.ERR, "[---]encSonySNC.discover",e, sys.exc_info()[-1].tb_lineno)
                #end for devLoc in devs
            #end if devs>0
            else:
                # dbg.prn(dbg.SNC,"not found any SNCs")
                pass
        except Exception as e:
            dbg.prn(dbg.SNC|dbg.ERR,"[---]encSonySNC.discover",e, sys.exc_info()[-1].tb_lineno)
    def getParams(self,ip=False, vq='HQ'):
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
            sn_key = {}
            if (vq=='HQ'):
                sn_key['video_path']='/media/video1'
                sn_key['VBRBitrateMax']='VBRBitrateMax1'
                sn_key['VBRMode']='VBRMode1'
                sn_key['CBR']='CBR1'
                sn_key['BitRate']='BitRate1'
                sn_key['AutoRateCtrlBitrateMax']='AutoRateCtrlBitrateMax1'
                sn_key['AutoRateCtrl']='AutoRateCtrl1'
                sn_key['ImageSize']='ImageSize1'
                sn_key['FrameRate']='FrameRate1'
            else:
                sn_key['video_path']='/media/video2'
                sn_key['VBRBitrateMax']='VBRBitrateMax2'
                sn_key['VBRMode']='VBRMode2'
                sn_key['CBR']='CBR2'
                sn_key['BitRate']='BitRate2'
                sn_key['AutoRateCtrlBitrateMax']='AutoRateCtrlBitrateMax2'
                sn_key['AutoRateCtrl']='AutoRateCtrl2'
                sn_key['ImageSize']='ImageSize2'
                sn_key['FrameRate']='FrameRate2'
            
            params['rtsp_url']='rtsp://'+ip+sn_key['video_path'] #'/media/video1'
            status = pu.io.url('http://'+ip+'/command/inquiry.cgi?inq=camera',timeout=10)
            network = pu.io.url('http://'+ip+'/command/inquiry.cgi?inq=network',timeout=10, username="admin", password="admin")
            if (network):
                netParams = dict(parse_qsl(network))
                params['mac'] = netParams['MacAddress']
                params['username'] = False # "admin"
                params['password'] = False # "admin"                
            else:
                params['username'] = False
                params['password'] = False
                params['mac'] = False
            # cbr    : VBRMode1: 'standard', 'CBR1': 'on', 'AutoRateCtrl1': 'off', bitrate is in 'BitRate1'
            # vbr nomax: VBRMode1: 'standard', 'CBR1': 'off', 'AutoRateCtrl1': 'off', bitrate is in 'VBRBitrateMax1'
            # vbr max: VBRMode1: 'bitratelimit', 'CBR1': 'off', 'AutoRateCtrl1': 'off', bitrate is in 'VBRBitrateMax1'
            # adaptive: VBRMode1: 'bitratelimit', 'CBR1': 'off', 'AutoRateCtrl1': 'on', bitrate is in 'AutoRateCtrlBitrateMax1'
            if(status):
                rtspParams = dict(parse_qsl(status))
                if(len(rtspParams)>1):
                    params['streamBitrate']=rtspParams[sn_key['VBRBitrateMax']] #for VBR mode, the max allowed bitrate, use max allowed bitrate
                    if(rtspParams[sn_key['VBRMode']]=='standard' and rtspParams[sn_key['CBR']]=='on'): #this is CBR mode - bitrate is fixed
                        params['streamBitrate']=rtspParams[sn_key['BitRate']]
                    if(rtspParams[sn_key['VBRMode']]=='bitratelimit' and rtspParams['AutoRateCtrl1']=='on'): #this is adaptive mode, the max bitrate is defined in another variable
                        params['streamBitrate']=rtspParams[sn_key['AutoRateCtrlBitrateMax']]
                    res = rtspParams[sn_key['ImageSize']].split(',')
                    params['inputResolution']=res[1]+'p'+rtspParams[sn_key['FrameRate']]
                    params['streamResolution']=res[1]+'p'
                    params['streamFramerate']=rtspParams[sn_key['FrameRate']]
                    params['rtsp_port']=int(rtspParams['RTSPPort'])
                    params['connection']=True
                    if (pu.mdbg.checkscf(sockCmd, pu.SCF_SHOWBONJ)):
                        dbg.prn(dbg.MN, "-->SONY:recs_parsed-->ip:{} vq:{} param:{}".format(ip, vq, params))
        except Exception as e:
            dbg.prn(dbg.SNC|dbg.ERR,"[---]encSonySNC.getParams",e,sys.exc_info()[-1].tb_lineno)
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
    def setVideoInputType(self, vit):
        self.vit = vit
    def setBitrate(self,bitrate):
        """ Set device bitrate is in kbps 
            Args:
                bitrate(int): new bitrate in kbps
            Returns:
                (str): response from the url request
        """
        try:
            # bypassed by request from Ivan
            if (pu.pxpconfig.IgnoreVideoSettings()):
                dbg.prn(dbg.TDK,"snc -- setBitrate BYBASSED")
                return True
            result = False
            dbg.prn(dbg.SNC,"snc.setbitrate:",bitrate, self.ip)
            # ensure it's in CBR mode and set the bitrate
            if (self.vidquality=='HQ'):
                result = pu.io.url("http://"+self.ip+"/command/camera.cgi?CBR1=on&BitRate1="+str(bitrate),username='admin',password='admin')
            else:
                result = pu.io.url("http://"+self.ip+"/command/camera.cgi?CBR1=on&BitRate2="+str(bitrate),username='admin',password='admin')
            self.updatedb()  
            dbg.prn(dbg.SNC,"SNC.setbitrate:", bitrate, self.ip, self.vidquality)                        
            return result
        except Exception as e:
            dbg.prn(dbg.ERR|dbg.SNC,"[---]snc.setBitrate:", e, sys.exc_info()[-1].tb_lineno)
        return result
    def setFramerate(self,framerate):
        """ Set device frame rate is in fps 
            Args:
                framerate(int): new frame rate in fps
            Returns:
                (str): response from the url request
        """
        try:
            # bypassed by request from Ivan
            if (pu.pxpconfig.IgnoreVideoSettings()):
                dbg.prn(dbg.SNC,"snc -- setFramerate BYBASSED")
                return True
            result = False
            dbg.prn(dbg.SNC,"snc.setframerate:",framerate, self.ip, self.vidquality)
            # set the framerate (page uses basic authentication)
            if (self.vidquality=='HQ'):
                result = pu.io.url("http://"+self.ip+"/command/camera.cgi?FrameRate1="+str(framerate),username='admin',password='admin')
            else:
                result = pu.io.url("http://"+self.ip+"/command/camera.cgi?FrameRate2="+str(framerate),username='admin',password='admin')
            return result
        except Exception as e:
            dbg.prn(dbg.ERR|dbg.SNC,"[---]snc.setFramerate:", e, sys.exc_info()[-1].tb_lineno)
        return result
    def update(self):
        """ Requests encoding parameters of the device and updates local class properties"""
        # get the device parameters
        if(enc.code & enc.STAT_SHUTDOWN): #exit immediately if there's a shutdown going on
            return
        params = self.getParams(vq=self.vidquality)
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
    def startRec(self):
        pass        
    def stopRec(self):
        pass        

class encDebug(encDevice):
    """ A test device class: at the moment used for Liquid Image EGO"""
    def __init__(self, ip=False, vq="HQ", uid=False, pwd=False, realm=False, mac=False):
        if(ip):
            super(encDebug,self).__init__(ip, vq, uid=uid, pwd=pwd, realm=realm, mac=mac)
            self.model = "FAKECAM"
    def buildCapCmd(self, camURL, chkPRT, camMP4, camHLS): 
        """ Overrides encDevice's method: EGO produces inconsistent PTS, so it requires ffmpeg to generate its own PTS """
        # if ther's a problem, try adding -rtsp_transport udp before -i
        # liquid image EGO camerea requires -fflags +genpts otherwise you get "first pts value must be set" error and won't start ffmpeg
        return c.ffbin+" -fflags +genpts+igndts -rtsp_transport udp -i "+camURL+" -codec copy -f h264 udp://127.0.0.1:"+chkPRT+" -codec copy -f mpegts udp://127.0.0.1:"+camMP4+" -codec copy -f mpegts udp://127.0.0.1:"+camHLS
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
                output['vid-quality'] = 'HQ'
                output['username'] = False
                output['password'] = False
                output['realm'] = False
                output['mac'] = False       
                output['model'] = self.model                                                                                                   
                callback(output)
            else:
                # dbg.prn(dbg.TST,"not found any debug devices")
                pass
        except Exception as e:
            dbg.prn(dbg.TST|dbg.ERR,"[---]encDebug.discover",e, sys.exc_info()[-1].tb_lineno)
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
    def startRec(self):
        pass        
    def stopRec(self):
        pass        

##############################
### source classes ###
##############################

class source:
    """ A wrapper for a video source (this contains the reference to the video device instance) """
    def __init__(self, vq, ip, encType, ports={}, url=False, preview=False, devClass=False, uid=False, pwd=False, realm=False, mac=False, modelname=False, idx=-1):
        """ create a new video source
            Args:
                ip(str)       : ip address of the source (used for checking if the device is alive)
                ports(dict)   : dictionary of ports used for this source: 
                          mp4 : udp port where ffmpeg that records mp4 file receives data, 
                          hls : udp port where m3u8 segmenter receives MPEG-TS data, 
                          chk : udp port that is used to check whether packets are coming in, 
                          rtp : port used to connect to the rtsp server (for source validation)
                          xfb : X-Failover Backup port - used to ensure stream continuity (this is where data will be received from)
                encType(str)  : type of source/encoder (e.g. td_cube, ph_glass, mt_monarch)
                url(str)      : rtsp source url (must specify url or preview)
                preview(str)  : url of the preview rtp stream (must specify url or preview)
        """
        try:
            self.isEncoding     = False # set to true when it's being used in a live event
            self.ports          = ports
            self.type           = encType
            self.rtspURL        = False # this is the public (proxied) rtsp URL - a stream that anyone on the network can view
            self.xfbURL         = False # udp://... url after passing through the XFB
            self.previewURL     = False
            self.id             = int(time.time()*1000000) #id of each device is gonna be a time stamp in microseconds (only used for creating threads)
            self.ipcheck        = '127.0.0.1' #connect to this ip address to check rtsp - for now this will be simply connecting to the rtsp proxy, constant pinging of the RTSP on the device directly can cause problems
            self.urlFilePath    = False
            self.idx            = False
            # add a new device, based on its type
            if(not devClass):
                return False
            self.device = devClass(ip, vq, uid, pwd, realm, mac)
            self.device.model = modelname
            # see if Monarch HDX or Monarch DX...very nasty
            if (modelname.find('Monarch HDX')>=0):
                self.device.isHDX = True
            self.ffcap_cmd = False
            self.ffseg_cmd = False
            self.ffrec_cmd = False
            self.urlFilePath = "/tmp/pxp-url-"+self.device.vidquality+"-"+str(self.device.ip) #this file will contain the url to the proxied RTSP (after running live555proxy)
            self.disconn = []
            if (idx>=0):
                self.idx = idx
            self.sIN = False

            #if (pu.mdbg.checkscf(sockCmd, pu.SCF_SHOWBONJ)):
            dbg.prn(dbg.SRC, "[###]{0}[{1}] IP:{2}.{3} FILE:[{4}] SOURCE_PORTS-->{5}".format(modelname, idx, ip, vq, self.urlFilePath, ports))

            self.listFile = False #this will contain the name of the .m3u8 file (not full path)
            if(url):
                self.device.rtspURL = url #this is a private url used for getting the video directly form the device
                self.device.baseRTSPURL = url
            if(preview):
                self.previewURL = preview
                self.device.rtspURL = preview
                self.device.baseRTSPURL = preview
            self.device.updatedb()
            if('xfo' in ports):
                self.xfbURL = "udp://127.0.0.1:"+str(ports['xfo'])
            if(not 'src' in tmr):
                tmr['src']={}
            # monitor the stream
            tmr['src'][self.id] = TimedThread(self.monitor,period=3)
            # monitor alarms 
            tmr['src'][str(self.id)+'alarm'] = TimedThread(self.device.alarmChk,period=2)
            # monitor device parameters
            tmr['src'][str(self.id)+'param'] = TimedThread(self.device.update,period=5)
            
            dbg.prn(dbg.SRC, "[###] ip:{}  model:{}  idx:{}  id:{} made -------------".format(ip, modelname, idx, self.id))
        except Exception as e:
            dbg.prn(dbg.ERR|dbg.SRC, "[---]source.init", e, sys.exc_info()[-1].tb_lineno)
    #end init
    def __repr__(self):
        # prints a string representation of the class object)
        return "<source> idx:{idx}  url:{rtspURL}  preview:{previewURL}  urlfile:{urlFilePath}  type:{type}  dev:{device}".format(**self.__dict__)
    def buildCapCmd(self):
        """ creates an ffmpeg capture command for this source using device's buildCapCmd method """
        try:
            if (pu.pxpconfig.use_proxy() or not self.device.baseRTSPURL):
                cmd = self.device.buildCapCmd(self.xfbURL,self.ports['chk'],self.ports['mp4'],self.ports['hls'])
            else:
                cmd = self.device.buildCapCmd(self.device.baseRTSPURL, self.ports['chk'],self.ports['mp4'],self.ports['hls'])
                dbg.prn(dbg.SRC, "capture uses no proxy - model:{} url:{}".format(self.device.model, self.device.baseRTSPURL))
            dbg.prn(dbg.SRC, "capture device:{} baseRTSPURL:{} xfbURL:{}".format(self.device.model, self.device.baseRTSPURL, self.xfbURL))
        except Exception as e:
            dbg.prn(dbg.ERR|dbg.SRC,"[---]src.buildcapcmd err:".format(e))
            cmd = self.device.buildCapCmd(self.rtspURL,self.ports['chk'],self.ports['mp4'],self.ports['hls'])
        return cmd
    def clearport(self):
        self.sIN.close()
        self.sIN = False
    def camPortMon_resusable(self):
        """ monitor data coming in from the camera (during live) - to make sure it's continuously receiving """
        try:
            dbg.prn(dbg.SRC,"starting camportmon_reusable for {} {}".format(self.idx, self.ports['chk']))
            host = '127.0.0.1'          #local ip address
            self.sIN = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP) #Create a socket object
            self.sIN.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            portIn = self.ports['chk']
            err = True
            while (err and not (enc.code & enc.STAT_SHUTDOWN)):
                try:
                    self.sIN.bind((host, portIn)) #Bind to the port
                    err = False
                except (socket.error, KeyboardInterrupt), msg:
                    self.sIN.close()
                    self.sIN = False
                    time.sleep(1)
                    err = True
                    dbg.prn(dbg.ERR|dbg.SRC,"portmon cannot start {} {} {}".format(portIn, socket.error, msg))
                    pass
            #end while err
            dbg.prn(dbg.SRC,".............bound.................{} {} {}".format(self.idx, self.ports['chk'], self.isEncoding), )
            self.sIN.setblocking(0)
            self.sIN.settimeout(0.5)
            timeStart = time.time()
            while ((enc.code & (enc.STAT_LIVE | enc.STAT_START | enc.STAT_PAUSED)) and self.isEncoding):
                try:
                    if((enc.code & enc.STAT_PAUSED)): #the encoder is paused - do not check anything
                        time.sleep(0.2) #reduce the cpu load
                        continue
                    data, addr = self.sIN.recvfrom(65535)
                    if(len(data)<=0):
                        continue
                    #pxp status should be 'live' at this point
                    if((enc.code & enc.STAT_START) and (time.time()-timeStart)>2):
                        enc.statusSet(enc.STAT_LIVE,autoWrite=False)
                except (socket.error, KeyboardInterrupt), msg:
                    # only gets here if the connection is refused or interrupted
                    # sys.stdout.write('.')
                    dbg.prn(dbg.ERR|dbg.SRC,"^.^  port:{}  sock:{}  msg:{}".format(portIn, socket.error, msg))
                    #print '^.^   port:{0}'.format(portIn)
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
                    except (Exception,KeyboardInterrupt) as e:
                        self.sIN.close()
                        self.sIN = False
                        dbg.prn(dbg.ERR|dbg.SRC,"TT.TT  err:{}".format(e))
                        pass
                except (Exception,KeyboardInterrupt) as e:
                    dbg.prn(dbg.ERR|dbg.SRC,"[---]camportmon_reusable err: ",e,sys.exc_info()[-1].tb_lineno)
            #end while
        except (Exception, KeyboardInterrupt) as e:
            self.sIN.close()
            self.sIN = False
            dbg.prn(dbg.ERR|dbg.SRC,"[---]camportmon_reusable err: ", e, sys.exc_info()[-1].tb_lineno)
        self.sIN.close()
        self.sIN = False
        dbg.prn(dbg.SRC,"camportmon_reusable exited normally")
    def camPortMon(self):
        """ monitor data coming in from the camera (during live) - to make sure it's continuously receiving """
        try:
            dbg.prn(dbg.SRC,"starting camportmon for {} {}".format(self.idx, self.ports['chk']))
            host = '127.0.0.1'          #local ip address
            sIN = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP) #Create a socket object
            portIn = self.ports['chk']
            #sIN.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            err = True
            while (err and not (enc.code & enc.STAT_SHUTDOWN)):
                try:
                    sIN.bind((host, portIn)) #Bind to the port
                    err = False
                except socket.error, msg:
                    time.sleep(1)
                    err = True
                    dbg.prn(dbg.ERR|dbg.SRC,"portmon cannot start {} {} {}".format(portIn, socket.error, msg))
            #end while err
            dbg.prn(dbg.SRC,".............bound.................{} {} {}".format(self.idx, self.ports['chk'], self.isEncoding), )
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
                    dbg.prn(dbg.ERR|dbg.SRC,"^.^  port:{}  sock:{}  msg:{}".format(portIn, socket.error, msg))
                    #print '^.^   port:{0}'.format(portIn)
                    try:
                        timeStart = time.time()                            
                        if(enc.code & enc.STAT_LIVE):
                            # only set encoder status if there is a live event 
                            # to make sure the monitor runs an RTSP check on the stream
                            # self.device.isOn=False #don't restart anything - just enable filemon
                            # start file monitor to add EXT-X-DISCONTINUITY
                            if(not(str(self.id)+'_filemon' in tmr['src'])):
                                tmr['src'][str(self.id)+'_filemon'] = TimedThread(self.fileSegMon)
                        time.sleep(1) #wait for a second before trying to receive data again
                    except Exception as e:
                        dbg.prn(dbg.ERR|dbg.SRC,"TT.TT  err:{}".format(e))
                        pass
                except Exception as e:
                    dbg.prn(dbg.ERR|dbg.SRC,"[---]camPortMon err: ",e,sys.exc_info()[-1].tb_lineno)
            #end while
        except Exception as e:
            dbg.prn(dbg.ERR|dbg.SRC,"[---]camportmon err: ", e, sys.exc_info()[-1].tb_lineno)
        sIN.close()
        sIN = False
        dbg.prn(dbg.SRC,"camportmon exited normally")
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
            if (pu.pxpconfig.use_split_event_folder()):
                listPath = c.live_video + self.device.vidquality + "_" + str(self.idx).zfill(2)
                
            dbg.prn(dbg.SRC,"^^^^^^FILE SEG MON^^^^^^ file:",listPath,' exists?',os.path.exists(listPath))
            if(not os.path.exists(listPath)):#the file does not exist - can happen here if the camera got disconnected before any segments came in
                dbg.prn(dbg.SRC,"no listPath????????", listPath)
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
            pu.mdbg.log("------fileSegMon:".format(e,str(sys.exc_info()[-1].tb_lineno)))
    #-----------------------
    def monitor(self):
        """ monitors the (actual) device parameters and sets source (i.e. wrapper) parameters accordingly """
        try:
            if(enc.code & enc.STAT_SHUTDOWN):
                self.stopMonitor()
                return False
            # ensure there's a live555 proxy running for this device - this statement is executed once, when the device is just added
            if(self.device.rtspURL and not procMan.pexists(name="livefeed_"+self.device.vidquality, devID=self.device.ip+"."+self.device.vidquality)): #there is no live555 associated with this device
                self.startProxy(uid=self.device.username, pwd=self.device.password)

            live555timeout = time.time()-10 #wait for 10 seconds to restart live555 server if it stalls
            
            # stop live555 to restart it later in an attempt to recover a stalled/stopped stream
            if(not self.device.isOn and self.device.liveStart<live555timeout): 
                # timeout reached - there was no stream - restart live555
                # usually this will happen if the ip address or port on the device changed, 
                # restarting live555 will set it up with those new parameters and get the stream going
                dbg.prn(dbg.SRC,"stopping_1 livefeed_{} IP:{}  status:{}".format(self.device.vidquality,self.device.ip, self.device.isOn))
                procMan.pstop(name="livefeed_"+self.device.vidquality, devID=self.device.ip+"."+self.device.vidquality)
                
            # if live555 proxy is running, it'll have an rtsp url - this block will get that url
            oldURL = self.rtspURL
            self.setRTSPurl()
            if (oldURL != self.rtspURL):
                dbg.prn(dbg.SRC,"[######]IDX:{0} {1} {2} {3} URL changed ===>new:{4} old:{5}".format(self.idx, self.device.model, self.device.ip, self.device.vidquality, self.rtspURL, oldURL))

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
                while(procMan.pexists(name=c.CAPTURE+self.device.vidquality, devID = self.device.ip)):
                    #try to stop and wait untill the process is gone 
                    # NB: could stall here if the process refuses to exit or if it's not forced to exit
                    dbg.prn(dbg.SRC,"trying to stoppppppppppppppppp")
                    procMan.pstop(name=c.CAPTURE+self.device.vidquality, devID=self.device.ip+"."+self.device.vidquality)
                capCMD  = self.buildCapCmd()   # this will create the HQ capture command (it's individual based on the type of device)
                # start the ffmpeg process
                procMan.padd(name=c.CAPTURE+self.device.vidquality, devID=self.device.ip, cmd=capCMD, keepAlive=True, killIdle=True, forceKill=True, threshold=5, srcidx=self.idx)
            #end if stream_url_changed !!!

            # get the port (used to connect to rtsp stream to check its state)
            # the url should be in this format: rtsp://192.168.3.140:8554/proxyStream
            # to get the port:
            # 1) split it by colons: get [rtsp, //192.168.3.140, 8554/proxyStream]
            # 2) take 3rd element and split it by /, get: [8554, proxyStream]
            # 3) return the 8554
            # this port is used for a 'telnet' connection to the server (in the next step)
            newrts = int(self.rtspURL.split(':')[2].split('/')[0].strip())
            if (newrts != self.ports['rts']):
                dbg.prn(dbg.SRC,"[######]IDX:{0} {1} {2} {3} RTS HAS CHANGED ===>NEW:{4} OLD:{5}".format(self.idx, self.device.model, self.device.ip, self.device.vidquality, newrts, self.ports['rts']))
            self.ports['rts'] = newrts    
            #end if path.exists
            # check rtsp connectivity if it wasn't checked yet
            if(self.rtspURL and not(self.device.isOn and enc.busy())):# stream wasn't flagged as OK yet
                # send a rtsp DESCRIBE command to check if the streaming server is ok
                msg = "DESCRIBE "+self.rtspURL+" RTSP/1.0\r\nCSeq: 2\r\nAccept: application/sdp\r\nUser-Agent: Python MJPEG Client\r\n\r\n"""
                s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                s.settimeout(2)
                try:
                    s.connect((self.ipcheck, self.ports['rts']))
                    s.send(msg)
                    data = s.recv(65535)
                except Exception as e:
                    data = str(e)
                    dbg.prn(dbg.SRC|dbg.ERR,"[---]source.monitor err: ",e, self.ipcheck, self.ports["rts"])
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
                #pu.mdbg.log("DEVICE STATUS-->IP:{0} DATA:{1}".format(self.rtspURL, data))
                self.device.isOn = (data.find('RTSP/1.0 200 OK')>=0)
                try:
                    show_message = pu.pxpconfig.show_pingcam_check()
                    if (pu.pxpconfig.use_ping_camcheck()):
                        if (not self.device.isOn):
                            self.device.isOn = pu.io.ping(self.device.ip)
                            if (show_message):
                                dbg.prn(dbg.SRC,"-->check cam with ping now...ip:{}  status:{}  url:{}  model:{}".format(self.device.ip, self.device.isOn, self.rtspURL, self.device.model))
                        if (show_message):
                            dbg.prn(dbg.SRC,"-->check cam DEV:{}  status:{}  model:{}  rtsp:{}  data:{}".format(self.rtspURL, self.device.isOn, self.device.model, self.device.rtspURL, strdata))
                except Exception as e:
                    dbg.prn(dbg.SRC|dbg.ERR,"[---]source.monitor ping err:{} ipcheck:{} ports:{} on:{}".format(e, self.ipcheck, self.ports["rts"], self.device.isOn))

            # this next IF cuts the framerate in half if it's 50p or 60p
            # most iPads (as of Aug. 2014) can't handle decoding that framerate (coming by RTSP) using ffmpeg 
            # it will decode about 30-50% slower which will create a noticeable (and growing) lag
            # this is only relevant for medical (or any other system that gets direct RTSP stream)
            # maybe now this is irrelevant and can be removed?
            # if(self.device.initialized and self.device.ccFramerate and self.device.framerate>=50):
            #     self.device.setFramerate(self.device.framerate/2) #set resolution to half if it's too high (for tablet rtsp streaming)

            #when device is initialized already, reset the timer - this timer is used to kill the device if it didn't initialize in a certain amount of time
            if(self.device.initialized):
                self.device.initStarted = int(time.time()*1000) 

            # device is only considered initialized if the stream is on
            # if the stream is unreachable, this will cause device to be re-initialized 
            # or to be removed form the system (if it doesn't start in time) in the sourceManager monitor
            self.device.initialized = self.device.isOn 
        except Exception as e:
            dbg.prn(dbg.ERR|dbg.SRC,"[---]source.monitor {0} {1} {2}".format(self.idx, e, sys.exc_info()[-1].tb_lineno))
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
#                     dbg.prn(dbg.SRC,"[##1]setRTSPurl[{0}] -- {1} -- {2} -- {3} -- {4} -- {5}".format(self.idx, self.urlFilePath, streamURL, self.rtspURL, self.device.ip, self.device.model))
#                 else:
#                     dbg.prn(dbg.SRC,"[##2]setRTSPurl[{0}] -- {1} -- {2} -- {3} -- {4} -- {5}".format(self.idx, self.urlFilePath, streamURL, self.rtspURL, self.device.ip, self.device.model))
        except Exception as e:
            dbg.prn(dbg.ERR|dbg.SRC,"[---]source.setRTSPurl", e, sys.exc_info()[-1].tb_lineno)
    def startProxy(self, uid=False, pwd=False):
        """ Starts the live555  RTSP proxy for this source """
        try:
            #start live555 process for this device
            rtsp_url = self.device.rtspURL
            if (self.device.model.find('AXIS')>=0):
                bitrate, framerate = self.device.getcamdb()
                if (bitrate>0):
                    rtsp_url = self.device.baseRTSPURL + "&videomaxbitrate=" + str(bitrate)  
            
            if (uid):
                live555cmd=c.approot+"live555 -u " + uid + " " + pwd + " -o "+self.urlFilePath+" -p "+str(self.ports['rts'])+" "+rtsp_url
            else:
                live555cmd=c.approot+"live555 -o "+self.urlFilePath+" -p "+str(self.ports['rts'])+" "+rtsp_url
            
            dbg.prn(dbg.SRC,"Adding livefeed for idx:{} FILE:{} PORT:{} IP:{}.{} {} {}".format(self.idx, self.urlFilePath, self.ports['rts'], self.device.ip, self.device.vidquality, self.device.model, self.type))
            
            pname = "livefeed_" + self.device.vidquality
            pdevId = self.device.ip + "." + self.device.vidquality
            procMan.padd(name=pname, devID=pdevId, cmd=live555cmd, keepAlive=True, killIdle=True, forceKill=True, modelname=self.device.model, srcidx=self.idx)
            # record the time of the live555 server start - will be used in the next step to determine when live555 should be restarted
            self.device.liveStart = time.time()
        except Exception as e:
            dbg.prn(dbg.ERR|dbg.SRC,"[---]source.startProxy", e, sys.exc_info()[-1].tb_lineno,)
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
            dbg.prn(dbg.SRC,"stopping_2 livefeed")
            # stop the processes associated with this device
            procMan.pstop(name="livefeed_" + self.device.vidquality, devID=str(self.id) + "." +self.device.vidquality)
            dbg.prn(dbg.SRC,"done stopping")
        except Exception as e:
            dbg.prn(dbg.ERR|dbg.SRC,"[---]source.stopMonitor", e, sys.exc_info()[-1].tb_lineno)
    def stopRTSP(self):
        if(enc.code & enc.STAT_READY): 
            if(self.device.rtspURL and procMan.pexists(name="livefeed_"+self.device.vidquality, devID=self.device.ip+"."+self.device.vidquality)):
                procMan.pstop(name="livefeed_"+self.device.vidquality, devID=self.device.ip+"."+self.device.vidquality)
                dbg.prn(dbg.SRC,"stopping_3 livefeed_" + self.device.vidquality)
    #-----------------------
    def StartDeviceRecord(self):
        try:
            if (self.device.model.find('Monarch')>=0):
                self.device.startRec()
        except Exception as e:
            pass
    def StopDeviceRecord(self):
        try:
            if (self.device.model.find('Monarch')>=0):
                self.device.stopRec()
        except Exception as e:
            pass

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
        self.xfiBase = 20000 #X-Failover Backup main input port - this is where XFB will try to pull the main stream from
        self.xfbBase = 21000 #X-Failover Backup blue screen port - this is where XFB will get the backup stream if XFI port fails
        self.xfoBase = 22000 #X-Failover Backup output port - the XFB will output data on this port
        self.mp4BaseByType = {'sn_snc':22100, 'td_cube':22400, 'sn_axis':22700, 'mt_monarch':23100, 'ph_glass':23400, 'dt_enc':23700} 
        self.hlsBaseByType = {'sn_snc':22200, 'td_cube':22500, 'sn_axis':22800, 'mt_monarch':23200, 'ph_glass':23500, 'dt_enc':23800} 
        self.chkBaseByType = {'sn_snc':22300, 'td_cube':22600, 'sn_axis':22900, 'mt_monarch':23300, 'ph_glass':23600, 'dt_enc':23900} 
        self.rtpBaseByType = {'sn_snc':10100, 'td_cube': 8500, 'sn_axis':14100, 'mt_monarch':15100, 'ph_glass':16100, 'dt_enc':17100} 
        #self.rtpBaseByType = {'sn_snc':8500, 'td_cube':8500, 'sn_axis':8500, 'mt_monarch':8500, 'ph_glass':8500} 
        #self.mp4BaseByType = {'sn_snc':22500, 'td_cube':22500, 'sn_axis':22500, 'mt_monarch':22500, 'ph_glass':22500} 
        #self.hlsBaseByType = {'sn_snc':22600, 'td_cube':22600, 'sn_axis':22600, 'mt_monarch':22600, 'ph_glass':22600} 
        #self.chkBaseByType = {'sn_snc':22700, 'td_cube':22700, 'sn_axis':22700, 'mt_monarch':22700, 'ph_glass':22700} 
        self.sources = [] #video sources go here
        self.devList = devList
        if(not 'srcmgr' in tmr):
            tmr['srcmgr'] = {}
        tmr['srcmgr']['mgrmon'] = TimedThread(self.monitor, period=3)
        tmr['srcmgr']['discvr'] = TimedThread(self.discovererManage, period=3)
        self.total_cams = 0
        self.total_feeds = 0
        self.camip_vq = {}
        # adjust mp4 starting point for alignment
        self.evt_stat = {}
        self.rec_stat_worker = False
        self.checkStatDone = True    
        self.evt_path = ''
        self.ffcaps = {} #ffmpeg commands to capture data from XFB and push it to mp4 recorders, HLS segmenters, and whomever else
        self.xfbcaps = {} #ffmpeg commands to capture data from the device and push it to XFB
        self.xfbcmds = {} #xfb utility commands

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
        global devaddingnow
        devaddingnow = True
        try:
            if((enc.code & enc.STAT_SHUTDOWN) or enc.busy()):#do not add new cameras during live event
                devaddingnow = False
                return False
            if(len(self.sources)>c.maxSources): #do not add more than maximum allowed sources in the system
                devaddingnow = False
                return False
            sources = copy.deepcopy(self.sources)
            if(not((('url' in inputs) or ('preview' in inputs)) and ('ip' in inputs))):
                #neither url nor preview was specified or ip wasn't specified - can't do anything with this encoder
                devaddingnow = False
                return False
#             if (not pu.disk.checkip(appg.mainip, inputs['ip'])):
#                 if ('model' in inputs):
#                     pu.mdbg.log("-->adddevice_{0} IP:{1} is excluded in PXP_IP:{2}".format(inputs['model'], inputs['ip'], appg.mainip))
#                 else:
#                     pu.mdbg.log("-->adddevice IP:{0} is excluded in PXP_IP:{1}".format(inputs['ip'], appg.mainip))
#                 return False

            ip = inputs['ip']
            vq = inputs['vid-quality']
            idx = self.vqexists(sources, ip, vq)
            if(idx>=0): 
                # this device already exists in the list
                # must've re-discovered it, or discovered another streaming server on it (e.g. preview)
                if('url' in inputs): #update url (in case it's changed)
                    self.sources[idx].device.rtspURL = inputs['url']
                    self.sources[idx].device.baseRTSPURL = self.sources[idx].device.rtspURL 
                elif('preview' in inputs):
                    self.sources[idx].previewURL = inputs['preview']
                    self.sources[idx].device.baseRTSPURL = self.sources[idx].device.rtspURL
                if('port' in inputs): #update the ports as well (may have changed)
                    self.sources[idx].ports['rtp'] = inputs['port']
                if('preview-port' in inputs):
                    self.sources[idx].ports['rtp'] = inputs['preview-port']
                if ('serialport' in inputs):
                    self.sources[idx].device.set_dtparams(inputs['serialport'])
                if ('td_cube'==inputs['type'] and not self.sources[idx].device.mac):
                    ans = self.sources[idx].device.getmac()
                    if (ans):
                        self.sources[idx].device.mac = self.sources[idx].device.getParam(ans,'macaddress')
                #dbg.log(dbg.SRC, "-->founddev: IP:{} VQ:{} idx:{} ports:{} name:{} mac:{}".format(ip, vq, idx, self.sources[idx].ports, self.sources[idx].device.model, self.sources[idx].device.mac))
                devaddingnow = False
                return True
            # endif 

            # discovered a new streaming device
            idx = self.nextIdx(sources)
            
            #device does not exist yet (just found it)
            #assign ports accordingly
            ports = {
                    "mp4":self.mp4Base+2*idx,
                    "hls":self.hlsBase+2*idx,
                    "chk":self.chkBase+2*idx,
                    "xfo":self.xfoBase+2*idx,
                    "xfb":self.xfbBase+2*idx,
                    "xfi":self.xfiBase+2*idx,
                    "rts":self.rtpBase+(2*idx*50), # each camera has 100 rtsp/rtp proxy ports - in case it needs to restart the live555 instance and it doesn't have a proxy port available, it can increment it
                }
            # override port number to make distinct port number camera to camera.
            # this is needed when same idx is detected due to concurrent call. (before self.sources length is updated).  
            # by distigushing the base port number, it can avoid duplicated port number.
            cam_type = False
            try:
                if ('type' in inputs):
                    cam_type = inputs['type']
                    ports['mp4'] = self.mp4BaseByType[cam_type]+2*idx
                    ports['hls'] = self.hlsBaseByType[cam_type]+2*idx
                    ports['chk'] = self.chkBaseByType[cam_type]+2*idx
                    ports['rts'] = self.rtpBaseByType[cam_type]+(2*idx*50)
            except:
                pass
                
            newsrc = False
            if('url' in inputs):#the device discovered was the main url device
                ports['rtp'] = int(inputs['port'])
                newsrc = source(vq=inputs['vid-quality'], ip=ip, url=inputs['url'], encType=inputs['type'], ports=ports, devClass=inputs['devClass'], uid=inputs['username'], pwd=inputs['password'], realm=inputs['realm'], mac=inputs['mac'], modelname=inputs['model'], idx=idx)
                #dbg.log(dbg.SRC, "-->adddev: HQ found IP:{0} VQ:{1} idx:{2} ports:{3}".format(ip, vq, idx, ports))
            elif('preview' in inputs):#discovered the preview version of the device
                ports['rtp'] = int(inputs['preview-port'])
                newsrc = source(vq=inputs['vid-quality'], ip=ip, preview=inputs['preview'], encType=inputs['type'], ports=ports, devClass=inputs['devClass'], uid=inputs['username'], pwd=inputs['password'], realm=inputs['realm'], mac=inputs['mac'], modelname=inputs['model'], idx=idx)
                #dbg.log(dbg.SRC, "-->adddev: LQ found IP:{0} VQ:{1} idx:{2} ports:{3}".format(ip, vq, idx, ports))
            if(newsrc):
                newsrc.idx = idx
                if ('serialport' in inputs):
                    newsrc.device.set_dtparams(inputs['serialport'])
                    newsrc.device.dev = inputs['delta_dev'] # copy proxy device found in discovery
                if ('td_cube'==inputs['type'] and not newsrc.device.mac):
                    ans = newsrc.device.getmac()
                    if (ans):
                        newsrc.device.mac = newsrc.device.getParam(ans,'macaddress')
                    else:
                        newsrc.device.mac = False
                        if ('url' in inputs):
                            dbg.log(dbg.SRM, "MAC cannot found...{}".format(inputs['url']))
                self.sources.append(newsrc)
                #dbg.prn(dbg.SRM,"all sources (devices): ", self.sources)
                appg.updateVideoSourceCount(len(self.sources))
                devaddingnow = False        
                msgstr = "-->Adding Device-->idx:{}/{} ip:{} vq:{} type:{} ports:{} mac:{} model:{}".format(idx, len(self.sources), ip, inputs['vid-quality'], cam_type, ports, newsrc.device.mac, newsrc.device.model)
                dbg.log(dbg.SRM, msgstr)
                return True
        except Exception as e:
            dbg.prn(dbg.SRM|dbg.ERR, "[---]srcMgr.addDevice: ",e, sys.exc_info()[-1].tb_lineno)
            devaddingnow = False            
        devaddingnow = False        
        return False
    #end addDevice

    def discovererManage(self):
        """ Starts device discoverers if the current server is master or stops them if it's not """
        try:
            if(enc.code & enc.STAT_SHUTDOWN):
                if('srcmgr' in tmr):
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
                if (not pu.pxpconfig.support_cam(devName)):
                    dbg.prn(dbg.SRM, "cam type:{} not supported".format(devName))
                    continue
                dev = self.devList[devName]['class']()
                tmr['srcmgr']['devs'][devName] = TimedThread(dev.discover, params=self.addDevice, period=5)
        except Exception as e:
            dbg.prn(dbg.ERR|dbg.SRM, "[---]srcMgr.discover: ",e, sys.exc_info()[-1].tb_lineno)
    
    def dumpSources(self):
        pass
    
    def encCapPause(self):
        """ Pause a live stream """
        if(enc.code & enc.STAT_LIVE):
            dbg.log(dbg.ENC, "EVENT_PAUSES =========================================> SRC_LEN:{0}".format(len(self.sources)))
            enc.statusSet(enc.STAT_PAUSED)
            procMan.pstop(name=c.CAPTURE+'HQ',remove=True)
            procMan.pstop(name=c.CAPTURE+'LQ',remove=True)
            for idx in xrange(len(self.sources)):
                if(idx>=len(self.sources)):
                    break
                src = self.sources[idx]
                if(not src.isEncoding):
                    continue
                if (src.device.model.find("Monarch")>=0):
                    src.device.stopRec()
                    src.device.collect_mp4(c.live_video)

    def encCapResume(self):
        """ Resume a paused live stream """
        if(enc.code & enc.STAT_PAUSED):
            dbg.log(dbg.ENC, "EVENT_RESUMES =========================================> SRC_LEN:{0}".format(len(self.sources)))                    
            #procMan.pstart(name='capture_HQ')
            #procMan.pstart(name='capture_LQ')
            for idx in xrange(len(self.sources)):
                if(idx>=len(self.sources)):
                    break
                src = self.sources[idx]
                if(not src.isEncoding):
                    continue
                if (src.device.model.find("Monarch")>=0):
                    src.device.startRec()
                postfix = src.device.vidquality
                startSuccess = procMan.padd(name=c.CAPTURE+postfix, devID=src.device.ip+"."+postfix, cmd=self.ffcaps[src.device.ip+"."+postfix], keepAlive=True, killIdle=True, forceKill=True, threshold=5, modelname=src.device.model, srcidx=src.idx)
                #tmr['portCHK'][src.device.ip+"."+postfix]=TimedThread(self.sources[idx].camPortMon)
                dbg.prn(dbg.SRM, "resuming...{}".format(idx))
        time.sleep(2)
        enc.statusSet(enc.STAT_LIVE)
        
    def build_m3u8(self, cidx, cvq, m3u8_file=""):
        """
        Build m3u8 file in the event folder when the structured folder system is used.
        """
        templ_file = c.wwwroot + "_db/list_templ.m3u8"
        if (m3u8_file==""):
            m3u8_file = c.live_video + "list_" + cidx + cvq + ".m3u8"
        os.system("cp " + templ_file + " " + m3u8_file)
        with open(m3u8_file) as f:
            m3u8_str = f.read()
        f.close()
        m3u8_str = m3u8_str.replace("{{{folder}}}", cvq + "_" + cidx)
        #m3u8_str = m3u8_str.replace("{{{folder}}}", "http://127.0.0.1/min/events/live/video/"+cvq + "_" + cidx)        
        m3u8_str = m3u8_str.replace("{{{m3u8}}}", "list_" + cidx + cvq + ".m3u8")
        with open(m3u8_file, "w") as f:
            f.write(m3u8_str)
        f.close()        
        
    def encCapStart(self, evt_hid=''):
        """ Start live stream """
        dbg.prn(dbg.SRM, "\n\n\n\ncap start")
        try:
            if(not (enc.code & enc.STAT_READY)): #tried to start a stream that's already started or when there are no cameras
                return False
            
            if (self.checkStatDone == False):
                dbg.log(dbg.SRM, "Cannot do EVENT_STARTS: postprocessing is performing...")                    
                return False
                
            self.checkStatDone == False
            self.evt_path = evt_hid
            
            dbg.log(dbg.SRM, "EVENT_STARTS =========================================> SRC_LEN:{0} EVT_HID:{1}".format(len(self.sources), evt_hid))                    
            enc.statusSet(enc.STAT_START)            

            dbg.log(dbg.SRM, "EVENT_STARTS --> 1")                    

            
            # make sure ffmpeg's and segmenters are off:
            os.system("killall -9 "+c.segname+" 2>/dev/null")
            os.system("killall -9 "+c.ffname+" 2>/dev/null")

            dbg.log(dbg.SRM, "EVENT_STARTS --> 2")                    
            
            self.rec_stat_worker = False
            self.evt_stat = {}

            dbg.log(dbg.SRM, "EVENT_STARTS --> 3")                    
            
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
            self.ffcaps = {}
            streamid = 0
            # old versions of the app do not dynamically read urls, the url (events/live/list.m3u8) is hard-coded (why?!!)
            # and thus with multicam (or single camera but new server) setup it will not work
            # for backwards compatibility, use first camera as "the only" camera available for streaming 
            # and create a soft link to the first list_XX.m3u8
            oldSupportSuffix = -1
            # go through each source and set up the streaming/capturing services

            dbg.log(dbg.SRM, "EVENT_STARTS --> 4")                    

            
            EVERY_RECS = 1
            ffrecs = {}
            mapIdx = 0
            ffMP4recorder = ""
             
            srcs = pp.pformat(self.sources, indent=4)
            dbg.log(dbg.SRM, "SOURCES-->", "\n"+srcs)
                                     
            self.camip_vq = {}        
            feedIdx = -1
            
            precmdopt = pu.pxpconfig.pre_rec_conf()
            postcmdopt = pu.pxpconfig.post_rec_conf()
                                                 
            # command line for ffmpeg that captures from camera itself and forwards data to XFB
            ffCapCmdTpl = "{ff} -fflags +igndts -rtsp_transport udp -i {url} -codec copy -f mpegts udp://127.0.0.1:{xfi}"
            # start XFB command 
            #   xfbin - path to the xfb binary
            #   xfi - input port (output of ffCapCmdTpl)
            #   xfb - backup port (where filler data is coming in)
            #   xfo - output port
            xfbCmdTpl = "{xfbin} -t {timeout} {xfi} {xfb} {xfo}"
            xfbStreams = [] #list of urls where backup streams will be pushed

            for idx in xrange(len(self.sources)):
                if(idx>=len(self.sources)): #would only go here if number of sources changed during iteration. there are checks to prevent this
                    dbg.log(dbg.SRM, "SOURCE_IDX-->{}/{} error:number of sources changed during iteration".format(idx, len(self.sources)))
                    break
                src = self.sources[idx]
                
                if(not(src.device.isCamera and src.device.isOn)):#skip devices that do not have a video stream available
                    dbg.log(dbg.SRM, "CHECK SOURCE_IDX-->{}/{} idx:{} model:{} ip:{} vq:{} url:{} ports:{} (cam:{} on:{} mac:{})".format(idx, len(self.sources), src.idx, src.device.model, src.device.ip, src.device.vidquality, src.rtspURL, src.ports, src.device.isCamera, src.device.isOn, src.device.mac)) 
                    continue
                else:
                    dbg.log(dbg.SRM, "STARTING SOURCE_IDX-->{}/{} idx:{} model:{} url:{} ports:{} (cam:{} on:{} mac:{})".format(idx, len(self.sources), src.idx, src.device.model, src.rtspURL, src.ports, src.device.isCamera, src.device.isOn, src.device.mac)) 
                                
                # # each camera has its own ffmpeg running it, otherwise if 1 camera goes down, all go lldown with it
                # if('format' in cameras[devID] and 'devID'=='blackmagic'): #format is explicitly specified for this camera (usually for blackmagic)
                #   ffstreamIn = c.ffbin+" -y -f "+cameras[devID]['format']+" -i "+cameras[devID]['url']
                #   ffstreamIn += " -codec copy -f h264 udp://127.0.0.1:221"+str(streamid)
                #   ffstreamIn += " -codec copy -f mpegts udp://127.0.0.1:220"+str(streamid)
                #   ffstreamIns.append(ffstreamIn)
                # for saving multiple mp4 files, one ffmpeg instance can accomplish that
                camIdx  = str(idx) #obsolete, camip_vq[ip][vq].zfill(2) used instead.
                postfix = src.device.vidquality
                vidq = postfix.lower()

                if (src.device.ip in self.camip_vq): # found
                    if ('hq' in self.camip_vq[src.device.ip]):
                        self.camip_vq[src.device.ip][vidq] = self.camip_vq[src.device.ip]['hq']
                    elif ('lq' in self.camip_vq[src.device.ip]):
                        self.camip_vq[src.device.ip][vidq] = self.camip_vq[src.device.ip]['lq']
                else:
                    feedIdx += 1
                    self.camip_vq[src.device.ip] = {}
                    self.camip_vq[src.device.ip][vidq] = str(feedIdx)
                
                camMP4  = str(src.ports['mp4']) #ffmpeg captures rtsp from camera and outputs h.264 stream to this port
                camHLS  = str(src.ports['hls']) #ffmpeg captures rtsp form camera and outputs MPEG-TS to this port
                chkPRT  = str(src.ports['chk']) #port where a monitor is sitting and checking if packets are arriving, doesn't matter the format
                #xfb backup stream - blue screen (or filler) video - includes all ffmpeg output parameters
                xfbStreams.append("-c copy -f mpegts udp://127.0.0.1:"+str(src.ports['xfb']))

                self.xfbcaps[src.device.ip+'.'+postfix] = ffCapCmdTpl.format(ff=c.ffbin,url=src.rtspURL,xfi=src.ports['xfi'])
                self.xfbcmds[src.device.ip+'.'+postfix] = xfbCmdTpl.format(xfbin=c.approot+"xfb", timeout=150, \
                                                                xfi=src.ports['xfi'], xfb=src.ports['xfb'], xfo=src.ports['xfo'])
                # if(len(self.sources)<2):
                #     listSuffix = ""
                #     # there is only one camera - no need to set camIdx for file names
                #     filePrefix = ""
                # else: #multiple cameras - need to identify each file by camIdx
                # always add source indecies - future server versions will deprecate old style file naming
                #filePrefix = camIdx.zfill(2)+ postfix.lower() + '_' #left-pad the camera index with zeros (easier to sort through segment files and thumbnails later on)
                #listSuffix = "_"+camIdx.zfill(2)+ postfix.lower() #for normal source, assume it's high quality                                
                sidx = self.camip_vq[src.device.ip][vidq].zfill(2)    
                filePrefix = sidx + vidq + '_'   # 00hq_
                listSuffix = "_" + sidx + vidq   # _00hq
                
                cpath = c.live_video
                if (pu.pxpconfig.use_split_event_folder()):
                    cpath = c.live_video + vidq + "_" + sidx
                    dbg.log(dbg.SRM, "camip_vq-->ip:{} vq:{} feedIdx:{} sidx:{} dir:{}".format(src.device.ip, vidq, feedIdx, sidx, cpath))
                    try:
                        os.mkdir(cpath)
                    except:
                        pass

                # backward-compatibility for old ipad app versions
                if(oldSupportSuffix<1):
                    oldSupportSuffix = listSuffix
                dbg.log(dbg.SRM, "ENC_PORTS-->", src.device.ip+"."+postfix, src.rtspURL, src.ports, src.device.model)    

                self.sources[idx].listFile = 'list' + listSuffix + '.m3u8'
                
                #-------------------------------------------- record command line
                # ffmpeg -fflags +igndts -i tcp://127.0.0.1:5678 -f mpegts -vcodec copy -acodec copy -bsf:a aac_adtstoasc abc.mp4
                sock_feed = "udp://127.0.0.1:" + camMP4
                if (pu.pxpconfig.use_mp4tcp()):
                    sock_feed = "tcp://127.0.0.1:" + camMP4 + "?listen"
                ffmp4Ins +=" -fflags +igndts -i " + sock_feed 

                mapIdx = idx % EVERY_RECS
                ffmp4out_destpath =  c.wwwroot + "live/video/" 
                if (pu.pxpconfig.use_split_event_folder()):
                    ffmp4out_destpath =  cpath + "/" 
                if (pu.pxpconfig.post_rec_conf()==""):
                    ffmp4Out +=" -map " + str(mapIdx) + " -fflags +igndts -codec copy -bsf:a aac_adtstoasc " + ffmp4out_destpath + "main"+listSuffix + ".mp4"
                else:
                    newcmdopt = " -map " + str(mapIdx) + " " + precmdopt + " " + postcmdopt + " " + ffmp4out_destpath + "main"+listSuffix + ".mp4"                    
                    newcmdopt = newcmdopt.replace("  ", " ") 
                    ffmp4Out += newcmdopt

                # ismv muxer AVOptions: (fragmented MP4 as ISMV (Smooth Streaming) file)
                # -movflags          <flags> E.... MOV muxer flags
                #    rtphint                 E.... Add RTP hint tracks
                #    empty_moov              E.... Make the initial moov atom empty (not supported by QuickTime)
                #    frag_keyframe           E.... Fragment at video keyframes
                #    separate_moof           E.... Write separate moof/mdat atoms for each track
                #    frag_custom             E.... Flush fragments on caller requests
                #    isml                    E.... Create a live smooth streaming feed (for pushing to a publishing point)
                # -moov_size         <int>   E.... maximum moov size so it can be placed at the begin
                # -rtpflags          <flags> E.... RTP muxer flags
                #    latm                    E.... Use MP4A-LATM packetization instead of MPEG4-GENERIC for AAC
                #    rfc2190                 E.... Use RFC 2190 packetization instead of RFC 4629 for H.263
                #    skip_rtcp               E.... Don't send RTCP sender reports
                # -skip_iods         <int>   E.... Skip writing iods atom.
                # -iods_audio_profile <int>  E.... iods audio profile atom.
                # -iods_video_profile <int>  E.... iods video profile atom.
                # -frag_duration     <int>   E.... Maximum fragment duration
                # -min_frag_duration <int>   E.... Minimum fragment duration
                # -frag_size         <int>   E.... Maximum fragment size
                # -ism_lookahead     <int>   E.... Number of lookahead entries for ISM files

                # this is HLS capture (segmenter)
                segment_conf = pu.pxpconfig.segment_conf()
                if (segment_conf==""):
                    segment_conf = c.segment_conf
                    
                segbin_destpath = c.wwwroot+"live/video"
                if (pu.pxpconfig.use_split_event_folder()):
                    segbin_destpath = cpath
                if (pu.osi.name=='mac'): #mac os
                    #segmenters[src.device.ip+"."+postfix] = c.segbin+" -p -t 1s -S 1 -B "+filePrefix+"segm_ -i "+self.sources[idx].listFile+" -f "+c.wwwroot+"live/video 127.0.0.1:"+camHLS
                    segmenters[src.device.ip+"."+postfix] = c.segbin+" " + segment_conf + " " + filePrefix + "segm_ -i " + self.sources[idx].listFile +" -f " + segbin_destpath + " 127.0.0.1:" + camHLS
                elif(pu.osi.name=='linux'): #linux
                    os.chdir(c.wwwroot+"live/video")
                    segmenters[src.device.ip+"."+postfix] = c.segbin+" -d 1 -p "+filePrefix+"segm_ -m list"+filePrefix+".m3u8 -i udp://127.0.0.1:"+camHLS+" -u ./"

                # ffmpeg command line
                #dbg.prn(dbg.DBG, "capcmd:",src.rtspURL, chkPRT, camMP4, camHLS)
                self.ffcaps[src.device.ip+"."+postfix] = src.buildCapCmd()
                self.sources[idx].ffcap_cmd = self.ffcaps[src.device.ip+"."+postfix] 
                self.sources[idx].ffseg_cmd = segmenters[src.device.ip+"."+postfix] 
                self.sources[idx].isEncoding = True
                
                if ((idx%EVERY_RECS) == (EVERY_RECS-1)):
                    ffrecs['rec_'+str(idx)] = ffmp4Ins + ffmp4Out
                    self.sources[idx].ffrec_cmd = ffrecs['rec_'+str(idx)] 
                    ffmp4Ins = c.ffbin + " -y"
                    ffmp4Out = ""
                
                #  Create m3u8 playlist link
                if (pu.pxpconfig.use_split_event_folder()):
                    #os.system("ln -s " + cpath + "/" + "list" + listSuffix + ".m3u8 " + c.live_video + "list" + listSuffix + ".m3u8 >/dev/null 2>/dev/null")
                    self.build_m3u8(sidx, vidq)
                # start ffmpeg capture for XFB
                procMan.padd(cmd=self.xfbcaps[src.device.ip+'.'+postfix],name="xfcap_"+postfix, devID="xfcap_"+str(idx), forceKill=True,modelname="xfcap_"+str(idx))
                dbg.prn(dbg.SRC, "ENC_REC_START----> xfbcap:{} cmd:{}".format(src.device.ip, self.xfbcaps[src.device.ip+'.'+postfix]))
                # XFB process itself
                procMan.padd(cmd=self.xfbcmds[src.device.ip+'.'+postfix],name="xfbin_"+postfix, devID="xfbin_"+str(idx), forceKill=True,modelname="xfbin_"+str(idx))
                dbg.prn(dbg.SRC, "ENC_REC_START----> xfbbin:{} cmd:{}".format(src.device.ip, self.xfbcmds[src.device.ip+'.'+postfix]))

            #end for ------------------------------------------------------------- 
            
            # start bluescreen capture utility - it'll need all the xfb ports for all of the sources
            # only need 1 ffmpeg to push data to all the required ports. since it's pushing to UDP ports
            # it doesn't matter if any of the listeners go down - it won't affect the rest of the process
            # dbg.prn(dbg.SRC,"ENC_REC_START-----> loss_filler:{}".format(xfbStreams))
            fillCmdTpl = "{ff} -stream_loop -1 -re -i filler.ts {xfb_streams}"
            fillCmd = fillCmdTpl.format(ff = c.ffbin, xfb_streams = " ".join(xfbStreams))
            procMan.padd(cmd = fillCmd, name="loss_filler", devID="loss_filler", forceKill = True, modelname="loss_filler")

            if (len(ffmp4Out) > 0): 
                ffMP4recorder = ffmp4Ins + ffmp4Out
            else:
                ffMP4recorder = ""

            time.sleep(2) #wait for previous ffmpeg's to start - ensure that recording will start at the same time

            # start the HLS segmenters and rtsp/rtmp captures
            segmenterLater = pu.pxpconfig.use_segment_later()
            startSuccess = True
            tmr['portCHK'] = {}
            for idx in xrange(len(self.sources)):
                if(idx>=len(self.sources)):
                    break
                src = self.sources[idx]
                if(not src.isEncoding):
                    continue
                postfix = src.device.vidquality
                
                if (src.device.model.find("Monarch")>=0):
                    src.StartDeviceRecord()
                    
                if (pu.pxpconfig.use_mp4tcp()):
                    # recording mp4
                    if ((idx%EVERY_RECS) == (EVERY_RECS-1) and len(ffrecs) > 0):
                        startSuccess = startSuccess and procMan.padd(cmd=ffrecs['rec_'+str(idx)],name="record_"+postfix, devID="rec_"+str(idx),  \
                                forceKill=False, modelname="rec_"+str(idx))
                        dbg.prn(dbg.DBG, "ENC_REC_START----> record_{} cmd:{}".format(postfix, ffrecs['rec_'+str(idx)]))
                    # segmenter
                    if (not segmenterLater):
                        startSuccess = startSuccess and procMan.padd(name="segment_"+postfix, devID=src.device.ip+"."+postfix, cmd=segmenters[src.device.ip+"."+postfix], forceKill=True, modelname=src.device.model, srcidx=src.idx)
                    # ffmpeg RTSP capture
                    startSuccess = startSuccess and procMan.padd(name=c.CAPTURE+postfix, devID=src.device.ip+"."+postfix, cmd=self.ffcaps[src.device.ip+"."+postfix], keepAlive=True, killIdle=True, forceKill=True, threshold=5, modelname=src.device.model, srcidx=src.idx)
                    # start port checkers for each camera
                    tmr['portCHK'][src.device.ip+"."+postfix]=TimedThread(self.sources[idx].camPortMon)
                else:
                    # segmenter
                    if (not segmenterLater):
                        startSuccess = startSuccess and procMan.padd(name="segment_"+postfix, devID=src.device.ip+"."+postfix, cmd=segmenters[src.device.ip+"."+postfix], forceKill=True, modelname=src.device.model, srcidx=src.idx)
                    # ffmpeg RTSP capture
                    startSuccess = startSuccess and procMan.padd(name=c.CAPTURE+postfix, devID=src.device.ip+"."+postfix, cmd=self.ffcaps[src.device.ip+"."+postfix], keepAlive=True, killIdle=True, forceKill=True, threshold=5, modelname=src.device.model, srcidx=src.idx)
                    # start port checkers for each camera
                    tmr['portCHK'][src.device.ip+"."+postfix]=TimedThread(self.sources[idx].camPortMon)
                    if ((idx%EVERY_RECS) == (EVERY_RECS-1) and len(ffrecs) > 0):
                        #startSuccess = startSuccess and procMan.padd(cmd=ffMP4recorder,name="record",devID="ALL",forceKill=False)
                        startSuccess = startSuccess and procMan.padd(cmd=ffrecs['rec_'+str(idx)],name="record_"+postfix, devID="rec_"+str(idx),  \
                                forceKill=False, modelname="rec_"+str(idx))
                        dbg.prn(dbg.DBG, "ENC_REC_START----> record_{} cmd:{}".format(postfix, ffrecs['rec_'+str(idx)]))
                # update cams table                
#                 db = pu.db(c.wwwroot+"_db/pxp_main.db")
#                 sqlcmd = "INSERT INTO `cams` (`hid`, `camip`, `vq`, `camurl`, `error`, `mac`, `starttime`, `name`, `rts`, `chk`, `mp4`) VALUES(?,?,?,?,?,?,?,?,?,?,?)"
#                 db.query(sqlcmd, (evt_hid, src.device.ip, src.device.vidquality, src.device.ip, 'sucess', \
#                     src.device.mac, "datetime('now','localtime')", src.device.model, \
#                     src.ports['hls'], src.ports['chk'], src.ports['mp4']))
#                 db.close()

            # ======== start segmenter after ffmpegs are all started...by Andrei
            dbg.prn(dbg.SRM, "ENC_REC_START----> segmenterLater:{}".format(segmenterLater))
            all_stream_ok = False
            if (segmenterLater):
                # For this to be continued, all of src.device.isOn should be  ok
                check_time = time.time() 
                while(True):
                    count = 0
                    for idx in xrange(len(self.sources)):
                        if(idx>=len(self.sources)):
                            break
                        src = self.sources[idx]
                        if(not src.isEncoding):
                            continue
                        if (src.device.isOn):
                            count += 1
                    if (count == len(self.sources)):
                        all_stream_ok = True
                        break
                    if ((time()-check_time)>3): # will wait 3 seconds...
                        break
                
                dbg.prn(dbg.SRM, "ENC_REC_START----> segmenterLater:{}  all_stream_ok:{}".format(segmenterLater, all_stream_ok))
                for idx in xrange(len(self.sources)):
                    if(idx>=len(self.sources)):
                        break
                    src = self.sources[idx]
                    if(not src.isEncoding):
                        continue
                    postfix = src.device.vidquality
                    startSuccess = startSuccess and procMan.padd(name="segment_"+postfix, devID=src.device.ip+"."+postfix, cmd=segmenters[src.device.ip+"."+postfix], forceKill=True, modelname=src.device.model, srcidx=src.idx)

            #end for ------------------------------------------------------------- 
            
            self.total_cams = feedIdx+1
            dbg.prn(dbg.SRM, "ENC_REC_START----> total number of physical cams: {}".format(self.total_cams))
            self.total_feeds = 0
            for ipcam in self.camip_vq.keys():
                self.total_feeds += len(self.camip_vq[ipcam])
            dbg.prn(dbg.SRM, "ENC_REC_START----> total number of running feeds: {}".format(self.total_feeds))
            camips = pp.pformat(self.camip_vq, indent=4)
            dbg.prn(dbg.SRM, "ENC_REC_START----> {}".format(camips))

            if (ffMP4recorder != ""):
                startSuccess = startSuccess and procMan.padd(cmd=ffMP4recorder, name="record", devID="ALL", forceKill=False, modelname="rec_"+str(idx), srcidx=src.idx)
                dbg.prn(dbg.DBG, "ENC_REC_START----> record cmd:{}".format(ffMP4recorder))

            if (not startSuccess): #the start didn't work, stop the encode
                self.encCapStop() #it will be force-stopped automatically in the stopcap function
                
            # Create file links for m3u8 and mp4 files ---------------------
            try:
                if (startSuccess and pu.pxpconfig.use_split_event_folder()):
                    old_playlist = False
                    for srcidx in xrange(len(self.sources)):
                        if(srcidx>=len(self.sources)):
                            break
                        #pu.mdbg.log("srcidx:{}".format(srcidx))
                        cfeed = self.sources[srcidx]
                        cvq = cfeed.device.vidquality.lower()
                        if (cfeed.device.ip in self.camip_vq and cvq in self.camip_vq[cfeed.device.ip]):
                            cidx = self.camip_vq[cfeed.device.ip][cvq].zfill(2)    
                            feedpath = c.live_video + cvq + "_" + cidx
                            
                            live_mp4_linkpath = c.live_video + "main_" + cidx + cvq + ".mp4"
                            if (not os.path.exists(live_mp4_linkpath)):
                                os.system("ln -s " + feedpath + "/" + "main_" + cidx + cvq + ".mp4 " + c.live_video + "main_" + cidx + cvq + ".mp4 >/dev/null 2>/dev/null")
                            else:
                                dbg.prn(dbg.SRM,"encCapStart-->{} is not existing".format(live_mp4_linkpath))
                            if (not old_playlist and cvq == 'hq'):
                                if (not os.path.exists(c.live_video + "list.m3u8")):
                                    self.build_m3u8(sidx, vidq, c.live_video +  "list.m3u8")
                                    # It would be regarded old system if this line is activated...
                                    #os.system("ln -s " + feedpath + "/" + "main_" + cidx + cvq + ".mp4 " + c.live_video + "main.mp4 >/dev/null 2>/dev/null")
                                    old_playlist = True
                                else:
                                    dbg.prn(dbg.SRM,"encCapStart-->{} is not existing".format(c.live_video + "list.m3u8"))
            except Exception as e:
                dbg.prn(dbg.ERR|dbg.SRM,"[---]link-creation-error: ", e, sys.exc_info()[-1].tb_lineno)
                pass
        except Exception as e:
            dbg.prn(dbg.ERR|dbg.SRM,"[---]encCapStart: ", e, sys.exc_info()[-1].tb_lineno)
            self.encCapStop() #it will be force-stopped automatically in the stopcap function
            enc.statusSet(enc.STAT_READY)

    def encCapStop(self,force=False):
        """ Stops live stream, kill all ffmpeg's and segmenters
            Args:
                force (bool,optional) : force-kill all the processes - makes stopping process faster
        """
        try:
            dbg.log(dbg.SRM, "")
            dbg.log(dbg.SRM, "EVENT_STOPS =========================================> SRC_LEN:{0}".format(len(self.sources)))

            content = pu.disk.file_get_contents(c.wwwroot+"live/evt.txt")
            if (content):
                self.evt_path = content.strip()


            USE_BLUE = pu.pxpconfig.use_blue_cmd()       # use blue or SIGINT??
            EVERY_BLUE = 1
            
            dbg.prn(dbg.SRM,"stopping capture... force:{}  blue:{}".format(force, USE_BLUE))
            if(enc.code & enc.STAT_STOP): #already stopping
                return False
            if(not(enc.code & (enc.STAT_LIVE | enc.STAT_PAUSED))):
                force = True #the encode didn't finish starting or didn't start properly - force shut down everything
            if(not (enc.code & enc.STAT_SHUTDOWN)): #set the status to stopping (unless the script is being shut down then it should stay at shutting down)
                enc.statusSet(enc.STAT_STOP)
            
            # stop all captures
            dbg.prn(dbg.SRM,"stopping segment and capture")
                        
                                    
            # TRY STOPPPING CAPTURE_HQ/LQ and SEGMENT_HQ/LQ GENTLY            
            procMan.pstop(name=c.SEGMENT+"HQ")
            procMan.pstop(name=c.CAPTURE+"HQ")
            procMan.pstop(name=c.SEGMENT+"LQ")
            procMan.pstop(name=c.CAPTURE+"LQ")
            
            for idx in xrange(len(self.sources)):
                if(idx>=len(self.sources)):
                    break
                src = self.sources[idx]
                if(not src.isEncoding):
                    continue
                if (src.device.model.find("Monarch")>=0):
                    src.StopDeviceRecord()                
                self.sources[idx].isEncoding = False
            #end for
                
            # FORCED TO STOP CAPTURE_HQ/LQ and SEGMENT_HQ/LQ            
            timeout = 20            # how many seconds to wait for process before force-stopping it
            timeStart = time.time() # start the timeout timer to make sure the process doesn't hang here
            #while((procMan.palive("capture_HQ") or procMan.palive("segment_HQ") or procMan.palive("capture_LQ") or procMan.palive("segment_LQ")) and (not (enc.code & enc.STAT_SHUTDOWN)) and (time.time()-timeStart)<timeout):
            while((procMan.palive("capture_HQ") or procMan.palive("segment_HQ") or procMan.palive("capture_LQ") or procMan.palive("segment_LQ")) and (not (enc.code & enc.STAT_SHUTDOWN)) and (time.time()-timeStart)<timeout):
                time.sleep(1)
            # couldn't stop 
            if((time.time()-timeStart)>=timeout): #timeout reached
                if(procMan.palive(c.CAPTURE+"HQ")): #force-stop the capture ffmpeg
                    procMan.pstop(name=c.CAPTURE+"HQ", force=True)
                if(procMan.palive(c.CAPTURE+"LQ")): #force-stop the capture ffmpeg
                    procMan.pstop(name=c.CAPTURE+"LQ", force=True)
                if(procMan.palive("segment_HQ")): #force-stop the segmenter
                    procMan.pstop(name="segment_HQ", force=True)
                if(procMan.palive("segment_LQ")): #force-stop the segmenter
                    procMan.pstop(name="segment_LQ", force=True)
            dbg.prn(dbg.SRM,"stopped")
            # Kill RECORD ffmpeg
            dbg.log(dbg.SRM,"------- stopping mp4 recorder")
            procMan.pstop(name='record_HQ',force=force)
            procMan.pstop(name='record_LQ',force=force)
            timeStart = time.time()
            count = 0
            while((procMan.pexists("record_HQ") or procMan.pexists("record_LQ")) and not (enc.code & enc.STAT_SHUTDOWN) and (time.time()-timeStart)<timeout):
                dbg.log(dbg.SRM,"------- mp4 record stopping...{}".format(count))
                count += 1
                time.sleep(1)
            if((time.time()-timeStart)>=timeout):#timeout reached
                procMan.pstop(name='record_HQ', force=True)
                procMan.pstop(name='record_LQ', force=True)
            dbg.log(dbg.SRM,"------- mp4 record stopped")

            # STOP ALL of LIVE555 (for good measure)
            os.system("killall -9 live555 >/dev/null 2>/dev/null")
            # stop the ffmpeg that was capturing video and pushing it to the XFB
            procMan.pstop(name="xfcap_LQ")
            procMan.pstop(name="xfcap_HQ")
            # stop the lost-signal filler
            procMan.pstop(name="loss_filler")
            # stop the xfb itself
            procMan.pstop(name="xfbin_LQ")
            procMan.pstop(name="xfbin_HQ")

            dbg.log(dbg.SRM, "EVENT_STOPS ENDS =========================================>")                    
        except Exception as e:
            dbg.prn(dbg.SRM|dbg.ERR,"[---]encCapStop: ",e,sys.exc_info()[-1].tb_lineno)
        dbg.prn(dbg.SRM,"stopping DONE! current status:",enc.code)
        if(enc.code & enc.STAT_STOP):
            enc.statusSet(enc.STAT_READY)

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
            dbg.prn(dbg.SRM|dbg.ERR, "[---]sources.exists:",e,sys.exc_info()[-1].tb_lineno)
        return -1
    #end exists

    def vqexists(self, srcs, ip, vq):
        """ Check if a device with this IP exists already
            Args:
                ip (str) :   ip address of the device to lookup
                vq (str) :   video quality either "HQ" or "LQ"
            Returns:
                (int): if the search is successful, return index of the device in the array, if the device is not found return -1
        """
        try:
            #sources = copy.deepcopy(self.sources)
            idx = 0
            for src in srcs:
                if(ip==src.device.ip and vq==src.device.vidquality):
                    return idx
                idx +=1
        except Exception as e:
            dbg.prn(dbg.SRM|dbg.ERR, "[---]vqexists:",e,sys.exc_info()[-1].tb_lineno)
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
                        dbg.prn(dbg.SRM, "could not init device or IP sources are not allowed - stop monitor:{}.{}".format(self.sources[idx].device.ip, self.sources[idx].device.vidquality))
                        # src.stopMonitor()
                        self.sources[idx].stopMonitor()
                        postfix = "HQ"
                        if (self.sources[idx].device.vidquality == 'HQ'):
                            postfix = "HQ"
                        else:
                            postfix = "LQ"     
                        devIP = src.device.ip + postfix
                        dbg.prn(dbg.SRM, "deleting...", self.sources)
                        del self.sources[idx]
                        dbg.prn(dbg.SRM, "deleted ", self.sources)
                        if(not(enc.code & (enc.STAT_LIVE|enc.STAT_PAUSED|enc.STAT_STOP))):
                            procMan.pstop(devID=devIP+postfix) #stop all the processes associated with this device
                    # end if not busy
                else:
                    idx+=1
                    isCamera = isCamera or src.device.isCamera
                #end if not inited...else
            #end for src in sources

            # rec_stat check after starting event: retry until it get proper data
            if ((enc.code & enc.STAT_LIVE) and not self.evt_stat and not self.rec_stat_worker):
                self.rec_stat_worker = pxphelper.PXPHeler('rec_stat', 'c-eventstart', '{"sidx":"*","event":"live","srclen":' + str(self.total_feeds) + '}') # cmd,cookie,param
                self.rec_stat_worker.start()
            else:
                if ((enc.code & enc.STAT_LIVE) and self.rec_stat_worker and self.rec_stat_worker.done):
                    self.evt_stat = self.rec_stat_worker.rec_stat
                    if (self.evt_stat['success']):
                        self.rec_stat_worker = False # done, no more try...
                        dbg.prn(dbg.ERR|dbg.SRM, "REC_STAT-->{}".format(self.evt_stat))
                    else:
                        self.rec_stat_worker = False # for retrying purpose
                        self.evt_stat = False
                        dbg.prn(dbg.ERR|dbg.SRM, "retrying...REC_STAT-->{}".format(self.evt_stat))

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
            dbg.prn(dbg.ERR|dbg.SRM, "[---]srcmgr.monitor:",e, sys.exc_info()[-1].tb_lineno)

    def nextIdx(self,srcs):
        """ Finds next available camera index """
        if(len(srcs)<1): #there are no sources yet - first index will be zero
            return 0 
        # get indecies of all sources
        indecies = []
        for src in srcs:
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

    def setVideoInputType(self, vit=0, camID=-1):
        try:
            sources = copy.deepcopy(self.sources)
            for src in sources:
                if(src.device.ccBitrate and (src.id==camID or int(camID)<0)): #this device allows changing bitrate, found the right camera or setting bitrate for all the cameras
                    src.device.setVideoInputType(int(vit))
                    if (src.device.model.upper().find("AXIS")>=0):
                        if(enc.code & enc.STAT_READY): 
                            src.stopRTSP() # cannot set bitrate if event is started because this needs to restart the live555, ffmpeg 
        except Exception as e:
            dbg.prn(dbg.ERR|dbg.SRM, "[---]mgr.setVIT",e,sys.exc_info()[-1].tb_lineno)

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
            for src in sources:
                if(src.device.ccBitrate and (src.id==camID or int(camID)<0)): #this device allows changing bitrate, found the right camera or setting bitrate for all the cameras
                    src.device.setBitrate(int(bitrate))
                    if (src.device.model.upper().find("AXIS")>=0):
                        if(enc.code & enc.STAT_READY): 
                            src.stopRTSP() # cannot set bitrate if event is started because this needs to restart the live555, ffmpeg 
        except Exception as e:
            dbg.prn(dbg.ERR|dbg.SRM, "[---]mgr.setBitrate",e,sys.exc_info()[-1].tb_lineno)

    def toJSON(self):
        # Creates a dictionary of all the sources and returns it
        # Args:
        #     autosave(bool,optional): saves the dictionary in json format to a pre-defined file.default:True
        # Return:
        #     (dictionary): indecies are camera IPs.
        try:
            sources = copy.deepcopy(self.sources)
            if (pu.mdbg.checkscf(sockCmd, pu.SCF_SHOWBONJ)):
                dbg.log(dbg.SRM,"feed list length-->{}".format(len(sources)))
                
            feedIdx = -1
            ip_vq = {}
            for idx in xrange(len(sources)):
                src = sources[idx]
                vip = src.device.ip
                vidq = src.device.vidquality
#               if (not src.device.isCamera or not src.device.isOn):
#                   continue                
                if (vip in ip_vq): # found
                    if ('HQ' in ip_vq[vip] and 'LQ' in ip_vq[vip]):
                        continue
                    else:
                        if ('HQ' in ip_vq[vip]):
                            ip_vq[vip][vidq] = ip_vq[vip]['HQ']
                        elif ('LQ' in ip_vq[vip]):
                            ip_vq[vip][vidq] = ip_vq[vip]['LQ']
                else:
                    feedIdx += 1
                    ip_vq[vip] = {}
                    ip_vq[vip][vidq] = str(feedIdx)

            validDevs = {}
            for src in sources:
                vip = src.device.ip
                vidq = src.device.vidquality
                validDevs[vip+"-"+vidq] = {
                    "url"           :   src.rtspURL,
                    "resolution"    :   src.device.resolution,
                    "bitrate"       :   src.device.bitrate,
                    "ccBitrate"     :   src.device.ccBitrate,
                    "framerate"     :   src.device.framerate,
                    "deviceURL"     :   src.device.rtspURL,
                    "type"          :   src.type,
                    "cameraPresent" :   src.device.isCamera,
                    "on"            :   src.device.isOn,
                    "vid-quality"   :   src.device.vidquality,
                    "mac"           :   src.device.mac,
                    "ip"            :   src.device.ip,
                    "sidx"          :   ""
                }
                if (vip in ip_vq and vidq in ip_vq[vip]):
                    validDevs[vip+"-"+vidq]["sidx"] = ip_vq[vip][vidq].zfill(2)
                if (pu.pxpconfig.support_cam('dt')):
                    vit_str = ["CVBS/SDI Auto Detect", "CVBS", "SDI", "DVI", "Test Pattern"]
                    validDevs[vip+"-"+vidq]['vit'] = src.device.vit # delta video input type
            if (pu.mdbg.checkscf(sockCmd, pu.SCF_SHOWBONJ)):
                pu.mdbg.log("CML-JSON-->{}".format(validDevs))
                pu.mdbg.log("CML-IP_VQ-->{}".format(ip_vq))
                pu.mdbg.log("CML-CAMIP_VQ->{}".format(self.camip_vq))
            return validDevs
        except Exception as e:
            dbg.prn(dbg.ERR|dbg.SRM, "[---]srcmgr.toJSON", e, sys.exc_info()[-1].tb_lineno)
        return {}

##########################
## network sync classes ##
##########################

    def getFeedCount(self, evt='live'):
        if (evt=='live' and (enc.code & enc.STAT_LIVE) or (enc.code & enc.STAT_START) or (enc.code & enc.STAT_PAUSED)):
            return len(self.sources)
        else:
            fc = glob.glob(c.wwwroot+evt+"/video/list_*.m3u8")
            if (fc):
                return len(fc)
        return 0
    
    def IsPostProcDone(self):
        if (self.checkStatDone):
            return 1
        return 0

    def checkStat(self, evt_path):
        """
            old way: Convert all of recorded fragmented mp4 files to non-fragmented mp4 files (obsolete)
            new way: Align the mp4 files to start at the same time
        """
        sources = copy.deepcopy(self.sources)
        offset = 0
        minv = 0
        maxv = 0
        postprocess = False
        
        pu.mdbg.log("check status for mp4")
        try:
            
            for idx in xrange(len(sources)):
                if(idx>=len(sources)):
                    break
                src = sources[idx]
                pu.mdbg.log("src--> idx:{} ip:{} vq:{} model:{} on:{} cam:{}".format(src.idx, src.device.ip, src.device.vidquality, src.device.model, src.device.isOn, src.device.isCamera))
                if(not(src.device.isCamera and src.device.isOn)): # skip devices that do not have a video stream available
                    continue    

                if (src.device.model.find("Monarch")>=0):
                    evtpath = c.wwwroot + evt_path + "/video"
                    src.device.collect_mp4(evtpath)
                    src.device.postproc(src.idx, src.device.vidquality, evtpath)
            
            if (self.evt_stat):
                minv = self.evt_stat['ctime-00hq']
                maxv = self.evt_stat['ctime-00hq']
                for idx in xrange(len(sources)):
                    src = sources[idx]
                    sidx = src.idx/2
                    vq = src.device.vidquality.lower()
                    timekey = 'ctime-' + str(sidx).zfill(2) + vq
                    if (timekey in self.evt_stat and self.evt_stat[timekey]):
                        if (minv>self.evt_stat[timekey]):
                            minv = self.evt_stat[timekey]
                        if (maxv<self.evt_stat[timekey]):
                            maxv = self.evt_stat[timekey]
                if (maxv>minv):
                    offset = maxv - minv
                else:
                    offset = 0
                dbg.log(dbg.SRM, "check offset-->minv:{}  maxv:{}  offset:{}".format(minv, maxv, offset))            
                
                if (pu.pxpconfig.enable_mp4_convert()):
                    for idx in xrange(len(sources)):
                        src = sources[idx]
                        if(not(src.device.isCamera and src.device.isOn)): # skip devices that do not have a video stream available
                            continue    
                        sidx = src.idx/2
                        vq = src.device.vidquality.lower()
                        if (not pu.pxpconfig.virtual_lq_enabled() and vq=='lq'):
                            continue
                        if (self.evt_stat):
                            timekey = 'ctime-' + str(sidx).zfill(2) + vq
                            offset = maxv - self.evt_stat[timekey]
                        else:
                            offset = 0
                        if (not pu.pxpconfig.use_mp4align()): # use offset if mp4align is set...
                            offset = 0
                        else: 
                            if (offset>0):
                                if (pu.pxpconfig.use_split_event_folder()):
                                    postprocess = self.dosplit(offset, sidx, vq, evt_path, vq + "_" + str(sidx).zfill(2))
                                else:
                                    postprocess = self.dosplit(offset, sidx, vq, evt_path, False)
                else:
                    pu.mdbg.log("check status disabled")
                    self.checkStatDone = True    
                    return
                
                if (postprocess):
                    video_path = c.wwwroot + evt_path + "/video/"  
                    for cam_no in xrange(len(sources)):
                        camsid = str(cam_no).zfill(2)
                        vq = ['hq', 'lq']
                        for j in xrange(2):
                            if (not pu.pxpconfig.virtual_lq_enabled() and vq[j] == 'lq'):
                                continue
                            if (pu.pxpconfig.use_split_event_folder()):
                                mp4_path = video_path + vq[j] + "_" + camsid + "/main_" + camsid + vq[j] +".mp4"
                            else:
                                mp4_path = video_path + "main_" + camsid + vq[j] +".mp4"
                            cmd_path = video_path + "main_" + camsid + vq[j] +".mp4" + ".cmd"
                            if (os.path.exists(cmd_path)):
                                cmd = pu.disk.file_get_contents(cmd_path)
                                if (cmd):
                                    #os.system(cmd)
                                    pu.ffmpeg.split(c.wwwroot + evt_path + "/video/main_" + camsid + vq[j] + c.mp4progress_ext, cmd) # .mp4.progress
                                    pu.mdbg.log("validating mp4 file...{}".format(cmd))            
                                    if (os.path.exists(c.wwwroot + evt_path + "/video/tmp_main_" + camsid + vq[j] + ".mp4")):
                                        cmd = 'mv ' + c.wwwroot + evt_path + "/video/tmp_main_" + camsid + vq[j] + ".mp4 " + mp4_path
                                        pu.mdbg.log("Renaming file...{}".format(cmd))
                                        os.system(cmd)
                                else:
                                    pu.mdbg.log("check: cannot convert...cmd:{}".format(cmd))
            self.checkStatDone = True    
            dbg.log(dbg.SRM, "check stat done ... mp4")            
        except Exception as e:
            pu.mdbg.log("[---] showStat: line:{} err:{}".format(sys.exc_info()[-1].tb_lineno, e))
            self.checkStatDone = True    
    
    def dosplit(self, start_secs, cam_no, vq, evt_path=False, split_path=False):
        """
            Count ts files to get mp4 duration and assemble ffmpeg command line for conversion (fMP4 to MP4 via splitting)  
        """
        try:
            mp4path = c.wwwroot + evt_path + "/video/"
            if (pu.pxpconfig.use_split_event_folder()):
                secs = pu.disk.get_dur(cam_no, vq.lower(), c.wwwroot + evt_path + "/video/" + split_path + "/") # based on ts file count
            else:
                secs = pu.disk.get_dur(cam_no, vq.lower(), mp4path) # based on ts file count
                
            if (start_secs>0):
                secs = secs - start_secs
                if (secs<0):
                    secs = 0 
                       
            if (secs>0 and start_secs>0):
                hh = secs/3600
                mm = (secs%3600)/60
                ss = (secs%3600)%60
                split_time = str(hh).zfill(2) + ":" + str(mm).zfill(2) + ":" + str(ss).zfill(2)
    
                hh = start_secs/3600
                mm = (start_secs%3600)/60
                ss = (start_secs%3600)%60
                start_time = str(hh).zfill(2) + ":" + str(mm).zfill(2) + ":" + str(ss).zfill(2)
    
                mp4file = "main_" + str(cam_no).zfill(2) + vq.lower() + ".mp4"
                stat_list = mp4file + " -> duration(in seconds):" + str(secs) + " ;  start_offset(in seconds):" + str(start_secs)
                filepath =  mp4file + c.mp4info_ext
                if (not mp4path):
                    mp4path = "."
                filepath = mp4path + mp4file + c.mp4info_ext
                pu.disk.file_set_contents(filepath, stat_list) # main_00hq.mp4.info.txt
                
                if (start_secs>0):
                    # ffmpeg -ss 00:00:10 -i input.mp4 -t 00:20:24 -c copy -y cut.mp4
                    cmd = "/usr/bin/ffmpeg -ss " + start_time + " -i "+ mp4path + mp4file + " -t " + split_time + " -c copy " + mp4path + "tmp_" + mp4file
                else:
                    cmd = "/usr/bin/ffmpeg -i " + mp4path + "/" + mp4file + " -t " + split_time + " -c copy " + mp4path + "tmp_" + mp4file
                pu.disk.file_set_contents(mp4path + mp4file + ".cmd", cmd)
                return True
            return False
        except Exception as e:
            pu.mdbg.log("[---] dosplit: line:{} err:{}".format(sys.exc_info()[-1].tb_lineno, e))
            return False

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
            dbg.prn(dbg.ERR|dbg.SSV,"[---]syncsrv.init:", e, sys.exc_info()[-1].tb_lineno)
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
            dbg.prn(dbg.ERR|dbg.SSV,"[---]syncsrv.syncUp:", e, sys.exc_info()[-1].tb_lineno, 'ip:',self.ip)
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
            dbg.prn(dbg.ERR|dbg.SSV,"[---]syncsrv.init:", e, sys.exc_info()[-1].tb_lineno)

class SyncManager(object):
    """ Manages networked servers: finds pxp servers, checks their options, syncs the events between them """
    servers = {} #dictionary of syncable servers
    enabledUp = False #this is irrelevant for current server, it will pull new info from other servers, not push anything
    enabledDn = False
    isMaster = False
    oldstatus = False
    msg_count = 10
    def __init__(self):
        super(SyncManager, self).__init__()
        # start discovering as soon as the system is up
        if(not 'srvsync' in tmr):
            tmr['srvsync'] = {}
        tmr['srvsync']['mgr'] = TimedThread(self.discover,period=10)
        tmr['srvsync']['snc'] = TimedThread(self.syncAll,period=30)
        tmr['srvsync']['mon'] = TimedThread(self.monitor,period=5)
        self.startTime = time.time()
        self.msg_count = self.get_max_msg_count()

    def get_max_msg_count(self):
        return 10
    def arbitrate(self):
        """ Based on all discovered devices makes a decision on whether this server will be master or not """
        try:
            global sockCmd
            if(enc.code & (enc.STAT_START | enc.STAT_LIVE | enc.STAT_PAUSED)): 
                # there is a live event on this encoder - it must be master already
                # even if it's not, that means another master already has a live event as well - cannot re-arbitrate during live event
                return
            dbg.prn(dbg.SMG,"arbitrating")
            servers = self.servers.keys() #list of remote servers
            masterPresent = False
            highestIP = pu.io.myIP() #start from itself assuming it's highest IP
            appg.updateMainIP(highestIP)
            for srvIP in servers: #go through each server and check if it's a master
                masterPresent = masterPresent or ((srvIP in self.servers) and self.servers[srvIP].master)
                highestIP = max(highestIP, srvIP)
            #local device will be a master if there are no other masters on the network, 
            # and local device has highest string-value-IP of all other servers OR it was elected as a master previously
            self.isMaster = (not masterPresent) and ((highestIP in pu.io.myIP(allDevs = True)) or self.isMaster)
            master = 'master' if self.isMaster else 'not master'
            if (self.oldstatus != master):
                speak("server is now " + master)
            self.oldstatus = master
            if (sockCmd&pu.SCF_HIDEMASTER==0 or self.msg_count>0):
                if (self.isMaster):
                    dbg.log(dbg.SMG,'found:',highestIP,' the local is', master)
                else:
                    dbg.log(dbg.SMG,'found:',servers,'(LEN:', (len(servers)), ') the local is', master)
                self.msg_count -= 1
                if (self.msg_count<0):
                    self.msg_count = 0
            if(enc.code & enc.STAT_INIT):
                enc.statusSet(enc.STAT_READY,overwrite=False)
        except Exception as e:
            dbg.prn(dbg.SMG|dbg.ERR, "[---]syncmgr.arbitrate:", e, sys.exc_info()[-1].tb_lineno)

    def compareVersion(self,ver1,ver2="1.1.8"):
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
            global sockCmd
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
                self.msg_count = self.get_max_msg_count()
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
                    #xs = "found "+re.sub('[\.]','.dot.',str(result['ip'][result['ip'].rfind('.')+1:]))+", total "+str(len(self.servers)+1)+" servers, derka derka."
                    xs = "found " + str(len(self.servers)) + " PXP servers"
                    speak(xs)
                    if (pu.mdbg.checkscf(sockCmd, pu.SCF_SHOWBONJ)):
                        dbg.prn(dbg.PCM, "-->SYNCMAN:", result)
                else:
                    dbg.prn(dbg.SMG,"server not added (wrong customer):",result['ip'])
            except Exception as e:
                # most likely could not process response - that was an old server
                dbg.prn(dbg.ERR|dbg.SMG, "[---]syncmgr.discovered:", e, sys.exc_info()[-1].tb_lineno, "response:",srvResponse)
            self.discoveredRunning = False
        #end discovered

        pu.bonjour.discover(regtype="_pxp._udp", callback=discovered)
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
            dbg.prn(dbg.ERR|dbg.SMG,"[---]syncmgr.monitor",e,sys.exc_info()[-1].tb_lineno)
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
            dbg.prn(dbg.ERR|dbg.SMG, "[---]syncmgr.syncAll:", e, sys.exc_info()[-1].tb_lineno)

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
    return {"master":syncMgr.isMaster,"alarms":srcMgr.alarms(),"postproc":srcMgr.checkStatDone}

def speak(msg):
    """ speaks passed text (only on 192.168.3.100 ip address)"""
    if(pu.io.myIP()=='192.168.2.143'):
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
        if (pxpmisc.tmr_misc and len(pxpmisc.tmr_misc)>0):
            #mp4builder.cleanup()
            pxpTTKiller(pxpmisc.tmr_misc,"misc_tmr")
        # make sure live555 isn't running
        os.system("killall -9 live555 2>/dev/null &")
        dbg.prn(dbg.KLL,"procMan cleanup... ")
        try:
            if(procMan):
                procMan.pstop(name="livefeed_HQ", async=False)
                procMan.pstop(name="livefeed_LQ", async=False)
                del procMan
        except:
            pass
        dbg.prn(dbg.KLL,"terminated!")
    except Exception as e:
        dbg.prn(dbg.KLL|dbg.ERR,"[---]pxpCleanup FAIL?!!!!?!?!", e, sys.exc_info()[-1].tb_lineno)
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
                dbg.prn(dbg.ERR|dbg.BBQ,'[---]bbqManager',e,sys.exc_info()[-1].tb_lineno)
        #for client in globalBBQ
    except Exception as e:
        dbg.prn(dbg.ERR|dbg.BBQ,'[---]bbqManager',e,sys.exc_info()[-1].tb_lineno)
#end bbqManage

class proc:
    """ Processor class - manages a specified process (starts, restarts, stops) """
    def __init__(self, cmd, name, devID, keepAlive=False, killIdle=False, forceKill=False, threshold=0, modelname=False, srcidx=-1):
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
        self.threads['manager'] = TimedThread(self._manager, period=10)
        self.threshold = threshold
        self.startIdle = 0 #time when process became idle
        self.model = modelname
        self.srcidx = srcidx
        self.myproc = False
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
            #if(self.name=='capturez'):#display output in the terminal #DEBUG ONLY#
            if(self.name=='capturez_HQ' or self.name=='capturez_LQ'):#display output in the terminal #DEBUG ONLY#
                ps = sb.Popen(self.cmd.split(' '))
            else:#hide output for all other ffmpeg's/processes
                ps = sb.Popen(self.cmd.split(' '), stderr=FNULL, stdout=FNULL)
                
            self.myproc = ps    
                
            # get its pid
            self.pid=ps.pid
            #dbg.prn(dbg.PPC,"proc starting: ", self.name, self.pid, self.cmd, "force:", self.forcekill)
            # get the reference to the object (for communicating/killing it later)
            self.ref=ps
            #set these 2 variables to make sure it doesn't get killed by the next manager run
            self.threads[ps.pid]=TimedThread(self._monitor,period=1.5)
            self.alive=True
            self.cpu=100
            self.run = True
            import inspect
            dbg.prn(dbg.PPC, "proc.start ===========> from:{} name:{} dev:{} alive:{} pid:{}".format(inspect.stack()[1][3], self.name, self.dev, self.alive, self.pid))
#             if(self.name=='capture_HQ' or self.name=='capture_LQ'):
#                 pass
            return True
        except Exception as e:
            dbg.prn(dbg.ERR|dbg.PPC,"[---]proc.start:{} {} cmd:{} ".format(e, sys.exc_info()[-1].tb_lineno, self.cmd))
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
        dbg.prn(dbg.PPC, "proc stopping: ", self.name, self.pid, self.cmd, "force:", (force or self.forcekill))
        import inspect
        dbg.prn(dbg.PPC, "proc.stop ===========> from:{}  name:{}  pid:{}  cmd:{}".format(inspect.stack()[1][3], self.name, self.pid, self.cmd))
        self.off = end
        self.run = False
        try:
#             dbg.prn(dbg.PPC|dbg.DBG,"2========>",self.name)
#             if (self.name.startswith("rec")):
#                 s = 'q'
#                 dbg.prn(dbg.PPC|dbg.DBG,"2========> send q:")
#                 self.myproc.communicate(s.encode('ascii'))
#                 
#                 dbg.prn(dbg.PPC|dbg.DBG,"2========> send q:")
#                 self.myproc.communicate(s.encode('ascii'))
#                 time.sleep(1)
                            
            if(self.off):
                self.threads['manager'].kill()

#           if(self.name=='capture_HQ' or self.name=='capture_LQ'):
#               pass
                
        except Exception as e:
            dbg.prn(dbg.PPC|dbg.ERR, "[---]proc.stop:",e,sys.exc_info()[-1].tb_lineno)
        if(force):
            self.forcekill = True
        if(async):
            TimedThread(self._killer)
        else:
            self._killer()
    def restart(self):
        """ Stops the process and immediately restarts it """
#         if(self.name=='capture_HQ' or self.name=='capture_LQ'):
#             dbg.prn(dbg.PPC,"RESTART CAPTURE =======================> proc._monitor:name:{} dev:{} alive:{} pid:{}".format(self.name, self.dev, self.alive, self.pid))
        dbg.prn(dbg.PPC,"proc.restart: name:{} dev:{} alive:{} pid:{}".format(self.name, self.dev, self.alive, self.pid))
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
            if (not self.alive):
                dbg.prn(dbg.PPC,"proc._monitor: dead proc:{} name:{}".format(self.pid, self.name))
            self.cpu = pu.disk.getCPU(pid=self.pid) #get cpu usage
            #if(self.name=='capture_HQ' or self.name=='capture_LQ'):
            #    dbg.prn(dbg.PPC,"CAPTURE =======================> proc._monitor:name:{} dev:{} alive:{} pid:{}".format(self.name, self.dev, self.alive, self.pid))
            if(self.cpu>=0.1):
                self.startIdle = 0 #reset idle timer if the process becomes active
            if((self.cpu<0.1) and (self.threshold>0) and ((not self.startIdle) or (time.time()-self.startIdle)<self.threshold)): #cpu is idle and user set a threshold - need to wait before declaring process as idle
                #process has recently become idle
                self.cpu = 1 #fake the cpu usage for an idle process until threshold is reached
                if(not self.startIdle):
                    self.startIdle = time.time()
            # self.cpu=2
        except Exception as e:
            dbg.prn(dbg.PPC|dbg.ERR,"[---]proc._monitor: ",e,sys.exc_info()[-1].tb_lineno)
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
            import inspect
            dbg.prn(dbg.PPC, "proc._killer ===========> from:", inspect.stack()[1][3], "  name:", self.name, " pid:", self.pid)
            while psOnID(pid=self.pid):
                if(self.killcount>2): #the process didn't die after 3 attempts - force kill next time
                    self.forcekill = True
                self.killcount += 1
                
#                 dbg.prn(dbg.PPC|dbg.DBG,"========>",self.name)
#                 if (self.name.startswith("record")):
#                     s = 'q'
#                     self.myproc.communicate(s.encode('ascii'))
#                     dbg.prn(dbg.PPC|dbg.DBG,"========> send q:")
#                     
#                     self.myproc.communicate(s.encode('ascii'))
#                     dbg.prn(dbg.PPC|dbg.DBG,"========> send q:")

#                     time.sleep(3)
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
#             if(self.name=='capture_HQ' or self.name=='capture_LQ'):
#                 dbg.prn(dbg.PPC,"KILL CAPTURE =======================> proc._monitor:name:{} dev:{} alive:{} pid:{}".format(self.name, self.dev, self.alive, self.pid))
            return True
        except Exception as e:
            import sys
            if(sys and sys.exc_traceback and sys.exc_info()[-1].tb_lineno):
                errline = sys.exc_info()[-1].tb_lineno
            else:
                errline = ""
            dbg.prn(dbg.PPC|dbg.ERR,"[---]proc._killer: ",e,errline)
#end class proc

class procmgr:
    """ Process management class """
    def __init__(self):
        self.procs = {} #processes in the system
    def dbgprint(self):
        #return
        global sockCmd
        procs = self.procs.copy()
        live555Count = 0
        segmentCount = 0
        captureCount = 0
        recordsCount = 0
        live555proc = False
        if(len(procs)>0 and (sockCmd&pu.SCF_HIDECMD==0)):
            dbg.prn(dbg.PCM,"--------------------------------------------------------------------")
            for idx in procs:
                cmd = procs[idx].cmd
                if (procs[idx].name.find('livefeed')>=0):
                    live555Count += 1
                    live555proc = True
                if (procs[idx].name.find('segment')>=0):
                    segmentCount += 1
                    if (live555proc):
                        dbg.prn(dbg.PCM,"---------------------------------")
                        live555proc = False
                if (procs[idx].name.find('capture')>=0):
                    captureCount += 1
                if (procs[idx].name.find('record')>=0):
                    recordsCount += 1
                                    
                i = cmd.find("-rtsp_transport")
                if (i>0):
                    i = cmd.find("-fflags", i)
                    while(i>0):
                        cmd = cmd[:i] + "\n\t" + cmd[i:]
                        i = cmd.find("-fflags", i+3)
                else:
                    i = cmd.find("-fflags")
                    while(i>0):
                        cmd = cmd[:i] + "\n\t" + cmd[i:]
                        i = cmd.find("-fflags", i+3)
                    i = cmd.find("-map")    
                    while(i>0):
                        cmd = cmd[:i] + "\n\t" + cmd[i:]
                        i = cmd.find("-map", i+3)    
                    i = cmd.find("-r")    
                    while(i>0):
                        cmd = cmd[:i] + "\n\t" + cmd[i:]
                        i = cmd.find("-r", i+3)                                                  
                if (sockCmd&pu.SCF_SHOWDETAILEDCMD>0):
                    dbg.prn(dbg.PCM, "\""+cmd+"\"", procs[idx].name, procs[idx].alive, procs[idx].cpu, procs[idx].pid, procs[idx].keepalive, procs[idx].run, procs[idx].dev, procs[idx].model)
                else:
                    #dbg.prn(dbg.PCM, "\""+cmd+"\"", procs[idx].name, procs[idx].alive, procs[idx].cpu, procs[idx].pid, procs[idx].keepalive, procs[idx].run, procs[idx].dev)
                    dbg.prn(dbg.PCM, procs[idx].name, procs[idx].alive, procs[idx].cpu, procs[idx].pid, procs[idx].keepalive, procs[idx].run, procs[idx].dev, procs[idx].model)
            appg.updateCaptureCount(captureCount)
            appg.updateFeedCount(live555Count)
            appg.updateSegmentCount(segmentCount)
            appg.updateRecorderCount(recordsCount)
            if (appg.IsVideoStartSuccessfully()):
                dbg.prn(dbg.PCM,"OK ----- LIVEFEED:{0} CAPTURE:{1} SEGMENTER:{2} RECORD:{3}".format(live555Count, captureCount, segmentCount, recordsCount))
                if(enc.code&enc.STAT_LIVE):
                    if (appg.IsEventStartSuccessfully()):
                        dbg.prn(dbg.PCM,"----- Event recording successfully in progress")
                    else:
                        dbg.prn(dbg.PCM,"CHECK ----- Event recording CAP:{0} SEG:{1} REC:{2} in progress".format(appg.launchedCaptureLen, appg.launchedSegmentLen, appg.launchedRecorderLen))
            else:
                dbg.prn(dbg.PCM,"CHECK ----- LIVEFEED:{0} CAPTURE:{1} SEGMENTER:{2} RECORD:{3} SRC:{4}".format(live555Count, captureCount, segmentCount, recordsCount, appg.srcLen))
    
    def retryCamFeed(self, srcidx=-1):
        if (srcidx < 0):
            return False
        dbg.prn(dbg.PCM, "procmgr: feed stopped to retrying...srcidx:{}".format(srcidx))
        procs = self.procs.copy()
        for idx in procs:
            proc = procs[idx]
            if(proc.srcidx==srcidx and proc.srcidx>=0):
                dbg.prn(dbg.PCM, "procmgr: feed stopped to retry -------------->srcidx:{} pid:{} name:{} model:{}".format(proc.srcidx, proc.pid, proc.name, proc.model))
                self.pstop(proc.name, proc.dev)
        return True
    def palive(self,name, devID=False):
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
    def padd(self,cmd,name,devID,keepAlive=False,killIdle=False,forceKill=False,threshold=0,modelname=False,srcidx=-1):
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
        import inspect
        try:
            idx = 0 #the index of the new process
            procs = self.procs.copy()
            #find the next available index
            for pidx in procs:
                if(pidx>=idx):
                    idx = pidx+1
            self.procs[idx] = proc(cmd, name, devID, keepAlive, killIdle, forceKill, threshold, modelname, srcidx)
            # start the process as soon as it's added
            if(self.procs[idx].start()):
                dbg.prn(dbg.PCM, " pcm.proc.added via:{}::::::::::idx:{} pid:{} name:{} model:{} srcidx:{}".format(inspect.stack()[1][3], idx, self.procs[idx].pid, self.procs[idx].name, self.procs[idx].model, srcidx))
                return True
            #could not start stream - no need to add it to the list
            del self.procs[idx]
            return False
        except Exception as e:
            dbg.prn(dbg.PCM|dbg.ERR, "[---]pcm.padd:", e)
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
    def psend_sigint(self, name=False, devID=False, force=False, remove=True, async=True):
        try:
            import inspect
            if(not (name or devID)): #can't stop a process when neither name nor devID were specified
                return
            dbg.prn(dbg.PCM, "killer hierarchy: sig_int", inspect.stack()[1][3])
            procs = self.procs.copy()
            for idx in procs:
                proc = procs[idx]
                if(((not name) or (proc.name==name)) and ((not devID) or (proc.dev==devID))):
                    dbg.prn(dbg.PCM, "=======> sig_int send to ", proc.name)
                    os.kill(proc.pid, signal.SIGINT)
                    if(remove): #only delete the process from the list if user specifically requested it
                        if(not 'killers' in tmr):
                            tmr['killers'] = []
                        tmr['killers'].append(TimedThread(self._stopwait,(idx,)))
        except Exception as e:
            dbg.prn(dbg.PCM, "[---] psend_sigint:", e)
            pass        
                    
    def pkill(self, name=False, devID=False):
        import inspect
        if(not (name or devID)): #can't stop a process when neither name nor devID were specified
            return
        dbg.prn(dbg.PCM, "killer hierarchy:", inspect.stack()[1][3])
        procs = self.procs.copy()
        for idx in procs:
            proc = procs[idx]
            if(((not name) or (proc.name==name)) and ((not devID) or (proc.dev==devID))):
                pass
            #end if name or devID
        
    def pstop(self, name=False, devID=False, force=False, remove=True, async=True, restart=False):        
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
#         if (name.startswith("record")):
#             self.psend_sigint(name=name, devID=devID, force=force, remove=remove, async=async)
#             return
        try:
            dbg.prn(dbg.PCM, "killer hierarchy:", inspect.stack()[1][3], "  name:", name, "devid:", devID, "restart:", restart, " remove:", remove, " force:", force)
            procs = self.procs.copy()
            for idx in procs:
                proc = procs[idx]
                if(((not name) or (proc.name==name)) and ((not devID) or (proc.dev==devID))):
                    dbg.prn(dbg.PCM, "pcm.pstop:", inspect.stack()[1][3], "  name:", name, "pid", proc.pid, "devid:", devID)
                    if(restart):
                        proc.restart() #this operation is synchronous
                    else:#just stop the process
                        proc.stop(async=async, force=force, end=remove) #if removing the process, do not allow it to  be restarted
                        if(remove): #only delete the process from the list if user specifically requested it
                            if(not 'killers' in tmr):
                                tmr['killers'] = []
                            tmr['killers'].append(TimedThread(self._stopwait,(idx,)))
                    #end if restart...else
                #end if name or devID
        except Exception as e:
            dbg.prn(dbg.ERR|dbg.PCM, "[---] pcm.pstop {}". format(e))
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
                cmd = "kill -15 "+str(pid)
                os.system(cmd)
                dbg.prn(dbg.PCM, "cmd:", cmd);
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
        dbg.prn(dbg.PCM|dbg.ERR,"kill err::::::::::::::::::",e,sys.exc_info()[-1].tb_lineno)

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
    global globalBBQ, sockCmd
    # get timestamp for every broadcast
    timestamp = int(time.time()*1000)
    # add him to the BBQ if he's not there already
    if(c and not client in globalBBQ):
        globalBBQ[client] = [{},c,True]
    # send the data to the client - do this in the BBQ manager
    # globalBBQ[client][1].sendLine(str(timestamp)+"|"+msg)
    # add the data to the BBQ for this client
    bbqmsg = str(timestamp)+"|"+msg
    globalBBQ[client][0][timestamp]={'ACK':0,'timesSent':0,'lastSent':(timestamp-3000),'data':bbqmsg}
    if (sockCmd&pu.SCF_SHOWBBQ>0):
        dbg.prn(dbg.MN,"--->BBQ SENT: ", bbqmsg)
    
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
        global sockCmd
        # client IP address
        senderIP = str(addr[0])
        # client port
        senderPT = str(addr[1])
        if (sockCmd&pu.SCF_SHOWSOCKCMD>0):
            dbg.prn(dbg.PCM,"............... BBQ GOT: ",data,' FROM ',senderIP,':',senderPT)
        #if it was a command, it'll be split into segments by vertical bars
        dataParts = data.split('|')
        # if(senderIP!="127.0.0.1"):
            # dbgLog("got data: "+data+" from: "+senderIP)
        if(len(dataParts)>0):
            # this is a service request
            if(senderIP=="127.0.0.1"):
                nobroadcast = False #local server allows broadcasting
                # these actions can only be sent from the local server - do not broadcast these
                if(dataParts[0]=='RMF' or dataParts[0]=='RMD' or dataParts[0]=='VIT' or dataParts[0]=='BTR' or dataParts[0]=='BKP' or dataParts[0]=='RRE' or dataParts[0]=='LVL' or dataParts[0]=='LOG'):
                    # remove file, remove directory, set bitrate or backup event - these don't need to go to the commander queue - they're non-blocking and independent of one another
                    nobroadcast = True
                    encControl.enq(data,bypass=True)
                if(dataParts[0]=='STR' or dataParts[0]=='STP' or dataParts[0]=='PSE' or dataParts[0]=='RSM' or dataParts[0]=='STK'):
                    #start encode, stop encode, pause encode, resume encode
                    nobroadcast = True
                    encControl.enq(data)
                if(dataParts[0]=='BRQ'):
                    #appreq in background
                    nobroadcast = True
                    encControl.enq(data)
                #------------------------------------------------------------------------------------------------------------
                if(dataParts[0]=='FCT'): #list events that are backed up on external storage (available for restore)
                    return srcMgr.getFeedCount(dataParts[1])
                if(dataParts[0]=='PPD'): #list events that are backed up on external storage (available for restore)
                    return srcMgr.IsPostProcDone()
                if(dataParts[0]=='LBE'): #list events that are backed up on external storage (available for restore)
                    return backuper.archiveList()
                if(dataParts[0]=='SNF'):# server info
                    return serverInfo()
                if(dataParts[0]=='CML'): # camera list
                    return srcMgr.toJSON()
                if(dataParts[0]=='LBP'): # list events that are in the process of backing up (do not yet fully exist on local machine)
                    return backuper.list()
                if(dataParts[0]=='FIX'): # fix MP4 
                    return doMP4Fix(dataParts[1], dataParts[2], dataParts[3]) # event_path, camid, vq
                if(dataParts[0]=='XVT'): # export event 
                    return doExportEvent(dataParts[1], dataParts[2], dataParts[3]) # event_path, camid, vq
                if(dataParts[0]=='SCF'): # extra debug control flag (SCF_XXX)
                    try:
                        global pxpworker
                        if (dataParts[1].strip() == ''):
                            sockCmd = pu.pxpconfig.reload()
                            dbg.setcmdlevel(pu.pxpconfig.getdbglevel())
                        else:
                            if (dataParts[1].strip() == 'workers'): # SCF|workers
                                for w in pxpworker:
                                    pu.mdbg.log(w)
                            else:        
                                sockCmd = int(dataParts[1].strip())
                                bitstr = ""
                                for ix in xrange(16):
                                    if ((sockCmd&(1<<(15-ix)))>0):
                                        bitstr += "1"
                                    else:
                                        bitstr += "0"
                                    if (ix != 15):
                                        bitstr += " "
                                pu.disk.file_set_contents(c.approot+"avoca", bitstr)
                                pu.mdbg.readscf()
                    except Exception as e:
                        return {'results': {'status': False}}
                    return {'results': {'status': True}}
                elif(dataParts[0]=='RTM' and len(dataParts)>2):
                    rtmp_mgr.get_rtmp_cast(dataParts[1], dataParts[2])    
                    return False                
                elif(dataParts[0]=='RTS'):
                    return rtmp_mgr.get_rtmp_stat()                    
                #---------------------------------------------------------------------
                if (dataParts[0]=='PCS'): # PastPage Check Status PCS|USB+BKP+FIX
                    nobroadcast = True
                    # PCS|param|bkp_hid|fix_hid
                    res = {'results': {'status': False}}
                    if (len(dataParts)>=2):
                        try:
                            bkp_hid = dataParts[2].split(',')
                            fix_hid = dataParts[3].split(',')
                            xpt_hid = dataParts[4].split(',')
                            usb_status = {}
                            bkp_status = {}
                            fix_status = {}
                            ejt_status = {}
                            xpt_status = {}
                            if (dataParts[1]):
                                for arg in dataParts[1].split('+'):
                                    if (arg == 'USB'):
                                        usb_status['status'] = backuper.checkusbthere()
                                    elif (arg == 'BKP'):
                                        bkp_status['status'] = backuper.get_status2()
                                    elif (arg == 'FIX'):
                                        fix_status['status'] = mp4builder.check_status(progress=True)
                                    elif (arg == 'EJT'):
                                        ejt_status['status'] = False
                                    elif (arg == 'XPT'):
                                        xpt_status['status'] = export_event.check_status(progress=True)
                                # {'status':true, 'usb':{'status':true}, 'bkp':{'status':{'hid-camid-vq':56,...}}, 'fix':{'status':{}} }    
                                if (xpt_status):
                                    x = 1    
                                res = {'results': {'status':True, 'live':(enc.code&enc.STAT_LIVE), 'usb':usb_status, 'bkp':bkp_status, 'fix':fix_status, 'xpt':xpt_status}} 
                                #pu.mdbg.log("PCS: ---> data1:{}".format(dataParts))
                                #pu.mdbg.log("PCS: ---> data2:{}".format(res))
                        except Exception as e:
                            pu.mdbg.log("[---] PCS: {}  data:{}".format(e, dataParts))
                            return {'results': {'status': False}}
                    return res  
                if(dataParts[0]=='CPS'): # copy status request
                    nobroadcast = True
                    return backuper.status(dataParts[1])
                if(len(dataParts)>=2):
                    dataParts[1]=False
                if (dataParts[0]=='USB'):
                    nobroadcast = True
                    return {'status':backuper.checkusbthere()} # usbmounted()
                if (dataParts[0]=='EJS'):
                    status=backuper.ejectStatus() # ejtprogress()
                    nobroadcast = True
                    return {'status':status, 'progress':backuper.ejectProgressCount, 'msg':'ejecting usb drive'}
                if (dataParts[0]=='EJT'):
                    nobroadcast = True
                    backuper.ejectDrive() # ejectusbdrv()
                    return {'status':True}
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
        #end if len(dataParts)>0
        
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
    except Exception as e:
        dbg.prn(dbg.ERR|dbg.SHL, "[---]DataHandler: addr:{}  data:{}  err:{}  line:{}".format(addr, data, e, sys.exc_info()[-1].tb_lineno))
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
            #pu.mdbg.log(data,addr)
            if(result or (type(result) is dict) or (type(result) is list)):
                try:
                    rspString = json.dumps(result)
                except Exception as e:
                    dbg.prn(dbg.SHL, "[---]sockhandler: data:{} result:{}  err:{}".format(data, result,e))
                    rspString = result
                sock.send(rspString)
            # clientsock.send(msg)
        #client disconnected
    except Exception as e:
        dbg.prn(dbg.ERR|dbg.SHL, "[---]SockHandler: data:{}  err:{}  line:{}".format(data, e, sys.exc_info()[-1].tb_lineno))
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


# devices that will be discovered on this system
devEnabled = {
    "td":{ #teradek cube
         "class":encTeradek
    }
    ,"mt":{ #matrox monarch HD
        "class":encMatrox
    }
    # ,"ph":{ #pivothead
    #     "class":encPivothead
    # }
    ,"sn":{ #sony SNC
        "class":encSonySNC
    }
    ,"dt":{ #delta
        "class":encDelta
    }
    , "ax":{ #axis
          "class":encAxis
    }
    , "dc":{ #dummy IPCam 
          "class":encIPcam
    }
#     ,"db":{
#          "class":encDebug
#     }
}
tmr = {}
tmr['misc'] = [] #contains miscellaneous threads (that might have been killed already or still alive but useless)
# initialize logging class
dbg = debugLogger()
#dbg = pxplog.appLog()
appg = appGlobal()

if __name__=='__main__': # will enter here only when executing this file (if it is included from another process, this IF condition will be false)
    try:
        sockCmd = 0
        
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

        dbg.prn(dbg.MN,"---APP START--", c.ver)
        procMan = procmgr()
        try:
            # remove old encoders from the list, the file will be re-created when the service finds encoders
            os.remove(c.devCamList)
        except:
            pass
        try:
            os.system("rm /tmp/pxp-url*")
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
        tmr['bonjour']      = TimedThread(pu.bonjour.publish,params=("_pxp._udp", pu.io.myName()+' - '+hex(getmac())[2:],80), period=10)

        mp4builder = pxpmisc.MP4Rebuilder()
        
        export_event = pxpmisc.ExportEvent()

        rtmp_mgr = rtmpmgr()

        syncMgr = SyncManager()

        srcMgr = sourceManager(devEnabled)

        # start deleter timer (deletes files that are not needed/old/etc.)
        tmr['delFiles']     = TimedThread(deleteFiles,period=5)

        tmr['cleanupEvts']  = TimedThread(removeOldEvents,period=10)
        #start the threads for forwarding the blue screen to udp ports (will not forward if everything is working properly)

        db = pu.db(c.wwwroot+"_db/pxp_main.db")
        sql = "DELETE FROM `camsettings`"
        success = db.query(sql,'')
        db.close()

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
        pu.mdbg.log("svr_ip:{}".format(pu.io.myIP()))         
        #-------------------------------------------
        sockCmd = pu.pxpconfig.reload()
        dbg.setcmdlevel(pu.pxpconfig.getdbglevel())
        #-------------------------------------------
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
        dbg.prn(dbg.ERR|dbg.MN, "MAIN ERRRRR????????? {0} {1}".format(e, sys.exc_info()[-1].tb_lineno))
    dbg.prn(dbg.MN,'---APP STOP---')
#emd if main
