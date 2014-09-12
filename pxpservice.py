#!/usr/bin/python
from tendo import singleton
from datetime import datetime as dt
from uuid import getnode as getmac
from pxputil import TimedThread
import camera, constants as c, copy, json, os, psutil, pxp, pxputil as pu, signal, socket, subprocess as sb, time
import sys






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

###################################################
################## delete files ##################
###################################################
rmFiles     = []
rmDirs      = []
FNULL       = open(os.devnull,"w") #for dumping all cmd output using Popen()
def deleteFiles():
    try:
        # if there is a deletion in progress - let it finish
        if (pu.disk.psOn("rm -f") or pu.disk.psOn("rm -rf") or pu.disk.psOn("xargs -0 rm")):
            return
        # check how big is the log file
        if(os.stat(c.logFile).st_size>c.maxLogSize):
            #the file is too big - leave only last 500k lines in there (should be about 40-50mb)
            os.system("cat -n 500000 "+c.logFile+" > "+c.logFile)
        # first, take care of the old session files (>1 day) should take no more than a couple of seconds
        os.system("find "+c.sessdir+" -mtime +1 -type f -print0 | xargs -0 rm 2>/dev/null &")
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
        print "[---]deleteFiles", e, sys.exc_traceback.tb_lineno
        pass
#end deleteFiles

# deleting old events
def removeOldEvents():

    if(len(rmDirs)>0):
        return #only do this if the service is not busy deleting other things
    try:
        # delete any undeleted directories
        # get a list of deleted events
        oldevents = pxp._listEvents(onlyDeleted = True)
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
###################################################
################ end delete files ################
###################################################

###################################################
################## util functions ################
###################################################

### pxpservice control classes ###

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
            print "[---]commander init fail??????? ", e
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
            print "executing: ", cmd
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
        except Exception as e:
            print "[---]cmd._exc", e, sys.exc_traceback.tb_lineno
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
        print "init hierarchy:",inspect.stack()[1][3]
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
            print "set hierarchy:",inspect.stack()[1][3]
            print "status before:"
            if(overwrite):
                self.code = statusBit
                self.status = self.statusTxt(statusBit)
            else:
                self.code = self.code | statusBit
            dbgLog("status: "+self.status+' '+str(bin(self.code)))
            if(autoWrite):
                self.statusWrite()
        except Exception as e:
            print "[---]enc.statusSet",e, sys.exc_traceback.tb_lineno
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
            print "status before..:"
            self.code = self.code & ~statusBit
            self.status = self.statusTxt(self.code)
            dbgLog("status: "+self.status+' '+str(bin(self.code)))
            if(autoWrite):
                self.statusWrite()
        except Exception as e:
            print "[---]enc.statusUnset",e, sys.exc_traceback.tb_lineno
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

