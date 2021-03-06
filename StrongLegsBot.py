"""
Copyright 2016 Pawel Bartusiak

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

    http://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License.
"""

import logging
import logging.handlers
import os
import time
import socket
import sqlite3 as sql
import sys

import default_commands
from default_commands.constants import ConfigDefaults
import _functions
import _reloadbot
import unpackconfig

cfg = unpackconfig.configUnpacker()
sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)


class IRC:
    def __init__(self):
        # Initializes all class variables
        self.config = cfg.unpackcfg()
        self.CHANNEL = sys.argv[1] if len(sys.argv) > 1 else "#floppydisk_"
        self.USERNAME = self.config['settings_username']
        self.PASSWORD = self.config['settings_password']
        self.HOST = self.config['settings_host']
        self.PORT = int(self.config['settings_port'])

        self.privmsg_str = u"PRIVMSG {channel} :".format(channel=self.CHANNEL)
        self.custom = False
        self.silence = False

        if os.path.isfile('debug.txt'):
            fileread = open('debug.txt', 'r')
            self.custom = fileread.readline().strip("\n")
            self.silence = fileread.readline().strip("\n")

    def init(self):
        try:
            sock.connect((self.HOST, self.PORT))
            sock.settimeout(0.01)
            self.send_raw('CAP REQ :twitch.tv/membership\r\n')
            self.send_raw('CAP REQ :twitch.tv/tags\r\n')
            self.send_raw('CAP REQ :twitch.tv/commands\r\n')
            self.send_raw('PASS %s\r\n' % self.PASSWORD)
            self.send_raw('NICK %s\r\n' % self.USERNAME)
            self.send_raw('JOIN %s\r\n' % self.CHANNEL)
        except Exception as ERR_exception:
            log.critical(ERR_exception)

    # Send raw message to Twitch
    def send_raw(self, output):
        try:
            sock.send(output.format(channel=self.CHANNEL).encode("UTF-8"))
        except UnicodeEncodeError as UnicodeErr:
            self.send_whisper(":: ".join(["Unicode Error in send_raw", str(UnicodeErr)]),
                              "floppydisk_")

    def send_privmsg(self, output, me=False):
        if not self.silence:
            try:
                me = '/me : ' if me else ''
                custom = self.custom if self.custom else ''
                formatted_output = u"%s%s{output}\r\n"\
                                   .format(output=output) % (me, custom)

                self.send_raw(self.privmsg_str + formatted_output)
                log.info("[PRIVMSG] :| [SENT] %s: %s", self.CHANNEL, formatted_output.strip("\r\n"))

            except UnicodeEncodeError as UnicodeErr:
                self.send_whisper(":: ".join(["Unicode Error in send_privmsg", str(UnicodeErr)]),
                                  "floppydisk_")

    def send_timeout(self, output, target, duration):
        if not self.silence:
            try:
                custom = self.custom if self.custom else ''
                self.send_raw(self.privmsg_str + u'.timeout {target} {duration} %s{reason}\r\n'
                              .format(target=target,
                                      duration=duration,
                                      reason=output)) % custom

            except UnicodeEncodeError as UnicodeErr:
                self.send_whisper(":: ".join(["Unicode Error in send_timeout", str(UnicodeErr)]),
                                  "floppydisk_")

    def send_ban(self, output, target):
        if not self.silence:
            try:
                custom = self.custom if self.custom else ''
                self.send_raw(self.privmsg_str + u'.ban {target} %s{reason}\r\n'
                              .format(target=target,
                                      reason=output)) % custom

            except UnicodeEncodeError as UnicodeErr:
                self.send_whisper(":: ".join(["Unicode Error in send_ban", str(UnicodeErr)]),
                                  "floppydisk_")

    def send_whisper(self, output, target):
        if not self.silence:
            try:
                custom = self.custom if self.custom else ''
                formatted_output = u".w {target} %s{output}\r\n"\
                                   .format(target=target, output=output) % custom
                self.send_raw(self.privmsg_str + formatted_output)
                log.info("[WHISPER] :| [SENT] %s: %s" % (self.CHANNEL, formatted_output.strip("\r\n")))

            except UnicodeEncodeError as UnicodeErr:
                self.send_whisper(u":: ".join(["Unicode Error in send_whisper", str(UnicodeErr)]),
                                  "floppydisk_")


