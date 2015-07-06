#!/usr/bin/env python
# -*- coding: UTF-8 -*-
#
# Copyright 2014 European Commission (JRC);
# Licensed under the EUPL (the 'Licence');
# You may not use this work except in compliance with the Licence.
# You may obtain a copy of the Licence at: http://ec.europa.eu/idabc/eupl

"""
It provides tools to create models with the :func:`~dispatcher.Dispatcher`.
"""

__author__ = 'Vincenzo Arcidiacono'

__all__ = ['combine_dicts', 'bypass', 'summation', 'map_dict', 'map_list',
           'selector', 'replicate_value',
           'SubDispatch', 'ReplicateFunction', 'SubDispatchFunction']

from .gen import caller_name
from networkx.classes.digraph import DiGraph
from copy import deepcopy
from dispatcher.constants import NONE


def combine_dicts(*dicts):
    """
    Combines multiple dicts in one.

    :param dicts:
        A sequence of dicts.
    :type dicts: (dict, ...)

    :return:
        A unique dict.
    :rtype: dict

    Example::

        >>> sorted(combine_dicts({'a': 3, 'c': 3}, {'a': 1, 'b': 2}).items())
        [('a', 1), ('b', 2), ('c', 3)]
    """

    if len(dicts) == 1:
        return dicts[0]

    res = {}

    for a in dicts:
        res.update(a)

    return res


def bypass(*inputs):
    """
    Returns the same arguments.

    :param inputs:
        Inputs values.
    :type inputs: (object, ...)

    :return:
        Same input values.
    :rtype: tuple, object

    Example::

        >>> bypass('a', 'b', 'c')
        ('a', 'b', 'c')
        >>> bypass('a')
        'a'
    """

    return inputs if len(inputs) > 1 else inputs[0]


def summation(*inputs):
    """
    Sums inputs values.

    :param inputs:
        Inputs values.
    :type inputs: int, float

    :return:
        Sum of the input values.
    :rtype: int, float

    Example::

        >>> summation(1, 3.0, 4, 2)
        10.0
    """

    return sum(inputs)


def map_dict(key_map, *dicts):
    """
    Returns a dict with new key values.

    :param key_map:
        A dictionary that maps the dict keys ({old key: new key}
    :type key_map: dict

    :param dicts:
        A sequence of dicts.
    :type dicts: (dict, ...)

    :return:
        A unique dict with new key values.
    :rtype: dict

    Example::

        >>> d = map_dict({'a': 'c', 'b': 'd'}, {'a': 1, 'b': 1}, {'b': 2})
        >>> sorted(d.items())
        [('c', 1), ('d', 2)]
    """

    it = combine_dicts(*dicts).items()
    get = key_map.get

    return {get(k, k): v for k, v in it}


def map_list(key_map, *inputs):
    """
    Returns a new dict

    :param key_map:
        A list that maps the dict keys ({old key: new key}
    :type key_map: [str, dict, ...]

    :param dicts:
        A sequence of dicts.
    :type dicts: (dict, ...)

    :return:
        A unique dict with new values.
    :rtype: dict

    Example::

        >>> key_map = [
        ...     'a',
        ...     {'a': 'c'},
        ...     [
        ...         'a',
        ...         {'a': 'd'}
        ...     ]
        ... ]
        >>> inputs = (
        ...     2,
        ...     {'a': 3, 'b': 2},
        ...     [
        ...         1,
        ...         {'a': 4}
        ...     ]
        ... )
        >>> d = map_list(key_map, *inputs)
        >>> sorted(d.items())
        [('a', 1), ('b', 2), ('c', 3), ('d', 4)]
    """

    d = {}

    for m, v in zip(key_map, inputs):
        if isinstance(m, dict):
            d.update(map_dict(m, v))
        elif isinstance(m, list):
            d.update(map_list(m, *v))
        else:
            d[m] = v

    return d


def selector(keys, *dicts, copy=True, output_type='dict'):
    """
    Selects the chosen dictionary keys from the given sequence of dictionaries.

    :param keys:
        Keys to select.
    :type keys: list

    :param dicts:
        Sequence of dictionaries.
    :type dicts: (dict, ...)

    :param copy:
        If True the output contains deep-copies of the values.
    :type copy: bool

    :return:
        A dictionary with chosen dictionary keys if present in the sequence of
        dictionaries. These are combined with :func:`combine_dicts`.
    :rtype: dict

    Example::

        >>> from functools import partial
        >>> fun = partial(selector, ['a', 'b'])
        >>> sorted(fun({'a': 1, 'b': 1}, {'b': 2, 'c': 3}).items())
        [('a', 1), ('b', 2)]
    """

    it = combine_dicts(*dicts)

    get = deepcopy if copy else lambda x: x

    if output_type == 'list':
        if len(keys) > 1:
            return tuple([get(it[k]) for k in keys])
        else:
            return get(it[keys[0]])

    return {k: get(v) for k, v in it.items() if k in keys}


