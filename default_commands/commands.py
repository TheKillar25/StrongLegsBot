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
import re

from .constants import ConfigDefaults, boolean
import default_commands
from default_commands._exceptions import *


class commands:
    def __init__(self, bot, irc, sqlconn, info, userlevel=0, whisper=False):
        self.local_dispatch_map = {'add': self.add, 'edit': self.edit,
                                   'delete': self.delete, "del": self.delete,
                                   'help': self.help, '': self.disp_commands}
        self.bot = bot
        self.irc = irc
        self.sqlConnectionChannel, self.sqlCursorChannel = sqlconn
        self.info = info
        self.message = info["privmsg"]
        self.userlevel = userlevel
        self.whisper = whisper
        self.sqlVariableString = "SELECT value FROM config WHERE grouping=? AND variable=?"

        self.configdefaults = ConfigDefaults(sqlconn)

        self.enabled = boolean(self.configdefaults.sqlExecute(
            self.sqlVariableString, ("commands", "enabled")).fetchone()[0])

        self.commandkeyword = self.configdefaults.sqlExecute(
            self.sqlVariableString, ("commands", "keyword")).fetchone()[0]
        default_commands.dispatch_naming["commands"] = self.commandkeyword

        if not self.enabled:
            return

        self.min_userlevel = int(self.configdefaults.sqlExecute(
            self.sqlVariableString, ("commands", "min_userlevel")).fetchone()[0])
        self.min_userlevel_edit = int(self.configdefaults.sqlExecute(
            self.sqlVariableString, ("commands", "min_userlevel_edit")).fetchone()[0])

    def chat_access(self):
        temp_split = self.message.split(' ')
        if self.userlevel >= self.min_userlevel:
            if len(temp_split) > 1:
                if temp_split[1] == 'help':
                    self.help()
                elif temp_split[1] == 'page':
                    pass
                elif self.userlevel >= self.min_userlevel_edit:
                    if temp_split[1] in list(self.local_dispatch_map.keys()):
                        self.local_dispatch_map[temp_split[1]]()
                    else:
                        self.irc.send_privmsg("Error: '%s' is not a valid command variation." % temp_split[1])
                        return
                else:
                    self.irc.send_privmsg('Error: You are not allowed to use any variations of {command}.'
                                          .format(command=default_commands.dispatch_naming['commands']))
                    return
            else:
                self.disp_commands()

    def disp_commands(self):
        self.sqlCursorChannel.execute('SELECT userlevel FROM commands')

        sqlCursorOffload = self.sqlCursorChannel.fetchall()

        if not sqlCursorOffload:
            self.irc.send_privmsg(': Error: Channel %s has no custom commands.' % self.irc.CHANNEL, True)
            return

        self.sqlCursorChannel.execute('SELECT * FROM commands WHERE userlevel <= ?', (self.userlevel,))

        sqlCursorOffload = self.sqlCursorChannel.fetchall()

        command_dict = {}
        command_string = ''

        for entry in sqlCursorOffload:
            if entry[0] not in list(command_dict.keys()):
                command_dict[entry[0]] = []

            command_dict[entry[0]].append(entry[1])

        if not sqlCursorOffload:
            self.irc.send_whisper("Error: Channel '%s' has no commands available for use with your current userlevel "
                                  "(%s)" % (self.irc.CHANNEL, self.userlevel), self.info['username'])
            return

        for key in sorted(list(command_dict.keys()), reverse=True):
            command_string += ("%s: %s | " % (key, ", ".join(sorted(command_dict[key]))))

        whisper_string = 'Custom commands in channel %s, available with your userlevel (%s), are: %s'\
                         % (self.irc.CHANNEL, self.userlevel, command_string.strip(" | "))

        self.irc.send_whisper(whisper_string, self.info['username'])
        return

    def page(self):
        pass

    def help(self):
        parameters = self.message.split("help", 1)
        if len(parameters[1]) <= 0:
            command_keyword = default_commands.dispatch_naming['commands']
            if command_keyword not in default_commands.help_defaults:
                self.irc.send_privmsg("Error: '%s' is not a valid command variation." % command_keyword)
                return

            command_help = default_commands.help_defaults[command_keyword][''].format(command=command_keyword)
            self.irc.send_privmsg(('%s help -> ' + command_help) % command_keyword, True)
            return

        parameters = parameters[1].strip()
        split_params = parameters.split(" ")
        command_keyword = split_params[0].strip()
        command_variant = split_params[1].strip() if len(split_params) == 2 else ''

        try:
            if command_keyword in default_commands.dispatch_map:
                command_help = default_commands.help_defaults[command_keyword][command_variant] \
                    .format(command=command_keyword)
                self.irc.send_privmsg(('%s %s -> ' + command_help) % (command_keyword, command_variant), True)
            else:
                self.irc.send_privmsg("Error: '%s' is not a valid command." % command_keyword)
                return
        except KeyError:
            self.irc.send_privmsg("Error: '%s' is not a valid command variation of '%s'."
                                  % (command_variant, command_keyword))
            return

    def add(self):
        try:
            parameters = self.message.split("add", 1)
            if len(parameters[1]) <= 0:
                raise DCIncorrectAmountArgsError

            parameters = parameters[1].strip()
            split_params = parameters.split(" ")
            command_offset = 0
            command_userlevel = 0
            command_sendmode = "privmsg"
            userlevel_specified = False
            sendmode_specified = False

            for split_pos in range(len(split_params)):
                if userlevel_specified and sendmode_specified:
                    break

                if userlevel_specified:
                    pass
                elif split_params[split_pos].startswith("-ul="):
                    command_offset += 1
                    temp_split_parms = split_params[split_pos].split("=", 1)
                    if temp_split_parms[1] != '':
                        if 0 <= int(temp_split_parms[1]) <= 700:
                            command_userlevel = temp_split_parms[1]
                            userlevel_specified = True
                        else:
                            self.irc.send_privmsg("Error: Invalid userlevel, must be 0 <= userlevel <= 700.")
                            return
                    else:
                        self.irc.send_privmsg("Error: Userlevel cannot be nil.")
                        return
                else:
                    command_userlevel = 0

                if sendmode_specified:
                    pass
                elif split_params[split_pos].startswith("-sm=") and self.info["userlevel"] >= 400:
                    temp_split_parms = split_params[split_pos].split("=", 1)
                    command_offset += 1
                    if temp_split_parms[1] != '':
                        if temp_split_parms[1] in ("privmsg", "whisper"):
                            command_sendmode = temp_split_parms[1]
                            sendmode_specified = True
                        else:
                            self.irc.send_privmsg("Error: Invalid sendtype, must be 'privmsg' or 'whisper'.")
                            return
                    else:
                        self.irc.send_privmsg("Error: Sendmode cannot be nil.")
                        return

                elif split_params[split_pos].startswith("-sm=") and self.info["userlevel"] < 400:
                    self.irc.send_privmsg("Permissions Error: You don't have the permissions to specify command "
                                          "sendmode.")

                else:
                    command_sendmode = "privmsg"

            command_keyword = split_params[command_offset]

            if command_keyword in default_commands.dispatch_map:
                self.irc.send_privmsg("Error: Command keyword must not shadow a default command.")
                return

            command_output = " ".join(split_params[(command_offset + 1):])

            self.sqlCursorChannel.execute('SELECT keyword FROM commands WHERE keyword == ?',
                                          (command_keyword,))
            sqlCursorOffload = self.sqlCursorChannel.fetchone()
            if sqlCursorOffload is not None:
                self.irc.send_privmsg("Error: Command with keyword '%s' already exists." % command_keyword)
                return

            command_args = 0
            for x in range(3):
                for word in command_output.split(" "):
                    if "{arg%d}" % (x + 1) in word:
                        command_args += 1
                        break

            syntaxerr = "Error: Unexpected error occurred."

            if command_args > 0:
                syntaxerr = "Syntax Error: %s" % command_keyword
                for x in range(command_args):
                    syntaxerr += " <arg%d>" % (x + 1)

            self.sqlCursorChannel.execute(
                'INSERT INTO commands (userlevel, keyword, output, args, sendtype, syntaxerr) '
                'VALUES (?, ?, ?, ?, ?, ?)', (command_userlevel, command_keyword, command_output,
                                              command_args, command_sendmode, syntaxerr)
            )
            self.sqlConnectionChannel.commit()

            self.irc.send_privmsg("Added '%s' successfully." % command_keyword)
            return

        except DCIncorrectAmountArgsError:
            logging.warning("No arguments found")
            self.irc.send_privmsg("Error: Incorrect amount of arguments given.")

        except DCSyntaxError:
            pass

        except IndexError:
            self.irc.send_privmsg("Error: Incorrect amount of arguments given.")
            return

        except Exception as e:
            self.irc.send_whisper("%s Add Command Error: %s" % (self.irc.CHANNEL, str(e)), "floppydisk_")
            return

    def edit(self):
        parameters = self.message.split("edit", 1)
        if len(parameters[1]) <= 0:
            logging.warning("No arguments found")
            self.irc.send_privmsg("Error: Incorrect amount of arguments given.")
            return
        try:
            parameters = parameters[1].strip()
            split_params = parameters.split(" ")
            command_output = ""
            command_args = 0
            command_syntaxerr = "Error: Unexpected error occurred"
            command_offset = 0
            command_userlevel = 0
            command_sendmode = "privmsg"
            output_specified = False
            userlevel_specified = False
            sendmode_specified = False

            command_keyword = split_params[0]
            if len(split_params) <= 1:
                self.irc.send_privmsg("Error: Edit command must have at least 1 edit parameter "
                                      "(type \"{command} help {command} edit\" for information."
                                      .format(command=default_commands.dispatch_naming["commands"]))
                return

            self.sqlCursorChannel.execute('SELECT * FROM commands WHERE keyword == ?',
                                          (command_keyword,))

            sqlCursorOffload = self.sqlCursorChannel.fetchone()

            if sqlCursorOffload is None:
                self.irc.send_privmsg("Error: Command with keyword '%s' does not exist" % command_keyword)
                return

            if "-output=" in parameters:
                regex_output = '-output=(.*\")'
                regex_output = re.search(regex_output, parameters)
                if regex_output is not None:
                    if regex_output.group(1) == '' or regex_output.group(1) == '""'\
                            or re.match('"\s+"', regex_output.group(1)):

                        self.irc.send_privmsg("Error: Output must not be nil.")
                        return
                    elif regex_output.group(1) == '"' or (not regex_output.group(1).startswith('"')
                                                          or not regex_output.group(1).endswith('"')):
                        self.irc.send_privmsg("Error: Output must be surrounded with double-quotes.")
                        return
                    elif regex_output.group(1) != '':
                        command_output = regex_output.group(1).strip('"')
                        output_specified = True
                    else:
                        command_output = sqlCursorOffload[2]
                else:
                    self.irc.send_privmsg("Error: Output must not be nil.")
                    return

            for split_pos in range(len(split_params)):
                if userlevel_specified and sendmode_specified:
                    break

                if userlevel_specified:
                    pass
                elif split_params[split_pos].startswith("-ul="):
                    command_offset += 1
                    temp_split_parms = split_params[split_pos].split("=", 1)
                    if temp_split_parms[1] != '':
                        if 0 <= int(temp_split_parms[1]) <= 700:
                            command_userlevel = temp_split_parms[1]
                            userlevel_specified = True
                        else:
                            self.irc.send_privmsg("Error: Invalid userlevel, must be 0 <= userlevel <= 700.")
                            return
                    else:
                        self.irc.send_privmsg("Error: Userlevel cannot be nil.")
                        return
                else:
                    command_userlevel = 0

                if sendmode_specified:
                    pass

                elif split_params[split_pos].startswith("-sm=") and self.info["userlevel"] >= 400:
                    temp_split_parms = split_params[split_pos].split("=", 1)
                    command_offset += 1
                    if temp_split_parms[1] != '':
                        if temp_split_parms[1] in ("privmsg", "whisper"):
                            command_sendmode = temp_split_parms[1]
                            sendmode_specified = True
                        else:
                            self.irc.send_privmsg("Error: Invalid sendtype, must be 'privmsg' or 'whisper'.")
                            return
                    else:
                        self.irc.send_privmsg("Error: Sendmode cannot be nil.")
                        return

                elif split_params[split_pos].startswith("-sm=") and self.info["userlevel"] < 400:
                    self.irc.send_privmsg("Permissions Error: You don't have the permissions to specify command "
                                          "sendmode.")

                else:
                    command_sendmode = "privmsg"

            if not output_specified and sqlCursorOffload is not None:
                command_output = sqlCursorOffload[2]
                command_args = sqlCursorOffload[3]
                command_syntaxerr = sqlCursorOffload[5]

            elif output_specified:
                command_args = 0
                for x in range(3):
                    for word in command_output.split(" "):
                        if "{arg%d}" % (x + 1) in word:
                            command_args += 1
                            break

                if command_args > 0:
                    command_syntaxerr = "Syntax Error: %s" % command_keyword
                    for x in range(command_args):
                        command_syntaxerr += " <arg%d>" % (x + 1)
                else:
                    command_syntaxerr = "Error: Unexpected error occurred"

            else:
                self.irc.send_privmsg("Unexpected Error has ocurred.")
                logging.error("Edit command error.")
                return

            if not userlevel_specified and sqlCursorOffload is not None:
                command_userlevel = int(sqlCursorOffload[0])

            if not sendmode_specified and sqlCursorOffload is not None:
                command_sendmode = sqlCursorOffload[4]

            self.sqlCursorChannel.execute(
                'UPDATE commands SET userlevel = ?, output = ?, args = ?, sendtype = ?, syntaxerr = ? '
                'WHERE keyword = ?', (command_userlevel, command_output, command_args, command_sendmode,
                                      command_syntaxerr, command_keyword)
            )
            self.sqlConnectionChannel.commit()

            self.irc.send_privmsg("Edited '%s' successfully." % command_keyword)
            return

        except IndexError:
            self.irc.send_privmsg("Error: Incorrect amount of arguments given.")
            return

        except Exception as e:
            self.irc.send_whisper("%s Edit Command Error: %s" % (self.irc.CHANNEL, str(e)), "floppydisk_")
            return

    def delete(self):
        parameters = self.message.split("delete", 1)
        if len(parameters[1]) <= 0:
            logging.warning("No arguments found")
            self.irc.send_privmsg("Error: Incorrect amount of arguments given.")
            return
        try:
            parameters = parameters[1].strip()
            split_params = parameters.split(" ")
            command_keyword = split_params[0]

            self.sqlCursorChannel.execute('SELECT keyword FROM commands WHERE keyword == ?',
                                          (command_keyword,))
            sqlCursorOffload = self.sqlCursorChannel.fetchone()

            if sqlCursorOffload is None:
                self.irc.send_privmsg("Error: Command with keyword '%s' does not exist" % command_keyword)
                return
            else:
                self.sqlCursorChannel.execute(
                    'DELETE FROM commands WHERE keyword == ?',
                    (command_keyword,)
                )
                self.sqlConnectionChannel.commit()

            self.irc.send_privmsg("Deleted '%s' successfully." % command_keyword)
            return

        except IndexError:
            self.irc.send_privmsg("Error: Incorrect amount of arguments given.")
            return

        except Exception as e:
            self.irc.send_whisper("%s Delete Command Error: %s" % (self.irc.CHANNEL, str(e)), "floppydisk_")
            return