### encoder device classes ###

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
    def __repr__(self):
        return "<encDevice> ip:{ip} fr:{framerate} br:{bitrate} url:{rtspURL} init:{initialized} on:{isOn}".format(**self.__dict__)
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
        try:
            print "tdSetBitrate"
            url = "http://"+self.ip+"/cgi-bin/api.cgi"
            if(not self.tdSession):
                self.login()
            #end if not tdSession
            print "logged in: ", self.tdSession
            url +="?session="+self.tdSession
            # bitrate should be in bps not in kbps:
            bitrate = bitrate * 1000
            print "NEW BITRATE:.....................................", bitrate
            setcmd = "&VideoEncoder.Settings.1.bitrate="+str(bitrate)
            savecmd = "&q=VideoEncoder.Settings.1.bitrate"

            print "setting..."
            answer = False
            while(not answer):
                answer = pu.io.url(url+"&command=set"+setcmd,timeout=10)
            print answer
            # apply settings
            print "applying..."
            answer = False
            while(not answer):
                answer = pu.io.url(url+"&command=apply"+savecmd,timeout=10)
                print answer
            print answer
            # save the settings
            print "saving..."
            answer = False
            while(not answer):
                answer = pu.io.url(url+"&command=save"+savecmd,timeout=10)
            print answer
        except Exception as e:
            print "[---]encTeradek.setBitrate:", e, sys.exc_traceback.tb_lineno
    #end setBitrate
    def setFramerate(self, framerate):
        try:
            url = "http://"+self.ip+"/cgi-bin/api.cgi"
            if(not self.tdSession):
                self.login()
            #end if not tdSession
            print "logged in: ", self.tdSession
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
            print "NEW RATE:.....................................", newrate
            setcmd = "&VideoEncoder.Settings.1.framerate="+str(newrate)
            savecmd = "&q=VideoEncoder.Settings.1.framerate"
            if(self.nativerate):#currently native frame rate is set - need to reset it manually
                setcmd +="&VideoEncoder.Settings.1.use_native_framerate=0"
                savecmd = "&q=VideoEncoder.Settings.1.use_native_framerate"
            # set the frame rate
            print "setting..."
            answer = False
            attempts = 0
            while((not answer) and attempts<3):
                answer = pu.io.url(url+"&command=set"+setcmd,timeout=10)
                attempts +=1
            if(not answer):
                return False
            print answer
            # apply settings
            print "applying..."
            answer = False
            attempts = 0
            while((not answer) and attempts<3):
                answer = pu.io.url(url+"&command=apply"+savecmd,timeout=10)
                attempts +=1
            if(not answer):
                return False
            print answer
            # save the settings
            print "saving..."
            answer = False
            attempts = 0
            while((not answer) and attempts<3):
                answer = pu.io.url(url+"&command=save"+savecmd,timeout=10)
                attempts +=1
            if(not answer):
                return False
            print answer
            return True
        except Exception as e:
            print "[---]encTeradek.setFramerate:", e, sys.exc_traceback.tb_lineno
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
                dbgLog("no response from: "+url+url2,level=1)
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
            dbgLog("[---]td.update: "+str(e)+" "+str(sys.exc_traceback.tb_lineno),level=2)
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
            monarchs  = pu.ssdp.discover("MonarchUpnp",timeout=7)
            if(len(monarchs)>0):
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
                        print "[---]encMatrox.discover",e, sys.exc_traceback.tb_lineno
                #end for devLoc in monarchs
            #end if monarchs>0
        except Exception as e:
            print "[---]encMatrox.discover",e, sys.exc_traceback.tb_lineno
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
        # for now the only way to extract this information is using the monarch home page (no login required for this one)
        # when they provide API, then we can use that
        mtPage = pu.io.url("http://"+ip+"/Monarch", timeout=10)
        if(not mtPage):
            return False #could not connect to the monarch page
        ########### get rtsp url ###########
        resPos = mtPage.find("ctl00_MainContent_RTSPStreamLabelC2") #this is the id of the label containing video input
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
            rtspURL = mtPage[posStart:posStop] #either this is blank or it has the url
            if(len(rtspURL)>10 and rtspURL.startswith("rtsp://")):
                # got the url
                params['rtsp_url']=rtspURL
                # extract the port
                ip, port = self.parseURI(rtspURL)
                params['rtsp_port']=port
        #end if posStart>0
        ########### end rtsp url ###########
        ########### get video input ###########
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
        ########### get stream settings ###########
        pos = mtPage.find("ctl00_MainContent_StreamSettingsLabel")
        if(pos>0):
            posStart = mtPage.find('>',pos)+1
        else:
            posStart = -1
        if(posStart>0):        
            posStop = mtPage.find('<',posStart)
        else:
            posStop = -1
        if(posStart>0 and posStop>0 and posStop>posStart):
            streamText = mtPage[posStart:posStop] #e.g. 1280x720p, 30 fps, 2000 kb/s; 192 kb/s audio; RTSP
            if((streamText.find(',')>0) and (streamText.find('fps')>0) and (len(streamText.split(','))>2)): #stream information contains at least resolution and frame rate
                parts = streamText.split(',')
                # resolution is in the first part of the text
                resolution = parts[0].strip().split('x')
                if(len(resolution)>1):
                    resolution = resolution[1].strip() #now contains "720p"
                else:
                    resolution = False
                # get framerate - in the second part
                framerate = parts[1].strip().split('fps')
                if(len(framerate)>1):
                    framerate = framerate[0].strip() #contains "30"
                else:
                    framerate = False
                # get bitrate            
                bitrate = parts[2].strip().split("kb") #it will contain kbps or kb/s
                if(len(bitrate)>1):
                    bitrate = bitrate[0].strip()
                else:
                    bitrate = False
                params["streamResolution"] = resolution;
                params["streamFramerate"]  = framerate;
                params["streamBitrate"]    = bitrate;
        #end if posStart>0
        ########### end stream settings ###########
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
        print params, "mt.update"
        if(params):
            self.resolution = params['inputResolution']
            self.isCamera = self.resolution!=False
            self.bitrate = params['streamBitrate']
            self.framerate = params['streamFramerate']
            self.rtspURL = params['rtsp_url']
            print "!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!RESET RTSP URL"
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
            self.rtspURL        = False
            self.id             = int(time.time()*1000000) #id of each device is gonna be a time stamp in microseconds (only used for creating threads)
            self.ipcheck        = '127.0.0.1' #connect to this ip address to check rtsp 
            if(self.type=='td_cube'):
                self.device = encTeradek(ip)
            elif(self.type=='mt_monarch'):
                self.device = encMatrox(ip)
            elif(self.type=='ph_glass'):
                self.device = encPivothead(ip)
            else: #unknown device type specified
                return False
            if(url):
                self.device.rtspURL = url
            if(preview):
                self.previewURL = preview
            if(not 'src' in tmr):
                tmr['src']={}
            tmr['src'][self.id] = TimedThread(self.monitor,period=2)
        except Exception as e:
            print "[---]source.init", e, sys.exc_traceback.tb_lineno
    #end init
    def __repr__(self):
        return "<source> url:{rtspURL} type:{type} dev:{device}".format(**self.__dict__)
    def camPortMon(self):
        """ monitor data coming in from the camera - to make sure it's continuously receiving """
        try:
            print "starting camportmon for ", str(self)
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
            print ".............bound.................", self.isEncoding
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
                    dbgLog("[---]camPortMon err: "+str(e)+str(sys.exc_traceback.tb_lineno),level=2)
            #end while
        except Exception as e:
            print "[---]camportmon err: ", e, sys.exc_traceback.tb_lineno
    def monitor(self):
        """ monitors the device parameters and sets its parameters accordingly """
        try:
            self.device.update() #get all available parameters
            if(enc.code & enc.STAT_SHUTDOWN):
                return False
            # make sure live555 is running
            urlFilePath = "/tmp/pxp-url-"+str(self.device.ip)
            if(not procMan.pexists(name="live555",devID=self.device.ip)):
                print "adding live555 for ", self.device.ip, self.type
                procMan.padd(name="live555",devID=self.device.ip,cmd="live555ProxyServer -o "+urlFilePath+" "+self.device.rtspURL,keepAlive=True,killIdle=True, forceKill=True)
                self.device.liveStart = time.time()  # record the time of the live555 server start
            live555timeout = time.time()-10 #wait for 10 seconds to restart live555 server
            if(not self.device.isOn and self.device.liveStart<live555timeout):
                print "stopping live555"
                procMan.pstop(name="live555",devID=self.device.ip)
            #make sure live555 is up and running and no changes were made to the ip address
            if(os.path.exists(urlFilePath)): #should always exist!!!!
                streamURL = pu.disk.file_get_contents(urlFilePath).strip()
                if(enc.busy() and not (enc.code & enc.STAT_STOP) and self.rtspURL != streamURL):
                    print "url changed", self.rtspURL, streamURL
                    #the streaming url changed - update it in the capturing ffmpeg command if the encoder was live already
                    while(procMan.pexists(name='capture', devID = self.device.ip)):
                        print "trying to stoppppppppppppppppp"
                        procMan.pstop(name='capture',devID=self.device.ip)
                    camMP4  = str(self.ports['mp4'])
                    camHLS  = str(self.ports['hls'])
                    chkPRT  = str(self.ports['chk'])
                    capCMD  = encBuildCapCmd(streamURL, chkPRT, camMP4, camHLS)
                    procMan.padd(name="capture",devID=self.device.ip,cmd=capCMD, keepAlive=True, killIdle=True, forceKill=True)
                self.rtspURL = streamURL
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
                    dbgLog("[---]source.monitor err: "+str(e)+" "+str(self.ipcheck)+" "+str(self.ports["rtp"]),level=2)
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
                    pass
                if(strdata.find('timed out')>-1): #the connection is down (maybe temporarily?), the isOn is already set to false
                    pass
                #a device is not available (either just connected or it's removed from the system)
                #when connection can't be established or a response does not contain RTSP/1.0 200 OK
                self.device.isOn = (data.find('RTSP/1.0 200 OK')>=0)

            # this is only relevant for medical
            if(self.device.initialized and self.device.ccFramerate and self.device.framerate>=50):
                self.device.setFramerate(self.device.framerate/2) #set resolution to half if it's too high (for iPad rtsp streaming)
            # if(self.device.isOn):
                # self.device.initialized = True
            if(self.device.initialized):
                self.device.initStarted    = int(time.time()*1000) #when device is initialized already, reset the timer
            self.device.initialized = self.device.isOn #if the stream is unreachable, try to re-initialize the device or remove it form the system
        except Exception as e:
            print "[---]source.monitor", e, sys.exc_traceback.tb_lineno
            return False
        return True
    #end monitor
    def stopMonitor(self):
        try:
            # stop the monitor
            print "stop monitor thread"
            self.isEncoding = False
            if('src' in tmr and self.id in tmr['src']):
                tmr['src'][self.id].kill()
            print "stopping camportmon thread"
            if('portCHK' in tmr and self.id in tmr['portCHK']):
                print "encoding: ", self.isEncoding
                tmr['portCHK'][self.id].kill()
            print "stopping live555"
            # stop the processes associated with this device
            procMan.pstop(name="live555",devID=self.id)
            print "done stopping"
        except Exception as e:
            print "[---]source.stopMonitor", e, sys.exc_traceback.tb_lineno
