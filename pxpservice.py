#!/usr/bin/python
from twisted.internet import reactor, protocol, task
from twisted.protocols import basic
from tendo import singleton

# big broadcast queue - queue containing all of the sent messages for every client that it was sent to
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
def onTimer():
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
    for client in BBQcopy:
        try:
            # client entry in the BBQ list
            clnInfo = BBQcopy[client]
            # commands sent to this client that were not ACK'ed
            myCMDs = clnInfo[0]
            if(sendStatus):
                print "sending to "+str(client)+" status:"+sendStatus
                # globalBBQ[client][1].sendLine(json.dumps({'actions':{'event':'live','status':sendStatus}}))
                addMsg(client,json.dumps({'actions':{'event':'live','status':sendStatus}}))
            for cmdID in myCMDs:
                if((now-myCMDs[cmdID]['lastSent'])>3000): #over 3 seconds passed
                    print "resending cmd: "+str(globalBBQ[client][0][cmdID])+" to: "+str(client)
                    # re-send the request
                    globalBBQ[client][1].sendLine(myCMDs[cmdID]['data'])
                    # last sent would be now
                    globalBBQ[client][0][cmdID]['lastSent']=now
                    # increment number of times the request was sent
                    globalBBQ[client][0][cmdID]['timesSent']+=1
                # remove stale commands
                if(globalBBQ[client][0][cmdID]['timesSent']>5):
                    print "cmd sent 5 times, no ACK - removing: "+ str(globalBBQ[client][0][cmdID])
                    # requests that have been sent over 5 times need to be deleted
                    del globalBBQ[client][0][cmdID]
                    # if a client did not respond, remove the client
                    
            #for cmd in client
        except Exception as e:
            pass
    #for client in globalBBQ
#end onTimer

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
        # print e
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
    import time, os
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
            print "NOT STREAMING"
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
        # print "ok"
    else:
        print "paused"
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
    print 'adding msg to '+client
    # add him to the BBQ if he's not there already
    if(c and not client in globalBBQ):
        print "new client, adding..."
        globalBBQ[client] = [{},c]
    # send the data to the client
    globalBBQ[client][1].sendLine(str(timestamp)+"|"+msg)
    # add the data to the BBQ for this client
    globalBBQ[client][0][timestamp]={'timesSent':1,'lastSent':timestamp,'data':str(timestamp)+"|"+msg}

class PubProtocol(basic.LineReceiver):
    def __init__(self, factory):
        self.factory = factory
        # broadcast queue - where all sent requests appear
        # it's in this format:
        # bbq = {
        # '<clientIP1>':[{
        #       '<request1>':{'timesSent':<times_sent>, 'lastSent':<last_time_sent>, 'data':<data>},
        #       '<request2>':{'timesSent':<times_sent>, 'lastSent':<last_time_sent>, 'data':<data>}
        #   }, <client ref>], 
        # '<clientIP2>':[{
        #       '<request1>':{'timesSent':<times_sent>, 'lastSent':<last_time_sent>, 'data':<data>},
        #       '<request2>':{'timesSent':<times_sent>, 'lastSent':<last_time_sent>, 'data':<data>}
        #   }, <client ref>] 
        # }
        globalBBQ = {}

    def connectionMade(self):
        global globalBBQ
        # user just connected
        # add him to the factory
        self.factory.clients.add(self)
        clientID = str(self.transport.getPeer().host)+"_"+str(self.transport.getPeer().port)
        print "connected: "+clientID
        globalBBQ[clientID] = [{},self]
    def connectionLost(self, reason):
        self.factory.clients.remove(self)
        clientID = str(self.transport.getPeer().host)+"_"+str(self.transport.getPeer().port)
        print "disconnected: "+clientID
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
            print "got data: "+data+" from: "+senderIP
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
                        del globalBBQ[senderIP+"_"+senderPT][0][int(cmdID)]
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
                    print "adding msg to queue"
                    # add message to the queue (and send it)
                    addMsg(clientID,data,c)
                    print "bbq length for "+clientID+": "+str(len(globalBBQ[clientID][0]))
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

me = singleton.SingleInstance() #make sure there is only 1 instance of this script running
reactor.listenTCP(2232, PubFactory()) #listen to socket connections on port 2232
taskStreamMon = task.LoopingCall(streamMon)
taskStreamMon.start(4.0)
l = task.LoopingCall(onTimer) #set up a function to execute periodically
l.start(1.0) #execute onTimer() every second
reactor.run()