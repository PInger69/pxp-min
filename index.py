#!/usr/bin/python
from imp import load_compiled as lp
from imp import load_source as ls
try:
	# print("Content-Type: text/html\n")
	# print "zzz"
	cs = ls("controller","_app/_c/controller.py")
	# cs = lp("controller","_app/_c/controller.pyc")
	# print("Cache-Control: no-store,no-cache, must-revalidate,post-check=0, pre-check=0,max-age=0\n")
	# print("Expires: Wed, 01 Sep 2010 00:00:00 GMT")
	# print("Pragma: no-cache")
	# response.headers['Cache-Control'] = 'no-store,no-cache, must-revalidate,post-check=0, pre-check=0,max-age=0'
	# response.headers['Expires'] = 'Wed, 01 Sep 2010 00:00:00 GMT'
	# response.headers['Pragma'] = 'no-cache'
	# initialize the controller
	c = cs.Controller()
	# run it
	c._run()
except Exception as e:
	import sys
	print("Content-Type: text/html\n")
	print("{'success':0,'msg':'"+str(e)+"','line':'"+str(sys.exc_traceback.tb_lineno)+"'}") #manual json output