# Class housing main loop for SLB
class Bot:
    def __init__(self):
        sock.settimeout(0.01)
        self.data = "."
        self.databuffer = ''
        self.temp = ''
        self.currentdatetime = 0
        self.currentdatetimelist = []
        self.olddatetime = 0
        self.olddatetimelist = []
        self.startmarkloop = 0
        self.endmarkloop = 0
        self.previous_line = None
        self.mainloopbreak = False

        self.logFile = None
        self.logFileFormat = None
        self.logDate = None
        self.chatLogFile = None

        self.sqlConnectionChannel = None
        self.sqlCursorChannel = None
        self.sqlconn = None

        self.configdefaults = None

        self.ignoredusersfile = None
        self.ignoredusersread = None
        self.ignoredusers = None

        self.birthdayusers = {}

    def init(self):
        self.currentdatetime = time.gmtime(time.time())
        self.olddatetime = time.gmtime(time.time())
        self.ignoredusersfile = open('ignoredusers.txt', 'r')
        self.ignoredusersread = self.ignoredusersfile.readlines()
        self.ignoredusers = [username.strip('\n').strip('\r') for username in self.ignoredusersread]

        if not os.path.exists("/".join([os.getcwd(), "logs", irc.CHANNEL, "chat"])):
            os.makedirs("/".join([os.getcwd(), "logs", irc.CHANNEL, "chat"]))

        if not os.path.exists("/".join([os.getcwd(), "logs", irc.CHANNEL, "raw"])):
            os.makedirs("/".join([os.getcwd(), "logs", irc.CHANNEL, "raw"]))

        self.logFileFormat = logging.Formatter("<%(asctime)s> %(message)s")
        self.logFile = logging.FileHandler(encoding="utf-8", filename="/".join([os.getcwd(), "logs",
                                                                               irc.CHANNEL, "raw",
                                                                               "{}_rawlog.log".format(
                                                                                   time.strftime("%Y-%m-%d"))]))
        self.logFile.setFormatter(self.logFileFormat)
        self.logFile.setLevel(logging.INFO)
        log.addHandler(self.logFile)

        if sys.platform == "linux2":
            self.sqlConnectionChannel = sql.connect('SLB.sqlDatabase/{}DB.db'
                                                    .format(IRC().CHANNEL.strip("#")))
        else:
            self.sqlConnectionChannel = sql.connect(os.path.dirname(os.path.abspath(__file__)) +
                                                    '\SLB.sqlDatabase\{}DB.db'
                                                    .format(IRC().CHANNEL.strip("#").strip("\n")))

        self.sqlCursorChannel = self.sqlConnectionChannel.cursor()
        self.sqlconn = (self.sqlConnectionChannel, self.sqlCursorChannel)

        self.sqlCursorChannel.execute(
            'CREATE TABLE IF NOT EXISTS birthdays(userid TEXT, username TEXT, displayname TEXT, date TEXT)'
        )
        self.sqlCursorChannel.execute(
            'CREATE TABLE IF NOT EXISTS commands(userlevel INTEGER, keyword TEXT, output TEXT, args INTEGER, '
            'sendtype TEXT, syntaxerr TEXT)'
        )
        self.sqlCursorChannel.execute(
            'CREATE TABLE IF NOT EXISTS config(grouping TEXT, variable TEXT, value TEXT, args TEXT, userlevel INTEGER)'
        )
        self.sqlCursorChannel.execute(
            'CREATE TABLE IF NOT EXISTS faq(userlevel INTEGER, name TEXT, regex TEXT, output TEXT, sendtype TEXT)'
        )
        self.sqlCursorChannel.execute(
            'CREATE TABLE IF NOT EXISTS regulars(userid INTEGER, username TEXT)'
        )

        self.sqlConnectionChannel.commit()

        ConfigDefaults(self.sqlconn).all_(2)

        self.configdefaults = ConfigDefaults(self.sqlconn)

        for command in default_commands.dispatch_naming.keys():
            if command == "config":
                continue
            commandkeyword = self.sqlCursorChannel.execute(
                "SELECT value FROM config WHERE grouping=? AND variable=?", (command, "keyword")
            ).fetchone()[0]
            default_commands.dispatch_naming[command] = commandkeyword

        self.olddatetimelist = [int(self.olddatetime[index]) for index in range(0, 6)]
        self.currentdatetimelist = [int(self.currentdatetime[index]) for index in range(0, 6)]

        self.birthdayusers = default_commands.birthdays.getbirthdayusers(self.sqlconn,
                                                                         self.configdefaults,
                                                                         self.currentdatetimelist)

        return

    def main(self):
        while not self.mainloopbreak:
            try:
                try:
                    # Attempts a data grab from twitch
                    self.data = sock.recv(1024).decode("UTF-8")
                    self.databuffer = self.databuffer + self.data  # Appends data received to buffer
                    self.temp = self.databuffer.rsplit('\n')  # Splits buffer into list
                    self.databuffer = self.temp.pop()  # Grabs the last list item and assigns to buffer

                except socket.timeout:
                    self.temp = []  # Makes empty list if socket returns None

                # Checks if socket conn closed, then restarts
                if len(self.data) == 0:
                    _funcdiagnose.bot_restart("Lost connection with Twitch IRC server", user_loggingchoice)

                self.logDate = time.strftime("%Y-%m-%d")
                if sys.platform == "linux2":
                    self.chatLogFile = open('logs/{channel}/chat/{logDate}_log.log'
                                            .format(channel=irc.CHANNEL, logDate=self.logDate),
                                            'a+')
                else:
                    self.chatLogFile = open('logs/{channel}/chat/{logDate}_log.log'
                                            .format(channel=irc.CHANNEL, logDate=self.logDate),
                                            'a+', encoding="utf-8")

                # Captures current time for response time measuring
                if self.temp:
                    self.olddatetime = self.currentdatetime
                    self.olddatetimelist = list(map(int, self.olddatetime))
                    self.currentdatetime = time.gmtime(time.time())
                    self.currentdatetimelist = list(map(int, self.currentdatetime))

                    self.startmarkloop = time.time()
                    log.debug("START MARK")

                    if self.currentdatetimelist[2] - self.olddatetimelist[2]:
                        log.removeHandler(self.logFile)
                        self.logFile = logging.FileHandler(filename="/".join([os.getcwd(), "logs",
                                                                              irc.CHANNEL, "raw",
                                                                              "{}_rawlog.log".format(
                                                                                  time.strftime("%Y-%m-%d"))]))
                        log.addHandler(self.logFile)

                        self.birthdayusers = default_commands.birthdays.getbirthdayusers(self.sqlconn,
                                                                                         self.configdefaults,
                                                                                         self.currentdatetimelist)
                        log.info("[_BOTCOM] :| [CVAR] {channel}: Birthday users: %s".format(channel=irc.CHANNEL) % list(self.birthdayusers.keys()))

                else:
                    continue

                # Loop for dealing with each item separately
                for line in self.temp:
                    log.debug(repr(line))

                    # Parse and extract data from line and display formatted string
                    parsetype, identifier, info, display, parsed = _functions.Parse(irc, self.sqlconn, line).parse()

                    if display:
                        log.info("[%s] :| %s", parsetype.upper(), parsed)

                    if "username" in list(info.keys()) and info["username"] in self.ignoredusers:
                        if identifier == "privmsg":
                            try:
                                temp_log_output = "<%02d:%02d:%02d> {---} [%s]: %s\n" % (
                                    self.currentdatetimelist[3], self.currentdatetimelist[4],
                                    self.currentdatetimelist[5], info["username"], info["privmsg"])

                                self.chatLogFile.write(temp_log_output)
                            except UnicodeEncodeError as e:
                                log.exception(str(e))

                        continue

                    if identifier == "366":
                        log.info("[_BOTCOM] :| [JOIN] Joined %s Successfully..." % irc.CHANNEL)

                    # Find and deal with periodic ping request (approx. every 5 minutes,
                    # socket disconnect after 11 minutes)
                    if identifier == "PING":
                        pingstring = info["pingstring"]
                        pingstring = pingstring.replace(":", "").strip("\r")
                        irc.send_raw("PONG%s\r\n" % pingstring)

                    if identifier == "JOIN":
                        default_commands.birthdays.joinevent(irc, self.configdefaults,
                                                             self.birthdayusers, info["username"])

                    if identifier == "PART":
                        pass

                    # Find and deal with user chat messages, majority of activity occurs here
                    if identifier == "privmsg":
                        handleuserlevel = (info["user-id"], info["username"], info["user-type"],
                                           info["subscriber"], info["turbo"])

                        # Determines user's status as an integer
                        #   0 - Normal users
                        #  50 - Turbo
                        # 100 - Subscribers
                        # 150 - Regulars
                        # 250 - Moderators
                        # 350 - Global Moderators
                        # 400 - Broadcaster
                        # 500 - Admin
                        # 600 - Staff
                        # 700 - FloppyDisk_

                        userlevel = _funcdata.handleUserLevel(handleuserlevel)
                        info["userlevel"] = userlevel

                        try:
                            temp_log_output = "<%02d:%02d:%02d> {%s} [%s]: %s\n" % (
                                self.currentdatetimelist[3], self.currentdatetimelist[4],
                                self.currentdatetimelist[5], info["userlevel"],
                                info["username"], info["privmsg"])

                            self.chatLogFile.write(temp_log_output)
                        except UnicodeEncodeError as e:
                            log.exception(str(e))

                        # Passes user through filters if permission level is under 250
                        # if userlevel < 250:
                        #     if filters.filters(irc, self.sqlconn, info).linkprotection():
                        #         continue  # If one of the filters return True, the user is omitted

                        # -=-=-=-=-=-=-= Non-restricted users past this point =-=-=-=-=-=-=-

                        default_commands.commands.customCommands(bot, irc, self.sqlconn, info)

                        if info["userlevel"] >= 700 and info["privmsg"].startswith("$forcerestart"):
                            _funcdiagnose.bot_restart("Forced restart by bot admin", user_loggingchoice)

                    # Find and deal with whispers
                    if identifier == "whisper":
                        if irc.CHANNEL in info['privmsg']:
                            log.info("[%s] :| %s", parsetype.upper(), parsed)

                        handleuserlevel = (info["user-id"], info["username"], info["user-type"],
                                           0, info["turbo"])
                        userlevel = _funcdata.handleUserLevel(handleuserlevel, True)
                        info["userlevel"] = userlevel

                        temp_split_message = info["privmsg"].split(" ")
                        if info["username"] == 'floppydisk_':
                            if temp_split_message[0] == '!reload':
                                log.warning("IMPORTANT: Reloading app resources")
                                try:
                                    _reloadbot.reloadall()
                                except Exception as e:
                                    log.error(e)

                            if temp_split_message[0] == '$forcerestart':
                                if len(temp_split_message) == 2:
                                    if temp_split_message[1] in ('all', irc.CHANNEL):
                                        _funcdiagnose.bot_restart("Forced restart by admin", user_loggingchoice)
                                elif len(temp_split_message) > 2:
                                    if temp_split_message[1] in ('all', irc.CHANNEL):
                                        if temp_split_message[2] in ('/me', '.me'):
                                            irc.send_privmsg(" ".join(temp_split_message[3:]), True)
                                        else:
                                            irc.send_privmsg(" ".join(temp_split_message[2:]))

                                        _funcdiagnose.bot_restart("Forced restart by admin", user_loggingchoice)

                            if temp_split_message[0] == '$stop':
                                if len(temp_split_message) == 2:
                                    if temp_split_message[1] in ('all', irc.CHANNEL):
                                        self.mainloopbreak = True

                                elif len(temp_split_message) > 2:
                                    if temp_split_message[1] in ('all', irc.CHANNEL):
                                        if temp_split_message[2] in ('/me', '.me'):
                                            irc.send_privmsg(" ".join(temp_split_message[3:]), True)
                                        else:
                                            irc.send_privmsg(" ".join(temp_split_message[2:]))

                                        self.mainloopbreak = True

                            if temp_split_message[0] == '$send' and userlevel >= 400:
                                if len(temp_split_message) <= 2:
                                    irc.send_whisper("Error: Not enough arguments.", info["username"])

                                if len(temp_split_message) > 2:
                                    if temp_split_message[1] == irc.CHANNEL or \
                                            (temp_split_message[1] == 'all' and userlevel >= 700):
                                        if temp_split_message[2] in ('/me', '.me'):
                                            irc.send_privmsg(" ".join(temp_split_message[3:]), True)
                                        else:
                                            irc.send_privmsg(" ".join(temp_split_message[2:]))

                        if temp_split_message[0] == irc.CHANNEL:
                            default_commands.commands.customCommands(bot, irc, self.sqlconn, info,
                                                                     " ".join(temp_split_message[1:]), True)

                    if self.temp.index(line) == len(self.temp) - 1:
                        self.endmarkloop = time.time()
                        log.debug("END MARK: Dealt with data chunk in %s milliseconds." %
                                  ((self.endmarkloop - self.startmarkloop) * 1000))

            except KeyboardInterrupt:
                log.critical('Process Interrupted by KeyboardInterrupt')
                self.mainloopbreak = True


