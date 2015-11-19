# Copyright 2010-2011 OpenStack LLC.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or
# implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""
Configuration setup for kollacli.
"""

import logging
import os

from oslo_config import cfg

from kollacli import i18n as u
from kollacli import version

MAX_LOG_SIZE = 500000

log_opts = [

    cfg.IntOpt('max_size_of_log_in_bytes',

               default=MAX_LOG_SIZE,
               help=u._('The maximum log size in bytes.')),
]


def parse_args(conf, args=None, usage=None, default_config_files=None):
    conf(args=args if args else [],
         project='kollacli',
         prog='kollacli',
         version=version.__version__,
         usage=usage,
         default_config_files=default_config_files)

    conf.pydev_debug_host = os.environ.get('PYDEV_DEBUG_HOST')
    conf.pydev_debug_port = os.environ.get('PYDEV_DEBUG_PORT')


def list_opts():
    yield None, log_opts


def new_config():
    conf = cfg.ConfigOpts()
    conf.register_opts(log_opts)
    return conf


def setup_remote_pydev_debug():
    """Required setup for remote debugging."""
    if CONF.pydev_debug_host and CONF.pydev_debug_port:
        try:
            try:
                from pydev import pydevd
            except ImportError:
                import pydevd

            pydevd.settrace(CONF.pydev_debug_host,
                            port=int(CONF.pydev_debug_port),
                            stdoutToServer=True,
                            stderrToServer=True)

        except Exception:
            LOG.exception('Unable to join debugger, please '
                          'make sure that the debugger processes is '
                          'listening on debug-host \'%s\' debug-port \'%s\'.',
                          CONF.pydev_debug_host, CONF.pydev_debug_port)
            raise


CONF = new_config()
LOG = logging.getLogger(__name__)
parse_args(CONF)
