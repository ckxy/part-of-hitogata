import cv2
import math
import random
import numpy as np
from .builder import INTERNODE
from .base_internode import BaseInternode
from PIL import Image, ImageOps, ImageDraw
from ..utils.common import get_image_size, is_pil


__all__ = ['RandomErasing', 'GridMask']


class ErasingInternode(BaseInternode):
    def __init__(self, **kwargs):
        super(ErasingInternode, self).__init__(**kwargs)

    def forward_image(self, data_dict):
        if 'intl_erase_mask' not in data_dict.keys():
            return data_dict

        target_tag = data_dict['intl_base_target_tag']

        mask = data_dict['intl_erase_mask']

        if is_pil(data_dict[target_tag]):
            bgd = data_dict['intl_erase_bgd']
            data_dict[target_tag] = Image.composite(data_dict[target_tag], bgd, mask)
        else:
            bgd = data_dict['intl_erase_bgd']
            data_dict[target_tag] = Image.fromarray(data_dict[target_tag])
            data_dict[target_tag] = Image.composite(data_dict[target_tag], bgd, mask)
            data_dict[target_tag] = np.array(data_dict[target_tag])

        return data_dict

    def forward_mask(self, data_dict):
        if 'intl_erase_mask' not in data_dict.keys():
            return data_dict

        target_tag = data_dict['intl_base_target_tag']

        mask = data_dict['intl_erase_mask']

        mask = (np.asarray(mask) > 0).astype(np.int32)
        w, h = get_image_size(data_dict[target_tag])
        bgd = np.zeros((h, w), np.int32)
        data_dict[target_tag] = data_dict[target_tag] * mask + bgd * (1 - mask)

        return data_dict

    def erase_intl_param_forward(self, data_dict):
        if 'intl_erase_mask' in data_dict.keys():
            data_dict.pop('intl_erase_mask')
        if 'intl_erase_bgd' in data_dict.keys():
            data_dict.pop('intl_erase_bgd')
        return data_dict


@INTERNODE.register_module()
class RandomErasing(ErasingInternode):
    def __init__(self, scale=(0.02, 0.33), ratio=(0.3, 3.3), offset=False, value=(0, 0, 0), **kwargs):
        assert isinstance(value, tuple)
        if (scale[0] > scale[1]) or (ratio[0] > ratio[1]):
            warnings.warn("range should be of kind (min, max)")
        if scale[0] < 0 or scale[1] > 1:
            raise ValueError("range of scale should be between 0 and 1")

        self.scale = scale
        self.ratio = ratio
        self.offset = offset
        self.value = value

        super(RandomErasing, self).__init__(**kwargs)

    def calc_intl_param_forward(self, data_dict):
        assert 'point' not in data_dict.keys() and 'bbox' not in data_dict.keys()

        w, h = get_image_size(data_dict['image'])
        area = w * h
        for attempt in range(10):
            erase_area = random.uniform(self.scale[0], self.scale[1]) * area
            aspect_ratio = random.uniform(self.ratio[0], self.ratio[1])

            new_h = int(round(math.sqrt(erase_area * aspect_ratio)))
            new_w = int(round(math.sqrt(erase_area / aspect_ratio)))

            if new_h < h and new_w < w:
                y = random.randint(0, h - new_h)
                x = random.randint(0, w - new_w)

                data_dict['intl_erase_mask'] = Image.new("L", get_image_size(data_dict['image']), 255)
                draw = ImageDraw.Draw(data_dict['intl_erase_mask'])
                draw.rectangle((x, y, x + new_w, y + new_h), fill=0)

                if 'image' in data_dict.keys():
                    if self.offset:
                        offset = 2 * (np.random.rand(h, w) - 0.5)
                        offset = np.uint8(offset * 255)
                        data_dict['intl_erase_bgd'] = Image.fromarray(offset).convert('RGB')
                    else:
                        data_dict['intl_erase_bgd'] = Image.new('RGB', get_image_size(data_dict['image']), self.value)
                break

        return data_dict

    def __repr__(self):
        if self.offset:
            return 'RandomErasing(scale={}, ratio={}, offset={})'.format(self.scale, self.ratio, self.offset)
        else:
            return 'RandomErasing(scale={}, ratio={}, value={})'.format(self.scale, self.ratio, self.value)


@INTERNODE.register_module()
class GridMask(ErasingInternode):
    def __init__(self, use_w=True, use_h=True, rotate=0, offset=False, invert=False, ratio=1, **kwargs):
        assert 0 <= rotate < 90

        self.use_h = use_h
        self.use_w = use_w
        self.rotate = rotate
        self.offset = offset
        self.invert = invert
        self.ratio = ratio

        super(GridMask, self).__init__(**kwargs)

    def calc_intl_param_forward(self, data_dict):
        assert 'point' not in data_dict.keys()

        w, h = get_image_size(data_dict['image'])

        hh = int(1.5 * h)
        ww = int(1.5 * w)
        d = np.random.randint(2, min(h, w))

        if self.ratio == 1:
            l = np.random.randint(1, d)
        else:
            l = min(max(int(d * self.ratio + 0.5), 1), d - 1)

        mask = np.ones((hh, ww), np.float32)

        st_h = np.random.randint(d)
        st_w = np.random.randint(d)

        if self.use_h:
            for i in range(hh // d):
                s = d * i + st_h
                t = min(s + l, hh)
                mask[s:t, :] = 0

        if self.use_w:
            for i in range(ww // d):
                s = d * i + st_w
                t = min(s + l, ww)
                mask[:, s:t] = 0

        mask = Image.fromarray(np.uint8(mask * 255))
        if not self.invert:
            mask = ImageOps.invert(mask)

        if self.rotate != 0:
            r = np.random.randint(self.rotate)
            mask = mask.rotate(r)

        data_dict['intl_erase_mask'] = mask.crop(((ww - w) // 2, (hh - h) // 2, (ww - w) // 2 + w, (hh - h) // 2 + h))

        if 'image' in data_dict.keys():
            if self.offset:
                offset = 2 * (np.random.rand(h, w) - 0.5)
                offset = np.uint8(offset * 255)
                data_dict['intl_erase_bgd'] = Image.fromarray(offset).convert('RGB')
            else:
                data_dict['intl_erase_bgd'] = Image.new('RGB', get_image_size(data_dict['image']), 0)

        return data_dict

    def __repr__(self):
        return 'GridMask(use_h={}, use_w={}, ratio={}, rotate={}, offset={}, invert={})'.format(self.use_h, self.use_w, self.ratio, self.rotate, self.offset, self.invert)
