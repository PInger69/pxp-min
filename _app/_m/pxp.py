from imp import load_source as ls
from imp import load_compiled as lp
import os, json
# m = lp("MVC","_m/mvc.pyc")
m = ls("MVC","_m/mvc.py")

class pxp(m.MVC):
	tagVidBegin = 10
	#######################################################
	#DEBUG#
	def reset(self):
		db = self.dbsqlite(self.wwwroot+"live/pxp.db")
		self.str().pout("Emptying logs table...")
		db.qstr("DELETE FROM `logs`")
		print "complete\n<br/>Emptying tags table..."
		db.qstr("DELETE FROM `tags`")
		print "complete\n<br/>Updating indecies..."
		db.qstr("DELETE FROM `sqlite_sequence`")
		print "complete\n<br/>Deleting thumbnails..."
		# delete thumbnails
		os.system("rm "+self.wwwroot+"live/thumbs/*")
		if not self.uri().segment(3,"")=='novideo':
			print "complete\n<br/>Deleting videos..."
			# delete vieos
			cmd = "find "+self.wwwroot+"live/video/ -type f -print0 | xargs -0 rm"
			os.system(cmd)
		print "complete\n<br/>RESET COMPLETE"
		return {}
	#END DEBUG#
	#create a bunch of random tags
	def alll(self):
		from random import randrange as rr
		tags = ["purple","teal","cyan","white","yellow","black","blue","red","pink"]
		colours = ["FF0000","00FF00","0000FF","FF00FF","00FFFF","FFFF00","333366","FFFFFF"]
		self.str().pout("")
		vidlen = len(os.listdir(self.wwwroot+"live/video/"))-2
		for i in range(0,800):
			col = colours[i % len(colours)]
			# col = hex(rr(0,255))[2:].rjust(2,'0')+hex(rr(0,255))[2:].rjust(2,'0')+hex(rr(0,255))[2:].rjust(2,'0')
			tstr = '{"name":"'+tags[i%len(tags)]+'","colour":"'+col+'","user":"356a192b7953b04c54574d18c28d46e6395428ab","tagtime":"'+str(rr(10,vidlen))+'","event":"live","period":"1"}'
			print self.tagset(tstr)
	#######################################################
	#######################################################
	# creates a coach pick
	#######################################################
	def coachpick(self,sess):
		import glob
		# make sure there is a live event
		if (not os.path.exists(self.wwwroot+'live/video')):
			return self._err("no live event")
		# get logged in user
		user = sess.data['user'] # user HID
		# get his tag colour from the database
		db = self.dbsqlite(self.wwwroot+'_db/pxp_main.db')
		sql = "SELECT `tagColour` FROM `users` WHERE `hid` LIKE ?"

		db.query(sql,(user,))
		users = db.getasc()
		# make sure this user is in the database
		if(len(users)<1):
			return self._err("invalid user")
		colour = users[0]['tagColour']
		# find last created segment (to get the time)
		segFiles = glob.glob(self.wwwroot+"live/video/segm*.ts")
		if(len(segFiles)<2):
			return self._err("there is no video yet")
		lastSeg = len(segFiles)-2 #segments start at segm0
		# set time
		tagTime = lastSeg * 0.984315
		# create tag
		tagStr = '{"name":"Coach Tag","colour":"'+colour+'","user":"'+user+'","tagtime":"'+str(tagTime)+'","event":"live","coachpick":"1"}'
		return dict(self.tagset(tagStr),**{"action":"reload"})
	#######################################################
	# gets download progress from the progress.txt file
	# sums up all the individual progresses and outputs a number
	#######################################################
	def dlprogress(self):
		#get progress for each device

		progresses = self.disk().file_get_contents("/tmp/pxpidevprogress")
		copyStatus = self.disk().file_get_contents("/tmp/pxpidevstatus")

		totalPercent = 0
		numDevices   = 1 #number of devices connected - do not set this to zero to avoid 0/0 case
		# check if the idevcopy is running 
		if(not (self.disk().psOn("idevcopy") or progresses)):
			return {"progress":0,"status":-1}
		if (not progresses): #file doesn't exist
			return {"progress":totalPercent, "status":copyStatus}
		progresses = progresses.strip().split("\n")
		numDevices = len(progresses)		
		#go through each one
		for progress in progresses:
			if(len(progress)<=5 or len(progress.split("-"))<2):
				continue #skip empty/erroneous lines in the file
			# extract percentage from the line (right before -)
			percentNum = int(progress.split("-")[0])
			totalPercent += percentNum
		return {"progress":int(totalPercent/numDevices),"status":copyStatus}
	#end dlprogress
	#######################################################
	# easter egg - prints the comparison features list 
	#######################################################
	def egg(self):
		r = """
		<div class="col_3">
			<!-- left-most side -->
		</div>
		<div class="col_6">
			<!-- center  -->
			<div class="row bold border-bottom large">
				<div class="col_6 bold">feature</div>
				<div class="col_3">NEW</div>
				<div class="col_3">OLD</div>
			</div>
			<div class="row">
				<div class="col_6 bold">UI/UX response speed</div>
				<div class="col_3">fast</div>
				<div class="col_3">slow</div>
			</div>
			<div class="row">
				<div class="col_6 bold">App updates</div>
				<div class="col_3">simple</div>
				<div class="col_3">complex</div>
			</div>
			<div class="row">
				<div class="col_6 bold">UI design</div>
				<div class="col_3">clean</div>
				<div class="col_3">poor</div>
			</div>
			<div class="row">
				<div class="col_6 bold">Encoder installation time</div>
				<div class="col_3">10 minutes (automatic)</div>
				<div class="col_3">2 - 4 hours (manual)</div>
			</div>
			<div class="row">
				<div class="col_6 bold">Encode start time</div>
				<div class="col_3">2-4 seconds</div>
				<div class="col_3">2 minutes</div>
			</div>
			<div class="row">
				<div class="col_6 bold">Post-encode delay</div>
				<div class="col_3">2-4 seconds</div>
				<div class="col_3">2-5 minutes</div>
			</div>
			<div class="row">
				<div class="col_6 bold">Encoder computer access</div>
				<div class="col_3">not required</div>
				<div class="col_3">required</div>
			</div>
			<div class="row">
				<div class="col_6 bold">Video source identification</div>
				<div class="col_3">automatic</div>
				<div class="col_3">manual</div>
			</div>
			<div class="row">
				<div class="col_6 bold">Accidental camera disconnect</div>
				<div class="col_3">handled - resume</div>
				<div class="col_3">not handled - content lost</div>
			</div>
			<div class="row">
				<div class="col_6 bold">3hr-game file size</div>
				<div class="col_3">3gb</div>
				<div class="col_3">4-5gb</div>
			</div>
			<div class="row">
				<div class="col_6 bold">Discrete clip export</div>
				<div class="col_3 green large"><i class="icon-ok"></i></div>
				<div class="col_3 red large"><i class="icon-remove"></i></div>
			</div>
			<div class="row">
				<div class="col_6 bold">Automatic encoder recognition</div>
				<div class="col_3 green large"><i class="icon-ok"></i></div>
				<div class="col_3 red large"><i class="icon-remove"></i></div>
			</div>
			<div class="row">
				<div class="col_6 bold">Audio</div>
				<div class="col_3 green large"><i class="icon-ok"></i></div>
				<div class="col_3 red large"><i class="icon-remove"></i></div>
			</div>
			<div class="row">
				<div class="col_6 bold">Timeline scrubbing</div>
				<div class="col_3 green large"><i class="icon-ok"></i></div>
				<div class="col_3 red large"><i class="icon-remove"></i></div>
			</div>
			<div class="row">
				<div class="col_6 bold">Pause encoding</div>
				<div class="col_3 green large"><i class="icon-ok"></i></div>
				<div class="col_3 red large"><i class="icon-remove"></i></div>
			</div>
			<div class="row">
				<div class="col_6 bold">Pinch-to-zoom gestures</div>
				<div class="col_3 green large"><i class="icon-ok"></i></div>
				<div class="col_3 red large"><i class="icon-remove"></i></div>
			</div>
			<div class="row">
				<div class="col_6 bold">Airplay</div>
				<div class="col_3 green large"><i class="icon-ok"></i></div>
				<div class="col_3 red large"><i class="icon-remove"></i></div>
			</div>
			<div class="row">
				<div class="col_6 bold">Slow motion playback</div>
				<div class="col_3 green large"><i class="icon-ok"></i></div>
				<div class="col_3 red large"><i class="icon-remove"></i></div>
			</div>
			<div class="row">
				<div class="col_6 bold">Source code security</div>
				<div class="col_3">PYC - no access</div>
				<div class="col_3">PHP - open source</div>
			</div>
			<div class="row">
				<div class="col_6 bold">Tag thumbnail delay</div>
				<div class="col_3">2-3 seconds</div>
				<div class="col_3">30 seconds</div>
			</div>
			<div class="row">
				<div class="col_6 bold">Tag accuracy</div>
				<div class="col_3">0-1 seconds</div>
				<div class="col_3">*10-30 seconds</div>
			</div>
			<div class="row">
				<div class="col_6 bold">Live video delay</div>
				<div class="col_3">5-6 seconds</div>
				<div class="col_3">12 seconds</div>
			</div>
			<div class="row">
				<div class="col_6 bold">OS Compatibility</div>
				<div class="col_3">OSX, Windows</div>
				<div class="col_3">Windows</div>
			</div>
			* on 1s HLS fragment size
		</div>
		<div class="col_3">
			<!-- right-most side -->
		</div>
		"""
		return r
	#end egg
	#######################################################
	# removes an event (sets deleted = 1)
	# delets all content associated with it
	#######################################################
	def evtdelete(self):
		import os
		io = self.io()
		folder = io.get('name') #name of the folder containing the content
		event  = io.get('event') #hid of the event  stored in the database
		if((not event) or (len(event)<5) or ('\\' in event) or ('/' in event)):
			#either event was not specified or there's invalid characters in the name 
			#e.g. user tried to get clever by deleting other directories
			return self._err("Invalid event")
		# remove the event from the database
		db = self.dbsqlite(self.wwwroot+"_db/pxp_main.db")
		sql = "UPDATE `events` SET `deleted`=1 WHERE `hid` LIKE ?"
		db.query(sql,(event,))
		db.close()
		# remove the content
		success = True
		if(os.path.exists(self.wwwroot+folder)):
			success = not os.system("rm -r "+self.wwwroot+folder)
		return {"success":success}
	#end evtdelete
	#######################################################
	# returns encoder status as a string, 
	# either json or plain text (depending on textOnly)
	#######################################################
	def encoderstatus(self,textOnly=True):
		state = self._encState()
		if(state==1):
			status = "live"
		elif(state==2):
			status = "paused"
		elif(state==-1):
			status = "unknown"
		# elif(os.path.exists(self.wwwroot+'live/video/list.m3u8')): #no need for vod mode 
		# 	status = "vod"
		else:
			status = "off"
		# status = "live"
		if (textOnly):
			return status
		return {"status":status,"code":state}
	#end encoderstatus
	def encoderstatjson(self):
		return self.encoderstatus(textOnly = False)
	#######################################################
	#pauses a live encode
	#######################################################
	def encpause(self):
		import os
		msg = ""
		try:
			# rez = os.system(self.wwwroot+"_db/encpause ")
			rez = os.system("echo '3' > /tmp/pxpcmd")
			# add entry to the database that the encoding has paused
			msg = self._logSql(ltype="enc_pause",dbfile=self.wwwroot+"live/pxp.db",forceInsert=True)
		except Exception as e:
			msg = str(e)
			rez = False
		# rez = False
		return {"success":not rez,"msg":msg}
	#end encpause
	#######################################################
	#resumes a paused encode
	#######################################################
	def encresume(self):
		import os
		msg = ""
		try:
			# rez = os.system(self.wwwroot+"_db/encresume ")
			rez = os.system("echo '4' > /tmp/pxpcmd")
			# add entry to the database that the encoding has paused
			msg = self._logSql(ltype="enc_resume",dbfile=self.wwwroot+"live/pxp.db",forceInsert=True)
		except Exception as e:
			rez = False
		# rez = False
		return {"success":not rez}
	#end encresume
	#######################################################
	#shuts down the encoder
	#######################################################
	def encshutdown(self):
		import os
		import getpass
		msg = ""
		try:
			self.encstop()
			rez = os.system("sudo /sbin/shutdown -h now")
		except Exception as e:
			rez = False
		# rez = False
		return {"success":not rez, "msg":rez}
	#end encresume
	#######################################################
	#starts a new encode
	#######################################################
	def encstart(self):
		import os
		from datetime import datetime as dt
		from time import time as tm
		try:
			#make sure not overwriting an old event
			if(os.path.exists(self.wwwroot+"live/evt.txt")):
				self._postProcess()
			#make sure the 'live' directory was initialized
			if(not os.path.exists(self.wwwroot+"live/thumbs")):
				self._initLive()							
			io = self.io()
			# get the team and league informaiton
			hmteam = io.get('hmteam')
			vsteam = io.get('vsteam')
			league = io.get('league')
			if not (hmteam and vsteam and league):
				return self._err("Please specify teams and league")
			# make sure everything is off before starting a new stream
			os.system("/usr/bin/killall mediastreamsegmenter")
			#send 2 kill signals to ffmpeg
			os.system("/bin/kill `ps ax | grep \"ffmpeg -f mpegts -i udp://\" | grep 'grep' -v | awk '{print $1}'`")
			os.system("/bin/kill `ps ax | grep \"ffmpeg -f mpegts -i udp://\" | grep 'grep' -v | awk '{print $1}'`")

			# start the capture
			# rez = os.system(self.wwwroot+"_db/encstart >/dev/null &")
			rez = os.system("echo '1' > /tmp/pxpcmd")

			# create new event in the database
			# get time for hid and for database
			timestamp = dt.fromtimestamp(tm()).strftime('%Y-%m-%d %H:%M:%S')
			evthid = self.enc().sha(timestamp) #event hid
			db = self.dbsqlite(self.wwwroot+"_db/pxp_main.db")
			sql = "INSERT INTO `events` (`hid`,`date`,`homeTeam`,`visitTeam`,`league`) VALUES(?,?,?,?,?)"
			db.query(sql,(evthid,timestamp,hmteam,vsteam,league))
			# get hid of the teams
			# home team
			sql = "SELECT `hid` FROM `teams` WHERE `name` LIKE ?"
			db.query(sql,(hmteam,))
			hmteamHID = db.getasc()
			hmteamHID = hmteamHID[0]['hid']
			# visitor team
			sql = "SELECT `hid` FROM `teams` WHERE `name` LIKE ?"
			db.query(sql,(vsteam,))
			vsteamHID = db.getasc()
			vsteamHID = vsteamHID[0]['hid']
			# get hid of the leagu
			sql = "SELECT `hid` FROM `leagues` WHERE `name` LIKE ?"
			db.query(sql,(league,))
			leagueHID = db.getasc()
			leagueHID = leagueHID[0]['hid']
			db.close()
			# add entry to the database that the encoding has started
			msg = self._logSql(ltype="enc_start",lid=(hmteamHID+','+vsteamHID+','+leagueHID),dbfile=self.wwwroot+"live/pxp.db",forceInsert=True)
			#the name of the directory will be YYYY-MM-DD_HH-MM-SS
			evtName = dt.fromtimestamp(tm()).strftime('%Y-%m-%d_%H-%M-%S')+'_H'+hmteam[:3]+'_V'+vsteam[:3]+'_L'+league[:3]
			#store the event name (for processing when it's stopped)
			cmd = "echo '"+evtName+"' > "+self.wwwroot+"live/evt.txt"
			rez = not os.system(cmd)
			msg = ""
		except Exception as e:
			import sys
			return self._err(str(e)+' '+str(sys.exc_traceback.tb_lineno))
		return {"success":rez,"msg":msg}
	#end encstart
	#######################################################
	#stops a live encode
	#######################################################
	def encstop(self):
		import os
		from time import sleep
		msg = ""
		try:
			# rez = os.system(self.wwwroot+"_db/encstop")
			rez = os.system("echo '2' > /tmp/pxpcmd")
			os.system("/usr/bin/killall mediastreamsegmenter")
			#send 2 kill signals to ffmpeg
			os.system("/bin/kill `ps ax | grep \"ffmpeg -f mpegts -i udp://\" | grep 'grep' -v | awk '{print $1}'`")
			os.system("/bin/kill `ps ax | grep \"ffmpeg -f mpegts -i udp://\" | grep 'grep' -v | awk '{print $1}'`")
			msg = self._logSql(ltype="enc_stop",dbfile=self.wwwroot+"live/pxp.db",forceInsert=True)
			# rename the live directory to the proper event name
			sleep(5) #wait for 5 seconds for ffmpeg to finish its job
			self._postProcess()
		except Exception as e:
			rez = False
			msg=str(e)
		return {"success":not rez,"msg":msg}
	#end encstop
	#######################################################
	# returns the input video settings
	#######################################################
	def getcamera(self):
		# check if streamer app is running
		appon = self.disk().psOn('pxpStream')
		cfg = self.disk().file_get_contents(self.wwwroot+"_db/.cam")
		if appon and cfg:
			return {"success":True,"msg":cfg,"encoder":self.encoderstatus()}
		return {"success":True,"msg":"No camera","encoder":self.encoderstatus()}
	#end getcamera
	#######################################################
	# returns list of the past events in array
	#######################################################
	def getpastevents(self):
		return {"events":self._listEvents()} #send it in dictionary format to match the sync2cloud format
	#end getpastevents
	#######################################################
	#returns all the game tags for a specified event
	#######################################################
	def gametags(self):
		strParam = self.uri().segment(3,"{}")
		jp = json.loads(strParam)
		if not ('user' in jp and 'event' in jp and 'device' in jp):
			return self._err("Specify user, event, and device")

		#get user id
		usr = jp['user']
		#device ID
		dev = jp['device']
		#event
		evt = jp['event']
		return self._syncTab(user=usr, device=dev, event=evt, allData = True)
	#######################################################
	#returns true if there is an active feed present
	#######################################################
	def islive(self):
		hlsPresent = os.path.exists(self.wwwroot+'live/video/list.m3u8')
		return {"success":(self._encState()==1) and hlsPresent}
	def login(self, sess):
		try:
			io = self.io()
			email = io.get("email")
			passw = io.get("pass")
			if not (email and passw):
				return self._err("Email and password must be specified")
			encEm = self.enc().sha(email)
			encPs = self._hash(passw)
			# make sure the encoder has been initialized
			if not self._inited():
				# it wasn't initialized yet - activate it in the cloud
				res = self._init(email,passw)
				if (not res==1):
					return self._err(res)
				# activation was successful, perform a sync
				self._syncEnc(encEm,encPs)
			#if not inited

			# check if user is in the database
			db = self.dbsqlite(self.wwwroot+"_db/pxp_main.db")
			sql = "SELECT `hid` FROM `users` WHERE `email` LIKE ? AND `password` LIKE ?"
			db.query(sql,(email,encPs))
			rows = db.getrows()
			if(len(rows)<1):
				return self._err("Invalid email or password")
			# log him in
			#first, make sure there are no old session variables
			sess.destroy()
			sess.start(glob=self, expires=24*60*60,cookie_path="/")
			usrData = rows[0]
			sess.data['user']=usrData[0] #user hid
			# store plain text email in the session (to display logged in user)
			sess.data['email']=email
			# encrypted email
			sess.data['ee']=encEm
			# encrypted password
			sess.data['ep']=encPs
		except Exception as e:
			import sys
			return self._err(str(e)+' '+str(sys.exc_traceback.tb_lineno))
		# return {io.get("email"):io.get("pass")}
		return {"success":True}
	#logs the user out
	#session variable must be passed here
	#initializing it in this method opens it as read-only(??)
	def logout(self, sess):
		sess.data['user']=False
		sess.data['email']=False
		# del sess.data['user']
		return {"success":True}
	#######################################################
	# prepares the download - converts tags to a plist
	#######################################################
	def prepdown(self):
		import pty
		# pty.fork()
		io = self.io()
		event = io.get('event')
		try:
			# # remove old plist if it exists
			# if(os.path.exists(self.wwwroot+event+'/tags.plist')):
			# 	os.remove(self.wwwroot+event+'/tags.plist')
			if not event: #event was not specified
				return self._err()
			# make sure it has no : or / \ in the name
			if('/' in event or '\\' in event): #invalid name
				return self._err()
			db = self.dbsqlite(self.wwwroot+event+'/pxp.db')
			# select all even-type tags (deleted are odd, so won't be downloaded)
			db.qstr('SELECT * FROM `tags` WHERE  (`type` & 1) = 0')
			# self.str().pout("")
			xmlOutput = '<?xml version="1.0" encoding="UTF-8"?>\n'+\
						'<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">\n'+\
						'<plist version="1.0">\n<dict>\n'
			# types of fields stored in xml .plist
			# since fields are declared as e.g.: <key>fieldName</key> <string>fieldvalue</string>
			fieldTypes = {'bookmark':'integer',	'coachpick':'integer',
						'colour':'string', 'comment':'string',
						'displaytime':'string',	'duration':'string',
						'event':'string', 'id':'integer',
						'name':'string', 'playerpick':'integer',
						'rating':'integer', 'starttime':'real',
						'time':'real', 'type':'integer',
						'url':'string',	'user':'string', 'teleurl':'string'
						}
			# get each tag, format it and output to xml
			for t in db.getasc():
				# format the tag (get thumbnail image, telestration url, etc.)
				tag = self._tagFormat(event=event,tag=t)
				# add tag key
				xmlOutput+='\t<key>'+str(tag['id'])+'</key>\n'
				# add tag entries
				xmlOutput+='\t<dict>\n'
				# get standard fields into the plist
				# go through each field and add it in the proper format
				for field in tag:
					if ((field in fieldTypes) and (field in tag)):
						xmlOutput+='\t\t<key>'+field+'</key>\n'
						xmlOutput+='\t\t<'+fieldTypes[field]+'>'+str(tag[field])+'</'+fieldTypes[field]+'>\n'
				# add unique fields into the plist
				xmlOutput+='\t\t<key>deleted</key>\n'
				xmlOutput+='\t\t<'+str(tag['deleted']).lower()+'/>\n'
				xmlOutput+='\t\t<key>own</key>\n'
				xmlOutput+='\t\t<'+str(tag['own']).lower()+'/>\n'
				# output lines
				xmlOutput+='\t\t<key>line</key>\n'
				xmlOutput+='\t\t<array>\n'
				for line in tag['line']:
					xmlOutput+='\t\t\t<string>'+line+'</string>\n'
				xmlOutput+='\t\t</array>\n'
				# output period
				xmlOutput+='\t\t<key>period</key>\n'
				xmlOutput+='\t\t<array>\n'
				for period in tag['period']:
					xmlOutput+='\t\t\t<string>'+period+'</string>\n'
				xmlOutput+='\t\t</array>\n'
				# output strength
				xmlOutput+='\t\t<key>strength</key>\n'
				xmlOutput+='\t\t<array>\n'
				for strength in tag['strength']:
					xmlOutput+='\t\t\t<string>'+strength+'</string>\n'
				xmlOutput+='\t\t</array>\n'
				# output player
				xmlOutput+='\t\t<key>player</key>\n'
				xmlOutput+='\t\t<array>\n'
				for player in tag['player']:
					xmlOutput+='\t\t\t<string>'+player+'</string>\n'
				xmlOutput+='\t\t</array>\n'
				# finish tag
				xmlOutput+='\t</dict>\n'
			# finish the xml
			xmlOutput += '</dict>\n</plist>'
			db.close()
			# plist file is ready, write it to the folder:
			self.disk().file_set_contents(self.wwwroot+event+'/tags.plist',xmlOutput)
			return {"success":True}
		except Exception as e:
			import sys 
			return self._err(str(sys.exc_traceback.tb_lineno)+' '+str(e))
	#end prepdown
	def sync2cloud(self,sess):
		try:
			if not ('ee' in sess.data and 'ep' in sess.data):
				return {"success":False,"action":"reload"}
			#the dict({},**{}) is to combine 2 dictionaries into 1: 
			#{"success":True/False} and {"action":"reload"})
			return dict(self._syncEnc(sess.data['ee'],sess.data['ep']),**{"action":"reload"})
		except Exception as e:
			# import sys
			# self._x(sys.exc_traceback.tb_lineno)
			# print e
			pass
	#######################################################
  	#get any new events that happened since the last update (e.g. new tags, removed tags, etc.)
	#######################################################
	def syncme(self):
		strParam = self.uri().segment(3,"{}")
		jp = json.loads(strParam)
		if not ('user' in jp and 'event' in jp and 'device' in jp):
			return self._err("Specify user, event, and device")

		#get user id
		usr = jp['user']
		#device ID
		dev = jp['device']
		#event
		evt = jp['event']
		return self._syncTab(user=usr, device=dev, event=evt)
	#######################################################
	#return list of teams in the system with team setups
	#######################################################
	def teamsget(self):
		try:
			db = self.dbsqlite(self.wwwroot+'_db/pxp_main.db')
			result = {"teams":{},"teamsetup":{},"leagues":{}}
			# get the teams from the database
			sql = "SELECT * FROM `teams`"
			db.qstr(sql)
			#convert this data to json-readable:
			# will be similar to : 
			# "0ade7c2cf97f75d009975f4d720d1fa6c19f4897": {"txt_name": "Real_Madrid", "hid": "0ade7c2cf97f75d009975f4d720d1fa6c19f4897", "name": "Real Madrid"}
			for team in db.getasc():
				result['teams'][team['hid']] = {}
				for field in team:
					result['teams'][team['hid']][field] = team[field]

			# get team setup (players, positions, etc.)
			sql = "SELECT * FROM `teamsetup` ORDER BY `team`, `jersey`"
			db.qstr(sql)
			# get players for each team
			# will be {"team_HID":[{p1},{p2},{p3}]} where pX is {'player':'13','jersey':55,....}
			idx = 0
			for player in db.getasc():
				# print player
				# print "--------------\n<br>"
				# if the team was not added to the array yet, add it
				if(not player['team'] in result['teamsetup']):
					result['teamsetup'][player['team']] = []
				# create a blank player setup for this team (an empty dictionary - will be populated in the for loop after)
				result['teamsetup'][player['team']].append({})
				# simply populate the player setup dictionary that was just added
				for field in player:
					#index of the last player (the new one)
					lastPlayerIdx = len(result['teamsetup'][player['team']])-1
					result['teamsetup'][player['team']][lastPlayerIdx][field] = player[field]

			sql = "SELECT * FROM `leagues`"

			db.qstr(sql)
			for league in db.getasc():
				result['leagues'][league['hid']] = {}
				for field in league:
					result['leagues'][league['hid']][field] = league[field]
			db.close()
		except Exception as e:
			import sys
			# self._x("")
			# print e
			# print sys.exc_traceback.tb_lineno
			return self._err(str(e)+' '+str(sys.exc_traceback.tb_lineno))
		return result
	#######################################################
	#modify a tag - set as coachpick, bookmark, etc
	#######################################################
	def tagmod(self):
		strParam = self.uri().segment(3,"{}")
		jp = json.loads(strParam)
		if not ('user' in jp and 'event' in jp and 'id' in jp):
			return self._err("Specify user, event, and tag id")
		#determine the info that user wants to update
		params = ()
		sqlInsert = []
		tid = jp['id']
		user = jp['user']
		event = jp['event']
		#user info, tag id and event name are not modifications - remove those from the dictionary
		del jp['id']
		del jp['user']
		del jp['event']
		# go through all json parameters (tag mod's) and check 
		# which modifications should be applied
		bookmark = False
		for mod in jp:
			#modifying starttime (extending the beginning of the tag)
			if (mod=='starttime' and float(jp[mod])<0):
				value = 0
			if (mod=='delete'):
				#when deleting a tag, simply change type to 3
				sqlInsert.append("`type`=?")
				params +=(3,)
			else:
				#any other modifications, just add them to the sql query
				bookmark = bookmark or ((mod=='bookmark') and (jp['bookmark']=='1'))
				sqlInsert.append("`"+mod+"`=?")
				params +=(jp[mod],)
		#end for mod in jp
		if len(sqlInsert)<1:#nothing was specified 
			return self._err()
		# parameters to add to the sql - tag id (no need to check user at the moment)
		params += (tid,)
		#update the tag
		sql = "UPDATE `tags` SET "+(', '.join(sqlInsert))+" WHERE id=?"
		#make sure the database exists
		if(not os.path.exists(self.wwwroot+event+'/pxp.db')):
			return self._err()
		db = self.dbsqlite(self.wwwroot+event+'/pxp.db')
		# if(not bookmark):#do not mark as bookmark in the database - only give the user the ability to download it, no need for everyon else to get this file
			#update the tag info in the database
		success = db.query(sql,params) and db.numrows()>0
		# else:
			# success = True
		if success and not bookmark:
			#add an entry to the event log that tag was updated or deleted
			success = self._logSql(ltype='mod_tags',lid=tid,uid=user,db=db)
		if success:
			# sql = "SELECT * FROM `tags` WHERE `id`=?"
			# db.query(sql,(tid,))
			# tag = db.getasc()
			db.close() #close db here because next statement will return
			if (bookmark):
				# user wants to make a bookmark - extract the video
				success = success and self._extractclip(tagid=tid,event=event)
			return self._tagFormat(event=event, user=user, tagID=tid)
		db.close()
		return {'success':success}
	#end tagmod
	#######################################################
	#creates a new tag
	#information that needs to be submitted in json form:
	# {
	# 	'event':'<event>',
	# 	'name':'<tag name>',
	# 	'id':'[tag_id]',
	# 	'user':'user_hid',
	# 	'tagtime':'<time of the tag in seconds>',
	# 	'colour':'<tag colour>',
	# 	'period':'<period number>',
	# 	['coachpick':'<0/1>'],
	# 	['type':'<0/1/2/3...>'], 
	#	['bookmark':'<0/1>'],
	# 	[<other options may be added>]
	# }
	#event can be an HID of an event or 'live' for live event
	#######################################################
	def tagset(self, tagStr=False):
		#tag types:
		#NOTE: odd-numbered tag types do not get thumbnails!!

		#default			= 0
		#start line/zone	= 1
		#stop line/zone		= 2
		#deleted			= 3 - this one shouldn't happen on tagSet
		#telestration 		= 4
		#player start shift	= 5
		#player end shift	= 6
		#period/half start	= 7
		#period/half end 	= 8
		#strength start 	= 9
		#strength end 		= 10
		import json, os, sys
		tagVidBegin = self.tagVidBegin
		if (not tagStr):
			tagStr = self.uri().segment(3)
		#just making sure the tag was supplied
		if(not tagStr):
			return self._err("Tag string not specified")
		sql = ""
		# self._x(tagStr)
		# return self._err(os.environ)
		db = self.dbsqlite()
		try:
			# convert the json string to dictionary
			t = json.loads(tagStr)
			# t might be an array of dictionaires (size 1) or a dictionary itself
			if (len(t)>0 and (not 'name' in t)):
				t = t[0] # this is an array of dictionaries - get the first element
			if (not 'event' in t):
				return self._err("Specify event") #event was not defined - can't open the database
			if (not os.path.exists(self.wwwroot+t['event']+'/pxp.db')):
				# this is the first tag in the event 
				self.disk().mkdir(self.wwwroot+t['event'])
				# copy the template db for tags
				self.disk().copy(self.wwwroot+'_db/event_template.db', self.wwwroot+t['event']+'/pxp.db')
			db.open(self.wwwroot+t['event']+'/pxp.db')
			db.transBegin() #in case we need to roll it back later
			success = 1
			if(not 'type' in t):
				t['type'] = 0 #if type is not defined set it to default
			else:
				t['type'] = int(t['type'])
			if(not 'coachpick' in t): #will be only set if coach tags it 
				t['coachpick']=0

			#a new tag was received - add it
			# TODO: check if this user already has a tag with the same name in the same place
			if(t['type']&1): #odd types are tag 'start'
				#tag 'start' received - stop the previous tag
				#simply update the duration and the type of the start tag
				#also set the starttime to begin when user tagged it, not at the usual -10 seconds
				# for line tagging, if it's line_d or line_f, treat them accordingly
				if(t['type']==1 and t['line'][:4]=='line'):
					#this is a line tag - end previous line (e.g. if this is line_f then end the last line_f, not line_d)
					extraVars = (t['line'][:6]+"%",)
					sqlAddVal = " AND line LIKE ?"
				else:
					extraVars = ()
					sqlAddVal = ""
				sql = "UPDATE tags SET starttime=time, duration=CASE WHEN (?-time)>0 THEN (?-time) ELSE 0 END, type=? WHERE type=?"+sqlAddVal
				success = success and db.query(sql,(t['tagtime'],t['tagtime'],t['type']+1,t['type'])+extraVars)
				# success = success and db.numrows()>0
			#end if type is odd		
			#add the tag to the database
			if (t['type']&1): #start tags are odd numbers and have starttime same as tagtime
				startTime = float(t['tagtime'])
			else:
				startTime = float(t['tagtime'])-tagVidBegin
			#make sure starttime is not below 0
			if startTime < 0:
				startTime = 0

			sqlVars = (t['name'], t['user'], startTime, t['type'], t['tagtime'], t['colour'], t['coachpick'])
			if('duration' in t):
			# if duration was specified, add it to the sql
				sqlAddVal = ",?" #added to the sql values
				sqlVars += (t['duration'],) #added to the variables tuple
				sqlAddFld = ", duration"
				if(t['duration']==0):
					# duration is zero - make starttime same as the time
					startTime = t['tagtime']
			elif(t['type']&1):
			#for a start tag, the duration should be set to zero (unless otherwise specified - previous if statement)
				sqlAddVal = ",?"
				sqlVars += (0,)
				sqlAddFld = ", duration"
			else:
			# duration not specified - just leave the sql unchanged
				sqlAddVal = ""
				sqlAddFld = ""
			# if players were specified add them to the sql as well
			if('player' in t):
				if(isinstance(t['player'],list)):
					#players is an array, join it with commas
					sqlVars += (",".join(t['player']),)
				else:
					#single player is given, just add the value as is
					sqlVars += (t['player'],)
				sqlAddFld += ", player"
				sqlAddVal += ", ?"
			#check if lines/zones were specified (ignore it if the tag type is not 'line')
			if(('line' in t) and (t['type']==1)):
				sqlVars += (t['line'],)
				sqlAddFld += ", line"
				sqlAddVal += ", ?"
			#if period was set (0, 1, 2...), add it(ignore it if the tag type is not 'period/half')
			if(('period' in t) and (t['type']==7)):
				sqlVars += (t['period'],)
				sqlAddFld += ", period"
				sqlAddVal += ", ?"
			#if strength was set (i.e. 5vs6 etc.), add it (ignore it if the tag type is not 'strength')
			if(('strength' in t) and (t['type']==9)):
				sqlVars += (t['strength'],)
				sqlAddFld += ", strength"
				sqlAddVal += ", ?"
			#if zone was set (i.e. OZ, NZ, DZ for hockey), add it
			if('zone' in t):
				sqlVars += (t['zone'],)
				sqlAddFld += ", zone"
				sqlAddVal += ", ?"
			# create a query to add the new tag
			sql = "INSERT INTO tags (name, user, starttime, type, time, colour, coachpick"+sqlAddFld+") VALUES(?, ?, ?, ?, ?, ?, ?"+sqlAddVal+")"
			#run it
			success = success and db.query(sql,sqlVars)
			#get the id of the newly created tag
			lastID = db.lastID()

			if(not success):#something went wrong, roll back the sql statement
				db.rollback()
				return self._err()
			# get tag time, tag duration and video start time (of the tag)
			sql = "SELECT time, duration, starttime FROM tags WHERE id=?"
			success = success and db.query(sql,(lastID,))
			tmp = db.getrow()
			if(tmp):
				t['tagtime'] = tmp[0]
				t['duration'] = tmp[1]
				startTime = tmp[2]
			else:
				# could not get the tag info - probably invalid tag ID (should never happen)
				db.rollback()
				return self._err()

			#get the time of the current tag
			tagTime = t['tagtime']
			tagOut = False
			# if((t['type']==0) or (t['type']==4)):
			#only normal tags and telestrations should be updated with periods and logged in the database log

			#find a line/third  corresponding to this tag - 
			#either the tag is being created in the past and its 
			#time falls within the duration of the line tag, 
			#or it's being created live and there is a line/third active right now
			#name contains the line designation, i.e. d_2, or o_1

			types = {
				#numbers are: [stop, start] codes for line, period, strength
				"line"		: ['2','1'], 
				"player"	: ['6','5'],
				"period"	: ['8','7'],
				"strength"	: ['10','9']
			}
			#go through every type of metadata for each tag (e.g. line, period)
			#and update that attribute for the current tag based on what was the last line/zone, period/half etc. selected
			# self._x("")
			for tp in types:
				if (tp in t): #this 
					continue
				#get the sql query with proper types
				sql = "SELECT `"+tp+"` FROM `tags` WHERE `starttime`<=? AND ((`type`="+types[tp][0]+" AND (`starttime`+`duration`)>=?) OR (`type`="+types[tp][1]+" AND `duration`=0)) ORDER BY `starttime` "
				# print sql+' '+str(tagTime)+" \n<br/>"
				db.query(sql,(tagTime,tagTime))
				rows = db.getrows()
				# return
				#array with lines, or players or whatever was selected
				dataArray = []
				#select any active lines (or zones, or thirds at the time of the tag)
				#there can be multiple players or lines per tag
				for row in rows:
					if (not row[0]==None):
						dataArray.append(row[0])
				if (len(dataArray)>0): #make sure there are elements in the array, otherwise the next query will cause the entire transaction to fail
					sqlVals = ",".join(dataArray)
					sql = "UPDATE `tags` SET `"+tp+"`=? WHERE `id`=?"
					db.query(sql,(sqlVals,lastID))
			#for tp in types

			tagOut = {} # this dictionary will be returned

			if (t['type']&1) : #odd types are start of a new line/zone/etc. - return the last line/zone/etc. that just ended
				tagTypes = {1:'line',5:'player',7:'period',9:'strength'}
				# if the tag type is line then the lines can be offensive/defensive, select that
				if(t['type']==1 and t['line'][:4]=='line'):
					#this is a line tag - end previous line (e.g. if this is line_f then end the last line_f, not line_d)
					tagTypeString = t['line'][:6]+'%'
				else:
					tagTypeString = '%'
				# get the last active line/player/period, etc.
				sql = "SELECT `id` FROM `logs` WHERE `type` LIKE 'current_"+tagTypes[t['type']]+"' AND `id` LIKE ? ORDER BY `logID` DESC"
				db.query(sql,(tagTypeString,))

				rows = db.getrows()
				if(len(rows)>0):#previous line/zone/etc was specified
					lastEntry = rows[0][0]
					# get id of the tag containing that entry
					sql = "SELECT IFNULL(MAX(`id`),0) FROM `tags` WHERE `"+tagTypes[t['type']]+"` LIKE ? AND `type`=?"
					db.query(sql,(lastEntry,t['type']+1))
					lastID = db.getrows()
					if(len(lastID)>0):
						lastID = lastID[0][0]
					else:
						lastID = 0
				else:#this is a first time tagging line/zone/etc
					lastID = 0
				# set new line/zone/period/etc.
				success = success and self._logSql(ltype="current_"+tagTypes[t['type']],lid=t[tagTypes[t['type']]],uid=t['user'],db=db)
				# return {"success":success}
			#if odd type
			if(success):
				# get all the details about the tag that was created (or last line/period/etc. if a new line/period was started)
				db.commit()
			else:
				db.rollback()
			# cleanup
			if(t['type'] & 1):
				# remove nonsensical tags (tags with short duration)
				# make sure not to delete current line/period/strength, etc. (odd type tags)
				sql = "DELETE FROM `tags` WHERE (`duration`<5) AND ((`type` & 1) = 0) AND (NOT (`type`=4))"
				db.qstr(sql)
			#if type is odd

			# check if the tag that was just created wasn't deleted in the cleanup (will happen for tags of less than 5s long)
			sql = "SELECT * FROM `tags` WHERE `id`=?"
			db.query(sql,(lastID,))
			if(success and lastID and len(db.getrows())>0): 
				#create a thumbnail for the tag video - only do this when a tag is created
				#i.e. tagStart is not technically a "tag" - wait till the Stop is set, then make a thumbnail
				#this only happens when it's a first 'start' tag - since every other 'start' tag will 
				#automatically stop the previous start 'tag'

				# get the tag information
				tagOut = self._tagFormat(event=t['event'], user=t['user'], tagID=lastID, db=db)	
				if 'success' in tagOut:
					if not tagOut['success']:
						return tagOut
				t['tagtime'] = tagOut['time']
				vidSegmfileName = self._thumbName(t['tagtime'],event=t['event'])
				#create a tag image if it doesn't exist already
				pathToEvent = self.wwwroot+t['event']+'/'
				imgFile = pathToEvent+"thumbs/tn"+str(lastID)+".jpg"
				if(not os.path.exists(imgFile)):
					vidFile = pathToEvent+"video/"+str(vidSegmfileName)
					# self._thumbName(t['tagtime'],number=True)
					# roundedSec = int(self._thumbName(t['tagtime'],number=True,event=t['event']))
					#get the accurate time within the .ts file 
					#TODO: should be more accurate but for some reason ffmpeg only grabs first frame ??
					# sec = (t['tagtime']/0.984315-roundedSec)*0.984315 
					# if sec<0: #sanity check - should never happen
					# do it at 0 for now, we'll figure out how to increase accuracy later on 
					sec = 0
					self._mkThumb(vidFile, imgFile, sec)
				#log that a tag was created
				success = success and self._logSql(ltype="mod_tags",lid=lastID,uid=t['user'],db=db)
			#if lastID
			if not tagOut: #tag will not be returned - happens when line/zone/etc. is tagged for the first time
				tagOut = {"success":success}
			return tagOut
		except Exception as e:
			db.rollback()
			return self._err(str(sys.exc_traceback.tb_lineno)+' '+str(e))
	#end tagSet()
	#######################################################
	def teleset(self):
		import sys, Image
		io = self.io()
		try:
			# create a tag first
			tagStr = str(io.get("tag"))
			event = json.loads(tagStr)['event']
			t = self.tagset(tagStr)
			#upload a file with the tag name
			imgID = str(t['id'])
			io.upload(self.wwwroot+event+"/thumbs/tl"+imgID+".png")
			# update the thumbnail with the telestration overlay
			# background is the thumbnail
			bgFile = self.wwwroot + event+"/thumbs/tn"+imgID+".jpg"
			# overlay is the png telestration
			olFile = self.wwwroot + event+"/thumbs/tl"+imgID+".png"			
			# open the image files
			bg = Image.open(bgFile)
			ol = Image.open(olFile)

			# get the size of the thumbnail
			(wd,hg) = bg.size
			# resize the overlay to match thumbnail
			ol = ol.resize((wd, hg), Image.ANTIALIAS)
			# overlay the tags
			bg = bg.convert("RGBA")
			ol = ol.convert("RGBA")
			bg.paste(ol, (0, 0), ol)
			bg.save(bgFile,quality=100)
			return t #already contains telestration url
		except Exception as e:
			# print sys.exc_traceback.tb_lineno
			# print e
			return self._err("No tag info specified")
