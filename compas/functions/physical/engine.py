__author__ = 'Vincenzo Arcidiacono'

from math import pi
import numpy as np
from sklearn.ensemble import  GradientBoostingRegressor
from compas.functions.physical.constants import *
from compas.functions.physical.utils import bin_split, reject_outliers
from functools import partial
from scipy.integrate import trapz
from compas.dispatcher.utils import pairwise


def identify_idle_engine_speed_out(velocities, engine_speeds_out):
    """
    Identifies engine speed idle.

    :param velocities:
        Velocity vector [km/h].
    :type velocities: np.array

    :param engine_speeds_out:
        Engine speed vector.
    :type engine_speeds_out: np.array

    :returns:
        - Engine speed idle.
        - Its standard deviation.
    :rtype: (float, float)
    """

    x = engine_speeds_out[
        velocities < VEL_EPS & engine_speeds_out > MIN_ENGINE_SPEED]

    idle_speed = bin_split(x, bin_std=(0.01, 0.3))[1][0]

    return idle_speed[-1], idle_speed[1]


def identify_upper_bound_engine_speed(
        gears, engine_speeds_out, idle_engine_speed):
    """
    Identifies upper bound engine speed.

    It is used to correct the gear prediction for constant accelerations (see
    :func:`compas.functions.physical.AT_gear.
    correct_gear_upper_bound_engine_speed`).

    This is evaluated as the median value plus 0.67 standard deviation of the
    filtered cycle engine speed (i.e., the engine speeds when engine speed >
    minimum engine speed plus 0.67 standard deviation and gear < maximum gear).

    :param gears:
        Gear vector.
    :type gears: np.array

    :param engine_speeds_out:
        Engine speed vector.
    :type engine_speeds_out: np.array

    :param idle_engine_speed:
        Engine speed idle median and std.
    :type idle_engine_speed: (float, float)

    :returns:
        Upper bound engine speed.
    :rtype: float

    .. note:: Assuming a normal distribution then about 68 percent of the data
       values are within 0.67 standard deviation of the mean.
    """

    max_gear = max(gears)

    idle_speed = idle_engine_speed[1]

    dom = (engine_speeds_out > idle_speed) & (gears < max_gear)

    m, sd = reject_outliers(engine_speeds_out[dom])

    return m + sd * 0.674490


def calculate_piston_speeds(engine_stroke, engine_speeds_out):
    """
    Calculates piston speed.

    :param engine_stroke:
        Engine stroke.
    :type engine_stroke: np.array, float

    :param engine_speeds_out:
        Engine speed [RPM].
    :type engine_speeds_out: np.array, float

    :return:
        Engine piston speed.
    :rtype: np.array, float
    """

    return engine_speeds_out / 60 * 2 * engine_stroke / 1000


def calculate_braking_powers(
        engine_speeds_out, engine_torques_in, piston_speeds,
        engine_loss_parameters, engine_capacity):
    """
    Calculates braking power.

    :param engine_speeds_out:
        Engine speed.
    :type engine_speeds_out: np.array

    :param engine_torques_in:
        Engine torque out.
    :type engine_torques_in: np.array

    :param piston_speeds:
        Piston speed.
    :type piston_speeds: np.array

    :param engine_loss_parameters:
        Engine parameter (loss, loss2).
    :type engine_loss_parameters: (float, float)

    :param engine_capacity:
        Engine capacity.
    :type engine_capacity: float

    :return:
        Braking powers.
    :rtype: np.array
    """

    loss, loss2 = engine_loss_parameters
    cap, es = engine_capacity, engine_speeds_out

    # indicative_friction_powers
    friction_powers = ((loss2 * piston_speeds ** 2 + loss) * es * cap) / 1200000

    bp = engine_torques_in * engine_speeds_out * (pi / 30000)

    bp[bp < friction_powers] = 0

    return bp


def calibrate_engine_temperature_regression_model(
        engine_temperatures, velocities, wheel_powers, engine_speeds_out):
    """
    Calibrates an engine temperature regression model to predict engine
    temperatures.

    This model returns the delta temperature function of temperature (previous),
    acceleration, and power at the wheel.

    :param engine_temperatures:
        Engine temperature vector [°C].
    :type engine_temperatures: np.array

    :param velocities:
        Velocity vector [km/h].
    :type velocities: np.array

    :param wheel_powers:
        Power at the wheels [kW].
    :type wheel_powers: np.array

    :param engine_speeds_out:
        Engine speed [RPM].
    :type engine_speeds_out: np.array

    :return:
        The calibrated engine temperature regression model.
    :rtype: sklearn.ensemble.GradientBoostingRegressor
    """

    temp = np.zeros(engine_temperatures.shape)
    temp[1:] = engine_temperatures[:-1]

    kw = {
        'random_state': 0,
        'max_depth': 2,
        'n_estimators': int(min(300, 0.25 * (len(temp) - 1)))
    }

    model = GradientBoostingRegressor(**kw)

    X = list(zip(temp, velocities, wheel_powers, engine_speeds_out))

    model.fit(X[1:], np.diff(engine_temperatures))

    return model


