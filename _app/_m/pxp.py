from imp import load_source as ls
from imp import load_compiled as lp
import os, json
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
	# returns encoder status as a string, 
	# either json or plain text
	#######################################################
	def encoderstatus(self,textOnly=True):
		state = self._encState()
		if(state==1):
			status = "live"
		elif(state==2):
			status = "paused"
		elif(os.path.exists(self.wwwroot+'live/video/list.m3u8')):
			status = "vod"
		else:
			status = "off"
		# status = "live"
		if (textOnly):
			return status
		return {"status":status}
	#end encoderstatus
	#######################################################
	#pauses a live encode
	#######################################################
	def encpause(self):
		import os
		msg = ""
		try:
			rez = os.system(self.wwwroot+"_db/encpause >/dev/null &")
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
			rez = os.system(self.wwwroot+"_db/encresume >/dev/null &")
			# add entry to the database that the encoding has paused
			msg = self._logSql(ltype="enc_resume",dbfile=self.wwwroot+"live/pxp.db",forceInsert=True)
		except Exception as e:
			rez = False
		# rez = False
		return {"success":not rez}
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
			# start the capture
			rez = os.system(self.wwwroot+"_db/encstart >/dev/null &")
			# add entry to the database that the encoding has started
			msg = self._logSql(ltype="enc_start",dbfile=self.wwwroot+"live/pxp.db",forceInsert=True)
			# create new event in the database
			# get time for hid and for database
			timestamp = dt.fromtimestamp(tm()).strftime('%Y-%m-%d %H:%M:%S')
			evthid = self.enc().sha(timestamp) #event hid
			db = self.dbsqlite(self.wwwroot+"_db/pxp_main.db")
			sql = "INSERT INTO `events` (`hid`,`date`,`homeTeam`,`visitTeam`,`league`) VALUES(?,?,?,?,?)"
			db.query(sql,(evthid,timestamp,hmteam,vsteam,league))
			#the name of the directory will be YYYY-MM-DD_HH-MM-SS
			evtName = dt.fromtimestamp(tm()).strftime('%Y-%m-%d_%H-%M-%S')+'_H'+hmteam[:3]+'_V'+vsteam[:3]+'_L'+league[:3]
			#store the event name (for processing when it's stopped)
			cmd = "echo '"+evtName+"' > "+self.wwwroot+"live/evt.txt"
			rez = not os.system(cmd)
		except Exception as e:
			self.str().pout(e)
			print sys.exc_traceback.tb_lineno
			rez = False
		# rez = False
		return {"success":rez}
	#end encstart
	#######################################################
	#stops a live encode
	#######################################################
	def encstop(self):
		import os
		from time import sleep
		msg = ""
		try:
			rez = os.system(self.wwwroot+"_db/encstop >/dev/null &")
			os.system("/bin/kill `ps ax | grep mediastreamsegmenter | grep 'grep' -v | awk '{print $1}'`")
			#send 2 kill signals to ffmpeg
			os.system("/bin/kill `ps ax | grep ffmpeg | grep 'grep' -v | awk '{print $1}'`")
			os.system("/bin/kill `ps ax | grep ffmpeg | grep 'grep' -v | awk '{print $1}'`")
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
		return {"success":True,"msg":"No camera connected","encoder":self.encoderstatus()}
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
			return self.str().err("Specify user, event, and device")

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
	def logincheck(self):
		io = self.io()
		email = io.get("email")
		passw = io.get("pass")
		# sess = self.session(expires=24*60*60,cookie_path="/")
		if not (email and passw):
			return self.str().err("Email and password must be specified")
		encEm = self.enc().sha(email)
		encPs = self._hash(passw)
		if not self._inited():
			res = self._init(email,passw)
			if (not res==1):
				return {"success":False, "msg":res}
		self._syncEnc(encEm,encPs)
		# check if user is in the database
		db = self.dbsqlite(self.wwwroot+"_db/pxp_main.db")
		sql = "SELECT * FROM `users` WHERE `email` LIKE ? AND `password` LIKE ?"
		db.query(sql,(encEm,encPs))
		# log him in
		# return {io.get("email"):io.get("pass")}
		return {"success":True}
	#######################################################
  	#get any new events that happened since the last update (e.g. new tags, removed tags, etc.)
	#######################################################
	def syncme(self):
		strParam = self.uri().segment(3,"{}")
		jp = json.loads(strParam)
		if not ('user' in jp and 'event' in jp and 'device' in jp):
			return self.str().err("Specify user, event, and device")

		#get user id
		usr = jp['user']
		#device ID
		dev = jp['device']
		#event
		evt = jp['event']
		return self._syncTab(user=usr, device=dev, event=evt)
	#######################################################
	#modify a tag - set as coachpick, bookmark, etc
	#######################################################
	def tagmod(self):
		strParam = self.uri().segment(3,"{}")
		jp = json.loads(strParam)
		if not ('user' in jp and 'event' in jp and 'id' in jp):
			return self.str().err("Specify user, event, and tag id")
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
		bookmark = False;
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
				sqlInsert.append("`"+mod+"`=?")
				params +=(jp[mod],)
				bookmark = bookmark or ((mod=='bookmark') and (jp['bookmark']==1))
		#end for mod in jp
		if len(sqlInsert)<1:#nothing was specified 
			return {'success':False}
		# parameters to add to the sql - tag id (no need to check user at the moment)
		params += (tid,)
		#update the tag
		sql = "UPDATE `tags` SET "+(', '.join(sqlInsert))+" WHERE id=?"
		#make sure the database exists
		if(not os.path.exists(self.wwwroot+event+'/pxp.db')):
			return {'success':False}
		#perform the update
		db = self.dbsqlite(self.wwwroot+event+'/pxp.db')
		# return {"sq":sql,"i":params}
		success = db.query(sql,params) and db.numrows()>0
		if success:
			#add an entry to the event log that tag was updated or deleted
			success = self._logSql(ltype='mod_tags',lid=tid,uid=user,db=db)
		if success:
			sql = "SELECT * FROM `tags` WHERE `id`=?"
			db.query(sql,(tid,))
			tag = db.getasc()
			db.close()
			if (bookmark):
				# user wants to make a bookmark - extract the video
				success = success and self._bookmark(tagid=tid,event=event)
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
			return self.str().err("Tag string not specified")
		sql = ""
		db = self.dbsqlite()
		try:
			t = json.loads(tagStr)
			# t might be an array of dictionaires (size 1) or a dictionary itself
			if (t and (not 'name' in t)):
				t = t[0] # this is an array of dictionaries - get the first element
			if (not 'event' in t):
				return self.str().err("Specify event") #event was not defined - can't open the database
			if (not os.path.exists(self.wwwroot+t['event']+'/pxp.db')):
				# this is the first tag in the event 
				self.disk().mkdir(self.wwwroot+t['event'])
				# copy the template db for tags
				self.disk().copy(self.wwwroot+'_db/event_template.db', self.wwwroot+t['event']+'/pxp.db')
			db.open(self.wwwroot+t['event']+'/pxp.db')
			db.transBegin() #in case we need to roll it back later
			epath = self.wwwroot+t['event']+'/'
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
			#check if lines/zones were specified
			if(('line' in t) and (t['type']==1)):
				sqlVars += (t['line'],)
				sqlAddFld += ", line"
				sqlAddVal += ", ?"
			#if period was set (0, 1, 2...)
			if(('period' in t) and (t['type']==7)):
				sqlVars += (t['period'],)
				sqlAddFld += ", period"
				sqlAddVal += ", ?"
			#if strength was set (i.e. 5vs6 etc.)
			if(('strength' in t) and (t['type']==9)):
				sqlVars += (t['strength'],)
				sqlAddFld += ", strength"
				sqlAddVal += ", ?"
			# create the query
			sql = "INSERT INTO tags (name, user, starttime, type, time, colour, coachpick"+sqlAddFld+") VALUES(?, ?, ?, ?, ?, ?, ?"+sqlAddVal+")"
			#run it
			success = success and db.query(sql,sqlVars)
			#get the id of the newly created tag
			lastID = db.lastID()

			if(not success):#something went wrong, roll back the sql statement
				db.rollback()
				return {'success':False}
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
				return {'success':False}
			#either default tag or start tag - create thumbnails for those
			if(not (t['type'] & 1)): #odd-number types do not require thumbnail, even ones do
				#create a thumbnail for the tag video - only do this when a tag is created
				#i.e. tagStart is not technically a "tag" - wait till the Stop is set, then make a thumbnail
				fileName = self._thumbName(t['tagtime'])
				#create a tag if it doesn't exist already
				imgFile = epath+"thumbs/tn"+str(lastID)+".jpg"
				if(not os.path.exists(imgFile)):
					vidFile = epath+"video/"+str(fileName)
					sec = 0
					self._mkThumb(vidFile, imgFile, sec)
			#if not t['type']==2

			#get the time of the current tag
			tagTime = t['tagtime']

			if((t['type']==0) or (t['type']==4)):
				#only normal tags and telestrations should be updated with periods and logged in the database log

				#find a line/third  corresponding to this tag - 
				#either the tag is being created in the past and its 
				#time falls within the duration of the line tag, 
				#or it's being created live and there is a line/third active right now
				#name contains the line designation, i.e. d_2, or o_1

				types = {
					#numbers are: stop, start codes for line, period, strength
					"line"		: ['2','1'], 
					"period"	: ['8','7'],
					"strength"	: ['10','9']
					}
				#players might have been specified in the tag, if it is the case, add them
				if (not 'player' in t):
					#players were not defined with the tag - get it automatically
					types["player"]=['6','5']
				#go through every type of metadata for each tag (e.g. line, period)
				#and update that attribute for the current tag based on what was the last line/zone, period/half etc. selected
				for tp in types:
					#get the sql query with proper types
					sql = "SELECT `"+tp+"` FROM `tags` WHERE `starttime`<=? AND ((`type`="+types[tp][0]+" AND (`starttime`+`duration`)>=?) OR (`type`="+types[tp][1]+" AND `duration`=0)) ORDER BY `starttime` "
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

				# tagOut = {} # this dictionary will be returned
				if(t['type']==1):
					tagOut = {
						'id':lastID,
						'success':success
					}
				else:
					#log that a tag was created
					if(success):
						success = success and self._logSql(ltype="mod_tags",lid=lastID,uid=t['user'],db=db)
					tagOut = self._tagFormat(event=t['event'], user=t['user'], tagID=lastID)
				if(success):
					db.commit()
				else:
					db.rollback()
				#output result as JSON
				return tagOut
			#if type==0 or type==4
			else:
				tagTypes = {1:'zone',5:'player',7:'period',9:'strength'}
				self._logSql(ltype="current_"+tagTypes[t['type']],lid=t['name'],uid=t['user'],db=db)
				if(success):
					db.commit()
				else:
					db.rollback()
				return {"success":success}
		except Exception as e:
			self.str().pout(sys.exc_traceback.tb_lineno)
			print e
			db.rollback()
			return self.str().err()
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
			return self.str().err("No tag info specified")