if __name__ == '__main__':
    logging_levels = {'debug': logging.DEBUG, 'info': logging.INFO,
                      'warning': logging.WARNING, 'error': logging.ERROR,
                      'critical': logging.CRITICAL}

    # Set logging level based on sys.argv or set to default if none given
    if len(sys.argv) == 3:
        user_loggingchoice = sys.argv[2]
    else:
        user_loggingchoice = ""

    if user_loggingchoice.lower() not in logging_levels:  # If user entered a logging level that is incorrect
        logging_level = logging.INFO
    else:
        logging_level = logging_levels[user_loggingchoice]

    # Set logging formatting default
    logging.basicConfig(format='<%(asctime)s> %(filename)s:%(levelname)s:%(lineno)s: %(message)s')
    log = logging.getLogger("StrongLegsBot")
    log.setLevel(logging_level)

    # logStreamFormat = logging.Formatter('<%(asctime)s> %(filename)s:%(levelname)s:%(lineno)s: %(message)s')
    # logStream = logging.StreamHandler(stream=sys.stdout)
    # logStream.setFormatter(logStreamFormat)
    # logStream.setLevel(logging_level)
    # log.addHandler(logStream)

    # Create instances of each class in StrongLegsBot and initialize IRC conn
    irc = IRC()
    irc.init()
    bot = Bot()
    bot.init()

    # Shorten function calls and create instance
    _funcdiagnose = _functions.Diagnostic(irc, bot.sqlconn)
    _funcdata = _functions.Data(irc, bot.sqlconn)

    bot.main()
    log.critical("Bot running in channel %s stopped." % irc.CHANNEL)
    sys.exit()
