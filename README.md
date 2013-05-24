CannedPostResponder is a Reddit bot.  It's purpose is to scan Reddit for top level posts about a certain topic and then posts a pre-written response when it finds a match.  Matching is done using regular expressions.

You invoke and control CannedPostResponder using a script called cpr_admin.py.  For an overview of the flags and functionality of cpr_admin.py you can display the help page for that script by running the command

    ./cpr_admin.py --help

For more information about using CannedPostResponder, read the file manual.txt included in CannedPostResponder's home directory or you can view a more nicely formatted copy of the same document [online](www.nonbird.com/rbb_article/manual.html).

Included in this directory is a helper script called install_cpr.py.  This script will check your system to make sure it contains all the modules that CannedPostResponder needs to run.  If anything is missing, it will let you know.  If everything is in order, it will create a wrapper script for cpr_admin.py.  You can then place this script wherever is convenient within your filepath.  cpr_admin.py must be in the same directory as all the other files associated with CannedPostResponder, so this wrapper script should make using CannedPostResponder much more convenient.

This program and all its associated documentation copyright Charlie Pashayan in 2013.