#!/usr/bin/python
import controller as cs
try:
	# initialize the controller
	c = cs.Controller()
	# run it
	c._run()
except Exception as e:
	import sys
	print("Content-Type: text/html\n")
	print("{'success':0,'msg':'"+str(e)+"','line':'"+str(sys.exc_traceback.tb_lineno)+"'}") #manual json output
