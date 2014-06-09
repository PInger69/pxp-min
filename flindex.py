from flask import Flask, redirect, url_for ,render_template, request
import re, pxputil as pu
import sys, inspect, os, json
import pxp
import constants as c
import urllib

print "FLASKKKKKKKKKKKKKKKKKKKKKKKKKKKKKKKKKKKKKKK"
app = Flask(__name__)

p = None #pxp controller variable
d = {} #data passed to the template engine
sess = None


@app.route('/min/', methods=['GET','POST'])
@app.route('/min/<path:path>', methods=['GET','POST'])
@app.errorhandler(404)
def catch_all(path=""):
	try:
		pu.uri.host = request.host
		pu.uri.uriString = "min/"+urllib.unquote(path).decode('utf8')
		pu.uri.uriList = pu.uri.uriString.split('/')
		print '--------------------------:'
		print request.args
		print ':--------------------------'
		if(request.method=='GET'):
			pu.io.frm = request.args
		else:
			pu.io.frm = request.form
		print "Catch all path " + str(path)
		sess = pu.session
		# check if session variable was set already (it will contain 'email' once user logs in)
		if (sess and not 'email' in sess.data):
			sess.data['email']=False
		# user will be set when user logs in
		if (sess and 'user' in sess.data):
			# someone is logged in - set the session variable
			d['user'] = sess.data['user']
			d['email']= sess.data['email']
		else:
			# nobody is logged in
			d['user'] = False
			d['email'] = False
		# get the name of the function user wants to call
		functionName = pu.uri.segment(1,"home")
		# check if there are any command line arguments 
		# check if user is trying to call a private function
		if (functionName[:1]=="_"): # methods starting with _ are private - user cannot access them
			functionName = ""
		elif (functionName=="ajax"): #call method from the pxp model (ajax mode)
			# function itself will be in the next parameter: e.g. min/ajax/tagset
			functionName = pu.uri.segment(2,"")
			# the function will be called from the pxp model (not from this controller)
			fn = getattr(pxp, functionName, None)
		else: #not ajax and not command line, so user is viewing the web-based interface
			# get address of the function that user is requesting 
			# the function is either in this class (controller) 
			# or it's an html page, in which case fn will be false
			fn = globals()[functionName] if functionName in globals() else None
			print fn
			# check if user is logged in or not
			if (not ((sess and 'user' in sess.data and sess.data['user']) or functionName=='login')):
				print "redirect????????"
				#user is not logged in and is not trying to login
				# redirect to login page
				sess.data['uri'] = functionName #remember the page he was trying to reach
				# print("Location: login\n")
				# make sure the user does not proceed any further
				return redirect("/min/login")
		print "FUNCIONNNNNNNNNNNNNNNNNNNNNN:", functionName
		# check what the user is trying to do
		if(functionName=='login' and sess and ('user' in sess.data) and sess.data['user']):
			print "logged in????"
			#user just logged in, redirect him to home or the last page to which he was going
			if('uri' in sess.data and not (sess.data['uri'] == 'login' or sess.data['uri']=='logout')):
				# there was a page he was trying to reach - redirect him there
				# print("Location: "+sess.data['uri']+"\n")
				return redirect("/min/"+sess.data['uri'])
			else:
				# he didn't try going to any page prior to login - take him to the home page
				# print("Location: home\n")
				return redirect("/min/home")
		# check if function exists in this class (controller)
		if callable(fn):# it exists - go to that function
			print "callbale!!"
			if(functionName=='login' or functionName=='sync2cloud' or functionName=='coachpick'):
				# these functions require session variable to be passed to it
				result = fn(sess)
			else:
				# all the other functions can be called without parameters
				print functionName, " getting..."
				result = fn()
			print "RESPONSE:::::::::::::::::::", result
			# check if the result of the function is a dictionary and output it
			if type(result) is dict: 
				#make sure the result is dictionary (not a string or int) before tyring to assign values to it
				result['sender']='.min' #just to know who sent that message
				result['requrl']=pu.uri.uriString #the URL that user requested
				return json.dumps(result)
			#the result isn't a dictionary, just output the data (probably garbage)
			return result
		else: # the method that user tried to access does not exist 
			print "not callable!!!!!!"
			  # try to find an html page with this name
			return _page(functionName)
	except Exception as e:
		# in an event of unhandled error, output the result
		return json.dumps({"msg":str(e)+' '+str(sys.exc_traceback.tb_lineno),"line":str(sys.exc_traceback.tb_lineno),"fct":"c.run","url":pu.uri.uriString})
#end catch_all


# prints out the requested page
def _out(pgName,params):
	# load "wheezy" template engine
	print "_out wheezy"

	from wheezy.template.engine import Engine
	from wheezy.template.ext.core import CoreExtension
	from wheezy.template.ext.code import CodeExtension
	from wheezy.template.loader import FileLoader
	madePage = ""
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
	print params
	# output the html header of the page
	madePage += template.render(params)
	try:
		if(pgName=='egg.html'):
			print(pxp.egg()) #for the egg function, just output its contents
		else:
			# all the other functions need to go through template engine
			template = engine.get_template(pgName)
			madePage = madePage + (template.render(params))
	except Exception as e:
		pass
		#in case of error, output it
		# print(e)
		# madePage = madePage + e 
	# load the html footer
	template = engine.get_template('footer.html')
	# output the footer
	# print(template.render(params))
	madePage += template.render(params)

	return madePage

def _page(page):
	#assign the page name
	try:
		print "_page:::::::::::::::", page
		d["page"]=page
		# get info about the disk
		d["disk"]=pxp._diskStat()
		# get encoder status info
		d['encoder']=pxp.encoderstatus(textOnly=False)
		# home page requires list of leagues and teams
		if(page=="home"):
			d['leagues']=pxp._listLeagues()
			d['teams']=pxp._listTeams()
		# past events page requires list of past events
		if(page=="past"):
			d['events']=pxp._listEvents(showDeleted=False)
		if(page=='sett'):
			d['settings']=pxp.settingsGet()
		return _out(page+'.html', d)
	except Exception as e:
		return json.dumps({"msg":str(e)+' '+str(sys.exc_traceback.tb_lineno),"line":str(sys.exc_traceback.tb_lineno),"fct":"c.page","url":pu.uri.uriString})

def logout():
	# call the logout function of pxp (model)
	pxp.logout(pu.session)
	# redirect the user to login page afterwards
	return redirect("/min/login")

print "FLASK INITTTTTTTTTTTTTTTTTTTTTTTTTTTT"
# if (not pu.disk.psOn("pxpStream.app")):
	# os.system("/usr/bin/open /Applications/pxpStream.app")
# to make sure proper file is loaded
# make sure list monitor is on (checks for discontinuities in the video)
if(os.path.exists(c.approot+"pxplistmon.py")):
	suffix=""
else:
	suffix="c"
#if (not pu.disk.psOn("pxplistmon")):
#	os.system("/usr/bin/python "+c.approot+"pxplistmon.py"+suffix+" >/dev/null 2>/dev/null &")
# make sure socket service is on (for push instead of pull notifications)
if(os.path.exists(c.approot+"pxpservice.py")):
	suffix=""
else:
	suffix="c"
#if (not pu.disk.psOn("pxpservice.py")):
#	os.system("/usr/bin/python "+c.approot+"pxpservice.py"+suffix+" >/dev/null 2>/dev/null &")
d['version']=c.ver
pu.session.start(expires=24*60*60,cookie_path=c.sessdir)
# pu.uri.host = request.url_root
print "FLASK INITED!!!"

if __name__ == '__main__':
	app.debug = True
	app.run(host='0.0.0.0')
