compiled = False
# loads external python module (either from source or compiled)
def lm(module,path):
	global compiled
	from imp import load_source as ls
	from imp import load_compiled as lp
	if(compiled):
		return lp(module,path+"c") #compiled extensions are .pyc
	return ls(module,path)
from time import sleep
import os, json
m = lm("MVC","_m/mvc.py")

class pxp(m.MVC):
	# minimum free space required in order to have an encode running
	minFreeSpace = 1073741824 * 5 #5gb
#######################################################
#######################################################
################debug section goes here################
#######################################################
#######################################################
	#create a bunch of random tags
	def alll(self):
		from random import randrange as rr
		# tags = ["MID.3RD", "OFF.3RD", "DEF.3RD"]
		tags = ["purple","teal","cyan","white","yellow","black","blue","red","pink"]
		colours = ["FF0000","00FF00","0000FF","FF00FF","00FFFF","FFFF00","333366","FFFFFF"]
		self.str().pout("")
		vidlen = len(os.listdir(self.wwwroot+"live/video/"))-2
		for i in range(0,800):
			col = colours[i % len(colours)]
			tstr = '{"name":"'+tags[i%len(tags)]+'","colour":"'+col+'","user":"356a1927953b04c54574d18c28d46e6395428ab","time":"'+str(rr(10,vidlen))+'","event":"live"}'
			print self.tagset(tstr)
	def ttt(self):
		db = self.dbsqlite(self.wwwroot+"live/pxp.db")
		sql = "SELECT * FROM tags"
		db.qstr(sql)
		tags = db.getasc()
		# print tags
		# print "_"+tags[0]['comment']+"_"
		print str(tags[0]['comment'])==''
		db.close()
	def usbreset(self):
		import usb
		for bus in usb.busses():
			for dev in bus.devices:
				print dev.idVendor
				if int(dev.idVendor) == 0x1edb and int(dev.idProduct) == 0xbd43:
					print "resetting"
					conf = dev.configurations[0]
					print "confs", dev.configurations
					iface = conf.interfaces[0][0]
					print "ifaces[0]", conf.interfaces[0]
					endpoint = iface.endpoints[0]
					print "endpoints", iface.endpoints
					# open it
					handle = dev.open()

					print "iin", iface.interfaceNumber

					# usb 2-2: usbfs: interface 0 claimed by ldusb while 'python' sets config #1
					# ie. we need to run detacth *once* at least...
					# if None:
					handle.detachKernelDriver(0) # Should this be iface.interfaceNumber?
					# Note that if you don't run this, you'll actually get messages like
					# [222572.952000] usb usb1: usbfs: process 20986 (python) did not claim interface 1 before use
					# in dmesg...
					handle.setConfiguration(conf)
					handle.claimInterface(iface)
					handle.setAltInterface(iface)
					handle.reset()					
					# print dev
					# print dir(dev.dev)
					# dev.dev.reset()
#######################################################
	# def importfix(self):
	# 	from glob import glob
	# 	pathToEventDB = "/Volumes/Macintosh HD-1/private/var/www/html/events/"
	# 	eventDirs = glob(pathToEventDB+'*')
	# 	# go through every event, open the database and change league
	# 	leaguemap ={'6f99359b91f4af3f7bb726c37ca73d46c98152cc':'1574bddb75c78a6fd2251d61e2993b5146201319', #usehl16
	# 				'7da3b7ca3005af25d584597f0ce62e288c959ae1':'f1abd670358e036c31296e66b3b66c382ac00812', #usehl
	# 				'075bb6a5b912909f292c4fec737284f2614e9c53':'77de68daecd823babbb58edb1c8e14d7106e83bb', #EJHL
	# 				'fa7fee05b76d02dc2b9da32b58990c1adc5b2e98':'0716d9708d321ffb6a00818614779e779925365c', #EMPIRE
	# 				'df9b17f710ba0790e491010bc0542f061f00fbc5':'9e6a55b6b4563e652a23be9d623ca5055c356940'  #ESHL
	# 				}
	# 	for eventDir in eventDirs:
	# 		self._log("\n<br/>"+eventDir)
	# 		if (os.path.exists(eventDir+'/pxp.db')):
	# 			# open the database
	# 			db = self.dbsqlite(eventDir+'/pxp.db')
	# 			# get the current event info
	# 			sql = "SELECT `id` FROM `logs` WHERE `type` LIKE 'enc_start'"
	# 			db.qstr(sql)
	# 			eventInfo = db.getasc()
	# 			eventInfo = eventInfo[0]['id'].split(',')
	# 			self._log("\n<br/>")
	# 			self._log("\n"+eventDir.split('/')[-1:][0].split('_')[-1:][0][1:])
	# 			if(eventInfo[2] in leaguemap):
	# 				sql = "UPDATE `logs` SET `id`=? WHERE `type` LIKE 'enc_start'"
	# 				self._log("\n"+eventInfo[0]+','+eventInfo[1]+','+leaguemap[eventInfo[2]])
	# 				db.query(sql,(eventInfo[0]+','+eventInfo[1]+','+leaguemap[eventInfo[2]],))
	# 			db.close()
	# 		else:
	# 			self._log("\n<br/>fail")
	# import events from the old-style system
	# def importold(self):
	# 	from glob import glob
	# 	try:
	# 		# return #prevent accidental messups
	# 		self._x("Starting import...<br/>\n")
	# 		# name of the folder to parse:
	# 		cust = "SAC"
	# 		pathToOld = "/Users/dev/Downloads/"+cust
	# 		pathToNew = "/var/www/html/events/"
	# 		# create a blank copy of the new format database
	# 		if(not os.path.exists(pathToNew+'_db/pxp_main.db')):
	# 			# create directories
	# 			self.disk().mkdir(pathToNew+"_db")
	# 			self.disk().copy(self.wwwroot+'_db/pxp_main_blank.db', pathToNew+'_db/pxp_main.db')
	# 		# get all the old events
	# 		oldEvents = glob(pathToOld+"/htdocs/event/*")
	# 		# go through each one, and convert it:
	# 		teamLookup = {
	# 			# TIGERS TEAMS
	# 			# 'AUR':'Aurora',
	# 			# 'ORA':'Orangeville',
	# 			# 'OTHER':'OTHER',
	# 			# 'BUR':'Burlington',
	# 			# 'WHI':'Whitby',
	# 			# 'TRE':'Trenton',
	# 			# 'LIN':'Lindsay',
	# 			# 'STM':'St Michaels',
	# 			# 'TLP':'Toronto Lakeshore',
	# 			# 'KIN':'Kingston',
	# 			# 'WEL':'Wellington',
	# 			# 'COB':'Cobourg',
	# 			# 'STO':'Stouffville',
	# 			# 'GEO':'Georgetown',
	# 			# 'NMK':'Newmarket',
	# 			# 'PIC':'Pickering',
	# 			# 'HAM':'Hamilton'
	# 			# SAC TEAMS
	# 			'LFA':'Lake Forest',
	# 			'SAC':'St. Andrews',
	# 			'UCC':'UCC',
	# 			'LA':'Loyola Academy',
	# 			'SSA':'Shady Side',
	# 			'SFP':'St Francis Preps',
	# 			'GA':'Gilmour',
	# 			'RID':'Ridley Tigers',
	# 			'STA':'Stanstead College',
	# 			'NIC':'Nichols',
	# 			'APP':'Appleby',
	# 			'EDGE':'Edge',
	# 			'RMHS':'Rice Memorial HS',
	# 			'SMC':'St. Michael\'s',
	# 			'OTHER':'OTHER'
	# 		}
	# 		leagueLookup = {
	# 			'CISAA':'CISAA Hockey',
	# 			'MPHL': 'Midwest Prep Hockey League',
	# 			'OJHL': 'Ontario Junior Hockey League'
	# 		}
	# 		for event in oldEvents:
	# 			evtFile = event[event.rfind('/')+1:]
	# 			if(len(evtFile)<10):
	# 				continue
	# 			self._log("Found: "+event+"</br>\n")
	# 			# get the event folder name (not full path)
	# 			eventParts = evtFile.split('-')
	# 			# date in YYYY-MM-DD format
	# 			eventDate = eventParts[0][:4]+'-'+eventParts[0][4:6]+'-'+eventParts[0][6:8]
	# 			# time in HH:MM:SS format
	# 			eventTime = eventParts[1][:2]+":"+eventParts[1][2:]+":00" #seconds are assumed 00
	# 			# teams
	# 			homeTeam  = eventParts[2][1:]
	# 			if(homeTeam in teamLookup):
	# 				homeTeam = teamLookup[homeTeam]
	# 			vistTeam  = eventParts[3][1:]
	# 			if(vistTeam in teamLookup):
	# 				vistTeam = teamLookup[vistTeam]
	# 			# league
	# 			evtLeague = eventParts[4][1:]
	# 			if(evtLeague in leagueLookup):
	# 				evtLeague = leagueLookup[evtLeague]

	# 			self._log("Generating timestamp...<br/>\n")
	# 			# create timestamp (for database)
	# 			timestamp = eventDate+' '+eventTime
	# 			# format the directory name
	# 			stampForFolder = timestamp.replace(":","-").replace(" ","_")
	# 			minEvtHid = self.enc().sha(timestamp) #event hid - just SHA1 hash of the timestamp
	# 			db = self.dbsqlite(pathToNew+"_db/pxp_main.db")
	# 			sql = "INSERT INTO `events` (`hid`,`date`,`homeTeam`,`visitTeam`,`league`) VALUES(?,?,?,?,?)"
	# 			db.query(sql,(minEvtHid,timestamp,homeTeam,vistTeam,evtLeague))

	# 			self._log("Checking home team...<br/>\n")
	# 			# get hid of the teams
	# 			# home team
	# 			# check if team exists in the table already
	# 			sql = "SELECT `hid` FROM `teams` WHERE `name` LIKE ?"
	# 			db.query(sql,(homeTeam,))
	# 			dbresult = db.getasc()
	# 			if(len(dbresult)>0):
	# 				hmteamHID = dbresult[0]['hid']
	# 			else:
	# 				hmteamHID = self.enc().sha(homeTeam)
	# 				sql = "INSERT INTO `teams`(`hid`,`name`,`txt_name`) VALUES(?,?,?)"
	# 				db.query(sql,(hmteamHID,homeTeam,homeTeam))
	# 			self._log("Checking visitor team...<br/>\n")
	# 			# visitor team
	# 			sql = "SELECT `hid` FROM `teams` WHERE `name` LIKE ?"
	# 			db.query(sql,(vistTeam,))
	# 			dbresult = db.getasc()
	# 			if(len(dbresult)>0):
	# 				vsteamHID = dbresult[0]['hid']
	# 			else:
	# 				vsteamHID = self.enc().sha(vistTeam)
	# 				sql = "INSERT INTO `teams`(`hid`,`name`,`txt_name`) VALUES(?,?,?)"
	# 				db.query(sql,(vsteamHID,vistTeam,vistTeam))

	# 			self._log("Checking league...<br/>\n")
	# 			# get hid of the league
	# 			sql = "SELECT `hid` FROM `leagues` WHERE `name` LIKE ?"
	# 			db.query(sql,(evtLeague,))
	# 			dbresult = db.getasc()
	# 			if(len(dbresult)>0):
	# 				leagueHID = dbresult[0]['hid']
	# 			else:
	# 				leagueHID = self.enc().sha(evtLeague)
	# 				sql = "INSERT INTO `leagues`(`hid`,`name`,`short`,`sport`) VALUES(?,?,?,?)"
	# 				db.query(sql,(leagueHID,evtLeague,evtLeague,'Hockey'))
	# 			db.close()
	# 			#the name of the directory will be YYYY-MM-DD_HH-MM-SS_HTM1_VTM2_LNME
	# 			evtName = stampForFolder+'_H'+homeTeam[:3]+'_V'+vistTeam[:3]+'_L'+evtLeague[:3]
	# 			self.disk().mkdir(pathToNew+evtName+"/thumbs")
	# 			self.disk().mkdir(pathToNew+evtName+"/video")
	# 			self._log("Event added, checking tags...<br/>\n")
	# 			self.disk().copy(self.wwwroot+'_db/event_template.db', pathToNew+evtName+'/pxp.db')
	# 			# add event_start encoder event to the log
	# 			self._log("adding event...</br>\n")
	# 			msg = self._logSql(ltype="enc_start",lid=(hmteamHID+','+vsteamHID+','+leagueHID),dbfile=pathToNew+evtName+'/pxp.db')
	# 			# get list of thumbnails/telestrations for the event:
	# 			oldThumbs = glob(event+'/images/*.jpg')
	# 			oldTeles = glob(event+'/images/*.png')
	# 			# open the old sqlite database
	# 			dbnew = self.dbsqlite(pathToNew+evtName+'/pxp.db')
	# 			dbold = self.dbsqlite(event+'/tag.db')
	# 			# copy over the tag
	# 			sql = "SELECT * FROM `Enc_Tag`"
	# 			dbold.qstr(sql)
	# 			oldTags = dbold.getasc()
	# 			self._log("Tags found: "+str(len(oldTags)))
	# 			for oldtag in oldTags:
	# 				# get the extra data about the tag from the meta table:
	# 				sql = "SELECT * FROM `Enc_TagMeta` WHERE `secs`=?"
	# 				dbold.query(sql,oldtag['secs'])
	# 				extraRows = dbold.getasc()
	# 				strength = "5,5"
	# 				tagzone = ""
	# 				tagtype = 0
	# 				players = ""

	# 				# strength,tagzone
	# 				for row in extraRows:
	# 					if(row['metaName'].lower()=='players'):
	# 						players = row['value']
	# 					if(row['metaName'].lower()=='even'):
	# 						strength=str(row['value'])+','+str(row['value'])
	# 					if(row['metaName'].lower()=='pk'):
	# 						strength=str(row['value'])[:1]+','+str(int(str(row['value'])[:1])+1)
	# 					if(row['metaName'].lower()=='pp'):
	# 						strength=str(int(str(row['value'])[:1])+1)+','+str(row['value'])[:1]
	# 				#end for row in extraRows
	# 				if(oldtag['overlay']):
	# 					tagtype=4
	# 				if(oldtag['name'][:5].lower()=='f/off'):
	# 					name = oldtag['name']
	# 					oldtag['name'] = 'Face-off'
	# 					if(name[-1:].lower()=='w'):
	# 						oldtag['name'] += ' win'
	# 					else:
	# 						oldtag['name'] += ' loss'
	# 					tagzone = name[6:8].upper()
	# 				newTag = (oldtag['name'],oldtag['source'],oldtag['secs'],oldtag['period'],self.defaultTagDuration,oldtag['coach'],oldtag['colour'],float(oldtag['secs'])-10,tagtype,players,strength,tagzone)
	# 				sql = "INSERT INTO `tags`(name, user, time, period, duration, coachpick, colour, starttime, type, player, strength, zone) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)"
	# 				dbnew.query(sql,newTag)
	# 				newID = str(dbnew.lastID())
	# 				#copy the thumbnail
	# 				for imgName in oldThumbs:
	# 					if(imgName[imgName.rfind('/')+1:].find('l-'+str(oldtag['secs']))>-1):
	# 						# found image, copy it over
	# 						self.disk().copy(imgName,pathToNew+evtName+'/thumbs/tn_'+newID+'.jpg')
	# 				if(oldtag['overlay']):
	# 					# this tag is a telestration, copy the png file
	# 					for imgName in oldTeles:
	# 						if(imgName[imgName.rfind('/')+1:].find('o-'+str(oldtag['secs']))>-1):
	# 							# found image, copy it over
	# 							self.disk().copy(imgName,pathToNew+evtName+'/thumbs/tl_'+newID+'.png')
	# 			#end for tag in oldTags
	# 			dbnew.close()
	# 			dbold.close()
	# 			self._log("copying the video...")
	# 			vidPath = pathToOld+'/vod/event/'+evtFile+'-1.mp4'
	# 			self._log(vidPath)
	# 			if(os.path.exists(vidPath)):
	# 				self.disk().copy(vidPath,pathToNew+evtName+'/video/main.mp4')
	# 			else:
	# 				self._log("no video file")
	# 			self._log("event done<br/>\n<br/>\n")
	# 			# break
	# 		#end for event in events
	# 		self._log("conversion complete!\n<br/>")
	# 	except Exception as e:
	# 		import sys
	# 		return self._err(str(sys.exc_traceback.tb_lineno)+' '+str(e))
	#end importold
