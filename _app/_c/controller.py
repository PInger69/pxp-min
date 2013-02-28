from imp import load_source as ls
from imp import load_compiled as lp
m = lp("MVC","_m/mvc.pyc")
class Controller(m.MVC):
	p = None
	def __init__(self):
		pass
		# super(Controller, self).__init__()
	#this function is executed first
	def _run(self):
		# get the method name that the user is trying to access
		self.p = self.loader().module("pxp").pxp()
		sess = self.session(expires=24*60*60,cookie_path="/")

		functionName = self.uri().segment(1,"home")
		# if not "user" in sess.data and not functionName=="logincheck" and not functionName=="login":
		# 	#user is not logged in
		# 	#redirect to login
		# 	print "Location: login"		
		if (functionName[:1]=="_"): # methods starting with _ are private - user cannot access them
			functionName = ""
		# if (functionName=="ajax"): #call method from the pxp model
		# 	functionName = self.uri().segment(2,"")
		# 	fn = getattr(self.p, functionName, None)
		# else:#load view
		# 	if not self.sget("user"):
		# 		functionName ="login"
		# 	fn = getattr(self, functionName, None)
		fn = getattr(self.p, functionName, None)

		# check if it exists
		if callable(fn):# it does - go to that method
			self.str().jout(fn())
		else: # the method does not exist
			self.page(functionName)

		# print self.loader.modul
		# print "got here first"
	#end run
	def page(self,page):
		# output the page
		d = {
			"page":page,			
		}
		if(page=="home"):
			d['encStatus']=self.p.encoderstatus()
		if(page=="past"):
			d['events']=self.p._listEvents()
		self._out(page+'.html',d)
######################################
##		 internal functions	   ##
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
			template = engine.get_template(pgName)
			print(template.render(params))	
		except:
			pass
		template = engine.get_template('footer.html')
		print(template.render(params))
#end pout#end Controller()