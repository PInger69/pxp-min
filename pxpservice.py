#!/usr/bin/python
from tendo import singleton
from datetime import datetime as dt
from uuid import getnode as getmac
from pxputil import TimedThread
import camera, constants as c, copy, json, os, psutil, platform, pxp, pxputil as pu, pybonjour, select, signal, socket, subprocess as sb, time
import netifaces as ni
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

# queue of PIDs that need to be killed in this format: 
# [
#     {
#         'pid':<pid>,
#         'pgid':<pgid>,
#         'ref':<obj reference>, --reference to the process that was started 
#         'timeout':<seconds>,
#         'force':True/False,
#         'count':<number> --of kill attempts
#     }
#     ...
# ]

lastStatus = 0
# when was a kill sig issued
lastKillSig = 0
# when was a start signal issued
lastStartSig = 0
bitENC      =  1 << 0
bitCAM      =  1 << 1
bitSTREAM   =  1 << 2
bitSTART    =  1 << 3

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
# references for subprocesses (to communicate with them)
# {
#   '192.168.1.153':{
#       'bluecmd':"ffmpeg -loop 1 -re -i img.jpg.....",
#       'blueref':<object reference>
#       #OR
#       'ffcmd':"ffmpeg -i rtsp://192.168.1.109:554/stream1 -map 0.....",
#       'ffref':<object reference>
#   }
# }

# input ports with their statuses.
# e.g.:
# {
#   2270:{
#           forwarding  :True,              #--whether this port is forwarding
#           status      :'paused',          #--status of the camera, data will be forwarded here only when 'live'
#           type        :'mp4',             #--type of stream on this port
#           camera      :'192.168.1.119',   #--devID for this camera
#           input       :22700,             #--where data is being received
#           output      :22000,             #--where data is being sent
#           active      :True               #--False if no data is being received on this port, True if receiving data
#       },
#   2280:{
#           forwarding  :True,
#           status      :'paused'
#           type        :'hls',
#           camera      :'192.168.1.119',
#           input       :2270,
#           output      :2210,
#           active      :True
#       }
# }
# 
portIns = {}
# used in UDP port forwarding - contains sets of ports, 
# ports that are specified here will receive data from incoming ports (in the portFwd() function)
# every port in a set will receive same packets
# each set is a list with a name. e.g. 'mp4':[12345, 12346, 12347]
portFwds = {}

proxyBase  = 22000 #output port for rtsp stream (live555 takes in rtsp from the IP source and forwards it to local server on this port)

dskMP4base = 22100 #ffmpeg listens on this port and writes mp4 to disk (for subsequent cameras, ports will be 22001, 22002...)
dskHLSbase = 22200 #m3u8 segmenter listens on this port and writes segments to disk
blueHLS    = 22300 #ffmpeg output for MPEG-TS with blue screen image
blueMP4    = 22400 #ffmpeg output for h.264 stream with blue screen image
camMP4base = 22500 #ffmpeg captures rtsp stream and outputs H.264 stream here
camHLSbase = 22600 #ffmpeg captures rtsp stream and outputs MPEG-TS here

sockInPort = 2232
# blueFwds = {'mp4':[],'hls':[]} #add -1 to kill the port fwd process
###################################################
################## delete files ##################
###################################################
rmFiles     = []
rmDirs      = []
bonjouring  = [True] #has to be a list to stop bonjour externally
FNULL       = open(os.devnull,"w") #for dumping all cmd output using Popen()
SHUTDOWN    = False #set to true when pxpservive is shutting down
def deleteFiles():
    # if there is a deletion in progress - let it finish
    if (psOn("rm -f") or psOn("rm -rf") or psOn("xargs -0 rm")):
        return    
    # first, take care of the old session files (>1 day) should take no more than a couple of seconds
    os.system("find "+c.wwwroot+"session -mtime +1 -type f -print0 | xargs -0 rm &")
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

class encoder:
    """
    encoder status/configuration class
    """
    code = 0 #encoder status code
    status = 'unknown'

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
            if(overwrite):
                self.code = statusBit
                self.status = self.statusTxt(statusBit)
            else:
                self.code = self.code | statusBit
            dbgLog("status: "+self.status+' '+str(bin(self.code)))
            if(autoWrite):
                self.statusWrite()
        except Exception as e:
            print e, sys.exc_traceback.tb_lineno
    #end status

    def statusUnset(self,statusBit, autoWrite = True):
        """Resets the status bit 
        statusBit - which bit to unset (set to 0)
        autoWrite - (optional) write the status to disk right away (default=True)
        """
        try:
            self.code = self.code & ~statusBit
            self.status = self.statusTxt(self.code)
            dbgLog("status: "+self.status+' '+str(bin(self.code)))
            if(autoWrite):
                self.statusWrite()
        except Exception as e:
            print e, sys.exc_traceback.tb_lineno
    #end statusUnset
    def statusWrite(self):
        """ writes out current status to disk """
        # this function is executed automatically (initialized at the bottom of this file), simply records current pxp status in a file
        # the text status is saved simply as 'status' and the numeric status code is saved as 'statuscode'
        # replace() is to make sure that if status has \ or ', it won't break the command and give invalid status
        os.system("echo '"+json.dumps({"status":self.status.replace("\"","\\\""), "code":self.code})+"' > "+c.encStatFile)
    #end statusWrite

    def statusTxt(self, statusCode):
        """ return the text corresponding to the status code """
        if(statusCode & self.STAT_INIT):
            return 'initializing'
        if(statusCode & self.STAT_CAM_LOADING):
            return 'loading camera'
        if(statusCode & self.STAT_READY):
            return 'ready'
        if(statusCode & self.STAT_LIVE):
            return 'live'
        if(statusCode & self.STAT_SHUTDOWN):
            return 'shutting down'
        if(statusCode & self.STAT_PAUSED):
            return 'paused'
        if(statusCode & self.STAT_STOP):
            return 'stopping'
        if(statusCode & self.STAT_START):
            return 'starting'
        if(statusCode & self.STAT_NOCAM):
            return 'no camera'
        return 'unknown'
    #end statusTxt
#end encoder class

def pxpCleanup(signal=False, frame=False):
    global SHUTDOWN
    try:
        dbgLog("terminating services...")
        if(enc.code & (enc.STAT_LIVE | enc.STAT_PAUSED)):
            print "stopping live event"
            encStopCap(force=True)
        SHUTDOWN = True
        enc.statusSet(enc.STAT_SHUTDOWN)
        dbgLog("stopping timers...")
        for tm in tmr:
            dbgLog(str(tm)+"...")
            if(type(tmr[tm]) is dict):
                for t in tmr[tm]:
                    try:
                        tmr[tm][t].kill()
                    except:
                        pass
            else:
                try: #use try here in case the thread was stopped previoulsy
                    tmr[tm].kill()
                except:
                    pass
        dbgLog("terminated!")
    except Exception as e:
        pass
#end pxpCleanup

def dbgLog(msg, timestamp=True):
    try:
        print dt.fromtimestamp(time.time()).strftime("%Y-%m-%d %H:%M:%S.%f"), msg
        with open(c.wwwroot+"_db/pxpservicelog.txt","a") as fp:
            fp.write(dt.fromtimestamp(time.time()).strftime("%Y-%m-%d %H:%M:%S.%f"))
            fp.write(msg)
            fp.write("\n")
    except Exception as e:
        pass
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

#returns true if both ip addresses belong to the same subnet
def sameSubnet(ip1,ip2):
    return ".".join(ip1.split('.')[:3])==".".join(ip2.split('.')[:3])

def get_lan_ip():
    try:
        ipaddr = "127.0.0.1"
        for dev in ni.interfaces():
                adds = ni.ifaddresses(dev)
                for addr in adds:
                        for add in adds[addr]:
                                if('addr' in add):
                                        ip = add['addr']
                                        ipp = ip.split('.')
                                        if(len(ipp)==4 and ip!=ipaddr): #this is a standard X.X.X.X address (ipv4)
                                            ipaddr = ip
                                        if(not sameSubnet("127.0.0.1",ipaddr)): #first non-localhost ip found returns - should be en0 - or ethernet connection (not wifi)
                                            return ipaddr
    except:
        pass
    return ipaddr
