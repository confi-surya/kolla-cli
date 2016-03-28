# Copyright(c) 2016, Oracle and/or its affiliates.  All Rights Reserved.
#
#    Licensed under the Apache License, Version 2.0 (the "License"); you may
#    not use this file except in compliance with the License. You may obtain
#    a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
#    WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#    License for the specific language governing permissions and limitations
#    under the License.
import fcntl
import json
import logging
import os
import subprocess  # nosec
import tempfile
import time

import kollacli.i18n as u

from kollacli.common.inventory import remove_temp_inventory
from kollacli.common.utils import get_admin_uids
from kollacli.common.utils import safe_decode

LOG = logging.getLogger(__name__)

LINE_LENGTH = 80

PIPE_PREFIX = '.kolla_pipe_'

# action defs
ACTION_PLAY_START = 'play_start'
ACTION_TASK_START = 'task_start'
ACTION_TASK_END = 'task_end'
ACTION_INCLUDE_FILE = 'includefile'
ACTION_STATS = 'stats'


class AnsibleJob(object):
    """class for running ansible commands"""

    def __init__(self, cmd, deploy_id, print_output, inventory_path):
        self._command = cmd
        self._deploy_id = deploy_id
        self._print_output = print_output
        self._temp_inv_path = inventory_path

        self._fragment = ''
        self._is_first_packet = True
        self._fifo_path = os.path.join(
            tempfile.gettempdir(), '%s_%s' % (PIPE_PREFIX, self._deploy_id))
        self._fifo_fd = None
        self._process = None
        self._errors = []
        self._cmd_output = ''

    def run(self):
        try:
            # create and open named pipe, must be owned by kolla group
            os.mkfifo(self._fifo_path, 0o660)
            _, grp_id = get_admin_uids()
            os.chown(self._fifo_path, os.getuid(), grp_id)
            self._fifo_fd = os.open(self._fifo_path,
                                    os.O_RDONLY | os.O_NONBLOCK)

            self._process = subprocess.Popen(self._command,  # nosec
                                             shell=True,
                                             stdout=subprocess.PIPE,
                                             stderr=subprocess.PIPE)

            # setup stdout to be read without blocking
            flags = fcntl.fcntl(self._process.stdout, fcntl.F_GETFL)
            fcntl.fcntl(self._process.stdout, fcntl.F_SETFL,
                        (flags | os.O_NONBLOCK))
        except Exception as e:
            self._cleanup()
            raise e

    def wait(self):
        """wait for job to complete

        return status of job (see get_status for status values)
        """
        while True:
            status = self.get_status()
            if status is not None:
                break
            time.sleep(1)
        return status

    def get_status(self):
        """get process status

        status:
        - None: running
        - 0: done, success
        - 1: done, error
        """
        status = self._process.poll()
        self._read_from_callback()
        if status is not None:
            self._cleanup()
            status = 0
            if self._process.returncode != 0:
                status = 1
        try:
            out = safe_decode(self._process.stdout.read())
            if out:
                self._cmd_output = ''.join([self._cmd_output, out])
        except IOError:  # nosec
            # error can happen if stdout is empty
            pass
        return status

    def get_error_message(self):
        """"get error message"""
        msg = ''
        for error in self._errors:
            msg = ''.join([msg, error, '\n'])
        return msg

    def get_command_output(self):
        """get command output

        get final output text from command execution
        """
        return self._cmd_output

    def _log_lines(self, lines):
        if self._print_output:
            for line in lines:
                LOG.info(line)

    def _cleanup(self):
        # delete temp inventory file
        remove_temp_inventory(self._temp_inv_path)

        # close and delete the named pipe (fifo)
        if self._fifo_fd:
            try:
                os.close(self._fifo_fd)
            except OSError:  # nosec
                # fifo already closed
                pass
        if self._fifo_path and os.path.exists(self._fifo_path):
            os.remove(self._fifo_path)

    def _read_from_callback(self):
        """read lines from callback in real-time"""
        data = None
        try:
            data = os.read(self._fifo_fd, 1000000)
            data = safe_decode(data)
        except OSError:  # nosec
            # error can happen if fifo is empty
            pass
        if data:
            packets = self._deserialize_packets(data)
            for packet in packets:
                formatted_data = self._format_packet(packet)
                lines = formatted_data.split('\n')
                self._log_lines(lines)

    def _format_packet(self, packet):
        action = packet['action']
        if action == ACTION_INCLUDE_FILE:
            return self._format_include_file(packet)
        elif action == ACTION_PLAY_START:
            return self._format_play_start(packet)
        elif action == ACTION_STATS:
            return self._format_stats(packet)
        elif action == ACTION_TASK_END:
            return self._format_task_end(packet)
        elif action == ACTION_TASK_START:
            return self._format_task_start(packet)
        else:
            raise Exception(u._('Invalid action [{action}] from callback')
                            .format(action=action))

    def _format_include_file(self, packet):
        return 'included: %s' % packet['filename']

    def _format_play_start(self, packet):
        msg = '\n' + self._add_filler('PLAY ', LINE_LENGTH, '*')
        if self._is_first_packet:
            msg += '\nPlaybook: %s' % packet['playbook']
            self._is_first_packet = False
        return msg

    def _format_stats(self, packet):
        # each element is a dictionary with host as key
        msg = '\n' + self._add_filler('PLAY RECAP ', LINE_LENGTH, '*')
        processed = packet['processed']
        ok = packet['ok']
        changed = packet['changed']
        unreachable = packet['unreachable']
        failures = packet['failures']
        for host in processed:
            hostline = '\n%s' % self._add_filler(host, 28, ' ')
            hostline += (': ok=%s'
                         % self._add_filler('%s' % ok[host], 5, ' '))
            hostline += ('changed=%s'
                         % self._add_filler('%s' % changed[host], 5, ' '))
            hostline += ('unreachable=%s'
                         % self._add_filler('%s' % unreachable[host], 5, ' '))
            hostline += 'failed=%s' % failures[host]
            msg += hostline
        return msg

    def _format_task_end(self, packet):
        host = packet['host']
        status = packet['status']
        msg = '%s: [%s]' % (status, host)
        if status == 'failed' or status == 'unreachable':
            results_dict = packet['results']
            taskname = packet['task']['name']

            # update saved error messages
            self._errors.append(self._format_error(taskname, host,
                                                   status, results_dict))
            # format log message
            results = json.dumps(results_dict)
            msg = 'fatal: [%s]: %s! => %s' % (host, status.upper(), results)
        return msg

    def _format_task_start(self, packet):
        taskname = packet['name']
        task_line = 'TASK [%s] ' % taskname
        msg = '\n' + self._add_filler(task_line, LINE_LENGTH, '*')
        return msg

    def _format_error(self, taskname, host, status, results):
        err_msg = ''
        if 'msg' in results and results['msg']:
            err_msg = results['msg']
        msg = ('Host: %s, Task: %s, Status: %s, Message: %s' %
               (host, taskname, status, err_msg))
        return msg

    def _add_filler(self, msg, length, filler):
        num_stars = max(length - len(msg), 0)
        stars = num_stars * filler
        return msg + stars

    def _deserialize_packets(self, data):
        """get json packets from callback

        Packets are delimited by \n's. It's possible that a packet
        is cut in the middle, creating 2 fragments. Need to handle that.

        return list of dictionaries
        """
        packets = []
        has_fragment = True
        if data.endswith('\n'):
            has_fragment = False
        i = 0
        lines = data.split('\n')
        num_lines = len(lines)
        for line in lines:
            if not line:
                # ignore empty string lines
                continue
            i += 1
            if i == 1:
                # first line
                line = self._fragment + line
                self._fragment = ''
            elif i == num_lines - 1:
                # last line
                if has_fragment:
                    self._fragment = line
                    continue
            try:
                packets.append(json.loads(line))
            except Exception as e:
                LOG.error('invalid line for json encoding: %s' % line)
                raise e
        return packets