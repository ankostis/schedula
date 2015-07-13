__author__ = 'iMac2013'
from math import pi
from compas.functions.constants import *
from compas.functions.utils import bin_split, reject_outliers


def identify_idle_engine_speed_out(velocities, engine_speeds_out):
    """
    Identifies engine speed idle.

    :param velocities:
        Velocity vector.
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
    :func:`compas.functions.AT_gear.correct_gear_upper_bound_engine_speed`).

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
        Engine speed.
    :type engine_speeds_out: np.array, float

    :return:
        Engine piston speed.
    :rtype: np.array, float
    """

    return engine_speeds_out / 60 * 2 * engine_stroke / 1000


def calculate_braking_powers(
        engine_speeds_out, gear_box_torques_in, piston_speeds,
        engine_loss_parameters, engine_capacity):
    """
    Calculates braking power.

    :param engine_speeds_out:
        Engine speed.
    :type engine_speeds_out: np.array

    :param gear_box_torques_in:
        Gearbox torque in.
    :type gear_box_torques_in: np.array

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

    bp = gear_box_torques_in * engine_speeds_out * (pi / 30000)

    bp[bp < friction_powers] = 0

    return bp


# ##############################################################################
'''
def evaluate_engine_speed(
        engine_speed_idle, engine_speed_min, engine_speed_idle_add_start,
        engine_therma_start, engine_therma_thres, logical_idling,
        previous_logical_idling,
        gearbox_speed_out, next_gearbox_speed_out, acceleration,
        previous_temperature, engine_status):
    """
    Calculates engine speed.

    :param engine_speed_idle:
        Engine idling speed.
    :type engine_speed_idle: float

    :param engine_speed_min:
        Engine minimum speed.
    :type engine_speed_min: float

    :param engine_speed_idle_add_start:
        Additional starting RPM.
    :type engine_speed_idle_add_start: float

    :param engine_therma_start:
        Engine starting temperature.
    :type engine_therma_start: float

    :param engine_therma_thres:
        Engine temperature threshold.
    :type engine_therma_thres: float

    :param logical_idling:
        Logical idling.
    :type logical_idling: binary

    :param previous_logical_idling:
        Previous step's logical idling.
    :type previous_logical_idling: binary

    :param gearbox_speed_out:
        Gearbox speed out.
    :type gearbox_speed_out: float

    :param next_gearbox_speed_out:
        Next step's gearbox speed out.
    :type next_gearbox_speed_out: float

    :param acceleration:
        Acceleration.
    :type acceleration: float

    :param previous_temperature:
        Previous step's temperature.
    :type previous_temperature: float

    :param engine_status:
        Engine status.
    :type engine_status: binary

    :return:
        Engine speed.
    :rtype: float
    """

    if logical_idling == 1:
        if (gearbox_speed_out == 0 and next_gearbox_speed_out > 0) or (
                        gearbox_speed_out > 0 and next_gearbox_speed_out == 0):
            rpm1 = engine_speed_idle + 0.9 * np.abs(
                engine_speed_min - gearbox_speed_out)
        else:
            rpm1 = engine_speed_idle
    else:
        if gearbox_speed_out < engine_speed_min and acceleration >= 0:
            rpm1 = engine_speed_min + 0.9 * (
                engine_speed_min - gearbox_speed_out)
        else:
            rpm1 = gearbox_speed_out

    if previous_temperature < 30 and previous_logical_idling == 1:
        if engine_speed_idle_add_start > 0:
            rpm2 = engine_speed_idle_add_start * (
                np.abs(previous_temperature - 30) / np.abs(
                    30 - engine_therma_start))
        else:
            rpm2 = (273 + engine_therma_thres) / (
                273 + previous_temperature) * 320
    else:
        rpm2 = 0

    return (rpm1 + rpm2) * engine_status

def evaluate_engine_speed_(
        idle_engine_speed, engine_speed_idle_add_start,
        engine_therma_start, engine_therma_thres, logical_idling,
        previous_logical_idling,
        gear_box_speed_in, next_gearbox_speed_out, acceleration,
        previous_temperature, engine_status):
    """
    Calculates engine speed.

    :param engine_speed_idle:
        Engine idling speed.
    :type engine_speed_idle: float

    :param engine_speed_min:
        Engine minimum speed.
    :type engine_speed_min: float

    :param engine_speed_idle_add_start:
        Additional starting RPM.
    :type engine_speed_idle_add_start: float

    :param engine_therma_start:
        Engine starting temperature.
    :type engine_therma_start: float

    :param engine_therma_thres:
        Engine temperature threshold.
    :type engine_therma_thres: float

    :param logical_idling:
        Logical idling.
    :type logical_idling: binary

    :param previous_logical_idling:
        Previous step's logical idling.
    :type previous_logical_idling: binary

    :param gear_box_speed_in:
        Gearbox speed out.
    :type gear_box_speed_in: float

    :param next_gearbox_speed_out:
        Next step's gearbox speed out.
    :type next_gearbox_speed_out: float

    :param acceleration:
        Acceleration.
    :type acceleration: float

    :param previous_temperature:
        Previous step's temperature.
    :type previous_temperature: float

    :param engine_status:
        Engine status.
    :type engine_status: binary

    :return:
        Engine speed.
    :rtype: float
    """

    if logical_idling == 1:
        if (gear_box_speed_in == 0 and next_gearbox_speed_out > 0) or (
                        gear_box_speed_in > 0 and next_gearbox_speed_out == 0):
            rpm1 = engine_speed_idle + 0.9 * np.abs(
                engine_speed_min - gear_box_speed_in)
        else:
            rpm1 = engine_speed_idle
    else:
        if gear_box_speed_in < engine_speed_min and acceleration >= 0:
            rpm1 = engine_speed_min + 0.9 * (
                engine_speed_min - gear_box_speed_in)
        else:
            rpm1 = gear_box_speed_in

    if previous_temperature < 30 and previous_logical_idling == 1:
        if engine_speed_idle_add_start > 0:
            rpm2 = engine_speed_idle_add_start * (
                np.abs(previous_temperature - 30) / np.abs(
                    30 - engine_therma_start))
        else:
            rpm2 = (273 + engine_therma_thres) / (
                273 + previous_temperature) * 320
    else:
        rpm2 = 0

    return (rpm1 + rpm2) * engine_status
'''
