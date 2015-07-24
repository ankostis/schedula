#-*- coding: utf-8 -*-
#
# Copyright 2015 European Commission (JRC);
# Licensed under the EUPL (the 'Licence');
# You may not use this work except in compliance with the Licence.
# You may obtain a copy of the Licence at: http://ec.europa.eu/idabc/eupl

"""
The gear box model.

Sub-Modules:

.. currentmodule:: compas.models.physical.gear_box

.. autosummary::
    :nosignatures:
    :toctree: gear_box/

    thermal
    AT_gear
"""

__author__ = 'Arcidiacono Vincenzo'
from compas.dispatcher import Dispatcher
from compas.functions.physical.gear_box import *
from compas.dispatcher.utils import bypass
from compas.functions.physical.gear_box import get_gear_box_efficiency_constants


def _gear_box():

    gear_box = Dispatcher(
        name='Gear box model',
        description='Calculates forces and power acting on the vehicle.'
    )

    gear_box.add_function(
        function=identify_gears,
        inputs=['times', 'velocities', 'accelerations', 'engine_speeds_out',
                'velocity_speed_ratios', 'idle_engine_speed'],
        outputs=['gears']
    )

    gear_box.add_function(
        function=get_gear_box_efficiency_constants,
        inputs=['gear_box_type'],
        outputs=['gear_box_efficiency_constants'],
    )

    gear_box.add_function(
        function=calculate_gear_box_efficiency_parameters_cold_hot,
        inputs=['gear_box_efficiency_constants', 'engine_max_torque'],
        outputs=['gear_box_efficiency_parameters_cold_hot'],
    )

    gear_box.add_function(
        function=calculate_gear_box_torques,
        inputs=['gear_box_powers_out', 'gear_box_speeds_in', 
                'gear_box_speeds_out'],
        outputs=['gear_box_torques'],
    )

    gear_box.add_data(
        data_id='temperature_references',
        default_value=(40, 80)
    )

    gear_box.add_function(
        function=calculate_gear_box_torques_in,
        inputs=['gear_box_torques', 'gear_box_speeds_in',
                'gear_box_speeds_out', 'gear_box_temperatures',
                'gear_box_efficiency_parameters_cold_hot', 
                'temperature_references'],
        outputs=['gear_box_torques_in<0>']
    )

    gear_box.add_function(
        function=correct_gear_box_torques_in,
        inputs=['gear_box_torques', 'gear_box_torques_in<0>', 'gears',
                'gear_box_ratios'],
        outputs=['gear_box_torques_in'],
    )

    gear_box.add_function(
        function=bypass,
        inputs=['gear_box_torques_in<0>'],
        outputs=['gear_box_torques_in'],
        weight=100,
    )

    gear_box.add_function(
        function=calculate_gear_box_efficiencies_v2,
        inputs=['gear_box_powers_out', 'gear_box_speeds_in', 
                'gear_box_speeds_out', 'gear_box_torques', 
                'gear_box_torques_in'],
        outputs=['gear_box_efficiencies'],
    )

    gear_box.add_function(
        function=calculate_torques_losses,
        inputs=['gear_box_torques_in', 'gear_box_torques'],
        outputs=['gear_box_torque_losses'],
    )

    gear_box.add_function(
        function=calculate_gear_box_efficiencies,
        inputs=['gear_box_powers_out', 'gear_box_speeds_in',
                'gear_box_speeds_out', 'gear_box_torques',
                'gear_box_efficiency_parameters_cold_hot',
                'equivalent_gear_box_heat_capacity',
                'engine_thermostat_temperature', 'temperature_references',
                'initial_gear_box_temperature', 'gears', 'gear_box_ratios'],
        outputs=['gear_box_efficiencies', 'gear_box_torques_in',
                 'gear_box_temperatures'],
        weight=50
    )

    gear_box.add_function(
        function=calculate_gear_box_efficiencies,
        inputs=['gear_box_powers_out', 'gear_box_speeds_in',
                'gear_box_speeds_out', 'gear_box_torques',
                'gear_box_efficiency_parameters_cold_hot',
                'equivalent_gear_box_heat_capacity',
                'engine_thermostat_temperature', 'temperature_references',
                'initial_gear_box_temperature'],
        outputs=['gear_box_efficiencies', 'gear_box_torques_in',
                 'gear_box_temperatures'],
        weight=100
    )

    gear_box.add_function(
        function=calculate_gear_box_speeds_in,
        inputs=['gears', 'velocities', 'velocity_speed_ratios'],
        outputs=['gear_box_speeds_in'],
        weight=100
    )

    gear_box.add_function(
        function=calculate_gear_box_speeds_in_v1,
        inputs=['gears', 'gear_box_speeds_out', 'gear_box_ratios'],
        outputs=['gear_box_speeds_in']
    )

    gear_box.add_function(
        function=calculate_speed_velocity_ratios,
        inputs=['gear_box_ratios', 'final_drive_ratio', 'r_dynamic'],
        outputs=['speed_velocity_ratios']
    )

    gear_box.add_function(
        function=identify_speed_velocity_ratios,
        inputs=['gears', 'velocities', 'gear_box_speeds_in'],
        outputs=['velocity_speed_ratios'],
        weight=5
    )

    gear_box.add_function(
        function=identify_speed_velocity_ratios,
        inputs=['gears', 'velocities', 'engine_speeds_out'],
        outputs=['velocity_speed_ratios'],
        weight=10
    )

    gear_box.add_function(
        function=calculate_velocity_speed_ratios,
        inputs=['speed_velocity_ratios'],
        outputs=['velocity_speed_ratios'],
        weight=15
    )

    gear_box.add_function(
        function=identify_velocity_speed_ratios,
        inputs=['gear_box_speeds_in', 'velocities', 'idle_engine_speed'],
        outputs=['velocity_speed_ratios'],
        weight=20
    )

    gear_box.add_function(
        function=calculate_gear_box_powers_in,
        inputs=['gear_box_torques_in', 'gear_box_speeds_in'],
        outputs=['gear_box_powers_in']
    )

    return gear_box