#end getlanip

###################################################
################# end util functions ##############
###################################################

def encState(state):
    #       app starting
    #       | encoder streaming
    #       | | camera present
    #       | | | pro recorder present
    #       | | | |
    # bits: 0 0 0 0
    if(not (state&1)):
        return "pro recoder disconnected"
    if(not (state&2)):
        return "camera disconnected"
    if(not (state&4)): #not streaming for some reason
        return "camera disconnected"
    # if(state & 8):
        # return "streaming app is starting"
    return "streaming ok"
# function called with ever timer tick that resends any unreceived events and deletes old ones
# also checks encoder status
def bbqManage():
    global globalBBQ, lastStatus
    # get encoder status
    newStatus = enc.code #int(pu.disk.file_get_contents("/tmp/pxpstreamstatus")) #contains status code
    sendStatus = False
    if(newStatus != lastStatus):
        sendStatus = newStatus #encState(pxpStatus)
    lastStatus = newStatus
    now = int(time.time()*1000) #current time
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

################## network management ##################
# registers pxp as bonjour service
def pubBonjour():
    global SHUTDOWN
    name    = socket.gethostname() #computer name
    if(name[-6:]=='.local'):# hostname ends with .local, remove it
        name = name[:-6]
    # append mac address as hex ( [2:] to remove the preceding )
    name += ' - '+ hex(getmac())[2:]
    regtype = "_pxp._udp" #pxp service
    # port is the HTTP port specified in apache:
    p = sb.Popen("cat /etc/apache2/httpd.conf | grep ^Listen | awk '{print $2}' | head -n1", shell=True, stdout=sb.PIPE, stderr=sb.PIPE)
    out, err= p.communicate()
    port    = int(out.strip())

    # gets called when bonjour registration is complete
    def register_callback(sdRef, flags, errorCode, name, regtype, domain):
        pass
    #end register_callback
    try:
        # register the pxp service
        sdRef = pybonjour.DNSServiceRegister(name = name,
                                             regtype = regtype,
                                             port = port,
                                             callBack = register_callback)
        while not SHUTDOWN:#bonjouring[0]:
            ready = select.select([sdRef], [], [],2)
            if sdRef in ready[0]:
                pybonjour.DNSServiceProcessResult(sdRef)
    except Exception as e:
        pass
    finally:
        sdRef.close()
#end pubBonjour
#forwards a udp port to another (or several)
#portIN - which port to read from
#portOutSet - index of the set of ports where to forward ('hls','mp4'...)
def portFwd(portIN,portOutSet):
    # portIN = 2240
    global SHUTDOWN
    try:
        host = '127.0.0.1'          #local ip address
        # portIN = 2250             #where packets are coming from
        # portOUT= 2200             #where packets are forwarded
        sIN = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)      #Create a socket object
        sOUT = socket.socket(socket.AF_INET, socket.SOCK_DGRAM) #create socket for outgoing packets    
        sIN.bind((host, portIN))    #Bind to the port
        sIN.settimeout(1)
        while not SHUTDOWN: #keep receiving forever
            try:
                if(not (portOutSet in portFwds) or len(portFwds[portOutSet])<1):
                    time.sleep(0.1)
                    continue #this set is not defined or is empty
                ports = portFwds[portOutSet]
                data, addr = sIN.recvfrom(1024)
                if(len(data)<=0):#no data received
                    continue
                for port in ports:
                    sOUT.sendto(data,(host,port))
            except socket.error, msg:
                dbgLog("portFwd sock err: "+str(msg))
                pass
            except Exception as e:
                dbgLog("portFwd err: "+str(e)+str(sys.exc_traceback.tb_lineno))
                pass
        #end while True
    except Exception as e:
        dbgLog("portFwd global err: "+str(e)+str(sys.exc_traceback.tb_lineno))
        pass
#end main
################## network management ##################

################## teradek management ##################
def camPortMon(port):
    global SHUTDOWN
    try:
        host = '127.0.0.1'          #local ip address
        sIN = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)  #Create a socket object
        sOUT = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP) #create socket for outgoing packets
        portIn = port['input']
        portOut= port['output']
        sIN.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        err = True
        while (err):
            try:
                sIN.bind((host, portIn)) #Bind to the port
                err = False
            except:
                time.sleep(1)
                err = True
        #end while err
        sIN.setblocking(0)
        sIN.settimeout(0.5)
        timeStart = time.time()
        while portIns[port['input']]['forwarding'] and not SHUTDOWN:
            try:
                if(port['status']!='live'): #this camera is paused or stopped - do not forward anything
                    time.sleep(0.1) #reduce the cpu load
                    continue
                data, addr = sIN.recvfrom(65535)
                if(len(data)<=0 and portIns[portIn]['active']):
                    continue
                #pxp status should be 'live' at this point
                if((enc.code & enc.STAT_START) and (time.time()-timeStart)>2):
                    enc.statusSet(enc.STAT_LIVE,autoWrite=False)
                portIns[portIn]['active']=True
                sOUT.sendto(data,(host,portOut))
                # send to cloud
                # sOUT.sendto(data,("54.221.235.84",20202))
            except socket.error, msg:
                # only gets here if the connection is refused
                try:
                    timeStart = time.time()
                    if(portIn in portIns):
                        portIns[portIn]['active']=False
                        devID = portIns[portIn]['camera']
                        if(enc.code & enc.STAT_LIVE):
                            encoders[devID]['on']=False #only set encoder status if there is a live event
                    # time.sleep(0.5)
                except Exception as e:
                    pass
            except Exception as e:
                dbgLog("camportmon err: "+str(e)+str(sys.exc_traceback.tb_lineno))
                pass
        #end while
    except Exception as e:
        dbgLog("camportmon global err: "+str(e)+str(sys.exc_traceback.tb_lineno))
        pass
#end camPortMon

def encBitrateSet(bitrate, camIdx=-1):
    """set new bitrate for a specified camera"""
    print "set bitrate....................", bitrate, camIdx
    cameras = camera.getOnCams()
    try:
        camIdx = int(camIdx)
    except:
        camIdx = -1
    if(camIdx>=0):
        print "ONE CAMERA!!!!!!!!"
        camID = cameras.getCamID(camIdx)
        if(camID):#camera is still enabled
            # set bitrate
            if('enctype' in cameras[camID] and cameras[camID]['enctype']=='td_cube'):
                #this is a teradek cube, set bitrate accordingly
                try:
                    val = int(bitrate)
                    if(val>=1000 and val<=5000): #valid bitrate
                        bpsBitrate = val*1000 #convert bitrate to bps (for teradek)
                        tdSetBitrate(camID,bpsBitrate)
                except:
                    pass
        #end if camID
        else:
            return
    else:#camera wasn't specified - set bitrate for all cameras
        for camID in cameras:
            print "......\n......\n......\nsetting bitrate for ", cameras[camID]
            if('enctype' in cameras[camID] and cameras[camID]['enctype']=='td_cube'):
                #this is a teradek cube - set bitrate accordingly
                try:
                    val = int(bitrate)
                    if(val>=1000 and val<=5000): #valid bitrate
                        bpsBitrate = val*1000 #convert bitrate to bps (for teradek)
                        tdSetBitrate(camID,bpsBitrate)
                except:
                    pass
        #end for camID in cameras
    #end if camIdx>0 ... else
#end encBitrateSet