###############################################
##	           utility functions             ##
###############################################
	#######################################################
	# XORs config file (simple 'encryption') to prevent tampering
	#######################################################
	def _cfgGet(self, cfgDir):
		cfgFile = cfgDir+".cfg"
		saltedKey = "3b2b2bcfee23d8377a3828fe3c155a868377a38"
		# remove last 7 characters from the key
		# this is in case someone disassembles the python 
		# and tries to use the key string as they key to the config file
		key = saltedKey[:-7] 
		# check if file exists
		if(not os.path.exists(cfgFile)):
			return ""
		# get the encrypted text
		encText = self.disk().file_get_contents(cfgFile)
		# make the key and the string equal length
		key = self.enc().repeat_str(key,len(encText))
		# xor it to decrypt the file
		decLines = self.enc().sxor(encText,key).split("\n")
		# return the string
		if (decLines[0]==".min config file"):
			return decLines
		return ""

	#######################################################
	# XORs config file (simple 'encryption') to prevent tampering
	#######################################################
	def _cfgSet(self, cfgDir,lines):
		# parameters are in this function so that user can't view them with dir() function
		cfgFile = cfgDir+".cfg"
		saltedKey = "3b2b2bcfee23d8377a3828fe3c155a868377a38"
		key = saltedKey[:-7] 
		try:
			# merge the list items together as a single string with end-line characters
			decText = ".min config file\n"+"\n".join(lines)
			# make the key and the string equal length
			key = self.enc().repeat_str(key,len(decText))
			# encrypt the text
			encText = self.enc().sxor(decText,key)
			# overwite the config file
			f = open(cfgFile,"w")
			f.write(encText)
			f.close()
			return True
		except:
			return False
	#######################################################
	#cleans a string for sqlite query (doubles " quotes)
	#######################################################
	def _cln(self, text):
		import string
		return string.replace(text,'"','""')
	#end cln	
	def _diskStat(self):
		import os
		st = os.statvfs("/")
		diskFree = st.f_bavail * st.f_frsize
		diskTotal = st.f_blocks * st.f_frsize
		diskUsed = diskTotal-diskFree
		diskPrct = int(diskUsed*100/diskTotal)
 		return {"total":self._sizeFmt(diskTotal),"free":self._sizeFmt(diskFree),"used":self._sizeFmt(diskUsed),"percent":str(diskPrct)}
	#######################################################
	#returns encoder state (0 - off, 1 - live, 2 - paused)
	#######################################################
	def _encState(self):
		# using file as means to transfer status works better than sockets as there are no timeouts with these
		return int(self.disk().file_get_contents("/tmp/pxpstreamstatus")) #int(self.disk().sockRead(udpPort=2224,timeout=0.5))
	#end encState
	def _err(self, msgText=""):
		return {"success":False,"msg":msgText}
	#######################################################
	# extract number from a string (returns 0 if no numbers found)
	#######################################################
	def _exNum(self, text):
		import re
		try:
			return int(re.search('\d+', text).group())
		except:
			return 0
	#end exNum
	#######################################################
	# extracts video clip and saves it as mp4 file (for bookmarks)
	#######################################################
	def _extractclip(self, tagid, event):
		from random import randrange
		import glob
		# the process is as follows:
		# 1) grab .ts files that encompass the tag duration
		# 2) concatenate them
		# 3) resize and convert to 540xHHH (keeping aspect ratio) mp4 file
		# 4) convert it back to .ts file 
		# 5) concatenate the 540x ad and the 540x video clip into one .ts
		# 6) convert the resulting .ts into mp4 file
		# get tag ID
		db = self.dbsqlite(self.wwwroot+event+'/pxp.db')
		# get the time from the database
		sql = "SELECT starttime, duration FROM tags WHERE id=?"
		db.query(sql,(tagid,))
		row = db.getrow()
		db.close()
		startTime = float(row[0])
		endTime   = float(row[0])+float(row[1])
		strFile = self._thumbName(startTime,number=True,event=event) #index of the starting .ts file
		endFile = self._thumbName(endTime,number=True,event=event) #index of the ending .ts file

		bigTsFile = self.wwwroot+event+"/video/vid"+str(tagid)+".ts" #temporary .ts output file containing all .ts segments 
		bigMP4File = self.wwwroot+event+"/video/vid_"+str(tagid)+".mp4" #converted mp4 file (low res)
		tempTs = self.wwwroot+event+"/video/int_"+str(tagid)+".ts"#TS file containing resized video clip


		vidFiles = "" #small .ts files to concatenate
		#select .ts files that should be merged
		for i in range(int(strFile),int(endFile)):
			vidFiles = vidFiles+self.wwwroot+event+"/video/segm"+str(i)+".ts "
		if (os.path.exists(bigMP4File)):
			return True # no need to re-create bookmarks that already exist

		# concatenate the videos
		cmd = "/bin/cat "+vidFiles+">"+bigTsFile
		os.system(cmd)
		# convert to mp4
		#using ffmpeg
		# cmd = "/usr/bin/ffmpeg -f mpegts -i "+bigTsFile +" -y -strict experimental -vf scale=iw/2:-1 -f mp4 "+bigMP4File
		#using handbrake
		cmd = "/usr/bin/handbrake -X 540 --keep-display-aspect -i "+bigTsFile+" -o "+bigMP4File
		os.system(cmd)
		#remove the temporary ts file
		os.remove(bigTsFile)

		# randomy select an ad to add to the video
		# this list contains all the ads videos in the directory
		adFiles = glob.glob(self.wwwroot+"/ads/*.ts")
		if(len(adFiles)<1):#there are no ad videos to choose from - just return after creating the video mp4 file
			return True
		adFile = adFiles[randrange(0,len(adFiles))] #TS file containing small size ad video (random ad)


		#convert mp4 back to .ts for merging with an ad
		cmd = "/usr/local/bin/ffmpeg -i "+bigMP4File+" -b:v 3000k -f mpegts "+tempTs #use 3Mbps bitrate to ensure high ad quality
		# self.str().pout(cmd)
		os.system(cmd)
		# remove the mp4
		os.remove(bigMP4File)
		# merge the ad and the video file
		cmd = "/bin/cat "+adFile+" "+tempTs+" >"+bigTsFile
		os.system(cmd)
		# remove temporary ts:
		os.remove(tempTs)
		# convert the result to an mp4 file again:
		cmd = "/usr/bin/handbrake -i "+bigTsFile+" -o "+bigMP4File
		os.system(cmd)
		# remove the temporary ts file
		os.remove(bigTsFile)
		return True
	#end extractClip
	#######################################################
	#return salted hash sha256 of the password
	#######################################################
	def _hash(self, password):
		import hashlib
		s = hashlib.sha256(password+"azucar")
		return s.hexdigest()
	#end hash
	#######################################################
	#initializes the encoder
	#######################################################
	def _init(self, email, password):
		import platform
		# make sure the credentials were supplied
		url = "http://www.myplayxplay.net/max/activate/ajax"
		
		params = {
			'v0':self.enc().sha('encoder'),
			'v1':self.enc().sha(email),
			'v2':self._hash(password),
			'v3':platform.uname()[1],
			'v4':", ".join(platform.uname())
		}
		resp = self.io().send(url, params, jsn=True)
		if(resp):
			if(resp['success']):
				#create all the necessary directories
				self.disk().mkdir(self.wwwroot+"_db")
				#save the config info
				self._cfgSet(self.wwwroot+"_db/",[resp['authorization'],resp['customer']])
				#download encoder control scripts
				os.system("curl -#Lo "+self.wwwroot+"_db/encpause http://myplayxplay.net/.assets/min/encpause")
				os.system("curl -#Lo "+self.wwwroot+"_db/encstart http://myplayxplay.net/.assets/min/encstart")
				os.system("curl -#Lo "+self.wwwroot+"_db/encstop http://myplayxplay.net/.assets/min/encstop")
				os.system("curl -#Lo "+self.wwwroot+"_db/encresume http://myplayxplay.net/.assets/min/encresume")
				os.system("curl -#Lo "+self.wwwroot+"_db/idevcopy http://myplayxplay.net/.assets/min/idevcopy")
				#add execution privileges for the scripts
				os.system("chmod +x "+self.wwwroot+"_db/*")
				#download the blank database files
				os.system("curl -#Lo "+self.wwwroot+"_db/event_template.db http://myplayxplay.net/.assets/min/event_template.db")
				os.system("curl -#Lo "+self.wwwroot+"_db/pxp_main.db http://myplayxplay.net/.assets/min/pxp_main.db")
				self._initLive()

				return 1
			#there was a response but it was an error with a message
			return resp['msg']
		#either response was not received or it was a 404 or some other unexpected error occurred
		return 0
	#end init
	#######################################################
	# returns true if this encoder has been initialized
	#######################################################
	def _inited(self):
		# LATER ON: check if server is online. if so, check auth code against the cloud
		cfg = self._cfgGet(self.wwwroot+"_db/")
		return (len(cfg)>1 and cfg[0]=='.min config file')
	#end inited
	#######################################################
	#initializes the live directory (creates it and subfolders)
	#######################################################
	def _initLive(self):
		self.disk().mkdir(self.wwwroot+"live/thumbs")
		self.disk().mkdir(self.wwwroot+"live/video")
		self.disk().copy(self.wwwroot+'_db/event_template.db', self.wwwroot+'live/pxp.db')
	#end initLive
	#######################################################
	#returns a list of events in the system
	#######################################################
	def _listEvents(self, showDeleted=True):
		try:
			query = "" if showDeleted else ' AND events.deleted=0'
			sql = "SELECT IFNULL(events.homeTeam,'---') AS `homeTeam`, \
						  IFNULL(events.visitTeam,'---') AS `visitTeam`, \
						  IFNULL(events.league,'---') AS `league`, \
						  IFNULL(events.date,'2000-01-01') AS `date`, \
						  IFNULL(events.hid,'000') AS `hid`, \
						  strftime('%Y-%m-%d_%H-%M-%S',events.date) AS `dateFmt`, \
						  leagues.sport AS `sport`, \
						  events.deleted AS `deleted` \
					FROM `events` \
					LEFT JOIN `leagues` ON events.league=leagues.name \
					WHERE strftime('%s',events.date)<= strftime('%s','now')"+query+"\
					ORDER BY events.date DESC"
			if(not os.path.exists(self.wwwroot+"_db/pxp_main.db")):
				return False
			db = self.dbsqlite(self.wwwroot+"_db/pxp_main.db")
			db.qstr(sql)
			result = db.getasc()
			# go through events and check if they have videos
			i = 0
			# get the name of the live event
			if(os.path.exists(self.wwwroot+'live/evt.txt')):
				live = self.disk().file_get_contents(self.wwwroot+"live/evt.txt").strip()
			else:
				live = ""
			# self.str().pout("")
			for row in result:
				# event name
				# print row	
				evtName = row['dateFmt']+'_H'+row['homeTeam'][:3]+'_V'+row['visitTeam'][:3]+'_L'+row['league'][:3]
				evtDir = self.wwwroot+evtName
				result[i]['name']=evtName
				# check if there is a streaming file in there
				if(os.path.exists(evtDir+'/video/list.m3u8')):
					result[i]['vid']='http://'+os.environ['HTTP_HOST']+'/events/'+evtName+'/video/list.m3u8'
				# check if the video file is there
				if(os.path.exists(evtDir+'/video/main.mp4')):
					#it is - provide a path to it
					result[i]['mp4']='http://'+os.environ['HTTP_HOST']+'/events/'+evtName+'/video/main.mp4'
					result[i]['vid_size']=self._sizeFmt(os.stat(evtDir+"/video/main.mp4").st_size)
				# check if this is a live event
				if(evtName==live):
					result[i]['live']='http://'+os.environ['HTTP_HOST']+'/events/live/video/list.m3u8'
				i+=1
			db.close()
			return result
		except Exception as e:
			import sys
			return self._err(str(e)+' '+str(sys.exc_traceback.tb_lineno)+" -- listEvents")
	#end listevents
	#######################################################
	#returns a list of teams in the system
	#######################################################
	def _listLeagues(self):
		sql = "SELECT * FROM `leagues` ORDER BY `name` ASC"
		if(not os.path.exists(self.wwwroot+"_db/pxp_main.db")):
			return False
		db = self.dbsqlite(self.wwwroot+"_db/pxp_main.db")
		db.qstr(sql)
		result = db.getasc()
		db.close()
		return result
	#end _listLeagues
	#######################################################
	#returns a list of teams in the system
	#######################################################
	def _listTeams(self):
		sql = "SELECT * FROM `teams` ORDER BY `name` ASC"
		if(not os.path.exists(self.wwwroot+"_db/pxp_main.db")):
			return False
		db = self.dbsqlite(self.wwwroot+"_db/pxp_main.db")
		db.qstr(sql)
		result = db.getasc()
		db.close()
		return result
	#end listTeams
	#######################################################
	#logs an entry in the sqlite database
	#######################################################
	def _logSql(self, ltype,lid=0,uid=0,dbfile="",forceInsert=False,db=False):
		import os
		if db:
			autoclose = False
		else:
			autoclose = True
			if(not os.path.exists(dbfile)):
				return False
			db = self.dbsqlite(dbfile)
		#logging an event - delete the last identical event (e.g tag_mod for specific tag id by the same user)
		sql = "DELETE FROM `logs` WHERE (`type` LIKE ?) AND (`user` LIKE ?) AND (`id` LIKE ?)"
		db.query(sql,(ltype,uid,lid))
		#add it again
		sql = "INSERT INTO `logs`(`type`,`id`,`user`) VALUES(?,?,?)";
		success = db.query(sql,(ltype,lid,uid))
		if(autoclose):
			# db was opened in this function - close it
			db.close()
		return success
	#end logSql
	#######################################################
	#creates a thumbnail from 'videoFile' at 'seconds' 
	#and puts it in 'outputFile' using ffmpeg
	#######################################################
	def _mkThumb(self, videoFile, outputFile, seconds, width=190, height=106):
		import os
		if not os.path.exists(videoFile):
			#there is no video for this event
			return False
		if not os.path.exists(os.path.dirname(outputFile)):
			self.disk().mkdir(os.path.dirname(outputFile))
		#make the thumbnail
		cmd = "/usr/local/bin/ffmpeg"
		#automatically calculates height based on defined width:
		# -itsoffset is slower than -ss but insignificant for small files
		params = " -itsoffset "+str(seconds)+"  -i "+videoFile+" -vcodec mjpeg -vframes 1 -an -vf scale="+str(width)+":ih*"+str(width)+"/iw "+outputFile
		os.system(cmd+params) # need to wait for response otherwise the tablet will try to download image file that does not exist yet
	
	#######################################################
	#renames directories
	#######################################################
	def _postProcess(self):
		# get the name of what the new directory should be called
		event = self.disk().file_get_contents(self.wwwroot+"live/evt.txt").strip()
		#delete the file containing the name of the event (not needed anymore)
		os.remove(self.wwwroot+"live/evt.txt")
		# rename the live to that directory
		os.rename(self.wwwroot+"live",self.wwwroot+event)
		# remove all .ts files - leave them on the server for streaming
		# cmd = "find "+self.wwwroot+event.strip()+"/video/ -name *.ts -print0 | xargs -0 rm"
		# os.system(cmd)
		# re-create the directories for live:
		self._initLive()
	#end postProcess

	def _sizeFmt(self,size):
		#size names
		sizeSuffix = ['b','KB','MB','GB','TB','PB','EB','ZB','YB']
		for x in sizeSuffix:			
			if size < 1024 or x==sizeSuffix[len(sizeSuffix)-1]:
				#either reached the capacity (i.e. size will be under 1024)
				#or reached the end of suffixes (highly unlikely)
				return "%d %s" % (size, x)
			#shift left by 10 is equivalent to dividing by 1024 with round down
			size = size >> 10
		return ""
	#######################################################
	#adds tags to an event during the sync procedure (gets called once for each event)
	#######################################################
	def _syncAddTags(self, path,tagrow,del_arr,add_arr):
		if(not os.path.exists(path+'/pxp.db')):
			# event directory does not exist yet
			# create it recursively (default mode is 0777)
			self.disk().mkdir(path)
			# copy the template database there
			self.disk().copy(self.wwwroot+'_db/event_template.db', path+'/pxp.db')
		#end if not path exists

		sql_del = "DELETE FROM `tags` WHERE"+("OR".join(del_arr))
		if(len(add_arr)<1):#nothing to add - run dummy query
			sql_ins = "SELECT 1"
		elif(len(add_arr)<2):#a single tag needs to be added - special case syntax
			sql_ins = 'INSERT INTO `tags`(`'+('`, `'.join(tagrow.keys()))+'`) VALUES("'+('", "'.join(tagrow.values()))+'") '
		else:#adding multiple tags
			sql_ins = 'INSERT INTO `tags`(`'+('`, `'.join(tagrow.keys()))+'`) SELECT '+('UNION SELECT'.join(add_arr))
		# connect to the database of the event
		db = self.dbsqlite(path+'/pxp.db')
		#delete tags that should be deleted
		db.qstr(sql_del)
		#add tags that need to be added
		db.qstr(sql_ins)
		# disconnect from the db
		db.close()
	#end syncAddTags
	#######################################################
	#adds tags to an event during the sync procedure (gets called once for each event)
	#######################################################
	def _syncEnc(self, encEmail="",encPassw=""):
		db = self.dbsqlite()
		#open the main database (where everything except tags is stored)
		if(not db.open(self.wwwroot+"_db/pxp_main.db")):
			return self._err("no database")
		url = 'http://www.myplayxplay.net/max/sync/ajax'
		# name them v1 and v2 to make sure it's not obvious what is being sent
		# v3 is a dummy variable
		# v0 is the authorization code (it will determine if this is encoder or another device)
		cfg = self._cfgGet(self.wwwroot+"_db/")
		if(not cfg): 
			return self._err("not initialized")
		authorization = cfg[1]
		customerID = cfg[2]
		params ={   'v0':authorization,
					'v1':encEmail,
					'v2':encPassw,
					'v3':encEmail.encode("rot13"),
					'v4':customerID
				}
		# return self._err("zz")
		resp = self.io().send(url,params, jsn=True)
		if not resp:
			return self._err("connection error")
		# return resp
		# self.str().jout(resp)
		# self._x("")
		tables = ['users','leagues','teams','events', 'teamsetup']
		for table in tables:
			if (resp and (not (table in resp)) or (len(resp[table])<1)):
				continue
			sql_del = "DELETE FROM `"+table+"` WHERE"
			sql_ins = "INSERT INTO `"+table+"` "
			del_arr = [] #what will be deleted
			add_arr = [] #values will be added here
			# add all data rows in a single query
			for row in resp[table]:
				delFields = row['primary'].split(",")#contains names of the fields that are the key - used to delete entries from old tables
				# e.g. may have "player, team" as the key
				delQuery = []
				for delField in delFields:
					#contains query conditions for deletion
					delQuery.append(' `'+delField+'` LIKE "'+self._cln(row[delField])+'" ')

				del_arr.append(" AND ".join(delQuery)) 

				#if the entry was deleted, move on to the next one (do not add it to the insert array)
				if('deleted' in row and row['deleted']=='1'):
					continue
				values = [] #contains values that are added to the query
				firstRow = {} #contains special format for the first row of the sql query (for SQLite)
				#go throuch each field in a row and add it to the query array
				for name in row:
					if(name=='primary' or name=='deleted'):
						continue #this is only a name of a row - not actual data
					value = row[name]
					if not value:
						value = ''
					name = self._cln(name)
					value = self._cln(value)
					values.append(value)
					firstRow[name] = ' "'+value+'" AS `'+name+'` '
				#end for name in row
				# append the values string to the query (add a row)
				if(len(add_arr)>0):
					# all subsequent rows are in more-less standard format
					add_arr.append((", ".join(firstRow.values()))+" ")
					# add_arr.append(' "'+('", "'.join(values)+'" ')
				else:
					# first row has special format
					add_arr.append("SELECT "+(", ".join(firstRow.values()))+" ")
			#end for row in table

			# delete query is fairly standard: DELETE FROM `table` WHERE `field` LIKE 'value' OR `field` LIKE 'another value'
			sql_del += "OR".join(del_arr)
			# create SQL query in this format:
			# INSERT INTO `table`
			# SELECT 'fld1_value1' AS `field1`, 'fld2_value1', AS `field2` 
			# UNION SELECT 'fld1_value2', 'fld2_value2'
			# and so on...
			sql_ins +='(`'+('`, `'.join(firstRow.keys()))+'`)'+'UNION SELECT'.join(add_arr)

			# for a single row entry, the insert syntax has to be different 
			# otherwise duplicates are added for some reason (???)
			if(len(add_arr)==1):
				sql_ins = 'INSERT INTO `'+table+'`(`'+('`, `'.join(firstRow.keys()))+'`) VALUES("'+('", "'.join(values))+'") '
			if(len(add_arr)<1):
				sql_ins = "SELECT 1" #nothing to add - simply run a dummy query
			if(table=='events'): #only delete events that were deleted in the cloud
				db.qstr(sql_del)
			else:#delete all the data from the table (except for events)
				db.qstr("DELETE FROM `"+table+"`")
			# if(table=='teamsetup'):
			# 	print sql_ins
			db.qstr(sql_ins)
		#foreach table
		db.qstr("INSERT OR IGNORE INTO `teams`(`hid`,`name`,`txt_name`) VALUES('00000','Unspecified','Unspecified')")
		db.close()	
		#now sync tags - go to each event folder and add tags to those databases

		eventDir = "../events/"
		event = ""
		if not 'tags' in resp:
			resp['tags']={}
		lastTagRow = {}
		for tagrow in resp['tags']:
			#check if still adding tags to the same event or a new one
			if(event!=tagrow['event']):
				#new event: submit the sql query for the previous event

				# first time the loop runs event will be empty
				# run sql query only after it's been created
				if(len(event)>0):
					self._syncAddTags(eventDir+event,tagrow,del_arr,add_arr)
				#if len(event)>0
				del_arr = [] #what will be deleted
				add_arr = [] #values will be added here
			#end if event != tagrow[event]

			#get the event name (used as path to the database)
			event = tagrow['event']
			#remove it from the dictionary (don't need it for the query)
			del tagrow['event']
			del_arr.append(" (`name` LIKE '"+tagrow['name']+"' AND `user` LIKE '"+tagrow['user']+"' AND `time`="+str(tagrow['time'])+") ")
			if ('deleted' in tagrow and tagrow['deleted']=='1'):
				#skip deleted tags
				continue
			fields = [] 
			for field in tagrow:
				fields.append('"'+self._cln(tagrow[field])+'" AS `'+field+'`')
			#end for field in tagrow
			add_arr.append(", ".join(fields))
			lastTagRow = tagrow
		#end for tagrow in resp[tags]
			# sql = "INSERT INTO `tags`(`hid`, `name`, `user`, `time`, `period`, `duration`, `coachpick`, `bookmark`, `playerpick`, `colour`,`starttime`,`type`)";
		#end for tagrow in tags
		if (len(lastTagRow)>0):
			#last add/delete query will be run after all the tags were parsed:
			self._syncAddTags(eventDir+event,lastTagRow,del_arr,add_arr)
		return {"success":True}
	#end syncEnc
	#######################################################
	#syncs tablet with ecnoder (sends any tag modifications 
	#that were created in a specific event since the last sync)
	#######################################################
	def _syncTab(self, user, device, event, allData=False):
		##get the user's ip
		##userIP = os.environ['REMOTE_ADDR']
		if (not user) or len(user)<1 or (not device) or len(device)<1 or (not event) or len(event)<1 or (not os.path.exists(self.wwwroot+event+"/pxp.db")):
			return [] #return empty list if user did not provide the correct info or event does not exist
		db = self.dbsqlite(self.wwwroot+event+"/pxp.db")
		try:
			if(allData):#selecting all tags from this game (assumption here - user has no tags yet, so he doesn't need to see deleted tags)
				lastup = 0
				sql = "SELECT * FROM `tags` WHERE NOT `type`=3"
				db.qstr(sql)
			else:
				#get the time of the last update
				sql = "SELECT IFNULL(MAX(`logID`),0) AS `logid` FROM `logs` WHERE `id` LIKE ? AND `user` LIKE ? AND `type` LIKE 'sync_tablet' ORDER BY `logID`"
				success = db.query(sql,(device,user))
				lastup = db.getrow()
				lastup = lastup[0]
				#if allData...else
				#get new events that happened since the last update
				#get all tag changes that were made since the last update
				sql = "SELECT DISTINCT(tags.id) AS dtid, tags.* FROM tags LEFT JOIN logs ON logs.id=tags.id WHERE (logs.logID>?) AND (logs.type LIKE 'mod_tags')"
				db.query(sql,(lastup,))
			#put them in a list of dictionaries:
			tags = db.getasc()
			#format tags for output
			tagsOut = {}
			for tag in tags:
				if ((int(tag['type'])&1) and (not int(tag['type'])==3)):
					#only even type tags are sent (normal, telestration, period/half/zone/line end tags)
					#also deleted tags are sent - to delete them from other tablets
					continue
				if(str(tag['time'])=='nan'):
					tag['time']=0
				tagJSON = self._tagFormat(tag=tag,event=event, db=db)
				# if(allData or not user==tag['user']):
				tagsOut[tag['id']]=(tagJSON)
			#end for tags:
	
			#get any other events (other than tags)
			sql = "SELECT `type`, `id` FROM `logs` WHERE `logID`>? AND NOT(`type` LIKE 'mod_tags' OR `type` LIKE 'sync%')"
			db.query(sql,(lastup,))
			evts = db.getasc()
			# get the teams playing
			sql = "SELECT `id` FROM `logs` WHERE `type` LIKE 'enc_start'"
			db.qstr(sql)
			teamHIDs = db.getasc()
			if (len(teamHIDs)>0): #this will be the case when there is a blank db in the event (encode was not started)
				teamHIDs = teamHIDs[0]['id'].split(',')
			if(len(teamHIDs)>2):#in case this is an old event, and the league HID is not listed along with team HIDs (comma-delimeted) in the log table, add empty value for the league
				leagueHID = teamHIDs[2]
				del(teamHIDs[2]) #remove league id from the teams list
			else:
				leagueHID = ""
			#close the database (so that log can use it)
			db.close();
			evts.append({"camera":self.encoderstatus()})
			outJSON = {
				'tags':tagsOut,
				'events':evts,
				'teams':teamHIDs,
				'league':leagueHID
				# 'camera':self.encoderstatus()
			}
			for key in outJSON.keys():
				if len(outJSON[key])<1:
					del(outJSON[key])
			if len(outJSON)>0: #only log sync when something was sync'ed
				self._logSql(ltype='sync_tablet',lid=device,uid=user,dbfile=self.wwwroot+event+'/pxp.db')
			return outJSON
		except Exception as e:
			import sys
			return self._err(str(e)+' '+str(sys.exc_traceback.tb_lineno))
	#end syncTab()
	#######################################################
	# formats the tag in a proper json format and returns it as json dictionary
	# if db is not specified, the default db from the specified 'event' will be opened
	#######################################################
	def _tagFormat(self, event=False, user=False, tagID=False, tag=False, db=False):
		import os, datetime
		try:
			outDict = {}
			if(tagID): #tag id was given - retreive it from the database
				sql = "SELECT * FROM `tags` WHERE `id`=?"
				if(not db):
					autoclose = True #db was not passed, open and close it in this function
					db = self.dbsqlite(self.wwwroot+event+"/pxp.db")
				else:
					autoclose = False #db was passed as argument - do not close it here
				db.query(sql,(tagID,))
				tag = db.getasc()[0]
				if(autoclose):
					db.close()
			elif(not tag):
				# no tag id or other information given - return empty dictionary
				return {}
			# some sanity checks before the round function
			if (not tag['duration']):
				tag['duration']=0.01
			if (not tag['time']):
				tag['time']=0.01
			#format some custom fields
			tag['duration']=str(round(float(tag['duration'])))[:-2]
			tag['displaytime'] = str(datetime.timedelta(seconds=round(float(tag['time']))))
			tag['url'] = 'http://'+os.environ['HTTP_HOST']+'/events/'+event+'/thumbs/tn'+str(tag['id'])+'.jpg'
			tag['own'] = tag['user']==user #whether this is user's own tag
			if(event=='live' and os.path.exists(self.wwwroot+event+'/evt.txt')):
				tag['event'] = self.disk().file_get_contents(self.wwwroot+event+'/evt.txt').strip()
			else:
				tag['event'] = event
			#set deleted attribute for a tag
			if not 'deleted' in tag:
				tag['deleted']=0
			tag['deleted'] = (tag['deleted']==1 or tag['type']==3) #this will be removed in the future and set to type==3 only
			tag['success'] = True
			if(int(tag['type'])==4): #add telestration url for telestration tags only
				tag['teleurl']='http://'+os.environ['HTTP_HOST']+'/events/'+event+'/thumbs/tl'+str(tag['id'])+'.png'
			if(os.path.exists(self.wwwroot+event+'/video/vid_'+str(tag['id'])+'.mp4')):
				tag['vidurl']='http://'+os.environ['HTTP_HOST']+'/events/'+event+'/video/vid_'+str(tag['id'])+'.mp4'
			if('hid' in tag):
				del(tag['hid'])
			for field in tag:
				field = field.replace("_"," ") #replace all _ with spaces in the field names
				if(tag[field]== None):
					tag[field] = ''
				if(field=='line' or field=='player' or field=='period' or field=='strength'):
				# if(field=='player'):
					outDict[field]=tag[field].split(",")
				else:
					outDict[field]=tag[field]
			return outDict
		except Exception as e:
			import sys
			return self._err(str(sys.exc_traceback.tb_lineno)+' '+str(e))
	#end tagFormat
	#######################################################
	#returns file name for the video that contains appropriate time 
	#######################################################
	def _thumbName(self,seekTo,number=False,event="live"):
		import math
		# path to the list.m3u8 file - playlist for the hls
		listPath = self.wwwroot+event+"/video/list.m3u8"
		#open m3u8 file:
		f = open(listPath,"r")

		#the time of the current file. e.g. if there are 50 files of 1seconds each then file50.ts will be at roughly 00:00:50 time. reachedTime contains the number of seconds since file0
		reachedTime = 0.0
		try:
			seekTo = float(seekTo) # make sure this is not a string
		except:
			return 0
		#starting from the top, add up the times until reached desired time - that's the file
		#assuming m3u8 file is in this format:
		# #EXTINF:0.98431,
		# fileSequence531.ts
		#and so on - a line with time precedes the file 

		fileName = False
		for line in f:
			 cleanStr = line.strip()
			 if(cleanStr[:7]=='#EXTINF'):#this line contains time information
				 reachedTime += float(cleanStr[8:-1]) #get the number (without the trailing comma) - this is the duration of this segment file
			 elif(cleanStr[-3:]=='.ts' and seekTo<=reachedTime):#this line contains filename
				 #found the right time - this file contains the frame we need
				 fileName = cleanStr
				 break
		f.close()
		if (not fileName):
			return 0
		# each .ts file contains slightly less than 1 second
		# round down to the nearest file
		# secname = str(int(seekTo/0.984315)) 
		# if secname=='0':
		# 	#when the time is 0.0 then the 0 frame of the first video may not work properly
		# 	#set it to second fragment (semg1.ts)
		# 	secname='1'
		# fileName = "segm"+secname+".ts"
		if(number):#only return the number without the rest of the filename
			return self._exNum(fileName)
		return fileName
	#end calcThumb
	def _x(self,txt):
		self.str().pout(txt)
#end pxp class