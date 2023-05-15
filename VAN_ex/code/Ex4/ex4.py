import os
import pickle
import time

import cv2
import imageio
import numpy as np
from matplotlib import animation
from collections import defaultdict

import VAN_ex.code.utils as utils
import matplotlib.pyplot as plt
import VAN_ex.code.Ex1.ex1 as ex1_utils
import VAN_ex.code.Ex2.ex2 as ex2_utils
import VAN_ex.code.Ex3.ex3 as ex3_utils
import VAN_ex.code.utils as utils


# Constants #
MOVIE_LENGTH = 2559
CAM_TRAJ_PATH = os.path.join('..', '..', 'dataset', 'poses', '05.txt')
N_FEATURES = 1000
PNP_POINTS = 4
CONSENSUS_ACCURACY = 2
MAX_RANSAC_ITERATIONS = 5000
START_FRAME = 0
END_FRAME = 50
TRACK_MIN_LEN = 10
k, m1, m2 = ex2_utils.read_cameras()


class Track:
    """
    A class that represents a track.
    A track is a 3D landmark that was matched across multiple pairs of stereo images (frames).
    Every track will have a unique id, we will refer to it as track_id.
    Every image stereo pair will have a unique id, we will refer to it as frame_id.
    """

    def __init__(self, track_id, frame_ids, kp):
        """
        Initialize a track.
        :param track_id: Track ID.
        :param frame_ids: Frame IDs.
        :param kp: list of tuples of key points in both images, for each frame.
        """
        self.track_id = track_id
        self.frame_ids = frame_ids
        self.kp = kp  # Dict of tuples of key-points, each tuple is a pair of key-points

    def __str__(self):
        return f"Track ID: {self.track_id}, Frame IDs: {self.frame_ids}, " \
               f"Key-points: {len(self.kp)}"

    def __repr__(self):
        return str(self)

    def get_track_id(self):
        return self.track_id

    def get_frame_ids(self):
        return self.frame_ids

    def add_frame(self, frame_id, curr_kp, next_kp):
        """
        Add a frame to the track.
        :param frame_id: Frame ID.
        :param curr_kp: Key-points of the current frame.
        :param next_kp: Key-points of the next frame.
        """
        kp_to_keep = [kp for kp in self.kp[self.frame_ids[-1]][0] if kp in curr_kp[0]]
        # idx of kp in curr_kp that are in kp_to_keep
        idx_to_keep = [np.where(curr_kp[0] == kp)[0][0] for kp in kp_to_keep]
        self.kp[frame_id] = next_kp[0][idx_to_keep], next_kp[1][idx_to_keep]
        self.frame_ids.append(frame_id)