#starts mp4/hls capture on all cameras
def encStartCap(quality):
    enc.statusSet(enc.STAT_START)
    # make sure ffmpeg's and segmenters are off:
    os.system("killall -9 "+c.segname+" 2>/dev/null")
    os.system("killall -9 "+c.ffname+" 2>/dev/null")
    cameras = camera.getOnCams()
    try:
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
        for devID in cameras:
            # # each camera has its own ffmpeg running it, otherwise if 1 camera goes down, all go down with it
            # if('format' in cameras[devID] and 'devID'=='blackmagic'): #format is explicitly specified for this camera (usually for blackmagic)
            #   ffstreamIn = c.ffbin+" -y -f "+cameras[devID]['format']+" -i "+cameras[devID]['url']
            #   ffstreamIn += " -codec copy -f h264 udp://127.0.0.1:221"+str(streamid)
            #   ffstreamIn += " -codec copy -f mpegts udp://127.0.0.1:220"+str(streamid)
            #   ffstreamIns.append(ffstreamIn)
            # for saving multiple mp4 files, one ffmpeg instance can accomplish that
            camID = str(cameras[devID]['idx'])
            dskMP4  = str(dskMP4base+int(camID)) #ffmpeg reads from this UDP port and writes mp4 to disk
            dskHLS  = str(dskHLSbase+int(camID)) #m3u8 segmenter reads from this UDP port and writes segments to disk
            camMP4  = str(camMP4base+int(camID)) #ffmpeg captures rtsp from camera and outputs h.264 stream to this port
            camHLS  = str(camHLSbase+int(camID)) #ffmpeg captures rtsp form camera and outputs MPEG-TS to this port
            ffmp4Ins +=" -i udp://127.0.0.1:"+dskMP4
            if(len(cameras)<2):
              # there is only one camera - no need to set camID for file names
              fileSuffix = ""
            else: #multiple cameras - need to identify each file by camID
              fileSuffix = camID

            ffmp4Out +=" -map "+camID+" -codec copy "+c.wwwroot+"live/video/main"+fileSuffix+".mp4"
            # this is HLS capture (segmenter)
            segmenters[devID] = c.segbin+" -p -t 1s -S 1 -B segm_"+fileSuffix+"st -i list"+fileSuffix+".m3u8 -f "+c.wwwroot+"live/video 127.0.0.1:"+dskHLS
            if(quality=='low' and 'preview' in cameras[devID]):
                camURL = cameras[devID]['preview']
            else:
                camURL = cameras[devID]['url']
            # this ffmpeg instance captures stream from camera and redirects to mp4 capture and to hls capture
            ffcaps[devID] = c.ffbin+" -rtsp_transport udp -i "+camURL+" -codec copy -f h264 udp://127.0.0.1:"+camMP4+" -codec copy -f mpegts udp://127.0.0.1:"+camHLS
            # each camera also needs its own port forwarder
            portIns[int(camMP4)]={
                'forwarding'  :True,
                'status'      :'live',
                'type'        :'mp4',
                'camera'      :devID,
                'input'       :int(camMP4),
                'output'      :int(dskMP4),
                'active'      :True
                }
            portIns[int(camHLS)]={
                'forwarding'  :True,
                'status'      :'live',
                'type'        :'hls',
                'camera'      :devID,
                'input'       :int(camHLS),
                'output'      :int(dskHLS),
                'active'       :True
                }
            if(not 'portFwd' in tmr):
                tmr['portFwd'] = {}
            tmr['portFwd']['MP4_'+camID] = TimedThread(camPortMon,portIns[int(camMP4)])
            tmr['portFwd']['HLS_'+camID] = TimedThread(camPortMon,portIns[int(camHLS)])
        #end for device in cameras
        # this command will start a single ffmpeg instance to record to multiple mp4 files from multiple sources
        ffMP4recorder = ffmp4Ins+ffmp4Out
        # this starts an ffmpeg instance to simulate blue scren in case the camera kicks off when the event is being stopped
        ffBlue = c.ffbin+" -loop 1 -y -re -i "+c.approot+"/bluescreen.jpg -r 30 -vcodec libx264 -an -shortest -f h264 udp://127.0.0.1:"+str(blueMP4)+" -r 30 -vcodec libx264 -vbsf h264_mp4toannexb -f mpegts udp://127.0.0.1:"+str(blueHLS)
        # start the HLS segmenters and rtsp/rtmp captures
        for devID in segmenters:
            # segmenter
            procMan.padd(name="segment",devID=devID,cmd=segmenters[devID],forceKill=True)
            # ffmpeg RTSP capture
            procMan.padd(name="capture", devID=devID, cmd=ffcaps[devID], keepAlive=True, killIdle=True, forceKill=True)
        #end for dev in segmenters

        # start blue screen simulator
        procMan.padd(cmd=ffBlue,       name="blue",  devID="ALL", keepAlive=True, killIdle = True, forceKill=True)        
        # start mp4 recording to file
        procMan.padd(cmd=ffMP4recorder,name="record",devID="ALL")
    except Exception as e:
        enc.statusSet(enc.STAT_READY)
        dbgLog("START CAP ERR: "+str(e)+str(sys.exc_traceback.tb_lineno))
        pass
#end encStartCap

def encStopCap(force=False):
    """stops the capture, kills all ffmpeg's and segmenters
    force - (optional) force-kill all the processes - makes stopping process faster
    """
    global SHUTDOWN
    try:
        dbgLog("stopping capture... force:"+str(force))
        if(not(enc.code & (enc.STAT_LIVE | enc.STAT_PAUSED))):
            force = True #the encode didn't finish starting or didn't start properly - force shut down everything
        enc.statusSet(enc.STAT_STOP)
        # remove all forwaders
        for port in portIns:
            portIns[port]['forwarding']=False
            portIns[port]['status']='stopped'
        # stop all captures
        cameras = camera.getOnCams()
        dbgLog("stopping segment and capture")
        for devID in cameras:
            procMan.stop(devID=devID,name="segment", force=force)
            procMan.stop(devID=devID,name="capture", force=force)
        #end while
        # wait for processes to stop
        while((procMan.findProc("capture") or procMan.findProc("segment")) and not SHUTDOWN):
            time.sleep(1)
        dbgLog("stopped, forwarding the bluescreen")
        # to stop mp4 recorder need to push blue screen to that ffmpeg first, otherwise udp stalls and ffmpeg produces a broken MP4 file
        # start forwarding blue screen to all the mp4 recorder ports
        if(not 'mp4' in portFwds):
            portFwds['mp4']=[]
        # forward bluescreen OUT port ----> mp4 recorder IN port
        for portNum in portIns:
            port = portIns[portNum]
            if(port['type']=='mp4'):
                portFwds['mp4'].append(port['output'])
        dbgLog("stopping mp4 recorder")
        procMan.stop(devID='ALL',name='record',force=force)
        # wait for the recorder to stop, then kill blue screen forward
        while(procMan.findProc("record") and not SHUTDOWN):
            time.sleep(1)
        dbgLog("mp4 record stopped")
        # kill the blue screen ffmpeg process
        procMan.stop(devID='ALL',name='blue', force=force)
        while(procMan.findProc("blue") and not SHUTDOWN): #wait for bluescreen ffmpeg to stop
            time.sleep(1)
        # remove blue screen forwarders
        portFwds['mp4'] = []
        # delete port forwarding threads (cam OUT ---> disk IN)
        if('portFwd' in tmr):
            for thd in tmr['portFwd']:
                tmr['portFwd'][thd].kill()
    except Exception as e:
        dbgLog("stopcap err: "+str(e)+str(sys.exc_traceback.tb_lineno))
        pass
    enc.statusSet(enc.STAT_READY)
#end encStopCap

def encPauseCap():
    enc.statusSet(enc.STAT_PAUSED)
def encResumeCap():
    enc.statusSet(enc.STAT_LIVE)
