#  Copyright 2008-2009 Nokia Siemens Networks Oyj
#
#  Licensed under the Apache License, Version 2.0 (the "License");
#  you may not use this file except in compliance with the License.
#  You may obtain a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
#  Unless required by applicable law or agreed to in writing, software
#  distributed under the License is distributed on an "AS IS" BASIS,
#  WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#  See the License for the specific language governing permissions and
#  limitations under the License.

import os
import re
import operator
import tempfile

from robot.errors import DataError
from robot.parsing.model import ResourceFile
from robot.parsing.settings import Library, Resource, Variables
from robot.utils.normalizing import normalize
from robot.variables import Variables as RobotVariables

from robotide.namespace.cache import LibraryCache, ExpiringCache
from robotide.spec.iteminfo import (TestCaseUserKeywordInfo,
                                    ResourceseUserKeywordInfo,
                                    VariableInfo, _UserKeywordInfo)
from robotide.robotapi import NormalizedDict, is_var
from robotide import utils


class Namespace(object):

    regexp = re.compile("\s*(given|when|then|and)(.*)", re.IGNORECASE)

    def __init__(self):
        self.lib_cache = LibraryCache()
        self.res_cache = ResourceCache()
        self.retriever = DatafileRetriever(self.lib_cache, self.res_cache)
        self._content_assist_hooks = []

    def register_content_assist_hook(self, hook):
        self._content_assist_hooks.append(hook)

    def get_all_keywords(self, datafiles):
        kws = set()
        kws.update(self._get_default_keywords())
        kws.update(self.retriever.get_keywords_from_several(datafiles))
        return list(kws)

    def _get_default_keywords(self):
        return self.lib_cache.get_default_keywords()

    def get_suggestions_for(self, controller, start):
        datafile = controller.datafile
        sugs = set()
        sugs.update(self._get_suggestions_from_hooks(datafile, start))
        if self._blank(start):
            sugs.update(self._all_suggestions(controller))
        elif self._looks_like_variable(start):
            sugs.update(self._variable_suggestions(controller, start))
        else:
            sugs.update(self._keyword_suggestions(datafile, start))
        sugs_list = list(sugs)
        sugs_list.sort()
        return sugs_list

    def _get_suggestions_from_hooks(self, datafile, start):
        sugs = []
        for hook in self._content_assist_hooks:
            sugs.extend(hook(datafile, start))
        return sugs

    def _blank(self, start):
        return start == ''

    def _all_suggestions(self, controller):
        vars = self._variable_suggestions(controller, '')
        kws = self._keyword_suggestions(controller.datafile, '')
        all = vars + kws
        all.sort()
        return all

    def _looks_like_variable(self, start):
        return (len(start) == 1 and start.startswith('$') or start.startswith('@')) \
            or (len(start) >= 2 and start.startswith('${') or start.startswith('@{'))

    def _variable_suggestions(self, controller, start):
        datafile = controller.datafile
        start_normalized = normalize(start)
        vars = self.retriever.get_variables_from(datafile)
        self._add_kw_arg_vars(controller, vars)
        return [v for v in vars
                if normalize(v.name).startswith(start_normalized)]

    def _add_kw_arg_vars(self, controller, vars):
        for name, value in controller.get_local_variables().iteritems():
            vars.set(name, value, 'Argument')

    def _keyword_suggestions(self, datafile, start):
        start_normalized = normalize(start)
        suggestions = self._get_default_keywords()
        suggestions.extend(self.retriever.get_keywords_from(datafile))
        return sorted([sug for sug in suggestions
                       if normalize(sug.name).startswith(start_normalized)])

    def get_resources(self, datafile):
        return self.retriever.get_resources_from(datafile)

    def get_resource(self, path):
        return self.res_cache.get_resource('', path)

    def find_user_keyword(self, datafile, kw_name):
        kw = self.find_keyword(datafile, kw_name)
        return kw if isinstance(kw, _UserKeywordInfo) else None

    def is_user_keyword(self, datafile, kw_name):
        return bool(self.find_user_keyword(datafile, kw_name))

    def find_library_keyword(self, datafile, kw_name):
        kw = self.find_keyword(datafile, kw_name)
        return kw if kw and kw.is_library_keyword() else None

    def find_keyword(self, datafile, kw_name):
        if not kw_name:
            return None
        kwds = self.retriever.get_keywords_dict_cached(datafile)
        if kw_name in kwds:
            return kwds[kw_name]
        bdd_name = self._get_bdd_name(kw_name)
        if bdd_name and bdd_name in kwds:
            return kwds[bdd_name]
        return None

    def _get_bdd_name(self, kw_name):
        match = self.regexp.match(kw_name)
        return match.group(2) if match else None

    def is_library_keyword(self, datafile, kw_name):
        return bool(self.find_library_keyword(datafile, kw_name))

    def keyword_details(self, datafile, name):
        kw = self.find_keyword(datafile, name)
        return kw.details if kw else None