# Section 4.1
class TracksDB:
    """
    A class that represents a database for tracks.
    """

    def __init__(self):
        """
        Initialize a tracks database.
        """
        self.tracks = {}  # Dictionary of all tracks
        self.frame_ids = []
        self.track_ids = []
        self.track_id = 0  # Track ID counter

    def __str__(self):
        return f"Tracks: {self.tracks}, Frame IDs: {self.frame_ids}, " \
               f"Track IDs: {self.track_ids}, Track ID: {self.track_id}"

    def __repr__(self):
        return str(self)

    def add_track(self, track):
        """
        Add a track to the database.
        :param track: Track to add.
        """
        self.tracks[self.track_id] = track  # Add track to tracks dictionary by track_id as key
        self.frame_ids += track.frame_ids
        self.track_ids.append(self.track_id)
        self.track_id += 1

    def get_track_ids(self, frame_id):
        """
        Get all the track_ids that appear on a given frame_id.
        :param frame_id: Frame ID.
        :return: Track IDs.
        """
        return [track_id for track_id in self.track_ids if frame_id in self.tracks[track_id].frame_ids]

    def get_frame_ids(self, track_id):
        """
        Get all the frame_ids that are part of a given track_id.
        :param track_id: Track ID.
        :return: Frame IDs.
        """
        return self.tracks[track_id].frame_ids

    def get_feature_locations(self, frame_id, track_id):
        """
        Given track_id and frame_id, get feature locations of track on both
         left and right images, as a triplet (xl, xr, y) with:
         - (xl, y) the feature location on the left image
         - (xr, y) the feature location on the right image.
            Note that the y index is shared on both images.
        :param frame_id: Frame ID.
        :param track_id: Track ID.
        :return: Feature locations of track TrackId on both left and right images.
        """
        track = self.tracks[track_id]
        frame_ids = track.frame_ids
        if frame_id not in frame_ids:
            return None
        frame_index = frame_ids.index(frame_id)  # Get the index of the frame id in the track
        kp = track.kp[frame_index]
        return kp.pt

    # Implement an ability to extend the database with new tracks on a new
    # frame as we match new stereo pairs to the previous ones.
    def extend_tracks(self, frame_id, curr_frame_supporters_kp, next_frame_supporters_kp):
        """
        Get the matches of a new frame, and add the matches that consistent
         with the previous frames in the tracks as a new frame in every track.
        """
        # treats the kps as unique objects
        # get the tracks that include the previous frame_id
        relevant_tracks = [track_id for track_id in self.track_ids if frame_id - 1 in self.tracks[track_id].frame_ids]
        # get the tracks that include the curr_frame_supporters_kp in the previous frame
        relevant_tracks = [track_id for track_id in relevant_tracks if any(
            kp in self.tracks[track_id].kp[frame_id - 1][0] for kp in curr_frame_supporters_kp[0]) and any(
            kp in self.tracks[track_id].kp[frame_id - 1][1] for kp in curr_frame_supporters_kp[1])]

        # add a new frame to every fitting track with the new frame supporters_kp
        for track_id in relevant_tracks:
            track = self.tracks[track_id]
            track.add_frame(frame_id, curr_frame_supporters_kp, next_frame_supporters_kp)

        # get the set of kp in the relevant tracks
        relevant_kp = {}
        for track_id in relevant_tracks:
            relevant_kp.update(self.tracks[track_id].kp)

        # get the matches that are not in the relevant tracks
        new_matches = (left_kp, right_kp) = next_frame_supporters_kp

        # add the new track to the tracks db
        self.add_new_track(Track(self.get_new_id(), [frame_id], {frame_id: new_matches}))

    # Implement an ability to add a new track to the database.
    def add_new_track(self, track):
        """
        Add a new track to the database.
        :param track: Track to add.
        """
        self.tracks[track.track_id] = track
        self.frame_ids += track.frame_ids
        self.track_ids.append(track.track_id)

    def get_new_id(self):
        """
        Get a new track ID.
        :return: New track ID.
        """
        self.track_id += 1
        return self.track_id - 1

    # Implement functions to serialize the database to a file and read it from a file.
    def serialize(self, file_name):
        """
        Serialize the database to a file.
        :param file_name: File name.
        """
        with open(file_name, 'wb') as file:
            pickle.dump(self, file)

    @staticmethod
    def deserialize(file_name):
        """
        Deserialize the database from a file, and return a new TracksDB object.
        :param file_name: File name.
        """
        with open(file_name, 'rb') as file:
            tracks_db = pickle.load(file)
        return tracks_db

    # Section 4.2
    def get_statistics(self):
        """
        Present a plot of the following tracking statistics:
        • Total number of tracks
        • Number of frames
        • Mean track length, maximum and minimum track lengths
        • Mean number of frame links (number of tracks on an average image)
        """
        # get the number of tracks
        num_tracks = len(self.track_ids)
        # get the number of frames
        num_frames = len(self.frame_ids)
        # get the track lengths
        track_lengths = [len(self.tracks[track_id].frame_ids) for track_id in self.track_ids]
        # get the mean track length
        mean_track_length = np.mean(track_lengths)
        # get the maximum track length
        max_track_length = np.max(track_lengths)
        # get the minimum track length
        min_track_length = np.min(track_lengths)
        # get the mean number of frame links
        mean_num_frame_links = np.mean([len(self.get_track_ids(frame_id)) for frame_id in self.frame_ids])
        # print the statistics
        print('Total number of tracks: {}'.format(num_tracks))
        print('Number of frames: {}'.format(num_frames))
        print('Mean track length: {}'.format(mean_track_length))
        print('Maximum track length: {}'.format(max_track_length))
        print('Minimum track length: {}'.format(min_track_length))
        print('Mean number of frame links: {}'.format(mean_num_frame_links))


