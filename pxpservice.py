#!/usr/bin/python
from twisted.internet import reactor, protocol, task
from twisted.protocols import basic
from tendo import singleton
from datetime import datetime as dt
from uuid import getnode as getmac
import camera, constants as c, copy, json, os, psutil, platform, pybonjour, select, signal, socket, subprocess as sb, thread, time

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
################## delete files ##################
rmFiles = []
rmDirs = []
def deleteFiles():
    # if there is a deletion in progress - let it finish
    if (psOn("rm -f") or psOn("rm -rf") or psOn("xargs -0 rm")):
        return    
    # first, take care of the old session files (>1 day) should take no more than a couple of seconds
    os.system("find "+c.wwwroot+"session -mtime +1 -type f -print0 | xargs -0 rm &")
    dbgLog("DELETING FILES: "+str(rmFiles))
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
    dbgLog("DELETING FOLDERS: "+str(rmDirs))
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
################ end delete files ################


def dbgLog(msg, timestamp=True):
    print dt.fromtimestamp(time.time()).strftime("%Y-%m-%d %H:%M:%S.%f"), msg
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
        try:
            while True:
                ready = select.select([sdRef], [], [])
                if sdRef in ready[0]:
                    pybonjour.DNSServiceProcessResult(sdRef)
        except KeyboardInterrupt:
            pass
    except Exception as e:
        pass
    finally:
        sdRef.close()
    # try:
    #     try:
    #         while True:
    #             ready = select.select([sdRef], [], [])
    #             if sdRef in ready[0]:
    #                 pybonjour.DNSServiceProcessResult(sdRef)
    #     except KeyboardInterrupt:
    #         pass
    # finally:
    #     sdRef.close()
#end pubBonjour

################## teradek management ##################

# stops acquisition (either blue screen, ffmpeg or both)
# @param (string) td    - id of the encoder to stop
# @param (bool) blue    - whether to stop the blue screen streaming
# @param (bool) ff      - whether to stop the ffmpeg stream acquisition
# @param (bool) group   - use PGID if true, PID if false
# @param (bool) cmd     - remove CMD from the terarefs as well
def tdKill(td, blue=False, ff=False,group=False, cmd=False):
    if(not (td in teraRefs)):
        return #it's been killed
    if(blue):#killing blue screen
        if('blueref' in teraRefs[td]):
            #verified, it was started earlier
            if('bluepid' in teraRefs[td]):# pid specified
                #kill the process
                if(group): #pgid was specified
                    psKill(pgid=teraRefs[td]['bluepid'])
                else:#pid was specified
                    psKill(pid=teraRefs[td]['bluepid'],ref=teraRefs[td]['blueref'])
                # remove the process from monitoring
                if(teraRefs[td]['bluepid'] in procMons):
                    del procMons[teraRefs[td]['bluepid']]
                # delete the pid
                del teraRefs[td]['bluepid']
            # after process was killed and pid/pgid was removed, delete the reference
            del teraRefs[td]['blueref']
        #end if blueref in terarefs
        if(cmd and 'bluecmd' in teraRefs[td]):
            del teraRefs[td]['bluecmd']
    #end if blue
    if(ff):
        if('ffref' in teraRefs[td]):
            #verified, it was started earlier
            if('ffpid' in teraRefs[td]):# pid specified
                #kill the process
                if(group):#pgid was specified
                    psKill(pgid=teraRefs[td]['ffpid'])
                else:#pid was specified
                    psKill(pid=teraRefs[td]['ffpid'],ref=teraRefs[td]['ffref'])
                # remove the process from monitoring
                if(teraRefs[td]['ffpid'] in procMons):
                    del procMons[teraRefs[td]['ffpid']]
                # delete the pid
                del teraRefs[td]['ffpid']
            # after process was killed and pid/pgid was removed, delete the reference
            del teraRefs[td]['ffref']
        #end if blueref in terarefs
        if(cmd and 'ffcmd' in teraRefs[td]):
            del teraRefs[td]['ffcmd']
    #end if ff
#end tdKill

