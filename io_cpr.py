#! /usr/bin/python
# -*- coding: UTF-8

###############################################################################
# CannedPostResponder
# by Charlie Pashayan                                                          
# 2012                                                                         
# io_cpr.py: The module containing the handrolled io functions specific to 
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

import sys
import re
import token
import tokenize
import readline
import smtplib
from email.mime.text import MIMEText
from datetime import datetime
import logging
import os

path = os.path.dirname(os.path.abspath(__file__)) + os.sep

log_file = path + ".log.txt"

class FatalError(Exception):
    pass

class parseError(FatalError):
    def __init__(self):
        self.name = "Parse Error"

    def __str__(self):
        return self.name

class fileError(FatalError):
    def __init__(self):
        self.name = "Required file doesn't exist"

    def __str__(self):
        return self.name

def dfa_barf(tok, filename, filetype):
    """If one of the DFAs below has a problem, it calls this function to
    report it and and raise an exception."""
    logging.error(("Errant token, '%s' found in line %s "
                      "of %s file, %s:\n%s") % (tok[1], tok[2][0], filetype, 
                                                filename, 
                                                unicode(tok[4].rstrip())))
    raise parseError

class CPR_SMTP(smtplib.SMTP_SSL):
    """This class returns an smtp object specifically designed for
    passing along messages from CannedPostResponder."""
    def __init__(self, host, port = 465):
        """Creates an SMTP_SSL object for handling mail."""
        self.smtp = smtplib.SMTP_SSL(host = host, port = port)

    def login(self, user, password):
        """Logs in to the specified address."""
        self.sender = user
        return self.smtp.login(user, password)        

    def set_recipients(self, recipients):
        """Set recipients for mail for this session."""
        self.recipients = recipients

    def send_email(self, subject, message):
        """Sends specified message with specified subject to specified
        recipients.  Uses the email address that was previously specified."""
        message = message.encode("UTF-8")
        msg = MIMEText(message)
        msg['Subject'] = subject
        msg['From'] = self.sender
        msg['To'] = ", ".join(self.recipients)
        self.smtp.sendmail(self.sender, self.recipients, msg.as_string())

    def archive_comment(self, submission, instruction):
        """Archives the fact that CannedPostResponder has responded to a 
        submission."""
        subject = "[archive] %s: %s" % (str(datetime.now()), submission.title)
        message = ("A match was found for the following post:\n"
                   "\tPermalink:\n%s\n"
                   "\tPattern:\n%s\n"
                   "\tResponse:\n%s\n"
                   "\tTitle:\n%s\n"
                   "\tBody:\n%s" % (submission.permalink,
                                     instruction.re_string, 
                                     instruction.filename, 
                                     submission.title, 
                                     submission.selftext))
        return self.send_email(subject, message)

    def forward_message(self, msg):
        """When CannedPostResponder receives replies or messages, this function
        forwards them to the appropriate email address."""
        if msg.was_comment:
            link = "http://www.reddit.com" + msg.context
            link = link[:link.index('?')]
            subject = "[comment] %s replies in %s" % (msg.author, msg.link_title)
            message = ("\tUser:\n%s\n"
                       "\tThread:\n%s\n"
                       "\tLink:\n%s\n"
                       "\tBody:\n%s\n") % (msg.author,
                                          msg.link_title,
                                          link,
                                          msg.body)
                       
        else:
            subject = "[message] from %s: %s" % (msg.author, msg.subject)
            message = ("\tUser:\n%s\n"
                       "\tBody:\n%s\n") % (msg.author,
                                           msg.body)
        return self.send_email(subject, message)

def get_settings(settings):
    """Reads the CannedPostResponder settings file (setting.txt) and converts
    its contents into a dictionary."""
    try:
        fp = open(settings, "r")
    except:
        logging.error("Settings file %s nonexistent or unreadable." % 
                      (settings))
        raise FatalError.fileError
    settings = eval(fp.read())
    return settings

def store_settings(settings_file, settings):
    """Stores the CannedPostResponder settings to the settings file."""
    fp = open(settings_file, "w")
    fp.write(str(settings))

