import cv2
import math
import random
import numpy as np
from PIL import Image
from .bamboo import Bamboo
from .warp import WarpResize
from .builder import INTERNODE
from .builder import build_internode
from .base_internode import BaseInternode
from .control_flow import InternodeWarpper
from ..utils.common import get_image_size, is_pil


__all__ = ['Resize', 'Rescale', 'RescaleLimitedByBound', 'ResizeAndPadding']


def resize_image(image, size):
    if is_pil(image):
        image = image.resize(size, Image.Resampling.BILINEAR)
    else:
        image = cv2.resize(image, size)
    return image


def resize_bbox(bboxes, scale):
    bboxes[:, 0] *= scale[0]
    bboxes[:, 1] *= scale[1]
    bboxes[:, 2] *= scale[0]
    bboxes[:, 3] *= scale[1]
    return bboxes


def resize_poly(polys, scale):
    for i in range(len(polys)):
        polys[i][..., 0] *= scale[0]
        polys[i][..., 1] *= scale[1]
    return polys


def resize_point(points, scale):
    points[..., 0] *= scale[0]
    points[..., 1] *= scale[1]
    return points


def resize_mask(mask, size):
    mask = cv2.resize(mask, size, interpolation=cv2.INTER_NEAREST)
    return mask


class ResizeInternode(BaseInternode):
    def __init__(self, **kwargs):
        super(ResizeInternode, self).__init__(**kwargs)

    def calc_scale_and_new_size(self, w, h):
        raise NotImplementedError

    def calc_intl_param_forward(self, data_dict):
        w, h = get_image_size(data_dict['image'])
        data_dict['intl_scale'], data_dict['intl_new_size'] = self.calc_scale_and_new_size(w, h)
        return data_dict

    def forward_image(self, data_dict):
        target_tag = data_dict['intl_base_target_tag']

        data_dict[target_tag] = resize_image(data_dict[target_tag], data_dict['intl_new_size'])
        return data_dict

    def forward_bbox(self, data_dict):
        target_tag = data_dict['intl_base_target_tag']
        
        data_dict[target_tag] = resize_bbox(data_dict[target_tag], data_dict['intl_scale'])
        return data_dict

    def forward_mask(self, data_dict):
        target_tag = data_dict['intl_base_target_tag']

        data_dict[target_tag] = resize_mask(data_dict[target_tag], data_dict['intl_new_size'])
        return data_dict

    def forward_point(self, data_dict):
        target_tag = data_dict['intl_base_target_tag']
        
        data_dict[target_tag] = resize_point(data_dict[target_tag], data_dict['intl_scale'])
        return data_dict

    def forward_poly(self, data_dict):
        target_tag = data_dict['intl_base_target_tag']
        
        data_dict[target_tag] = resize_poly(data_dict[target_tag], data_dict['intl_scale'])
        return data_dict

    def erase_intl_param_forward(self, data_dict):
        data_dict.pop('intl_scale')
        data_dict.pop('intl_new_size')
        return data_dict


@INTERNODE.register_module()
class Resize(ResizeInternode):
    def __init__(self, size, keep_ratio=True, short=False, **kwargs):
        assert len(size) == 2
        assert size[0] > 0 and size[1] > 0

        self.size = size
        self.keep_ratio = keep_ratio
        self.short = short

        super(Resize, self).__init__(**kwargs)

    def calc_scale_and_new_size(self, w, h):
        tw, th = self.size
        rw, rh = tw / w, th / h

        if self.keep_ratio:
            if self.short:
                r = max(rh, rw)
                scale = (r, r)
            else:
                r = min(rh, rw)
                scale = (r, r)

            # new_size = (int(r * w), int(r * h))
            new_size = int(round(r * w)), int(round(r * h))
        else:
            scale = (rw, rh)
            new_size = (tw, th)

        return scale, new_size

    def calc_intl_param_backward(self, data_dict):
        if 'intl_resize_and_padding_reverse_flag' in data_dict.keys():
            w, h = data_dict['ori_size']
            scale, _ = self.calc_scale_and_new_size(w, h)
            data_dict['intl_scale'] = (1 / scale[0], 1 / scale[1])
            data_dict['intl_new_size'] = (w, h)
        return data_dict

    def backward_image(self, data_dict):
        if 'intl_scale' not in data_dict.keys():
            return data_dict
        return self.forward_image(data_dict)

    def backward_bbox(self, data_dict):
        if 'intl_scale' not in data_dict.keys():
            return data_dict
        return self.forward_bbox(data_dict)

    def backward_mask(self, data_dict):
        if 'intl_scale' not in data_dict.keys():
            return data_dict
        return self.forward_mask(data_dict)

    def backward_point(self, data_dict):
        if 'intl_scale' not in data_dict.keys():
            return data_dict
        return self.forward_point(data_dict)

    def backward_poly(self, data_dict):
        if 'intl_scale' not in data_dict.keys():
            return data_dict
        return self.forward_poly(data_dict)

    def erase_intl_param_backward(self, data_dict):
        if 'intl_scale' in data_dict.keys():
            data_dict = self.erase_intl_param_forward(data_dict)
        return data_dict

    def __repr__(self):
        return 'Resize(size={}, keep_ratio={}, short={})'.format(self.size, self.keep_ratio, self.short)