#gets status of all encoder devices in the system
def devStatus():
    # list of active encoders
    validTDs = {}
    try:
        teraCopy = copy.deepcopy(encoders)
        print "...................."
        print "...................."
        print teraCopy
        print "...................."
        print "...................."
        myip = get_lan_ip()
        for td in teraCopy:
            if(not(('url_port' in teraCopy[td]) and ('url' in teraCopy[td]))):
                #port or main URL is not specified in this teradek entry - it's faulty
                continue #move on to the next device
            if(not sameSubnet(td,myip)):
                continue #skip encoders that are not on local network
            tdPort = teraCopy[td]['url_port']
            tdURL = teraCopy[td]['url']
            tdAddress = td

            if(not teraCopy[td]['on']): #only ping devices that are offline
                # message that should receive RTSP/1.0 200 OK response from a valid rtsp stream
                msg = "DESCRIBE "+tdURL+" RTSP/1.0\r\nCSeq: 2\r\nAccept: application/sdp\r\nUser-Agent: Python MJPEG Client\r\n\r\n"""
                s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                s.settimeout(2)
                try:
                    s.connect((tdAddress, int(tdPort)))
                    s.send(msg)
                    data = s.recv(1024)
                except Exception as e:
                    data = str(e)
                    dbgLog("devstatus err: "+str(e)+" at "+str(tdAddress)+':'+str(tdPort)+' '+str(sys.exc_traceback.tb_lineno))
                #close the socket
                try:
                    s.close()
                except:
                    #probably failed because couldn't connect to the rtsp server - no need to worry
                    pass
                # make sure the framerate is ok on this device 
                strdata = data.lower().strip()
                print "^^^^^^^^^^^^^^^^^^^^^^^^devStatus data:", strdata
                if(strdata.find('host is down')>-1 or strdata.find('no route to host')>-1):
                    # found a "ghost": this device recently disconnected
                    if(not enc.busy()):
                        #no active encode - remove this device from the list so it doesn't interfere with other ones
                        del encoders[td]                    
                    continue
                if(strdata.find('timed out')>-1): #the connection is down (maybe temporarily?)
                    continue
                #a device is not available (either just connected or it's removed from the system)
                #when connection can't be established or a response does not contain RTSP/1.0 200 OK
                teraCopy[td]['on'] = (data.find('RTSP/1.0 200 OK')>=0)
                if(td in encoders): #this may be false if during the execution of this loop a teradek dropped off the system
                    encoders[td]['on'] = teraCopy[td]['on']

            #if not teracopy
            validTDs[td] = teraCopy[td]
        #end for td in tds
        # save the info about encoders to a file
        f = open(c.tdCamList,"w")
        f.write(json.dumps(validTDs))
        f.close()
    except Exception as e:
        pass
    return validTDs
#end devStatus

def camMonitor():
    # get all cameras that are active
    try:
        # get status of all connected encoders
        tds = devStatus()
        if(not enc.busy()): #when there's no live event, just enable all cameras so that the user will be able to start a live event
            camera.camOff()
            camera.camOn() #enable all available cameras (this will be useful if user wants to hot-swap encoders)
        cams = camera.getOnCams()
        # go through active cameras and make sure they're all online and active
        for td in cams:
            # set the activated camera status to the encoder status
            if(td in encoders and 'on' in encoders[td]):
                camera.camParamSet("on",encoders[td]['on'],camID=td)
            # get local udp ports for this camera
            camMP4 = camMP4base+int(cams[td]['idx'])
            camHLS = camHLSbase+int(cams[td]['idx'])
            # check camera status
            if('state' in cams[td] and cams[td]['state']=='paused'):
                ############
                ## PAUSED ##
                ############
                if(camMP4 in portIns):
                    portIns[camMP4]['status']='paused'
                if(camHLS in portIns):
                    portIns[camHLS]['status']='paused'
                print "paused"
                continue #this camera is paused - no need to check anything else here
            elif('state' in cams[td] and cams[td]['state']=='stopped'):
                #############
                ## STOPPED ##
                #############
                if(camMP4 in portIns):
                    portIns[camMP4]['status']='stopped'
                if(camHLS in portIns):
                    portIns[camHLS]['status']='stopped'
                print "stopped"
                continue #this camera is stopped
            else: #by default assume camera is live
                ############
                ##  LIVE  ##
                ############
                if(camMP4 in portIns):
                    portIns[camMP4]['status']='live'
                if(camHLS in portIns):
                    portIns[camHLS]['status']='live'
                print "live"
            dbgLog("cam: "+str(td))
            if(td in tds):
                dbgLog("details: "+str(tds[td]))
        #end for td in cams
    except Exception as e:
        dbgLog("cammon err: "+str(e)+str(sys.exc_traceback.tb_lineno))
        pass
#end tdMonitor

# looks for teradek cube published through bonjour
def tdFind():
    # encoders are identified by this
    regtype = "_tdstream._tcp"
    # list of devices that are queried on the network, in case there are other matches besides teradek (internal only)
    queried  = []
    # don't bother if a device is unreachable
    timeout  = 5
    # list of devices for which was able to get the info (internal only)
    resolved = []    
    # parses txtRecord into VAR=VALUE format
    def parseStream(txtRecord):
        length = len(txtRecord)
        parts = []
        line = ""
        for i in xrange(length):
            if(ord(txtRecord[i])<27):
                # line ended
                parts.append(line)
                line = ""
            else:
                line += txtRecord[i]
        records = {}
        for line in parts:
            linepart = line.split('=')
            if(len(linepart)>1):
                records[str(linepart[0])] = str(linepart[1])
        return records
    #end extractStream    

    # gets called when device is resolved
    def resolve_callback(sdRef, flags, interfaceIndex, errorCode, fullname, hosttarget, port, txtRecord):
        def query_record_callback(sdRef, flags, interfaceIndex, errorCode, fullname, rrtype, rrclass, rdata, ttl):
            if errorCode == pybonjour.kDNSServiceErr_NoError:
                ipAddr = socket.inet_ntoa(rdata)
                if(not sameSubnet(ipAddr,get_lan_ip())): #ignore encoders with an ip address from a different subnet
                    return
                queried.append(True)
                # found teradek, add it to the list
                # get details about this device
                recs = parseStream(txtRecord)
                if(port!=554): #only explicitly define port if it's something other than 554, i.e. non-standard rtsp
                    strport = ":"+str(port)
                else:
                    strport = ""
                camID = ipAddr

                if(not camID in encoders):
                    encoders[camID] = {}
                    encoders[camID]['on']=False
                    encoders[camID]['enctype']='td_cube'
                # url to the stream, consists of:
                # 'sm' - streaming method/protocol (e.g. rtsp)
                # ipAddr - ip address of the encoder (e.g. 192.168.1.100)
                # strport - port of the stream (e.g. 554)
                # 'sn' - stream name (e.g. stream1)
                streamURL = recs['sm'].lower()+'://'+ipAddr+strport+'/'+recs['sn']
                # check if this is a preview or a full rez stream
                if(recs['sn'].lower().find('quickview')>=0):# this is a preview stream
                    encoders[camID]['preview']=streamURL
                    encoders[camID]['preview_port']=str(port)
                else: # this is full resolution stream
                    encoders[camID]['url']=streamURL
                    encoders[camID]['url_port']=str(port)
        #end query_record_callback
        if errorCode != pybonjour.kDNSServiceErr_NoError:
            return
        query_sdRef = pybonjour.DNSServiceQueryRecord(interfaceIndex = interfaceIndex,  fullname = hosttarget, rrtype = pybonjour.kDNSServiceType_A, callBack = query_record_callback)
        try:
            while not queried:
                ready = select.select([query_sdRef], [], [], timeout)
                if query_sdRef not in ready[0]:
                    break
                pybonjour.DNSServiceProcessResult(query_sdRef)
            else:
                queried.pop()
            query_sdRef.close()
        except:
            pass
        resolved.append(True)
    #end resolve_callback

    def browse_callback(sdRef, flags, interfaceIndex, errorCode, serviceName, regtype, replyDomain):
        if (errorCode != pybonjour.kDNSServiceErr_NoError) or not (flags & pybonjour.kDNSServiceFlagsAdd): 
            # error or the service was removed
            return
        try:
            resolve_sdRef = pybonjour.DNSServiceResolve(0, interfaceIndex, serviceName, regtype, replyDomain, resolve_callback)
            while not resolved:
                ready = select.select([resolve_sdRef], [], [], timeout)
                if resolve_sdRef not in ready[0]:
                    break
                pybonjour.DNSServiceProcessResult(resolve_sdRef)
            else:
                resolved.pop()
            resolve_sdRef.close()
        except:
            pass
    #end browse_callback

    try:
        browse_sdRef = pybonjour.DNSServiceBrowse(regtype = regtype, callBack = browse_callback)
        start_time = time.time()
        now = start_time
        try:
            while ((now-start_time)<2):#look for encoders for 3 seconds, then exit
                ready = select.select([browse_sdRef], [], [], 0.1)
                if browse_sdRef in ready[0]:
                    pybonjour.DNSServiceProcessResult(browse_sdRef)
                now = time.time()
        except:
            pass
    except:
        pass
    finally:
        browse_sdRef.close()