class ResourceCache(object):

    def __init__(self):
        self.cache = {}
        self.python_path_cache = {}

    def get_resource(self, directory, name):
        path = os.path.join(directory, name) if directory else name
        res = self._get_resource(path)
        if res:
            return res
        path_from_pythonpath = self._get_python_path(name)
        if path_from_pythonpath:
            return self._get_resource(path_from_pythonpath)
        return None

    def _get_python_path(self, name):
        if name in self.python_path_cache:
            return self.python_path_cache[name]
        path_from_pythonpath = utils.find_from_pythonpath(name)
        self.python_path_cache[name] = path_from_pythonpath
        return self.python_path_cache[name]

    def _get_resource(self, path):
        normalized = os.path.normpath(path)
        if normalized not in self.cache:
            try:
                self.cache[normalized] = ResourceFile(path)
            except Exception:
                self.cache[normalized] = None
                return None
        return self.cache[normalized]


class RetrieverContext(object):

    def __init__(self):
        self.vars = _VariableStash()
        self.parsed = set()

    def allow_going_through_resources_again(self):
        """Resets the parsed-cache.
        Normally all resources that have been handled are added to 'parsed' and
        then not handled again, to prevent looping forever. If this same context
        is used for going through the resources again, then you should call
        this.
        """
        self.parsed = set()


class _VariableStash(object):
    # Global variables copied from robot.variables.__init__.py
    global_variables =  {'${TEMPDIR}': os.path.normpath(tempfile.gettempdir()),
                         '${EXECDIR}': os.path.abspath('.'),
                         '${/}': os.sep,
                         '${:}': os.pathsep,
                         '${SPACE}': ' ',
                         '${EMPTY}': '',
                         '${True}': True,
                         '${False}': False,
                         '${None}': None,
                         '${null}': None,
                         '${OUTPUT_DIR}': '',
                         '${OUTPUT_FILE}': '',
                         '${SUMMARY_FILE}': '',
                         '${REPORT_FILE}': '',
                         '${LOG_FILE}': '',
                         '${DEBUG_FILE}': '',
                         '${PREV_TEST_NAME}': '',
                         '${PREV_TEST_STATUS}': '',
                         '${PREV_TEST_MESSAGE}': '',
                         '${CURDIR}': '.',
                         '${TEST_NAME}': '',
                         '@{TEST_TAGS}': '',
                         '${TEST_STATUS}': '',
                         '${TEST_MESSAGE}': '',
                         '${SUITE_NAME}': '',
                         '${SUITE_SOURCE}': '',
                         '${SUITE_STATUS}': '',
                         '${SUITE_MESSAGE}': ''}


    def __init__(self):
        self._vars = RobotVariables()
        self._sources = {}
        for k, v in self.global_variables.iteritems():
            self.set(k, v, 'Global')

    def set(self, name, value, source):
        self._vars[name] = value
        self._sources[name] = source

    def replace_variables(self, value):
        try:
            return self._vars.replace_scalar(value)
        except DataError:
            return self._vars.replace_string(value, ignore_errors=True)

    def set_from_variable_table(self, variable_table):
        for variable in variable_table:
            try:
                name, value = self._vars._get_var_table_name_and_value(variable.name,
                                                                 variable.value)
                if not self._vars.has_key(name):
                    self.set(name, value, variable_table.source)
            except DataError:
                if is_var(variable.name):
                    self.set(variable.name, '', variable_table.source)

    def set_from_file(self, varfile_path, args):
        temp = RobotVariables()
        temp.set_from_file(varfile_path, args)
        for (name, value) in temp.items():
            self.set(name, value, varfile_path)

    def __iter__(self):
        for name, value in self._vars.items():
            yield VariableInfo(name, value, self._sources[name])


