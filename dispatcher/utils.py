#!/usr/bin/env python
# -*- coding: UTF-8 -*-
#
# Copyright 2014 European Commission (JRC);
# Licensed under the EUPL (the 'Licence');
# You may not use this work except in compliance with the Licence.
# You may obtain a copy of the Licence at: http://ec.europa.eu/idabc/eupl

__author__ = 'Vincenzo Arcidiacono'

import inspect
from itertools import tee
from heapq import heappop

__all__ = ['Token', 'pairwise', 'heap_flush', 'rename_function', 'AttrDict']


class Token(str):
    """
    Token.
    """
    def __repr__(self):
        return self

    def __eq__(self, other):
        return self is other

    def __ne__(self, other):
        return self is not other

    def __hash__(self):
        return id(self)


def pairwise(iterable):
    """
    s -> (s0, s1), (s1, s2), (s2, s3), .

    :param iterable:
        An iterable object.
    :type iterable: iterable

    :return:
        A zip object.
    :rtype: zip
    """

    a, b = tee(iterable)

    next(b, None)

    return zip(a, b)


def heap_flush(heap):
    """
    Returns an ordered list of heap elements.

    :param heap:
        Fibonacci heap.
    :type heap: list

    :return:
        A list of elements sorted in descending order.
    :rtype: list

    Example::

        >>> from heapq import heappush
        >>> heap = []
        >>> heappush(heap, 3)
        >>> heappush(heap, 1)
        >>> heappush(heap, 2)
        >>> heap_flush(heap)
        [1, 2, 3]
    """

    ordered_list = []

    while heap:
        ordered_list.append(heappop(heap))

    return ordered_list


def rename_function(new_name, module_name=None):
    """
    Decorator to rename a function.

    :param new_name:
        New name of the function.
    :type new_name: str

    :return:
        Renamed function.
    :rtype: function

    Example::

        >>> @rename_function('new name')
        ... def f():
        ...     pass
        >>> f.__name__
        'new name'
    """
    if module_name is not None:
        def decorator(f):
            f.__name__ = new_name
            f.__module__ = module_name
            return f
    else:
        def decorator(f):
            f.__name__ = new_name
            return f

    return decorator


class AttrDict(dict):
    """

    Example::

        >>> d = AttrDict({'a': 3, 'b': 4})
        >>> d.a
        'a'
        >>> d.pop('b')
        4
        >>> c = d.copy()
        >>> d.popitem()
        ('a', 3)
        >>> c.a
        'a'
        >>> c.clear()
    """

    def __init__(self, *args, **kwargs):
        super(AttrDict, self).__init__(*args, **kwargs)
        self.__dict__ = {k: k
                         for k in self
                         if isinstance(k, str) and k.isidentifier()}

    def __setitem__(self, key, value):
        super(AttrDict, self).__setitem__(key, value)
        if isinstance(key, str) and key.isidentifier():
            self.__dict__[key] = key

    def __delitem__(self, key):
        super(AttrDict, self).__delitem__(key)
        self.__dict__.pop(key, None)

    def pop(self, k, d=None):
        self.__dict__.pop(k, None)
        return super(AttrDict, self).pop(k, d)

    def popitem(self):
        k, v = super(AttrDict, self).popitem()
        self.__dict__.pop(k, None)
        return k, v

    def clear(self):
        super(AttrDict, self).clear()
        self.__dict__ = {}

    def copy(self):
        return AttrDict(super(AttrDict, self).copy())



def caller_name(skip=2):
    """Get a name of a caller in the format module.class.method

       `skip` specifies how many levels of stack to skip while getting caller
       name. skip=1 means "who calls me", skip=2 "who calls my caller" etc.

       An empty string is returned if skipped levels exceed stack height
    """

    stack = inspect.stack()
    start = 0 + skip
    if len(stack) < start + 1:
      return ''
    parentframe = stack[start][0]

    name = []
    module = inspect.getmodule(parentframe)
    # `modname` can be None when frame is executed directly in console
    # TODO(techtonik): consider using __main__
    if module:
        name.append(module.__name__)
    # detect classname
    if 'self' in parentframe.f_locals:
        # I don't know any way to detect call from the object method
        # XXX: there seems to be no way to detect static method call - it will
        #      be just a function call
        name.append(parentframe.f_locals['self'].__class__.__name__)
    codename = parentframe.f_code.co_name
    if codename != '<module>':  # top level usually
        name.append( codename ) # function or a method
    del parentframe
    return ".".join(name)
