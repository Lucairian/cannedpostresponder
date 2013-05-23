#! /usr/bin/python
# -*- coding: UTF-8

###############################################################################
# CannedPostResponder
# by Charlie Pashayan                                                          
# 2012                                                                         
# cannedpostresponder.py: The module providing the main functionality for 
# CannedPostResponder
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

import os
import praw
import re
import io_cpr
import argparse
from email.mime.text import MIMEText
import time
import signal
import logging

__author__ = 'Charlie Pashayan'
__version__ = '1.0.0'
__title__ = "CannedPostResponder"
program_description = ("Scan Reddit for threads matching certain criteria "
                       "and post canned responses to them.")

# want absolute path so program can run from anywhere
path = os.path.dirname(os.path.abspath(__file__)) + os.sep

alreadies_file = path + "alreadies.txt"
settings_file = path + "settings.txt"
instructions_file = path + "instructions.txt"
latest_file = path + "latest.txt"
pid_file = path + "pid.txt"
source_file = path + "cannedpostresponder.py"

no_kill = False
please_stop = False
please_die = False
is_change = False

pseudostop = signal.SIGUSR1
pseudokill = signal.SIGUSR2
sigchange = signal.SIGCHLD

settings_vars = ['username', 'text_editor', 'log_reader', 'smtp_port',
'recipients', 'email_password', 'password', 'subreddits', 'smtp_server',
'sleep_time', 'proprietor', 'limit', 'email']

RETRY_CODES = [502, 503, 504]

def sleep_handler(signum, frame):
    """Signal handler for pseudostop; tries to ensure
    that CannedPostResponder never stops while lock()ed."""
    global no_kill, please_stop
    if no_kill:
        please_stop = True
    else:
        os.kill(os.getpid(), signal.SIGSTOP)

def die_handler(signum, frame):
    """Signal handler for pseudostop; tries to ensure
    that CannedPostResponder never dies while lock()ed."""
    global no_kill, please_die
    if no_kill:
        please_die = True
    else:
        terminate(0)

def register_change(signum, frame):
    """Signal handler for sigchange, the signal CannedPostResponder
    from cpr_admin when a change has been made to any of the
    settings, instructions or message files."""
    global is_change
    is_change = True

def lock():
    """psudokill and psudostop will be postponed when received
    in the lock()ed state.  Used to protect the critical sections
    to avoid responding to the same thread twice."""
    global no_kill
    no_kill = True

def unlock():
    """If a pseudokill or pseudostop signal has been received
    during the time while CannedPostResponder was locked, this is the
    time to act on it.  If not, prepare to act immediately on
    these signals in the future."""
    global no_kill, please_stop
    no_kill = False
    if please_stop:
        please_stop = False
        os.kill(os.getpid(), signal.SIGSTOP)
    if please_die:
        terminate(0)

def terminate(exit_code):
    """Used to exit.  Importantly, cleans up pid_file."""
    os.remove(pid_file)
    os._exit(exit_code)

def are_new():
    """Says whether some change has been made to CannedPostResponder's 
    ancillary files."""
    global is_change
    return is_change

def file_barf(filename, filetype):
    """Deliver an error message and exit in the event that
    the given file of the given type is not found or readable."""
    logging.error("%s file %s is nonexistent or unreadable." % (filetype, 
                                                                filename))

def subname(submission):
    """Extracts the subreddit's name from the full url of a submission."""
    url_pieces = submission.permalink.split(os.sep)
    last = ""
    for piece in url_pieces:
        if last == "r":
            return piece
        last = piece
    return ""

class Instruction:
    """Stores the compiled regex, human readable regex (with flags) and
    the name of the text file containing the response to messages
    matched by the regex."""
    def __init__(self, re_string, flags, filename):
        self.re_string = "(%s, %s)" % (re_string, flags)
        if not flags:
            flags = "0"
        self.re_compiled = re.compile(eval(re_string), eval(flags))
        self.filename = eval(filename)

    def __str__(self):
        return "%s %s" % (self.re_string, self.filename)

class Alreadies:
    def __init__(self, alreadiesstr = ""):
        if alreadiesstr:
            self.done = eval(alreadiesstr)
        else:
            self.done = {}

    def __contains__(self, submission):
        subreddit, post = subname(submission), submission.id
        return subreddit in self.done and \
            post in self.done[subreddit]

    def insert(self, submission):
        subreddit, post = subname(submission), submission.id
        if subreddit in self.done:
            if submission not in self.done[subreddit]:
                self.done[subreddit].append(post)
        else:
            self.done[subreddit] = [post]

    def __str__(self):
        return str(self.done)

