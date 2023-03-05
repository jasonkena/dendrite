import numpy as np
from math import gcd
from scipy.spatial import KDTree
from scipy.spatial.distance import cdist
from scipy.interpolate import UnivariateSpline

import dask
import dask.array as da


@dask.delayed
def segment_pc(idx, spine, skel, longest_path, path_length, segment_per, anisotropy):
    dtype = np.float64
    anisotropy = np.array(anisotropy).astype(dtype)
    # idx: [n, 3]
    # spine: [n]

    # get isotropic pc
    # [n, 4]
    pc = np.concatenate([idx.astype(dtype) * anisotropy, spine[:, None]], axis=1)

    centerline = spline_interpolate_centerline(
        skel.vertices[longest_path].astype(dtype) * anisotropy, path_length
    )
    # centerline = interp_centerline(skel.vertices[longest_path]*anisotropy, path_length)
    dist, closest_idx = get_closest(pc[:, :3], centerline)

    cord_skel, T, N, B, dis_geo_skel = get_cord_skel(centerline)
    assert cord_skel.shape == centerline.shape

    assert centerline.shape[0] == path_length
    assert np.max(closest_idx) < path_length

    unique, inverse, counts = np.unique(
        closest_idx, return_inverse=True, return_counts=True
    )
    idx = np.argsort(inverse)

    closest_idx = closest_idx[idx]
    dist = dist[idx]
    pc = pc[idx]

    cumsum = np.zeros(path_length, dtype=int)
    cumsum[unique] = counts
    cumsum = np.cumsum(cumsum)

    split_idx = np.arange(0, path_length, segment_per)
    split_idx = cumsum[split_idx]

    pc_segments = np.split(pc, split_idx[1:])
    closest_idx_segments = np.split(closest_idx, split_idx[1:])
    dist_segments = np.split(dist, split_idx[1:])

    # assert min([len(x) for x in pc_segments]) > 0

    result = {
        "skel": centerline,
        "skel_gnb": cord_skel,
        "T": T,
        "N": N,
        "B": B,
        "dis_geo_skel": dis_geo_skel,
    }

    for i, (pc, closest_idx, dist) in enumerate(
        zip(pc_segments, closest_idx_segments, dist_segments)
    ):
        if len(pc) == 0:
            print(f"Missing segment: {i}")
            result[f"pc_{i}"] = -np.ones((1, 4))
            result[f"dist_{i}"] = -np.ones((1,))
            result[f"closest_idx_{i}"] = -np.ones((1,))
        else:
            result[f"pc_{i}"] = pc
            result[f"dist_{i}"] = dist
            result[f"closest_idx_{i}"] = closest_idx

    return result


@dask.delayed
def cylindrical_segment_pc(pc, dist, closest_idx, centerline, T, N, B, dis_geo_skel):
    if np.any(pc == -1):
        return {"pc_gnb": -np.ones((1, 4))}
    cyd_pc = cylindrical_transformation(
        pc, centerline, dist, closest_idx, T, N, B, dis_geo_skel
    )
    assert cyd_pc.shape == pc.shape

    result = {
        "pc_gnb": cyd_pc,
    }

    return result


def get_closest(pc_a, pc_b):
    # pc_a: (m,3)
    # pc_b: (n,3)
    # return: (m) - the index of the closest point in pc_b for each point in pc_a

    # pc_a = pc_a.astype(np.float64)
    # pc_b = pc_b.astype(np.float64)

    tree = KDTree(pc_b)
    dist, idx = tree.query(pc_a, workers=-1)

    if np.max(idx) >= pc_b.shape[0]:
        np.save("/mmfs1/data/adhinart/dendrite/logs/pc_a.npy", pc_a)
        np.save("/mmfs1/data/adhinart/dendrite/logs/pc_b.npy", pc_b)
        raise ValueError("idx is out of range")

    return dist, idx


def spline_interpolate_centerline(path, path_length, kwargs={"k": 2, "s": 15}):
    # skel_upsampled = (path,k=2,s=15)
    # path: (n,3)
    # path_length: int
    # kwargs: dict, for UnivariateSpline
    l2 = np.linalg.norm(path[1:] - path[:-1], axis=1)
    cumsum = np.cumsum(l2)
    cumsum = np.insert(cumsum, 0, 0)

    total_length = cumsum[-1]
    x, y, z = path[:, 0], path[:, 1], path[:, 2]
    new_path = np.zeros((path_length, 3))

    w = cumsum
    try:
        sx = UnivariateSpline(w, x, **kwargs)
        sy = UnivariateSpline(w, y, **kwargs)
        sz = UnivariateSpline(w, z, **kwargs)
    except Exception as e:
        raise ValueError(f"Error in spline interpolation: {e} {cumsum}")

    wnew = np.linspace(0, total_length, num=path_length)
    new_path[:, 0] = sx(wnew)
    new_path[:, 1] = sy(wnew)
    new_path[:, 2] = sz(wnew)

    return new_path


