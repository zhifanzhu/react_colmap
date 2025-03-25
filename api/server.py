import os
import torch
from pytorch3d.transforms.rotation_conversions import quaternion_to_matrix, matrix_to_quaternion
import numpy as np
import ujson

from flask import (
    Flask,
    request, jsonify, send_file
)
from flask_cors import CORS, cross_origin
from markupsafe import escape

app = Flask(__name__)
cors = CORS(app)
app.config['CORS_HEADERS'] = 'Content-Type'
app = Flask(__name__)


""" Data flow
Input:
    image: {name: [qw, qx, qy, qz, tx, ty, tz], ...}
    point: [x, y, z, r, g, b], rgb in [0, 255]

Output-to-client:
    model/:
        image: [qw, qx, qy, qz, tx, ty, tz]
        point: [x, y, z, r, g, b]
        line: [x1 y1 z1 x2 y2 z2]

    registration/
        points: [ [x, y, z, r, g, b], ... ],
        lines:  [ [x1 y1 z1 x2 y2 z2 r g b], ...]
        images: [ [qw, qx, qy, qz, tx, ty, tz, r, g, b], ...]]

output rgb in [0, 1]
"""


def generate_colormap(num_colors):
    """ colors in [0, 1]"""
    from matplotlib import pyplot as plt
    colormap = plt.get_cmap("hsv", num_colors)
    color_dict = {}
    inds = np.arange(num_colors)
    np.random.seed(1)
    inds = np.random.permutation(inds)
    for i in range(num_colors):
        color_name = f"color_{i}"
        color_dict[color_name] = colormap(inds[i])[:3]
    return color_dict


def qtvec2mat(qvec: np.ndarray, tvec: np.ndarray) -> torch.Tensor:
    n = len(qvec)
    R = quaternion_to_matrix(torch.from_numpy(qvec))  # qvec2rotmat(qvec)
    mat = torch.eye(4).view(-1, 4, 4).tile([n, 1, 1])
    mat[:, :3, :3] = R
    mat[:, :3, 3] = torch.from_numpy(tvec)
    return mat.float()


def mat2qtvec(mat: torch.Tensor) -> np.ndarray:
    qvec = matrix_to_quaternion(mat[:, :3, :3]).numpy()
    tvec = mat[:, :3, 3].numpy()
    qtvecs = np.concatenate([qvec, tvec], 1)
    return qtvecs


def get_inverse_transform(s, R, t) -> torch.Tensor:
    """ 
    input matrix of {RsP + st} is [R, t, 1/s],
    and it's inverse is [R.T, -R.T @ s*t, s]
    """
    mat = np.eye(4)
    mat[:3, :3] = R.T
    mat[:3, 3] = - R.T @ (s*t)
    mat[-1, -1] = s
    return torch.from_numpy(mat).float()


@app.route("/model/<path:subpath>")
@cross_origin()
def model(subpath):
    model = escape(subpath)  # e.g 'colmap_projects/json_models/P04_01_skeletons.json'
    print(model)
    with open(model) as fp:
        data = ujson.load(fp)
    points = np.asarray(data['points'])
    points[:, 3:] = points[:, 3:] / 255
    data['points'] = points.tolist()
    data['images'] = [im for im in data['images'].values()]

    return jsonify(data)


@app.route("/registration/<path:reg_path>")
@cross_origin()
def registration(reg_path):
    """ We merge everything together in the server side:
    - Loading of different models 
    - Rotate, scale and translate 
    - Color the points
    - Loading the line, color it
    """
    reg = escape(reg_path)  # e.g 'colmap_projects/registration/P04A/P04A.json'
    print(reg)
    with open(reg) as fp:
        model_infos = ujson.load(fp)
    
    colors = generate_colormap(32)
    alpha = 0.5
    model_prefix = 'colmap_projects/json_models/'
    model_suffix = '_skeletons.json'

    all_points = []
    all_lines = []
    all_images = []
    for model_vid, model_info, clr in zip(model_infos.keys(), model_infos.values(), colors.values()):
        model_path = model_prefix + model_vid + model_suffix
        print(f'loading {model_path}')
        # if model_vid.startswith('P01_'):
        if not (model_vid == 'P01_14' or model_vid == 'P01_02'):
        # if not (model_vid == 'P03_04' or model_vid == 'P03_05'):
            # if not model_vid == 'P30_101':
            #     print("skip")
            continue
        with open(model_path) as fp:
            model = ujson.load(fp)
            points = np.asarray(model['points'])

            images = np.asarray([im for im in model['images'].values()])
            # if model_vid == 'P30_107':
            #     _img = model['images'][f'frame_{122962:010d}.jpg']
            #     images = np.asarray([_img])
            # if model_vid == 'P30_101':
            #     _img = model['images'][f'frame_{15450:010d}.jpg']
            #     images = np.asarray([_img])

            # if 'line' in model:
            #     line = np.asarray(model['line']).reshape(-1, 3)
            # else:
            line = np.float32([0, 0, 0, 1, 0, 0]).reshape(-1, 3)

        rot = np.asarray(model_info['rot']).reshape(3, 3)
        transl = np.asarray(model_info['transl'])
        scale = model_info['scale']

        pos = points[:, :3] * scale @ rot.T + transl
        rgb = alpha * points[:, 3:] / 255 + (1-alpha) * np.float32(clr)
        rgb = np.clip(rgb, 0, 1)
        new_points = np.concatenate([pos, rgb], axis=1)
        all_points.extend(new_points.tolist())

        w2c = qtvec2mat(images[:, :4], images[:, 4:])
        inv_transf = get_inverse_transform(s=scale, R=rot, t=transl/scale)  # {RsP+t} == {RsP + s*(t/s)}
        new_w2c = w2c @ inv_transf
        new_images = mat2qtvec(new_w2c)
        image_colors = np.float32([clr]).repeat(new_images.shape[0], axis=0)
        new_images = np.concatenate([new_images, image_colors], axis=1)
        all_images.extend(new_images.tolist())

        line_length = 5
        line = line * scale @ rot.T + transl
        vc = (line[0, :] + line[1, :]) / 2
        line_dir = line[1, :] - line[0, :]
        line_len_half = line_length / 2
        lst = vc + line_len_half * line_dir
        led = vc - line_len_half * line_dir
        cur_line = np.concatenate([lst, led, np.float32(clr)]).tolist()
        all_lines.append(cur_line)

    data = {
        'points': all_points,
        'lines': all_lines,
        'images': all_images,
    }

    return jsonify(data)


@app.route("/data")
@cross_origin()
def data():
    data = [
        {
            'example-data': 'example-number',
        }
    ]
    return jsonify(data)


if __name__ == '__main__':
    json_model = 'colmap_projects/json_models/P04_01_skeletons.json'
    with open(json_model) as fp:
        json_data = ujson.load(fp)