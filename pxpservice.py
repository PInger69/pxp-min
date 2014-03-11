#!/usr/bin/python
from twisted.internet import reactor, protocol, task
from twisted.protocols import basic
from tendo import singleton
from datetime import datetime as dt
from uuid import getnode as getmac
from tt import TimedThread
import camera, constants as c, copy, json, os, psutil, platform, pxp, pybonjour, select, signal, socket, subprocess as sb, time

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
#teradek devices found through bonjour
# in this format: 
# teradeks = {
#     '192.168.1.153':{
#         'preview'     :'rtsp://192.168.1.153:554/stream1',
#         'preview_port': 554,
#         'url'         :'rtsp://192.168.1.153:554/quickstream',
#         'url_port'    : 554,
#         'on'          : True
#     }
teradeks    = {}
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
teraRefs = {}
#processes being monitored
procMons = {}
# input ports with their statuses.
# e.g.:
# {
#   2270:{
#           forwarding  :True,              #--whether this port is forwarding
#           status      :'paused',          #--status of the camera, data will be forwarded here only when 'live'
#           type        :'mp4',             #--type of stream on this port
#           camera      :'192.168.1.119',   #--devID for this camera
#           input       :22700,             #--where data is being received
#           output      :22000,             #--output port
#           active      :True              #--False if no data is being received on this port, True if receiving data
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
# blue screen will be forwarded to these ports (when they're specified)
blueOut = {'mp4':[],'hls':[]}
blueMP4 = 22500 #ffmpeg output for h.264 stream with blue screen image
blueHLS = 22400 #ffmpeg output for MPEG-TS with blue screen image

dskMP4base = 22000 #ffmpeg listens on this port and writes mp4 to disk (for subsequent cameras, ports will be 22001, 22002...)
dskHLSbase = 22100 #m3u8 segmenter listens on this port and writes segments to disk
camMP4base = 22700 #ffmpeg captures rtsp stream and outputs H.264 stream here
camHLSbase = 22800 #ffmpeg captures rtsp stream and outputs MPEG-TS here
# blueFwds = {'mp4':[],'hls':[]} #add -1 to kill the port fwd process
################## delete files ##################
rmFiles = []
rmDirs = []
bonjouring = [True] #has to be a list to stop bonjour externally
FNULL = open(os.devnull,"w") #for dumping all cmd output using Popen()

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
        dbgLog("DELETING FIL: "+str(fileToRm))
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
        dbgLog("DELETING DIR: "+str(dirToRm))
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
        dbgLog(rmDirs)
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
################ end delete files ################
################## util functions ################
def pxpCleanup(signal, frame):
    dbgLog("terminating services...")
    blueOut['mp4']=[{'input':-1}] #stop forwarding blue screen to mp4 port
    blueOut['hls']=[{'input':-1}] #stop forwarding blue screen to hls port
    bonjouring[0] = False
    #stop camera port forwarding
    for port in portIns:
        portIns[port]['forwarding']=False
    for tm in tmr:
        dbgLog(str(tm)+"...")
        if(type(tmr[tm]) is dict):
            for t in tmr[tm]:
                tmr[tm][t].kill()
        else:
            tmr[tm].kill()
    reactor.stop()
    dbgLog("terminated!")
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

# reads a text file and returns it
def readFile(filename):
    if(not os.path.exists(filename)):
        return 0
    contents = ""
    with open(filename,"rb") as f:
        contents = f.read()
    return contents
#################end util functions ##############
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
    pxpStatus = int(readFile("/tmp/pxpstreamstatus")) #contains status code
    sendStatus = False
    if(pxpStatus != lastStatus):
        sendStatus = encState(pxpStatus)
    lastStatus = pxpStatus
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
                    globalBBQ[client][1].sendLine(myCMDs[cmdID]['data'])
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
#returns true if both ip addresses belong to the same subnet
def sameSubnet(ip1,ip2):
    return ".".join(ip1.split('.')[:3])==".".join(ip2.split('.')[:3])
if os.name != "nt":
    import fcntl
    import struct
    def get_interface_ip(ifname):
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        return socket.inet_ntoa(fcntl.ioctl(s.fileno(), 0x8915, struct.pack('256s',ifname[:15]))[20:24])

