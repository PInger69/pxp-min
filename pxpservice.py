from twisted.internet import reactor, protocol, task
from twisted.protocols import basic
# big broadcast queue - queue containing all of the sent messages for every client that it was sent to
globalBBQ={}

# function called with ever timer tick that resends any unreceived events and deletes old ones
def onTimer():
    global globalBBQ
    import time, copy
    now = int(time.time()*1000) #current time
    # go through each sent command and if it wasn't ACK'd in 3 seconds, send it again
    BBQcopy = copy.deepcopy(globalBBQ)
    for client in BBQcopy:
        try:
            # client entry in the BBQ list
            clnInfo = BBQcopy[client]
            # commands sent to this client that were not ACK'ed
            myCMDs = clnInfo[0]
            for cmdID in myCMDs:
                if((now-myCMDs[cmdID]['lastSent'])>3000): #over 3 seconds passed
                    # re-send the request
                    globalBBQ[client][1].sendLine(myCMDs[cmdID]['data'])
                    # last sent would be now
                    globalBBQ[client][0][cmdID]['lastSent']=now
                    # increment number of times the request was sent
                    globalBBQ[client][0][cmdID]['timesSent']+=1
                # remove stale commands
                if(globalBBQ[client][0][cmdID]['timesSent']>5):
                    # requests that have been sent over 5 times need to be deleted
                    del globalBBQ[client][0][cmdID]
            #for cmd in client
        except Exception as e:
            pass
    #for client in globalBBQ
#end on Timer


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
        globalBBQ[clientID] = [{},self]
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
            import time  #for timestamping 
            for c in self.factory.clients:
                try:
                    # get timestamp for every broadcast
                    timestamp = int(time.time()*1000)
                    # get the ip address of the client
                    clientID = c.transport.getPeer().host+"_"+str(c.transport.getPeer().port)
                    # add him to the BBQ if he's not there already
                    if(not clientID in globalBBQ):
                        globalBBQ[clientID] = [{},c]
                    # send the data to the client
                    c.sendLine(str(timestamp)+"|"+data)
                    # add the data to the BBQ for this client
                    globalBBQ[clientID][0][timestamp]={'timesSent':1,'lastSent':timestamp,'data':str(timestamp)+"|"+data}
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

reactor.listenTCP(2232, PubFactory()) #listen to socket connections on port 2232
l = task.LoopingCall(onTimer) #set up a function to execute periodically
l.start(1.0) #execute onTimer() every second
reactor.run()