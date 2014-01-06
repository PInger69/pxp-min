#!/usr/bin/python
compiled = False
# loads external python module (either from source or compiled)
def lm(module,path):
	global compiled
	from imp import load_source as ls
	from imp import load_compiled as lp
	if(compiled):
		return lp(module,path+"c") #compiled extensions are .pyc
	return ls(module,path)
try:
	cs = lm("controller","_app/_c/controller.py")
	# initialize the controller
	c = cs.Controller()
	# run it
	c._run()
except Exception as e:
	import sys
	print("Content-Type: text/html\n")
	print("{'success':0,'msg':'"+str(e)+"','line':'"+str(sys.exc_traceback.tb_lineno)+"'}") #manual json output