def interp_centerline(path, path_length):
    # path: (n,3)
    # path_length: int

    l2 = np.linalg.norm(path[1:] - path[:-1], axis=1)
    cumsum = np.cumsum(l2)
    cumsum = np.insert(cumsum, 0, 0)
    total_length = cumsum[-1]

    sample_length = np.linspace(0, total_length, path_length)

    points = [np.interp(sample_length, cumsum, path[:, i]) for i in range(3)]
    points = np.stack(points, axis=1)

    return points


def get_cord_skel(skel):
    T, N, B = frenet_frame(skel)
    dis_geo_skel_tmp = np.insert((((T ** 2).sum(1)) ** 0.5)[:-1], 0, 0)
    dis_geo_skel = np.zeros_like(dis_geo_skel_tmp)
    for i in range(dis_geo_skel.shape[0]):
        dis_geo_skel[i] = dis_geo_skel_tmp[: i + 1].sum()
    cord_skel = np.concatenate(
        (dis_geo_skel[:, None], np.zeros(dis_geo_skel.shape)[:, None]), axis=1
    )
    cord_skel = np.concatenate(
        (cord_skel, np.zeros(dis_geo_skel.shape)[:, None]), axis=1
    )

    return cord_skel, T, N, B, dis_geo_skel


def cylindrical_transformation(pc, skel, dist, closest_idx, T, N, B, dis_geo_skel):
    # input pc [N, 3+1], smoothed_skel [S,3]

    pc_skel = skel[closest_idx]
    vec_tan = T[closest_idx]
    vec_norm = N[closest_idx]
    vec_binorm = B[closest_idx]

    # non-skeleton
    dis_geo_pc = dis_geo_skel[closest_idx]

    t = ((pc_skel * vec_tan).sum(1) - (pc[:, :3] * vec_tan).sum(1)) / (
        (vec_tan ** 2).sum(1)
    )
    pc_proj = pc[:, :3] + t[:, None] * vec_tan
    vec_proj = pc_proj - pc_skel
    cos_norm = (vec_norm * vec_proj).sum(1) / (
        (vec_norm ** 2).sum(1) + (vec_proj ** 2).sum(1)
    )
    cos_binorm = (vec_binorm * vec_proj).sum(1) / (
        (vec_binorm ** 2).sum(1) + (vec_proj ** 2).sum(1)
    )
    cos_binorm[cos_binorm >= 0] = 1
    cos_binorm[cos_binorm < 0] = -1
    dis_theta_pc = np.arccos(cos_norm) * cos_binorm

    cyd_pc = np.concatenate((dis_geo_pc[:, None], dist[:, None]), axis=1)
    cyd_pc = np.concatenate((cyd_pc, dis_theta_pc[:, None]), axis=1)
    cyd_pc = np.concatenate((cyd_pc, pc[:, 3, None]), axis=1)

    return cyd_pc


