from imp import load_source as ls
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
		if not self.uri().segment(2,"")=='novideo':
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
		self.str().pout("")
		vidlen = len(os.listdir(self.wwwroot+"live/video/"))-2
		for i in range(0,800):
			col = hex(rr(0,255))[2:].rjust(2,'0')+hex(rr(0,255))[2:].rjust(2,'0')+hex(rr(0,255))[2:].rjust(2,'0')
			tstr = '{"name":"'+tags[i%len(tags)]+'","colour":"'+col+'","user":"356a192b7953b04c54574d18c28d46e6395428ab","tagtime":"'+str(rr(10,vidlen))+'","event":"live","period":"1"}'
			# print tstr+"<br/>"
			print self.tagset(tstr)
	#######################################################

	#######################################################
	# returns encoder status as a string, 
	# either json or plain text
	#######################################################
	def encoderstatus(self,textOnly=True):
		state = int(self._encState())
		if(state==1):
			status = "live"
		elif(state==2):
			status = "paused"
		else:
			status = "off"
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
		try:
			rez = os.system(self.wwwroot+"_db/encstart >/dev/null &")
			# add entry to the database that the encoding has started
			msg = self._logSql(ltype="enc_start",dbfile=self.wwwroot+"live/pxp.db",forceInsert=True)
		except Exception as e:
			rez = False
		# rez = False
		return {"success":not rez}
	#end encstart
	#######################################################
	#stops a live encode
	#######################################################
	def encstop(self):
		import os
		msg = ""
		try:
			rez = os.system(self.wwwroot+"_db/encstop >/dev/null &")
			os.system("/bin/kill `ps ax | grep mediastreamsegmenter | grep 'grep' -v | awk '{print $1}'`")
			os.system("/bin/kill `ps ax | grep ffmpeg | grep 'grep' -v | awk '{print $1}'`")
			msg = self._logSql(ltype="enc_stop",dbfile=self.wwwroot+"live/pxp.db",forceInsert=True)
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
			return {"success":True,"msg":cfg}
		return {"success":True,"msg":"No camera connected"}
	#######################################################
	#returns all the game tags for a specified event
	#######################################################
	def gametags(self):
		strParam = self.uri().segment(2,"{}")
		jp = json.loads(strParam)
		if not ('user' in jp and 'event' in jp and 'device' in jp):
			return self.str().err("Specify user, event, and device")

		#get user id
		usr = jp['user']
		#device ID
		dev = jp['device']
		#event
		evt = jp['event']
		return self._syncTab(user=usr, device=dev, event=evt, allTags = True)
	#######################################################
	#returns true if there is an active feed present
	#######################################################
	def islive(self):
		wwwroot = self.wwwroot
		hlsPresent = os.path.exists(wwwroot+'live/video/list.m3u8')
		return {"success":(self._encState()==1) and hlsPresent}
	def logincheck(self):
		io = self.io()
		email = io.get("email")
		passw = io.get("pass")
		# sess = self.session(expires=24*60*60,cookie_path="/")
		if not (email and passw):
			return self.str().err("Email and pass must be specified")
		if not self._inited():
			self.str().pout(self._init(io.get("email"),io.get("pass")))
		# check if user is in the database
		db = self.dbsqlite(self.wwwroot+"_db/pxp_main.db")
		encEm = self.enc().sha(email),
		encPs = self._hash(passw),
		sql = "SELECT * FROM `users` WHERE SHA(`email`) LIKE ? AND `password` LIKE ?"
		db.query(sql,(encEm,encPs))
		# log him in
		return None
		# return {io.get("email"):io.get("pass")}
		# return {"success":True}
	#######################################################
  	#get any new events that happened since the last update (e.g. new tags, removed tags, etc.)
	#######################################################
	def syncme(self):
		strParam = self.uri().segment(2,"{}")
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
	#modify a tag
	#######################################################
	def tagmod(self):
		wwwroot = self.wwwroot
		strParam = self.uri().segment(2,"{}")
		# strParam = '{"starttime":"367.090393","duration":"35","user":"fe5dbbcea5ce7e2988b8c69bcfdfde8904aabc1f","event":"live","id":9}'
		jp = json.loads(strParam)
		if not ('user' in jp and 'event' in jp and 'id' in jp):
			return self.str().err("Specify user, event, and tag id")
		#determine the info that user wants to update
		params = ()
		sqlInsert = []
		for mod in jp:
			if (mod=='user' or mod=="id" or mod=="event"):
				continue
			if (mod=='starttime' and float(jp[mod])<0):
				value = 0
			if (not mod=='delete'): #this case will happen more often - put it first
				sqlInsert.append("`"+mod+"`=?")
				params +=(jp[mod],)
			else:
				#when deleting a tag, simply change type to 3
				sqlInsert.append("`type`=?")
				params +=(3,)
		#end for mod in jp
		if len(sqlInsert)<1:#nothing was specified 
			return {'success':False}
		tid = jp['id']
		user = jp['user']
		event = jp['event']
		# parameters to add to the sql during a query call
		params += (tid,)
		#update the tag
		sql = "UPDATE `tags` SET "+(', '.join(sqlInsert))+" WHERE id=?"
		if(not os.path.exists(wwwroot+event+'/pxp.db')):
			return {'success':False}

		db = self.dbsqlite(wwwroot+event+'/pxp.db')
		success = db.query(sql,params) and db.numrows()>0
		if success:
			#add an entry to the event log that tag was updated or deleted
			success = self._logSql(ltype='mod_tags',lid=tid,uid=user,dbfile=wwwroot+event+'/pxp.db')
		if success:
			sql = "SELECT * FROM `tags` WHERE `id`=?"
			db.query(sql,(tid,))
			tag = db.getasc()
			return self._tagFormat(event=event, user=user, tagID=tid)
		return {'success':success}
	#end tagmod
	#######################################################
	#creates a new tag
	#information that needs to be submitted in json form:
	# {'event':'<event>','name':'<tag name>','id':'[tag_id]',
	#  'user':'user_hid','tagtime':'<time of the tag in seconds>',
	#  'colour':'<tag colour>','period':'<period number>',
	#  ['coachpick':'<0/1>'],['type':'<0/1/2/3...>']}
	#event can be an HID of an event or 'live' for live event
	#######################################################
	def tagset(self, tagStr=False):
		import json, os, sys
		wwwroot = self.wwwroot
		tagVidBegin = self.tagVidBegin
		if (not tagStr):
			tagStr = self.uri().segment(2)
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
			if (not os.path.exists(wwwroot+t['event']+'/pxp.db')):
				# this is the first tag in the event 
				self.disk().mkdir(wwwroot+t['event'])
				# copy the template db for tags
				self.disk().copy(wwwroot+'_db/event_template.db', wwwroot+t['event']+'/pxp.db')
			db.open(wwwroot+t['event']+'/pxp.db')
			db.transBegin()
			epath = wwwroot+t['event']+'/'
			#tag types:
			#default	= 0
			#start line	= 1
			#stop line	= 2
			#deleted	= 3 - this one won't happen on tagSet
			success = 1
			if(not 'type' in t):
				t['type'] = 0
			else:
				t['type'] = int(t['type'])
			if(not 'coachpick' in t):
				t['coachpick']=0
			if(t['type']==2):
				#tag 'stop' received - no need to add the stop tag to the database
				#simply update the duration and the type of the start tag
				#also set the starttime to begin when user tagged it, not at the usual -10 seconds
				sql = "UPDATE tags SET starttime=time, duration=(?-time), type=2 WHERE id=? AND user=? AND type=1"
				success = success and db.query(sql,(t['tagtime'],t['id'],t['user']))
				success = success and db.numrows()>0
				lastID = t['id']
			#if t['type']==2
			else:
				# TODO: check if this user already has a tag with the same name in the same place
				#add the tag to the database
				startTime=float(t['tagtime'])-tagVidBegin
				if startTime < 0:
					startTime = 0

				sqlVars = (t['name'], t['user'], startTime, t['type'], t['tagtime'], t['colour'], t['period'], t['coachpick'])
				# if duration was specified, add it to the sql
				if('duration' in t):
					# duration is specified
					sqlAdd = ",?"
					sqlVars += (t['duration'],)
					sqlFld = ", duration"
					if(t['duration']==0):
						# duration is zero - make starttime same as the time
						startTime = t['tagtime']
				else:
					# duration not specified - just leave the sql unchanged
					sqlAdd = ""
					sqlFld = ""
				# create the query
				sql = "INSERT INTO tags (name, user, starttime, type, time, colour, period, coachpick"+sqlFld+") VALUES(?, ?, ?, ?, ?, ?, ?, ?"+sqlAdd+")"
				success = success and db.query(sql,sqlVars)
				lastID = db.lastID()
			#if t['type']==1 ... else
			if(not success):
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
			if(not t['type']==2):
				#create a thumbnail for the tag video - only do this when a tag is created
				#i.e. tagStart is not technically a "tag" - wait till the Stop is set, then make a thumbnail
				fileName = self._thumbName(t['tagtime'])						
				#create a tag if it doesn't exist already
				imgFile = epath+"thumbs/tn"+str(lastID)+".jpg"
				if(not os.path.exists(imgFile)):
					vidFile = epath+"video/"+fileName
					sec = 0
					self._mkThumb(vidFile, imgFile, sec)
			#if not t['type']==2

			tagOut = {} # this dictionary will be returned
			if(t['type']==1):
				tagOut = {
					'id':lastID,
					'success':success
				}
			else:
				#log that a tag was created
				if(success):
					success = success and self._logSql(ltype="mod_tags",lid=lastID,uid=t['user'],dbfile=wwwroot+t['event']+'/pxp.db')
				tagOut = self._tagFormat(event=t['event'], user=t['user'], tagID=lastID)
			if(success):
				db.commit()
			else:
				db.rollback()
			#output result as JSON
			return tagOut
		except Exception as e:
			# print sys.exc_traceback.tb_lineno
			# print e
			db.rollback()
			return self.str().err()
	#end tagSet()
	#######################################################
	def teleset(self):
		import sys, Image
		wwwroot = self.wwwroot
		io = self.io()
		try:
			# create a tag first
			tagStr = str(io.get("tag"))
			event = json.loads(tagStr)['event']
			t = self.tagset(tagStr)
			#upload a file with the tag name
			imgID = str(t['id'])
			io.upload(wwwroot+event+"/thumbs/tl"+imgID+".png")
			# update the thumbnail with the telestration overlay
			# background is the thumbnail
			bgFile = wwwroot + event+"/thumbs/tn"+imgID+".jpg"
			# overlay is the png telestration
			olFile = wwwroot + event+"/thumbs/tl"+imgID+".png"			
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
			#### DEBUG ####
			t["zzzzzzzz"]= bgFile
			###END DEBUG###
			return t #already contains telestration url
		except Exception as e:
			# print sys.exc_traceback.tb_lineno
			# print e
			return self.str().err("No tag info specified")
