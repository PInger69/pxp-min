#!/usr/bin/python

# pXp List monitor
# monitors list.m3u8 file for dropped connection/pause 
# and inserts discontinuities as appropriate

from tendo import singleton
import constants as c
import sys
# import thread
listPath = c.wwwroot+"live/video/list.m3u8"


# returns true when both times are defined and different by more than 0.5ms
# @param (float) time1 - time in seconds
# @param (float) time2 - time in seconds
# @return (bool) whether the times are significantly different
def timeIsDiff(time1,time2):
	return (abs(time1-time2)>=0.0005) and (time1>=0) and (time2>=0)

#end onTimer
me = singleton.SingleInstance() #make sure there is only 1 instance of this script running

import re, time, os
prevTime = -1
# with open(listPath) as file_:
file_ = False;
lastTime = time.time()
lastPos = 0 #last position in the playlist file
while True:
	try:
		if(not os.path.exists(listPath)): 
			print "file doesn't exist"
			time.sleep(1)#wait until the file shows up
			if(file_):
				try:
					file_.close()
				except:
					pass
				file_ = False
			continue
		# if(not file_): #file showed up - open it
		file_ = open(listPath,"r")
		file_.seek(lastPos)
		line = file_.readline()
		lastPos = file_.tell()
		# print "pos:", lastPos
		if (not line):
			pass
			# print "didn't get a line"
			# file_.seek(curr_position)
		else:
			# print "got a line", line
			lastTime = time.time()
			# print line
			if(line[:7]=='#EXTINF'):
				print "TIMELINE: ", line
				# this line contains time
				try:
					lineTime=float(re.search('[0-9\.]+', line).group())
				except:
					lineTime=-1 #happens when can't extract a number - WHY???
				if(timeIsDiff(prevTime,lineTime)):#time is different between this line and the time 2 lines above
					print "!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!DISCONT!"
					os.system("echo '#EXT-X-DISCONTINUITY' >> "+listPath)
				prevTime = lineTime #set 'previous' line as current - for the next run
		file_.close()
		time.sleep(0.01)
	except Exception as e:
		print "errrrrrr: ", e, sys.exc_traceback.tb_lineno
		time.sleep(0.01)