def predict_engine_temperatures(
        model, velocities, wheel_powers, engine_speeds_out,
        initial_temperature):
    """
    Predicts the engine temperature.

    :param model:
        Engine temperature regression model.
    :type model: sklearn.ensemble.GradientBoostingRegressor

    :param velocities:
        Velocity vector [km/h].
    :type velocities: np.array

    :param wheel_powers:
        Power at the wheels [kW].
    :type wheel_powers: np.array

    :param engine_speeds_out:
        Engine speed [RPM].
    :type engine_speeds_out: np.array

    :param initial_temperature:
        Engine initial temperature [°C]
    :type initial_temperature: float

    :return:
        Engine temperature vector [°C].
    :rtype: np.array
    """

    predict = model.predict
    it = zip(velocities[:-1], wheel_powers[:-1], engine_speeds_out[:-1])

    temp = [initial_temperature]
    for v, p, e in it:
        temp.append(temp[-1] + predict([[temp[-1], v, p, e]])[0])

    return np.array(temp)


def calculate_normalized_engine_speeds_out(engine_speeds_out, engine_stroke):

    return (engine_stroke / 30000) * engine_speeds_out  # [m/sec]


def calculate_normalized_engine_temperatures(
        engine_temperatures, temperature_target):

    T = (engine_temperatures + 273) / (temperature_target + 273)

    T[T > 1] = 1

    return T


def calculate_normalized_engine_powers_out(
        engine_speeds_out, engine_powers_out, engine_capacity):

    p = (1200000 / engine_capacity) * engine_powers_out / engine_speeds_out

    return np.nan_to_num(p)  # BMEP [bar]


def _ABC(params, n_speeds, n_powers, n_temperatures):

    p = params

    B = p['a'] + (p['b'] + p['c'] * n_speeds) * n_speeds
    C = np.power(n_temperatures, -p['t']) * (p['l'] + p['l2'] * n_speeds**2)
    C -= n_powers

    if p['a2'] == 0 and p['b2'] == 0:
        return -C / B, B

    A_2 = (p['a2'] + p['b2'] * n_speeds)

    v = np.sqrt(np.abs(B**2 - 2 * A_2 * C))

    return (-B + v) / A_2, v


def calculate_fuel_consumptions(
        engine_speeds_out, engine_powers_out, normalized_engine_speeds_out,
        normalized_engine_powers_out, normalized_engine_temperatures,
        engine_fuel_lower_heating_value, idle_engine_speed, engine_stroke,
        engine_capacity, params):

    p = {
        'a2': -0.0008513081016491450000000 * 2,
        'b2': 0 * 2,
        'a': 0.4008202804136560000000000,
        'b': 0.045379155511281064,
        'c': -0.002629032788415591,
        'l': -1.0531830384713001,
        'l2': -0.026090627593754138,
        't': 3
    }
    p.update(params)

    n_speeds = normalized_engine_speeds_out
    n_powers = normalized_engine_powers_out
    n_temperatures = normalized_engine_temperatures
    lhv = engine_fuel_lower_heating_value

    ABC = partial(_ABC, p)

    fc = ABC(n_speeds, n_powers, n_temperatures)[0]  # FMEP [bar]

    fc *= engine_speeds_out * (engine_capacity / (lhv * 1200))  # [g/sec]

    engine_cm_idle = idle_engine_speed[0] * engine_stroke / 30000

    engine_wfb_idle, engine_wfa_idle = ABC(engine_cm_idle, 0, 1)
    engine_wfa_idle = (3600000 / lhv) / engine_wfa_idle
    engine_wfb_idle *= (3 * engine_capacity / lhv * idle_engine_speed[0])

    ec_P0 = -engine_wfb_idle / engine_wfa_idle

    fc[(engine_powers_out <= ec_P0) | (engine_speeds_out == 0) | (fc < 0)] = 0

    return np.nan_to_num(fc)  # [g/sec]


def calculate_cumulative_fuels(
        times, engine_fuel_consumptions, fuel_integration_times):

    fuels = []

    for t0, t1 in pairwise(fuel_integration_times):
        b = (t0 <= times) & (times < t1)
        fuels.append(trapz(engine_fuel_consumptions[b], times[b]))

    return fuels