class Latest:
    """A dicionary of the most recent posts examined for responsded to,
    used to avoid checking the same posts twice."""
    def __init__(self, lateststr = ""):
        if lateststr:
            self.done = eval(lateststr)
        else:
            self.done = {}

    def latest(self, subreddit):
        if subreddit in self.done:
            return self.done[subreddit][0]
        else:
            return None
        
    def insert(self, submission):
        subreddit = subname(submission) 
        title = submission.id
        time = submission.created_utc
        if subreddit not in self.done or time >= self.done[subreddit][1]:
            self.done[subreddit] = (title, time)
    
    def __str__(self):
        return str(self.done)

class CannedPostResponder:
    """The thing itself.  Reads through posts on Reddit, examines posts to see
    if they match a set of regexes.  Each regex is matched with a text file.
    If a match is found, it posts the contents of that file.  Posts the first 
    match then stops looking, by the way."""
    def __init__(self, settings_file = None):
        """Pushes off most of the work to get_set(), which is necessary
        as it is liable to be called multiple times."""
        self.sleep_multiplier = 1
        if settings_file:
            self.get_set(settings_file)
        return

    def get_set(self, settings_file):
        """Read in the settings file and configure CannedPostResponder 
        accordingly."""
        settings = io_cpr.get_settings(settings_file)
        for setting in settings_vars:
            try:
                setattr(self, setting, settings[setting])
            except KeyError:
                logging.error("%s not present in settings file.  Terminating.",
                              setting)
                terminate(1)
        try:
            ip = io_cpr.Instruction_Parser(instructions_file)
            self.instructions = [Instruction(i[0], i[1], i[2]) for 
                                 i in ip]
        except io_cpr.parseError as err:
            logging.error("Could not parse instructions file.  Terminating")
            terminate(1)
        except IOError as err:
            if err.errno == 2:
                # file doesn't exist
                logging.error("Instructions file not found.  Terminating.")
                terminate(1)
        self.messages = {}
        for instruction in self.instructions:
            message_file = path + instruction.filename
            try:
                self.messages[instruction.filename] = \
                    open(message_file, 'r').read().rstrip()
            except IOError as err:
                if err.errno == 2:
                    # file doesn't exist
                    logging.error(("%s file is nonexistent or unreadable.  "
                                   "Terminating."), 
                                  message_file)
                    terminate(1)
        if os.path.exists(latest_file):
            latest_text = open(latest_file, "r").read()
        else:
            latest_text = ""
        self.latest = Latest(latest_text)
        if os.path.exists(alreadies_file):
            alreadies_text = open(alreadies_file, "r").read()
        else:
            alreadies_text = ""
        self.alreadies = Alreadies(alreadies_text)
        self.smtp = io_cpr.CPR_SMTP(host = self.smtp_server, 
                                    port = self.smtp_port)
        self.email_on = False
        if self.email:
            try:
                self.smtp.login(self.email, self.email_password)
                self.smtp.set_recipients(self.recipients)
                self.email_on = True
            except Exception as err:
                logging.error("Could not log into email as %s\nError: %s", 
                              self.email, str(err))
                terminate(1)
        self.user_agent = ('CannedPostResponder %s '
                           'operated by %s '
                           'writtn by %s' % (__version__, 
                                             self.proprietor, 
                                             __author__))

    def connect(self):
        """Connect CannedPostResponder to Reddit."""
        self.reddit = praw.Reddit(user_agent = self.user_agent, 
                                  disable_update_check = True)
        if not all([self.username, self.password]):
            logging.error(("Insufficient login data provided.  "
                           "Could not log in to Reddit.  Terminating."))
            terminate(1)
        try:
            self.reddit.login(username = self.username, 
                              password = self.password)
        except (praw.errors.InvalidUserPass, praw.errors.InvalidUser) as err:
            logging.error("Login failed, %s.\n%s\nterminating", type(err), 
                          str(err))
            terminate(1)

    def forward_unread(self):
        """Forward PMs and responses to personal address."""
        if not self.email_on:
            return
        for msg in self.reddit.get_unread(limit = None):
            if are_new():
                return
            lock()
            logging.info("forwarding %s from %s" % \
                           ("reply" if msg.was_comment else "message",
                            msg.author))
            try:
                self.smtp.forward_message(msg)
            except smtplib.SMTPException as err:
                logging.warning(('Could not email message: %s\n'
                                 '%s'), str(err), msg)
            msg.mark_as_read()
            unlock()

    def wants_response(self, submission):
        """Determine whether a submission is eligible for a response
        and which response is needed.  Returns either the name of
        the appropriate response or None."""
        if submission in self.alreadies:
            return None
        for instruction in self.instructions:
            pattern = instruction.re_compiled
            # concatenate subreddit name, post title and body, separated by 
            # newlines this way the user can specify where the string appears 
            # if needed
            bigstr = "\n".join([unicode(s) for s in [subname(submission), 
                                                 submission.title, 
                                                 submission.selftext]])
            if pattern.search(bigstr):
                return instruction
        return None

    def match_and_respond(self):
        """Scans posts in relevant subreddits, responding to the ones that 
        match with the preset response.  Note that only the response associated
        with the first matching regular expression will be posted."""
        for sub in self.subreddits:
            latest = self.latest.latest(sub)
            subreddit = self.reddit.get_subreddit(sub)
            limit = None if latest else self.limit
            # if digging for latest don't bother with numerical limit
            try:
                submissions = list(subreddit.get_new(place_holder = latest, 
                                                     limit = limit))
            except praw.errors.InvalidSubreddit:
                logging.warning("%s is not a valid subreddit.", sub)
                self.subreddits.remove(sub)
                continue
            except requests.exceptions.HTTPError as err:
                logging.error(err.errstr)
                if err.response.status_code in RETRY_CODES:
                    self.sleep_multiplier += 1
                    return
                else:
                    raise
            except requests.exceptions.ConnectionError as err:
                logging.error(err.errstr)
                self.sleep_multiplier += 1
                return
            newest = None
            for submission in reversed(list(submissions)):
                if submission.id == latest:
                    continue
                instruction = self.wants_response(submission)
                if instruction:
                    if are_new():
                        return
                    lock()
                    msg = self.messages[instruction.filename]
                    try:
                        submission.add_comment(msg)
                    except Exception as err:
                        # not sure what errors are possible here so
                        # catch them all and record them, assuming they're
                        # caused by network errors or maintenence downtime
                        logging.error(str(err))
                        self.sleep_multiplier += 1
                        unlock()
                        return
                    self.latest.insert(submission)
                    open(latest_file, "w").write(str(self.latest))
                    self.alreadies.insert(submission)
                    open(alreadies_file, "w").write(str(self.alreadies))
                    logging.info("post: %s\nmatching: %s\nresponse: %s" % 
                                 (submission.title, instruction.re_string, 
                                  instruction.filename))
                    if self.email_on:
                        try:
                            self.smtp.archive_comment(submission, instruction)
                        except smtplib.SMTPException as err:
                            logging.warning('Could not send email: %s', 
                                            str(err))
                    unlock()
            self.sleep_multiplier = 1