def replicate_value(value, n=2, copy=True):
    """
    Replicates `n` times the input value.

    :param n:
        Number of replications.
    :type n: int

    :param value:
        Value to be replicated.
    :type value: object

    :param copy:
        If True the list contains deep-copies of the value.
    :type copy: bool

    :return:
        A list with the value replicated `n` times.
    :rtype: list

    Example::

        >>> from functools import partial
        >>> fun = partial(replicate_value, n=5)
        >>> fun({'a': 3})
        [{'a': 3}, {'a': 3}, {'a': 3}, {'a': 3}, {'a': 3}]
    """

    if copy:
        return [deepcopy(value) for i in range(n)]

    return [value] * n


class SubDispatch(object):
    """
    It dispatches a given :func:`~dispatcher.Dispatcher` like a function.

    This function takes a sequence of dictionaries as input that will be
    combined before the dispatching.

    :return:
        A function that executes the dispatch of the given
        :func:`~dispatcher.Dispatcher`.
    :rtype: function

    .. seealso:: :func:`~dispatcher.Dispatcher.dispatch`, :func:`combine_dicts`

    Example:

    .. dispatcher:: dsp
       :opt: graph_attr={'ratio': '1'}, level=1
       :code:

        >>> from dispatcher import Dispatcher
        >>> sub_dsp = Dispatcher()
        ...
        >>> def fun(a):
        ...     return a + 1, a - 1
        ...
        >>> sub_dsp.add_function('fun', fun, ['a'], ['b', 'c'])
        'fun'
        >>> dispatch = SubDispatch(sub_dsp, ['a', 'b', 'c'], output_type='dict')
        >>> dsp = Dispatcher()
        >>> dsp.add_function('Sub-dispatch', dispatch, ['d'], ['e'])
        'Sub-dispatch'

    Dispatch the dispatch output is:

    .. dispatcher:: dsp
       :opt: workflow=True, graph_attr={'ratio': '1'}, level=1

        >>> w, o = dsp.dispatch(inputs={'d': {'a': 3}})
        >>> sorted(o['e'].items())
        [('a', 3), ('b', 4), ('c', 2)]
        >>> w.node['Sub-dispatch']['workflow']
        (<...DiGraph object at 0x...>, {...}, {...})

    """

    def __init__(self, dsp, outputs=None, cutoff=None, wildcard=False,
                 no_call=False, shrink=True, output_type='all'):
        """
        Initializes the Sub-dispatch.

        :param dsp:
            A dispatcher that identifies the model adopted.
        :type dsp: dispatcher.Dispatcher

        :param outputs:
            Ending data nodes.
        :type outputs: iterable

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

        :params output_type:
            Type of function output:

                + 'all': a :class:`~dispatcher.utils.AttrDict` with all dispatch
                  outputs.
                + 'list': a list with all outputs listed in `outputs`.
                + 'dict': a :class:`~dispatcher.utils.AttrDict` with any outputs
                  listed in `outputs`.
        :type output_type: str
        """

        self.dsp = dsp
        self.outputs = outputs
        self.cutoff = cutoff
        self.wildcard = wildcard
        self.no_call = no_call
        self.shrink = shrink
        self.output_type = output_type
        self.data_output = {}
        self.dist = {}
        self.workflow = DiGraph()
        self.__module__ = caller_name()
        self.__name__ = dsp.name

    def __call__(self, *input_dicts):

        # combine input dictionaries
        i = combine_dicts(*input_dicts)

        # namespace shortcut
        outputs = self.outputs

        # dispatch the function calls
        w, o = self.dsp.dispatch(
            i, outputs, self.cutoff, self.wildcard, self.no_call, self.shrink
        )

        self.data_output = o
        self.dist = self.dsp.dist
        self.workflow = w

        # set output
        if self.output_type in ('list', 'dict'):
            o = selector(outputs, o, copy=False, output_type=self.output_type)

        return o


class ReplicateFunction(object):
    """
    Replicates a function.
    """
    def __init__(self, function):
        self.function = function
        self.__module__ = caller_name()
        self.__name__ = function.__name__

    def __call__(self, *inputs):
        function = self.function
        return [function(i) for i in inputs]


