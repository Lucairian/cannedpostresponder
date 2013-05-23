#! /usr/bin/python

###############################################################################
# CannedPostResponder
# by Charlie Pashayan                                                          
# 2012                                                                         
# cpr_admin.py: This script provides the user interface for 
# CannedPostResponder.
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

import cannedpostresponder
import io_cpr
import argparse
import sys
import re
import os
import psutil
import time
import random
import signal

program_description = ("cpr_admin lets you administer a CannedPostResponder "
                       "by modifying its settings, running, suspending "
                       "and killing it.")

parser = argparse.ArgumentParser(description = program_description)
parser.add_argument('--version', action = 'version', 
                    version = "%s version %s by %s" % 
                    (cannedpostresponder.__title__, 
                     cannedpostresponder.__version__, 
                     cannedpostresponder.__author__))
parser.add_argument('--display', action = 'store_true',
                    help = ('display the current values for all '
                            'settings and then quit'))
parser.add_argument('--instructions', action = 'store_true',
                    help = ('edit the instructions file used by CannedPostResponder '
                            'instructions must begin with a Python ready '
                            'regular expression, including  optional flags, '
                            'followed byt the name of the file containing '
                            'the response to posts maching the regular '
                            'expression'))
parser.add_argument('--message', nargs = '+', type = str,
                    help = ('edit the named message files and create them '
                            'if necessary'))
parser.add_argument('--clear_latest', nargs = '+', type = str,
                    help = ('clear the timestamp of the most recent post '
                            'viewed from the named subreddit, so that <limit> '
                            'posts will be retreived; useful after changing '
                            'instructions for the given subreddit'))
parser.add_argument('--clear_all_latest', action = 'store_true',
                    help = ('clear the timestamps for most recent posts '
                            'for all subreddits'))
parser.add_argument('--log', action = 'store_true',
                    help = ('view the log file'))
parser.add_argument('--username', nargs = 1, type = str,
                    help = ('the username of the account used to '
                            'access Reddit by CannedPostResponder'))
parser.add_argument('--password', nargs = 1, type = str,
                    help = ('the password for the account used to '
                            'access Reddit by CannedPostResponder'))
parser.add_argument('--email', nargs = 1, type = str,
                    help = ('the email address used to send mail '
                            'by CannedPostResponder'))
parser.add_argument('--add_recipients', nargs = '+', type = str,
                    help = ('email addresses to add to the list of '
                            'recipients for mail from CannedPostResponder'))
parser.add_argument('--del_recipients', nargs = '+', type = str,
                    help = ('email addresses to remove from the list '
                            'of recipients for mail from CannedPostResponder'))
parser.add_argument('--email_password', nargs = 1, type = str,
                    help = ('the password for the email address '
                            'used to send mail by CannedPostResponder'))
parser.add_argument('--smtp_server', nargs = 1, type = str,
                    help = ('the SMTP server from which '
                            'CannedPostResponder will send email'))
parser.add_argument('--smtp_port', nargs = 1, type = int,
                    help = ('the port used to connect to the '
                            'SMTP server'))
parser.add_argument('--proprietor', nargs = 1, type = str,
                    help = ('the Reddit account of the '
                            'person running CannedPostResponder'))
parser.add_argument('--limit', nargs = 1, type = int,
                    help = ('the maximum number of posts to '
                            'retreive from a new subreddit; '
                            '\'None\' will retreive all posts '
                            'but is likely to be very slow'))
parser.add_argument('--add_subreddits', nargs = '+', type = str,
                    help = ('email addresses to add to the list of '
                            'subreddits for mail from CannedPostResponder'))
parser.add_argument('--del_subreddits', nargs = '+', type = str,
                    help = ('email addresses to remove from the list '
                            'of subreddits for mail from CannedPostResponder'))
parser.add_argument('--text_editor', nargs = 1,
                    help = ('which text editor to envoke when '
                            'editing instructions file'))
parser.add_argument('--log_viewer', nargs = 1,
                    help = ('what program to use to view log file'))
parser.add_argument('--sleep_time', nargs = 1, type = int,
                    help = ('how CannedPostResponder should sleep before checking '
                            'for new submissions'))
parser.add_argument('--silent', action = 'store_true',
                    help = ('run cpr_admin with no visible output '
                            'unless invoked with --display or --status'))
parser.add_argument('--run', action = 'store_true',
                    help = ('create an instance of Cannedpostresponder if there '
                            'isn\'t already one'))
parser.add_argument('--suspend', action = 'store_true',
                    help = ('suspend the currently running instance '
                            'of CannedPostResponder if there is one'))
parser.add_argument('--resume', action = 'store_true',
                    help = ('resume the currently running instance '
                            'of CannedPostResponder if there is one'))
parser.add_argument('--kill', action = 'store_true',
                    help = ('kill the currently running instance '
                            'of CannedPostResponder if there is one'))
parser.add_argument('--status', action = 'store_true',
                    help = ('report whether or not an instance of '
                            'CannedPostResponder is currently running'))