@INTERNODE.register_module()
class Rescale(ResizeInternode):
    def __init__(self, ratio_range, mode='range', **kwargs):
        if mode == 'range':
            assert len(ratio_range) == 2 and ratio_range[0] <= ratio_range[1] and ratio_range[0] > 0
        elif mode == 'value':
            assert len(ratio_range) > 1 and min(ratio_range) > 0
        else:
            raise NotImplementedError

        self.ratio_range = ratio_range
        self.mode = mode

        super(Rescale, self).__init__(**kwargs)

    def calc_scale_and_new_size(self, w, h):
        if self.mode == 'range':
            scale = np.random.random_sample() * (self.ratio_range[1] - self.ratio_range[0]) + self.ratio_range[0]
        elif self.mode == 'value':
            scale = random.choice(self.ratio_range)

        return (scale, scale), (int(scale * w), int(scale * h))

    def reverse(self, **kwargs):
        return kwargs

    def __repr__(self):
        return 'Rescale(ratio_range={}, mode={})'.format(self.ratio_range, self.mode)


@INTERNODE.register_module()
class RescaleLimitedByBound(Rescale):
    def __init__(self, ratio_range, long_size_bound, short_size_bound, mode='range', **kwargs):
        super(RescaleLimitedByBound, self).__init__(ratio_range, mode, **kwargs)
        assert long_size_bound >= short_size_bound

        self.long_size_bound = long_size_bound
        self.short_size_bound = short_size_bound

    def calc_scale_and_new_size(self, w, h):
        scale1 = 1

        if max(h, w) > self.long_size_bound:
            scale1 = self.long_size_bound * 1.0 / max(h, w)

        scale2, _ = super(RescaleLimitedByBound, self).calc_scale_and_new_size(w, h)
        scale = scale1 * scale2[0]

        if min(h, w) * scale <= self.short_size_bound:
            scale = (self.short_size_bound + 10) * 1.0 / min(h, w)

        return (scale, scale), (int(scale * w), int(scale * h))

    def reverse(self, **kwargs):
        return kwargs

    def __repr__(self):
        return 'RescaleLimitedByBound(ratio_range={}, mode={}, long_size_bound={}, short_size_bound={})'.format(self.ratio_range, self.mode, self.long_size_bound, self.short_size_bound)


@INTERNODE.register_module()
class ResizeAndPadding(Bamboo):
    def __init__(self, resize=None, padding=None, **kwargs):
        assert resize or padding

        self.internodes = []
        if resize:
            assert resize['type'] in ['Resize', 'WarpResize']
            resize['expand'] = True
            self.internodes.append(build_internode(resize))
        else:
            self.internodes.append(build_internode(dict(type='BaseInternode')))

        if padding:
            assert padding['type'] in ['PaddingBySize', 'PaddingByStride']
            self.internodes.append(build_internode(padding))
        else:
            self.internodes.append(build_internode(dict(type='BaseInternode')))

    def calc_intl_param_backward(self, data_dict):
        if 'ori_size' in data_dict.keys():
            w, h = data_dict['ori_size']

            if hasattr(self.internodes[0], 'calc_scale_and_new_size'):
                _, (nw, nh) = self.internodes[0].calc_scale_and_new_size(w, h)
                data_dict['intl_resize_size'] = (nh, nw)
            elif isinstance(self.internodes[0], InternodeWarpper) and hasattr(self.internodes[0].internode, 'calc_scale_and_new_size'):
                _, (nw, nh) = self.internodes[0].internode.calc_scale_and_new_size(w, h)
                data_dict['intl_resize_size'] = (nh, nw)
            else:
                data_dict['intl_resize_size'] = (h, w)

            data_dict['intl_resize_and_padding_reverse_flag'] = True
        return data_dict

    def backward(self, data_dict):
        if 'intl_resize_and_padding_reverse_flag' in data_dict.keys():
            ori_size = data_dict['ori_size']

            data_dict['ori_size'] = data_dict['intl_resize_size']
            data_dict = self.internodes[1].reverse(**data_dict)

            data_dict['ori_size'] = ori_size
            data_dict = self.internodes[0].reverse(**data_dict)
        return data_dict

    def erase_intl_param_backward(self, data_dict):
        if 'intl_resize_and_padding_reverse_flag' in data_dict.keys():
            data_dict.pop('intl_resize_and_padding_reverse_flag')
            data_dict.pop('intl_resize_size')
        return data_dict

    def rper(self):
        res = type(self).__name__
        res = res[:1].lower() + res[1:]
        res = res[::-1]
        res = res[:1].upper() + res[1:] + '('

        split_str = [i.__repr__() for i in self.internodes[::-1]]

        for i in range(len(split_str)):
            res += '\n  ' + split_str[i].replace('\n', '\n  ')
        res = '{}\n)'.format(res)
        return res
