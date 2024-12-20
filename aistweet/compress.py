import os
from PIL import Image


def resize_and_compress(input_path, output_path, max_size, target_resolution):
    with Image.open(input_path) as image:
        # resize to target resolution
        if image.size[0] > target_resolution[0] or image.size[1] > target_resolution[1]:
            image = image.resize(target_resolution, Image.LANCZOS)

        # reduce quality until below maximum size
        quality = 95
        while quality > 10:
            image.save(output_path, format="JPEG", quality=quality)
            if os.path.getsize(output_path) <= max_size:
                return True
            quality -= 5
        return False