#######################################################
#######################################################
###################end of debug section################
#######################################################
#######################################################

	#######################################################
	# checks if there is enough space on the hard drive
	# if there isn't, stops whatever encode is going on
	# currently. 
	# @return boolean: true if there is enough free space
	#######################################################
	def checkspace(self):
		# find how much free space is available
		diskInfo = self._diskStat(humanReadable=False)
		enoughSpace = diskInfo['free']>self.minFreeSpace
		# if there's not enough, stop the current encode
		if(not enoughSpace):
			self.encstop()
		return enoughSpace
	#end checkspace
	#######################################################
	# creates a coach pick
	#######################################################
	def coachpick(self,sess):
		import glob
		# make sure there is a live event
		if(not os.path.exists(self.wwwroot+'live/video')):
			return self._err("no live event")
		if(self._stopping()):
			return self._stopping(msg=True)
		# get logged in user
		user = sess.data['user'] # user HID
		if(not os.path.exists(self.wwwroot+'_db/pxp_main.db')):
			return self._err("not initialized")
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
		# segFiles = glob.glob(self.wwwroot+"live/video/segm*.ts")
		# if(len(segFiles)<3):
		# 	return self._err("there is no video yet")
		# lastSeg = len(segFiles)-3 #segments start at segm0
		# # set time
		# tagTime = lastSeg * 0.984315
		# get the total video time minus a couple seconds (to make sure that .ts file already exists)
		tagTime = self._thumbName(0,totalTime=True)-2 
		try:
			tagnum = int(self.uri().segment(3,"1"))
		except Exception as e:
			tagnum = 1
		# create tag
		tagStr = '{"name":"Coach Tag '+str(tagnum)+'","colour":"'+colour+'","user":"'+user+'","time":"'+str(tagTime)+'","event":"live","coachpick":"1"}'
		return dict(self.tagset(tagStr),**{"action":"reload"})
	#######################################################
	# updates database to the latest format (from ios6 to ios7)
	#######################################################
	def dbupdate(self):
		pprefix = "/var/www/html/events/"
		# open the main db		
		db = self.dbsqlite(pprefix+"_db/pxp_main.db")
		# add 'datapath' column to the events table
		sql = "ALTER TABLE events ADD COLUMN datapath TEXT"
		db.qstr(sql)
		sql = "ALTER TABLE events ADD COLUMN extra TEXT"
		db.qstr(sql)
		sql = "ALTER TABLE teams ADD COLUMN league TEXT"
		db.qstr(sql)
		sql = "ALTER TABLE teams ADD COLUMN sport TEXT"
		db.qstr(sql)
		sql = "ALTER TABLE teams ADD COLUMN extra TEXT"
		db.qstr(sql)
		# update datapath in the table as proper path name: event timestamp + HID
		sql = "UPDATE events SET datapath=strftime('%Y-%m-%d_%H-%M-%S',`date`) || '_' || `hid`"
		db.qstr(sql)
		# get a list of all events
		sql = "SELECT strftime('%Y-%m-%d_%H-%M-%S',events.date) || '_H' || replace(replace(substr(events.homeTeam,1,3),' ','_'),'''','_') || '_V' || replace(replace(substr(events.visitTeam,1,3),' ','_'),'''','_') || '_L' || replace(replace(substr(events.league,1,3),' ','_'),'''','_') AS `oldpath`, events.*, leagues.sport FROM `events` LEFT JOIN `leagues` ON leagues.name=events.league"
		db.qstr(sql)
		events = db.getasc()
		db.close()
		# generate event folder: 2013-05-06_17-32-03_HTes_VSwa_LCIS - done in sql
		for event in events:
			# check if directory exists
			if(not os.path.exists(pprefix+event['oldpath']) or not os.path.exists(pprefix+event['oldpath']+"/pxp.db")):
				continue #move on to the next event
			# get sport
			sport = event['sport'].lower()
			# rename directory
			os.rename(pprefix+event['oldpath'],pprefix+event['datapath'])
			# connect to the event database
			db.open(pprefix+event['datapath']+'/pxp.db')
			# get all the tags
			sql = "SELECT * FROM `tags`"
			db.qstr(sql)
			tags = db.getasc()
			# alter table: remove - period, coachpick, bookmark, deleted, line, player, strength, zone
			#              add    - meta (TEXT)
			# sqlite doesn't support alter table - so have to re-create it
			# BEGIN TRANSACTION;
			# CREATE TEMPORARY TABLE tags_backup("id" INTEGER PRIMARY KEY  NOT NULL ,"hid" text,"name" text,"user" text,"time" decimal(5,3),"duration" INTEGER DEFAULT 30 ,"colour" text DEFAULT 000000 ,"starttime" decimal(5,3),"type" integer DEFAULT 0 ,"comment" TEXT,"rating" INTEGER DEFAULT 0 ,"extra" TEXT, "meta" TEXT);
			# INSERT INTO tags_backup SELECT * FROM `tags`;
			# DROP TABLE tags;
			# CREATE TABLE tags("id" INTEGER PRIMARY KEY  NOT NULL ,"hid" text,"name" text,"user" text,"time" decimal(5,3),"duration" INTEGER DEFAULT 30 ,"colour" text DEFAULT 000000 ,"starttime" decimal(5,3),"type" integer DEFAULT 0 ,"comment" TEXT,"rating" INTEGER DEFAULT 0 ,"extra" TEXT, "meta" TEXT);
			# INSERT INTO tags SELECT * FROM tags_backup;
			# DROP TABLE tags_backup
			# COMMIT;

			sql = """
					BEGIN TRANSACTION;
					DROP TABLE tags;
					CREATE TABLE tags("id" INTEGER PRIMARY KEY  NOT NULL,
									  "hid" text,
									  "name" text,
									  "user" text,
									  "time" decimal(5,3),
									  "duration" INTEGER DEFAULT 30 ,
									  "colour" text DEFAULT 000000 ,
									  "starttime" decimal(5,3),
									  "type" integer DEFAULT 0 ,
									  "comment" TEXT,
									  "rating" INTEGER DEFAULT 0 ,
									  "extra" TEXT, 
									  "meta" TEXT);
					COMMIT;
				"""
			db.qstr(sql,multiple=True)
			for tag in tags:
				# check type:
				# 0 - simply add it to the table:
					# id, name, user, time, duration, colour, starttime, type, comment, rating, meta (only if zone or player is specified) (extra is blank)
				# 1 & 2 - distinguish between line_f_ (type 1 & 2 ) and line_d (type 5 & 6) HOCKEY; and zone SOCCER
					# now add
					# id, name, user, time, duration, colour, starttime, type(1,2,5,6, 15,16), comment, rating, meta contains zone or line (extra is blank)
				# 3 - ignore
				# 4 - add it:
					# id, name, user, time, duration, colour, starttime, type(4), comment, rating (meta and extra are blank)
				# 5, 6 - player shift (those don't exist) - ignore
				# 7, 8 - period(hockey)/half(soccer)
					# now add
					# id, name, user, time, duration, colour, starttime, type(7,8, 17,18), comment, rating, meta contains period or half (extra is blank)
				# 9, 10 - strength (hockey only)
					# now add
					# id, name, user, time, duration, colour, starttime, type(9,10), comment, rating, meta contains strength (extra is blank)
				meta = {}
				tag['type'] = int(tag['type'])
				if(tag['type']==3): 
					continue
				oldfields =  ['period', 'bookmark', 'deleted', 'coachpick', 'line', 'player', 'strength', 'zone']
				for field in oldfields:
					# delete fields that are empty and extra attributes from telestrations
					#telestrations do not need this info
					if(field in tag and (str(tag[field])=='' or tag[field]==None) or tag['type']==4):
						del tag[field]

				if ('zone' in tag):
					meta['zone'] = tag['zone']
				if ('player' in tag):
					meta['player']=tag['player'].split(',')
				if (tag['type']==1 or tag['type']==2):
					if(tag['name'][:6]=='line_d'): #offence lines are types 5&6
						tag['type']=tag['type']+4
					if(sport=='soccer'):
						# for soccer 'lines' are zones: update - types 15&16
						tag['type']=tag['type']+14
						meta['zone']=tag['name']
				if(tag['type']==7 or tag['type']==8):
					if(sport=='hockey'):
						meta['period']=tag['name']
					if(sport=='soccer'):
						meta['half']=tag['name']
						tag['type']=tag['type']+10 #halfs are types 17&18 in soccer

				if(tag['type']==9 or tag['type']==10):
					meta['strength']=tag['strength']
					# tag['type']+=4# strength type is now 13 and 14
				if('coachpick' in tag and tag['coachpick']=='1'):
					meta['coachpick']="1"
				if(int(tag['rating'])>0):
					meta['rating']=tag['rating']
				sql = "INSERT INTO `tags`(`id`,`name`,`user`,`time`,`duration`,`colour`,`starttime`,`type`,`comment`,`rating`,`meta`) VALUES(?,?,?,?,?,?,?,?,?,?,?)"
				db.query(sql,(tag['id'],tag['name'],tag['user'],tag['time'],tag['duration'],tag['colour'],tag['starttime'],tag['type'],tag['comment'],tag['rating'],json.dumps(meta)))
			#end for tag in tags
			# go through logs and update current_XXXXXX to a number
			sql = "SELECT * FROM `logs`"
			db.qstr(sql)
			logs = db.getasc()
			if(sport=='hockey'):
				tagTypes = {'line':1,'period':7,'strength':9}
			else:
				tagTypes = {'line':15,'period':17}
			for log in logs:
				if(log['type'][:7]=='current'):
					tt = log['type'][8:]
					if(not tt in tagTypes):
						print tt
						continue
					curnum = tagTypes[tt]
					if(curnum==1 and log['id'][:6]=='line_d'):
						curnum=5
					newname='current_'+str(curnum)

					sql = "UPDATE `logs` SET `type`=? WHERE logID=?"
					db.query(sql,(newname,log['logID']))
			db.close() #close db for this event
		#end for event in events
	#end dbupdate
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
		if(not (self.disk().psOn("idevcopy") or progresses or copyStatus)):
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
				<div class="col_6 bold">Video bitrate (quality)</div>
				<div class="col_3">2 - 2.5 mbps</div>
				<div class="col_3">1 mbps</div>
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
				<div class="col_6 bold">Touch gestures</div>
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
			<div class="row">
				<div class="col_6 bold">Apple Approval</div>
				<div class="col_3 green large"><i class="icon-ok"></i></div>
				<div class="col_3 red large"><i class="icon-remove"></i></div>
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
		import subprocess
		# check to make sure the database event exists
		if(not os.path.exists(self.wwwroot+'_db/pxp_main.db')):
			return self._err("not initialized")
		io = self.io()
		folder = io.get('name') #name of the folder containing the content
		event  = io.get('event') #hid of the event  stored in the database
		if((not folder) or (len(folder)<5) or ('\\' in folder) or ('/' in folder) or len(self.wwwroot)<10):
			#either event was not specified or there's invalid characters in the name 
			#e.g. user tried to get clever by deleting other directories
			return self._err("Invalid event")
		# remove event folder
		# if(os.path.exists(self.wwwroot+folder)):
			# subprocess.Popen(["rm", "-r", self.wwwroot+folder])
			# os.system("rm -r "+self.wwwroot+folder+" >/dev/null &")
			# success = not subprocess.call("rm -r "+self.wwwroot+folder,shell=True) #os.system("rm -r "+self.wwwroot+folder)
		# remove the event from the database
		db = self.dbsqlite(self.wwwroot+"_db/pxp_main.db")
		sql = "UPDATE `events` SET `deleted`=1 WHERE `hid` LIKE ?"
		db.query(sql,(event,))
		db.close()
		# wait for files to finish removing
		if 'rmPipe' in locals():
			rmPipe.communicate()
		success = True
		return {"success":success}
	#end evtdelete
	#######################################################
	# returns encoder status as a string, 
	# either json or plain text (depending on textOnly)
	#######################################################
	def encoderstatus(self,textOnly=True):
		#		ffmpeg or mediasegmenter are on
		#       | app starting
		#       | | encoder streaming
		#       | | | camera present
		#       | | | | pro recorder present
		#       | | | | |
		# bits: 0 0 0 0 0
		try:
			state = self._encState()
			stopped = not (self.disk().psOn("ffmpeg -f mpegts -i udp") or self.disk().psOn("mediastreamsegmenter"))
			if(self._stopping()):
				state=0
				status = "Event is being stopped"
			elif((state & (1+2+4))==7): #live is defined as: pro recoder + camera + streaming
				# app is paused if mediasegmenter and ffmpeg are running, there is no stopping.txt file, and ports are set to 65535
				# stopping = self._stopping()
				# when app is stopping the encoder status will be set to 'off'
				paused = (not self.disk().psOn("pxpStream.app") or self._portSame()) and self.disk().psOn("ffmpeg -f mpegts -i udp") and self.disk().psOn("mediastreamsegmenter")
				if (paused):
					status = "paused"
				# elif(stopping):
				# 	status = "stopping"
				elif(stopped):
					status = "stopped"
				else:
					status = "live"
			elif(not (state&1)):
				status = "pro recoder disconnected"
			elif(not (state&2)):
				status = "camera disconnected"
			elif(state & 8):
				status = "streaming app is starting"
			else:
				status = "preparing to stream"
			if (stopped):
				state &= ~16; 
			else:
				state |= 16; #when stopped bit 4 will be set to 1
			if (textOnly):
				return status
			return {"status":status,"code":state}
		except:
			import sys
			return self._err(str(sys.exc_traceback.tb_lineno)+' '+str(e))
	#end encoderstatus
	def encoderstatjson(self):
		return self.encoderstatus(textOnly = False)
	#######################################################
	#pauses a live encode
	#######################################################
	def encpause(self):
		import os
		msg = ""
		rez = False
		try:
			if(self._stopping()):
				return self._stopping(msg=True)
			# rez = os.system("echo '3' > /tmp/pxpcmd")
			self._portSet(hls=65535,ffm=65535,chk=65535)
			# add entry to the database that the encoding has paused
			msg = self._logSql(ltype="enc_pause",dbfile=self.wwwroot+"live/pxp.db")
			self.disk().sockSend(json.dumps({'actions':{'event':'live','status':'paused'}}))
		except Exception as e:
			msg = str(e)
			rez = True
		# rez = False
		return {"success":not rez,"msg":msg}
	#end encpause
	#######################################################
	#resumes a paused encode
	#######################################################
	def encresume(self):
		import os
		msg = ""
		rez = False
		try:
			if(self._stopping()):
				return self._stopping(msg=True)
			# rez = os.system("echo '4' > /tmp/pxpcmd")
			# add entry to the m3u8 file to signify discontinuity
			# os.system("echo '#EXT-X-DISCONTINUITY' >> "+self.wwwroot+'live/video/list.m3u8')
			self._portSet()
			# add entry to the database that the encoding has paused
			msg = self._logSql(ltype="enc_resume",dbfile=self.wwwroot+"live/pxp.db")
			self.disk().sockSend(json.dumps({"actions":{'event':'live','status':'live'}}))
			rez = False
		except Exception as e:
			rez = True
		# rez = False
		return {"success":not rez}
	#end encresume
	#######################################################
	#shuts down the encoder
	#######################################################
	def encshutdown(self):
		import os
		msg = ""
		try:
			if(os.path.exists(self.wwwroot+"live/evt.txt")):
				self.encstop() #there is a live event - stop it before shut down
			while(self._stopping()):
				sleep(1) #wait until the live stream is stopped
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
		try:
			success = True
			if(not os.path.exists(self.wwwroot+'_db/pxp_main.db')):
				return self._err("not initialized")
			# if an event is being stopped, wait for it
			while(self._stopping()):
				sleep(1)
			# make sure there is enough free space
			if(not self.checkspace()):
				return self._err("Not enough free space to start a new encode. Delete some of the old events from the encoder.")
			# make sure not overwriting an old event
			if(os.path.exists(self.wwwroot+"live/evt.txt")):
				self.encstop()
			#make sure the 'live' directory was initialized
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

			# create new event in the database
			# get time for hid and for database in YYYY-MM-DD HH:MM:SS format
			timestamp = self._time()
			stampForFolder = timestamp.replace(":","-").replace(" ","_")

			minEvtHid = self.enc().sha(self._time(timeStamp=True))+'_local' #local event hid (temporary, will be updated when the event goes up to .Max)
			db = self.dbsqlite(self.wwwroot+"_db/pxp_main.db")
			#the name of the directory will be YYYY-MM-DD_HH-MM-SS_EVENTHID
			evtName = stampForFolder+'_'+minEvtHid#'_H'+hmteam[:3]+'_V'+vsteam[:3]+'_L'+league[:3]
			sql = "INSERT INTO `events` (`hid`,`date`,`homeTeam`,`visitTeam`,`league`,`datapath`) VALUES(?,?,?,?,?,?)"
			db.query(sql,(minEvtHid,timestamp,hmteam,vsteam,league,evtName))
			#store the event name (for processing when it's stopped)
			self.disk().file_set_contents(self.wwwroot+"live/evt.txt",evtName)

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
			msg = self._logSql(ltype="enc_start",lid=(hmteamHID+','+vsteamHID+','+leagueHID),dbfile=self.wwwroot+"live/pxp.db")
			self.disk().sockSend(json.dumps({"actions":{'event':'live','status':'live'}}))

			self._portSet()
			# start hls (media segmenter)
			# & at the end puts it in the background mode - so that the execution won't halt because of it
			# -p 		: create VOD
			# -t 1s 	: segment duration (1 second)
			# -S 1 		: start first segment file at ______1.ts
			# -B segm 	: name segment files as segm*.ts
			# -i list  	: the list file will be named as list.m3u8
			# -f ... 	: directory to output the segments
			# -127.0.0.1:2222 	: listen on port 2222 of local host to incoming UDP packets
			#>/dev/null &		: throw all output to null, & at the end puts it in background process (so python doesn't stop)
			success = success and not os.system("mediastreamsegmenter -p -t 1s -S 1 -B segm -i list.m3u8 -f "+self.wwwroot+"live/video 127.0.0.1:2222 >/dev/null &")

			# start the mp4 capture using ffmpeg
			# parameters:
			# -f mpegts: format of the video
			# -i 'udp....':  input file/stream (the udp port is the one to which this app sends packets)
			# -re : maintain the frame rate
			# -y : overrite output file without asking
			# -strict experimental: needed to have proper mp4 output
			# -vcodec copy: do not reincode
			# -f mp4: MP4 format
			# /var/www/.....mp4: output file
			# 2>/dev/null: redirect output to null, 2 since ffmpeg outputs to stderr not stdout
			# &: put the execution in background mode
			success = success and not os.system("ffmpeg -f mpegts -i 'udp://127.0.0.1:2223?fifo_size=1000000&overrun_nonfatal=1' -re -y -strict experimental -vcodec copy -f mp4 "+self.wwwroot+"live/video/main.mp4 2>/dev/null >/dev/null &")

			# return self._err(minEvtHid)
			if success:
				evtHid = minEvtHid
				# save the event ID
				self.disk().file_set_contents(self.wwwroot+"live/eventid.txt",evtHid)
			#if success
			msg = ""
		except Exception as e:
			import sys
			return self._err(str(e)+' '+str(sys.exc_traceback.tb_lineno))
		return {"success":success,"msg":msg}
	#end encstart
	#######################################################
	#stops a live encode
	#######################################################
	def encstop(self):
		msg = ""
		try:
			if(not os.path.exists(self.wwwroot+'live')):
				return self._err('no live event to stop')
			timestamp = self._time(timeStamp=True)

			# end any duration tags (lines, periods, etc.) set their duration to the end of the video
			# get the length of the video
			totalVidLength = self._thumbName(totalTime=True)
			# update all the odd-type (start) tags to proper duration
			sql = "UPDATE `tags` SET `duration`=CASE WHEN (?-`time`)>0 THEN (?-`time`) ELSE 0 END, `type`=`type`+1 WHERE (NOT (`type`=3)) AND ((`type` & 1)=1)"
			db = self.dbsqlite(self.wwwroot+'live/pxp.db')
			db.query(sql,(totalVidLength,totalVidLength))
			db.close()

			# make sure nobody creates new tags or does other things to this event anymore
			os.system("echo '"+timestamp+"' > "+self.wwwroot+"live/stopping.txt")
			self.disk().sockSend(json.dumps({"actions":{'event':'live','status':'stopped'}}))
			
			
			# stop HLS segmenting
			if(self.disk().psOn("mediastreamsegmenter")):
				os.system("/usr/bin/killall mediastreamsegmenter")
			# stop ffmpeg and wait for it to complete (to have a working mp4)
			if(self.disk().psOn("ffmpeg")):
				os.system("/bin/kill `ps ax | grep \"ffmpeg -f mpegts -i udp://\" | grep 'grep' -v | awk '{print $1}'`")
			# make sure pxpStream restarts
			os.system("/usr/bin/killall pxpStream")
			# wait for ffmpeg to finish its job, and for handbrake (in case user was creating bookmarks)
			while (self.disk().psOn('ffmpeg') or self.disk().psOn("handbrake")):
				sleep(1) #wait for ffmpeg to finish its job
				if(self.disk().psOn("ffmpeg -f mpegts -i udp")):
					os.system("/bin/kill `ps ax | grep \"ffmpeg -f mpegts -i udp://\" | grep 'grep' -v | awk '{print $1}'`")

			# stop the pxpStream app (it'll restart automatically, this is left over from the old times)
			rez = os.system("echo '2' > /tmp/pxpcmd")
			msg = self._logSql(ltype="enc_stop",dbfile=self.wwwroot+"live/pxp.db")
			
			# rename the live directory to the proper event name
			self._postProcess()
			# check if there are clips being generated
			bookmarking = self.disk().psOn("ffmpeg -ss") or self.disk().psOn("handbrake") or self.disk().psOn("ffmpeg -i")
		except Exception as e:
			bookmarking = False
			rez = False
			msg=str(e)
		return {"success":not rez,"msg":msg,"bookmarking":bookmarking}
	#end encstop
	#######################################################
	# returns the input video settings
	#######################################################
	def getcamera(self):
		# check if streamer app is running
		# return {"success":True,"msg":"test","encoder":"Live"}
		appon = self.disk().psOn('pxpStream.app')
		# get camera info
		cfg = self.disk().file_get_contents(self.wwwroot+"_db/.cam")
		if appon and cfg:
			return {"success":True,"msg":cfg,"encoder":self.encoderstatus()}
		return {"success":True,"msg":"N/A","encoder":self.encoderstatus()}
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
		if(self._stopping(evt)):
			return self._stopping(msg=True)
		return self._syncTab(user=usr, device=dev, event=evt, allData = True)
	#end gametags
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
		io = self.io()
		event = io.get('event')
		try:
			if not event: #event was not specified
				return self._err()
			# make sure it has no : or / \ in the name
			if('/' in event or '\\' in event): #invalid name
				return self._err()
			if(self._stopping(event)):
				return self._stopping(msg=True)
			db = self.dbsqlite(self.wwwroot+event+'/pxp.db')
			# select all even-type tags (deleted are odd, so won't be downloaded)
			db.qstr('SELECT * FROM `tags` WHERE  (`type` & 1) = 0')
			xmlOutput = '<?xml version="1.0" encoding="UTF-8"?>\n'+\
						'<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">\n'+\
						'<plist version="1.0">\n<dict>\n'
			# get each tag, format it and output to xml
			tags = db.getasc()
			# add playing teams
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
			db.close()

			for t in tags:
				# format the tag (get thumbnail image, telestration url, etc.)
				tag = self._tagFormat(event=event,tag=t)
				xmlOutput+=self._xmldict(t,t['id'],1)
			# finish the xml
			xmlOutput += '</dict>\n</plist>'
			# remove old plist if it exists
			if(os.path.exists(self.wwwroot+event+'/tags.plist')):
				os.remove(self.wwwroot+event+'/tags.plist')
			# plist file is ready, write it out:
			self.disk().file_set_contents(self.wwwroot+event+'/tags.plist',xmlOutput)

			# create extra.plist file
			xmlOutput = '<?xml version="1.0" encoding="UTF-8"?>\n'+\
						'<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">\n'+\
						'<plist version="1.0">\n<dict>\n'
			# for now extra only contains teams info (will add other stuff later if needed)
			xmlOutput+=self._xmldict(teamHIDs,"teams",1)
			xmlOutput+='</dict>\n</plist>'
			# remove old extra.plist if it exists
			if(os.path.exists(self.wwwroot+event+'/extra.plist')):
				os.remove(self.wwwroot+event+'/extra.plist')
			# plist file is ready, write it out:
			self.disk().file_set_contents(self.wwwroot+event+'/extra.plist',xmlOutput)

			return {"success":True}
		except Exception as e:
			import sys 
			return self._err(str(sys.exc_traceback.tb_lineno)+' '+str(e))
	#end prepdown
	#######################################################
	# service function - executed every 10 seconds, 
	# runs any service routines required for pxp
	#######################################################
	def _slog(self,text):
		# generate timestamp
		timestamp = self._time()
		os.system("echo '"+timestamp+": "+text+"' >> "+self.wwwroot+"_db/log.txt")

	def service(self):
		# deleting old events
		try:
			self._slog("service")
			if(not self._deleting()):

				self._slog('not deleting')
				# delete session files that are over 1 day old
				os.system('find '+self.wwwroot+"session -mtime +1 -type f -exec rm {} \\;")
				# delete the contents of the apache logs if it's over 500mb
				# logSize = os.stat("/var/log/apache2/access_log").st_size
				# if (logsize>200*1024*1024):
				# 	os.system("rotatelogs ")

				# delete any undeleted directories
				# get a list of deleted events
				oldevents = self._listEvents(onlyDeleted = True)
				# print oldevents
				if (len(oldevents)>0):
					self._slog("found "+str(len(oldevents))+" old events")
					# print "deleting..."
					db = self.dbsqlite(self.wwwroot+"_db/pxp_main.db")
					for event in oldevents:
						self._slog("start deleting: "+str(event))
						# print "DELETING event"
						# make sure there is a directory associated with the event
						if(not 'datapath' in event):
							# print "no datapath"
							#delete the event from the database (if there's no path to the file)
							sql = "DELETE FROM `events` WHERE `hid` LIKE ?"
							db.query(sql,(event['hid'],))
							continue
						# make sure directory path is not corrupted
						if(event['datapath'].find("/")>=0 or len(event['datapath'])<3):
							self._slog("invalid path")
							# print "invalid datapath"
							continue
						# check if it exists
						if(os.path.exists(self.wwwroot+event['datapath'])):
							self._slog("deleting files...")
							for r,d,f in os.walk(self.wwwroot+event['datapath']):
							    os.chmod( r , 0777)
							# remove the files
							cmd = "rm -rf "+self.wwwroot+event['datapath']+" >/dev/null &"
							self._slog(cmd)
							os.system(cmd)
							break #delete only 1 folder at a time
						else:
							# print "no files to delete"
							#delete the event from the database (once the file have been deleted)
							sql = "DELETE FROM `events` WHERE `hid` LIKE ?"
							db.query(sql,(event['hid'],))
					#for event in oldevents
					db.close()
				#if oldevents>0
				else:
					self._slog("zero deleted events")
			#if not self._deleting()
			else:
				self._slog("deleting")
				# print "deleting..";
		except:
			try:
				db.close()
			except:
				pass
		# uploading live stuff
		try:
			settings = self.settingsGet()
			# check if user has upload enabled
			if(int(settings['uploads']['autoupload']) and not self._uploading()):
				self._slog('uploading checked')
				# make sure autoupload is enabled and there is no upload happening already
				# check if there are segment files to upload
				if(self.io().isweb()):
					self._slog("online")
					event = "live"
					# check if there is a live game
					if(os.path.exists(self.wwwroot+event) and not self._stopping(event=event)):
						self._slog("upload tags")
						# UPLOAD TAGS
						# check if there are new tags to upload
						try:
							lastTagID = int(self.disk().file_get_contents(self.wwwroot+event+"/lasttag.txt"))
						except:
							# no tags were uploaded yet - this happens when event wasn't registered in the cloud - register it
							try:
								# get home team, visitor team, league
								db = self.dbsqlite(self.wwwroot+event+'/pxp.db')
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
								db.close()
	# GET TIMESTAMP FROM EVENT, NOT FROM CURRENT TIME!!!
								# send a request to create a new event in the cloud
								cfg = self._cfgGet(self.wwwroot+"_db/")
								# check if there is internet
								if self.io().isweb():
									url = "http://www.myplayxplay.net/maxdev/eventSet/ajax"
									params ={   'homeTeam':hmteamHID,
												'visitorTeam':vsteamHID,
												'league':leagueHID,
												'date':timestamp,
												'season':timestamp[:4], #just the year part of the date
												'v0':cfg[1], #authentication code
												'v1':cfg[2] #customer ID
											}
									resp = self.io().send(url,params,jsn=True)
									if resp and 'success' in resp and resp['success']:
										# the requrest was successful, get the HID of the new event
										maxEvtHid = resp['msg']
										# update it in the local database
										sql = "UPDATE `events` SET `hid`=? WHERE `hid`=?"
										db = self.dbsqlite(self.wwwroot+"_db/pxp_main.db")
										db.query(sql,(maxEvtHid,minEvtHid))
										db.close()
										evtHid = maxEvtHid
									#if resp['success']
									# else:
									# 	return self._err(str(resp))
								#if isweb
								lastTagID = 0
							#end try create new cloud event
							except:
								pass
						#end try get last tag id..except

						# find if there were tags created after the last
						db = self.dbsqlite(self.wwwroot+event+"/pxp.db")
						sql = "SELECT * FROM `tags` WHERE `id`>? ORDER BY `id`"
						db.query(sql,(lastTagID,))
						tags = db.getasc()
						db.close()
						# print tags						
						##############
						#exit for now#
						##############
						return
						for tag in tags:
							# set url parameters
							# extract meta parameters as individual fields:
							metaparams = json.loads(tag['meta'])
							# remove meta field from the tag
							del tag['meta']
							# add parameters from meta alongside with all the other params
							tag.update(metaparams)
							# set the event name (hid)
							# tag['event'] = 
							# url = 'http://myplayxplay.net/mid/ajax/tagset/'+json.dumps(tag)
							# params = {
							# 	''
							# }
							# create the tag in the cloud
							# resp = self.io().send(url, params, jsn=True)

							# record it
							self.disk().file_set_contents(self.wwwroot+event+"/lasttag.txt",tag['id'])
						# UPLOAD VIDEO
						# get the last uploaded .ts segment:
						lastUploaded = self.disk().file_get_contents(self.wwwroot+event+"/lastup.txt")				
						if(not lastUploaded):
							response = {}
							# nothing was uploaded yet, get the first file segment
							self._thumbName(10,results=response,event=event)
							nextFile = response['firstSegm']
						else:
							# the next segment file index
							nextNum = self._exNum(lastUploaded)+1
							# the string containing prefix before the digit
							filestr = self._exStr(lastUploaded)
							if(filestr[-3:]=='.ts'):
								# there are no letters before the digit, file name format: XXtext.ts
								nextFile = str(nextNum)+filestr
							else:
								# there is text before digit, file name format: textXX.ts
								nextFile = filestr + str(nextNum)+'.ts'
						#if not lastuploaded...else

						# get contents of the list file in an array
						listFile = self.disk().file_get_contents(self.wwwroot+event+"/video/list.m3u8")
						listArray = listFile.splitlines()
						# make sure the segment is in the file
						if(not nextFile in listArray):
							# file was not found in the list - some weird bug happened
							return
						# get the index of the element containing the file (i.e. line number)
						fileIndex = listArray.index(nextFile)
						# the line before contains the duration of this segment
						timeIndex = fileIndex-1
						# get the duration of the segment file to be uploaded
						nextTime = self._exNum(listArray[timeIndex],floatPoint=True)
						for idx in range(fileIndex, len(listArray), 2):
							# after every 8 segments check if user disabled uploading
							if(idx & 7==7): #will check when last 3 bits are 111, this is faster on CPU than (idx % 7)
								settings = self.settingsGet()
								try:
									if(not int(settings['uploads']['autoupload'])):
										break
								except:
									break

							# get the file name
							nextFile = listArray[idx]
							nextTime = str(self._exNum(listArray[idx-1],floatPoint=True))
							# upload the file
							result = self._uploadFile(self.wwwroot+event+"/video/"+nextFile,event=event,extraData=[nextTime])
							if(result and 'success' in result and result['success']):
								lastUploaded = nextFile
								self.disk().file_set_contents(self.wwwroot+event+"/lastup.txt",lastUploaded)
							else: #if upload failed, cancel the cycle, it will resume when service() gets called again
								break
						#for idx 
					#if live and not stopping
					else:#if there is no live game, upload any unaploaded events
					# get list of events that are uploaded on the server
					# check which events exist in the local database that are not on the server yet
					# upload that event
						pass
				#if isweb
			#if autoupload and not uploading
		except Exception as e:
			import sys
			# print str(sys.exc_traceback.tb_lineno)+' '+str(e)	
	#end service
	# retreives the settings file in json format
	def settingsGet(self):
		from collections import OrderedDict
		settings = self.disk().iniGet(self.wwwroot+"_db/.pxpcfg")
		try:
			# go through each section and assign possible values for it
			# make sure the setting section is available (if it's not, add it)
			# video settings
			if(not 'video' in settings): #video setting was not set
				settings['video']={'bitrate':5000}
			try:
				# check that bitrate is a valid number
				val = int(settings['video']['bitrate'])
				if(val<1000):
					settings['video']['bitrate']=5000
			except:
				settings['video']['bitrate']=5000
			settings['video']['bitrate_options']=OrderedDict([
				(5000,"Very high (5Mbps)"),
				(3000,"High (3Mbps)"),
				(2500,"Medium (2.5Mbps)"),
				(2000,"Low (2Mbps)"),
				(1500,"Very low (1.5Mbps)"),
				(1000,"Poor (1Mbps)")
			])
			# MyClip settings
			if(not 'clips' in settings):
				settings['clips']={'quality':1}
			try:
				# check that quality is a valid number
				val = int(settings['clips']['quality'])
				if(val<1):
					settings['clips']['quality']=8
			except:
				settings['clips']['quality']=8
			settings['clips']['quality_options']=OrderedDict([
				(1,"Very high"),
				(3,"High"),
				(6,"Medium"),
				(8,"Low"),
				(10,"Very low"),
			])
			# Tags settings
			if(not 'tags' in settings):
				settings['tags']={'preroll':5,'postroll':5}
			if(not 'preroll' in settings['tags']):
				settings['tags']['preroll']=5
			if(not 'postroll' in settings['tags']):
				settings['tags']['postroll']=5
			try:
				# check that preroll and postroll are valid numbers
				val1 = int(settings['tags']['preroll'])
				if(val1<0):
					settings['tags']['preroll']=10
				val2 = int(settings['tags']['postroll'])
				if(val2<0):
					settings['tags']['postroll']=10
				if((val1+val2)<5):
					settings['tags']['postroll']=10
					settings['tags']['preroll']=10
			except:
				settings['tags']['postroll']=10
				settings['tags']['preroll']=10

			settings['tags']['preroll_options']=OrderedDict([
				(0,"0s"),
				(1,"1s"),
				(2,"2s"),
				(5,"5s"),
				(10,"10s"),
				(20,"20s")
			])
			settings['tags']['postroll_options']=OrderedDict([
				(0,"0s"),
				(1,"1s"),
				(2,"2s"),
				(5,"5s"),
				(10,"10s"),
				(20,"20s")
			])
		except:
			# could not get/parse some settings, download the config file from the cloud
			pass
		return settings
	#end settingsGet
	# updates the config settings with whatever user selected
	def settingsSet(self):
		io = self.io()
		# get the parameter that user is trying to set
		secc = io.get("section")
		sett = io.get("setting")
		vals = io.get("value")
		if(secc=='video' and sett=='bitrate'):
			# changing video stream quality
			self.disk().file_set_contents(self.wwwroot+"_db/.cfgenc",vals)
			# reset the streaming app
			self.disk().file_set_contents("/tmp/pxpcmd","2")
			# add an event to live stream to indicate that the bitrate was changed
			self._logSql(ltype="changed_bitrate",lid=str(vals),dbfile=self.wwwroot+"live/pxp.db")
		# will be true or false depending on success/failure
		success = self.disk().iniSet(self.wwwroot+"_db/.pxpcfg",section=secc,param=sett,value=vals)
		return {"success":success}
	#end settingsSet
	# returns summary for the month or game
	def sumget(self):
		try:
			strParam = self.uri().segment(3,"{}")
			jp = json.loads(strParam) #json params
			if not ('user' in jp and 'id' in jp and 'type' in jp):
				return self._err("Specify event or month")
			# select the proper summary from the table
			sql = "SELECT * FROM `summary` WHERE `type` LIKE ? AND `id` LIKE ?"
			db = self.dbsqlite(self.wwwroot+"_db/pxp_main.db")
			db.query(sql,(jp['type'],jp['id']))
			# fetch the data
			summary = db.getasc()
			db.close()
			# return the summary if it's in the database
			if(len(summary)>0):
				return summary[0]
			return {"summary":""}
		except Exception as e:
			import sys 
			return self._err(str(sys.exc_traceback.tb_lineno)+' '+str(e))
	#end sumget
	# sets summary for month or game
	def sumset(self):
		try:
			# get the information from url
			strParam = self.uri().segment(3,"{}")
			jp = json.loads(strParam) #json params
			if not ('user' in jp and 'summary' in jp and 'id' in jp and 'type' in jp):
				return self._err("Specify event or month and summary")
			#add the info or update it (if already exists)
			sql = "INSERT OR REPLACE INTO `summary`(`summary`,`type`,`id`) VALUES(?,?,?)"
			db = self.dbsqlite(self.wwwroot+"_db/pxp_main.db")
			db.query(sql,(jp['summary'],jp['type'],jp['id']))
			db.close()
			return {"success":True}
		except Exception as e:
			import sys 
			return self._err(str(sys.exc_traceback.tb_lineno)+' '+str(e))
	#end sumset
	def sync2cloud(self,sess):
		try:
			if not ('ee' in sess.data and 'ep' in sess.data):
				return self._err("Not logged in")
			#the dict({},**{}) is to combine 2 dictionaries into 1: 
			#{"success":True/False} and {"action":"reload"})
			self._syncEncUp(sess.data['ee'],sess.data['ep'])
			syncResponse = self._syncEnc(sess.data['ee'],sess.data['ep'])
			if ('success' in syncResponse):
				return syncResponse
 			return dict(syncResponse,**{"action":"reload"})
		except Exception as e:
			import sys
			return self._err("Error occurred please contact technical support. "+str(e)+' -- '+str(sys.exc_traceback.tb_lineno))
	#end sync2cloud
	#######################################################
  	#get any new events that happened since the last update (e.g. new tags, removed tags, etc.)
	#######################################################
	def syncme(self):
		try:
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
			if(self._stopping(evt)):
				return self._stopping(msg=True)
			tags = self._syncTab(user=usr, device=dev, event=evt)
			return tags
		except Exception as e:
			import sys
			return self._err(str(e)+' '+str(sys.exc_traceback.tb_lineno))

	#######################################################
	#return list of teams in the system with team setups
	#######################################################
	def teamsget(self):
		try:
			if(not os.path.exists(self.wwwroot+'_db/pxp_main.db')):
				return self._err("not initialized")
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
					if(team[field] == None):
						team[field] = ""
					result['teams'][team['hid']][field] = team[field]

			# get team setup (players, positions, etc.)
			sql = "SELECT * FROM `teamsetup` ORDER BY `team`, `jersey`"
			db.qstr(sql)
			# get players for each team
			# will be {"team_HID":[{p1},{p2},{p3}]} where pX is {'player':'13','jersey':55,....}
			idx = 0
			for player in db.getasc():
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
			return self._err(str(e)+' '+str(sys.exc_traceback.tb_lineno))
		return result
	#######################################################
	#modify a tag - set as coachpick, bookmark, etc
	#######################################################
	def tagmod(self):
		try:
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

			# make sure event is not being stopped
			if(self._stopping(event)):
				return self._stopping(msg=True)
			#user info, tag id and event name are not modifications - remove those from the dictionary
			del jp['id']
			del jp['user']
			del jp['event']
			# go through all json parameters (tag mod's) and check 
			# which modifications should be applied
			bookmark = False
			# fields that are present in the database (everything else goes in the 'meta')
			dbFields = ('name', 'user', 'starttime', 'type', 'time', 'colour', 'duration', 'comment', 'rating', 'extra')
			if ('bookmark' in jp):
				bookmark = (jp['bookmark']=='1')
				del jp['bookmark']
			meta = {}
			# check if manually closing a duration tag:
			if(('type' in jp) and (int(jp['type'])&1)==0 and int(jp['type'])>0):
				# closing a duration tag
				sqlInsert.append("`duration`=CASE WHEN (?-`time`)>0 THEN (?-`time`) ELSE 0 END")
				params += (jp['time'],jp['time'])
				del jp['time']
				jp['modified']=0 #close duration tags do not have modified status
			else:
				jp['modified']=1
			for mod in jp:
				if (mod=='starttime' and float(jp[mod])<0):#modifying starttime (extending the beginning of the tag)
					value = 0
				if (mod=='delete'):	#when deleting a tag, simply change type to 3
					sqlInsert.append("`type`=?")
					params +=(3,)
				elif (mod!='requesttime'):#any other modifications, just add them to the sql query
					#flag to check if this is a bookmark ("my clip")
					if(not mod in dbFields):
						meta[mod]=jp[mod]
					else:
						sqlInsert.append("`"+mod+"`=?")
						if(type(jp[mod]) is dict):
							params +=(json.dumps(jp[mod]),)
						else:
							params +=(jp[mod],)
			#end for mod in jp
			
			#make sure the database exists and user is not trying to get at other folders
			if(('/' in event) or ('\\' in event) or (not os.path.exists(self.wwwroot+event+'/pxp.db'))):
				return self._err()
			db = self.dbsqlite(self.wwwroot+event+'/pxp.db')

			# add metadata params
			# select existing metadata params
			sql = "SELECT `meta` FROM `tags` WHERE id=?"
			db.query(sql,(tid,))
			tag = db.getasc()
			if(len(tag)<1):
				return self._err("tag "+str(tid)+" does not exist")
			metaOld = json.loads(tag[0]['meta'])
			# add all the old meta fields that were not changed to the meta field
			for field in metaOld:
				if(not field in meta):
					meta[field]=metaOld[field]
			# add the metadata field
			sqlInsert.append("`meta`=?")
			params += (json.dumps(meta),)
			if len(sqlInsert)<1:#nothing was specified 
				return self._err()
			if(bookmark and not self.checkspace()):
				return self._err("Not enough free space. Delete some of the old events from the encoder.")
			# parameters to add to the sql - tag id (no need to check user at the moment)
			params += (tid,)
			#update the tag
			sql = "UPDATE `tags` SET "+(', '.join(sqlInsert))+" WHERE id=?"
			if(not bookmark):#do not mark as bookmark in the database - only give the user the ability to download it, no need for everyone else to get this file				
				#update the tag info in the database
				success = db.query(sql,params)
				if success:
					#add an entry to the event log that tag was updated or deleted
					success = self._logSql(ltype='mod_tags',lid=tid,uid=user,db=db)
			else:
				success = True
			if success:
				db.close() #close db here because next statement will return
				if (bookmark):
					# user wants to make a bookmark - extract the video
					success = success and self._extractclip(tagid=tid,event=event)				
				return self._tagFormat(event=event, user=user, tagID=tid, sockSend=True)
			db.close()
			return {'success':success}
		except Exception as e:
			import sys
			return self._err(str(sys.exc_traceback.tb_lineno)+' '+str(e))
	#end tagmod




















	#######################################################
	#creates a new tag
	#information that needs to be submitted in json form:
	# {
	# 	'event':'<event>',
	# 	'name':'<tag name>',
	# 	'user':'user_hid',
	# 	'tagtime':'<time of the tag in seconds>',
	# 	'colour':'<tag colour>',
	# 	'period':'<period number>',
	# 	['coachpick':'<0/1>'],
	# 	['type':'<0/1...>'], 
	#	['bookmark':'<0/1>'],
	# 	[<other options may be added>]
	# }
	#tag types:
	#NOTE: odd-numbered tag types do not get thumbnails!!

	#default			= 0

	#deleted			= 3 - this one shouldn't happen on tagSet
	#telestration 		= 4

	#start o-line     	= 1 - hockey
	#stop o-line     	= 2 - hockey
	#start d-line		= 5 - hockey
	#stop  d-line		= 6 - hockey	
	#period start		= 7 - hockey
	#period	stop		= 8 - hockey
	#strength start 	= 9- hockey
	#strength stop 		= 10- hockey
	#opp. o-line start 	= 11- hockey
	#opp. o-line stop 	= 12- hockey
	#opp. d-line start 	= 13- hockey
	#opp. d-line stop 	= 14- hockey

	#zone start 		= 15- soccer
	#zone stop 			= 16- soccer
	#half start 		= 17- soccer
	#half stop 			= 18- soccer

	#down start 		= 19- football
	#down stop 			= 20- football
	#quarter start 		= 21- football
	#quarter stop 		= 22- football

	#event can be a folder name of an event or 'live' for live event

	#tagStr - json string with tag info
	#sendSock - send the tag to socket
	#######################################################
	def tagset(self, tagStr=False, sendSock=True):
		import math
		import json, os, sys
		config = self.settingsGet()

		if (not tagStr):
			tagStr = self.uri().segment(3)
		#just making sure the tag was supplied
		if(not tagStr):
			return self._err("Tag string not specified")
		sql = ""
		db = self.dbsqlite()
		try:
			# pre-roll - how long before the tag time to start playing back a clip
			tagVidBegin = int(config['tags']['preroll'])
			# duration is preroll+postroll
			tagVidDuration = int(config['tags']['postroll'])+tagVidBegin
			# convert the json string to dictionary
			t = json.loads(tagStr)
			# t might be an array of dictionaires (size 1) or a dictionary itself
			if (len(t)>0 and (not 'name' in t)):
				t = t[0] # this is an array of dictionaries - get the first element
			# make sure event is valid
			eventName = t['event']
			userhid = t['user']
			if (not 'event' in t or '/' in eventName or '\\' in eventName):
				return self._err("Specify event") #event was not defined or is invalid - can't open the database
			del t['event']
			if('requesttime' in t):
				del t['requesttime'] #this is just to make sure http request does not get cashed
			# make sure event is not being stopped
			if(self._stopping(eventName)):
				return self._stopping(msg=True)
			if (not os.path.exists(self.wwwroot+eventName+'/pxp.db')):
				# this is the first tag in the event 
				self.disk().mkdir(self.wwwroot+eventName)
				# copy the template db for tags
				self.disk().copy(self.wwwroot+'_db/event_template.db', self.wwwroot+eventName+'/pxp.db')
			if(not 'type' in t):
				t['type'] = 0 #if type is not defined set it to default
			else:
				t['type'] = int(t['type'])
			tagType = t['type']
			if(tagType==3):
				return self.err("Attempting to create deleted tag")
			# remove any temporary id that might be associated with the tag
			if ('id' in t):
				del t['id']
			success = 1
  			db.open(self.wwwroot+eventName+'/pxp.db')
			db.transBegin() #in case we need to roll it back later
			if(math.isnan(float(t['time']))):
				t['time'] = 0
			#a new tag was received - add it
			
			if(tagType==99):
				# type 99 is a duration tag - these ones auto-close only if from the same tablet, otherwise just create a new one
				# get device id
				if (not 'deviceid' in t): #old app builds don't have the deviceid - 'fake it' by using the user id instead, this will only work if different users are signed in on different ipads
					t['deviceid']=userhid
				devID = t['deviceid']
				# find last duration tag sent from this tablet 
				sql = "SELECT * FROM `tags` WHERE `type`=? AND `meta` LIKE ?"
				db.query(sql,(tagType,'%"deviceid": "'+devID+'"%'))
				prevTags = db.getasc()
				# auto-close previously opened duration tag from this tablet
				if(len(prevTags)>0):
					sql = "UPDATE `tags` SET `starttime`=`time`, `duration`=CASE WHEN (?-`time`)>0 THEN (?-`time`) ELSE 0 END, `type`=`type`+1 WHERE `type`=?  AND `meta` LIKE ?"
					success = success and db.query(sql,(t['time'],t['time'],tagType,'%"deviceid": "'+devID+'"%'))
					success = success and self._logSql(ltype="mod_tags",lid=prevTags[-1]['id'],uid=t['user'],db=db)
					# send the closed tag to socket
					self._tagFormat(event=eventName, user=userhid, tagID=prevTags[-1]['id'], db=db, checkImg=False, sockSend=True)
				# default duration for the 'start' tag is zero - it will be set when next one is laid
				t['duration']= 0				
				# regardless of preroll time, duration tags must start when the tag is laid
				t['starttime'] = t['time']
			elif(tagType&1): #odd types are tag 'start'
				# check where user is adding the start tag:
				# if it's after the last 'start' tag of the same type, simply add it and close the previous tag
				# if it's somewhere in the middle, this tag type will be automatically closed and the tag duration set
				# get all the tags of the same type that start before the current one
				sql = "SELECT * FROM `tags` WHERE (`starttime`<?) and ((`type`=?) or (`type`=?+1)) ORDER BY `starttime`"
				db.query(sql,(t['time'],tagType,tagType))
				prevTags = db.getasc()

				startTime = float(t['time'])
				if(len(prevTags)>0):
					# there are tags of the same type before this one
					# see if the last tag is odd type
					if(int(prevTags[-1]['type']) & 1):
						# last tag was odd type - just close that tag and start a new one
						# this only happens when there are no other tags of the same type after this one
						# simply update the duration and the type of the start tag
						# also set the starttime to begin when user tagged it, not at the usual -10 seconds
						# update a tag (duration will be current time minus start time). if duration is negative (user seeked back and hit tag) it will be set to zero
						sql = "UPDATE `tags` SET `starttime`=`time`, `duration`=CASE WHEN (?-`time`)>0 THEN (?-`time`) ELSE 0 END, `type`=`type`+1 WHERE `type`=?"
						success = success and db.query(sql,(t['time'],t['time'],tagType))
						success = success and self._logSql(ltype="mod_tags",lid=prevTags[-1]['id'],uid=t['user'],db=db)
						# self._sockTag(event=eventName,tag=tagOut,gameEvents=gameEvents)
						# send the closed tag to socket
						self._tagFormat(event=eventName, user=userhid, tagID=prevTags[-1]['id'], db=db, checkImg=False, sockSend=True)

						# default duration for the 'start' tag is zero - it will be set when next one is laid
						t['duration']= 0
					else:
						# the last tag of this type was even
						# must be adding in the middle of the event somewhere, 
						# update the duration of the last tag
						sql = "UPDATE `tags` SET `duration`=CASE WHEN (?-`time`)>0 THEN (?-`time`) ELSE 0 END WHERE `id`=?"
						success = success and db.query(sql,(t['time'],t['time'],prevTags[-1]['id']))
						success = success and self._logSql(ltype="mod_tags",lid=prevTags[-1]['id'],uid=t['user'],db=db)
						# select the next tag that would follow the inserted one
						sql ="SELECT * FROM `tags` WHERE (`starttime`>=?) AND ((`type`=?) OR (`type`=?+1)) ORDER BY `starttime`"
						db.query(sql,(startTime,tagType,tagType))
						nextTag = db.getasc()
						if(len(nextTag)>0):
							# set the proper duration of the inserted tag (to be between now and the next tag)
							t['duration']=nextTag[0]['time']-startTime
							# set the new tag as even type (close it automatically)
							tagType=tagType+1
						else: #this case would only happen if there was some sort of messup with the database
							t['duration']=0
				else:#there are no tags of the same type before this one
				# either this is the first of its kind or the first tag starts after
					# check if there are any tags after the new one
					# select the next tag that would follow the inserted one (if there are any)
					sql ="SELECT * FROM `tags` WHERE (`starttime`>=?) AND ((`type`=?) OR (`type`=?+1)) ORDER BY `starttime`"
					db.query(sql,(startTime,tagType,tagType))
					nextTag = db.getasc()
					if(len(nextTag)>0):
						# there are tags of this type after - update duration of the current one
						t['duration']=nextTag[0]['time']-startTime
						# and close it automatically
						tagType=tagType+1
					elif(eventName!='live'):
						#this is the first time the tag of this type is being sent
						# and this is not a live event
						# so, close the tag since we know the duration of the video
						pass
				# regardless of preroll time, 'start' tags must start when the tag is laid
				t['starttime'] = t['time']
				# make sure there is no old tag within 2 seconds of the current one
			#end if type is odd
			else: #for normal (event tags) the startTime will be tag time minus the pre-roll
				t['starttime'] = float(t['time'])-tagVidBegin
				if ((not 'duration' in t) or (int(t['duration'])<1)):
					t['duration']=tagVidDuration
			#end if type is odd ... else

			#make sure starttime is not below 0
			if (t['starttime'] < 0):
				t['starttime'] = 0
			# database fields that should all be set
			tagFields = ('name', 'user', 'starttime', 'type', 'time', 'colour', 'duration', 'comment', 'rating')
			#add the tag to the database
			# set standard tag fields (that are fields in the database)
			sqlVars = ()
			for field in tagFields:
				if(not field in t):
					t[field]=""
				sqlVars += (t[field],) #each field should be added as a tuple
				del t[field] #remove the field so it doesn't get added to the extras
			# add all the other fields as json dictionary to the meta field
			meta = {}
			# the rest of the fields can be dumped as json into meta field
			sqlVars += (json.dumps(t),)
			# create a query to add the new tag
			sql = "INSERT INTO tags(name, user, starttime, type, time, colour, duration, comment, rating, meta) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"
			#run it
			success = success and db.query(sql,sqlVars)
			#get the id of the newly created tag
			lastID = db.lastID()
			newTagID = lastID

			if(not success):#something went wrong, roll back the sql statement
				db.rollback()
				return self._err()

			# get all the details about the tag that was created (or last line/period/etc. if a new line/period was started)
			db.commit()
			# #get the time of the current tag
			# tagTime = t['time']
			tagOut = False

			#create a thumbnail for the tag video - only do this when a tag is created
			#i.e. tagStart is not technically a "tag" - wait till the Stop is set, then make a thumbnail
			#this only happens when it's a first 'start' tag - since every other 'start' tag will 
			#automatically stop the previous start 'tag'

			# get the tag information
			tagOut = self._tagFormat(event=eventName, user=userhid, tagID=lastID, db=db, checkImg=False)
			if 'success' in tagOut:
				if not tagOut['success']:
					return tagOut
			tagtime = tagOut['time']
			# a = int(tagOut)
			tagOut['newTagID']=newTagID
			#create a tag image if it doesn't exist already
			pathToEvent = self.wwwroot+eventName+'/'
			imgFile = pathToEvent+"thumbs/tn"+str(lastID)+".jpg"
			if(not os.path.exists(imgFile)):
				if(eventName=='live'):
					# for live events the thumbnail must be extracted from a .TS file
					# get the name of the .ts segment containing the right time				
					res = {}
					vidSegmfileName = self._thumbName(tagtime,event=eventName,results=res)
					vidFile = pathToEvent+"video/"+str(vidSegmfileName)
					# self._thumbName(t['time'],number=True)
					# roundedSec = int(self._thumbName(t['time'],number=True,event=eventName))
					#get the accurate time within the .ts file 
					#TODO: should be more accurate but for some reason ffmpeg only grabs first frame ??
					# sec = (t['time']/0.984315-roundedSec)*0.984315 
					# if sec<0: #sanity check - should never happen
					# do it at 0 for now, we'll figure out how to increase accuracy later on 
					sec = 0 #res['remainder']
				else:
					# for past events, the thumbnail can be extracted from the main.mp4
					vidFile = pathToEvent+"video/main.mp4"
					sec = tagtime
				if(tagOut['type']==4):
					# telestrations require full size image as well as a thumbnail
					fullimgFile = pathToEvent+"thumbs/tf"+str(lastID)+".jpg"
					self._mkThumb(vidFile, fullimgFile, sec, width=0)
				self._mkThumb(vidFile, imgFile, sec) 
			#log that a tag was created
			success = success and self._logSql(ltype="mod_tags",lid=lastID,uid=userhid,db=db)
			# add to the events array to send to the socket updater
			gameEvents = [{}]
			if(tagType & 1):
				# delete last current_<type> entry
				sql = "DELETE FROM `logs` WHERE `type` LIKE ?"
				db.query(sql,('current_'+str(tagType),))
				gameEvents = [{'id':tagOut['name'], 'type':'current_'+str(tagType)}]
				# self._x('current'+str('tagType'))
				success = success and self._logSql(ltype="current_"+str(tagType),lid=tagOut['name'],uid=userhid,db=db)
				# success = success and self._logSql(ltype="current_"+str(tagType),lid=lastID,uid=userhid,db=db)
			db.close()
			#if lastID
			if not 'id' in tagOut: #tag will not be returned - happens when line/zone/etc. is tagged for the first time
				tagOut["success"]=success
			tagOut['islive']=eventName=='live'
			if(sendSock):
				self._sockTag(event=eventName,tag=tagOut,gameEvents=gameEvents)
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
			tagStr = str(io.get("tag"))
			event = json.loads(tagStr)['event']
			if(self._stopping(event)):
				return self._stopping(msg=True)
			# create a tag first
			t = self.tagset(tagStr=tagStr,sendSock=False)
			if('success' in t and not t['success']):
				return t
			#upload a file with the tag name
			imgID = str(t['id'])
			io.upload(self.wwwroot+event+"/thumbs/tl"+imgID+".png")
			# update the thumbnail with the telestration overlay
			# thumbnail image as background for telestration thumbnail
			bgFile = self.wwwroot + event+"/thumbs/tn"+imgID+".jpg"
			# full image background as bg for telestration screenshot
			bfFile = self.wwwroot + event+"/thumbs/tf"+imgID+".jpg"
			# overlay is the png telestration
			olFile = self.wwwroot + event+"/thumbs/tl"+imgID+".png"			
			# open the image files
			bf = Image.open(bfFile) #full background
			bg = Image.open(bgFile) #thumbnail background
			ol = Image.open(olFile) #overlay - telestration

			bf = bf.convert("RGBA")
			ol = ol.convert("RGBA")
			bg = bg.convert("RGBA")

			# get the size of telestration
			(telew,teleh) = ol.size
			# resize full video to match telestration size
			bf.resize((telew,teleh),Image.ANTIALIAS)
			bf.paste(ol, (0, 0), ol)
			# save full size telestration
			bf.save(bfFile,quality=100)

			# get the size of the thumbnail
			(wd,hg) = bg.size
			# resize the overlay to match thumbnail
			ol = ol.resize((wd, hg), Image.ANTIALIAS)
			# overlay the tags
			# ol = ol.convert("RGBA")
			bg.paste(ol, (0, 0), ol)
			bg.save(bgFile,quality=100)
			self._sockTag(event=event,tag=t)
			return t #already contains telestration url
		except Exception as e:
			return self._err("No tag info specified (error: "+str(sys.exc_traceback.tb_lineno)+' - '+str(e))
	#end teleset
	# update server script
	def upgrader(self):
		currentVersion = self.version
		# get the update for the current version
		# os.system("curl -#Lo "+self.wwwroot+"_db/update.tar.gz http://myplayxplay.net/.assets/min/update"+currentVersion+".tar.gz")
		# os.system('tar -xf '+self.wwwroot+'_db/update.tar.gz')
		# os.system("")
		# run each update file
	#end updateEnc
	def version(self):
		return {"version":self.ver}
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
	# returns true if there is a delete process happening (will need to figure out later how to check what exactly is being deleted)
	def _deleting(self):
		return self.disk().psOn("rm -rf") or self.disk().psOn("-exec rm {}")
	def _diskStat(self, humanReadable=True):
		import os
		st = os.statvfs("/")
		diskFree = st.f_bavail * st.f_frsize
		diskTotal = st.f_blocks * st.f_frsize
		diskUsed = diskTotal-diskFree
		diskPrct = int(diskUsed*100/diskTotal)
		if(humanReadable):
	 		return {"total":self._sizeFmt(diskTotal),"free":self._sizeFmt(diskFree),"used":self._sizeFmt(diskUsed),"percent":str(diskPrct)}
	 	return {"total":diskTotal,"free":diskFree,"used":diskUsed,"percent":str(diskPrct)}
	#######################################################
	#returns encoder state (0 - off, 1 - live, 2 - paused)
	#######################################################
	def _encState(self):
		# using file as means to transfer status works better than sockets as there are no timeouts with these
		return int(self.disk().file_get_contents("/tmp/pxpstreamstatus")) #int(self.disk().sockRead(udpPort=2224,timeout=0.5))
	#end encState
	def _err(self, msgText=""):
		return {"success":False,"msg":msgText,"action":"popup"}
	#######################################################
	# extract number from a string (returns 0 if no numbers found)
	#######################################################
	def _exNum(self, text, floatPoint=False):
		import re
		try:
			# regular expression to match digits
			if floatPoint:
				return float(re.search('[0-9\.]+', text).group())
			return int(re.search('[0-9]+', text).group())
		except:
			return 0
	#end exNum
	#######################################################
	# extract text from a string before any number
	# returns blank string if only numbers are present
	#######################################################
	def _exStr(self,text):
		import re
		try:
			# regular expression to search string for anything but digits
			return re.search('[^0-9]+', text).group()
		except:
			return ""
	#end exStr
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
		try:
			if('/' in event or '\\' in event):
				return self._err("invalid event")
			db = self.dbsqlite(self.wwwroot+event+'/pxp.db')
			# get the time from the database
			sql = "SELECT starttime, duration FROM tags WHERE id=?"
			db.query(sql,(tagid,))
			row = db.getrow()
			db.close()
			event = event.replace(' ','\ ').replace('\'','\\\'')
			# start time of the clip
			startTime = float(row[0])
			# duration of the clip (needed for extraction from .MP4)
			duration = float(row[1])

			bigTsFile = self.wwwroot+event+"/video/vid"+str(tagid)+".ts" #temporary .ts output file containing all .ts segments 
			bigMP4File = self.wwwroot+event+"/video/vid_"+str(tagid)+".mp4" #converted mp4 file (low res)
			tempTs = self.wwwroot+event+"/video/int_"+str(tagid)+".ts"#TS file containing resized video clip
			mainMP4File = self.wwwroot+event+"/video/main.mp4"
			# re-create existing bookmarks 
			# if (os.path.exists(bigMP4File)):
			# 	return True # no need to re-create bookmarks that already exist

			if(event=='live'):
				# end time of the clip (needed for extraction from .TS fragments)
				endTime   = startTime+duration
				strFile = self._thumbName(startTime,number=True,event=event) #index of the starting .ts file
				endFile = self._thumbName(endTime,number=True,event=event) #index of the ending .ts file
				# only way to extract video for live events is to concatenate .ts segments
				vidFiles = "" #small .ts files to concatenate
				#select .ts files that should be merged
				for i in range(int(strFile),int(endFile)):
					vidFiles = vidFiles+self.wwwroot+event+"/video/segm"+str(i)+".ts "
				# concatenate the videos
				cmd = "/bin/cat "+vidFiles+">"+bigTsFile
				os.system(cmd)
			else:
				# for past events, the mp4 file is ready for processing, extract clip from it
				cmd = "/usr/local/bin/ffmpeg -ss "+str(startTime)+" -t "+str(duration)+" -i "+mainMP4File+" -b:v 10000k -f mpegts "+bigTsFile
				os.system(cmd)
			# self._x(cmd)
			# convert to mp4, resizing it
			#using ffmpeg
			# cmd = "/usr/local/bin/ffmpeg -f mpegts -i "+bigTsFile +" -y -strict experimental -vf scale=iw/2:-1 -f mp4 "+bigMP4File
			#using handbrake
			#compression ratio here determines quality (lower number=higher quality)
			config = self.disk().iniGet(self.wwwroot+"_db/.pxpcfg")
			quality = 0
			if('clips' in config):
				if('quality' in config['clips']):
					try:
						quality = int(config['clips']['quality'])
					except:
						# in case user messed up the config
						quality = 8
			if(quality<1):
				# if the config file doesn't exist, set default quality
				quality=8
			if(quality<6):
				# for very high quality add more keyframes
				extraframes = "--encoder x264 -x keyint=40"
			else:
				extraframes = ""
			cmd = "/usr/bin/handbrake -q "+str(quality)+" -X 720 --keep-display-aspect "+extraframes+" -i "+bigTsFile+" -o "+bigMP4File+" >/dev/null"
			os.system(cmd)
			#remove the temporary ts file
			os.remove(bigTsFile)

			#FIGURE OUT HOW TO COMPRESS VIDEOS WITH ADS
			# randomy select an ad to add to the video
			# this list contains all the ads videos in the directory
			adFiles = glob.glob(self.wwwroot+"/ads/*.ts")
			if(len(adFiles)<1):#there are no ad videos to choose from - just return after creating the video mp4 file
				return True

			adFile = adFiles[randrange(0,len(adFiles))] #TS file containing small size ad video (random ad)
			#convert small mp4 back to .ts for merging with an ad
			cmd = "/usr/local/bin/ffmpeg -i "+bigMP4File+" -b:v 8000k -f mpegts "+tempTs #use high bitrate to ensure high ad quality
			os.system(cmd)
			# remove the mp4
			os.remove(bigMP4File)
			# merge the ad and the video file
			cmd = "/bin/cat "+adFile+" "+tempTs+" >"+bigTsFile
			os.system(cmd)
			# remove temporary ts:
			os.remove(tempTs)
			# convert the result to an mp4 file again:
			cmd = "/usr/bin/handbrake -q 1 -i "+bigTsFile+" -o "+bigMP4File
			os.system(cmd)
			# remove the temporary ts file
			os.remove(bigTsFile)
			return True
		except Exception as e:
			import sys
			return self._err(str(sys.exc_traceback.tb_lineno)+' '+str(e))
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
		from uuid import getnode as mymac
		import subprocess
		# make sure the credentials were supplied
		url = "http://www.myplayxplay.net/max/activate/ajax"
		# this only works on a mac!
		try:
			proc = subprocess.Popen('ioreg -l | grep IOPlatformSerialNumber',shell=True,stdout=subprocess.PIPE)
			serialNum = ""
			# the output will be similar to:
			#     |   "IOPlatformSerialNumber" = "C07JKA31DWYL"
			for line in iter(proc.stdout.readline,""):
				if(line.find("\"")):
					lineParts = line.split("\"")
					if(len(lineParts)>3):
						serialNum +=lineParts[3]
		except Exception as e:
			serialNum = "n/a"
		params = {
			'v0':self.enc().sha('encoder'),
			'v1':self.enc().sha(email),
			'v2':self._hash(password),
			'v3':platform.uname()[1],
			'v4':str(hex(mymac()))[2:]+' - '+serialNum
		}
		resp = self.io().send(url, params, jsn=True)
		if(resp):
			if(resp['success']):
				#create all the necessary directories
				self.disk().mkdir(self.wwwroot+"_db")
				#save the config info
				self._cfgSet(self.wwwroot+"_db/",[resp['authorization'],resp['customer']])
				#download encoder control scripts
				# os.system("curl -#Lo "+self.wwwroot+"_db/encpause http://myplayxplay.net/.assets/min/encpause")
				# os.system("curl -#Lo "+self.wwwroot+"_db/encstart http://myplayxplay.net/.assets/min/encstart")
				# os.system("curl -#Lo "+self.wwwroot+"_db/encstop http://myplayxplay.net/.assets/min/encstop")
				# os.system("curl -#Lo "+self.wwwroot+"_db/encresume http://myplayxplay.net/.assets/min/encresume")
				os.system("curl -#Lo "+self.wwwroot+"_db/idevcopy http://myplayxplay.net/.assets/min/idevcopy")
				#add execution privileges for the scripts
				os.system("chmod +x "+self.wwwroot+"_db/*")
				#download the blank database files
				os.system("curl -#Lo "+self.wwwroot+"_db/event_template.db http://myplayxplay.net/.assets/min/event_template.db")
				os.system("curl -#Lo "+self.wwwroot+"_db/pxp_main.db http://myplayxplay.net/.assets/min/pxp_main.db")
				os.system("curl -#Lo "+self.wwwroot+"_db/pxpservice.sh http://myplayxplay.net/.assets/min/pxpservice.sh")
				os.system("curl -#Lo "+self.wwwroot+"_db/spacecheck.sh http://myplayxplay.net/.assets/min/spacecheck.sh")
				#download the config file
				os.system("curl -#Lo "+self.wwwroot+"_db/.pxpcfg http://myplayxplay.net/.assets/min/pxpcfg")
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
		if(os.path.exists(self.wwwroot+"live/pxp.db")):
			os.system("rm -f "+self.wwwroot+"live/pxp.db")
		if(self._stopping()):
			os.system("rm -f "+self.wwwroot+"live/stopping.txt")
		self.disk().copy(self.wwwroot+'_db/event_template.db', self.wwwroot+'live/pxp.db')
	#end initLive
	#######################################################
	# returns a list of events in the system
	# showDeleted - determines if the list should contain 
	# deleted events
	# onlyDeleted - will only return deleted events when set
	# onlyDeleted supercedes showDeleted
	#######################################################
	def _listEvents(self, showDeleted=True, onlyDeleted=False):
		try:
			# 
			query = "" if showDeleted else ' AND events.deleted=0' 
			query = ' AND events.deleted=1' if onlyDeleted else query

			sql = "SELECT IFNULL(events.homeTeam,'---') AS `homeTeam`, \
						  IFNULL(events.visitTeam,'---') AS `visitTeam`, \
						  IFNULL(events.league,'---') AS `league`, \
						  IFNULL(events.date,'2000-01-01') AS `date`, \
						  IFNULL(events.hid,'000') AS `hid`, \
						  strftime('%Y-%m-%d_%H-%M-%S',events.date) AS `dateFmt`, \
						  leagues.sport AS `sport`, events.datapath, \
						  events.deleted AS `deleted` \
					FROM `events` \
					LEFT JOIN `leagues` ON events.league=leagues.name \
					WHERE strftime('%s',events.date)<= strftime('%s','now')" + query + "\
					ORDER BY events.date DESC"
			if(not os.path.exists(self.wwwroot+"_db/pxp_main.db")):
				return []
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
			for row in result:
				# event name
				evtName = str(row['datapath'])
				evtDir = self.wwwroot+evtName
				result[i]['name']=evtName
				# check if there is a streaming file (playlist) exists
				if(os.path.exists(evtDir+'/video/list.m3u8') and ('HTTP_HOST' in os.environ)):
					result[i]['vid']='http://'+os.environ['HTTP_HOST']+'/events/'+evtName+'/video/list.m3u8'
				# check if the mp4 file exists
				if(os.path.exists(evtDir+'/video/main.mp4') and (evtName != live)):
					# it is - provide a path to it
					if ('HTTP_HOST' in os.environ):
						# result[i]['vid']='http://'+os.environ['HTTP_HOST']+'/events/'+evtName+'/video/main.mp4'
						result[i]['mp4']='http://'+os.environ['HTTP_HOST']+'/events/'+evtName+'/video/main.mp4'
					if(os.path.exists(evtDir+'/video/list.m3u8')):
						# video size is actually double (1 for streaming + 1 for mp4 file) - times by 2 (shift left by 1 is the same as multiplying by 2)
						shiftBy=1
					else:
						# if there are no .ts files, the file size is just the mp4
						shiftBy=0
					result[i]['vid_size']=self._sizeFmt((os.stat(evtDir+"/video/main.mp4").st_size)<<shiftBy)
				# check if this is a live event
				if((evtName==live) and ('HTTP_HOST' in os.environ)):
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
			return []
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
			return []
		db = self.dbsqlite(self.wwwroot+"_db/pxp_main.db")
		db.qstr(sql)
		result = db.getasc()
		db.close()
		return result
	#end listTeams
	def _log(self,string):
		print(string)
		os.system("echo '"+string+"' >>"+self.wwwroot+"convert.txt")
	#######################################################
	#logs an entry in the sqlite database
	# ltype = log type
	# lid   = log id (e.g. device id, tag id, etc.)
	# uid   = user id
	# dbfile= db file to open. if this is not specified, then DB must be specified
	# db    = database resoucre (opened databse)
	# ms    = milliseconds - used for timestamping the log entry, if omitted, current time is used
	#######################################################
	def _logSql(self, ltype,lid=0,uid=0,dbfile="",db=False,ms=False):
		import os
		try:
			if db:
				autoclose = False
			else:
				autoclose = True
				if(not os.path.exists(dbfile)):
					return False
				db = self.dbsqlite(dbfile)
			if (not ms):
				import time
				ms = int(round(time.time() * 1000))
			#logging an event - delete the last identical event (e.g tag_mod for specific tag id by the same user)
			sql = "DELETE FROM `logs` WHERE (`type` LIKE ?) AND (`user` LIKE ?) AND (`id` LIKE ?)"
			db.query(sql,(ltype,uid,lid))
			#add it again
			sql = "INSERT INTO `logs`(`type`,`id`,`user`,`when`) VALUES(?,?,?,?)";
			success = db.query(sql,(ltype,lid,uid,ms))
			if(autoclose):
				# db was opened in this function - close it
				db.close()
			return success
		except Exception as e:
			return False
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
		# only scale if the width is not 0
		if(width<=0):
			vidscale = ""
		else:
			vidscale = " -vf scale="+str(width)+":ih*"+str(width)+"/iw "
		ffparams = str(seconds)+"  -i "+videoFile.replace(' ','\ ').replace('\'','\\\'')+" -vcodec mjpeg -vframes 1 -an "+vidscale+outputFile.replace(' ','\ ').replace('\'','\\\'')
		#automatically calculates height based on defined width:
		if(videoFile[-3:]=='.ts'):#exctracting frame from a stream .ts file
			# -itsoffset is slower than -ss but it allows exact seeking (past keyframes) and speed is insignificant for small files
			params = " -itsoffset -"+ffparams
		else:
			params = " -ss "+ffparams
		os.system(cmd+params) # need to wait for response otherwise the tablet will try to download image file that does not exist yet
	#end mkThumb
	#######################################################
	#sets ports in /tmp/pxpports file
	#######################################################
	def _portSet(self, hls=2222, ffm=2223, chk=2224):
		self.disk().file_set_contents("/tmp/pxpports","HLS="+str(hls)+"\nFFM="+str(ffm)+"\nCHK="+str(chk))
	#end portSet
	#returns true if all ports are set to 65535 (all ports are set to 65535 when video is 'paused')
	def _portSame(self, portCheckValue=65535):
		equalports = True
		portLines = (self.disk().file_get_contents("/tmp/pxpports"))
		if not portLines:
			return False
		portLines = portLines.split("\n")
		for line in portLines:
			parts = line.split("=")
			if len(parts)>1:
				equalports = equalports and parts[1]==str(portCheckValue)
		return equalports
	#end portSame
	#######################################################
	#renames directories
	#######################################################
	def _postProcess(self):
		try:
			# get the name of what the new directory should be called
			event = self.disk().file_get_contents(self.wwwroot+"live/evt.txt").strip()
			#delete the file containing the name of the event (not needed anymore)
			os.remove(self.wwwroot+"live/evt.txt")
			# rename the live to that directory
			os.rename(self.wwwroot+"live",self.wwwroot+event)
			# update mp4 headers to make the mp4 streamable
			# os.system("/usr/local/bin/qtfaststart "+self.wwwroot+event+'/video/main.mp4')
			# remove all .ts files - leave them on the server for streaming past events
			# cmd = "find "+self.wwwroot+event.strip()+"/video/ -name *.ts -print0 | xargs -0 rm"
			# os.system(cmd)
			# remove the stopping.txt file
			os.system("rm "+self.wwwroot+event+"/stopping.txt")
		except Exception as e:
			import sys
			return self._err(str(e)+' '+str(sys.exc_traceback.tb_lineno))
	#end postProcess

	def _sizeFmt(self,size):
		s = float(size)
		#size names
		sizeSuffix = ['b','KB','MB','GB','TB','PB','EB','ZB','YB']
		for x in sizeSuffix:			
			if s < 1024 or x==sizeSuffix[len(sizeSuffix)-1]:
				#either reached the capacity (i.e. size will be under 1024)
				#or reached the end of suffixes (highly unlikely)
				return "%0.2f %s" % (s, x)
			s = s / 1024
		return ""
	# sends tag (or other data) to a pxpservice 
	# tag - sends this tag to the service
	# data - if no tag is specified, sends this raw data
	def _sockTag(self,event="live",tag=False,gameEvents=[{}],data=False,db=False):
		if(tag):
			# self._x(tag)
			# tag was specified - send it to the service
			if(not db):
				# no database specified - open it
				closedb = True
				db = self.dbsqlite(self.wwwroot+event+"/pxp.db")
			else:
				# database was specified - no need to open it (or close it) here
				closedb = False
			# get teams and league HIDs
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
			outJSON = {
				'tags':{tag['id']:tag},
				'status':self.encoderstatus(),
				'events':gameEvents,
				'teams':teamHIDs,
				'league':leagueHID
			}
			# send the tag (with other info) to the socket
			self.disk().sockSend(json.dumps(outJSON))
			if(closedb): #the db was opened here - so it must be closed here as well
				db.close()
		else:
			# tag was not specified - send the raw data
			self.disk().sockSend(data)
	#end sockTag
	# returns true if the event is being stopped
	def _stopping(self, event="live", msg=False):
		import psutil
		if(not msg):
			# return True
			# TODO:TODO:TODO:TODO:TODO:TODO:TODO:TODO:TODO:TODO:TODO:TODO:TODO:TODO:TODO:TODO:TODO:TODO:TODO:TODO:
			# ADD PROVISION, WHEN STOPPING ONE EVENT BUT CREATING BOOKMARKS IN ANOTHER
			# FFMPEG WILL BE ACTIVE, NEED TO TAKE THAT INTO CONSIDERATION:
			# DO ANOTHER ps ax | grep COMMAND AND CHECK 
			# IF THIS FFMPEG ALSO HAS THE 'event/video' AS PART OF ITS PARAMETERS
			if(os.path.exists(self.wwwroot+event+"/stopping.txt")):
				# check if the ffmpeg command is actually using any cpu
				# find the pid's of ffmpeg and handbrake processes
				pids = []
				for proc in psutil.process_iter():
					if (proc.name == 'ffmpeg' or proc.name == 'handbrake'):
						pids.append(proc.pid)
				# find the cpu usage
				processActive = False
				for pid in pids:
					 proc = psutil.Process(pid)
					 processActive = processActive or proc.get_cpu_percent()>=1
				# if the ffmpeg is just hanging out, the event has been stopped, delete the file
				if (not processActive or event!="live"):
					os.remove(self.wwwroot+event+"/stopping.txt")
				return processActive and event=='live'
			#end if not stopping.txt
			return False
		#end if not msg
		return self._err("Event is being stopped")
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
	#syncs encoder to cloud
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
		resp = self.io().send(url,params, jsn=True)
		if(not resp):
			return self._err("connection error")
		if ('success' in resp and not resp['success']):
			return self._err(resp['msg'])
		tables = ['users','leagues','teams','events', 'teamsetup']
		for table in tables:
			if (resp and (not (table in resp)) or (len(resp[table])<1)):
				continue
			sql_del = "DELETE FROM `"+table+"` WHERE"
			del_arr = [] #what will be deleted
			add_arr = [] #contains sql rows that will be inserted
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
				# sql_ins = "INSERT INTO `"+table+"`("
				# sql_vals = "VALUES("
				sql_cols = [] #column names
				sql_vals = [] #values to insert
				#go throuch each field in a row and add it to the query array

				for name in row:
					if(name=='primary' or name=='deleted'):
						continue #this is only a name of a row - not actual data
					sql_cols.append(name)
					sql_vals.append("'"+str(row[name]).replace("'","''")+"'")
				#end for name in row
				add_arr.append("INSERT INTO `"+table+"`("+','.join(sql_cols)+") VALUES ("+','.join(sql_vals)+")")
			#end for row in table
			sql_ins="BEGIN TRANSACTION; \n"+("; \n".join(add_arr))+"; \nCOMMIT;"
			# delete query is fairly standard: DELETE FROM `table` WHERE `field` LIKE 'value' OR `field` LIKE 'another value'
			sql_del += "OR".join(del_arr)

			if(table=='events'): #only delete events that were deleted in the cloud
				db.qstr(sql_del)
			else:#delete all the data from the table (except for events)
				db.qstr("DELETE FROM `"+table+"`")
			db.qstr(sql_ins,multiple=True)
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
	# syncs
	#######################################################
	def _syncEncUp(self,encMail="",encPassw=""):
		pass
	#end syncEncUp
	#######################################################
	#syncs tablet with ecnoder (sends any tag modifications 
	#that were created in a specific event since the last sync)
	#######################################################
	def _syncTab(self, user, device, event, allData=False):
		from collections import OrderedDict
		##get the user's ip
		##userIP = os.environ['REMOTE_ADDR']
		# get the current milliseconds (to make sure the sync event is registered before any other things are logged)
		from time import time
		ms = int(round(time() * 1000))
		if (not user) or len(user)<1 or (not device) or len(device)<1 or (not event) or len(event)<1 or ('/' in event) or ('\\' in event) or (not os.path.exists(self.wwwroot+event+"/pxp.db")):
			return [] #return empty list if user did not provide the correct info or event does not exist
		db = self.dbsqlite(self.wwwroot+event+"/pxp.db")
		try:
			if(allData):#selecting all tags from this game (assumption here - user has no tags yet, so he doesn't need to see deleted tags)
				lastup = 0
				sql = "SELECT * FROM `tags` WHERE NOT `type`=3 ORDER BY `starttime`, `duration`"
				db.qstr(sql)
			else:
				#get the time of the last update
				sql = "SELECT IFNULL(MAX(`when`),0) AS `lastUpdate` FROM `logs` WHERE `id` LIKE ? AND `user` LIKE ? AND `type` LIKE 'sync_tablet' ORDER BY `logID`"
				success = db.query(sql,(device,user))
				lastup = db.getrow()
				lastup = lastup[0]
				#if allData...else
				#get new events that happened since the last update
				#get all tag changes that were made since the last update
				sql = "SELECT DISTINCT(tags.id) AS dtid, tags.* FROM tags LEFT JOIN logs ON logs.id=tags.id WHERE (`logs`.`when`>?) AND (`logs`.`type` LIKE 'mod_tags') ORDER BY tags.starttime, tags.duration "
				# return self._err(sql+' '+str(lastup))
				db.query(sql,(lastup,))
			#put them in a list of dictionaries:
			tags = db.getasc()
			#close the database (for others to access this
			db.close()
			#format tags for output
			tagsOut = OrderedDict()
			for tag in tags:
				#only even type tags are sent (normal, telestration, period/half/zone/line end tags)
				#also deleted tags are sent - to delete them from other tablets
				# if ((int(tag['type'])&1) and (not int(tag['type'])==3)):
				# 	continue
				if(str(tag['time'])=='nan'):
					tag['time']=0
				tagJSON = self._tagFormat(tag=tag,event=event, user=user, db=db)
				# if(allData or not user==tag['user']):
				tagsOut[tag['id']]=(tagJSON)
			#end for tags:
			db = self.dbsqlite(self.wwwroot+event+"/pxp.db")
			#get any other events (other than tags)
			sql = "SELECT `type`, `id` FROM `logs` WHERE `when`>? AND NOT(`type` LIKE 'mod_tags' OR `type` LIKE 'sync%')"
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
			# evts.append({"camera":self.encoderstatus()})
			outJSON = {
				'tags':tagsOut,
				'status':self.encoderstatus(),
				'events':evts,
				'teams':teamHIDs,
				'league':leagueHID
				# 'camera':self.encoderstatus()
			}
			for key in outJSON.keys():
				if len(outJSON[key])<1:
					del(outJSON[key])
			if len(outJSON)>0: #only log sync when something was sync'ed
				self._logSql(ltype='sync_tablet',lid=device,uid=user,dbfile=self.wwwroot+event+'/pxp.db',ms=ms)
			return outJSON
		except Exception as e:
			import sys
			return self._err(str(e)+' '+str(sys.exc_traceback.tb_lineno))
	#end syncTab()
	#######################################################
	# formats the tag in a proper json format and returns it as json dictionary
	# if db is not specified, the default db from the specified 'event' will be opened
	# @event  	: event name
	# @user 	: user id
	# @tagID 	: the ID of the tag that user wants outputted
	# @tag   	: the tag details (tagID is irrelevant in this case)
	# @db 		: if tag is not specified, the db needs to be 
	# @checkImg : when true, the function will create the thumbnail if it does not exist
	# @sockSend : whether to send the data to a socket or not
	#######################################################
	def _tagFormat(self, event=False, user=False, tagID=False, tag=False, db=False, checkImg=True, sockSend=False):
		import os, datetime
		try:
			outDict = {}
			if(tagID): #tag id was given - retreive it from the database
				sql = "SELECT * FROM `tags` WHERE `id`=?"
				if(not db):
					autoclose = True #db was not passed, open and close it in this function
					if('/' in event or '\\' in event):
						return {} #invalid event
					db = self.dbsqlite(self.wwwroot+event+"/pxp.db")
				else:
					autoclose = False #db was passed as argument - do not close it here
				db.query(sql,(tagID,))
				tag = db.getasc()
				if(len(tag)<1): #invalid tag - not found in the database
					return self._err("Tag "+str(tagID)+" does not exist")
				tag = tag[0]
				if(autoclose):
					db.close()
					db = False
			#if no tagID is given, the tag fields must be passed in the tag parameter
			elif(not tag):
				# no tag id or other information given - return empty dictionary
				return {}
			if(event):
				if(event=='live'):
					# live event has the proper event name stored in a text file
					evtname = self.disk().file_get_contents(self.wwwroot+"live/evt.txt")
					if evtname:
						evtname = evtname.strip()
					else: #could not get the name from the text file - this should never happen
						evtname = 'live'
				#if event==live
				else:# event name is just the event passed to the server
					evtname = event
				#end if event live...else
				# open the database and get the info about the event (event name is the datapath)
				tmdb = self.dbsqlite(self.wwwroot+"_db/pxp_main.db")
				sql = "SELECT * FROM `events` WHERE `datapath` LIKE ?"
				tmdb.query(sql,(evtname,))
				evtInfo = tmdb.getasc()
				tmdb.close()
				if(len(evtInfo)>0):
					tag['homeTeam']=evtInfo[0]['homeTeam']
					tag['visitTeam']=evtInfo[0]['visitTeam']
			#end if event

			# some numeric sanity checks before the round function
			if (not tag['duration']):
				tag['duration']=0.01
			if (not tag['time']):
				tag['time']=0.01

			#format some custom fields
			tag['duration']=str(round(float(tag['duration'])))[:-2]
			#time to show on the thumbnail
			tag['displaytime'] = str(datetime.timedelta(seconds=round(float(tag['time']))))
			# thumbnail image url
			tag['url'] = 'http://'+os.environ['HTTP_HOST']+'/events/'+event+'/thumbs/tn'+str(tag['id'])+'.jpg'
			# path to the image file (to check if it exists)
			imgFile = self.wwwroot+event+'/thumbs/tn'+str(tag['id'])+'.jpg'
			# check we need to check whether the thumbnail image exists
			if (checkImg and not os.path.exists(imgFile)):
				# the thumbnail image does not exist, create it
				if(event=='live'):
					# for live events the thumbnail must be extracted from a .TS file
					# get the name of the .ts segment containing the right time				
					res = {}
					vidSegmfileName = self._thumbName(tag['time'],event=event,results=res)
					vidFile = self.wwwroot+event+"/video/"+str(vidSegmfileName)
					sec = res['remainder']
				else:
					# for past events, the thumbnail can be extracted from the main.mp4
					vidFile = self.wwwroot+event+"/video/main.mp4"
					sec = tag['time']
				self._mkThumb(vidFile, imgFile, sec)
			#end if checkImg

			tag['own'] = tag['user']==user #whether this is user's own tag

			if(event=='live' and os.path.exists(self.wwwroot+event+'/evt.txt')):
				tag['event'] = self.disk().file_get_contents(self.wwwroot+event+'/evt.txt').strip()
			else:
				tag['event'] = event
			#set deleted attribute for a tag
			tag['deleted'] = tag['type']==3

			tag['success'] = True #if got here, the tag info was retreived successfully
			if(int(tag['type'])==4): #add telestration url for telestration tags only
				tag['teleurl']='http://'+os.environ['HTTP_HOST']+'/events/'+event+'/thumbs/tl'+str(tag['id'])+'.png'
				tag['telefull']='http://'+os.environ['HTTP_HOST']+'/events/'+event+'/thumbs/tf'+str(tag['id'])+'.jpg'
			if(os.path.exists(self.wwwroot+event+'/video/vid_'+str(tag['id'])+'.mp4')):
				tag['vidurl']='http://'+os.environ['HTTP_HOST']+'/events/'+event+'/video/vid_'+str(tag['id'])+'.mp4'
			if('hid' in tag):
				del(tag['hid'])
			# extract metadata as individual fields
			if ('meta' in tag):
				meta = json.loads(tag['meta'])
				del tag['meta'] #remove the original meta field from the tags
				if('id' in meta): #delete 'id' from meta field - confusing with 'id' from the fields
					del meta['id']
				tag.update(meta) #join 2 dictionaries
			# go through each field in the tag and format it properly
			for field in tag:
				field = field.replace("_"," ") #replace all _ with spaces in the field names
				if(tag[field]== None):
					tag[field] = ''
				else:
					outDict[field]=tag[field]
			# send the data to the socket (broadcast for everyone)
			outDict['islive']=event=='live'
			if(sockSend):
				self._sockTag(event=event,tag=outDict,db=db)
			return outDict
		except Exception as e:
			import sys
			return self._err(str(sys.exc_traceback.tb_lineno)+' '+str(e))
	#end tagFormat
	# returns timestamp formatted as specified
	def _time(self,format='%Y-%m-%d %H:%M:%S',timeStamp=False):
		from time import time as tm
		if (timeStamp):
			return str(int(tm()*1000))
		from datetime import datetime as dt
		return dt.fromtimestamp(tm()).strftime(format)
	#end time
	#######################################################
	#returns file name for the video that contains appropriate time 
	#if totalTime is set to True, returns the length of the event in seconds
	#######################################################
	def _thumbName(self,seekTo=0,number=False,event="live", results={}, totalTime=False):
		import math
		# path to the list.m3u8 file - playlist for the hls
		listPath = self.wwwroot+event+"/video/list.m3u8"
		#open m3u8 file:
		#the time of the current file. e.g. if there are 50 files of 1seconds each then file50.ts will be at roughly 00:00:50 time. reachedTime contains the number of seconds since file0
		reachedTime = 0.0
		# how much time is between the beginning of the HLS segment containing the required time and the required time
		# e.g. segment starts at 953 seconds, lasts 1 second, the tagtime is at 953.73 seconds, the remainder will be 0.73s
		results['remainder']=0
		# number of the HLS segment containing the required time
		results['number']=0
		results['firstSegm']=0
		results['lastSegm']=0
		try:
			f = open(listPath,"r")
			seekTo = float(seekTo) # make sure this is not a string
		except:
			return 0

		#starting from the top, add up the times until reached desired time - that's the file
		#assuming m3u8 file is in this format:
		# #EXTINF:0.98431,
		# fileSequence531.ts
		#and so on - a line with time precedes the line with file name

		fileName = False
		for line in f:
			cleanStr = line.strip()
			if(cleanStr[:7]=='#EXTINF'):#this line contains time information
				reachedTime += float(cleanStr[8:-1]) #get the number (without the trailing comma) - this is the duration of this segment file
			elif(cleanStr[-3:]=='.ts'):#this line contains filename
				if (not results['firstSegm']): #only assign the first segment once
					results['firstSegm']=cleanStr
				#name of the last reached segment
				results['lastSegm']=cleanStr
				# check if desired time was reached (and user is not looking for total time)
				if (seekTo<=reachedTime and (not totalTime)):
					fileName = cleanStr
					results['remainder']=reachedTime-seekTo
					break
		f.close()
		# if user only wants the total time 
		if (totalTime):
			return reachedTime
		if (not fileName):
			return 0
		if(number):#only return the number without the rest of the filename
			results['number']=self._exNum(fileName)
			return results['number']
		return fileName
	#end calcThumb

	#######################################################
	# uploads a file to the server
	# fileToUpload - full path to the file to upload
	# event - event name
	# destination - where to upload the file: 
	# extradata - array of strings that will be added to the url: ...upload/video/eventid/extra/params/here
	# (video) ./event/video, (thumbs) ./event/thumbs or (root) ./event/
	#######################################################
	def _uploadFile(self,fileToUpload,event="live",destination="video",extraData=[]):
		from poster.encode import multipart_encode
		from poster.streaminghttp import register_openers
		import urllib2
		try:
			if (not os.path.exists(fileToUpload)):
				return False
			self.disk().file_set_contents(self.wwwroot+event+"/uploading","1")
			# get the id of the event
			evtHid = self.disk().file_get_contents(self.wwwroot+event+"/eventid.txt")
			# upload the file
			# Register the streaming http handlers with urllib2
			register_openers()
			

			# Start the multipart/form-data encoding of the file "DSC0001.jpg"
			# "image1" is the name of the parameter, which is normally set
			# via the "name" parameter of the HTML <input> tag.

			# headers contains the necessary Content-Type and Content-Length
			# datagen is a generator object that yields the encoded parameters
			datagen, headers = multipart_encode({"qqfile": open(fileToUpload, "rb")})

			# Create the Request object
			urladdr = "http://myplayxplay.net/maxdev/upload/"+destination+"/"+evtHid+"/"+("/".join(extraData))+"?timestamp="+self._time(timeStamp=True)
			request = urllib2.Request(urladdr, datagen, headers)
			# Actually do the request, and get the response
			response = urllib2.urlopen(request).read()
			if(os.path.exists(self.wwwroot+event+"/uploading")):
				os.remove(self.wwwroot+event+"/uploading")
			try:
				# try to return json-formatted response if it was json
				return json.loads(response)
			except:
				# if the response wasn't json, just return it as is
				return response
		except Exception as e:
			if(os.path.exists(self.wwwroot+event+"/uploading")):
				os.remove(self.wwwroot+event+"/uploading")
			return False
	#end uploadFile
	# returns true if there are files being uploaded at the moment
	def _uploading(self,event="live"):
		return os.path.exists(self.wwwroot+event+"/uploading")
	# shortcut for outputting text to the screen
	def _x(self,txt):
		self.str().pout(txt)
	# convert dictionary to xml
	# @param (dict) data: dictionary to parse (or any other object type)
	# @param (int) depth: level within a dictionary (translates to how many tabs to put before the string)
	# @param (str)	 key: dictionary key (required when passing dictionary, ignored otherwise)
	def _xmldict(self,data,key="",depth=0):
		xmlOutput = ""
		try:
			typeName = self._xmltype(data)
			# dictionaries must be parsed recursively
			if(typeName=='dict'):
				# output the key
				xmlOutput+=''.rjust(depth,'\t')+'<key>'+str(key)+'</key>\n'
				# add tag detail
				xmlOutput+=''.rjust(depth,'\t')+'<dict>\n'
				for field in data:
					# get the field type
					xmlOutput += self._xmldict(data[field],field,depth+1)
				#end for field in data
				xmlOutput+=''.rjust(depth,'\t')+'</dict>\n'
			elif(typeName=='array'):
			# for array - just list the entries
				xmlOutput+=''.rjust(depth,'\t')+'<key>'+key+'</key>\n'
				# indicate that this is an array
				xmlOutput+=''.rjust(depth,'\t')+'<array>\n'
				# output all the values of the array
				for val in data:
					xmlOutput+=''.rjust(depth+1,'\t')+'<'+self._xmltype(val)+'>'+str(val).replace('<','&lt;').replace('>','&gt;')+'</'+self._xmltype(val)+'>\n'
					# xmlOutput += self._xmldict(val,"", depth+1)
				xmlOutput+=''.rjust(depth,'\t')+'</array>\n'
			#end if array
			elif(typeName=='boolean'):
				xmlOutput+=''.rjust(depth,'\t')+'<key>'+key+'</key>\n'
				xmlOutput+=''.rjust(depth,'\t')+'<'+str(data).lower()+'/>\n'
			else:
			# regular fields are added as is:
				xmlOutput+=''.rjust(depth,'\t')+'<key>'+key+'</key>\n'
				xmlOutput+=''.rjust(depth,'\t')+'<'+typeName+'>'+str(data).replace('<','&lt;').replace('>','&gt;')+'</'+typeName+'>\n'
		except Exception as e:
			# import sys
			# return self._err(str(sys.exc_traceback.tb_lineno)+' '+str(e))
			pass
		return xmlOutput	
	#end xmldict
	def _xmltype(self,variable):
		varType = type(variable)
		if(varType is int or varType is long):
			return "integer"
		elif(varType is float):
			return "real"
		elif(varType is list):
			return "array"				
		elif(varType is bool):
			return "boolean"
		elif(varType is dict):
			return "dict"
		else:
			return "string"
#end pxp class
