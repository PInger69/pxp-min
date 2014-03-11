import constants as c
import os

#sqlite database management class
import sqlite3
class c_sqdb:
	con = None
	c   = None
	autocommit = True
	def __init__(self, dbpath=False):
		if dbpath:
			self.open(dbpath)
	def close(self):
		self.autocommit = True
		try:
			if self.c:
				self.c.close()
			if self.con:
				self.con.close()
		except:
			#put some error handlers later on
			pass
	#end close()
	def commit(self):
		self.autocommit = True
		if self.con:
			self.con.commit()
	#end commit()
   
	#returns all rows of a query as a dictionary (associative array)
	def getasc(self):
		try:
			if not self.c:
				return []
			rows = []
			#get column names
			cols = []
			for colname in self.c.description:
				cols.append(colname[0])
			#get all rows
			for row in self.getrows():
				entry = {}
				idx = 0
				for colname in cols:				
					entry[colname] = row[idx]
					idx += 1
				rows.append(entry)
		except:
			pass
		return rows
	#end getasc()
   
	#returns one row from the query
	def getrow(self):
		if self.c:
			return self.c.fetchone()
		return ()
	#end getrow()
   
	#returns all the query rows as an array
	def getrows(self):
		if self.c:
			return self.c.fetchall()
		return []
	#end getrows()
   
	#returns ID of the last inserted entry
	def lastID(self):
		if self.c:
			return self.c.lastrowid
		return False
	#end lastID()

	#returns number of rows
	def numrows(self):
		if self.c:
			return self.c.rowcount
		return 0
	#end numrows()
   
	#creates connection to the database
	def open(self, dbpath):
		#open the connection:
		try:
			if self.con:#if a database connection is already open - close it
				self.close()
			#connect to the database
			connectAttempts=0
			success = False
			while(connectAttempts<20 and not success):
				connectAttempts += 1
				try:
					self.con = sqlite3.connect(dbpath,timeout=1)
					self.c = self.con.cursor()
					self.c.execute("select * from sqlite_sequence")
					test = self.c.fetchall()
					success = True
				except Exception as e:
					success = False
			# cur.execute('SELECT SQLITE_VERSION()')
			# data = cur.fetchone()
		except sqlite3.Error, e:
			#put some errors here later
			success = False
			#sys.exit(1)
		return success
	#end open()
	
	#executes an sql query
	def query(self, sql, data, autocommit=True):
		error = False
		try:#to prevent sql errors from interrupting the script
			self.c.execute(sql,data)#run the query
			if autocommit:
				self.con.commit()#commit it - without this no changes will be made to the db
		except ValueError, e:

			error = True
		#success when there was at least 1 row affected
		return (not error) or (self.con.total_changes >= 1) #no need to do (changes>1) AND (not error): if changes >1 then error will be false
	#end query()
   	#executes a query string
	def qstr(self, query, multiple=False):
		error = False
		try:#to prevent sql errors from interrupting the script
			if(multiple):
				self.c.executescript(query)#run the query
			else:
				self.c.execute(query)
			if self.autocommit:
				self.con.commit()#commit it - without this no changes will be made to the db
		except ValueError, e:
			error = True
		#success when there was at least 1 row affected
		return (not error) or (self.con.total_changes >= 1) #no need to do (changes>1) AND (not error): if changes >1 then error will be false
	def rollback(self):
		self.autocommit = True
		if self.con:
			self.con.rollback()
	#end commit()
	#begin transaction - user must commit or rollback manually
	def transBegin(self):
		self.autocommit = False
	#end transBegin
#end c_sqdb
	#disk operations class

