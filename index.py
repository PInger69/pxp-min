#!/usr/bin/python
from imp import load_compiled as lp
from imp import load_source as ls
try:
	cs = ls("controller","_app/_c/controller.py")
	# cs = lp("controller","_app/_c/controller.pyc")
	# print("Content-Type: text/html\n")
	# initialize the controller
	c = cs.Controller()
	# run it
	c._run()
except Exception as e:
	import sys
	print("Content-Type: text/html\n")
	print("{'success':0,'msg':'"+str(e)+"','line':'"+str(sys.exc_traceback.tb_lineno)+"'}") #manual json output