class SubDispatchFunction(SubDispatch):
    """
    It dispatches a given :func:`~dispatcher.Dispatcher` like a function.

    This function takes a sequence of arguments as input of the dispatch.

    :return:
        A function that executes the dispatch of the given `dsp`.
    :rtype: function

    .. seealso:: :func:`~dispatcher.Dispatcher.dispatch`,
       :func:`~dispatcher.Dispatcher.shrink_dsp`

    **Example**:

    A dispatcher with two functions `max` and `min` and an unresolved cycle
    (i.e., `a` --> `max` --> `c` --> `min` --> `a`):

    .. dispatcher:: dsp
       :opt: graph_attr={'ratio': '1'}

        >>> from dispatcher import Dispatcher
        >>> dsp = Dispatcher()
        >>> dsp.add_function('max', max, inputs=['a', 'b'], outputs=['c'])
        'max'
        >>> from math import log
        >>> def my_log(x):
        ...     return log(x - 1)
        >>> dsp.add_function('log(x - 1)', my_log, inputs=['c'],
        ...                  outputs=['a'], input_domain=lambda c: c > 1)
        'log(x - 1)'

    Extract a static function node, i.e. the inputs `a` and `b` and the
    output `a` are fixed::

        >>> fun = SubDispatchFunction(dsp, 'myF', ['a', 'b'], ['a'])
        >>> fun.__name__
        'myF'
        >>> fun(2, 1)
        0.0

    .. dispatcher:: dsp
       :opt: workflow=True, graph_attr={'ratio': '1'}

        >>> dsp = fun.dsp
        >>> dsp.name = 'Created function internal'

    The created function raises a ValueError if un-valid inputs are
    provided::

        >>> fun(1, 0)
        Traceback (most recent call last):
        ...
        ValueError: Unreachable output-targets:...

    .. dispatcher:: dsp
       :opt: workflow=True, graph_attr={'ratio': '1'}

        >>> dsp = fun.dsp
    """

    def __init__(self, dsp, function_id, inputs, outputs=None, cutoff=None):
        """
        Initializes the Sub-dispatch Function.

        :param dsp:
            A dispatcher that identifies the model adopted.
        :type dsp: dispatcher.Dispatcher

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
        """

        # new shrink dispatcher
        dsp = dsp.shrink_dsp(inputs, outputs, cutoff=cutoff)

        if outputs:
            # outputs not reached
            missed = set(outputs).difference(dsp.nodes)

            if missed:  # if outputs are missing raise error
                raise ValueError('Unreachable output-targets:{}'.format(missed))

        # get initial default values
        input_values = dsp._get_initial_values(None, False)
        self.input_values = input_values
        self.inputs = inputs

        # set wildcards
        dsp._set_wildcards(inputs, outputs)

        dsp.name = function_id
        super(SubDispatchFunction, self).__init__(
            dsp, outputs, cutoff, True, False, True, 'list')
        self.__module__ = caller_name()

        # define the function to populate the workflow
        self.input_value = lambda k: {'value': input_values[k]}

        # define the function to return outputs sorted
        if outputs is None:
            def return_output(o):
                return o
        elif len(outputs) > 1:
            def return_output(o):
                return [o[k] for k in outputs]
        else:
            def return_output(o):
                return o[outputs[0]]
        self.return_output = return_output

    def __call__(self, *args):
        # namespace shortcuts
        input_values = self.input_values
        dsp = self.dsp

        # update inputs
        input_values.update(dict(zip(self.inputs, args)))

        # dispatch outputs
        w, o = dsp._run(*dsp._init_workflow(input_values, self.input_value))

        self.data_output = o
        self.dist = dsp.dist
        self.workflow = w

        try:
            # return outputs sorted
            return self.return_output(o)

        except KeyError:  # unreached outputs
            # raise error
            raise ValueError('Unreachable output-targets:'
                             '{}'.format(set(self.outputs).difference(o)))


class Semafore(object):
    def __init__(self, domain):
        self.domain = domain
        self.status = 'red'
        self.group = {self}
        self.node_id = None

    def new(self):
        new = self.__class__(self.domain)
        self.connect(new)
        return new

    def connect(self, other):
        self.group.add(other)

        for v in self.group:
            v.group = self.group
            v.group = self.kwargs

    def disconnect(self, other=None):
        if other is None:
            other = self

        self.group.remove(other)

        for v in self.group:
            v.group = self.group

        other.group = {other}

    def __call__(self, kwargs, node_id):
        if self.status == 'green':
            return True

        if self.domain(kwargs):
            for s in self.group:
                if s.status == 'red':
                    s.status = 'green'

        else:
            self.status = 'yellow'
            self.node_id = node_id

        return self.status == 'green'


