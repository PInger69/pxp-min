#!/usr/bin/python

# pXp List monitor
# monitors list.m3u8 file for dropped connection/pause 
# and inserts discontinuities as appropriate

from twisted.internet import reactor, protocol, task
from twisted.protocols import basic
from tendo import singleton

lastSegm = 0
listPath = "/var/www/html/events/live/video/list.m3u8"
# file monitor variable used for scheduling tasks
fm 	= None
monitoring = False

def dlog(text):
	print text

def sockRead(udpAddr="127.0.0.1", udpPort=2224, timeout=0.4, sizeToRead=1):
	import socket
	import errno
	from socket import error as socket_error
	sock = socket.socket(socket.AF_INET, # Internet
						 socket.SOCK_DGRAM) # UDP
	sock.settimeout(timeout) #wait for 'timeout' seconds - if there's no response, server isn't running
	#bind to the port and listen
	try:
		sock.bind((udpAddr, udpPort))
		data, addr = sock.recvfrom(sizeToRead)
	except Exception as e:
		dlog(e)
		data = 0
		#failed to bind to that port or timed out on receiving - no data sent
	#close the socket
	try:
		sock.close()
	except:
		#probably failed because bind didn't work - no need to worry
		pass
	return data
# sends msg to the specified socket

# returns the last segment listed in the m3u8 file
def getLastSeg():
	global listPath
	import subprocess, re
	# get last few lines of the file (no need to iterate through the entire file)
	p = subprocess.Popen(['tail', listPath], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
	lines, err = p.communicate()
	lastNum = 0
	# go through the last few lines of the file
	for line in lines.split("\n"):
		if (line[:7]=='#EXTINF'):
			# this line contains time
			try:
				lastNum=float(re.search('[0-9\.]+', line).group())
			except:
				lastNum=-1
				pass
		# if (line[:4]=='segm'):
		# 	# this line contains the segment name
		# 	try:
		# 		lastNum['num'] = int(re.search('[0-9]+', line).group())
		# 	except:#could not extract number from the line (something wrong)
		# 		pass
	return lastNum
#end getLastSeg

def onTimer():
	global lastSegm, listPath
	import os
	newSeg = getLastSeg()
	if(abs(newSeg-lastSegm)>=0.01):
		#new segment is significantly different from the previous one - add discontinuity after it
		os.system("echo '#EXT-X-DISCONTINUITY' >> "+listPath)
	lastSegm = newSeg
	dlog(str(lastSegm))
	dlog(newSeg)

me = singleton.SingleInstance() #make sure there is only 1 instance of this script running

l = task.LoopingCall(onTimer) #set up a function to execute periodically
l.start(0.5) #execute onTimer() every 1/2 seconds
reactor.run()