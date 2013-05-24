#! /usr/bin/python

###############################################################################
# CannedPostResponder
# by Charlie Pashayan                                                          
# 2012                                                                         
# install_cpr.py: This script makes sure that all the modules needed by
# CannedPostResponder can be imported.  If everything is in order, it makes
# a wrapper for cpr_admin.py that can be called from any directory, making it
# easier to run.
#
# Copyright (c) 2012 Charlie Pashayan                                          
#                                                                              
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to     
# deal in the Software without restriction, including without limitation the   
# rights to use, copy, modify, merge, publish, distribute, sublicense, and/or  
# sell copies of the Software, and to permit persons to whom the Software is   
# furnished to do so, subject to the following conditions:                     
#                                                                              
# The above copyright notice and this permission notice shall be included in   
# all copies or substantial portions of the Software.                         
#                                                                             
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR 
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,    
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE 
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER 
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING     
# FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS
# IN THE SOFTWARE.                                                            
###############################################################################

import argparse
import os
import compiler
import sys
import imp
import stat

sourcefiles = ["cannedpostresponder.py", "io_cpr.py", "cpr_admin.py"]
def_name = "cpr_admin"

def pull_imports(f):
    """Pull a list of all the modules imported
    in a script."""
    tree = compiler.parseFile(f)
    imps = set()
    for n in tree.node.nodes:
        node_type = str(n.__class__).split(".")[-1]
        if node_type == "Import":
            imps = imps.union([m[0] for m in n.names])
        if node_type == "From":
            imps.add(n.modname)
    return [m.split(".")[0] for m in imps]

def mod_exists(mod):
    """Check whether module is known to exist."""
    try:
        imp.find_module(mod)
        return True
    except ImportError:
        return False

# parse arguments
ap = argparse.ArgumentParser(description = 
                             ("verifies that system contains modules needed "
                              "by CannedPostResponder and creates an alias "
                              "for cpr_admin.py, making it easier to call "
                              "from another directory"))
ap.add_argument("name", type = str, nargs = "?", default = def_name,
                help = ("desired name of alias script; default is %s"
                        "'cpr_admin', in the current working directory"
                        % (def_name)))
ap.add_argument("--do_not_check", "-d", action = "store_true",
                default = False, help = ("don't bother checking for "
                                         "modules"))
args = ap.parse_args()

# check system for needed modules
if not args.do_not_check:
    imported = set()
    for f in sourcefiles:
        imported = pull_imports(f)
        lacking = [m for m in imported if not mod_exists(m)]
    if len(lacking):
        print "CannedPostResponder needs the following modules to run:"
        print "\n".join(["\t%s" % (mod) for mod in lacking])
        sys.exit(1)

# create alias
fullpath = (os.path.dirname(os.path.abspath(__file__)) + 
            os.sep +
            "cpr_admin.py")
fp = open(args.name, "w")
fp.write("# this script is a wrapper for cpr_admin.py, to allow it\n")
fp.write("# to be called easily from somewhere in the user's PATH\n")
fp.write(fullpath + "\n")
fp.close()
os.chmod(args.name, stat.S_IRWXU | stat.S_IRGRP | stat.S_IXGRP |
         stat.S_IROTH | stat.S_IXOTH)