###############################################
##			utility functions				 ##
###############################################
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
		wwwroot = self.wwwroot
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
				self.disk().mkdir(wwwroot+"live/video")
				self.disk().mkdir(wwwroot+"live/thumbs")
				self.disk().mkdir(wwwroot+"_db")
				#save the config info
				self._cfgSet(wwwroot+"_db/",[resp['authorization'],resp['customer']])
				#download the blank database files
				os.system("curl -#Lo "+wwwroot+"_db/event_template.db http://myplayxplay.net/assets/min/event_template.db")
				os.system("curl -#Lo "+wwwroot+"_db/pxp_main.db http://myplayxplay.net/assets/min/pxp_main.db")
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
		wwwroot = self.wwwroot
		# LATER ON: check if server is online. if so, check auth code against the cloud
		cfg = self._cfgGet(wwwroot+"_db/")
		return (len(cfg)>1 and cfg[0]=='.min config file')
	#end inited
	#######################################################
	#returns a list of events in the system
	#######################################################
	def _listEvents(self):
		wwwroot = self.wwwroot
		sql = "SELECT * FROM `events` WHERE strftime('%s',`date`)<= strftime('%s','now') AND `deleted`=0 ORDER BY `date` DESC"
		if(not os.path.exists(wwwroot+"_db/pxp_main.db")):
			return False
		db = self.dbsqlite(wwwroot+"_db/pxp_main.db")
		db.qstr(sql)
		evts = db.getasc()
		db.close()
		return evts
	#end listevents
	#######################################################
	#logs an entry in the sqlite database
	#######################################################
	def _logSql(self, ltype,lid=0,uid=0,dbfile="",forceInsert=False):
		import os
		if(not os.path.exists(dbfile)):
			return False
		db = self.dbsqlite(dbfile)
		# 
		#  TODO: fix duplicate sync_tablet - make the log select >= instead of logid>.....
		# 
		# check if this event has been logged since the last sync (no need to have duplicate events)
		sql = "SELECT IFNULL(MAX(`logID`),0) as `lid`, `type` FROM `logs` \
				WHERE `type` LIKE ? AND `id` LIKE ? \
					AND `logID`>IFNULL((SELECT MAX(`logID`) FROM `logs` WHERE `type` LIKE 'sync_%' AND `id` LIKE ?),0)"
		# update or insert a new entry
		db.query(sql,(ltype,lid,lid))

		rw = db.getrow()
		if((rw[0]>0) and not forceInsert):
			# this entry has been added recently, update the time, nothing else
			sql = "UPDATE `logs` SET `when`=datetime() WHERE `logID`=?";
			success = db.query(sql,(rw[0],))	
		else:
			# this entry does not exist yet
			sql = "INSERT INTO `logs`(`type`,`id`,`user`) VALUES(?,?,?)";
			success = db.query(sql,(ltype,lid,uid))
		# close db
		db.close()
		return success
	# end logSql
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
	#adds tags to an event during the sync procedure (gets called once for each event)
	#######################################################
	def _syncAddTags(self, path,tagrow,del_arr,add_arr):
		wwwroot = self.wwwroot
		if(not os.path.exists(path+'/pxp.db')):
			# event directory does not exist yet
			# create it recursively (default mode is 0777)
			self.disk().mkdir(path)
			# copy the template database there
			self.disk().copy(wwwroot+'_db/event_template.db', path+'/pxp.db')
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
	#######################################################
	#end syncAddEvt()
	#######################################################
	def _syncEnc(self, email="",password=""):
		global wwwroot
		db = self.dbsqlite()
		#open the main database (where everything except tags is stored)
		if(not db.open(wwwroot+"_db/pxp_main.db")):
			return False
		encEmail = self.enc().sha(email)
		encPassw = self._hash(password)
		url = 'http://www.myplayxplay.net/max/sync/ajax'
		# name them v1 and v2 to make sure it's not obvious what is being sent
		# v3 is a dummy variable
		# v0 is the authorization code (it will determine if this is encoder or another device)
		cfg = self._cfgGet(wwwroot+"_db/")
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
		tables = ['users','leagues','teams','events']
		for table in tables:
			if ((not (table in resp)) or (len(resp[table])<1)):
				continue
			sql_del = "DELETE FROM `"+table+"` WHERE"
			sql_ins = "INSERT INTO `"+table+"` "
			del_arr = [] #what will be deleted
			add_arr = [] #values will be added here
			# add all data rows in a single query
			for row in resp[table]:
				delField = row['del'] #contains name of the field that is the key used to delete entries from old tables
				#contains query conditions for deletion
				del_arr.append(' `'+delField+'` LIKE "'+self._cln(row[delField])+'" ') 

				#if the entry was deleted, move on to the next one (do not add it to the insert array)
				if('deleted' in row and row['deleted']=='1'):
					continue
				values = [] #contains values that are added to the query
				firstRow = {} #contains special format for the first row of the sql query (for SQLite)
				#go throuch each field in a row and add it to the query array
				for name in row:
					if(name=='del' or name=='deleted'):
						continue #this is only a name of a row - not actual data
					value = row[name]
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
			#remove it from the array (don't need it for the query)
			del tagrow['event']
			del_arr.append(" (`name` LIKE '"+tagrow['name']+"' AND `user` LIKE '"+tagrow['user']+"' AND `time`="+str(tagrow['time'])+") ")
			if ('deleted' in tagrow and tagrow['deleted']=='1'):
				#skip deleted tags
				continue
			fields = [] 
			for field in tagrow:
				fields.append('"'+self._cln(tagrow[field])+'" AS `'+field+'`')
			add_arr.append(", ".join(fields))
			#end for field in tagrow
			# sql = "INSERT INTO `tags`(`hid`, `name`, `user`, `time`, `period`, `duration`, `coachpick`, `bookmark`, `playerpick`, `colour`,`starttime`,`type`)";
		#end for tagrow in tags
		#last add/delete query will be run after all the tags were parsed:
		self._syncAddTags(eventDir+event,tagrow,del_arr,add_arr)
		return 1
	#end syncEnc
	#######################################################
	#syncs tablet with ecnoder (sends any tag modifications 
	#that were created in a specific event since the last sync)
	#######################################################
	def _syncTab(self, user, device, event, allTags=False):
		wwwroot = self.wwwroot
		##get the user's ip
		##userIP = os.environ['REMOTE_ADDR']
		if (not user) or len(user)<1 or (not device) or len(device)<1 or (not event) or len(event)<1 or (not os.path.exists(wwwroot+event+"/pxp.db")):
			return [] #return empty list if user did not provide the correct info or event does not exist
		db = self.dbsqlite(wwwroot+event+"/pxp.db")
		try:
			if(allTags):#selecting all tags from this game
				lastup = 0
				sql = "SELECT * FROM `tags` WHERE NOT `type`=3"
				db.qstr(sql)
			else:
				#get the time of the last update
				sql = "SELECT IFNULL(MAX(`logID`),0) AS `logid` FROM `logs` WHERE `id` LIKE ? AND `user` LIKE ? AND `type` LIKE 'sync_tablet' ORDER BY `logID`"
				success = db.query(sql,(device,user))
				lastup = db.getrow()
				lastup = lastup[0]
				#if alltags...else
				#get new events that happened since the last update
				#get all tag changes that were made since the last update
				sql = "SELECT DISTINCT(tags.id) AS dtid, tags.* FROM tags LEFT JOIN logs ON logs.id=tags.id WHERE (logs.logID>?) AND (logs.type LIKE 'mod_tags')"
				db.query(sql,(lastup,))
			#put them in a list of dictionaries:
			tags = db.getasc()
			#format tags for output
			tagsOut = {}
			for tag in tags:
				if(str(tag['time'])=='nan'):
					tag['time']=0
				tagJSON = self._tagFormat(tag=tag,event=event)
				if(allTags or not user==tag['user']):
					tagsOut[tag['id']]=(tagJSON)
			#end for tags:
	
			#get any other events (other than tags)
			sql = "SELECT type, id FROM logs WHERE logID>? AND NOT(type LIKE 'mod_tags' OR type LIKE 'sync%')"
			db.query(sql,(lastup,))
			evts = db.getasc()
			outJSON = {
				'tags':tagsOut,
				'events':evts,
				'camera':self.encoderstatus()
			}
			for key in outJSON.keys():
				if len(outJSON[key])<1:
					del(outJSON[key])
			if len(outJSON)>0: #only log sync when something was sync'ed
				self._logSql(ltype='sync_tablet',lid=device,uid=user,dbfile=wwwroot+event+'/pxp.db')
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

		tag['duration']=str(round(tag['duration']))[:-2]
		tag['displaytime'] = str(datetime.timedelta(seconds=round(tag['time'])))
		tag['url'] = 'http://'+os.environ['HTTP_HOST']+'/events/'+event+'/thumbs/tn'+str(tag['id'])+'.jpg'
		tag['own'] = tag['user']==user
		tag['deleted'] = (tag['deleted']==1 or tag['type']==3)
		tag['success'] = True
		tag['teleurl']='http://'+os.environ['HTTP_HOST']+'/events/'+event+'/thumbs/tl'+str(tag['id'])+'.png'
		if('hid' in tag):
			del(tag['hid'])
		for field in tag:
			if(tag[field]== None):
				tag[field] = ''
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
	def _thumbName(self,seekTo):
		import math
		# global wwwroot
		# listPath = wwwroot+"/list.m3u8"
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
		hr = math.floor(seekTo/3600)
		mn = math.floor((seekTo-hr*3600)/60)
		sc = math.floor(seekTo-hr*3600-mn*60)
		tagTime = str(hr)[:-2].zfill(2)+":"+str(mn)[:-2].zfill(2)+":"+str(sc)[:-2].zfill(2)
		# s = hl.sha1(str(seekTo))
		fileName = "segm"+secname+".ts"
		return fileName
	#end calcThumb

#end pxp class