@utils.measure_time
# create a gif of some frames of the video
def create_gif(start_frame, end_frame, tracks_db):
    # add the frames to a list
    images = []
    for frame in range(start_frame, end_frame):
        left0_image, _ = ex1_utils.read_images(frame)
        images.append(left0_image)

    fig, axes = plt.subplots(figsize=(12, 6))
    plt.axis("off")
    fig.suptitle(f"Run", fontsize=16)
    fig.tight_layout()
    ims = [[axes.imshow(i, animated=True, cmap='gray')] for i in images]
    # add a scatter plot of the tracks
    # create a dictionary of colors from mpl colormap
    cmap = plt.get_cmap('gist_rainbow')
    colors = [cmap(i) for i in np.linspace(0, 1, len(tracks_db.track_ids))]
    # reverse order of tracks_db.track_ids
    reversed_idx = tracks_db.track_ids[::-1]
    # only tracks that have at least 10 frames
    tracks_to_show = [track_id for track_id in reversed_idx if len(tracks_db.tracks[track_id].frame_ids) > 10]
    for track_id in tracks_to_show:
        track = tracks_db.tracks[track_id]
        for i, frame_id in enumerate(track.frame_ids):
            ims[frame_id].append(
                axes.scatter([kp[0] for kp in track.kp[frame_id][0]], [kp[1] for kp in track.kp[frame_id][0]],
                             color=colors[track_id], animated=True))

    ani = animation.ArtistAnimation(fig, ims, interval=50, repeat_delay=3000, blit=True)
    # save but compress it first so it won't be too big
    ani.save('run.gif', writer='pillow', fps=5, dpi=100)


def get_rand_track(track_len, tracks):
    """
    Get a randomized track with length of at least track_len.
    """
    track_id = np.random.choice(tracks.track_ids)
    track = tracks.tracks[track_id]
    while len(track.frame_ids) < track_len:
        track_id = np.random.choice(tracks.track_ids)
        track = tracks.tracks[track_id]
    return track


def plot_connectivity_graph(tracks_db):
    """
    Plot a connectivity graph of the tracks. For each frame, the number of
    tracks outgoing to the next frame (the number of tracks on the frame with
     links also in the next frame)
    """
    outgoing_tracks = []

    # Need to fix
    for frame in tracks_db.frame_ids:
        num_tracks = len(tracks_db.get_track_ids(frame))
        num_tracks_next = len(tracks_db.get_track_ids(frame + 1))
        outgoing_tracks.append(num_tracks_next - num_tracks)


    plt.title('Connectivity Graph')
    plt.xlabel('Frame')
    plt.ylabel('Outgoing tracks')
    plt.scatter(tracks_db.frame_ids, outgoing_tracks)
    plt.axhline(y=np.mean(outgoing_tracks), color='green')
    plt.show()


def plot_inliers_per_frame(tracks_db):
    """
    Present a graph of the percentage of inliers per frame.
    """
    # Need to fix
    inliers_per_frame = [len(tracks_db.get_track_ids(frame)) for frame in tracks_db.frame_ids]

    plt.title('Inliers per frame')
    plt.xlabel('Frame')
    plt.ylabel('Inliers')
    plt.scatter(tracks_db.frame_ids, inliers_per_frame)
    plt.axhline(y=np.mean(inliers_per_frame), color='green')
    plt.show()


def plot_track_length_histogram(tracks_db):
    """
    Present a track length histogram graph.
    """
    lengths_dict = defaultdict(int)

    for track_id in tracks_db.track_ids:
        lengths_dict[len(tracks_db.tracks[track_id].frame_ids)] += 1

    max_value = max(lengths_dict.values())
    track_number = [i for i in range(max_value)]
    track_lengths = [lengths_dict[i] for i in track_number]

    plt.title('Track length histogram')
    plt.xlabel('Track length')
    plt.ylabel('Track #')
    plt.scatter(track_lengths, track_number)
    plt.show()