class DatafileRetriever(object):

    def __init__(self, lib_cache, res_cache):
        self.lib_cache = lib_cache
        self.res_cache = res_cache
        self.keyword_cache = ExpiringCache()
        self.default_kws = self.lib_cache.get_default_keywords()

    def get_keywords_from_several(self, datafiles):
        kws = set()
        kws.update(self.default_kws)
        for df in datafiles:
            kws.update(self.get_keywords_from(df))
        return kws

    def get_keywords_from(self, datafile):
        ctx = RetrieverContext()
        self._get_vars_recursive(datafile, ctx)
        ctx.allow_going_through_resources_again()
        kws = self._get_datafile_keywords(datafile) +\
              self._get_imported_library_keywords(datafile, ctx) +\
              self._get_imported_resource_keywords(datafile, ctx)
        result_in_order = []
        for k in kws:
            if k not in result_in_order : result_in_order.append(k)
        return result_in_order

    def _get_datafile_keywords(self, datafile):
        return [TestCaseUserKeywordInfo(kw) for kw in datafile.keywords]

    def _get_imported_library_keywords(self, datafile, ctx):
        return self._collect_kws_from_imports(datafile, Library,
                                              self._lib_kw_getter, ctx)

    def _collect_kws_from_imports(self, datafile, instance_type, getter, ctx):
        kws = []
        for imp in self._collect_import_of_type(datafile, instance_type):
            kws.extend(getter(imp, ctx))
        return kws

    def _lib_kw_getter(self, imp, ctx):
        name = ctx.vars.replace_variables(imp.name)
        args = [ctx.vars.replace_variables(a) for a in imp.args]
        return self.lib_cache.get_library_keywords(name, args)

    def _collect_import_of_type(self, datafile, instance_type):
        return [imp for imp in datafile.imports
                if isinstance(imp, instance_type)]

    def _get_imported_resource_keywords(self, datafile, ctx):
        return self._collect_kws_from_imports(datafile, Resource,
                                              self._res_kw_recursive_getter, ctx)

    def _res_kw_recursive_getter(self, imp, ctx):
        kws = []
        resolved_name = ctx.vars.replace_variables(imp.name)
        res = self.res_cache.get_resource(imp.directory, resolved_name)
        if not res or res in ctx.parsed:
            return kws
        ctx.parsed.add(res)
        ctx.vars.set_from_variable_table(res.variable_table)
        for child in self._collect_import_of_type(res, Resource):
            kws.extend(self._res_kw_recursive_getter(child, ctx))
        kws.extend(self._get_imported_library_keywords(res, ctx))
        return [ResourceseUserKeywordInfo(kw) for kw in res.keywords] + kws

    def get_variables_from(self, datafile):
        return self._get_vars_recursive(datafile, RetrieverContext()).vars

    def _get_vars_recursive(self, datafile, ctx):
        ctx.vars.set_from_variable_table(datafile.variable_table)
        self._collect_vars_from_variable_files(datafile, ctx)
        self._collect_each_res_import(datafile, ctx, self._var_collector)
        return ctx

    def _collect_vars_from_variable_files(self, datafile, ctx):
        for imp in self._collect_import_of_type(datafile, Variables):
            varfile_path = os.path.join(datafile.directory,
                                        ctx.vars.replace_variables(imp.name))
            args = [ctx.vars.replace_variables(a) for a in imp.args]
            try:
                ctx.vars.set_from_file(varfile_path, args)
            except DataError:
                pass # TODO: log somewhere

    def _var_collector(self, res, ctx, items):
        self._get_vars_recursive(res, ctx)

    def get_keywords_dict_cached(self, datafile):
        values = self.keyword_cache.get(datafile.source)
        if not values:
            words = self.get_keywords_from(datafile)
            words.extend(self.default_kws)
            values = self._keywords_to_dict(words, datafile)
            self.keyword_cache.put(datafile.source, values)
        return values

    def _keywords_to_dict(self, keywords, datafile):
        ret = NormalizedDict()
        for kw in keywords:
            # TODO: this hack creates a preference for local keywords over resources and libraries
            # Namespace should be rewritten to handle keyword preference order
            if kw.name not in ret:
                ret[kw.name] = kw
            ret[kw.longname] = kw
        return ret

    def _get_user_keywords_from(self, datafile):
        return list(self._get_user_keywords_recursive(datafile, RetrieverContext()))

    def _get_user_keywords_recursive(self, datafile, ctx):
        kws = set()
        kws.update(datafile.keywords)
        kws_from_res = self._collect_each_res_import(datafile, ctx,
            lambda res, ctx, kws: kws.update(self._get_user_keywords_recursive(res, ctx)))
        kws.update(kws_from_res)
        return kws

    def _collect_each_res_import(self, datafile, ctx, collector):
        items = set()
        ctx.vars.set_from_variable_table(datafile.variable_table)
        for imp in self._collect_import_of_type(datafile, Resource):
            resolved_name = ctx.vars.replace_variables(imp.name)
            res = self.res_cache.get_resource(imp.directory, resolved_name)
            if res and res not in ctx.parsed:
                ctx.parsed.add(res)
                collector(res, ctx, items)
        return items

    def get_resources_from(self, datafile):
        resources = list(self._get_resources_recursive(datafile, RetrieverContext()))
        resources.sort(key=operator.attrgetter('name'))
        return resources

    def _get_resources_recursive(self, datafile, ctx):
        resources = set()
        res = self._collect_each_res_import(datafile, ctx, self._add_resource)
        resources.update(res)
        for child in datafile.children:
            resources.update(self.get_resources_from(child))
        return resources

    def _add_resource(self, res, ctx, items):
        items.add(res)
        items.update(self._get_resources_recursive(res, ctx))
