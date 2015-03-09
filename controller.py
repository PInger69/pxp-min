import pxp, pxputil as pu
import constants as c
import sys, inspect

# extend the main MVC class
class Controller:
	p = None #pxp controller variable
	d = {} #data passed to the template engine
	sess = None
	def __init__(self):
		import os
		# ensure that the pxpStream app is running
		# if (not pu.disk.psOn("pxpStream.app")):
			# os.system("/usr/bin/open /Applications/pxpStream.app")
		# to make sure proper file is loaded

		#### -- deprecated --- ####
		# make sure list monitor is on (checks for discontinuities in the video)
		# if(os.path.exists(c.approot+"pxplistmon.py")):
		# 	suffix=""
		# else:
		# 	suffix="c"
		# if (not pu.disk.psOn("pxplistmon")):
			# os.system("/usr/bin/python "+c.approot+"pxplistmon.py"+suffix+" >/dev/null 2>/dev/null &")
		#### -- end deprecated --- ####

		# make sure socket service is on (for push instead of pull notifications)
		if(os.path.exists(c.approot+"pxpservice.py")):
			suffix=""
		else:
			suffix="c"
		# if (not pu.disk.psOn("pxpservice.py")):
			# os.system("/usr/bin/python "+c.approot+"pxpservice.py"+suffix+" >/dev/null 2>/dev/null &")
		# super(Controller, self).__init__()
		self.d['version']=c.ver
	#this function is executed first
	def _run(self):
		import os, sys
		# get the method name that the user is trying to access
		try:
			# load that pxp model
			# set up the session (to save login info)
			pu.session.start(expires=24*60*60,cookie_path="/")
			self.sess = pu.session
			sess = self.sess
			# check if session variable was set already (it will contain 'email' once user logs in)
			if (sess and not 'email' in sess.data):
				sess.data['email']=False
			# user will be set when user logs in
			if (sess and 'user' in sess.data):
				# someone is logged in - set the session variable
				self.d['user'] = sess.data['user']
				self.d['email']= sess.data['email']
			else:
				# nobody is logged in
				self.d['user'] = False
				self.d['email'] = False
			# get the name of the function user wants to call
			functionName = pu.uri.segment(1,"home")
			# check if there are any command line arguments 
			# this will be >1 when user calls the script from command line and passes parameters to it
			# e.g. python index.py egg
			if len(sys.argv)>1:
				# when running from command line, call the ajax functions (no need to display html page output)
				functionName="ajax"
			# check if user is trying to call a private function
			if (functionName[:1]=="_"): # methods starting with _ are private - user cannot access them
				functionName = ""
			elif (functionName=="ajax"): #call method from the pxp model (ajax mode)
				# function itself will be in the next parameter: e.g. min/ajax/tagset
				functionName = pu.uri.segment(2,"")
				# check if user is running it from command line 
				if len(sys.argv)>1:
					# command line argument will be the name of the function
					functionName=sys.argv[1]
				# the function will be called from the pxp model (not from this controller)
				fn = getattr(pxp, functionName, None)
			else: #not ajax and not command line, so user is viewing the web-based interface
				# get address of the function that user is requesting 
				# the function is either in this class (controller) 
				# or it's an html page, in which case fn will be false
				fn = getattr(self, functionName, None)
				# check if user is logged in or not
				if (not ((sess and 'user' in sess.data and sess.data['user']) or functionName=='login')):
					#user is not logged in and is not trying to login
					# redirect to login page
					sess.data['uri'] = functionName #remember the page he was trying to reach
					print("Location: login\n")
					# make sure the user does not proceed any further
					return
			# check what the user is trying to do
			if(functionName=='login' and sess and ('user' in sess.data) and sess.data['user']):
				#user just logged in, redirect him to home or the last page to which he was going
				if('uri' in sess.data and not (sess.data['uri'] == 'login' or sess.data['uri']=='logout')):
					# there was a page he was trying to reach - redirect him there
					print("Location: "+sess.data['uri']+"\n")
				else:
					# he didn't try going to any page prior to login - take him to the home page
					print("Location: home\n")
				return
			# check if function exists in this class (controller)
			if callable(fn):# it exists - go to that function
				if(functionName=='login' or functionName=='sync2cloud' or functionName=='coachpick'):
					# these functions require session variable to be passed to it
					result = fn(sess)
				else:
					# all the other functions can be called without parameters
					result = fn()
				# check if the result of the function is a dictionary and output it
				if type(result) is dict: 
					#make sure the result is dictionary (not a string or int) before tyring to assign values to it
					result['sender']='.min' #just to know who sent that message
					result['requrl']=pu.uri.uriString #the URL that user requested
				# output the result
				pu.sstr.jout(result)
			else: # the method that user tried to access does not exist 
				  # try to find an html page with this name
				self.page(functionName)
		except Exception as e:
			# in an event of unhandled error, output the result
			pu.sstr.jout({"msg":str(e)+' '+str(sys.exc_traceback.tb_lineno),"line":str(sys.exc_traceback.tb_lineno),"fct":"c.run","url":pu.uri.uriString})
	#end run
	#logs user out
	def logout(self):
		# call the logout function of pxp (model)
		pxp.logout(self.sess)
		# redirect the user to login page afterwards
		print("Location: login")
	#end logout
	# outputs the requested page
	def page(self,page):
		#assign the page name
		try:
			self.d["page"]=page
			# get info about the disk
			self.d["disk"]=pxp._diskStat()
			# get encoder status info
			self.d['encoder']=pxp.encoderstatus(textOnly=False)
			# home page requires list of leagues and teams
			if(page=="home"):
				self.d['leagues']=pxp._listLeagues()
				self.d['teams']=pxp._listTeams()
			# past events page requires list of past events
			if(page=="past"):
				self.d['events']=pxp._listEvents(showDeleted=False)
			if(page=='sett'):
				self.d['settings']=pxp.settingsGet()
			# output the page
			self._out(page+'.html',self.d)
		except Exception as e:
			pu.sstr.jout({"msg":str(e)+' '+str(sys.exc_traceback.tb_lineno),"line":str(sys.exc_traceback.tb_lineno),"fct":"c.page","url":pu.uri.uriString})
			pass
######################################
##		 internal functions	   		##
######################################
	# prints out the requested page
	def _out(self,pgName,params):
		# load "wheezy" template engine
		from wheezy.template.engine import Engine
		from wheezy.template.ext.core import CoreExtension
		from wheezy.template.ext.code import CodeExtension
		from wheezy.template.loader import FileLoader
		# where to look for views
		searchpath = ['_v/']
		# initialize the tempate engine
		engine = Engine(
			loader=FileLoader(searchpath),
			extensions=[CoreExtension(), CodeExtension()]
		)
		# load the header of the page first
		template = engine.get_template('header.html')
		# this is required for proper html output
		print("Content-Type: text/html\n")
		# output the html header of the page
		print(template.render(params))
		try:
			if(pgName=='egg.html'):
				print(pxp.egg()) #for the egg function, just output its contents
			else:
				# all the other functions need to go through template engine
				template = engine.get_template(pgName)
				print(template.render(params))
		except Exception as e:
			#in case of error, output it
			print(e)
		# load the html footer
		template = engine.get_template('footer.html')
		# output the footer
		print(template.render(params))
	#end out
#end Controller()