def customCommands(bot, irc, sqlconn, info, message=False, whisper=False):
    # Deal with variables/sql
    sqlConnectionChannel, sqlCursorChannel = sqlconn

    if message is False:
        message = info["privmsg"]
    else:
        message = message

    if whisper and message is not False:
        info["privmsg"] = message

    userlevel = info["userlevel"]
    info["help"] = list(info.keys())
    split_message = message.split(" ")
    info["arg1"] = "nil" if (len(split_message) - 1) < 1 else split_message[1]
    info["arg2"] = "nil" if (len(split_message) - 1) < 2 else split_message[2]
    info["arg3"] = "nil" if (len(split_message) - 1) < 3 else split_message[3]

    if whisper:
        sqlCursorChannel.execute('SELECT userlevel FROM userLevel WHERE username == ?', (info['username'],))
        temp_userlevel = sqlCursorChannel.fetchone()
        if temp_userlevel is not None:
            userlevel = temp_userlevel[0]
        else:
            userlevel = 0

    temp_message_split = message.split(" ", 1)
    if temp_message_split[0] in list(default_commands.dispatch_map.keys()):
        default_commands.dispatch_map[temp_message_split[0]](bot, irc, sqlconn, info,
                                                             userlevel=userlevel, whisper=whisper).chat_access()
        return

    sqlCursorChannel.execute('SELECT * FROM commands WHERE userlevel <= ?',
                             (userlevel,))
    sqlCursorOffload = sqlCursorChannel.fetchall()

    # For every command in DB
    for command in sqlCursorOffload:
        try:
            # Checks if user is indeed requesting that command and is above or equal to the required userlevel
            if split_message[0] == command[1] and userlevel >= command[0]:
                logging.debug("Command usage request acknowledged")
                # Check is amount of args given is equal to the required amount
                if (len(split_message) - 1) == command[3]:
                    # Tidies command varible
                    command_output = command[2]
                    command_sendtype = command[4]
                    me = False

                    if command_output.startswith('/me') or command_output.startswith('.me'):
                        me = True

                    # Checks for 1, 2 or 3 args
                    if command[3] == 1:
                        info["arg1"] = " ".join(split_message[1:])
                        command_output = str(command[2]).format(arg1=info['arg1'])
                    elif command[3] == 2:
                        info["arg2"] = " ".join(split_message[2:])
                        command_output = str(command[2]).format(arg1=info['arg1'],
                                                                arg2=info['arg2'])
                    elif command[3] == 3:
                        info["arg3"] = " ".join(split_message[3:])
                        command_output = str(command[2]).format(arg1=info['arg1'],
                                                                arg2=info['arg2'],
                                                                arg3=info['arg3'])

                    if command_sendtype == 'whisper' or whisper:
                        irc.send_whisper(command_output.format(**info), info['username'])
                        return
                    else:
                        irc.send_privmsg(command_output.format(**info), me)
                        return

                # Checks if args are required and given are above or below required
                elif command[3] > 0 and ((len(split_message) - 1) < command[3]
                                         or (len(split_message) - 1) > command[3]):
                    if not whisper:
                        irc.send_privmsg(command[5])
                    else:
                        irc.send_whisper(command[5], info['username'])

                return

        except KeyError as err_key:
            if not whisper:
                irc.send_privmsg(err_key)
            else:
                irc.send_whisper(err_key, info["username"])
            return

    return

