# -*- coding: utf-8 -*-
#
# Copyright 2015 European Commission (JRC);
# Licensed under the EUPL (the 'Licence');
# You may not use this work except in compliance with the Licence.
# You may obtain a copy of the Licence at: http://ec.europa.eu/idabc/eupl

"""
It provides I/O models.

The model is defined by a Dispatcher that wraps all the functions needed.
"""

from co2mpas.dispatcher import Dispatcher
from co2mpas.functions.io import *
from co2mpas.functions.io.excel import write_to_excel, parse_excel_file
from co2mpas.functions.io.schema import validate_data

import co2mpas.dispatcher.utils as dsp_utl
from functools import partial


def load_inputs():
    """
    Defines a module to load the input file of the CO2MPAS model.

    .. dispatcher:: dsp

        >>> dsp = load_inputs()

    :return:
        The load input module.
    :rtype: SubDispatchFunction
    """

    dsp = Dispatcher(
        name='load_inputs',
        description='Loads from files the inputs for the CO2MPAS model.'
    )

    dsp.add_function(
        function=get_cache_fpath,
        inputs=['input_file_name', 'soft_validation'],
        outputs=['cache_file_name']
    )

    dsp.add_data(
        data_id='overwrite_cache',
        default_value=False,
    )

    dsp.add_function(
        function_id='load_from_cache',
        function=dsp_utl.add_args(load_from_dill, n=2),
        inputs=['overwrite_cache', 'input_file_name', 'cache_file_name'],
        outputs=['validated_data'],
        input_domain=check_cache_fpath_exists
    )

    dsp.add_function(
        function=parse_excel_file,
        inputs=['input_file_name'],
        outputs=['data'],
        input_domain=partial(check_file_format, extensions=('.xlsx', '.xls')),
        weight=10
    )

    dsp.add_function(
        function=load_from_dill,
        inputs=['input_file_name'],
        outputs=['data'],
        input_domain=partial(check_file_format, extensions=('.dill',)),
        weight=10
    )

    validate = partial(validate_data,
                       read_schema=define_data_schema(read=True),
                       cache=True)

    dsp.add_function(
        function=validate,
        inputs=['data', 'cache_file_name', 'soft_validation'],
        outputs=['validated_data']
    )

    dsp.add_data(
        data_id='select_outputs',
        default_value=False
    )

    dsp.add_function(
        function=build_input_data,
        inputs=['validated_data', 'select_outputs'],
        outputs=['input_data']
    )

    dsp.add_data(
        data_id='input_data',
        function=check_data_version
    )

    func = dsp_utl.SubDispatchFunction(
        dsp=dsp,
        function_id=dsp.name,
        inputs=['input_file_name', 'select_outputs', 'overwrite_cache',
                'soft_validation'],
        outputs=['input_data']
    )

    return func


def write_outputs():
    """
    Defines a module to write on files the outputs of the CO2MPAS model.

    .. dispatcher:: dsp

        >>> dsp = write_outputs()

    :return:
        The write outputs module.
    :rtype: SubDispatchFunction
    """

    dsp = Dispatcher(
        name='write_outputs',
        description='Writes on files the outputs of the CO2MPAS model.'
    )

    dsp.add_function(
        function=partial(convert2df,
                         data_descriptions=get_doc_description(),
                         write_schema=define_data_schema(read=False)),
        inputs=['output_data', 'start_time'],
        outputs=['dfs']
    )

    dsp.add_function(
        function=write_to_excel,
        inputs=['dfs', 'output_file_name', 'template_file_name']
    )

    return dsp_utl.SubDispatchFunction(dsp, dsp.name, ['output_file_name',
                                                       'template_file_name',
                                                       'output_data',
                                                       'start_time'])