def read_gt_cam_mat():
    """
    Read the ground truth camera matrices (in \poses\05.txt).
    """
    gt_cam_matrices = list()

    with open(CAM_TRAJ_PATH) as f:
        lines = f.readlines()

    for line in lines:
        line = line.strip().split(' ')
        gt_cam_matrices.append(np.array(line).reshape(3, 4).astype(np.float64))

    return gt_cam_matrices


def plot_reprojection_error(tracks_db):
    """
    Present a graph of the reprojection error over the track’s images
    """
    # Read the ground truth camera matrices (in \poses\05.txt)
    gt_cam_matrices = read_gt_cam_mat()

    # Triangulate a 3d point in world coordinates from the features in the last frame of the track
    track = get_rand_track(TRACK_MIN_LEN, tracks_db.get_tracks())

    left_locations = track.left_locations()  # Need to implement
    right_locations = track.right_locations()

    last_gt_mat = gt_cam_matrices[END_FRAME]
    last_left_proj_mat = k @ last_gt_mat
    last_right_proj_mat = k @ ex3_utils.composite_transformations(last_gt_mat, m2)

    last_left_img_coords = left_locations[track.frame_ids[-1]]
    last_right_img_coords = right_locations[track.frame_ids[-1]]
    p3d = utils.triangulate_points(last_left_proj_mat, last_right_proj_mat,
                                   last_left_img_coords, last_right_img_coords)

    # Project this point to all the frames of the track (both left and right cameras)
    left_projections, right_projections = [], []

    for gt_cam_mat in gt_cam_matrices[START_FRAME:END_FRAME]:
        left_proj_cam = k @ gt_cam_mat
        left_projections.append(utils.project(p3d, left_proj_cam))

        right_proj_cam = k @ ex3_utils.composite_transformations(gt_cam_mat, m2)
        right_projections.append(utils.project(p3d, right_proj_cam))

    left_projections, right_projections = np.array(left_projections), np.array(right_projections)

    # We’ll define the reprojection error for a given camera as the distance between the projection
    # and the tracked feature location on that camera.
    left_proj_dist = np.einsum("ij,ij->i", left_projections, left_locations)
    right_proj_dist = np.einsum("ij,ij->i", right_projections, right_locations)
    total_proj_dist = (left_proj_dist + right_proj_dist) / 2

    # Present a graph of the reprojection error over the track’s images.
    plt.title("Reprojection error over track's images")
    plt.ylabel('Error')
    plt.xlabel('Frames')
    plt.scatter(range(len(total_proj_dist)), total_proj_dist)
    plt.show()


def run_sequence(start_frame, end_frame):
    db = TracksDB()
    for idx in range(start_frame, end_frame):
        left_ext_mat, inliers = ex3_utils.track_movement_successive([idx, idx + 1])
        if left_ext_mat is not None:
            left0_kp, right0_kp, left1_kp, right1_kp = inliers
            db.extend_tracks(idx, (left0_kp, right0_kp), (left1_kp, right1_kp))
            # Test functions
            # if idx == 5:
            #     db.get_feature_locations(0, 0)

        print(" -- Step {} -- ".format(idx))

    db.serialize('tracks_db.pkl')
    return db


def run_ex4():
    np.random.seed(1)
    """
    Runs all exercise 4 sections.
    """
    tracks_db = run_sequence(START_FRAME, END_FRAME)  # Build the tracks database

    # q4.2
    tracks_db.get_statistics()

    # q4.3
    create_gif(START_FRAME, END_FRAME, tracks_db)

    # # q4.4
    # plot_connectivity_graph(tracks_db)
    #
    # # q4.5
    # plot_inliers_per_frame(tracks_db)
    #
    # # q4.6
    # plot_track_length_histogram(tracks_db)
    #
    # # q4.7
    # plot_reprojection_error(tracks_db)


def main():
    run_ex4()


if __name__ == '__main__':
    main()