#!/usr/bin/python
import imp
# import the controller
# loader = cu.loader()
# loader.module("modss")
cs = imp.load_source("controller","_app/_c/controller.py")
# print("Content-Type: text/html\n")
# initialize the controller
c = cs.Controller()
# run it
c._run()