def frenet_frame(skeleton):
    # tangent
    skel_tan = np.zeros(skeleton.shape)
    skel_tan[:-1] = skeleton[1:] - skeleton[:-1]
    skel_tan[-1] = skel_tan[-2]
    # normal
    v_1 = skeleton[:-2]
    v_2 = skeleton[1:-1]
    v_3 = skeleton[2:]
    assert np.any(((v_2 - v_1) ** 2).sum(1) != 0)
    t = ((v_2 - v_1) * (v_3 - v_2)).sum(1) / ((v_2 - v_1) ** 2).sum(1)
    assert np.any(t >= 0)
    normal = np.zeros(skeleton.shape)
    normal[:-2] = (v_3 - v_2) - t[:, None] * (v_2 - v_1)

    # find the last non-zero vertex
    idx_last_non_zero_vert = np.argwhere(
        (normal[:, 0] != 0) + (normal[:, 1] != 0) + (normal[:, 2] != 0)
    )
    if idx_last_non_zero_vert.shape[0] != 0:
        idx_last_non_zero_vert = idx_last_non_zero_vert[-1, 0]
    else:
        print("all vertices are colinear, return [0]")
        return skel_tan, np.zeros([0]), None
    normal[idx_last_non_zero_vert + 1] = normal_backwards(
        skeleton, idx_last_non_zero_vert
    )
    normal[idx_last_non_zero_vert + 2 :] = normal[idx_last_non_zero_vert + 1]
    # intermediate Zero values
    # backward calculate normal
    idx_v_line = np.argwhere(
        (normal[:, 0] == 0) * (normal[:, 1] == 0) * (normal[:, 2] == 0)
    )[:, 0]

    if idx_v_line.shape[0] != 0:
        for idx in idx_v_line[::-1]:
            if idx - 1 >= 0:
                normal[idx] = normal_backwards(skeleton, idx - 1)

    # backward assign normal - last vertice
    idx_v_line = np.argwhere(
        (normal[:, 0] == 0) * (normal[:, 1] == 0) * (normal[:, 2] == 0)
    )[:, 0]

    if idx_v_line.shape[0] != 0:
        if idx_v_line[-1] + 1 == normal.shape[0]:
            idx = idx_v_line[-1] - 1
            while idx in idx_v_line[::-1]:
                idx -= 1
            normal[idx:,] = normal[
                idx,
            ]  # optimize
    # backward assign normal - intermediate vertice
    idx_v_line = np.argwhere(
        (normal[:, 0] == 0) * (normal[:, 1] == 0) * (normal[:, 2] == 0)
    )[:, 0]
    if idx_v_line.shape[0] != 0:
        for idx in idx_v_line[::-1]:
            normal[idx] = normal[idx + 1]
    # binormal
    skel_binorm = np.cross(skel_tan, normal)
    assert (
        np.argwhere(
            (skel_binorm[:, 0] == 0)
            * (skel_binorm[:, 1] == 0)
            * (skel_binorm[:, 2] == 0)
        ).shape[0]
        == 0
    )
    return skel_tan, normal, skel_binorm


def normal_backwards(skeleton, idx_1):
    # normal_backward
    assert np.any(((skeleton[idx_1 + 2] - skeleton[idx_1 + 1]) ** 2).sum() != 0)
    lda = (
        (skeleton[idx_1 + 1] - skeleton[idx_1])
        * (skeleton[idx_1 + 2] - skeleton[idx_1 + 1])
    ).sum() / ((skeleton[idx_1 + 2] - skeleton[idx_1 + 1]) ** 2).sum()
    return (
        skeleton[idx_1]
        - skeleton[idx_1 + 1]
        - lda * (skeleton[idx_1 + 1] - skeleton[idx_1 + 2])
    )


def task_generate_point_cloud_segments(cfg, pc, skel):
    skel, longest_path = skel["skeleton"], skel["longest_path"]
    idx, spine = pc["idx"], pc["spine"]

    general = cfg["GENERAL"]
    uint_dtype = general["UINT_DTYPE"]
    anisotropy = general["ANISOTROPY"]
    chunk_size = general["CHUNK_SIZE"]
    chunk_size = np.prod(chunk_size)

    frenet = cfg["FRENET"]
    path_length = frenet["PATH_LENGTH"]
    segment_per = frenet["SEGMENT_PER"]

    # ceil
    num_segments = np.ceil(path_length / segment_per).astype(int)
    output = segment_pc(
        idx, spine, skel, longest_path, path_length, segment_per, anisotropy
    )

    result = {
        "skel": output["skel"],
        "skel_gnb": output["skel_gnb"],
    }

    for i in range(num_segments):
        result[f"pc_{i}"] = da.from_delayed(
            output[f"pc_{i}"], shape=(np.nan, 4), dtype=np.float64
        )
        result[f"closest_idx_{i}"] = da.from_delayed(
            output[f"closest_idx_{i}"], shape=(np.nan,), dtype=int
        )
        result[f"dist_{i}"] = da.from_delayed(
            output[f"dist_{i}"], shape=(np.nan,), dtype=np.float64
        )

        cyd_output = cylindrical_segment_pc(
            output[f"pc_{i}"],
            output[f"dist_{i}"],
            output[f"closest_idx_{i}"],
            output["skel"],
            output["T"],
            output["N"],
            output["B"],
            output["dis_geo_skel"],
        )
        result[f"pc_gnb_{i}"] = da.from_delayed(
            cyd_output[f"pc_gnb"], shape=(np.nan, 4), dtype=np.float64
        )

    # result["skel"].compute(scheduler="single-threaded")

    # don't bother with converting them to Dask arrays
    # results = {"segments" : segments}

    return result