#end source class

class sourceManager:
    def __init__(self):
        self.mp4Base = 22500 #ffmpeg captures rtsp stream and outputs H.264 stream here
        self.hlsBase = 22600 #ffmpeg captures rtsp stream and outputs MPEG-TS here
        self.chkBase = 22700 #port where a monitor is sitting and checking if packets are arriving, doesn't matter the format
        self.sources = []
        if(not 'src' in tmr):
            tmr['src'] = {}
        tmr['src']['mgrmon'] = TimedThread(self.monitor, period=3)
    def addDevice(self, inputs):
        """ adds a source to the list 
        @param (str)    ip      - ip address of the source (used for checking if the device is alive)
        @param (str)    url     - rtsp source url
        @param (str)    encType - type of source/encoder (e.g. td_cube, ph_glass, mt_monarch)
        """
        try:
            if(enc.code & enc.STAT_SHUTDOWN):
                return False
            ######################################## 
            dbgLog("add device:"+str(inputs))
            ######################################## 
            sources = copy.deepcopy(self.sources)
            if(not((('url' in inputs) or ('preview' in inputs)) and ('ip' in inputs))):
                #neither url nor preview was specified or ip wasn't specified - can't do anything with this encoder
                return False
            ip = inputs['ip']
            idx = self.exists(ip)
            ######################################## 
            dbgLog("exists?"+str(idx))
            ######################################## 
            if(idx>=0): #device already exists in the list, must've re-discovered it, or discovered another streaming server on it (e.g. preview)
                if('url' in inputs): #update url (in case it's changed)
                    self.sources[idx].device.rtspURL = inputs['url']
                    # self.sources[idx].device.ports['rtp'] = int(inputs['port'])
                elif('preview' in inputs):
                    self.sources[idx].previewURL = inputs['preview']
                    self.sources[idx].ports['preview'] = int(inputs['preview-port'])
                if('port' in inputs):#update the ports as well (may have changed)
                    self.sources[idx].ports['rtp'] = inputs['port']
                return True
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
                return True
        except Exception as e:
            print "[---]srcMgr.addDevice: ",e, sys.exc_traceback.tb_lineno
        return False
    #end addDevice
    def discover(self):
        # check if there are any encoders on the network
        if(not 'src' in tmr):
            tmr['src'] = {}
        try:
            encTD = encTeradek()
            encMT = encMatrox()
            encPH = encPivothead()
            tmr['src']['td'] = TimedThread(encTD.discover, params=self.addDevice, period=5)
            tmr['src']['mt'] = TimedThread(encMT.discover, params=self.addDevice, period=5)
            tmr['src']['ph'] = TimedThread(encPH.discover, params=self.addDevice, period=5)
        except Exception as e:
            print "[---]srcMgr.discover: ",e, sys.exc_traceback.tb_lineno
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
        print "cap start"
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
                if(len(self.sources)<2):
                  # there is only one camera - no need to set camIdx for file names
                  fileSuffix = ""
                else: #multiple cameras - need to identify each file by camIdx
                  fileSuffix = camIdx

                ffmp4Out +=" -map "+camIdx+" -codec copy "+c.wwwroot+"live/video/main"+fileSuffix+".mp4"
                # this is HLS capture (segmenter)
                if (pu.osi.name=='mac'): #mac os
                    segmenters[src.device.ip] = c.segbin+" -p -t 1s -S 1 -B "+fileSuffix+"segm_ -i list"+fileSuffix+".m3u8 -f "+c.wwwroot+"live/video 127.0.0.1:"+camHLS
                elif(pu.osi.name=='linux'): #linux
                    os.chdir(c.wwwroot+"live/video")
                    segmenters[src.device.ip] = c.segbin+" -d 1 -p "+fileSuffix+"segm_ -m list"+fileSuffix+".m3u8 -i udp://127.0.0.1:"+camHLS+" -u ./"

                # if(quality=='low' and 'preview' in cameras[src.device.ip]):
                #     camURL = cameras[src.device.ip]['preview']
                # else:
                # this ffmpeg instance captures stream from camera and redirects to mp4 capture and to hls capture
                print "capcmd:",src.rtspURL, chkPRT, camMP4, camHLS
                ffcaps[src.device.ip] = encBuildCapCmd(src.rtspURL, chkPRT, camMP4, camHLS)
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
            dbgLog("[---]encCapStop: "+str(e)+str(sys.exc_traceback.tb_lineno),level=2)
            self.encCapStop() #it will be force-stopped automatically in the stopcap function
            enc.statusSet(enc.STAT_READY)
    #end encCapStart
    def encCapStop(self,force=False):
        """stops the capture, kills all ffmpeg's and segmenters
        force - (optional) force-kill all the processes - makes stopping process faster
        """
        try:
            dbgLog("stopping capture... force:"+str(force))
            if(enc.code & enc.STAT_STOP): #already stopping
                return False
            if(not(enc.code & (enc.STAT_LIVE | enc.STAT_PAUSED))):
                force = True #the encode didn't finish starting or didn't start properly - force shut down everything
            if(not (enc.code & enc.STAT_SHUTDOWN)): #set the status to stopping (unless the script is being shut down then it should stay at shutting down)
                enc.statusSet(enc.STAT_STOP)
            # stop all captures
            dbgLog("stopping segment and capture")
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
            dbgLog("stopped, forwarding the bluescreen")

            # to stop mp4 recorder need to push blue screen to that ffmpeg first, otherwise udp stalls and ffmpeg produces a broken MP4 file
            procMan.padd(cmd=ffBlue, name="blue", devID="ALL", keepAlive=True, killIdle = True, forceKill=True)
            time.sleep(5)
            timeStart = time.time()
            while(((time.time()-timeStart)<timeout) and not procMan.palive(name="blue")):
                time.sleep(1)
            # now we can stop the mp4 recording ffmpeg
            dbgLog("stopping mp4 recorder")
            procMan.pstop(name='record',force=force)
            timeStart = time.time()
            # wait for the recorder to stop, then kill blue screen forward
            while(procMan.pexists("record") and not (enc.code & enc.STAT_SHUTDOWN) and (time.time()-timeStart)<timeout):
                time.sleep(1)
            if((time.time()-timeStart)>=timeout):#timeout reached
                procMan.pstop(name='record', force=True)
            dbgLog("mp4 record stopped--")
            # kill the blue screen ffmpeg process
            procMan.pstop(name='blue')
            timeStart = time.time()
            while(procMan.palive("blue") and not (enc.code & enc.STAT_SHUTDOWN) and (time.time()-timeStart)<timeout): #wait for bluescreen ffmpeg to stop
                time.sleep(1)
            if((time.time()-timeStart)>=timeout):#timeout reached
                procMan.pstop(name='blue', force=True)
            dbgLog("bluescreen stopped")
            # stop the live555 (for good measure)
            os.system("killall -9 live555ProxyServer >/dev/null 2>/dev/null")
        except Exception as e:
            dbgLog("[---]encCapStop: "+str(e)+str(sys.exc_traceback.tb_lineno),level=2)
            pass
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
            print "[---]sources.exists:",e,sys.exc_traceback.tb_lineno
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
            # print "mon.................."
            # print sources
            # print "..................mon"
            for src in sources:
                now = int(time.time()*1000)
                if ((not src.device.initialized) and (now-src.device.initStarted)>60000): #could not initialize the device after a minute
                    print "could not init device - stop monitor"
                    # src.stopMonitor()
                    self.sources[idx].stopMonitor()
                    print "deleting...", self.sources
                    del self.sources[idx]
                    print "deleted ", self.sources
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
            self.toJSON()
        except Exception as e:
            print "[---]srcmgr.monitor:",e, sys.exc_traceback.tb_lineno
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
            print "[---]mgr.setBitrate",e,sys.exc_traceback.tb_lineno
    #end setBitrate
    def toJSON(self, autosave = True):
        """ creates a dictionary of all the sources 
        @param (bool) autosave - (optional) saves the dictionary in json format to a pre-defined file (default=True)
        """
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
        with open(c.devCamList,"w") as f:
            f.write(json.dumps(validDevs))