class SubDispatcher(SubDispatchFunction):
    """
    It dispatches a given :func:`~dispatcher.Dispatcher` like a function.

    This function takes a sequence of arguments as input of the dispatch.

    :return:
        A function that executes the dispatch of the given `dsp`.
    :rtype: function

    .. seealso:: :func:`~dispatcher.Dispatcher.dispatch`,
       :func:`~dispatcher.Dispatcher.shrink_dsp`

    **Example**:

    A dispatcher with two functions `max` and `min` and an unresolved cycle
    (i.e., `a` --> `max` --> `c` --> `min` --> `a`):

    .. dispatcher:: dsp
       :opt: graph_attr={'ratio': '1'}

        >>> from dispatcher import Dispatcher
        >>> dsp = Dispatcher()
        >>> dsp.add_function('max', max, inputs=['a', 'b'], outputs=['c'])
        'max'
        >>> from math import log
        >>> def my_log(x):
        ...     return log(x - 1)
        >>> dsp.add_function('log(x - 1)', my_log, inputs=['c'],
        ...                  outputs=['a'], input_domain=lambda c: c > 1)
        'log(x - 1)'

    Extract a static function node, i.e. the inputs `a` and `b` and the
    output `a` are fixed::

        >>> fun = SubDispatchFunction(dsp, 'myF', ['a', 'b'], ['a'])
        >>> fun.__name__
        'myF'
        >>> fun(2, 1)
        0.0

    .. dispatcher:: dsp
       :opt: workflow=True, graph_attr={'ratio': '1'}

        >>> dsp = fun.dsp
        >>> dsp.name = 'Created function internal'

    The created function raises a ValueError if un-valid inputs are
    provided::

        >>> fun(1, 0)
        Traceback (most recent call last):
        ...
        ValueError: Unreachable output-targets:...

    .. dispatcher:: dsp
       :opt: workflow=True, graph_attr={'ratio': '1'}

        >>> dsp = fun.dsp
    """

    def __init__(self, dsp, inputs, outputs):
        """
        Initializes the Sub-dispatch Function.

        :param dsp:
            A dispatcher that identifies the model adopted.
        :type dsp: dispatcher.Dispatcher

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
        """

        super(SubDispatcher, self).__init__(
            dsp, dsp.name, inputs.values(), outputs.values()
        )
        self.mapping = {}
        self.mapping.update(inputs)
        self.mapping.update(outputs)

        # namespace shortcuts
        input_values = self.input_values
        init_wf = self.dsp._init_workflow

        # remove default values that are in inputs
        for k in self.inputs:
            input_values.pop(k, None)

        # dispatch outputs
        self.args = list(init_wf(input_values, self.input_value))
        self.to_add = {}

    def add_collected_inputs(self):
        d = self.to_add
        remove = d.pop
        added = False
        for data_id, dist in list(d.intems()):
            args = self.args[:-1] + [data_id, self.input_value, dist]

            if dsp._add_initial_value(*args):
                remove(data_id)
                added = True
        return added

    def append(self, data_id, value, dist):
        try:
            data_id = self.mapping[data_id]
            if not data_id in self.input_values:
                # update inputs
                self.input_values[data_id] = value
                self.to_add[data_id] = dist
        except KeyError:
            pass

    def update(self, cutoff):
        dsp = self.dsp

        # update cutoff
        dsp._cutoff = cutoff
        self.args[2] = dsp._check_cutoff()

        # add new inputs and run the dispatch
        if self.add_collected_inputs():
            dsp._run(*self.args)

    def clear(self):
        # namespace shortcuts
        input_values = self.input_values
        init_wf = self.dsp._init_workflow

        # get default initial values
        input_values.clear()
        dlt = self.dsp._get_initial_values(None, False)

        for k in self.inputs:
            dfl.pop(k, None)

        input_values.update(dlt)
        # dispatch outputs
        self.args = list(init_wf(input_values, self.input_value))
        self.to_add = {}

    def __call__(self, *args):
        self.update(None)
        dsp = self.dsp
        w, o, d = dsp.workflow, dsp.data_output, dsp.dist

        self.data_output = o
        self.dist = d
        self.workflow = w
        # define the function to return outputs sorted
        if len(self.outputs) > 1:
            return [o[k] if k in o else NONE for k in outputs]
        else:
            return o[outputs[0]] if outputs[0] in o else NONE

from collections import namedtuple

SubDispatcherNode = namedtuple('SubDispatcherNode', ['dsp', 'node'])