#end findTeradek

#extracts a specified paramater from the response string and gets its value
# function assumes response in this format:
# VideoInput.Info.1.resolution = 1080p60
# VideoEncoder.Settings.1.framerate = 30
# etc...
def tdGetParam(response,parameter):
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

def tdCamMon():
    """ checks parameters of the teradek cubes """
    devCopy = copy.deepcopy(encoders)
    # dbgLog("cam con mon ENCODERS:"+str(devCopy))
    try:
        myip = get_lan_ip()
        for dev in devCopy:
            print "checking..............................", dev
            if(enc.code & enc.STAT_SHUTDOWN): #exit immediately if there's a shutdown going on
                print "shutting down camconmon"
                return
            if(devCopy[dev]['enctype']!='td_cube'):
                print "not a cube"
                continue
            if(not sameSubnet(dev,myip)):
                print "subnet mismatch camconmon"
                try: # if the encoder is from a different ip group - don't bother recording it
                    del encoders[dev]
                except:
                    pass
                continue #skip encoders that are not on local network
            if(not (dev in tdSession and tdSession[dev])):
                tdLogin(dev)
            if(not (dev in tdSession)):#could not log in to the device - most likely it's gone from the network, set its status to off
                if((dev in encoders) and not enc.busy()):
                    print "encoder off!!!!!!!!!!!!!!!!!!!!!!!!!!",encoders[dev]
                    if((dev in encoders) and not enc.busy()):
                        if(encoders[dev]['on']): #the encoder was set as active - perhaps it's a temporary glitch - set ON status as False for now
                            encoders[dev]['on']=False
                        else:#the encoder was already inactive - most likely it dropped off the network - remove it from the system
                            del encoders[dev]
                else:
                    print "dev not in encoders??????", dev in encoders
                    print "enc busy??????????", enc.busy()
                continue
            url = "http://"+dev+"/cgi-bin/api.cgi?session="+tdSession[dev]
            url2= "&command=get&q=VideoInput.Info.1.resolution&q=VideoEncoder.Settings.1.framerate&q=VideoEncoder.Settings.1.bitrate"
            response = pu.io.url(url+url2, timeout=15)
            if(not response): #didn't get a response - timeout?
                dbgLog("no response from: "+url+url2)
                if(dev in tdSession):
                    del tdSession[dev]
                continue 
            resolution = tdGetParam(response,'resolution')
            framerate = tdGetParam(response,'framerate')
            bitrate = tdGetParam(response,'bitrate') #this is in bps
            dbgLog("res: "+str(resolution)+" frm: "+str(framerate)+" brt: "+str(bitrate))
            if(bitrate):#convert bitrate to kbps
                try:
                    intBitrate = int(bitrate)
                    intBitrate = int(intBitrate / 1000)
                except:
                    intBitrate = False
                    pass
            # set bitrate for the settings page
            camera.camParamSet('bitrate',intBitrate,camID=dev)
            if(resolution.strip().lower()=='vidloss' or resolution.strip().lower()=='unknown'):
                resolution = 'N/A'
                # lost camera
                # set status bit to NO CAMERA
                enc.statusSet(enc.STAT_NOCAM,overwrite=((enc.code & enc.STAT_READY)>0))#overwrite when encoder is ready
            else:
                if(enc.code == enc.STAT_NOCAM): #status was set to NOCAM, when camera returns it should be reset to ready
                    enc.statusSet(enc.STAT_READY)
                else:#encoder status was something else (e.g. live + nocam) now simply remove the nocam flag
                    enc.statusUnset(enc.STAT_NOCAM)
            # set the camera resolution for displaying on the web page
            camera.camParamSet('resolution',resolution,camID=dev)
            try:
                encoders[dev]['resolution']=resolution
                encoders[dev]['framerate']=framerate
                encoders[dev]['bitrate'] = intBitrate
            except:#may fail if the device was removed from the encoders list
                pass
            # if(framerate and int(framerate)>30):#frame rate was changed ??
            #     TimedThread(tdSetFramerate(dev))
    except Exception as e:
        dbgLog("camconmon ERRRR: "+str(e)+" "+str(sys.exc_traceback.tb_lineno))
#end tdCamMon

def tdLogin(td):
    url = "http://"+td+"/cgi-bin/api.cgi"
    # did not connect to the cube previously - login first
    response = pu.io.url(url+"?command=login&user=admin&passwd=admin",timeout=15)
    # get session id
    if(not response):
        return False
    response = response.strip().split('=')
    if(response[0].strip().lower()=='session' and len(response)>1):#login successful
        tdSession[td] = response[1].strip()
    else:#could not log in - probably someone changed username/password
        return False
#end tdLogin

def tdSetBitrate(td,bitrate):
    try:
        print "tdSetBitrate"
        if(not td in encoders):
            return
        url = "http://"+td+"/cgi-bin/api.cgi"
        if(not (td in tdSession and tdSession[td])):
            tdLogin(td)
        #end if not tdSession
        print "logged in: ", tdSession[td]
        url +="?session="+tdSession[td]

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
        print "BRRRRRRRRRRRRRRRRRRRRRRRRRRRR: ", e, sys.exc_traceback.tb_lineno
#end tdSetBitrate
# checks if teradek framerate is above 30 
# sets it appropriately, if it is
def tdSetFramerate(td):
    try:
        if(not td in encoders):
            return
        url = "http://"+td+"/cgi-bin/api.cgi"
        if(not (td in tdSession and tdSession[td])):
            tdLogin(td)
        #end if not tdSession
        print "logged in: ", tdSession[td]
        #######################################
        # try to get existing framerate first #
        #######################################
        # get all settings
        url +="?session="+tdSession[td]
        # get current framerate
        # whether it is native
        # and allowed framerates:
        resp = pu.io.url(url+"&command=get&q=VideoEncoder.Settings.1.framerate&q=VideoEncoder.Settings.1.use_native_framerate&q=VideoInput.Capabilities.1.framerates")
        # put them in an array

        # settings = resp.split("\n")
        # print "settings: ", settings
        # # go through each one looking for framerate
        framerate = False 
        framerates = [] #list of allowed frame rates with this camera
        nativeframe = False #whether the TD is using a native framerate
        framerate = tdGetParam(resp,"framerate")
        framerates = tdGetParam(resp,"framerates")
        nativeframe = tdGetParam(resp,"use_native_framerate")
        if(not framerates):
            return
        framerates = framerates.split(',')

        # got framerate - now make sure it's <=30
        if(not framerate or framerate<=30):
            print "STATUS QUO!!!!!!!!!!!!!!!!!!!!!!!! ", framerate
            return #could not get frame rate or it's normal 
        #############################
        # need to change frame rate #
        #############################
        print "framerate TOO HIGH!!!!!!!!!!!: ", framerate
        # find the framerate closest to 30 from the available ones
        newrate = framerate >> 1 #by default just half it...
        for rate in framerates:
            if(int(rate)<=30): #found the first framerate that will work without problems
                newrate = rate
                break
        print "NEW RATE:.....................................", newrate
        setcmd = "&VideoEncoder.Settings.1.framerate="+str(newrate)
        savecmd = "&q=VideoEncoder.Settings.1.framerate"
        if(nativeframe):#currently native frame rate is set - need to reset it manually
            setcmd +="&VideoEncoder.Settings.1.use_native_framerate=0"
            savecmd = "&q=VideoEncoder.Settings.1.use_native_framerate"
        # set the frame rate
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
        print "FRAMERRRRRRRRRRRRRRRRRRRRRRR: ", e, sys.exc_traceback.tb_lineno
        return