#end sourceManager class

#recursively kills threads in the ttObj
def pxpTTKiller(ttObj={},name=False):
    dbgLog("pxpkill: "+str(name)+"...")
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
            print "...killed"
        except Exception as e:
            print "[---]TTKiller:",e,sys.exc_traceback
        return

def pxpCleanup(signal=False, frame=False):
    global procMan
    try:
        dbgLog("terminating services...")
        if(enc.code & (enc.STAT_LIVE | enc.STAT_PAUSED)):
            print "stopping live event"
            srcMgr.encCapStop(force=True)
        enc.statusSet(enc.STAT_SHUTDOWN)
        dbgLog("stopping timers...")
        pxpTTKiller(tmr,"tmr")
        # make sure live555 isn't running
        os.system("killall -9 live555ProxyServer 2>/dev/null &")
        dbgLog("procMan cleanup... ")
        try:
            if(procMan):
                procMan.pstop(name="live555", async=False)
                del procMan
        except:
            pass
        dbgLog("terminated!")
    except Exception as e:
        print "[---]pxpCleanup FAIL?!!!!?!?!", e, sys.exc_traceback.tb_lineno
        pass
#end pxpCleanup

def dbgLog(msg, timestamp=True, level=0):
    """ print debug info 
        @param (str) msg - message to display
        @param (bool) timestamp - display timestamp before the message
        @param (int) level - debug level:
                                    0 - info
                                    1 - warning
                                    2 - error
    """
    try:
        debugLevel = 0 #the highest level to print
        if(level<debugLevel):
            return
        # if the file size is over 1gb, delete it
        logFile = c.logFile
        if(os.path.exists(logFile) and os.stat(logFile).st_size>=(1<<30)):
            os.remove(logFile)
        print dt.fromtimestamp(time.time()).strftime("%Y-%m-%d %H:%M:%S.%f"), msg
        with open(logFile,"a") as fp:
            fp.write(dt.fromtimestamp(time.time()).strftime("%Y-%m-%d %H:%M:%S.%f"))
            fp.write(msg)
            fp.write("\n")
    except Exception as e:
        print "[---]dbgLog:",e, sys.exc_traceback.tb_lineno

