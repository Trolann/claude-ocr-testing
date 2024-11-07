from PIL import Image
import numpy as np
from typing import List
import io
import base64

class ImageDistorter:
    @staticmethod
    def blur(image: Image.Image, radius: int = 2) -> Image.Image:
        """Apply Gaussian blur to image"""
        return image.filter(Image.GaussianBlur(radius))
    
    @staticmethod
    def noise(image: Image.Image, factor: float = 0.1) -> Image.Image:
        """Add random noise to image"""
        img_array = np.array(image)
        noise = np.random.normal(0, factor * 255, img_array.shape)
        noisy_array = np.clip(img_array + noise, 0, 255).astype(np.uint8)
        return Image.fromarray(noisy_array)
    
    @staticmethod
    def rotation(image: Image.Image, angle: float = 5.0) -> Image.Image:
        """Rotate image by specified angle"""
        return image.rotate(angle, expand=True)
    
    @staticmethod
    def compression(image: Image.Image, quality: int = 50) -> Image.Image:
        """Compress image using JPEG compression"""
        buffer = io.BytesIO()
        image.convert('RGB').save(buffer, format='JPEG', quality=quality)
        buffer.seek(0)
        return Image.open(buffer)

    @classmethod
    def apply_distortions(cls, image: Image.Image, distortions: List[str]) -> Image.Image:
        """Apply a list of distortions to an image"""
        distortion_map = {
            'blur': cls.blur,
            'noise': cls.noise,
            'rotation': cls.rotation,
            'compression': cls.compression
        }
        
        result = image.copy()
        for distortion in distortions:
            if distortion in distortion_map:
                result = distortion_map[distortion](result)
        return result

    @staticmethod
    def encode_image(image: Image.Image) -> str:
        """Convert PIL Image to base64 string"""
        buffered = io.BytesIO()
        image.save(buffered, format=image.format or 'PNG')
        return base64.b64encode(buffered.getvalue()).decode("utf-8")