############### end teradek management ################

############### matrox monarch management ###############
def mtCamMon():    
    """ monitors camera connected to matrox monarch, gets resolution/bitrate updates"""
    encCopy = copy.deepcopy(encoders)
    myip = get_lan_ip()
    for dev in encCopy:
        print "checking..............................", dev
        if(enc.code & enc.STAT_SHUTDOWN): #exit immediately if there's a shutdown going on
            print "shutting down mtCamMon"
            return
        if(encCopy[dev]['enctype']!='mt_monarch'):
            print "not a monarch"
            continue
        if(not sameSubnet(dev,myip)):
            print "subnet mismatch mtCamMon"
            try: # if the encoder is from a different ip group - don't bother processing it
                del encoders[dev]
            except:
                pass
            continue #skip encoders that are not on local network
        # get parameters of the encoder:
        params = mtGetParams(dev)
        if(not params): #the encoder dropped off?
            if(dev in encoders and not enc.busy()): #device is still listed in the array and there is no live event
                if(encCopy[dev]['on']): #status was set to active, encoder was working fine
                    encoders[dev]['on']=False #set it to inactive (perhaps this is a temporary downtime)
                else:#encoder was already inactive - most likely it dropped off the network for good
                    del encoders[dev] #remove the device from the list
            continue
        #end if not params
        if(params['rtsp_url'] and params['rtsp_port']):
            encoders[dev]['url'] = params['rtsp_url']
            encoders[dev]['url_port'] = params['rtsp_port']
        if(not params['inputResolution']): #no camera detected
            resolution = 'N/A'
            # lost camera
            # set status bit to NO CAMERA
            enc.statusSet(enc.STAT_NOCAM,overwrite=((enc.code & enc.STAT_READY)>0))#overwrite when encoder is ready
        else:#camera detected
            resolution = params['inputResolution']
            if(enc.code == enc.STAT_NOCAM): #status was set to NOCAM, when camera returns it should be reset to ready
                enc.statusSet(enc.STAT_READY)
            else:#encoder status was something else (e.g. live + nocam) now simply remove the nocam flag
                enc.statusUnset(enc.STAT_NOCAM)
        encoders[dev]['resolution'] = resolution
        camera.camParamSet('resolution',resolution,camID=dev)
    #end for dev in encCopy
#end mtConMon

def mtParseURI(mtURL):
    """extracts ip address and port from a uri.
    the url is usually in this format: "http://X.X.X.X:PORT/"
    e.g. from http://192.168.1.103:5953/
    will return 192.168.1.103 and 5953"""
    addr  = ""
    parts = []
    ip    = False
    parts = mtURL.split('/')
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
#end mtParseURI

# extracts the following parameters from the monarch
# rtsp url (if specified)
# video input resolution (if present)
# stream settings:
#   resolution
#   framerate
#   bitrate
def mtGetParams(mtIP):
    params = {
        "rtsp_url"          : False,
        "rtsp_port"         : False,
        "inputResolution"   : False,
        "streamResolution"  : False,
        "streamFramerate"   : False,
        "streamBitrate"     : False
        }
    # for now the only way to extract this information is using the monarch home page (no login required for this one)
    # when they provide API, then we can use that
    mtPage = pu.io.url("http://"+str(mtIP)+"/Monarch", timeout=15)
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
    if(posStart>0 and posStop>0 and posStop>posStart):
        rtspURL = mtPage[posStart:posStop] #either this is blank or it has the url
        if(len(rtspURL)>10 and rtspURL.startswith("rtsp://")):
            # got the url
            params['rtsp_url']=rtspURL
            # extract the port
            ip, port = mtParseURI(rtspURL)
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
    if(posStart>0 and posStop>0 and posStop>posStart):
        inRes = mtPage[posStart:posStop] #either contains "No Video Input" or something to the effect of "1920x1080p, 60 fps"
        if(inRes.find(",")>0 and inRes.find("fps")>0): #video source present
            # get resolution
            resParts = inRes.lower().strip().split(',')
            # now first part contains the resolution (e.g. 1280x720p)
            resolution = resParts[0].strip().split('x')
            if(len(resolution)>1):
                resolution = resolution[1].strip() #now contains "720p"
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
        if(streamText.find(',')>0 and streamText.find('fps')>0 and len(streamText.split(','))>2): #stream information contains at least resolution and frame rate
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
#end mtGetParams



# looks for monarch HD on the network (assumes that it's sending NOTIFY to 239.255.255.0 multicast address)
def mtFind():
    global SHUTDOWN
    attempts = 3 #try to find a monarch 3 times, then give up
    monarchs = []
    print "mtfind........."
    while(attempts>0 and len(monarchs)<1 and not SHUTDOWN):
        #the Search Target for monarch is:
        #to find ALL ssdp devices simply enter ssdp:all as the target
        monarchs  = pu.ssdp.discover("MonarchUpnp",timeout=5)
        attempts -= 1
    if(SHUTDOWN or (enc.code & enc.STAT_SHUTDOWN)):
        return
    if(len(monarchs)>0):
        print "found ", len(monarchs)
        myip = get_lan_ip()
        # found at least one monarch 
        for devLoc in monarchs:
            try:
                dev = monarchs[devLoc]
                devIP, devPT = mtParseURI(dev.location)
                print "dev: ", devIP, devPT
                if(not sameSubnet(devIP,myip)):
                    print "subnet mismatch, mtfind: ", devIP, myip
                    continue #devices on different networks are ignored
                if(devIP and devPT):
                    params = mtGetParams(devIP)
                    if(params['rtsp_url'] and params['rtsp_port']):
                        if(not devIP in encoders):
                            encoders[devIP] = {'on':False}
                        encoders[devIP]['enctype']='mt_monarch'
                        encoders[devIP]['url'] = params['rtsp_url']
                        encoders[devIP]['url_port'] = params['rtsp_port']
            except Exception as e: #may fail if the device is invalid or doesn't have required attributes
                print e, sys.exc_traceback.tb_lineno
        #end for devLoc in monarchs
    #end if monarchs>0
    else:
        print "did not find monarchs!!!!!"
        # devIP = "192.168.0.101"
        # params = mtGetParams(devIP)
        # if(not devIP in encoders):
        #     encoders[devIP] = {'on':False}
        # encoders[devIP]['enctype']='mt_monarch'
        # encoders[devIP]['url'] = params['rtsp_url']
        # encoders[devIP]['url_port'] = params['rtsp_port']
#end mtFind
############# end matrox monarch management #############

# finds cpu usage by all processes with the same pgid
def getCPU(pgid=0,pid=0):
    totalcpu = 0
    if(pgid):
        #list of all processes in the system
        proclist = psutil.get_process_list()
        for proc in proclist:
            try:#try to get pgid of the process
                foundpgid = os.getpgid(proc.pid)
            except:
                continue #skip processes that do not exist/zombie/invalid/etc.
            if(pgid==foundpgid):#this process belongs to the same group
                try: #can use the same function recursively to get cpu usage of a single process, but creates too much overhead
                    ps = psutil.Process(proc.pid)
                    totalcpu += ps.get_cpu_percent(interval=0.1)
                except:
                    continue
            #if pgid==foundpgid
        #for proc in proclist
    elif(pid):#looking for cpu usage of one process by pid
        try:
            ps = psutil.Process(pid)
            totalcpu = ps.get_cpu_percent(interval=0.1)
        except Exception as e:
            pass
    #get total cpu for a process
    return totalcpu