# kick the watchdog on each ipad (to make sure the socket does not get reset)
def kickDoge():
    # simply add the message to the queue of each ipad
    BBQcopy = copy.deepcopy(globalBBQ)
    for client in BBQcopy:
        # client entry in the BBQ list
        clnInfo = BBQcopy[client]
        # commands sent to this client that were not ACK'ed
        myCMDs = clnInfo[0]
        # kick the watchdog only if the queue is empty
        if(len(myCMDs)<=0):
            addMsg(client,"doge")
#end kickDoge

###################################################
################# end util functions ##############
###################################################


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
    for client in BBQcopy:
        try:
            # client entry in the BBQ list
            clnInfo = BBQcopy[client]
            # commands sent to this client that were not ACK'ed
            myCMDs = clnInfo[0]
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
            pass
    #for client in globalBBQ
#end bbqManage


# create ffmpeg command that captures the rtsp stream
def encBuildCapCmd(camURL, chkPRT, camMP4, camHLS):
    # if ther's a problem, try adding -rtsp_transport udp before -i
    return c.ffbin+" -rtsp_transport tcp -i "+camURL+" -codec copy -f h264 udp://127.0.0.1:"+chkPRT+" -codec copy -f h264 udp://127.0.0.1:"+camMP4+" -codec copy -f mpegts udp://127.0.0.1:"+camHLS