###############################################
##	           utility functions             ##
###############################################
	#######################################################
	# extracts video clip and saves it as mp4 file
	#######################################################
	def _bookmark(self, tagid, event):
		# get tag ID
		db = self.dbsqlite(self.wwwroot+event+'/pxp.db')
		# get the time from the database
		sql = "SELECT starttime, duration FROM tags WHERE id=?"
		db.query(sql,(tagid,))
		row = db.getrow()
		self.str().pout("")
		db.close()
		startTime = float(row[0])
		endTime   = float(row[0])+float(row[1])
		strFile = self._thumbName(startTime,number=True) #index of the starting .ts file
		endFile = self._thumbName(endTime,number=True) #index of the ending .ts file
		vidFiles = ""
		#select .ts files that should be merged
		for i in range(int(strFile),int(endFile)):
			vidFiles += self.wwwroot+event+"/video/segm"+str(i)+".ts "
		# concatenate the videos		
		bigTsFile = self.wwwroot+event+"/video/vid"+tagid+".ts" #temporary .ts output file
		bigMP4File= self.wwwroot+event+"/video/vid_"+tagid+".mp4" #converted mp4 file
		cmd = "/bin/cat "+vidFiles+">"+bigTsFile
		os.system(cmd)
		# convert to mp4
		#using ffmpeg
		# cmd = "/usr/bin/ffmpeg -f mpegts -i "+bigTsFile +" -y -strict experimental -vf scale=iw/2:-1 -f mp4 "+bigMP4File
		#using handbrake
		cmd = "/usr/sbin/handbrake -X 540 --keep-display-aspect -i "+bigTsFile+" -o "+bigMP4File
		os.system(cmd)
		#remove the temporary ts file
		os.remove(bigTsFile)
		return True
	#end bookmark
	#######################################################
	# XORs config file (simple 'encryption') to prevent onlookers
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
	# XORs config file (simple 'encryption') to prevent onlookers
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
	#######################################################
	#returns encoder state (0 - off, 1 - live, 2 - paused)
	#######################################################
	def _encState(self):
		import socket
		UDP_IP = "127.0.0.1"
		UDP_PORT = 2224
		sock = socket.socket(socket.AF_INET, # Internet
		                     socket.SOCK_DGRAM) # UDP
		sock.settimeout(0.2) #wait for 0.2 seconds - if there is no response, server is not streaming
		#bind to the port and listen
		try:
			sock.bind((UDP_IP, UDP_PORT))
			data, addr = sock.recvfrom(1)
			data = int(data)
		except Exception as e:
			#failed to bind to that port
			data = 0
		#close the socket
		try:
			sock.close()
		except:
			pass		
		return data
	#end encState
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
	def _listEvents(self):
		sql = "SELECT events.*, strftime('%Y-%m-%d_%H-%M-%S',`date`) AS `dateFmt` FROM `events` WHERE strftime('%s',`date`)<= strftime('%s','now') AND `deleted`=0 ORDER BY `date` DESC"
		if(not os.path.exists(self.wwwroot+"_db/pxp_main.db")):
			return False
		db = self.dbsqlite(self.wwwroot+"_db/pxp_main.db")
		db.qstr(sql)
		result = db.getasc()
		# go through events and check if they have videos
		i = 0
		for row in result:
			# event name
			evtName = row['dateFmt']+'_H'+row['homeTeam'][:3]+'_V'+row['visitTeam'][:3]+'_L'+row['league'][:3]
			evtDir = self.wwwroot+evtName
			result[i]['name']=evtName
			# check if the video file is there
			if(os.path.exists(evtDir+'/video/main.mp4')):
				#it is - provide a path to it
				result[i]['vid']='http://'+os.environ['HTTP_HOST']+'/events/'+evtName+'/video/main.mp4'
				result[i]['vid_size']=self._sizeFmt(os.stat(evtDir+"/video/main.mp4").st_size)
			i+=1
		db.close()
		return result
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
		params = " -ss "+str(seconds)+"  -i "+videoFile+" -vcodec mjpeg -vframes 1 -an -vf scale="+str(width)+":ih*"+str(width)+"/iw "+outputFile
		os.system(cmd+params) # need to wait for response otherwise the tablet will try to download image file that does not exist yet
	
	#######################################################
	#renames directories
	#######################################################
	def _postProcess(self):
		# get the name of what the new directory should be called
		event = self.disk().file_get_contents(self.wwwroot+"live/evt.txt").strip()
		# rename the live to that directory
		os.rename(self.wwwroot+"live",self.wwwroot+event)
		# remove all .ts files
		cmd = "find "+self.wwwroot+event.strip()+"/video/ -name *.ts -print0 | xargs -0 rm"
		os.system(cmd)
		# re-create the directories for live:
		self._initLive()
	#end postProcess

	def _sizeFmt(self,size):
		sizePrefix = ['b','KB','MB','GB','TB','PB','EB','ZB','YB']
		for x in sizePrefix:
			if size < 1024 or x==sizePrefix[len(sizePrefix)-1]:
				return "%d %s" % (size, x)
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
			return False
		url = 'http://www.myplayxplay.net/max/sync/ajax'
		# name them v1 and v2 to make sure it's not obvious what is being sent
		# v3 is a dummy variable
		# v0 is the authorization code (it will determine if this is encoder or another device)
		cfg = self._cfgGet(self.wwwroot+"_db/")
		if(not cfg): 
			return False
		authorization = cfg[1]
		customerID = cfg[2]
		params ={   'v0':authorization,
					'v1':encEmail,
					'v2':encPassw,
					'v3':encEmail.encode("rot13"),
					'v4':customerID
				}
		resp = self.io().send(url,params, jsn=True)		
		# self.str().pout("")
		# return self.str().err()
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
			db.qstr(sql_del)
			db.qstr(sql_ins)
		#foreach table
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
			if(allData):#selecting all tags from this game
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
				if (not(int(tag['type'])==0 or int(tag['type'])==4)):
					#only event names and telestrations should be sent
					continue
				if(str(tag['time'])=='nan'):
					tag['time']=0
				tagJSON = self._tagFormat(tag=tag,event=event)
				if(allData or not user==tag['user']):
					tagsOut[tag['id']]=(tagJSON)
			#end for tags:
	
			#get any other events (other than tags)
			sql = "SELECT type, id FROM logs WHERE logID>? AND NOT(type LIKE 'mod_tags' OR type LIKE 'sync%')"
			db.query(sql,(lastup,))
			evts = db.getasc()
			#close the database (so that log can use it)
			db.close();
			evts.append({"camera":self.encoderstatus()})
			outJSON = {
				'tags':tagsOut,
				'events':evts
				# 'camera':self.encoderstatus()
			}
			for key in outJSON.keys():
				if len(outJSON[key])<1:
					del(outJSON[key])
			if len(outJSON)>0: #only log sync when something was sync'ed
				self._logSql(ltype='sync_tablet',lid=device,uid=user,dbfile=self.wwwroot+event+'/pxp.db')
			return outJSON
		except Exception as e:
			# print e
			return {"success":False,"msg":str(e)}
	#end syncTab()
	#######################################################
	# formats the tag in a proper json format and returns it as json dictionary
	#######################################################
	def _tagFormat(self, event=False, user=False, tagID=False, tag=False):
		import os, datetime
		outDict = {}
		if(tagID): #tag id was given - retreive it from the database
			sql = "SELECT * FROM `tags` WHERE `id`=?"
			db = self.dbsqlite(self.wwwroot+event+"/pxp.db")
			db.query(sql,(tagID,))
			tag = db.getasc()[0]
		elif(not tag):
			# no tag id or other information given - return empty dictionary
			return {}
		# some sanity checks for the round function
		if (not tag['duration']):
			tag['duration']=0.01
		if (not tag['time']):
			tag['time']=0.01
		#format some custom fields
		tag['duration']=str(round(tag['duration']))[:-2]
		tag['displaytime'] = str(datetime.timedelta(seconds=round(tag['time'])))
		tag['url'] = 'http://'+os.environ['HTTP_HOST']+'/events/'+event+'/thumbs/tn'+str(tag['id'])+'.jpg'
		tag['own'] = tag['user']==user
		tag['deleted'] = (tag['deleted']==1 or tag['type']==3) #this will be removed in the future
		tag['success'] = True
		if(int(tag['type'])==4): #add telestration url for telestration tags only
			tag['teleurl']='http://'+os.environ['HTTP_HOST']+'/events/'+event+'/thumbs/tl'+str(tag['id'])+'.png'
		if(int(tag['bookmark'])):
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
		# return {
		#		 'type':tag['type'],
		#		 'id':tag['id'],
		#		 'url':'http://'+os.environ['HTTP_HOST']+'/events/'+event+'/thumbs/tn'+str(tag['id'])+'.jpg',
		#		 'name':tag['name'],
		#		 'starttime':tag['starttime'],
		#		 'duration':tag['duration'],
		#		 'displaytime':,
		#		 'time':tag['time'],
		#		 'coach':tag['coachpick'],
		#		 'colour':tag['colour'],
		#		 'own':own,
		#		 'deleted':(tag['deleted']==1 or tag['type']==3),
		#		 'comment':tag['comment'],
		#		 'success':success
		#	 }
	#end tagFormat
	#######################################################
	#returns file name for the video that contains appropriate time 
	#######################################################
	def _thumbName(self,seekTo,number=False):
		import math
		# global self.wwwroot
		# listPath = self.wwwroot+"/list.m3u8"
		#open m3u8 file:
		# f = open(listPath,"r")
		#the time of the current file. e.g. if there are 50 files of 1seconds each then file50.ts will be at 00:00:50 time. reachedTime contains the number of seconds since file0
		# reachedTime = 0.0
		try:
			seekTo = float(seekTo) # make sure this is not a string
		except:
			return 0
		#starting from the top, add up the times until reached desired time - that's the file
		#assuming m3u8 file is in this format:
		# #EXTINF:0.98431,
		# fileSequence531.ts
		#and so on - a line with time precedes the file 

		# fileName = ""
		# for line in f:
		#	 cleanStr = line.strip()
		#	 if(cleanStr[:7]=='#EXTINF'):#this line contains time information
		#		 reachedTime += float(cleanStr[8:-1]) #get the number (without the trailing comma)
		#	 elif(cleanStr[-3:]=='.ts' and seekTo<=reachedTime):#this line contains filename
		#		 #found the right time - this file contains the frame we need
		#		 fileName = cleanStr
		#		 break
		# f.close()

		# time of the thumbnail
		sec = round(seekTo)
		# for the file name
		# each .ts file contains slightly less than 1 second
		secname = str(round(seekTo/0.984315))[:-2] #trim the .0 from the name
		# convert time to hh:mm:ss
		# hr = math.floor(seekTo/3600)
		# mn = math.floor((seekTo-hr*3600)/60)
		# sc = math.floor(seekTo-hr*3600-mn*60)
		# tagTime = str(hr)[:-2].zfill(2)+":"+str(mn)[:-2].zfill(2)+":"+str(sc)[:-2].zfill(2)
		# s = hl.sha1(str(seekTo))
		fileName = "segm"+secname+".ts"
		if(number):#only return the number without the rest of the filename
			return secname
		return fileName
	#end calcThumb

#end pxp class