#end getCPU
def sockRead(udpAddr="127.0.0.1", udpPort=2224, timeout=1, sizeToRead=1):
    sock = socket.socket(socket.AF_INET, # Internet
                         socket.SOCK_DGRAM) # UDP
    sock.settimeout(timeout) #wait for 'timeout' seconds - if there's no response, server isn't running
    #bind to the port and listen
    try:
        sock.bind((udpAddr, udpPort))
        data, addr = sock.recvfrom(sizeToRead)
    except Exception as e:
        #failed to bind to that port
        data = -1
    #close the socket
    try:
        sock.close()
    except:
        #probably failed because bind didn't work - no need to worry
        pass
    return data
#end sockRead

# gets ports set in the config file
def getPorts():
    ports = {"HLS":65535,"FFM":65535,"CHK":65535}
    contents = pu.disk.file_get_contents("/tmp/pxpports")
    if not contents:
        return ports
    for line in contents.split("\n"):
        parts = line.split("=")
        if len(parts)>1:
            if(parts[0] in ports):
                ports[parts[0]] = int(parts[1])
    return ports

class procmgr():
    def __init__(self):
        self.procs = {} #processes in the system
    # look for process by name (returns list of idx'es of processes that have this name)
    # @param str procName - name of the process to find
    # @return mixed - list of IDX's of processes with this name or False if no process found
    def findProc(self, procName):
        procs = self.procs.copy()
        foundProcs = []
        for idx in procs:
            if(procs[idx]['name']==procName):
                foundProcs.append(idx)
        if(len(foundProcs)>0):
            return foundProcs
        return False
    # get the numeric index of a process based on its name and device it is associated with
    def getProcIndex(self,devID,name):
        procs = self.procs.copy()
        foundIdx = -1 #if the process could not be found, return -1
        for idx in procs:
            proc = procs[idx]
            if(proc['name']==name and proc['dev']==devID):
                foundIdx = idx
                break #to speed up the function, break out of the loop as soon as the process is found
        return foundIdx
    #end getProcIndex

    #############################################################
    # goes through the process list and kills those scheduled for termination
    def killer(self):
        killList = self.procs.copy()
        # go through the queue and try to kill all processes that are scheduled for termination
        for idx in killList:
            victim = killList[idx]
            if(not idx in self.procs or victim['run']):
                continue #this process was just killed or it isn't scheduled for termination
            #increment kill attempt count
            print "killing: ", self.procs[idx]
            self.procs[idx]['killcount'] += 1
            #try to kill it
            # psKill(pid=victim['pid'], force=victim['forcekill'])
            psKill(pid=victim['pid'],ref=victim['ref'], force=victim['forcekill'])
            if(idx in self.procs and not psOnID(pid=victim['pid'])):
                #success - the process id dead!
                if(victim['resume']): #the process should be restarted
                    self.procs[idx]['run']=True #mark it for startup
                    self.procs[idx]['resume']=False #reset the resume flag
                else:#the process was terminated for good
                    self.premove(idx) #remove it from the process list
            elif(idx in self.procs and self.procs[idx]['killcount']>2): #the process didn't die after 3 attempts - force kill next time
                self.procs[idx]['forcekill'] = True
        #for idx in killList...
    #end killer
    # this is the main function that monitors/manages processes
    def manager(self):
        try:
            procs = self.procs.copy()
            print "------------------------------------------"
            for idx in procs:
                proc = procs[idx]
                print idx, proc['name'], proc['alive'], proc['cpu'], proc['pid'], proc['keepalive']
                if(proc['run']): #this process should be alive
                    if((not proc['alive']) and proc['keepalive']): #process is dead but needs to be (re)started
                        self._start(idx)
                    elif(proc['alive'] and proc['cpu']<0.1 and proc['killidle']): #process is alive but stalled and needs to be killed
                        self.stop(procidx=idx,restart=True)
                        pass
                    elif(not (proc['alive'] or proc['keepalive'])): #the process died, and shouldn't be kept alive - remove it from the list
                        self.premove(idx)
                else: #process is scheduled for termination - self.killer will take care of it
                    pass
            print "------------------------------------------"
        except Exception as e:
            print "mgr err: ",e,sys.exc_traceback.tb_lineno
    #end manage
    #############################################################

    #monitors the process and sets various parameters (e.g. cpu usage, whether it's alive or not, etc.)
    def monitor(self):
        try:
            procs = self.procs.copy()
            for idx in procs:
                proc = procs[idx]
                # print proc['name'],"|",proc['cpu'],"|", proc['dev'],"|", proc['pid'],"|", proc['alive'], "|", proc['run']
                alive = psOnID(pid=proc['pid']) #check if the process is alive
                cpu = getCPU(pid=proc['pid']) #get cpu usage
                if(idx in self.procs):
                    self.procs[idx]['cpu'] = cpu
                    self.procs[idx]['alive'] = alive
                    self.procs[idx]['run'] = self.procs[idx]['run'] and not (enc.code & enc.STAT_READY)
        except Exception as e:
            print "monitor err: ", e, sys.exc_traceback.tb_lineno
    # add a new process and starts it
    # @param str cmd        - execute this command to start the process
    # @param str name       - process nickname (e.g. segmenter)
    # @param str devID      - device id associated with this process (e.g. encoder IP address)
    # @param bool keepAlive - restart the process if it's dead
    # @param bool killIdle  - kill the process if it's idle
    # @param bool forceKill - whether to force-kill the process (e.g. send SIGKILL instead of SIGINT)
    def padd(self,cmd,name,devID,keepAlive=False,killIdle=False,forceKill=False):
        idx = 0 #the index of the new process
        procs = self.procs.copy()
        #find the next available index
        for pidx in procs:
            if(pidx>=idx):
                idx = pidx+1
        #add the process to the array of processes
        self.procs[idx] = { #new process idx is just an increment of the last one
            'cmd'       : cmd,
            'name'      : name,
            'dev'       : devID,
            'keepalive' : keepAlive,
            'killidle'  : killIdle,
            'forcekill' : forceKill,
            'pid'       : False,    # until the process starts - pid is false
            'ref'       : False,    # process reference is also false until it's started
            'alive'     : False,    # whether this process is alive or not
            'cpu'       : 0,        # cpu usage
            'run'       : True,     # process will be killed when this is set to False
            'killcount' : 0,        # number of times the process was attempted to stop
            'resume'    : False     # this will be set to true when process is being killed but needs to restart
            }
        print " added:::::::::::::::: ",idx, self.procs[idx]
        # start the process as soon as it's added
        self._start(idx)
    #end padd

    # remove process from the list 
    def premove(self,procidx):
        if(procidx in self.procs):
            del self.procs[procidx]
    #end premove
    # starts a process from its command and sets the pid/ref accordingly
    def _start(self,procidx):
        if(not procidx in self.procs):
            return False
        cmd = self.procs[procidx]['cmd']
        # start the process
        ps = sb.Popen(cmd.split(' '),stderr=FNULL,stdout=FNULL)
        # get its pid
        self.procs[procidx]['pid']=ps.pid
        # get the reference to the object (for communicating/killing it later)
        self.procs[procidx]['ref']=ps
        #set these 2 variables to make sure it doesn't get killed by the next manager run
        self.procs[procidx]['alive']=True 
        self.procs[procidx]['cpu']=100
        self.procs[procidx]['resume']=False
    #end start
    # sets the RUN status of the process to false, indicating this process is to be killed
    # @param int [devID] - id of the device associated with this process
    # @param str [name]  - name of the process to stop
    # @param int [procidx] - numeric id of the process (if previous two arguments were not specified)
    # @param bool [restart] - whether to restart this process once it's killed
    # @param bool [force] - to force stop the process (regardless of its current flag setting) 
    def stop(self,devID=0,name=0,procidx=-1,restart=False,force=False):
        if(devID and name):
            idx = self.getProcIndex(devID,name)
        else:
            idx = procidx
        if(idx in self.procs):
            self.procs[idx]['forcekill'] = force
            self.procs[idx]['run'] = False
            self.procs[idx]['resume'] = restart
    #end stop