#disk utilities class
class c_disk:
	def cfgGet(self, cfgfile=c.pxpConfigFile, section=False, parameter=False):
		import json
		try:#load all the settings
			settings = json.loads(self.file_get_contents(cfgfile))
		except:
			settings = {}
		if(section): #section was specified
			if(section in settings): #make sure it exists
				if(parameter):#parameter within this section was specified
					if(parameter in settings[section]): #parameter exists in this section - return it
						return settings[section][parameter]
					else:#parameter was not found in this section
						return {}
				else:#parameter was not specified, return entire section
					return settings[section]
			else: #specified section does not exist
				return {}
		else: #section was not specified
			return settings #return all the settings
	#end cfgGet
	#assigns a config file (either entire thing or a section, based on input)
	def cfgSet(self, cfgfile=c.pxpConfigFile, section=False, parameter=False, value=False, jsonData=False):
		import json
		try: #load all the settings (to make sure nothing gets overwritten)
			settings = json.loads(self.file_get_contents(cfgfile))
		except:
			#could not load settings - probably error with the file or file doesn't exist
			settings = {}
		if(jsonData): #all of the settings are specified here - just overwrit the file WATCH OUT!!!!!
			self.file_set_contents(cfgfile, json.dumps(jsonData))
		# setting a specific section
		if(not section):
			return #if section was not specified, there's nothing to do
		if(not section in settings):
			# section does not exist yet, add it
			settings[section]={}
		if(parameter):
			# a single parameter within a section was specified
			settings[section][parameter]=value
		else:
			# overwriting the entire section
			settings[section] = value
		# write settings to the file
		self.file_set_contents(cfgfile, json.dumps(settings))
		return True
	#end cfgSet
	def copy(self, src, dst):
		import shutil
		shutil.copy(src,dst)
	#retrieves file contents as a string
	def file_get_contents(self, filename):
		import os
		if(not os.path.exists(filename)):
			return False
		contents = ""
		with open(filename,"rb") as f:
			contents = f.read()
		return contents
	def file_set_contents(self, filename,text):
		f = open(filename,"w")
		f.write(text)
		f.close()	
	# retreives data from a config file in a dictionary format
	# def iniGet(self,cfgfile):
	# 	import ConfigParser, os
	# 	parser = ConfigParser.ConfigParser()
	# 	cfgParams = {}
	# 	if(not os.path.exists(cfgfile)):
	# 		# file does not exist, return empty dictionary
	# 		return cfgParams
	# 	# get all sections
	# 	parser.read(cfgfile)
	# 	# parse sections
	# 	for section in parser.sections():
	# 		options = parser.options(section)
	# 		# each section is a dictionary
	# 		cfgParams[section]={}
	# 		# get list of options in each section
	# 		for option in options:
	# 			try:
	# 				# try to get the value for this parameter
	# 				cfgParams[section][option] = parser.get(section, option)
	# 			except:
	# 				# value was not specified, leave it as blank (not null)
	# 				cfgParams[section][option] = ''
	# 	return cfgParams
	#end iniGet
	# sets a config file parameter, returns true on success, false on failure
	# def iniSet(self,cfgFile,section,param,value):
	# 	import ConfigParser, os
	# 	try:
	# 		# init the parser
	# 		parser = ConfigParser.ConfigParser()
	# 		# check if the config file exist
	# 		fp = None
	# 		if(not os.path.exists(cfgFile)):
	# 			# file does not exist, create it
	# 			fp = open(cfgFile,"w")
	# 		# get the config file info (if any) to make sure any other settings don't get overwritten
	# 		parser.read(cfgFile)
	# 		if (not fp):
	# 			fp = open(cfgFile,"w")
	# 		# make sure the section we're setting exists
	# 		if(not section in parser.sections()):
	# 			# add if it doesn't
	# 			parser.add_section(section)
	# 		# set the value
	# 		parser.set(section,param,value)
	# 		# save the file
	# 		parser.write(fp)
	# 		fp.close()
	# 		return True
	# 	except Exception as e:
	# 		return False
	#end iniSet
	def mkdir(self, dirpath, perm=0777):
		import os
		try:
			os.makedirs(dirpath,perm)
			return True
		except Exception as e:
			return False
	#end mkdir
	#returns true if there is a specified process running
	def psOn(self, process):
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
	#end psOn
	# reads sizeToRead from a specified udp port
	def sockRead(self, udpAddr="127.0.0.1", udpPort=2224, timeout=0.5, sizeToRead=1):
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
	# sends msg to the specified socket
	def sockSend(self, msg, sockHost="127.0.0.1", sockPort=2232,addnewline=True):
		import socket
		sent = 0
		try:
			sock = socket.socket(
				socket.AF_INET, socket.SOCK_STREAM)
			sock.connect((sockHost, sockPort))
			if(addnewline and msg[-2:]!="\r\n"):
				msg+="\r\n"
			sent = sock.send(msg)
			sock.close()
		except Exception as e:
			try:
				sock.close()
			except:
				pass
			return e
		return sent