def tdMonitor():
    now = time.time()
    start_time = time.time()+3#wait for additional 3 seconds before starting the monitor - gives enough time to identfiy any teradeks in the system
    FNULL = open(os.devnull,"w") #for dumping all cmd output
    while(True):
        if((now-start_time)<2):#run the function every 2 seconds
            now = time.time()
            time.sleep(0.05) #dramatically reduces the load on the CPU
            continue
        start_time=now
        # list of active teradeks
        validTDs = {}
        # get all cameras that are active
        cams = camera.getOnCams()
        ###########################################################################
        for td in teradeks:
            if(not(('url_port' in teradeks[td]) and ('url' in teradeks[td]))):
                #port or main URL is not specified in this teradek entry - it's faulty
                continue #move on to the next device

            tdPort = teradeks[td]['url_port']
            tdURL = teradeks[td]['url']
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
            #close the socket
            try:
              s.close()
            except:
              #probably failed because couldn't connect to the rtsp server - no need to worry
              pass
            dbgLog(data)
            if(data.lower().strip()=='timed out'):
                # found a "ghost": this device recently disconnected - skip it
                continue
            #a device is not available (either just connected or it's removed from the system)
            #when connection can't be established or a response does not contain RTSP/1.0 200 OK
            teradeks[td]['on'] = (data.find('RTSP/1.0 200 OK')>=0)
            validTDs[td] = teradeks[td]
        #end for td in tds
        dbgLog("validTD:" +str(validTDs))
        ###########################################################################
        # go through active cameras and make sure they're all online and active
        dbgLog("teraRefs: "+str(teraRefs))
        for td in cams:
            if(not (td in teraRefs)):
                teraRefs[td]={}
            if('state' in cams[td] and cams[td]['state']=='paused'): #the camera state is paused
                #make sure this camera is paused - simply kill the ffmpeg acquiring the stream
                dbgLog("PAUSED CAMERA!!!!!")
                tdKill(td,blue=True,ff=True,cmd=True)
                continue #this camera is paused - no need to check anything here
            else:
                dbgLog("LIVE CAMERA!!")
            # make sure this encoder didn't drop off the network
            if(not ((td in teradeks) and (teradeks[td]['on']) or 'bluepid' in teraRefs[td])):
                ##################
                # ENCODER IS OFF #
                ##################
                #encoder is offline, or its stream is not available
                #and it doesn't yet have blue screen running 
                dbgLog(td+" IS OFFLINE, NO BLUE SCREEN YET !!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!")
                # this encoder is activated and it does not have blue screen
                # but the devcie is not ready to stream (i.e. identifying camera, etc.)
                # send blue screen in the mean time to make sure the user knows what's happening and it doesn't mess up the normal streaming 
                camid = str(cams[td]['idx'])

                # running ffmpeg in this way does not return reliable PID
                cmd = c.ffbin+" -loop 1 -y -re -i "+c.approot+"/bluescreen.jpg -r 30 -vcodec libx264 -an -shortest -f h264 udp://127.0.0.1:221"+camid+" -r 30 -vcodec libx264 -vbsf h264_mp4toannexb -f mpegts udp://127.0.0.1:220"+camid
                ps = sb.Popen(cmd.split(' '), stderr=FNULL)
                # ps = sb.Popen(cmd.split(' '), stdout=FNULL, preexec_fn=os.setsid)
                # to do stderr to a file, have to open the file for writing first, then pass the file to Popen, e.g.:
                # logfile = open("/tmp/pxplog","w")
                # sb.Popen(cmd,stderr=logfile)

                teraRefs[td]['bluecmd']=cmd
                teraRefs[td]['bluepid']=int(ps.pid)
                teraRefs[td]['blueref']=ps
                addMon(pid=ps.pid)
                if('ffpid' in teraRefs[td]):
                    #kill the stalled ffmpeg that was supposed to acquire the stream (if it still exists)
                    tdKill(td,ff=True, group=False,cmd=True)
                    # del procMons[teraRefs[td]['ffpid']] #remove it from the monitors
                    # psKill(pid=teraRefs[td]['ffpid'],ref=teraRefs[td]['ffref']) #kill the process
                    # del teraRefs[td]['ffpid'] #remove it from the list of pids
                    # del teraRefs[td]['ffref'] #remove the reference to that subprocess
            #if teradek off
            elif((td in teradeks) and teradeks[td]['on']):
                #################
                # ENCODER IS ON #
                #################            
                dbgLog(td+" in cams, running")
                # stop the blue screen if it was on already
                if('bluepid' in teraRefs[td]):
                    tdKill(td,blue=True, group=False,cmd=True)
                    # try:
                    #     dbgLog("...............................trying to kill blue screen")
                    #     psKill(pid=teraRefs[td]['bluepid'],ref=teraRefs[td]['blueref'])
                    # except Exception as e:
                    #     dbgLog("????????????!!!!!!!!!!!!!COULD NOT KILL BLUE SCREEN!!!!!!!!!!!????????")
                    #     dbgLog(e)
                    # del procMons[teraRefs[td]['bluepid']]
                    # del teraRefs[td]['bluepid']
                    # del teraRefs[td]['blueref']
                else:
                    dbgLog("..................................NO BLUE SCREEN TO KILL")
                if(not('ffpid' in teraRefs[td])):
                    # ffmpeg was not started for on this camera yet
                    camid = str(cams[td]['idx'])
                    # teradek is on - start the streaming (to a local UDP port, regardless if anyone is listening)
                    cmd =  c.ffbin+" -i "+cams[td]['url']+" -codec copy -f h264 udp://127.0.0.1:221"+camid+" -codec copy -f mpegts udp://127.0.0.1:220"+camid
                    ps = sb.Popen(cmd.split(' '),stderr=FNULL)
                    teraRefs[td]['ffcmd']=cmd
                    teraRefs[td]['ffpid']=int(ps.pid)
                    teraRefs[td]['ffref']=ps
                    addMon(pid=ps.pid)
            #end if td in cams and teradek on
            ###################
            # checking FFMPEG #
            ###################
            # check the status of the ffmpeg associated with this stream
            # ffmpeg for main stream and for blues creen stream
            # pt - process type
            for pt in [['ffpid','ffref','ffcmd'],['bluepid','blueref','bluecmd']]:
                if(pt[0] in teraRefs[td]):
                    #this device has ffmpeg or bluescreen associated with it
                    if(procMons[teraRefs[td][pt[0]]]['alert']): #there is an idle alert on this process
                        dbgLog("DEAD STREAM!DEAD STREAM!DEAD STREAM! "+pt[0]+' '+str(teraRefs[td][pt[0]]))
                        if(pt[0]=='ffpid'):#ffmpeg is dead - probably no camera input detected
                            tdKill(td,ff=True, group=False)
                        else: #bluescreen is dead
                            tdKill(td,blue=True,group=False)
                        # # status is anything other than running (sleeping, zombie, etc)
                        # # kill this process
                        # psKill(pid=teraRefs[td][pt[0]],ref=teraRefs[td][pt[1]])
                        # # remove all references to it
                        # del procMons[teraRefs[td][pt[0]]]
                        # del teraRefs[td][pt[0]]
                        # del teraRefs[td][pt[1]]
                        # restart the stream if it was there before
                        if(pt[2] in teraRefs[td]):
                            dbgLog("RESUMING STREAM...")
                            dbgLog(teraRefs[td][pt[2]])
                            ps = sb.Popen(teraRefs[td][pt[2]].split(' '),stderr=FNULL)
                            teraRefs[td][pt[0]]=ps.pid
                            teraRefs[td][pt[1]]=ps
                            addMon(ps.pid)
        #end for td in cams
        # save the info about teradeks to a file
        f = open(c.tdCamList,"w")
        f.write(json.dumps(validTDs))
        f.close()
        dbgLog("tdmon done-----------------------------------")
    #end while(true)
    FNULL.close()
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
    start_time = time.time()
    now = start_time
    while(True):
        if((now-start_time)<0.5):#run the function every 1/2 second
            now = time.time()
            time.sleep(0.05) #dramatically reduces the load on the CPU
            continue
        start_time=now
        # create a copy in case the original gets modified during this loop
        procCopy = copy.deepcopy(procMons)
        # go through all processes and check their CPU status
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
    #end while True
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
            dbgLog(e)
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
def psKill(pid=0,pgid=0,ref=False,timeout=20):
    start_time = time.time()
    now = start_time
    timeout = now+timeout
    if(not(pid or pgid)):
        return #one must be specified 
    dbgLog("KILLING: "+str(pid)+" "+str(pgid))
    #attempt to kill it every second until it's dead or timeout reached
    while(psOnID(pid=pid,pgid=pgid) and ((timeout-now)>0)):
        if(now-start_time<1):
            now = time.time()
            time.sleep(0.05) #dramatically reduces the load on the CPU
            continue
        try:
            if(pgid):#for group kills, sigterm needs to be sent to the entire group (parent+children) otherwise there will be zombie
                os.killpg(pgid, signal.SIGTERM)
            elif(pid):
                os.kill(pid,signal.SIGKILL)
            if(ref):
                ref.communicate()
        except Exception as e:
            dbgLog("!!!!!!!!!!!!!!!!!!!kill fail: "+str(e))
            pass
        start_time = now

    #end while psOnID
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
#pxp socket communication is done on port 2232
reactor.listenTCP(2232, PubFactory()) 

# stream monitor (checks if there is an encoding device connected)
tmrStreamMon = task.LoopingCall(streamMon)
tmrStreamMon.start(4)

# set up messages(tags) queue manager to execute every second
tmrBBQ = task.LoopingCall(bbqManage)
tmrBBQ.start(0.1) #execute bbqManage() every 1/10 second

# start a watchdog timer
tmrDogeKick = task.LoopingCall(kickDoge)
tmrDogeKick.start(30)

# register pxp on bonjour service
thread.start_new_thread(pubBonjour,())

# look for teradek cube's on bonjour
# thread.start_new_thread(tdFind,())
tmrTdFind = task.LoopingCall(tdFind)
tmrTdFind.start(10)

# monitor any found teradek devices
thread.start_new_thread(tdMonitor,())
# idle process monitor
thread.start_new_thread(idleProcMon,())


# start deleter timer (deletes files that are not needed/old/etc.)
rmTimer = task.LoopingCall(deleteFiles)
rmTimer.start(2)

reactor.run()