args = parser.parse_args()
settings = io_cpr.get_settings(cannedpostresponder.settings_file)
argdic = vars(args)
change_made = False
for key in argdic:
    if argdic[key]:
        adder = re.compile("add_(?P<variable>.*)")
        deleter = re.compile("del_(?P<variable>.*)")
        addmatch = adder.match(key)
        delmatch = deleter.match(key)
        varname = ""
        if addmatch:
            # anything appendable begins with add_<variable>
            varname = addmatch.group("variable")
            to_add = argdic[key]
            if varname in settings:
                settings[varname].extend(to_add)
        elif delmatch:
            # anything deletable begins with del_<variable>
            varname = delmatch.group("variable")
            to_del = argdic[key]
            if varname in settings:
                settings[varname] = [one for one in settings[varname] 
                                     if one not in to_del]
        elif key in settings:
            # copy over anything else that matches a key to settings
            varname = key
            settings[varname] = argdic[key][0]
        if varname in settings:
            change_made = True
            if not args.silent:
                print "%s: %s" % (varname, settings[varname])

if args.display or len(sys.argv) == 1:
    for var in settings:
        print "%s: %s" % (var, settings[var])

if args.instructions:
    os.system("%s %s" % (settings['text_editor'], \
                             cannedpostresponder.instructions_file))
    change_made = True

if args.message:
    for msg_file in args.message:
        os.system("%s %s" % (settings['text_editor'], msg_file))
    change_made = True

if args.clear_latest:
    if os.path.exists(cannedpostresponder.latest_file):
        latest = eval(open(cannedpostresponder.latest_file, "r").read())
        latest = {sub: latest[sub] for sub in latest \
                      if sub not in args.clear_latest}
        open(cannedpostresponder.latest_file, "w").write(str(latest))
        change_made = True

if args.clear_all_latest:
    os.remove(cannedpostresponder.latest_file)
io_cpr.store_settings(cannedpostresponder.settings_file, settings)    

if args.log:
    if os.path.exists(io_cpr.log_file):
        os.system("%s %s" % (settings['log_reader'], io_cpr.log_file))
    else:
        print "No log file currently exists"

if change_made:
    if os.path.exists(cannedpostresponder.pid_file):
        try:
            pid = eval(open(cannedpostresponder.pid_file, "r").read())
            os.kill(pid, cannedpostresponder.sigchange)
        except OSError as err:
            if err.errno == 3:
                os.remove(cannedpostresponder.pid_file)

if args.run:
    if os.path.exists(cannedpostresponder.pid_file):
        # clear out old pid_file if it exists
        pid = eval(open(cannedpostresponder.pid_file, "r").read())
        try:
            psutil.Process(pid)
        except Exception as err:
            if type(err) == psutil._error.NoSuchProcess:
                os.remove(cannedpostresponder.pid_file)
            else:
                raise err
    try:
        # open a file for the pid; fails if one already exists
        fd = os.open(cannedpostresponder.pid_file, 
                     os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        pid_key = os.getpid()
        os.fdopen(fd, "w").write(str(pid_key))
        p = psutil.Popen([cannedpostresponder.source_file, 
                          "--pid_key", str(pid_key)])
    except OSError as err:
        if err.errno == 17:
            # file already exists
            if not args.silent:
                print "There is already a CannedPostResponder process running."
        else:
            raise err

if args.suspend:
    if os.path.exists(cannedpostresponder.pid_file):
        try:
            pid = eval(open(cannedpostresponder.pid_file, "r").read())
            os.kill(pid, cannedpostresponder.pseudostop)
        except OSError as err:
            os.remove(cannedpostresponder.pid_file)
            if err.errno == 3:
                if not args.silent:
                    print "No CannedPostResponder process running"
            else:
                raise err
    else:
        if not args.silent:
            print "No CannedPostResponder process running"

if args.resume:
    if os.path.exists(cannedpostresponder.pid_file):
        try:
            pid = eval(open(cannedpostresponder.pid_file, "r").read())
            process = psutil.Process(pid)
            process.resume()
        except psutil._error.NoSuchProcess as err:
            os.remove(cannedpostresponder.pid_file)
            if not args.silent:
                print "No CannedPostResponder process running"
    else:
        if not args.silent:
            print "No CannedPostResponder process running"

if args.kill:
    if os.path.exists(cannedpostresponder.pid_file):
        pid = eval(open(cannedpostresponder.pid_file, "r").read())
        try:
            process = psutil.Process(pid)
            if process.status == psutil.STATUS_STOPPED:
                process.resume()
            os.kill(pid, cannedpostresponder.pseudokill)
        except psutil._error.NoSuchProcess as err:
            os.remove(cannedpostresponder.pid_file)
            if not args.silent:
                print "No CannedPostResponder process running"
    else:
        if not args.silent:
            print "No CannedPostResponder process running"

if args.status:
    try:
        pid = eval(open(cannedpostresponder.pid_file, "r").read())
        process = psutil.Process(pid)
        print "CannedPostResponder is %s" % (str(process.status))
    except Exception as err:
        if type(err) == psutil._error.NoSuchProcess or \
                type(err).__name__ == 'IOError' and err.errno == 2:
            print "No CannedPostResponder is active"
        else:
            raise err
