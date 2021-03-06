# -*- coding: utf-8 -*-

# Copyright 2010-2011 OpenStack Foundation
# Copyright (c) 2013 Hewlett-Packard Development Company, L.P.
#
# Licensed under the Apache License, Version 2.0 (the "License"); you may
# not use this file except in compliance with the License. You may obtain
# a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
# WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
# License for the specific language governing permissions and limitations
# under the License.
import random

from oslo_config import cfg
from oslotest import base

from qinling import config
from qinling import context as auth_context
from qinling.db import api as db_api
from qinling.db.sqlalchemy import sqlite_lock
from qinling import status

DEFAULT_PROJECT_ID = 'default'
OPT_PROJECT_ID = '55-66-77-88'


def get_context(default=True, admin=False):
    if default:
        return auth_context.Context.from_dict({
            'user_name': 'test-default-user',
            'user': '1-2-3-4',
            'tenant': DEFAULT_PROJECT_ID,
            'project_name': 'test-default-project',
            'is_admin': admin
        })
    else:
        return auth_context.Context.from_dict({
            'user_name': 'test-opt-user',
            'user': '5-6-7-8',
            'tenant': OPT_PROJECT_ID,
            'project_name': 'test-opt-project',
            'is_admin': admin
        })


class BaseTest(base.BaseTestCase):
    def override_config(self, name, override, group=None):
        """Cleanly override CONF variables."""
        cfg.CONF.set_override(name, override, group)
        self.addCleanup(cfg.CONF.clear_override, name, group)

    def _assertDictContainsSubset(self, parent, child):
        """Checks whether child dict is a superset of parent.

        assertDictContainsSubset() in standard Python 2.7 has been deprecated
        since Python 3.2

        Refer to https://goo.gl/iABb5c
        """
        self.assertEqual(parent, dict(parent, **child))

    def _assert_single_item(self, items, **props):
        return self._assert_multiple_items(items, 1, **props)[0]

    def _assert_multiple_items(self, items, count, **props):
        def _matches(item, **props):
            for prop_name, prop_val in props.items():
                v = (item[prop_name] if isinstance(item, dict)
                     else getattr(item, prop_name))
                if v != prop_val:
                    return False
            return True

        filtered_items = list(
            [item for item in items if _matches(item, **props)]
        )
        found = len(filtered_items)

        if found != count:
            self.fail("Wrong number of items found [props=%s, "
                      "expected=%s, found=%s]" % (props, count, found))

        return filtered_items

    def rand_name(self, name='', prefix=None):
        """Generate a random name that inclues a random number.

        :param str name: The name that you want to include
        :param str prefix: The prefix that you want to include
        :return: a random name. The format is
                 '<prefix>-<name>-<random number>'.
                 (e.g. 'prefixfoo-namebar-154876201')
        :rtype: string
        """
        randbits = str(random.randint(1, 0x7fffffff))
        rand_name = randbits
        if name:
            rand_name = name + '-' + rand_name
        if prefix:
            rand_name = prefix + '-' + rand_name
        return rand_name


class DbTestCase(BaseTest):
    is_heavy_init_called = False

    def setUp(self):
        super(DbTestCase, self).setUp()

        self._heavy_init()

        self.ctx = get_context()
        auth_context.set_ctx(self.ctx)

        self.addCleanup(auth_context.set_ctx, None)
        self.addCleanup(self._clean_db)

    @classmethod
    def heavy_init(cls):
        """Runs a long initialization.

        This method runs long initialization once by class
        and can be extended by child classes.
        """
        cfg.CONF.set_default('connection', 'sqlite://', group='database')
        cfg.CONF.set_default('max_overflow', -1, group='database')
        cfg.CONF.set_default('max_pool_size', 1000, group='database')

        qinling_opts = [
            (config.API_GROUP, config.api_opts),
            (config.PECAN_GROUP, config.pecan_opts),
            (config.ENGINE_GROUP, config.engine_opts),
            (config.STORAGE_GROUP, config.storage_opts),
            (config.KUBERNETES_GROUP, config.kubernetes_opts),
            (None, [config.launch_opt])
        ]
        for group, options in qinling_opts:
            cfg.CONF.register_opts(list(options), group)

        db_api.setup_db()

    @classmethod
    def _heavy_init(cls):
        """Method that runs heavy_init().

        Make this method private to prevent extending this one.
        It runs heavy_init() only once.

        Note: setUpClass() can be used, but it magically is not invoked
        from child class in another module.
        """
        if not cls.is_heavy_init_called:
            cls.heavy_init()
            cls.is_heavy_init_called = True

    def _clean_db(self):
        db_api.delete_all()
        sqlite_lock.cleanup()

    def create_runtime(self, prefix=None):
        runtime = db_api.create_runtime(
            {
                'name': self.rand_name('runtime', prefix=prefix),
                'image': self.rand_name('image', prefix=prefix),
                # 'auth_enable' is disabled by default, we create runtime for
                # default tenant.
                'project_id': DEFAULT_PROJECT_ID,
                'status': status.AVAILABLE
            }
        )

        return runtime

    def create_function(self, runtime_id=None, prefix=None):
        if not runtime_id:
            runtime_id = self.create_runtime(prefix).id

        function = db_api.create_function(
            {
                'name': self.rand_name('function', prefix=prefix),
                'runtime_id': runtime_id,
                'code': {"source": "package"},
                'entry': 'main.main',
                # 'auth_enable' is disabled by default, we create runtime for
                # default tenant.
                'project_id': DEFAULT_PROJECT_ID,
            }
        )

        return function

    def create_job(self, function_id=None, prefix=None, **kwargs):
        if not function_id:
            function_id = self.create_function(prefix=prefix).id

        job_params = {
            'name': self.rand_name('job', prefix=prefix),
            'function_id': function_id,
            # 'auth_enable' is disabled by default, we create runtime for
            # default tenant.
            'project_id': DEFAULT_PROJECT_ID,
        }
        job_params.update(kwargs)
        job = db_api.create_job(job_params)

        return job
