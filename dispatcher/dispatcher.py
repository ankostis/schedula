#!/usr/bin/env python
# -*- coding: UTF-8 -*-
#
# Copyright 2014 European Commission (JRC);
# Licensed under the EUPL (the 'Licence');
# You may not use this work except in compliance with the Licence.
# You may obtain a copy of the Licence at: http://ec.europa.eu/idabc/eupl

__author__ = 'Vincenzo Arcidiacono'

import logging
from networkx import DiGraph, isolates
from heapq import heappush, heappop
from itertools import count
from collections import OrderedDict
from .utils import rename_function, AttrDict, caller_name
from .graph_utils import add_edge_fun, remove_cycles_iteration
from .constants import EMPTY, START, NONE, SINK
from .dispatcher_utils import SubDispatch, bypass


log = logging.getLogger(__name__)

__all__ = ['Dispatcher']


def _warning(raises):
    """
    Returns a function that handle the error messages.

    :param raises:
        If True the dispatcher interrupt the dispatch when an error occur,
        otherwise it logs a warning.
    :type: bool

    :return:
        A function that handle the error messages.
    :rtype: function
    """

    if raises:
        def warning(msg):
            raise ValueError(msg)
    else:
        def warning(msg):
            log.warning(msg, exc_info=1)
    return warning