#end encBuildCmd

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
            # print "starting: ", self.name, self.pid, "force:", self.forcekill
            # get the reference to the object (for communicating/killing it later)
            self.ref=ps
            #set these 2 variables to make sure it doesn't get killed by the next manager run
            self.threads[ps.pid]=TimedThread(self._monitor,period=1.5)
            self.alive=True
            self.cpu=100
            self.run = True
            return True
        except Exception as e:
            dbgLog("[---]proc.start: "+str(e)+str(sys.exc_traceback.tb_lineno))
        return False
    def stop(self,async=True,force=False,end=False):
        """ stops the process 
            @param (bool) async - whether to stop this event in the background (default: True)
            @param (bool) force - force-stop the process if true
            @param (bool) end   - permanently end the process (no possibility of restart)
        """
        # print "stopping: ", self.name, self.pid, "force:", (force or self.forcekill)
        self.off = end
        self.run = False
        try:
            if(self.off):
                self.threads['manager'].kill()
        except Exception as e:
            print "[---]proc.stop:",e,sys.exc_traceback.tb_lineno
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
        print "proc", self.name, "cleanup"
        for thread in self.threads:
            try:#remove any running threads
                print "clean ",thread
                self.threads[thread].kill()
            except Exception as e:
                print "[---]proc._cleanup",self.name, thread, "---fail:",e
                pass
    def _monitor(self):
        try:
            # monitor the process health
            self.alive = psOnID(pid=self.pid) #check if the process is alive
            self.cpu = pu.disk.getCPU(pid=self.pid) #get cpu usage
        except Exception as e:
            dbgLog("[---]proc._monitor: "+str(e)+sys.exc_traceback.tb_lineno)
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
            dbgLog("[---]proc._killer: "+str(e)+" "+str(errline), level=2)