#end c_disk class

#encryption/string operations class
class c_enc:
	#return sha1 hash of the string
	def sha(self,string):
		import hashlib
		s = hashlib.sha1(string)
		return s.hexdigest()
	#repeats the string up to 'length' characters
	def repeat_str(self, string_to_expand, length):
	   return (string_to_expand * ((length/len(string_to_expand))+1))[:length]
	# performs bitwise exclusive or on 2 strings 
	# must be of equal length, otherwise result will be trimmed to the shortest string
	def sxor(self, s1,s2):
		# convert strings to a list of character pair tuples
		# go through each tuple, converting them to ASCII code (ord)
		# perform exclusive or on the ASCII code
		# then convert the result back to ASCII (chr)
		# merge the resulting array of characters as a string
		return ''.join(chr(c) for c in [ord(a) ^ ord(b) for a,b in zip(s1,s2)])
	#end sxor
#end enc class

#web input/output class
class c_io:
	frm = None
	def __init__(self):
		import cgitb; cgitb.enable()
		import cgi
		if not self.frm:
			self.frm = cgi.FieldStorage()
	def get(self, fieldName):
		return self.frm.getvalue(fieldName)
	#end get
	# checks if there is connection to myplayxplay.net website
	def isweb(self):
		import urllib2
		from time import time as tm				
		try:
			timestamp = str(int(tm()*1000))
			response=urllib2.urlopen('http://myplayxplay.net/?timestamp='+timestamp,timeout=10)
			return True
		except Exception as e: pass
		return False
	def send(self,url,params,jsn=False):
		import httplib, urllib, urlparse, json
		try:
			headers = {"Content-type": "application/x-www-form-urlencoded", "Accept": "text/plain"}
			parsed = urlparse.urlparse(url)
			conn = httplib.HTTPConnection(parsed.netloc)
			conn.request("POST", parsed.path, urllib.urlencode(params),headers)
			r1 = conn.getresponse()
			if(jsn):
				try:
					return json.loads(r1.read())
				except:
					return False
			return r1.read()
		except:
			return False
	#end send
	def upload(self, filePath):
		form = self.frm
		# A nested FieldStorage instance holds the file
		fileitem = form['file']
		# Test if the file was uploaded
		if fileitem.filename:
			# strip leading path from file name to avoid directory traversal attacks
			# fn = os.path.basename(fileitem.filename) # don't need file name
			f = open(filePath, 'wb')
			if not f:
				return False
			f.write(fileitem.file.read())
			f.close()
			return True
		return False
		#end fileitem
	#end upload
	def urlexists(self,urlpath):
		import httplib
		# remove the beginning http:// if it's there
		prefix = "http://"
		if(urlpath[:7]=='http://'):
			urlpath = urlpath[7:]
		if(urlpath[:8]=='https://'):
			prefix = "https://"
			urlpath = urlpath[8:]
		# make sure url ends with /
		if(urlpath[-1:]!='/'):
			urlpath = urlpath+'/'
		site = urlpath[:urlpath.find('/')]
		path = urlpath[urlpath.find('/'):-1] #exclude trailing slash from path
		conn = httplib.HTTPConnection(prefix+site)
		conn.request('HEAD', path)
		response = conn.getresponse()
		conn.close()
		return response.status > 308
	#end urlexists