class Dispatcher(object):
    """
    It provides a data structure to process a complex system of functions.

    The scope of this data structure is to compute the shortest workflow between
    input and output data nodes.

    A workflow is a sequence of function calls.

    :ivar dmap:
        The directed graph that stores data & functions parameters.
    :type dmap: DiGraph

    :ivar name:
        The dispatcher's name.
    :type name: str

    :ivar nodes:
        The function and data nodes of the dispatcher.
    :type nodes: AttrDict

    :ivar default_values:
        Data node default values. These will be used as input if it is not
        specified as inputs in the ArciDispatch algorithm.
    :type default_values: dict

    :ivar data_output:
        A dictionary with the dispatch outputs.
    :type data_output: dict

    :ivar dist:
        A dictionary of distances from the `START` node.
    :type dist: dict

    :ivar weight:
        Weight tag.
    :type weight: str

    :ivar workflow:
        The dispatch workflow graph. It is a sequence of function calls.
    :type workflow: DiGraph

    :ivar _visited:
        A set of visited nodes from the dispatch.
    :type _visited: set

    :ivar _targets:
        A set of target nodes.
    :type _targets: set

    :ivar _cutoff:
        Depth to stop the search.
    :type _cutoff: int, float, None

    :ivar _wildcards:
        A set of nodes with a wildcard.
    :type _wildcards: set

    :ivar _pred:
        The predecessors of the dispatcher map nodes.
    :type _pred: dict

    :ivar _succ:
        The successors of the dispatcher map nodes.
    :type _succ: dict

    :ivar _wf_add_edge:
        A function that add edges to the `workflow`.
    :type _wf_add_edge: function

    :ivar _wf_pred:
        The predecessors of the `workflow` nodes.
    :type _wf_pred: dict

    :ivar _wait_in:
        Data nodes that waits inputs. They are used in `shrink_dsp`.
    :type _wait_in: dict

    \***************************************************************************

    **Example**:

    As an example, here is a system of equations:

    :math:`b - a = c`

    :math:`log(c) = d_{from-log}`

    :math:`d = (d_{from-log} + d_{initial-guess}) / 2`

    that will be solved assuming that :math:`a = 0`, :math:`b = 1`, and
    :math:`d_{initial-guess} = 4`.

    **Steps**

    Create an empty dispatcher::

        >>> dsp = Dispatcher()

    Add data nodes to the dispatcher map::

        >>> dsp.add_data(data_id='a')
        'a'
        >>> dsp.add_data(data_id='c')
        'c'

    Add a data node with a default value to the dispatcher map::

        >>> dsp.add_data(data_id='b', default_value=1)
        'b'

    Add a function node::

        >>> def diff_function(a, b):
        ...     return b - a
        ...
        >>> dsp.add_function('diff_function', function=diff_function,
        ...                  inputs=['a', 'b'], outputs=['c'])
        'diff_function'

    Add a function node with domain::

        >>> from math import log
        ...
        >>> def log_domain(x):
        ...     return x > 0
        ...
        >>> dsp.add_function('log', function=log, inputs=['c'], outputs=['d'],
        ...                  input_domain=log_domain)
        'log'

    Add a data node with function estimation and callback function.

        - function estimation: estimate one unique output from multiple
          estimations.
        - callback function: is invoked after computing the output.

        >>> def average_fun(kwargs):
        ...     '''
        ...     Returns the average of node estimations.
        ...
        ...     :param kwargs:
        ...         Node estimations.
        ...     :type kwargs: dict
        ...
        ...     :return:
        ...         The average of node estimations.
        ...     :rtype: float
        ...     '''
        ...
        ...     x = kwargs.values()
        ...     return sum(x) / len(x)
        ...
        >>> def callback_fun(x):
        ...     print('(log(1) + 4) / 2 = %.1f' % x)
        ...
        >>> dsp.add_data(data_id='d', default_value=4, wait_inputs=True,
        ...              function=average_fun, callback=callback_fun)
        'd'

    .. testsetup::
        >>> from dispatcher.draw import dsp2dot
        >>> from dispatcher import dot_dir
        >>> dot = dsp2dot(dsp, graph_attr={'rankdir': 'LR'})
        >>> dot.save('Dispatcher/dsp.dot', dot_dir)
        '...'

    .. graphviz:: Dispatcher/dsp.dot

    Dispatch the function calls to achieve the desired output data node `d`::

        >>> workflow, outputs = dsp.dispatch(inputs={'a': 0}, outputs=['d'])
        (log(1) + 4) / 2 = 2.0
        >>> sorted(outputs.items())
        [('a', 0), ('b', 1), ('c', 1), ('d', 2.0)]

    .. testsetup::
        >>> dot = dsp2dot(dsp, workflow=True, graph_attr={'rankdir': 'LR'})
        >>> dot.save('Dispatcher/wf.dot', dot_dir)
        '...'

    .. graphviz:: Dispatcher/wf.dot
    """

    def __init__(self, dmap=None, name='Dispatcher', default_values=None,
                 raises=False):
        """
        Initializes the dispatcher.

        :param dmap:
            A directed graph that stores data & functions parameters.
        :type dmap: DiGraph, optional

        :param name:
            The dispatcher's name.
        :type name: str, optional

        :param default_values:
            Data node default values. These will be used as input if it is not
            specified as inputs in the ArciDispatch algorithm.
        :type default_values: dict, optional

        :param raises:
            If True the dispatcher interrupt the dispatch when an error occur,
            otherwise it logs a warning.
        :type raises: bool, optional
        """

        self.dmap = dmap if dmap else DiGraph()
        self.name = name
        self.dmap.node = AttrDict(self.dmap.node)
        self.nodes = self.dmap.node
        self.default_values = default_values if default_values else {}
        self.weight = 'weight'
        self.workflow = DiGraph()  # graph output
        self.data_output = {}
        self.dist = {}
        self.warning = _warning(raises)
        self._visited = set()
        self._targets = set()
        self._cutoff = None
        self._wildcards = set()
        self._pred = self.dmap.pred
        self._succ = self.dmap.succ
        self._wf_add_edge = add_edge_fun(self.workflow)
        self._wf_pred = self.workflow.pred
        self._wait_in = {}

    def add_data(self, data_id=None, default_value=EMPTY, wait_inputs=False,
                 wildcard=None, function=None, callback=None, **kwargs):
        """
        Add a single data node to the dispatcher.

        :param data_id:
            Data node id. If None will be assigned the next 'int' not in dmap.
        :type data_id: any hashable Python object except None, optional

        :param default_value:
            Data node default value. This will be used as input if it is not
            specified as inputs in the ArciDispatch algorithm.
        :type default_value: object, optional

        :param wait_inputs:
            If True ArciDispatch algorithm stops on the node until it gets all
            input estimations.
        :type wait_inputs: bool, optional

        :param wildcard:
            If True, when the data node is used as input and target in the
            ArciDispatch algorithm, the input value will be used as input for
            the connected functions, but not as output.
        :type wildcard: bool, optional

        :param function:
            Data node estimation function.
            This can be any function that takes only one dictionary
            (key=function node id, value=estimation of data node) as input and
            return one value that is the estimation of the data node.
        :type function: function, optional

        :param callback:
            Callback function to be called after node estimation.
            This can be any function that takes only one argument that is the
            data node estimation output. It does not return anything.
        :type callback: function, optional

        :param kwargs:
            Set additional node attributes using key=value.
        :type kwargs: keyword arguments, optional

        :return:
            Data node id.
        :rtype: object

        .. seealso:: add_function, add_from_lists

        .. note::
            A hashable object is one that can be used as a key in a Python
            dictionary. This includes strings, numbers, tuples of strings
            and numbers, etc.

            On many platforms hashable items also include mutable objects such
            as NetworkX Graphs, though one should be careful that the hash
            doesn't change on mutable objects.

        \***********************************************************************

        **Example**:

        .. testsetup::
            >>> dsp = Dispatcher()

        Add a data to be estimated or a possible input data node::

            >>> dsp.add_data(data_id='a')
            'a'

        Add a data with a default value (i.e., input data node)::

            >>> dsp.add_data(data_id='b', default_value=1)
            'b'

        Create a data node with function estimation and a default value.

            - function estimation: estimate one unique output from multiple
              estimations.
            - default value: is a default estimation.

            >>> def min_fun(kwargs):
            ...     '''
            ...     Returns the minimum value of node estimations.
            ...
            ...     :param kwargs:
            ...         Node estimations.
            ...     :type kwargs: dict
            ...
            ...     :return:
            ...         The minimum value of node estimations.
            ...     :rtype: float
            ...     '''
            ...
            ...     return min(kwargs.values())
            ...
            >>> dsp.add_data(data_id='c', default_value=2, wait_inputs=True,
            ...              function=min_fun)
            'c'

        Create a data with an unknown id and return the generated id::

            >>> dsp.add_data()
            'unknown<0>'
        """

        # base data node attributes
        attr_dict = {'type': 'data', 'wait_inputs': wait_inputs}

        if function is not None:  # add function as node attribute
            attr_dict['function'] = function

        if callback is not None:  # add callback as node attribute
            attr_dict['callback'] = callback

        if wildcard is not None:  # add wildcard as node attribute
            attr_dict['wildcard'] = wildcard

        # additional attributes
        attr_dict.update(kwargs)

        has_node = self.dmap.has_node  # namespace shortcut for speed

        if data_id is None:  # search for a unused node id
            n = count(0).__next__  # counter
            data_id = 'unknown<%d>' % n()  # initial guess
            while has_node(data_id):  # check if node id is used
                data_id = 'unknown<%d>' % n()  # guess

        # check if the node id exists as function
        elif has_node(data_id) and self.dmap.node[data_id]['type'] != 'data':
            raise ValueError('Invalid data id: '
                             'override function {}'.format(data_id))

        if default_value != EMPTY:  # add default value
            self.default_values[data_id] = default_value

        elif data_id in self.default_values:  # remove default value
            self.default_values.pop(data_id)

        # add node to the dispatcher map
        self.dmap.add_node(data_id, attr_dict=attr_dict)

        # return data node id
        return data_id

    def add_function(self, function_id=None, function=None, inputs=None,
                     outputs=None, input_domain=None, weight=None,
                     weight_from=None, weight_to=None, **kwargs):
        """
        Add a single function node to dispatcher.

        :param function_id:
            Function node id.
            If None will be assigned as <fun.__module__>:<fun.__name__>.
        :type function_id: any hashable Python object except None, optional

        :param function:
            Data node estimation function.
        :type function: function, optional

        :param inputs:
            Ordered arguments (i.e., data node ids) needed by the function.
        :type inputs: list, optional

        :param outputs:
            Ordered results (i.e., data node ids) returned by the function.
        :type outputs: list, optional

        :param input_domain:
            A function that checks if input values satisfy the function domain.
            This can be any function that takes the same inputs of the function
            and returns True if input values satisfy the domain, otherwise
            False. In this case the dispatch algorithm doesn't pass on the node.
        :type input_domain: function, optional

        :param weight:
            Node weight. It is a weight coefficient that is used by the dispatch
            algorithm to estimate the minimum workflow.
        :type weight: float, int, optional

        :param weight_from:
            Edge weights from data nodes to the function node.
            It is a dictionary (key=data node id) with the weight coefficients
            used by the dispatch algorithm to estimate the minimum workflow.
        :type weight_from: dict , optional

        :param weight_to:
            Edge weights from the function node to data nodes.
            It is a dictionary (key=data node id) with the weight coefficients
            used by the dispatch algorithm to estimate the minimum workflow.
        :type weight_to: dict, optional

        :param kwargs:
            Set additional node attributes using key=value.
        :type kwargs: keyword arguments, optional

        :return:
            Function node id.
        :rtype: object

        .. seealso:: add_node, add_from_lists

        \***********************************************************************

        **Example**:

        .. testsetup::
            >>> dsp = Dispatcher()

        Add a function node::

            >>> def my_function(a, b):
            ...     c = a + b
            ...     d = a - b
            ...     return c, d
            ...
            >>> dsp.add_function(function=my_function, inputs=['a', 'b'],
            ...                  outputs=['c', 'd'])
            '...dispatcher:my_function'

        Add a function node with domain::

            >>> from math import log
            >>> def my_log(a, b):
            ...     log(b - a)
            ...
            >>> def my_domain(a, b):
            ...     return a < b
            ...
            >>> dsp.add_function(function=my_log, inputs=['a', 'b'],
            ...                  outputs=['e'], input_domain=my_domain)
            '...dispatcher:my_log'
        """

        if inputs is None:  # set a dummy input
            if START not in self.nodes:
                self.add_data(START, default_value=NONE)

            inputs = [START]

        if outputs is None:  # set a dummy output
            if SINK not in self.nodes:
                self.add_data(SINK, wait_inputs=True, function=bypass)

            outputs = [SINK]

        # base function node attributes
        attr_dict = {'type': 'function',
                     'inputs': inputs,
                     'outputs': outputs,
                     'function': function,
                     'wait_inputs': True}

        if input_domain:  # add domain as node attribute
            attr_dict['input_domain'] = input_domain

        if function_id is None:  # set function name
            try:
                # noinspection PyUnresolvedReferences
                function_name = '%s:%s' % (function.__module__,
                                           function.__name__)
            except Exception as ex:
                raise ValueError('Invalid function name due to:\n{}'.format(ex))
        else:
            function_name = function_id

        fun_id = function_name  # initial function id guess

        n = count(0).__next__  # counter

        has_node = self.dmap.has_node  # namespace shortcut for speed

        while has_node(fun_id):  # search for a unused node id
            fun_id = '%s<%d>' % (function_name, n())  # guess

        if weight is not None:  # add weight as node attribute
            attr_dict['weight'] = weight

        # additional attributes
        attr_dict.update(kwargs)

        # add node to the dispatcher map
        self.dmap.add_node(fun_id, attr_dict=attr_dict)

        def add_edge(i, o, edge_weight, w):
            # Adds edge to the dispatcher map.

            if edge_weight is not None and w in edge_weight:
                self.dmap.add_edge(i, o, weight=edge_weight[w])  # weighted edge
            else:
                self.dmap.add_edge(i, o)  # normal edge

        for u in inputs:
            try:
                # check if the node id exists as data
                if self.dmap.node[u]['type'] != 'data':
                    self.dmap.remove_node(fun_id)
                    raise ValueError('Invalid input id:'
                                     ' {} is not a data node'.format(u))
            except KeyError:
                self.add_data(data_id=u)  # add data node

            add_edge(u, fun_id, weight_from, u)

        for v in outputs:
            try:
                # check if the node id exists as data
                if self.dmap.node[v]['type'] != 'data':
                    self.dmap.remove_node(fun_id)
                    raise ValueError('Invalid output id:'
                                     ' {} is not a data node'.format(v))
            except KeyError:
                self.add_data(data_id=v)  # add data node

            add_edge(fun_id, v, weight_to, v)

        # return function node id
        return fun_id

    def add_from_lists(self, data_list=None, fun_list=None):
        """
        Add multiple function and data nodes to dispatcher.

        :param data_list:
            It is a list of data node kwargs to be loaded.
        :type data_list: list, optional

        :param fun_list:
            It is a list of function node kwargs to be loaded.
        :type fun_list: list, optional

        :returns:
            - Data node ids.
            - Function node ids.
        :rtype: (list, list)

        .. seealso:: add_node, add_function

        \***********************************************************************

        **Example**:

        .. testsetup::
            >>> dsp = Dispatcher()

        Define a data list::

            >>> data_list = [
            ...     {'data_id': 'a'},
            ...     {'data_id': 'b'},
            ...     {'data_id': 'c'},
            ... ]

        Define a functions list::

            >>> def f(a, b):
            ...     return a + b
            ...
            >>> fun_list = [
            ...     {'function': f, 'inputs': ['a', 'b'], 'outputs': ['c']},
            ...     {'function': f, 'inputs': ['c', 'd'], 'outputs': ['a']}
            ... ]

        Add function and data nodes to dispatcher::

            >>> dsp.add_from_lists(data_list, fun_list)
            (['a', 'b', 'c'], ['...dispatcher:f', '...dispatcher:f<0>'])
        """

        if data_list:  # add data nodes
            data_ids = [self.add_data(**v) for v in data_list]  # data ids
        else:
            data_ids = []

        if fun_list:  # add function nodes
            fun_ids = [self.add_function(**v) for v in fun_list]  # function ids
        else:
            fun_ids = []

        # return data and function node ids
        return data_ids, fun_ids

    def set_default_value(self, data_id, value=EMPTY):
        """
        Set the default value of a data node in the dispatcher.

        :param data_id:
            Data node id.
        :type data_id: any hashable Python object except None

        :param value:
            Data node default value.
        :type value: object, optional

        \***********************************************************************

        **Example**:

        A dispatcher with a data node named `a`::

            >>> dsp = Dispatcher()
            ...
            >>> dsp.add_data(data_id='a')
            'a'

        Add a default value to `a` node::

            >>> dsp.set_default_value('a', value='value of the data')
            >>> dsp.default_values
            {'a': 'value of the data'}

        Remove the default value of `a` node::

            >>> dsp.set_default_value('a', value=EMPTY)
            >>> dsp.default_values
            {}
        """

        try:
            if self.dmap.node[data_id]['type'] == 'data':  # check if data node
                if value == EMPTY:
                    self.default_values.pop(data_id, None)  # remove default
                else:
                    self.default_values[data_id] = value  # add default
                return
            raise ValueError
        except:
            raise ValueError('Input error: %s is not a data node' % data_id)

    def get_sub_dsp(self, nodes_bunch, edges_bunch=None):
        """
        Returns the sub-dispatcher induced by given node and edge bunches.

        The induced sub-dispatcher contains the available nodes in nodes_bunch
        and edges between those nodes, excluding those that are in edges_bunch.

        The available nodes are non isolated nodes and function nodes that have
        all inputs and at least one output.

        :param nodes_bunch:
            A container of node ids which will be iterated through once.
        :type nodes_bunch: list, iterable

        :param edges_bunch:
            A container of edge ids that will be removed.
        :type edges_bunch: list, iterable, optional

        :return:
            A sub-dispatcher.
        :rtype: Dispatcher

        .. note::

            The sub-dispatcher edge or node attributes just point to the
            original dispatcher. So changes to the node or edge structure
            will not be reflected in the original dispatcher map while changes
            to the attributes will.

        \***********************************************************************

        **Example**:

        A dispatcher with a two functions `fun1` and `fun2`:

        .. testsetup::
            >>> dsp = Dispatcher()
            >>> dsp.add_function(function_id='fun1', inputs=['a', 'b'],
            ...                   outputs=['c', 'd'])
            'fun1'
            >>> dsp.add_function(function_id='fun2', inputs=['a', 'd'],
            ...                   outputs=['c', 'e'])
            'fun2'
            >>> from dispatcher.draw import dsp2dot
            >>> from dispatcher import dot_dir
            >>> dot = dsp2dot(dsp, graph_attr={'rankdir': 'LR'})
            >>> dot.save('get_sub_dsp/dsp.dot', dot_dir)
            '...'

        .. graphviz:: get_sub_dsp/dsp.dot

        Get the sub-dispatcher induced by given nodes bunch::

            >>> sub_dsp = dsp.get_sub_dsp(['a', 'c', 'd', 'e', 'fun2'])

        .. testsetup::
            >>> sub_dsp.name = 'Sub-Dispatcher'
            >>> dot = dsp2dot(sub_dsp, graph_attr={'rankdir': 'LR'})
            >>> dot.save('get_sub_dsp/sub_dsp.dot', dot_dir)
            '...'

        .. graphviz:: get_sub_dsp/sub_dsp.dot
        """

        # define an empty dispatcher
        sub_dsp = self.__class__(dmap=self.dmap.subgraph(nodes_bunch))

        # namespace shortcuts for speed
        nodes = sub_dsp.dmap.node
        dmap_out_degree = sub_dsp.dmap.out_degree
        dmap_remove_node = sub_dsp.dmap.remove_node
        dmap_remove_edge = sub_dsp.dmap.remove_edge
        dmap_dv = self.default_values

        # remove function nodes that has not whole inputs available
        for u in nodes_bunch:
            n = nodes[u].get('inputs', None)  # function inputs
            # no all inputs
            if n is not None and not set(n).issubset(nodes_bunch):
                dmap_remove_node(u)  # remove function node

        # remove edges that are not in edges_bunch
        if edges_bunch is not None:
            # iterate sub-graph edges
            for e in edges_bunch:
                dmap_remove_edge(*e)  # remove edge

        # remove function node with no outputs
        for u in [u for u, n in sub_dsp.dmap.nodes_iter(True)
                  if n['type'] == 'function']:

            if not dmap_out_degree(u):  # no outputs
                dmap_remove_node(u)  # remove function node

        # remove isolate nodes from sub-graph
        sub_dsp.dmap.remove_nodes_from(isolates(sub_dsp.dmap))

        # set default values
        sub_dsp.default_values = {k: dmap_dv[k] for k in dmap_dv if k in nodes}

        # return the sub-dispatcher
        return sub_dsp

    def get_sub_dsp_from_workflow(self, sources, graph=None, reverse=False):
        """
        Returns the sub-dispatcher induced by the workflow from sources.

        The induced sub-dispatcher of the dsp contains the reachable nodes and
        edges evaluated with breadth-first-search on the workflow graph from
        source nodes.

        :param sources:
            Source nodes for the breadth-first-search.
            A container of nodes which will be iterated through once.
        :type sources: iterable

        :param graph:
            A directed graph where evaluate the breadth-first-search.
        :type graph: DiGraph

        :param reverse:
            If True the workflow graph is assumed as reversed.
        :type reverse: bool, optional

        :return:
            A sub-dispatcher
        :rtype: Dispatcher

        .. note::

            The sub-dispatcher edge or node attributes just point to the
            original dispatcher. So changes to the node or edge structure
            will not be reflected in the original dispatcher map while changes
            to the attributes will.

        \***********************************************************************

        **Example**:

        A dispatcher with a function `fun` and a node `a` with a default value:

        .. testsetup::
            >>> dsp = Dispatcher()
            >>> dsp.add_data(data_id='a', default_value=1)
            'a'
            >>> dsp.add_function(function_id='fun1', inputs=['a', 'b'],
            ...                  outputs=['c', 'd'])
            'fun1'
            >>> dsp.add_function(function_id='fun2', inputs=['e'],
            ...                  outputs=['c'])
            'fun2'
            >>> from dispatcher.draw import dsp2dot
            >>> from dispatcher import dot_dir
            >>> dot = dsp2dot(dsp, graph_attr={'rankdir': 'LR'})
            >>> file = 'get_sub_dsp_from_workflow/dsp.dot'
            >>> dot.save(file, dot_dir)
            '...'

        .. graphviz:: get_sub_dsp_from_workflow/dsp.dot

        Dispatch with no calls in order to have a workflow::

            >>> o = dsp.dispatch(inputs=['a', 'b'], no_call=True)[1]

        Get sub-dispatcher from workflow inputs `a` and `b`::

            >>> sub_dsp = dsp.get_sub_dsp_from_workflow(['a', 'b'])

        .. testsetup::
            >>> sub_dsp.name = 'Sub-Dispatcher'
            >>> dot = dsp2dot(sub_dsp, graph_attr={'rankdir': 'LR'})
            >>> file = 'get_sub_dsp_from_workflow/sub_dsp1.dot'
            >>> dot.save(file, dot_dir)
            '...'

        .. graphviz:: get_sub_dsp_from_workflow/sub_dsp1.dot

        Get sub-dispatcher from a workflow output `c`::

            >>> sub_dsp = dsp.get_sub_dsp_from_workflow(['c'], reverse=True)

        .. testsetup::
            >>> sub_dsp.name = 'Sub-Dispatcher (reverse workflow)'
            >>> dot = dsp2dot(sub_dsp, graph_attr={'rankdir': 'LR'})
            >>> file = 'get_sub_dsp_from_workflow/sub_dsp2.dot'
            >>> dot.save(file, dot_dir)
            '...'

        .. graphviz:: get_sub_dsp_from_workflow/sub_dsp2.dot
        """

        # define an empty dispatcher map
        sub_dsp = self.__class__()

        if not graph:  # set default graph
            graph = self.workflow

        # visited nodes used as queue
        family = OrderedDict()

        # namespace shortcuts for speed
        nodes, dmap_nodes = (sub_dsp.dmap.node, self.dmap.node)
        dlt_val, dsp_dlt_val = (sub_dsp.default_values, self.default_values)

        if not reverse:
            # namespace shortcuts for speed
            neighbors = graph.neighbors_iter
            dmap_succ = self.dmap.succ
            succ, pred = (sub_dsp.dmap.succ, sub_dsp.dmap.pred)

            def check_node_inputs(c):
                node_attr = dmap_nodes[c]

                if node_attr['type'] == 'function':
                    if set(node_attr['inputs']).issubset(family):
                        set_node_attr(c)

                        # namespace shortcuts for speed
                        s_pred = pred[c]

                        for p in node_attr['inputs']:
                            # add attributes to both representations of edge
                            succ[p][c] = s_pred[p] = dmap_succ[p][c]
                    return True

                return False

        else:
            # namespace shortcuts for speed
            neighbors = graph.predecessors_iter
            dmap_succ = self.dmap.pred
            pred, succ = (sub_dsp.dmap.succ, sub_dsp.dmap.pred)

            def check_node_inputs(c):
                return False

        # function to set node attributes
        def set_node_attr(n):
            # set node attributes
            nodes[n] = dmap_nodes[n]

            # add node in the adjacency matrix
            succ[n], pred[n] = ({}, {})

            if n in dsp_dlt_val:
                dlt_val[n] = dsp_dlt_val[n]  # set the default value

            family[n] = neighbors(n)  # append a new parent to the family

        # set initial node attributes
        for s in sources:
            if s in dmap_nodes and s in graph.node:
                set_node_attr(s)

        # start breadth-first-search
        for parent, children in iter(family.items()):

            # namespace shortcuts for speed
            nbrs, dmap_nbrs = (succ[parent], dmap_succ[parent])

            # iterate parent's children
            for child in children:

                if child == START or check_node_inputs(child):
                    continue

                if child not in family:
                    set_node_attr(child)  # set node attributes

                # add attributes to both representations of edge: u-v and v-u
                nbrs[child] = pred[child][parent] = dmap_nbrs[child]

        # return the sub-dispatcher map
        return sub_dsp

    def remove_cycles(self, sources):
        """
        Returns a new dispatcher removing unresolved cycles.

        An unresolved cycle is a cycle that cannot be removed by the
        ArciDispatch algorithm.

        :param sources:
            Input data nodes.
        :type sources: iterable

        :return:
            A new dispatcher without the unresolved cycles.
        :rtype: Dispatcher

        \***********************************************************************

        **Example**:

        A dispatcher with an unresolved cycle (i.e., `c` --> `min1` --> `d` -->
        `min2` --> `c`):

        .. testsetup::
            >>> dsp = Dispatcher()
            >>> def average(kwargs):
            ...     return sum(kwargs.values()) / len(kwargs)
            >>> data = [
            ...     {'data_id': 'b', 'default_value': 3},
            ...     {'data_id': 'c', 'wait_inputs': True, 'function': average},
            ... ]
            >>> functions = [
            ...     {
            ...         'function_id': 'max1',
            ...         'function': max,
            ...         'inputs': ['a', 'b'],
            ...         'outputs': ['c']
            ...     },
            ...     {
            ...         'function_id': 'min1',
            ...         'function': min,
            ...         'inputs': ['a', 'c'],
            ...         'outputs': ['d']
            ...     },
            ...     {
            ...         'function_id': 'min2',
            ...         'function': min,
            ...         'inputs': ['b', 'd'],
            ...         'outputs': ['c']
            ...     },
            ...     {
            ...         'function_id': 'max2',
            ...         'function': max,
            ...         'inputs': ['b', 'd'],
            ...         'outputs': ['a']
            ...     },
            ... ]
            >>> dsp.add_from_lists(data_list=data, fun_list=functions)
            ([...], [...])
            >>> from dispatcher.draw import dsp2dot
            >>> from dispatcher import dot_dir
            >>> dot = dsp2dot(dsp, graph_attr={'rankdir': 'LR'})
            >>> dot.save('remove_cycles/dsp.dot', dot_dir)
            '...'

        .. graphviz:: remove_cycles/dsp.dot

        The dispatch stops on data node `c` due to the unresolved cycle::

            >>> res = dsp.dispatch(inputs={'a': 1})[1]
            >>> sorted(res.items())
            [('a', 1), ('b', 3)]

        .. testsetup::
            >>> dot = dsp2dot(dsp, True, graph_attr={'rankdir': 'LR'})
            >>> dot.save('remove_cycles/wf.dot', dot_dir)
            '...'

        .. graphviz:: remove_cycles/wf.dot

        Removing the unresolved cycle the dispatch continues to all nodes::

            >>> dsp_rm_cycles = dsp.remove_cycles(['a', 'b'])
            >>> res = dsp_rm_cycles.dispatch(inputs={'a': 1})[1]
            >>> sorted(res.items())
            [('a', 1), ('b', 3), ('c', 3.0), ('d', 1)]

        .. testsetup::
            >>> dsp_rm_cycles.name = 'Dispatcher without unresolved cycles'
            >>> dot = dsp2dot(dsp_rm_cycles, True, graph_attr={'rankdir': 'LR'})
            >>> file = 'remove_cycles/wf_rm_cycles.dot'
            >>> dot.save(file, dot_dir)
            '...'

        .. graphviz:: remove_cycles/wf_rm_cycles.dot
        """

        # Reachable nodes from sources
        reached_nodes = set()

        # List of edges to be removed
        edge_to_remove = []

        # updates the reachable nodes and list of edges to be removed
        remove_cycles_iteration(self.dmap, iter(sources), reached_nodes,
                                edge_to_remove)

        for v in self.dmap.node.values():
            if v.pop('undo', False):
                v['wait_inputs'] = True

        # sub-dispatcher induced by the reachable nodes
        new_dmap = self.get_sub_dsp(reached_nodes, edge_to_remove)

        # return a new dispatcher without the unresolved cycles
        return new_dmap

    def dispatch(self, inputs=None, outputs=None, cutoff=None,
                 wildcard=False, no_call=False, shrink=False):
        """
        Evaluates the minimum workflow and data outputs of the dispatcher
        model from given inputs.

        :param inputs:
            Input data values.
        :type inputs: dict, iterable, optional

        :param outputs:
            Ending data nodes.
        :type outputs: iterable, optional

        :param cutoff:
            Depth to stop the search.
        :type cutoff: float, int, optional

        :param wildcard:
            If True, when the data node is used as input and target in the
            ArciDispatch algorithm, the input value will be used as input for
            the connected functions, but not as output.
        :type wildcard: bool, optional

        :param no_call:
            If True data node estimation function is not used.
        :type no_call: bool, optional

        :param shrink:
            If True the dispatcher is shrink before the dispatch.
        :type shrink: bool, optional

        :return:
            - workflow: A directed graph with data node estimations.
            - data_output: Dictionary of estimated data node outputs.
        :rtype: (DiGraph, dict)

        \***********************************************************************

        **Example**:

        A dispatcher with a function `my_log` and two data `a` and `b`
        with default values:

        .. testsetup::
            >>> dsp = Dispatcher()
            >>> dsp.add_data(data_id='a', default_value=0)
            'a'
            >>> dsp.add_data(data_id='b', default_value=5)
            'b'
            >>> dsp.add_data(data_id='d', default_value=1)
            'd'
            >>> from math import log
            >>> def my_log(a, b):
            ...     return log(b - a)
            >>> def my_domain(a, b):
            ...     return a < b
            >>> dsp.add_function('my log', function=my_log, inputs=['c', 'd'],
            ...                  outputs=['e'], input_domain=my_domain)
            'my log'
            >>> dsp.add_function('min', function=min, inputs=['a', 'b'],
            ...                  outputs=['c'])
            'min'
            >>> from dispatcher.draw import dsp2dot
            >>> from dispatcher import dot_dir
            >>> dot = dsp2dot(dsp, graph_attr={'rankdir': 'LR'})
            >>> dot.save('dispatch/dsp.dot', dot_dir)
            '...'

        .. graphviz:: dispatch/dsp.dot

        Dispatch without inputs. The default values are used as inputs::

            >>> workflow, outputs = dsp.dispatch()
            ...
            >>> sorted(outputs.items())
            [('a', 0), ('b', 5), ('c', 0), ('d', 1), ('e', 0.0)]

        .. testsetup::
            >>> dot = dsp2dot(dsp, workflow=True, graph_attr={'rankdir': 'LR'})
            >>> dot.save('dispatch/wf1.dot', dot_dir)
            '...'

        .. graphviz:: dispatch/wf1.dot

        Dispatch until data node `c` is estimated::

            >>> workflow, outputs = dsp.dispatch(outputs=['c'])
            ...
            >>> sorted(outputs.items())
             [('a', 0), ('b', 5), ('c', 0), ('d', 1)]

        .. testsetup::
            >>> dot = dsp2dot(dsp, workflow=True, graph_attr={'rankdir': 'LR'})
            >>> dot.save('dispatch/wf2.dot', dot_dir)
            '...'

        .. graphviz:: dispatch/wf2.dot

        Dispatch with one inputs. The default value of `a` is not used as
        inputs::

            >>> workflow, outputs = dsp.dispatch(inputs={'a': 3})
            ...
            >>> sorted(outputs.items())
             [('a', 3), ('b', 5), ('c', 3), ('d', 1)]

        .. testsetup::
            >>> dot = dsp2dot(dsp, workflow=True, graph_attr={'rankdir': 'LR'})
            >>> dot.save('dispatch/wf3.dot', dot_dir)
            '...'

        .. graphviz:: dispatch/wf3.dot
        """

        # pre shrink
        if not no_call and shrink:
            dsp = self.shrink_dsp(inputs, outputs, cutoff)
        else:
            dsp = self

        # initialize
        args = dsp._init_run(inputs, outputs, wildcard, cutoff, no_call)

        # return the evaluated workflow graph and data outputs
        workflow, data_outputs = dsp._run(*args[1:])

        # nodes that are out of the dispatcher nodes
        out_dsp_nodes = set(args[0]).difference(dsp.nodes)

        # add nodes that are out of the dispatcher nodes
        if inputs:
            data_outputs.update({k: inputs[k] for k in out_dsp_nodes})

        # return the evaluated workflow graph and data outputs
        return workflow, data_outputs

    def shrink_dsp(self, inputs=None, outputs=None, cutoff=None):
        """
        Returns a reduced dispatcher.

        :param inputs:
            Input data nodes.
        :type inputs: iterable, optional

        :param outputs:
            Ending data nodes.
        :type outputs: iterable, optional

        :param cutoff:
            Depth to stop the search.
        :type cutoff: float, int, optional

        :return:
            A sub-dispatcher.
        :rtype: Dispatcher

        \***********************************************************************

        **Example**:

        A dispatcher like this:

        .. testsetup::
            >>> dsp = Dispatcher()
            >>> functions = [
            ...     {
            ...         'function_id': 'fun1',
            ...         'inputs': ['a', 'b'],
            ...         'outputs': ['c']
            ...     },
            ...     {
            ...         'function_id': 'fun2',
            ...         'inputs': ['b', 'd'],
            ...         'outputs': ['e']
            ...     },
            ...     {
            ...         'function_id': 'fun3',
            ...         'function': min,
            ...         'inputs': ['d', 'f'],
            ...         'outputs': ['g']
            ...     },
            ...     {
            ...         'function_id': 'fun4',
            ...         'function': max,
            ...         'inputs': ['a', 'b'],
            ...         'outputs': ['g']
            ...     },
            ...     {
            ...         'function_id': 'fun5',
            ...         'function': max,
            ...         'inputs': ['d', 'e'],
            ...         'outputs': ['c', 'f']
            ...     },
            ... ]
            >>> dsp.add_from_lists(fun_list=functions)
            ([], [...])
            >>> from dispatcher.draw import dsp2dot
            >>> from dispatcher import dot_dir
            >>> dot = dsp2dot(dsp, graph_attr={'rankdir': 'LR'})
            >>> dot.save('shrink_dsp/dsp.dot', dot_dir)
            '...'

        .. graphviz:: shrink_dsp/dsp.dot

        Get the sub-dispatcher induced by dispatching with no calls from inputs
        `a`, `b`, and `c` to outputs `c`, `e`, and `f`::

            >>> shrink_dsp = dsp.shrink_dsp(inputs=['a', 'b', 'd'],
            ...                             outputs=['c', 'f'])

        .. testsetup::
            >>> shrink_dsp.name = 'Sub-Dispatcher'
            >>> dot = dsp2dot(shrink_dsp, graph_attr={'rankdir': 'LR'})
            >>> dot.save('shrink_dsp/shrink_dsp.dot', dot_dir)
            '...'

        .. graphviz:: shrink_dsp/shrink_dsp.dot
        """

        bfs_graph = self.dmap

        if inputs:

            self._set_wait_in()
            wait_in = self._wait_in
            edges = set()
            bfs_graph = DiGraph()

            while True:

                for k, v in wait_in.items():
                    if v and k in inputs:
                        wait_in[k] = False

                # evaluate the workflow graph without invoking functions
                wf, o = self.dispatch(inputs, outputs, cutoff, True, True)

                edges.update(wf.edges())

                n_d = (wf.node.keys() - self._visited)

                if not n_d:
                    break

                inputs = n_d.union(inputs)

            bfs_graph.add_edges_from(edges)

            if outputs is None:
                # noinspection PyUnboundLocalVariable
                outputs = o

        self._wait_in = {}

        if outputs:
            dsp = self.get_sub_dsp_from_workflow(outputs, bfs_graph, True)
        else:
            return self.__class__()

        # return the sub dispatcher
        return dsp

    def create_function_node(self, function_id, inputs, outputs, cutoff=None):
        """
        Returns a function node that uses the dispatcher map as function.

        :param function_id:
            Function node id.
            If None will be assigned as <fun.__module__>:<fun.__name__>.
        :type function_id: any hashable Python object except None

        :param inputs:
            Input data nodes.
        :type inputs: iterable

        :param outputs:
            Ending data nodes.
        :type outputs: iterable

        :param cutoff:
            Depth to stop the search.
        :type cutoff: float, int, optional

        :return:
            Function attributes.
        :rtype: dict

        \***********************************************************************

        **Example**:

        A dispatcher with two functions `max` and `min` and an unresolved cycle
        (i.e., `a` --> `max` --> `c` --> `min` --> `a`):

        .. testsetup::
            >>> dsp = Dispatcher()
            >>> dsp.add_function('max', max, inputs=['a', 'b'], outputs=['c'])
            'max'
            >>> from math import log
            >>> def my_log(x):
            ...     return log(x - 1)
            >>> dsp.add_function('log(x - 1)', my_log, inputs=['c'],
            ...                  outputs=['a'], input_domain=lambda c: c > 1)
            'log(x - 1)'
            >>> from dispatcher.draw import dsp2dot
            >>> from dispatcher import dot_dir
            >>> dot = dsp2dot(dsp, graph_attr={'rankdir': 'LR'})
            >>> dot.save('create_function_node/dsp.dot', dot_dir)
            '...'

        .. graphviz:: create_function_node/dsp.dot

        Extract a static function node, i.e. the inputs `a` and `b` and the
        output `a` are fixed::

            >>> res = dsp.create_function_node('myF', ['a', 'b'], ['a'])
            >>> res['inputs'] == ['a', 'b']
            True
            >>> res['outputs'] == ['a']
            True
            >>> res['function'].__name__
            'myF'
            >>> res['function'](2, 1)
            0.0

        .. testsetup::
            >>> dsp.name = 'Created function internal'
            >>> dsp.dispatch({'a': 2, 'b': 1}, outputs=['a'], wildcard=True)
            (...)
            >>> dot = dsp2dot(dsp, workflow=True, graph_attr={'rankdir': 'LR'})
            >>> dot.save('create_function_node/wf1.dot', dot_dir)
            '...'

        .. graphviz:: create_function_node/wf1.dot

        The created function raises a ValueError if un-valid inputs are
        provided::

            >>> res['function'](1, 0)
            Traceback (most recent call last):
            ...
            ValueError: Unreachable output-targets:{'a'}

        .. testsetup::
            >>> dsp.dispatch({'a': 1, 'b': 0}, outputs=['a'], wildcard=True)
            (...)
            >>> dot = dsp2dot(dsp, workflow=True, graph_attr={'rankdir': 'LR'})
            >>> dot.save('create_function_node/wf2.dot', dot_dir)
            '...'

        .. graphviz:: create_function_node/wf2.dot
        """

        # new shrink dispatcher
        dsp = self.shrink_dsp(inputs, outputs, cutoff=cutoff)

        # outputs not reached
        missed = set(outputs).difference(dsp.nodes)

        if missed:  # if outputs are missing raise error
            raise ValueError('Unreachable output-targets:{}'.format(missed))

        # get initial default values
        input_values = dsp._get_initial_values(None, False)

        # set wildcards
        dsp._set_wildcards(inputs, outputs)

        # define the function to populate the workflow
        def input_value(k):
            return {'value': input_values[k]}

        # define the function to return outputs sorted
        if len(outputs) > 1:
            def return_output(o):
                return [o[k] for k in outputs]
        else:
            def return_output(o):
                return o[outputs[0]]

        # define function
        @rename_function(function_id, caller_name())
        def dsp_fun(*args):
            # update inputs
            input_values.update(dict(zip(inputs, args)))

            # dispatch outputs
            o = dsp._run(*dsp._init_workflow(input_values, input_value))[1]

            try:
                # return outputs sorted
                return return_output(o)

            except KeyError:  # unreached outputs
                # raise error
                raise ValueError('Unreachable output-targets:'
                                 '{}'.format(set(outputs).difference(o)))

        # return function attributes
        return {'function': dsp_fun, 'inputs': inputs, 'outputs': outputs}

    def _check_targets(self):
        """
        Returns a function to terminate the ArciDispatch algorithm when all
        targets have been visited.

        :return:
            A function to terminate the ArciDispatch algorithm.
        :rtype: function
        """

        if self._targets:

            targets = self._targets

            def check_targets(node_id):
                """
                Terminates ArciDispatch algorithm when all targets have been
                visited.

                :param node_id:
                    Data or function node id.
                :type node_id: any hashable Python object except None

                :return:
                    True if all targets have been visited, otherwise False
                :rtype: bool
                """
                try:
                    targets.remove(node_id)  # remove visited node
                    return not targets  # if no targets terminate the algorithm
                except KeyError:  # the node is not in the targets set
                    return False
        else:
            def check_targets(node_id):
                return False

        return check_targets

    def _check_cutoff(self):
        """
        Returns a function to stop the search of the investigated node of the
        ArciDispatch algorithm.

        :return:
            A function to stop the search
        :rtype: function
        """

        if self._cutoff is not None:

            cutoff = self._cutoff

            def check_cutoff(distance):
                """
                Stops the search of the investigated node of the ArciDispatch
                algorithm.

                :param distance:
                    Distance from the starting node.
                :type distance: float, int

                :return:
                    True if distance > cutoff, otherwise False
                :rtype: bool
                """

                return distance > cutoff  # check cutoff distance

        else:  # cutoff is None.
            def check_cutoff(distance):
                return False

        return check_cutoff

    def _edge_length(self, edge, node_out):
        """
        Returns the edge length.

        The edge length is edge weight + destination node weight.

        :param edge:
            Edge attributes.
        :type edge: dict

        :param node_out:
            Node attributes.
        :type node_out: dict

        :return:
            Edge length.
        :rtype: float, int
        """

        weight = self.weight

        return edge.get(weight, 1) + node_out.get(weight, 0)

    def _get_node_estimations(self, node_attr, node_id):
        """
        Returns the data nodes estimations and `wait_inputs` flag.

        :param node_attr:
            Dictionary of node attributes.
        :type node_attr: dict

        :param node_id:
            Data node's id.
        :type node_id: any hashable Python object except None

        :return:
            - node estimations with minimum distance from the starting node, and
            - `wait_inputs` flag
        :rtype: (dict, bool)
        """

        # get data node estimations
        estimations = self._wf_pred[node_id]

        # namespace shortcut
        wait_in = node_attr['wait_inputs']

        # check if node has multiple estimations and it is not waiting inputs
        if len(estimations) > 1 and not self._wait_in.get(node_id, wait_in):
            # namespace shortcuts
            dist = self.dist
            edge_length = self._edge_length
            edg = self.dmap.edge

            est = []  # estimations' heap

            for k, v in estimations.items():  # calculate length
                if k is not START:
                    d = dist[k] + edge_length(edg[k][node_id], node_attr)
                    heappush(est, (d, k, v))

            # the estimation with minimum distance from the starting node
            estimations = {est[0][1]: est[0][2]}

            # remove unused workflow edges
            self.workflow.remove_edges_from([(v[1], node_id) for v in est[1:]])

        # return estimations and `wait_inputs` flag.
        return estimations, wait_in

    def _check_wait_input_flag(self):
        """
        Returns a function to stop the search of the investigated node of the
        ArciDispatch algorithm.

        :return:
            A function to stop the search
        :rtype: function
        """

        # namespace shortcuts
        visited = self._visited
        pred = self._pred

        if self._wait_in:
            # namespace shortcut
            we = self._wait_in.get

            def check_wait_input_flag(wait_in, node_id):
                """
                Stops the search of the investigated node of the ArciDispatch
                algorithm, until all inputs are satisfied.

                :param wait_in:
                    If True the node is waiting input estimations.
                :type wait_in: bool

                :param node_id:
                    Data or function node id.
                :type node_id: any hashable Python object except None

                :return:
                    True if all node inputs are satisfied, otherwise False
                :rtype: bool
                """

                # return true if the node inputs are satisfied
                return we(node_id, wait_in) and (pred[node_id].keys() - visited)

        else:
            def check_wait_input_flag(wait_in, node_id):
                # return true if the node inputs are satisfied
                return wait_in and (pred[node_id].keys() - visited)

        return check_wait_input_flag

    def _set_wildcards(self, inputs=None, outputs=None):
        """
        Update wildcards set with the input data nodes that are also outputs.

        :param inputs:
            Input data nodes.
        :type inputs: iterable

        :param outputs:
            Ending data nodes.
        :type outputs: iterable
        """

        # clear wildcards
        self._wildcards = set()

        if outputs:
            # namespace shortcut
            node = self.nodes

            # input data nodes that are in output_targets
            wildcards = {u: node[u] for u in inputs if u in outputs}

            # data nodes without the wildcard
            self._wildcards.update([k
                                    for k, v in wildcards.items()
                                    if v.get('wildcard', True)])

    def _set_wait_in(self):
        """
        Set `wait_inputs` flags for data nodes that:
            - are estimated from functions with a domain function, and
            - are waiting inputs.
        """
        # clear wait_in
        self._wait_in = {}

        # namespace shortcut
        wait_in = self._wait_in

        for n, a in self.nodes.items():
            # namespace shortcut
            n_type = a['type']

            if n_type == 'function' and 'input_domain' in a:  # with a domain
                # nodes estimated from functions with a domain function
                for k in a['outputs']:
                    wait_in[k] = True

            elif n_type == 'data' and a['wait_inputs']:  # is waiting inputs
                wait_in[n] = True

    def _get_initial_values(self, inputs, no_call):
        """
        Returns inputs' initial values for the ArciDispatcher algorithm.

        Initial values are the default values merged with the input values.

        :param inputs:
            Input data nodes values.
        :type inputs: iterable, None

        :param no_call:
            If True data node value is not None.
        :type no_call: bool

        :return:
            Inputs' initial values.
        :rtype: dict
        """

        if no_call:
            # set initial values
            initial_values = dict.fromkeys(self.default_values, NONE)

            # update initial values with input values
            if inputs is not None:
                initial_values.update(dict.fromkeys(inputs, NONE))
        else:
            # set initial values
            initial_values = self.default_values.copy()

            # update initial values with input values
            if inputs is not None:
                initial_values.update(inputs)

        return initial_values

    def _init_workflow(self, inputs, input_value):
        """
        Initializes workflow, visited nodes, data output, and distance.

        :param inputs:
            Input data nodes.
        :type inputs: iterable

        :param input_value:
            A function that return the input value of a given data node.
            If input_values = {'a': 'value'} then 'value' == input_value('a')
        :type input_value: function

        :return:
            - fringe: Nodes not visited, but seen.
            - seen: Distance to seen nodes.
        """

        # clear previous outputs
        self.workflow = DiGraph()
        self.data_output = {}  # estimated data node output
        self._visited = set()
        self._wf_add_edge = add_edge_fun(self.workflow)
        self._wf_pred = self.workflow.pred

        # namespace shortcuts for speed
        node_attr = self.nodes
        graph = self.dmap
        edge_weight = self._edge_length
        check_cutoff = self._check_cutoff()
        wildcards = self._wildcards
        check_wait_in = self._check_wait_input_flag()
        add_visited = self._visited.add
        wf_add_edge = self._wf_add_edge
        wf_add_node = self.workflow.add_node

        add_visited(START)  # nodes visited by the algorithm

        # dicts of distances
        self.dist, seen = ({START: -1}, {START: -1})

        # use heapq with (distance, wait, label)
        fringe = []

        # add the starting node to the workflow graph
        wf_add_node(START, type='start')

        # add initial values to fringe and seen
        for v in inputs:

            if v not in node_attr:
                continue

            wait_in = node_attr[v]['wait_inputs']  # store wait inputs flag

            # input value
            value = input_value(v)

            # add edge
            wf_add_edge(START, v, **value)

            if v in wildcards:  # check if the data node is in wildcards

                # update visited nodes
                add_visited(v)

                # add node to workflow
                wf_add_node(v)

                for w, edge_data in graph[v].items():  # see function data node
                    # set workflow
                    wf_add_edge(v, w, **value)

                    # evaluate distance
                    vw_dist = edge_weight(edge_data, node_attr[w])

                    # check the cutoff limit and if all inputs are satisfied
                    if check_cutoff(vw_dist) or check_wait_in(True, w):
                        continue  # pass the node

                    # update distance
                    seen[w] = vw_dist

                    # add node to heapq
                    heappush(fringe, (vw_dist, True, w))

                continue

            # check if all node inputs are satisfied
            if not check_wait_in(wait_in, v):
                # update distance
                seen[v] = 0

                # add node to heapq
                heappush(fringe, (0, wait_in, v))

        return fringe, seen

    def _set_node_output(self, node_id, no_call):
        """
        Set the node outputs from node inputs.

        :param node_id:
            Data or function node id.
        :type node_id: any hashable Python object except None

        :param no_call:
            If True data node estimation function is not used.
        :type no_call: bool

        :return status:
            If the output have been evaluated correctly.
        :rtype: bool
        """

        # namespace shortcuts
        node_attr = self.nodes[node_id]
        node_type = node_attr['type']

        if node_type == 'data':  # set data node
            return self._set_data_node_output(node_id, node_attr, no_call)

        elif node_type == 'function':  # det function node
            return self._set_function_node_output(node_id, node_attr, no_call)

    def _set_data_node_output(self, node_id, node_attr, no_call):
        """
        Set the data node output from node estimations.

        :param node_id:
            Data node id.
        :type node_id: any hashable Python object except None

        :param node_attr:
            Dictionary of node attributes.
        :type node_attr: dict

        :param no_call:
            If True data node estimations are not used.
        :type no_call: bool

        :return status:
            If the output have been evaluated correctly.
        :rtype: bool
        """

        # get data node estimations
        est, wait_in = self._get_node_estimations(node_attr, node_id)

        if not no_call:

            # final estimation of the node and node status
            if not wait_in:

                if 'function' in node_attr:  # evaluate output
                    try:
                        kwargs = {k: v['value'] for k, v in est.items()}
                        # noinspection PyCallingNonCallable
                        value = node_attr['function'](kwargs)
                    except Exception as ex:
                        # some error occurs
                        msg = 'Estimation error at data node ({}) ' \
                              'due to: {}'.format(node_id, ex)
                        self.warning(msg)  # raise a Warning
                        return False
                else:
                    # data node that has just one estimation value
                    value = list(est.values())[0]['value']

            else:  # use the estimation function of node
                try:
                    # dict of all data node estimations
                    kwargs = {k: v['value'] for k, v in est.items()}

                    # noinspection PyCallingNonCallable
                    value = node_attr['function'](kwargs)  # evaluate output
                except Exception as ex:
                    # is missing estimation function of data node or some error
                    msg = 'Estimation error at data node ({}) ' \
                          'due to: {}'.format(node_id, ex)
                    self.warning(msg)  # raise a Warning
                    return False

            if 'callback' in node_attr:  # invoke callback function of data node
                try:
                    # noinspection PyCallingNonCallable
                    node_attr['callback'](value)
                except Exception as ex:
                    msg = 'Callback error at data node ({}) ' \
                          'due to: {}'.format(node_id, ex)
                    self.warning(msg)  # raise a Warning

            if value is not NONE:
                # set data output
                self.data_output[node_id] = value

            # output value
            value = {'value': value}
        else:
            # set data output
            self.data_output[node_id] = NONE

            # output value
            value = {}

        # list of functions
        succ_fun = [u for u in self._succ[node_id]]

        # check if it has functions as outputs and wildcard condition
        if succ_fun and succ_fun[0] not in self._visited:
            # namespace shortcuts for speed
            wf_add_edge = self._wf_add_edge

            # set workflow
            for u in succ_fun:
                wf_add_edge(node_id, u, **value)

        # return True, i.e. that the output have been evaluated correctly
        return True

    def _set_function_node_output(self, node_id, node_attr, no_call):
        """
        Set the function node output from node inputs.

        :param node_id:
            Function node id.
        :type node_id: any hashable Python object except None

        :param node_attr:
            Dictionary of node attributes.
        :type node_attr: dict

        :param no_call:
            If True data node estimation function is not used.
        :type no_call: bool

        :return status:
            If the output have been evaluated correctly.
        :rtype: bool
        """

        # namespace shortcuts for speed
        o_nds = node_attr['outputs']
        dist = self.dist
        nodes = self.nodes

        # list of nodes that can still be estimated by the function node
        output_nodes = [u for u in o_nds
                        if (not u in dist) and (u in nodes)]

        if not output_nodes:  # this function is not needed
            self.workflow.remove_node(node_id)  # remove function node
            return False

        # namespace shortcuts for speed
        wf_add_edge = self._wf_add_edge

        if no_call:
            # set workflow out
            for u in output_nodes:
                wf_add_edge(node_id, u)
            return True

        args = self._wf_pred[node_id]  # list of the function's arguments
        args = [args[k]['value'] for k in node_attr['inputs']]
        args = [v for v in args if v is not NONE]

        try:
            # noinspection PyCallingNonCallable
            if 'input_domain' in node_attr and \
                    not node_attr['input_domain'](*args):
                # args are not respecting the domain
                return False
            else:  # use the estimation function of node
                fun = node_attr['function']

                if isinstance(fun, SubDispatch):
                    w, res = fun(*args)
                    self.workflow.add_node(
                        node_id, workflow=(w, fun.data_output, fun.dist)
                    )
                else:
                    res = fun(*args)

                # list of function results
                res = res if len(o_nds) > 1 else [res]

        except Exception as ex:
            # is missing function of the node or args are not in the domain
            msg = 'Estimation error at function node ({}) ' \
                  'due to: {}'.format(node_id, ex)
            self.warning(msg)  # raise a Warning
            return False

        # set workflow
        for k, v in zip(o_nds, res):
            if k in output_nodes:
                wf_add_edge(node_id, k, value=v)

        # return True, i.e. that the output have been evaluated correctly
        return True

    def _init_run(self, inputs, outputs, wildcard, cutoff, no_call):
        """
        Initializes workflow, visited nodes, data output, and distance.

        :param inputs:
            Input data values.
        :type inputs: dict

        :param outputs:
            Ending data nodes.
        :type outputs: iterable

        :param wildcard:
            If True, when the data node is used as input and target in the
            ArciDispatch algorithm, the input value will be used as input for
            the connected functions, but not as output.
        :type wildcard: bool, optional

        :param cutoff:
            Depth to stop the search.
        :type cutoff: float, int

        :param no_call:
            If True data node estimation function is not used.
        :type no_call: bool

        :return:
            Inputs for _run:
                - fringe: Nodes not visited, but seen.
                - seen: Distance to seen nodes.
                - no_call.
        """

        # get inputs
        inputs = self._get_initial_values(inputs, no_call)

        # clear old targets
        self._targets = set()

        # update new targets
        if outputs is not None:
            self._targets.update(outputs)

        self._cutoff = cutoff  # set cutoff parameter

        if wildcard:
            self._set_wildcards(inputs, outputs)  # set wildcards
        else:
            self._set_wildcards()  # clear wildcards

        # define f function that return the input value of a given data node
        if no_call:
            def input_value(*k):
                return {}
        else:
            def input_value(k):
                return {'value': inputs[k]}

        # initialize workflow params
        fringe, seen = self._init_workflow(inputs, input_value)

        # return inputs for _run
        return inputs, fringe, seen, no_call

    def _run(self, fringe, seen, no_call=False):
        """
        Evaluates the minimum workflow and data outputs of the dispatcher map.

        Uses a modified (ArciDispatch) Dijkstra's algorithm for evaluating the
        workflow.

        :param no_call:
            If True data node estimation function is not used.
        :type no_call: bool, optional

        :return:
            - workflow: A directed graph with data node estimations.
            - data_output: Dictionary of estimated data node outputs.
        :rtype: (DiGraph, dict)
        """

        # namespace shortcuts for speed
        node_attr = self.nodes
        graph = self.dmap
        dist = self.dist
        add_visited = self._visited.add
        set_node_output = self._set_node_output
        check_targets = self._check_targets()
        edge_weight = self._edge_length
        check_cutoff = self._check_cutoff()
        check_wait_in = self._check_wait_input_flag()

        while fringe:
            (d, _, v) = heappop(fringe)  # visit the closest available node

            # set minimum distance
            dist[v] = d

            # update visited nodes
            add_visited(v)

            # set node output
            if not set_node_output(v, no_call):
                # some error occurs or inputs are not in the function domain
                continue

            # check wildcard option and if the targets are satisfied
            if check_targets(v):
                break  # stop loop

            for w, e_data in graph[v].items():
                node = node_attr[w]  # get node attributes

                vw_d = d + edge_weight(e_data, node)  # evaluate distance

                # wait inputs flag
                wait_in = node['wait_inputs']

                # check the cutoff limit and if all node inputs are satisfied
                if check_cutoff(vw_d) or check_wait_in(wait_in, w):
                    continue  # pass the node

                if w in dist:  # the node w already estimated
                    if vw_d < dist[w]:  # error for negative paths
                        raise ValueError('Contradictory paths found: '
                                         'negative weights?')
                elif w not in seen or vw_d < seen[w]:  # check min distance to w
                    # update distance
                    seen[w] = vw_d

                    # add node to heapq
                    heappush(fringe, (vw_d, wait_in, w))

        # remove unused functions
        for n in (set(self._wf_pred) - set(self._visited)):
            if self.nodes[n]['type'] == 'function':
                self.workflow.remove_node(n)

        # return the workflow and data outputs
        return self.workflow, self.data_output