#end class proc

class procmgr:
    """ process management class """
    def __init__(self):
        self.procs = {} #processes in the system
    def dbgprint(self):
        procs = self.procs.copy()
        if(len(procs)>0):
            print "----------------------------------"
            for idx in procs:
                dbgLog("%s %s %s %s %s %s"%(procs[idx].name, procs[idx].alive, procs[idx].cpu, procs[idx].pid, procs[idx].keepalive, procs[idx].run))
            print "----------------------------------"
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
    # add a new process and starts it
    def padd(self,cmd,name,devID,keepAlive=False,killIdle=False,forceKill=False):
        try:
            idx = 0 #the index of the new process
            procs = self.procs.copy()
            #find the next available index
            for pidx in procs:
                if(pidx>=idx):
                    idx = pidx+1
            self.procs[idx] = proc(cmd,name,devID,keepAlive,killIdle,forceKill)
            print " added:::::::::::::::: ",idx, self.procs[idx]
            # start the process as soon as it's added
            if(self.procs[idx].start()):
                return True
            #could not start stream - no need to add it to the list
            del self.procs[idx]
            return False
        except Exception as e:
            print "[---]padd:",e
            return False
    #end padd
    def pexists(self,name,devID=False):
        """ determine whether a process exists (stopped, idle, but present in the list)
        @param (str) name - name of the process
        @param (str) devID - id of the device this process belongs to. if unspecified, return the first process matching the name (default: False)
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
    def pstop(self,name,devID=False,force=False,remove=True,async=True,restart=False):
        """ stops a specified process
        @param (str) name - name of the process to stop
        @param (str) devID - id of the device this process belongs to. if unspecified, stop this process on every device (default: False)
        @param (bool) force - force-kill the process (default: False)
        @param (bool) remove - when True, this process will be removed from the list
        """
        import inspect
        print "killer hierarchy:",inspect.stack()[1][3]
        procs = self.procs.copy()
        for idx in procs:
            proc = procs[idx]
            if(proc.name==name):
                if(not devID or proc.dev==devID): #either devID matches or devID wasn't specified - just kill processes matching the name
                    if(restart):
                        proc.restart()#this operation is synchronous
                    else:#just stop the process
                        proc.stop(async=async,force=force, end=remove) #if removing the process, do not allow it to be restarted
                        if(remove): #only delete the process from the list if user specifically requested it
                            if(not 'killers' in tmr):
                                tmr['killers'] = []
                            tmr['killers'].append(TimedThread(self._stopwait,(idx,)))
                    #end if stop
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
        dbgLog("kill err::::::::::::::::::"+str(e)+str(sys.exc_traceback.tb_lineno))
        pass

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
####################################################################
def DataHandler(data,addr):
    try:
        # client IP address
        senderIP = str(addr[0])
        # client port
        senderPT = str(addr[1])
        dbgLog("............... BBQ GOT: "+str(data))
        #if it was a command, it'll be split into segments by vertical bars
        dataParts = data.split('|')
        # if(senderIP!="127.0.0.1"):
            # dbgLog("got data: "+data+" from: "+senderIP)
        if(len(dataParts)>0):
            # this is a service request
            if(senderIP=="127.0.0.1"):
                nobroadcast = False #local server allows broadcasting
                # these actions can only be sent from the local server - do not broadcast these
                if(dataParts[0]=='RMF' or dataParts[0]=='RMD' or dataParts[0]=='BTR'):
                    encControl.enq(data,bypass=True)
                    nobroadcast = True
                if(dataParts[0]=='STR' or dataParts[0]=='STP' or dataParts[0]=='PSE' or dataParts[0]=='RSM'):
                    encControl.enq(data)
                    nobroadcast = True
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
                return            
        #if len(dataParts)>0
        ###########################################
        #             broadcasting                #
        ###########################################
        if(nobroadcast or senderIP!="127.0.0.1"): #only local host can broadcast messages
            return
        BBQcopy = copy.deepcopy(globalBBQ)
        for clientID in BBQcopy:
            try:
                # add message to the queue (and send it)
                addMsg(clientID,data)
            except Exception as e:
                pass
    except:
        pass

def SockHandler(sock,addr):
    while 1:
        data = sock.recv(4096)
        if not data:#exit when client disconnects
            break
        # got some data
        DataHandler(data,addr)
        # clientsock.send(msg)
    #client disconnected
    clientID = str(addr[0])+"_"+str(addr[1])
    del globalBBQ[clientID]
    dbgLog("disconnected: "+clientID)
    sock.close()


# set encoder status

#make sure there is only 1 instance of this script running
# me = singleton.SingleInstance()
procs = pu.disk.psGet("pxpservice.py")
if(len(procs)>0 and not (os.getpid() in procs)):
    print "ps on!!"
    exit()
else:
    print procs
    print "ps off!!"
tmr = {}
enc = encoderStatus()
encControl = commander() #encoder control commands go through here (start/stop/pause/resume)

dbgLog("---APP START--")
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

srcMgr = sourceManager()

srcMgr.discover()

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

dbgLog("main...")
if __name__=='__main__':
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        dbgLog("got socket.")
        s.bind(("127.0.0.1",sockInPort))
        dbgLog("bind")
        s.listen(2)
        dbgLog("listen")
        appRunning = True
        dbgLog("run: "+str(appRunning))
        while appRunning:
            try:
                dbgLog("LISTENING ON "+str(sockInPort))
                sock, addr = s.accept()
                #will get here as soon as there's a connection
                clientID = str(addr[0])+"_"+str(addr[1])
                dbgLog("connected: "+clientID)
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
        print "MAIN ERRRRR????????? ",e
dbgLog('---APP STOP---')