def get_lan_ip():
    ip = socket.gethostbyname(socket.gethostname())
    if ip.startswith("127.") and os.name != "nt":
        interfaces = [
            "eth0",
            "eth1",
            "eth2",
            "wlan0",
            "wlan1",
            "wifi0",
            "ath0",
            "ath1",
            "ppp0",
            ]
        for ifname in interfaces:
            try:
                ip = get_interface_ip(ifname)
                break
            except:
                pass
    return str(ip)
#end getlanip
# registers pxp as bonjour service
def pubBonjour():
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
        while bonjouring[0]:
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
#portSet - index of the set of ports where to forward ('hls','mp4'...)
def portFwd(portIN,portSet):
    # portIN = 2240
    try:
        host = '127.0.0.1'          #local ip address
        # portIN = 2250             #where packets are coming from
        # portOUT= 2200             #where packets are forwarded
        sIN = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)      #Create a socket object
        sOUT = socket.socket(socket.AF_INET, socket.SOCK_DGRAM) #create socket for outgoing packets    
        sIN.bind((host, portIN))    #Bind to the port
        sIN.settimeout(2)
        forwarding = True
        while forwarding: #keep receiving until got all the data
            try:
                ports = blueOut[portSet]
                if(ports[0]['input']<=0):#stop this forwarder
                    forwarding = False
                    return
                data, addr = sIN.recvfrom(1024)
                if(len(data)<=0):
                    continue
                if(len(ports)<=0):
                    data = ""
                    time.sleep(0.1)
                    continue
                for port in ports:
                    sOUT.sendto(data,(host,port['output']))
            except socket.error, msg:
                pass
            except Exception as e:
                pass
        #end while True
    except Exception as e:
        # print "portFwd FAILLLLLLL: ", e, sys.exc_traceback.tb_lineno
        pass
#end main

################## network management ##################


################## teradek management ##################
def camPortMon(port):
    try:
        host = '127.0.0.1'          #local ip address    
        sIN = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)      #Create a socket object
        sOUT = socket.socket(socket.AF_INET, socket.SOCK_DGRAM) #create socket for outgoing packets    
        portIn = port['input']
        portOut= port['output']
        sIN.bind((host, portIn))    #Bind to the port
        sIN.settimeout(0.5)
        while portIns[port['input']]['forwarding']:
            try:
                if(port['status']!='live'): #this camera is paused or stopped - do not forward anything            
                    time.sleep(0.1) #reduce the cpu load
                    continue
                data, addr = sIN.recvfrom(65536)
                if(len(data)<=0 and portIns[portIn]['active']):
                    # portIns[portIn]['active']=False
                    # blueOut[port['type']].append(port)
                    continue
                #if no data
                portIns[portIn]['active']=True
                if(port in blueOut[port['type']]): #data was received, but there is a blue screen forwader - remove it
                    blueOut[port['type']].remove(port)
                sOUT.sendto(data,(host,portOut))
            except socket.error, msg:
                # only gets here if the connection is refused
                if(portIn in portIns):
                    portIns[portIn]['active']=False
                # time.sleep(0.5)
                # if(port['type'] in blueOut and not (port in blueOut[port['type']])):
                #     blueOut[port['type']].append(port)
                pass
            except Exception as e:
                pass
        #end while True
    except Exception as e:
        pass
#end tdPortMon

# stops acquisition (either blue screen, ffmpeg or both)
# @param (string) td    - id of the encoder to stop
# @param (bool) group   - use PGID if true, PID if false
def capKill(td, group=False):
    if(not (td in teraRefs)):
        return #it's been killed
    if('scapRef' in teraRefs[td]):
        #this process was started earlier
        if('scapPID' in teraRefs[td]):# pid specified
            #kill the process
            if(group):#pgid was specified
                psKill(pgid=teraRefs[td]['scapPID'])
            else:#pid was specified
                psKill(pid=teraRefs[td]['scapPID'],ref=teraRefs[td]['scapRef'])
            # remove the process from monitoring
            if(teraRefs[td]['scapPID'] in procMons):
                del procMons[teraRefs[td]['scapPID']]
            # delete the pid
            del teraRefs[td]['scapPID']
        # after process was killed and pid/pgid was removed, delete the reference
        del teraRefs[td]['scapRef']
