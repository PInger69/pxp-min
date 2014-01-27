#!/usr/bin/python
from twisted.internet import reactor, protocol, task
from twisted.protocols import basic
from tendo import singleton
import thread

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
#     '192.168.1.153_554_stream1':{
#         'port':554,
#         'ip': '192.168.1.153',
#         'url':'rtsp://192.168.1.153:554/stream1'
#         },
#     '192.168.1.153_554_quickstream':{
#         'port':554,
#         'ip': '192.168.1.153',
#         'url':'rtsp://192.168.1.153:554/quickstream'
#         }
#     }

teradeks    = {}
def dbgLog(msg, timestamp=True):
    from time import time as tm
    from datetime import datetime as dt
    print dt.fromtimestamp(tm()).strftime("%Y-%m-%d %H:%M:%S.%f"), msg
# kick the watchdog on each ipad (to make sure the socket does not get reset)
def kickDoge():
    import copy
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
    import os
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
    import time, copy, json
    # get encoder status
    pxpStatus = int(readFile("/tmp/pxpstreamstatus")) #contains status code
    sendStatus = False
    if(pxpStatus != lastStatus):
        sendStatus = encState(pxpStatus)
    lastStatus = pxpStatus
    now = int(time.time()*1000) #current time
    # go through each sent command and if it wasn't ACK'd in 3 seconds, send it again
    BBQcopy = copy.deepcopy(globalBBQ)
    # dbgLog(globalBBQ)
    for client in BBQcopy:
        try:
            # client entry in the BBQ list
            clnInfo = BBQcopy[client]
            # commands sent to this client that were not ACK'ed
            myCMDs = clnInfo[0]
            if(sendStatus):
                dbgLog("sending to "+str(client)+" status:"+sendStatus)
                # globalBBQ[client][1].sendLine(json.dumps({'actions':{'event':'live','status':sendStatus}}))
                addMsg(client,json.dumps({'actions':{'event':'live','status':sendStatus}}))
            dbgLog(str(len(myCMDs))+" commands for "+str(client))
            for cmdID in myCMDs:
                if(globalBBQ[client][2]):
                    # dbgLog("sending cmd: "+str(globalBBQ[client][0][cmdID] )+" to: "+str(client))
                    dbgLog("sending "+client+": "+myCMDs[cmdID]['data'])
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
                #     dbgLog("cmd sent 5 times, no ACK - removing: "+ str(globalBBQ[client][0][cmdID]))
                #     # requests that have been sent over 5 times need to be deleted
                #     del globalBBQ[client][0][cmdID]
                    # if a client did not respond, remove the client
            
            #for cmd in client
        except Exception as e:
            dbgLog("ERRRRRRRRRRRRRRRRRRRRRRRRRRRRRRRRRRRRR")
            dbgLog(e)
    #for client in globalBBQ
#end bbqManage

# registers pxp as bonjour service
def pubBonjour():
    import select, sys, pybonjour, subprocess, socket

    name    = socket.gethostname() #computer name
    regtype = "_pxp._udp" #pxp service
    # port is the HTTP port specified in apache:
    p = subprocess.Popen("cat /etc/apache2/httpd.conf | grep ^Listen | awk '{print $2}' | head -n1", shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
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
        dbgLog("ERRRRRR")
        dbgLog(str(e))
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

# looks for teradek cube published through bonjour
def findTeradek():
    import select, sys, pybonjour, socket
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
                teradeks[ipAddr+'_'+strport+'_'+recs['sn']] = {
                    'ip'  : ipAddr,
                    'port': strport,
                    #sm contains protocol (e.g. RTSP)
                    #sn contains stream name (e.g. stream1, quickview) 
                    'url' : recs['sm'].lower()+'://'+ipAddr+':'+strport+'/'+recs['sn']
                }
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

    browse_sdRef = pybonjour.DNSServiceBrowse(regtype = regtype, callBack = browse_callback)
    try:
        try:
            while True:
                ready = select.select([browse_sdRef], [], [])
                if browse_sdRef in ready[0]:
                    pybonjour.DNSServiceProcessResult(browse_sdRef)
        except KeyboardInterrupt:
            pass
    finally:
        browse_sdRef.close()
#end findTeradek
def sockRead(udpAddr="127.0.0.1", udpPort=2224, timeout=1, sizeToRead=1):
    import socket
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
def psOn(process):
    import platform, os
    if (platform.system()=="Windows"):
        #get all the processes for windows matching the specified one:
        cmd = "tasklist | findstr /I "+process
    else:
        #system can be Linux, Darwin
        #get all the processess matching the specified one:
        cmd = "ps -ef | grep \""+process+"\" | grep -v grep > /dev/null" #"ps -A | pgrep "+process+" > /dev/null"
    #result of the cmd is 0 if it was successful (i.e. the process exists)
    return os.system(cmd)==0

# monitors the pxpstream app - if the app stops streaming, restarts it
def streamMon():
    import time, os, json
    global lastKillSig, lastStartSig, bitCAM, bitENC, bitSTREAM, bitSTART
    # save the info about teradeks to a file
    f = open("/var/www/html/events/_db/.infenc","w")
    f.write(json.dumps(teradeks))
    f.close()   

    # check ports
    ports = getPorts()
    if(ports["CHK"]!=65535):
        # check port is set, so the video should be streaming - make sure that it is
        now = int(time.time())
        encstat = int(readFile("/tmp/pxpstreamstatus"))
        if((int(sockRead())!=1) and (encstat&bitCAM) and (not(encstat&bitSTART)) and ((now-lastStartSig)>10)):
            # no data or wrong data received - pxp is not streaming properly, but the camera is connected
            # restart the pxp streaming app
            dbgLog("NOT STREAMING")
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
        dbgLog("paused")
#end streamMon

# adds message for a client to the BBQ
# client - id of the client (ip + port)
# msg - message to send
# c - reference to the client variable (used to add them to the queue for the first time)
def addMsg(client,msg,c=False):
    global globalBBQ
    import time  #for timestamping 
    # get timestamp for every broadcast
    timestamp = int(time.time()*1000)
    dbgLog('adding msg to '+client)
    # add him to the BBQ if he's not there already
    if(c and not client in globalBBQ):
        dbgLog("new client, adding...")
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
        dbgLog("connected: "+clientID)
        globalBBQ[clientID] = [{},self,True]
    def connectionLost(self, reason):
        self.factory.clients.remove(self)
        clientID = str(self.transport.getPeer().host)+"_"+str(self.transport.getPeer().port)
        dbgLog("disconnected: "+clientID)
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
            if(senderIP!="127.0.0.1"):
                dbgLog("got data: "+data+" from: "+senderIP)
            if(len(dataParts)>0):
                # this is a service request
                if(dataParts[0]=='do'): #this is an action, perform it
                    if(dataParts[1]=='rm'): #remove a file
                        pass
                    return
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
                    # dbgLog("adding msg to queue")
                    # add message to the queue (and send it)
                    addMsg(clientID,data,c)
                    dbgLog("bbq length for "+clientID+": "+str(len(globalBBQ[clientID][0])))
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
taskStreamMon = task.LoopingCall(streamMon)
taskStreamMon.start(4.0)
# set up messages(tags) queue manager to execute every second
bbqTimer = task.LoopingCall(bbqManage)
bbqTimer.start(0.1) #execute bbqManage() every 1/10 second
# start a watchdog timer
dogeTimer = task.LoopingCall(kickDoge)
dogeTimer.start(30.0)
# register pxp on bonjour service
thread.start_new_thread(pubBonjour,())
# look for teradek cube on bonjour
thread.start_new_thread(findTeradek,())
reactor.run()