import os
import gtsam
import numpy as np
import matplotlib.pyplot as plt

from gtsam.utils import plot

import VAN_ex.code.Ex3.ex3 as ex3_utils
from VAN_ex.code.Ex4.ex4 import TracksDB, Track
from VAN_ex.code.BundleAdjustment import BundleAdjustment, BundleWindow

DB_PATH = os.path.join('..', 'Ex4', 'tracks_db.pkl')
T_ARR_PATH = os.path.join('..', 'Ex3', 'T_arr.npy')


def q6_1(T_arr, tracks_db):
    """
    Extract relative pose constraint from Bundle optimization.
    Calculate the correct covariance matrix of the relative motion (synthetic) measurement.
    The covariance should be the relative covariance between the frame poses.
     i.e. the covariance associated with the distribution P(ck|c0).
    """
    c0, ck = 0, 7  # First two keyframes
    first_window = BundleWindow.Bundle(c0, ck)
    first_window.alternate_ver_create_graph(T_arr, tracks_db)
    result = first_window.optimize()  # Estimate relative motion and uncertainty

    # Extract the marginal covariances of the solution
    marginals = first_window.get_marginals()

    # Plot the resulting frame locations as a 3D graph including the covariance
    # of the locations (all the frames in the bundle window).
    plot.plot_trajectory(1, result, marginals=marginals, scale=1)

    # Calculate the relative covariance between the first two keyframes
    keys = gtsam.KeyVector()
    keys.append(gtsam.symbol('c', c0))
    keys.append(gtsam.symbol('c', ck))
    marg_cov_mat = marginals.jointMarginalInformation(keys).fullMatrix()  # Information Matrix
    rel_cov = np.linalg.inv(marg_cov_mat)

    # Calculate the relative pose between the first two keyframes
    pose_c0 = result.atPose3(gtsam.symbol('c', c0))
    pose_ck = result.atPose3(gtsam.symbol('c', ck))
    rel_pose = pose_c0.between(pose_ck)

    # Print the resulting relative pose and the covariance associated.
    print("Relative pose between the first two keyframes:", rel_pose)
    print("Relative covariance between the first two keyframes:", rel_cov)


def q6_2():
    """
    Pose Graph
    Build a factor graph that represents the pose graph of the keyframes. Add the relative motion
    estimated in the previous section as constraints to that graph with the correct uncertainty
    (covariance matrix) for each constraint.
    Construct poses for the initial guess of the pose graph and optimize it.
    - What would be a reasonable initialization for the poses?
    - Plot the initial poses you supplied the optimization.
    - For the keyframe locations resulting from the optimization:
    o Plot the locations without covariances.
     What effect did the optimization have on the locations?
    What is the error of the factor graph before and after optimization?
    Is that surprising? Explain.
    o Plot the locations with the marginal covariances
    :return:
    """
    pass


def run_ex6():
    """
    Runs all exercise 6 sections.
    """
    np.random.seed(1)
    # Load tracks DB
    tracks_db = TracksDB.deserialize(DB_PATH)
    T_arr = np.load(T_ARR_PATH)
    rel_t_arr = ex3_utils.calculate_relative_transformations(T_arr)

    q6_1(rel_t_arr, tracks_db)
    # q6_2(tracks_db, rel_t_arr)


def main():
    run_ex6()


if __name__ == '__main__':
    main()