#end procmgr CLASS

#finds a gap in the sorted list of integers
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
# print gap(arr,0,count(arr)-1)


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
        ref.communicate('q')
        ref.communicate('')
    timeout += time.time()
    #continue trying to kill it until it's dead or timeout reached
    while(psOnID(pid=pid,pgid=pgid) and ((timeout-time.time())>0)):
        try:
            dbgLog("---------------PROC ALIVE "+str(pid))
            if(ref):#this is the proper way to stop a process opened with Popen
                if(force):
                    ref.kill()
                else:
                    os.system("kill -15 "+str(pid))
                t = TimedThread(comm,(ref,)) #same as ref.communicate()
                if(not force):
                    time.sleep(1)
            else:#no reference was specified - just send the signal to the pid
                if(force): #forcing a quit - send kill (-9)
                    sigToSend = signal.SIGKILL
                else:#gentle quit, sigint
                    sigToSend = signal.SIGINT
                if(pgid):#for group kills, signal needs to be sent to the entire group (parent+children) otherwise there will be zombies
                    os.killpg(pgid, sigToSend)
                elif(pid):
                    os.kill(pid,sigToSend)
            time.sleep(1)
        except Exception as e:
            dbgLog("kill err::::::::::::::::::"+str(e)+str(sys.exc_traceback.tb_lineno))
            pass
    #end while psOnID
    if(psOnID(pid=pid,pgid=pgid)):
        dbgLog("????????????did not kill?????? try again!!!!!")
        # exited loop on timeout - process is still alive, try to kill the process again with a SIGKILL this time
        try:
            if(ref):
                ref.kill()
                time.sleep(0.5)
                t = TimedThread(comm,(ref,)) #same as ref.communicate()
            elif(pid):
                os.kill(pid, signal.SIGKILL)
            elif(pgid):
                os.killpg(pgid, signal.SIGKILL)
        except:
            pass
    time.sleep(1) #wait for a bit
    if(psOnID(pid=pid,pgid=pgid)):
        # nothing has worked, last resort - kill this monkey!!!
        try:
            if(ref):
                ref.send_signal(signal.SIGHUP)
                time.sleep(0.5)
                t = TimedThread(comm,(ref,)) #same as ref.communicate
            elif(pgid):
                os.killpg(pgid, signal.SIGHUP)
            elif(pid):
                os.kill(pid,signal.SIGHUP)
        except:
            pass
#checks if process is on (By name)
def psOn(process):
    if (platform.system()=="Windows"):    #system can be Linux, Darwin
        #get all the processes for windows matching the specified one:
        cmd = "tasklist | findstr /I "+process
        #result of the cmd is 0 if it was successful (i.e. the process exists)
        return os.system(cmd)==0

    procs = psutil.get_process_list() #get all processes in the system
    for proc in procs:
        try:#try to get command line for each process
            ps  = psutil.Process(proc.pid)
            cmd = ' '.join(ps.cmdline)
            # see if this command line matches
            if(cmd.find(process)>=0):
                return True
        except:
            continue #skip processes that do not exist/zombie/invalid/etc.
    return False

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
    except:
        return False
    return psOn
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

# try to turn on the cameras until at least one is connected
def turnOnCams():
    global SHUTDOWN
    cams = 0
    enc.statusSet(enc.STAT_CAM_LOADING)
    while(cams<1 and not SHUTDOWN):
        try:
            time.sleep(1) #wait to make sure encoders get detected
            camera.camOn()
            cams = len(camera.getOnCams())
        except Exception as e:
            print e, sys.exc_traceback.tb_lineno
            pass
    enc.statusSet(enc.STAT_READY)
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
                if(dataParts[0]=='RMF'): #remove file
                    rmFiles.append(dataParts[1])
                    nobroadcast = True
                if(dataParts[0]=='RMD'): #remove directory
                    rmDirs.append(dataParts[1])
                    nobroadcast = True
                if(dataParts[0]=='STR'): #start encode
                    if(len(dataParts)>1):
                        encStartCap(dataParts[1])
                    else:
                        encStartCap()
                    nobroadcast = True
                if(dataParts[0]=='STP'): #stop encode
                    encStopCap()
                    nobroadcast = True
                if(dataParts[0]=='PSE'): #pause encode
                    encPauseCap()
                    nobroadcast = True
                if(dataParts[0]=='RSM'): #resume encode
                    encResumeCap()
                    nobroadcast = True
                if(dataParts[0]=='BTR' and len(dataParts)>2): #change bitrate
                    # data is in format BTR|<bitrate>|<camID>
                    encBitrateSet(dataParts[1],dataParts[2])
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

enc = encoder()
dbgLog("starting...")
#make sure there is only 1 instance of this script running
me = singleton.SingleInstance()
tmr = {}
procMan = procmgr()
try:
    # remove old encoders from the list, the file will be re-created when the service finds encoders
    os.remove(c.tdCamList)
    # remove cameras
    camera.camOff()
except:
    pass

# process monitor - gets various statuses
tmr['procmon']      = TimedThread(procMan.monitor,period=0.5)
# process manager - starts/stops processes
tmr['procman']      = TimedThread(procMan.manager,period=5)
# process killer  - terminates processes stopped by the manager
tmr['prockil']      = TimedThread(procMan.killer,period=3)

# set up messages(tags) queue manager
# this manages all socket communication (e.g. broadcasting new tags, sennds start/stop/pause/resume messages to tablets)
tmr['BBQ']          = TimedThread(bbqManage,period=0.1)

# start a watchdog timer
# sends a periodic 'kick' to the watchdoge on the clients - to make sure socket is still alive
tmr['dogeKick']     = TimedThread(kickDoge,period=30)

# register pxp on bonjour service
tmr['bonjour']      = TimedThread(pubBonjour)

# look for teradek cube's on bonjour
tmr['tdFind']       = TimedThread(tdFind,period=10)
# timer checks if camera is connected (simply checks resolution/bitrate)
tmr['tdCamMon']     = TimedThread(tdCamMon,period=3)

#looks for matrox Monarch HD using SSDP (a UPnP service)
tmr['mtFind']       = TimedThread(mtFind,period=10)

tmr['mtCamMon']     = TimedThread(mtCamMon,period=2) #monitor camera connected to a matrox monarch

tmr['camMonitor']   = TimedThread(camMonitor,period=10) #pinging teradek too often causes it to fall off after ~30 minutes

# start deleter timer (deletes files that are not needed/old/etc.)
tmr['delFiles']     = TimedThread(deleteFiles,period=2)

tmr['cleanupEvts']  = TimedThread(removeOldEvents,period=10)
#start the threads for forwarding the blue screen to udp ports (will not forward if everything is working properly)
tmr['fwdMP4'] = TimedThread(portFwd,(blueMP4,'mp4'))
# tmr['fwdHLS'] = TimedThread(portFwd,(blueHLS,'hls'))

#register what happens on ^C:
signal.signal(signal.SIGINT, pxpCleanup)

# after everything was started, wait for cameras to appear and set them as active
tmr['startcam']     = TimedThread(turnOnCams)
# writes out the pxp encoder status to file (for others to use)
tmr['pxpStatusSet'] = TimedThread(enc.statusWrite,period=1)
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
        # dbgLog("ERROR IN MAIN???"+str(e)+str(sys.exc_traceback.tb_lineno))
        print "MAIN ERRRRR????????? ",e
        print sys.exc_traceback.tb_lineno
