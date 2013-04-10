class MVC():
	"""main MVC class"""
	approot = "/var/www/html/min/"
	wwwroot = "/var/www/html/events/"
	# wwwroot = "/Applications/MAMP/htdocs/events/"
	def __init__(self):
		# self.loader = c_loader()
		import os
		if (not (os.getcwd()+"/")==self.approot):
			os.chdir(self.approot) #make sure the current working directory is properly set
		# super(loader, self).__init__()
	#sqlite operations class
	def dbsqlite(self,dbpath=False):
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
		        if not self.c:
		            return False        
		        rows = []
		        #get column names
		        cols = []
		        for cn in self.c.description:
		            cols.append(cn[0])
		        #get all rows
		        for row in self.getrows():
		            entry = {}
		            idx = 0
		            for cn in cols:                
		                entry[cn] = row[idx]
		                idx += 1
		            rows.append(entry)
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
					self.con = sqlite3.connect(dbpath)
					self.c = self.con.cursor()
					success = True
					# cur.execute('SELECT SQLITE_VERSION()')
					# data = cur.fetchone()
				except sqlite3.Error, e:
					#put some errors here later
					# print "Error %s:" % e.args[0]
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
		    def qstr(self, query):
		        error = False
		        try:#to prevent sql errors from interrupting the script
		            self.c.execute(query)#run the query
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
		#end sqdb
		return c_sqdb(dbpath)
	#end dbsqlite
	#disk operations class
	def disk(self):
		class c_disk():
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
			def mkdir(self, dirpath, perm=0777):
				import os
				try:
					os.makedirs(dirpath,perm)
					return True
				except Exception as e:
					return False
					# print sys.exc_traceback.tb_lineno
					# print e
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
			        cmd = "ps -ef | grep "+process+" | grep -v grep > /dev/null" #"ps -A | pgrep "+process+" > /dev/null"
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
					data = 0
				#close the socket
				try:
					sock.close()
				except:
					#probably failed because bind didn't work - no need to worry
					pass
				return data
		#end c_disk class
		return c_disk()
	#end disk
	#encryption/string operations class
	def enc(self):
		class c_enc():
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
		return c_enc()
	#end enc
	#web input/output class
	def io(self):
		class c_input():
			frm = None
			def __init__(self):
				import cgitb; cgitb.enable()
				import cgi
				if not self.frm:
					self.frm = cgi.FieldStorage()
			def get(self, fieldName):
				return self.frm.getvalue(fieldName)
			#end get
			def send(self,url,params,jsn=False):
				import httplib, urllib, urlparse, json
				headers = {"Content-type": "application/x-www-form-urlencoded", "Accept": "text/plain"}
				parsed = urlparse.urlparse(url)
				conn = httplib.HTTPConnection(parsed.netloc)
				conn.request("POST", parsed.path, urllib.urlencode(params),headers)
				r1 = conn.getresponse()
				# from httplib2 import Http
				# from urllib import urlencode
				# h = Http()
				# resp, content = h.request(url, "POST", urlencode(params))
				# if resp['status']=='200':
				if(jsn):
					try:
						return json.loads(r1.read())
					except:
						return False
				return r1.read()
				pass				
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
		#end c_input

		#end c_input class
		return c_input()
	#end io
	#module/view loading class
	def loader(self):
		from imp import load_source as ls
		from imp import load_compiled as lp
		class c_loader():
			def module(self,modname):
				# return lp(modname,"_app/_m/"+modname+".pyc")
				return ls(modname,"_app/_m/"+modname+".py")
			def view(self,viewname):
				pass
		#end c_loader class 
		return c_loader()
	#end loader
	#session class
	def session(self, expires=None, cookie_path=None):
		import sha, shelve, time, Cookie, os, sys
		class c_session(object):
			# data = None
			def __init__(self, glob, expires=None, cookie_path=None):
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
					session_dir = glob.wwwroot+"session/"
					if not os.path.exists(session_dir):
						glob.disk().mkdir(session_dir,0770)
					self.data = shelve.open(session_dir + 'sess_' + sid, writeback=True)
					# os.chmod(session_dir + '/sess_' + sid, 0660)
					
					# Initializes the expires data
					if not self.data.get('cookie'):
						self.data['cookie'] = {'expires':''}
					self.set_expires(expires)
					print ("%s"%(self.cookie))
				except Exception as e:
					# pass
					print sys.exc_traceback.tb_lineno
					print e
			#end __init__
			def close(self):
				self.data.close()
			#end close
			def set_expires(self, expires=None):
				if expires == '':
					self.data['cookie']['expires'] = ''
				elif isinstance(expires, int):
					self.data['cookie']['expires'] = expires
				 
				self.cookie['sid']['expires'] = self.data['cookie']['expires']		
		return c_session(self,expires,cookie_path)
	#end session class
	#string class
	def str(self):
		class c_str():
			#outputs a dictionary as json-formatted response
			def jout(self, dictionary):
				import json
				print("Content-Type: text/html\n")
				print(json.dumps(dictionary))
			#outputs a regular text to screen (with html header)
			def pout(self, text):
				print("Content-Type: text/html\n")
				print text
			def err(self, msgText=""):
				return {"success":False,"msg":msgText}
		return c_str()
	#url class
	def uri(self):
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
		#end uri
		return c_uri()
	#end uri
#end MVC class