def gear_box_calibration():
    """
    Define the gear box calibration model.

    .. dispatcher:: dsp

        >>> dsp = gear_box_calibration()

    :return:
        The gear box calibration model.
    :rtype: Dispatcher
    """

    gear_box_calibration = _gear_box()

    from .AT_gear import AT_gear

    at = AT_gear()

    gear_box_calibration.add_from_lists(
        data_list=[{'data_id': k, 'default_value': v}
                   for k, v in at.default_values.items()]
    )

    gear_box_calibration.add_dispatcher(
        dsp=at,
        dsp_id='AT_gear_shifting',
        inputs={
            'accelerations': 'accelerations',
            'engine_speeds_out': 'engine_speeds_out',
            'fuel_type': 'fuel_type',
            'gears': 'identified_gears',
            'gear_box_powers_out': 'gear_box_powers_out',
            'idle_engine_speed': 'idle_engine_speed',
            'max_engine_power': 'max_engine_power',
            'max_engine_speed_at_max_power': 'max_engine_speed_at_max_power',
            'road_loads': 'road_loads',
            'engine_temperatures': 'engine_temperatures',
            'time_cold_hot_transition': 'time_cold_hot_transition',
            'times': 'times',
            'upper_bound_engine_speed': 'upper_bound_engine_speed',
            'vehicle_mass': 'inertia',
            'velocities': 'velocities',
            'velocity_speed_ratios': 'velocity_speed_ratios',
        },
        outputs={
            'correct_gear': 'correct_gear',
            'CMV': 'CMV',
            'CMV_Cold_Hot': 'CMV_Cold_Hot',
            'DT_VA': 'DT_VA',
            'DT_VAT': 'DT_VAT',
            'DT_VAP': 'DT_VAP',
            'DT_VATP': 'DT_VATP',
            'GSPV': 'GSPV',
            'GSPV_Cold_Hot': 'GSPV_Cold_Hot',
            'CMV_error_coefficients': 'CMV_error_coefficients',
            'CMV_Cold_Hot_error_coefficients': 'CMV_Cold_Hot_error_coefficients',
            'DT_VA_error_coefficients': 'DT_VA_error_coefficients',
            'DT_VAT_error_coefficients': 'DT_VAT_error_coefficients',
            'DT_VAP_error_coefficients': 'DT_VAP_error_coefficients',
            'DT_VATP_error_coefficients': 'DT_VATP_error_coefficients',
            'GSPV_error_coefficients': 'GSPV_error_coefficients',
            'GSPV_Cold_Hot_error_coefficients': 'GSPV_Cold_Hot_error_coefficients',
        }
    )
    return gear_box_calibration


def gear_box_prediction():
    """
    Define the gear box prediction model.

    .. dispatcher:: dsp

        >>> dsp = gear_box_prediction()

    :return:
        The gear box prediction model.
    :rtype: Dispatcher
    """

    gear_box_prediction = _gear_box()

    from .AT_gear import AT_gear

    at = AT_gear()

    gear_box_prediction.add_from_lists(
        data_list=[{'data_id': k, 'default_value': v}
                   for k, v in at.default_values.items()]
    )

    gear_box_prediction.add_dispatcher(
        dsp=at,
        dsp_id='AT_gear_shifting',
        inputs={
            'correct_gear': 'correct_gear',
            'CMV': 'CMV',
            'CMV_Cold_Hot': 'CMV_Cold_Hot',
            'DT_VA': 'DT_VA',
            'DT_VAT': 'DT_VAT',
            'DT_VAP': 'DT_VAP',
            'DT_VATP': 'DT_VATP',
            'GSPV': 'GSPV',
            'GSPV_Cold_Hot': 'GSPV_Cold_Hot',
            'accelerations': 'accelerations',
            'gear_box_powers_out': 'gear_box_powers_out',
            'engine_temperatures': 'engine_temperatures',
            'time_cold_hot_transition': 'time_cold_hot_transition',
            'times': 'times',
            'velocities': 'velocities',
        },
        outputs={
            'gears': 'gears',
        }
    )

    return gear_box_prediction