def cpr_args():
    """Sets up the ArgumentParser; just to keep the main loop uncluttered."""
    parser = argparse.ArgumentParser(description = program_description)
    parser.add_argument('--pid_key', nargs = 1, type = int, default = None,
                        help = ('temprorary value in pid file to discourage '
                                'running multiple instances of RedditBotBo'))
    parser.add_argument('--version', action = 'version',
                        version = "%s version %s by %s" % 
                        (__title__, __version__, __author__))
    parser.add_argument('--settings', nargs = 1,
                        help = ('name of the settings file to be used '
                                'by CannedPostResponder'))
    return parser.parse_args()

def ensure_unique(pid_key = None):
    """Make sure there isn't a copy or CannedPostResponder already running."""
    if pid_key:
        pid_key = pid_key[0]
    try:
        fd = os.open(pid_file, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        os.fdopen(fd, "w").write(str(os.getpid()))
    except OSError as err:
        if err.errno == 17:
            # file already exists
            found_key = eval(open(pid_file, "r").read())
            if found_key == pid_key:
                open(pid_file, "w").write(str(os.getpid()))
            else:
                os._exit(1)

if __name__ == '__main__':
    logging.basicConfig(filename = io_cpr.log_file,
                        filemode = 'a',
                        level = logging.INFO,
                        format = ('%(asctime)s <%(levelname)s>\n%(message)s'))
    args = cpr_args()
    ensure_unique(args.pid_key)
    signal.signal(pseudostop, sleep_handler)
    signal.signal(pseudokill, die_handler)
    signal.signal(sigchange, register_change)
    cpr = CannedPostResponder(settings_file)
    cpr.connect()
    while True:
        if are_new():
            is_change = False
            cpr.get_set(settings_file)
            cpr.connect()
        cpr.forward_unread()
        cpr.match_and_respond()
        time.sleep(cpr.sleep_time * cpr.sleep_multiplier)
