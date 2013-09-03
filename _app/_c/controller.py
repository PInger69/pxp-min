from imp import load_source as ls
from imp import load_compiled as lp
# m = lp("MVC","_m/mvc.pyc")
m = ls("MVC","_m/mvc.py")
class Controller(m.MVC):
	version = "0.93.4"
	p = None #pxp controller variable
	d = {} #data passed to the template engine
	sess = None
	def __init__(self):
		import os
		# ensure that the pxpStream app is running
		if (not self.disk().psOn("pxpStream.app")):
			os.system("/usr/bin/open /Applications/pxpStream.app")
		# super(Controller, self).__init__()
		self.d['version']=self.version
	#this function is executed first
	def _run(self):
		import os, sys
		# get the method name that the user is trying to access
		try:
			self.p = self.loader().module("pxp").pxp()
			self.sess = self.session(expires=24*60*60,cookie_path="/")
			sess = self.sess
			# sess = False
			if (sess and not 'email' in sess.data):
				sess.data['email']=False
			# sess = {}
			# sess['data'] = {}
			if (sess and 'user' in sess.data):
				# someone is logged in - set the session variable
				self.d['user'] = sess.data['user']
				self.d['email']= sess.data['email']
			else:
				# nobody is logged in
				self.d['user'] = False
				self.d['email'] = False
			functionName = self.uri().segment(1,"home")
			if len(sys.argv)>1:
				functionName="ajax"
			if (functionName[:1]=="_"): # methods starting with _ are private - user cannot access them
				functionName = ""
			elif (functionName=="ajax"): #call method from the pxp model
				functionName = self.uri().segment(2,"")
				if len(sys.argv)>1:
					functionName=sys.argv[1]
				fn = getattr(self.p, functionName, None)
			else:#load view
				fn = getattr(self, functionName, None)
				# fn = getattr(self.p, functionName, None)		
				if (not ((sess and 'user' in sess.data and sess.data['user']) or functionName=='login')):
					#user is not logged in
					# redirect to login
					sess.data['uri'] = functionName
					print "Location: login\n"
					# make sure the user does not proceed any further
					return
			if(functionName=='login' and sess and ('user' in sess.data) and sess.data['user']):
				#user just logged in, redirect him to home
				if('uri' in sess.data and not (sess.data['uri'] == 'login' or sess.data['uri']=='logout')):
					print "Location: "+sess.data['uri']+"\n"
				else:
					print "Location: home\n"
				return
			# check if it exists
			if callable(fn):# it exists - go to that method
				if(functionName=='login' or functionName=='sync2cloud' or functionName=='coachpick'):
					result = fn(sess)
				else:
					result = fn()
				if type(result) is dict: 
					#make sure the result is dictionary (not a string or int) before tyring to assign values to it
					result['sender']='.min'
					result['requrl']=self.uri().uriString
				self.str().jout(result)
			else: # the method does not exist - try to find a page with this name
				self.page(functionName)
		except Exception as e:
			import sys, inspect
			self.str().jout({"msg":str(e)+' '+str(sys.exc_traceback.tb_lineno),"line":str(sys.exc_traceback.tb_lineno),"fct":"c.run","url":self.uri().uriString})
			# print inspect.trace()
		# db = self.dbsqlite(self.wwwroot+"live/pxp.db")
		# sql = "INSERT INTO tags (user, player) VALUES('zzz', '9')"
		# db.qstr(sql)
		# print db.lastID()
		# db.close()
		# print self.loader.modul
		# print "got here first"
	#end run
	#logs user out
	def logout(self):
		self.p.logout(self.sess)
		print "Location: login"
	#end logout
	def page(self,page):
		# output the page
		self.d["page"]=page
		self.d["disk"]=self.p._diskStat()
		self.d['encoder']=self.p.encoderstatus(textOnly=False)
		if(page=="home"):
			self.d['leagues']=self.p._listLeagues()
			self.d['teams']=self.p._listTeams()
		if(page=="past"):
			self.d['events']=self.p._listEvents(showDeleted=False)
		self._out(page+'.html',self.d)
######################################
##		 internal functions	   		##
######################################
	def _out(self,pgName,params):
		from wheezy.template.engine import Engine
		from wheezy.template.ext.core import CoreExtension
		from wheezy.template.ext.code import CodeExtension
		from wheezy.template.loader import FileLoader

		searchpath = ['_app/_v/']
		engine = Engine(
			loader=FileLoader(searchpath),
			extensions=[CoreExtension(), CodeExtension()]
		)
		template = engine.get_template('header.html')
		print("Content-Type: text/html\n")
		print(template.render(params))
		try:
			if(pgName=='egg.html'):
				print self.p.egg()
			else:
				template = engine.get_template(pgName)
				print(template.render(params))
		except Exception as e:
			print e
		template = engine.get_template('footer.html')
		print(template.render(params))
	#end out
#end Controller()