#end tdKill

#starts mp4/hls capture on all cameras
def tdStartCap():
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
            segmenters[devID] = c.segbin+" -p -t 1s -S 1 -B segm_"+fileSuffix+"st -i list"+fileSuffix+".m3u8 -f "+c.wwwroot+"live/video 127.0.0.1:"+dskHLS
            ffcaps[devID] = c.ffbin+" -i "+cameras[devID]['url']+" -codec copy -f h264 udp://127.0.0.1:"+camMP4+" -codec copy -f mpegts udp://127.0.0.1:"+camHLS
            if(not (devID in teraRefs)):
                teraRefs[devID]={}
            # each camera also needs its own port forwarder
            portIns[int(camMP4)]={
                'forwarding'  :True,
                'status'      :'live',
                'type'        :'mp4',
                'camera'      :devID,
                'input'       :int(camMP4),
                'output'      :int(dskMP4),
                'active'       :True
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
        # this starts an ffmpeg instance to simulate blue scren in case the camera kicks off
        # ffBlue = c.ffbin+" -loop 1 -y -re -i "+c.approot+"/bluescreen.jpg -r 30 -vcodec libx264 -an -shortest -f h264 udp://127.0.0.1:"+str(blueMP4)+" -r 30 -vcodec libx264 -vbsf h264_mp4toannexb -f mpegts udp://127.0.0.1:"+str(blueHLS)
        # start the HLS segmenters and rtsp/rtmp captures
        for devID in segmenters:
            # segmenter
            cmd = segmenters[devID]
            ps = sb.Popen(cmd.split(' '),stdout=FNULL)
            teraRefs[devID]['segmCmd']=cmd
            teraRefs[devID]['segmPID']=ps.pid
            teraRefs[devID]['segmRef']=ps
            # start monitoring the segmenter
            # addMon(pid=ps.pid)
            # ffmpeg RTSP capture
            cmd = ffcaps[devID]
            ps = sb.Popen(cmd.split(' '),stderr=FNULL)
            teraRefs[devID]['scapCmd']=cmd
            teraRefs[devID]['scapPID']=ps.pid
            teraRefs[devID]['scapRef']=ps
            print "started ",devID
        # start blue screen
        # ps = sb.Popen(ffBlue.split(' '),stderr=FNULL)
        # teraRefs['blue']={'cmd':ffBlue,'pid':ps.pid,'ref':ps}
        # start mp4 recording to file
        # dbgLog(ffMP4recorder)
        ps = sb.Popen(ffMP4recorder.split(' '),stderr=FNULL)
        teraRefs['mp4save']={'cmd':ffMP4recorder,'pid':ps.pid,'ref':ps}
    except Exception as e:
        dbgLog("startCam failed!!: "+str(e)+" at "+str(sys.exc_traceback.tb_lineno))
#end tdStartCap

#stops the capture, kills all ffmpeg's and segmenters
def tdStopCap():
    print "STOP CAP!!!!!"
    try:
        refCopy = copy.deepcopy(teraRefs)    
        for td in refCopy:
            print "stopping........................",td
            if('segmPID' in refCopy[td]):#kill segmenter
                print "kill segmenter: ", refCopy[td]['segmPID']
                psKill(pid=refCopy[td]['segmPID'],ref=refCopy[td]['segmRef'])
                del teraRefs[td]['segmPID']
                del teraRefs[td]['segmCmd']
            if('scapPID' in refCopy[td]):#kill stream capture (ffmpeg)
                print "kill capture: ", refCopy[td]['scapPID']
                psKill(pid=refCopy[td]['scapPID'],ref=refCopy[td]['scapRef'])
                del teraRefs[td]['scapPID']
                del teraRefs[td]['scapCmd']
            if(td=='blue' or td=='mp4save'): #kill mp4-recorder/bluescreen-forwader (ffmpeg)
                print "kill mp4: ", refCopy[td]['pid']
                psKill(pid=refCopy[td]['pid'],ref=refCopy[td]['ref'])
            if(td in teraRefs):
                del teraRefs[td]
        # remove all forwaders as well
        for port in portIns:
            portIns[port]['forwarding']=False
        #remove any bluescreen forwarders (if any)
        blueOut['mp4']=[]
        blueOut['hls']=[]
        for thd in tmr['portFwd']:
            tmr['portFwd'][thd].kill()
    except Exception as e:
        print "STOPFAILLLLLLLLLLLLLLLLLLLLL:", e, sys.exc_traceback.tb_lineno
    print "STOPDONE!!!!!"
#gets status of all teradeks in the system
def tdStatus():
    # list of active teradeks
    validTDs = {}
    ###########################################################################
    teraCopy = copy.deepcopy(teradeks)
    myip = get_lan_ip()
    for td in teraCopy:
        if(not(('url_port' in teraCopy[td]) and ('url' in teraCopy[td]))):
            #port or main URL is not specified in this teradek entry - it's faulty
            continue #move on to the next device
        if(not sameSubnet(td,myip)):
            continue #skip teradeks that are not on local network
        tdPort = teraCopy[td]['url_port']
        tdURL = teraCopy[td]['url']
        tdAddress = td
        # message that should receive RTSP/1.0 200 OK response from a valid rtsp stream
        msg = "DESCRIBE "+tdURL+" RTSP/1.0\r\nCSeq: 2\r\nAccept: application/sdp\r\nUser-Agent: Python MJPEG Client\r\n\r\n"""
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(1)
        try:
            s.connect((tdAddress, int(tdPort)))
            s.send(msg)
            data = s.recv(1024)
        except Exception as e:
            data = str(e)
            dbgLog("FAIL FAIL FAIL FAIL FAIL FAIL FAIL FAIL:"+data)
        #close the socket
        try:
            s.close()
        except:
            #probably failed because couldn't connect to the rtsp server - no need to worry
            pass
        
        strdata = data.lower().strip()
        if(strdata.find('timed out')>-1 or strdata.find('host is down')>-1 or strdata.find('no route to host')>-1):
            # found a "ghost": this device recently disconnected - skip it
            continue
        #a device is not available (either just connected or it's removed from the system)
        #when connection can't be established or a response does not contain RTSP/1.0 200 OK
        teraCopy[td]['on'] = (data.find('RTSP/1.0 200 OK')>=0)
        validTDs[td] = teraCopy[td]
    #end for td in tds
    # save the info about teradeks to a file
    f = open(c.tdCamList,"w")
    f.write(json.dumps(validTDs))
    f.close()
    ###########################################################################
    return validTDs
#end tdStatus

def camMonitor():
    # get all cameras that are active
    cams = camera.getOnCams()
    # get status of all connected teradeks
    tds = tdStatus()
    print "..................................REFSSS",teraRefs
    # go through active cameras and make sure they're all online and active
    for td in cams:
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
            dbgLog("PAUSED CAMERA!!!!!")
            continue #this camera is paused - no need to check anything else here
        elif('state' in cams[td] and cams[td]['state']=='stopped'):
            #############
            ## STOPPED ##
            #############
            dbgLog("CAMERA STOPPED!")
            continue #this camera is stopped
        else: #by default assume camera is live
            ############
            ##  LIVE  ##
            ############
            if(camMP4 in portIns):
                portIns[camMP4]['status']='live'
            if(camHLS in portIns):
                portIns[camHLS]['status']='live'
            dbgLog("LIVE CAMERA!!")
        if((td in tds) and tds[td]['on'] and (td in teraRefs)):
            #this camera is getting data
            #check if its ffmpeg is live and kicking
            if(not (('scapPID' in teraRefs[td]) and psOnID(pid=teraRefs[td]['scapPID']))):
                #no ffmpeg - it must've died when the camera disconnected - resume it
                ps = sb.Popen(teraRefs[td]['scapCmd'].split(' '),stderr=FNULL)
                teraRefs[td]['scapPID']=ps.pid
                teraRefs[td]['scapRef']=ps
        else:
            #camera is inactive
            # make sure ffmpeg is dead
            if(td in teraRefs and 'scapPID' in teraRefs[td]):
                psKill(pid=teraRefs[td]['scapPID'], ref=teraRefs[td]['scapRef'],force=True)
    #end for td in cams
#end tdMonitor

# looks for teradek cube published through bonjour
def tdFind():
    # teradeks are identified by this
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
                queried.append(True)
                # found teradek, add it to the list
                # get details about this device
                recs = parseStream(txtRecord)
                strport = str(port)
                camID = ipAddr
                if(not camID in teradeks):
                    teradeks[camID] = {}
                    teradeks[camID]['on']=False
                # url to the stream, consists of:
                # 'sm' - streaming method/protocol (e.g. rtsp)
                # ipAddr - ip address of the encoder (e.g. 192.168.1.100)
                # strport - port of the stream (e.g. 553)
                # 'sn' - stream name (e.g. stream1)
                streamURL = recs['sm'].lower()+'://'+ipAddr+':'+strport+'/'+recs['sn']
                # check if this is a preview or a full rez stream
                if(recs['sn'].lower().find('quickview')>=0):# this is a preview stream
                    teradeks[camID]['preview']=streamURL
                    teradeks[camID]['preview_port']=strport
                else: # this is full resolution stream
                    teradeks[camID]['url']=streamURL
                    teradeks[camID]['url_port']=strport
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
            while ((now-start_time)<2):#look for teradeks for 3 seconds, then exit
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
############### end teradek management ################

############### process monitors ###############
#monitors processes, creates alerts for idle ones
def idleProcMon():
    # create a copy in case the original gets modified during this loop
    procCopy = copy.deepcopy(procMons)
    # go through all processes and check theirwCPU status
    for proc in procCopy:
        if ('pid' in procCopy[proc]):
            cpu = getCPU(pid=procCopy[proc]['pid'])
        elif('pgid' in procCopy[proc]):
            cpu = getCPU(pgid=procCopy[proc]['pgid'])
        else:
            cpu = 0
        # if(not ('idle' in procCopy[proc])):
        #     procCopy[proc]['idle']=0 #how many idle ticks this process has
        # if(cpu<=0):
        #     procCopy[proc]['alert']=True #idle process - set off an alert
        if(cpu<=0):#process idle, increment idle count
            procCopy[proc]['idle']+=1
        else:#process is not idle, reset idle count
            procCopy[proc]['idle']=0
        if(procCopy[proc]['idle']>3):#process has been idle for 2 seconds, set off an alert
            procCopy[proc]['alert']=True
        else:#process has returned from idle state - clear the alert
            procCopy[proc]['alert']=False
    #end for proc in procMons
    # copy back the processes
    for proc in procCopy:
        if(proc in procMons):
            procMons[proc]=procCopy[proc]
#end idleProcMon    

# adds a process to monitor
def addMon(pid=0,pgid=0):
    if(pid): #if this process monitor already exists, it just resets all counters
        procMons[pid]={'pid':int(pid),'alert':False,'idle':0}
    if(pgid):
        procMons[pgid]={'pgid':int(pgid),'alert':False,'idle':0}
#end addMon
############## end process monitors ##############

# finds cpu usage by all processes with the same pgid
def getCPU(pgid=0,pid=0):
    totalcpu = 0
    if(pgid):
        #list of all processes in the system
        procs = psutil.get_process_list()
        for proc in procs:
            try:#try to get pgid of the process
                foundpgid = os.getpgid(proc.pid)
            except:
                continue #skip processes that do not exist/zombie/invalid/etc.
            if(pgid==foundpgid):#this process belongs to the same group
                try: #can use the same function recursively to get cpu usage of a single process, but creates too much overhead
                    ps = psutil.Process(proc.pid)
                    totalcpu += ps.get_cpu_percent()
                except:
                    dbgLog("INVALID!!")
                    continue
            #if pgid==foundpgid
        #for proc in procs
    elif(pid):#looking for cpu usage of one process by pid
        try:
            ps = psutil.Process(pid)
            totalcpu = ps.get_cpu_percent()
        except Exception as e:
            dbgLog("get cpu fail: "+str(e))
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
    contents = readFile("/tmp/pxpports")
    if not contents:
        return ports
    for line in contents.split("\n"):
        parts = line.split("=")
        if len(parts)>1:
            if(parts[0] in ports):
                ports[parts[0]] = int(parts[1])
    return ports

# attempts to kill a process based on PID (sends SIGKILL, equivalent to -9)
# @param (int) pid - process ID
# @param (int) pgid - process group ID
# @param (obj) ref - reference to the Popen process (used to .communicate() - should prevent zombies)
# @param (int) timeout - timeout in seconds how long to try and kill the process
# @param (bool) force - whether to force exit a process (sends KILL - non-catchable, non-ignorable kill)
def psKill(pid=0,pgid=0,ref=False,timeout=3,force=False):
    start_time = time.time()
    now = start_time
    timeout = now+timeout
    if(not(pid or pgid)):
        return #one must be specified 
    dbgLog("KILLING: "+str(pid)+" "+str(pgid))
    #attempt to kill it every second until it's dead or timeout reached
    while(psOnID(pid=pid,pgid=pgid) and ((timeout-now)>0)):
        if(now-start_time<1): #keep running until it's dead
            now = time.time()
            time.sleep(0.05) #dramatically reduces the load on the CPU
            continue
        try:
            if(force): #forcing a quit - send kill (-9)
                sigToSend = signal.SIGKILL
            else:#gentle quit, send term (-15)
                sigToSend = signal.SIGTERM
            # at first, try to kill the process softly, give it some time
            if(pgid):#for group kills, sigterm needs to be sent to the entire group (parent+children) otherwise there will be zombies
                os.killpg(pgid, sigToSend)
            elif(pid):
                os.kill(pid,sigToSend)
            if(ref):
                ref.communicate()
        except Exception as e:
            dbgLog("!!!!!!!!!!!!!!!!!!!kill fail: "+str(e))
            pass
        start_time = now
    #end while psOnID
    # if exited loop on timeout, attempt another 'harsher' way to end the process:
    if(psOnID(pid=pid,pgid=pgid)):
        try:
            if(pgid):
                os.killpg(pgid, signal.SIGKILL)
            elif(pid):
                os.kill(pid,signal.SIGKILL)
            if(ref):
                ref.communicate()
        except:
            pass
    time.sleep(1) #wait for a bit
    # if that hasn't worked, last resort - kill this monkey!!!
    if(psOnID(pid=pid,pgid=pgid)):
        try:
            if(pgid):
                os.killpg(pgid, signal.SIGHUP)
            elif(pid):
                os.kill(pid,signal.SIGHUP)
            if(ref):
                ref.communicate()
        except:
            pass
    dbgLog("PID: "+str(pid)+" PGID: "+str(pgid)+" IS "+str(psOnID(pid=pid,pgid=pgid)))
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
    except:
        return False
    return p.is_running()
    # cmd = "kill -0 "+str(pid) #"ps -A | pgrep "+process+" > /dev/null"
    # #result of the cmd is 0 if it was successful (i.e. the process exists)
    # return os.system(cmd)==0

# monitors the pxpstream app - if the app stops streaming, restarts it
def streamMon():
    global lastKillSig, lastStartSig, bitCAM, bitENC, bitSTREAM, bitSTART
    # check ports
    ports = getPorts()
    if(ports["CHK"]!=65535):
        # check port is set, so the video should be streaming - make sure that it is
        now = int(time.time())
        encstat = int(readFile("/tmp/pxpstreamstatus"))
        if((int(sockRead())!=1) and (encstat&bitCAM) and (not(encstat&bitSTART)) and ((now-lastStartSig)>10)):
            # no data or wrong data received - pxp is not streaming properly, but the camera is connected
            # restart the pxp streaming app
            now = int(time.time())
            # if the app is on and it's been at least 5 seconds since the last kill sig, try to kill it
            if(psOn("pxpStream.app") and (lastKillSig==0 or (now-lastKillSig)>5)):
                lastKillSig = now
                # if the pass is running, restart it
                # os.system("/usr/bin/killall pxpStream")
        now = int(time.time())
        if((not psOn("pxpStream.app")) and (lastStartSig==0 or (now-lastStartSig)>5)):
            #when the app is not on, start it to enable streaming
            # start the pxp app
            lastStartSig = now
            # os.system("/usr/bin/open /Applications/pxpStream.app")
    else:
        pass
#end streamMon

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

class PubProtocol(basic.LineReceiver):
    def __init__(self, factory):
        self.factory = factory
        globalBBQ = {}

    def connectionMade(self):
        global globalBBQ
        # user just connected
        # add him to the factory
        self.factory.clients.add(self)
        clientID = str(self.transport.getPeer().host)+"_"+str(self.transport.getPeer().port)
        globalBBQ[clientID] = [{},self,True]
        dbgLog("connected: "+str(clientID))
    def connectionLost(self, reason):
        self.factory.clients.remove(self)
        clientID = str(self.transport.getPeer().host)+"_"+str(self.transport.getPeer().port)
        del globalBBQ[clientID]
    def dataReceived(self, data):
        global globalBBQ
        try:
            # client IP address
            senderIP = str(self.transport.getPeer().host)
            # client port
            senderPT = str(self.transport.getPeer().port)
            #if it was a command, it'll be split into segments by vertical bars
            dataParts = data.split('|')
            # if(senderIP!="127.0.0.1"):
                # dbgLog("got data: "+data+" from: "+senderIP)
            if(len(dataParts)>0):                
                # this is a service request
                if(senderIP=="127.0.0.1"):
                    # these actions can only be sent from the local server
                    if(dataParts[0]=='RMF'): #remove file
                        rmFiles.append(dataParts[1])
                    if(dataParts[0]=='RMD'): #remove directory
                        rmDirs.append(dataParts[1])
                    if(dataParts[0]=='STR'): #start encode
                        tdStartCap()
                    if(dataParts[0]=='STP'): #stop encode
                        tdStopCap()
                #end if sender=127.0.0.1
                if(dataParts[0]=='ACK'): # acknowledgement of message receipt
                    cmdID = dataParts[1].strip() #the ack's come in format ACK|<message_id>
                    # broadcast acknowledgment received - remove that request from the queue of sent events
                    try:
                        # del globalBBQ[senderIP+"_"+senderPT][0][int(cmdID)]
                        globalBBQ[senderIP+"_"+senderPT][0][int(cmdID)]['ACK']=1
                    except Exception as e:
                        pass
                    return
                #if dataparts=='do'
            #if len(dataparts)>0
        ###########################################
        #             broadcasting                #
        ###########################################
            if(senderIP!="127.0.0.1"): #only local host can broadcast messages
                return
            for c in self.factory.clients:
                try:
                    # get the ip address of the client
                    clientID = c.transport.getPeer().host+"_"+str(c.transport.getPeer().port)
                    # add message to the queue (and send it)
                    addMsg(clientID,data,c)
                except Exception as e:
                    pass
        except:
            pass
    #end dataReceived

class PubFactory(protocol.Factory):
    def __init__(self):
        self.clients = set()

    def buildProtocol(self, addr):
        return PubProtocol(self)
#make sure there is only 1 instance of this script running
me = singleton.SingleInstance() 
tmr = {}
#pxp socket communication is done on port 2232
reactor.listenTCP(2232, PubFactory()) 

# stream monitor (checks if there is an encoding device connected)
tmr['streamMon'] = TimedThread(streamMon,period=4)

# set up messages(tags) queue manager to execute every second
tmr['BBQ'] = TimedThread(bbqManage,period=0.1)

# start a watchdog timer
tmr['dogeKick'] = TimedThread(kickDoge,period=30)
# register pxp on bonjour service
# thread.start_new_thread(pubBonjour,())
tmr['bonjour'] = TimedThread(pubBonjour)
# look for teradek cube's on bonjour
tmr['tdFind'] = TimedThread(tdFind,period=10)

tmr['camMonitor'] = TimedThread(camMonitor,period=2)

tmr['idleMon'] = TimedThread(idleProcMon,period=0.5)

# start deleter timer (deletes files that are not needed/old/etc.)
tmr['delFiles'] = TimedThread(deleteFiles,period=2)

tmr['cleanupEvts'] = TimedThread(removeOldEvents,period=10)

#start the threads for forwarding the blue screen to udp ports (will not forward if everything is working properly)
# tmr['fwdMP4'] = TimedThread(portFwd,(blueMP4,'mp4'))
# tmr['fwdHLS'] = TimedThread(portFwd,(blueHLS,'hls'))
#register what happens on ^C:
signal.signal(signal.SIGINT, pxpCleanup)

reactor.run()