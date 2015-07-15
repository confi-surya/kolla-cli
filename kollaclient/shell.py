#   Copyright 2015 Oracle TODO(bmace) -- FIX THIS LINE
#
#   Licensed under the Apache License, Version 2.0 (the "License"); you may
#   not use this file except in compliance with the License. You may obtain
#   a copy of the License at
#
#        http://www.apache.org/licenses/LICENSE-2.0
#
#   Unless required by applicable law or agreed to in writing, software
#   distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
#   WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#   License for the specific language governing permissions and limitations
#   under the License.
#

"""Command-line interface to Kolla"""

import sys

from cliff.app import App
from cliff.commandmanager import CommandManager


class KollaClient(App):

    def __init__(self):
        super(KollaClient, self).__init__(
            description='Command-Line Client for StackForge Kolla',
            version='0.1',
            command_manager=CommandManager('kolla.client'),
            )
        self.dump_stack_trace = True

    def prepare_to_run_command(self, cmd):
        self.LOG.debug('prepare_to_run_command %s', cmd.__class__.__name__)

    def clean_up(self, cmd, result, err):
        self.LOG.debug('clean_up %s', cmd.__class__.__name__)
        if err:
            self.LOG.debug('error: %s', err)


def main(argv=sys.argv[1:]):
    shell = KollaClient()
    return shell.run(argv)

if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