class Instruction_Parser:
    def __init__(self, instructions):
        self.instructions = instructions
        try:
            self.fp = open(instructions, "r")
        except:
            logging.error("Instructions file %s unreadable or nonexistent" % 
                          (instructions))
        self.unescaped_qm = re.compile("(?<!\\\\)'")
        self.tok_stream = tokenize.generate_tokens(self.fp.readline)

    def __iter__(self):
        return self

    def next(self):
        openers = ['(', '[', '{']
        closers = [')', ']', '}']
        state = "begin"
        regex, flags, filename = [None] * 3
        can_comma = False
        while state != "return":
            tok = next(self.tok_stream)
            if tok[0] == tokenize.COMMENT:
                # comments are accepted and ignored in any state
                continue
            if tok[0] == token.INDENT or \
                    tok[0] == token.DEDENT or \
                    (tok[0] == token.NEWLINE and state != "newline"):
                # a little tortured but avoids greater lack of clarity
                # and a lot of typing below
                continue
            if state == "begin":
                if tok[0] == token.STRING:
                    regex = tok[1]
                    can_comma = True
                    state = "flagxorfile"
                elif tok[1] in openers:
                    endpiece = closers[openers.index(tok[1])]
                    assemblage = tok[1]
                    state = "assemble"
                    whogets = "regex"
                elif tok[0] in [tokenize.NL, token.INDENT]:
                    pass
                elif tok[0] == token.ENDMARKER:
                    state = "return"
                else:
                    dfa_barf(tok, self.instructions, "instructions")
            elif state == "flagxorfile":
                if tok[0] == token.STRING:
                    filename = tok[1]
                    state = "newline"
                elif tok[1] in openers:
                    endpiece = closers[openers.index(tok[1])]
                    assemblage = tok[1]
                    state = "assemble"
                    whogets = "filename"
                elif tok[0] == token.NAME:
                    flags = tok[1]
                    state = "flag"
                elif tok[1] == "," and can_comma:
                    can_comma = False
                else:
                    dfa_barf(tok, self.instructions, "instructions")
            elif state == "flag":
                if tok[1] == ".":
                    flags += tok[1]
                    state = "moreflag"
                elif tok[1] == "|":
                    flags += tok[1]
                    state = "moreflag"
                elif tok[0] == token.STRING:
                    filename = tok[1]
                    state = "newline"
                elif tok[1] in openers:
                    endpiece = closers[openers.index(tok[1])]
                    assemblage = tok[1]
                    state = "assemble"
                    whogets = "filename"
                elif tok[1] == ",":
                    state = "filename"
                else:
                    dfa_barf(tok, self.instructions, "instructions")
            elif state == "moreflag":
                if tok[0] == token.NAME:
                    flags += tok[1]
                    state = "flag"
                else:
                    dfa_barf(tok, self.instructions, "instructions")
            elif state == "assemble":
                if tok[0] == token.STRING:
                    assemblage += tok[1]
                elif tok[0] in [tokenize.NL, token.INDENT]:
                    continue
                elif tok[1] == endpiece:
                    assemblage = eval(assemblage + tok[1])
                    assemblage = self.unescaped_qm.sub("\\'", assemblage)
                    assemblage = "'" + assemblage + "'"
                    if whogets == "regex":
                        regex = assemblage
                        can_comma = True
                        state = "flagxorfile"
                    elif whogets == "filename":
                        filename = assemblage
                        state = "newline"
                    else:
                        logging.error("Nothing to do with assembled string '%'" %
                            assemblage)
                        sys.exit(1)
                    pass
                else:
                    dfa_barf(tok, self.instructions, "instructions")
            elif state == "filename":
                if tok[0] == token.STRING:
                    filename = tok[1]
                    state = "newline"
                elif tok[1] in openers:
                    endpiece = closers[openers.index(tok[1])]
                    assemblage = tok[1]
                    state = "assemble"
                    whogets = "filename"
                else:
                    dfa_barf(tok, self.instructions, "instructions")
            elif state == "newline":
                if tok[0] == token.NEWLINE:
                    state = "return"
                else:
                    dfa_barf(tok, self.instructions, "instructions")
        if not any([regex, flags, filename]):
            raise StopIteration
        return regex, flags, filename

    def __del__(self):
        self.fp.close()