#end c_io class

#session management class
import sha, shelve, time, Cookie, os, sys
class c_session(object):
	def close(self):
		self.data.close()
	def destroy(self):
		try:
			self.data.close()
		except:
			pass
		try:
			self.data = None
		except:
			pass
	#end close
	# by default session expires in 1 day
	def start(self, expires=24*60*60, cookie_path="/"):
		try:
			string_cookie = os.environ.get('HTTP_COOKIE', '')
			self.cookie = Cookie.SimpleCookie()
			self.cookie.load(string_cookie)
			if self.cookie.get('sid'):
				sid = self.cookie['sid'].value
				# Clear session cookie from other cookies
				self.cookie.clear()
			else:
				self.cookie.clear()
				sid = sha.new(repr(time.time())).hexdigest()
			self.cookie['sid'] = sid
			if cookie_path:
				self.cookie['sid']['path'] = cookie_path
			session_dir = c.wwwroot+"session/"
			if not os.path.exists(session_dir):
				disk.mkdir(session_dir,0770)
			self.data = shelve.open(session_dir + 'sess_' + sid, writeback=True)
			# os.chmod(session_dir + '/sess_' + sid, 0660)
			
			# Initializes the expires data
			if not self.data.get('cookie'):
				self.data['cookie'] = {'expires':''}
			self.set_expires(expires)
			print("%s"%(self.cookie))
		except Exception as e:
			# pass
			print(sys.exc_traceback.tb_lineno, e)
	#end start
	def set_expires(self, expires=24*60*60):
		if expires == '':
			self.data['cookie']['expires'] = ''
		elif isinstance(expires, int):
			self.data['cookie']['expires'] = expires
		self.cookie['sid']['expires'] = self.data['cookie']['expires']
	#end set_expires
#end session class

#string class
class c_str():
	#outputs a dictionary as json-formatted response
	def jout(self, dictionary):
		import json
		print("Content-Type: text/html\n")
		print(json.dumps(dictionary))
	#outputs a regular text to screen (with html header)
	def pout(self, text):
		print("Content-Type: text/html\n")
		print(text)
#end string class

#url utilities class
class c_uri:
	uriString = ""
	uriList = []
	uriQuery = ""
	def __init__(self):
		import os
		# get uri string without the script name
		if "PATH_INFO" in os.environ:
			self.uriString = os.environ['PATH_INFO']
		else:
			self.uriString = ""
		self.uriList = self.uriString.split('/')
		if (not 'SCRIPT_NAME' in os.environ):
			os.environ['SCRIPT_NAME'] = ""
		self.uriList[0]=os.path.basename(os.environ['SCRIPT_NAME'])
		self.uriList = filter(None,self.uriList)
		if "QUERY_STRING" in os.environ:
			self.uriQuery = os.environ["QUERY_STRING"]
	#end __init__
	#returns total number of segments minus the script name
	def numsegs(self):
		return len(self.uriList)-1
	#end numsegs
	#returns array of segments
	def segarr(self):
		return self.uriList[1:]
	#returns a specified segment (segment 0 is the script name)
	def segment(self,segnum,ifempty=False):
		if len(self.uriList)<(segnum+1):
			#element doesn't exist, return the ifempty string (if it was specified)
			return ifempty
		return self.uriList[segnum]
	#end segment
	#returns query string (if one is present, false otherwise)
	def query(self):
		if len(self.uriQuery)>0:
			return self.uriQuery
		return False
	#end query
#end uri class

db = c_sqdb
disk = c_disk()
enc = c_enc()
io = c_io()
session = c_session()
sstr = c_str()
uri = c_uri()