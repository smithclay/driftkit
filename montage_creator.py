import os
import requests
import numpy as np
from PIL import Image
import io
from moviepy.editor import ImageSequenceClip, AudioFileClip, CompositeVideoClip, VideoFileClip
from moviepy.config import change_settings
from openai import OpenAI
import time
from typing import List, Dict
import math
from dotenv import load_dotenv
import subprocess
import cv2
from scipy.ndimage import gaussian_filter

# Load environment variables
load_dotenv()

class StreetMontageCreator:
    def __init__(self, api_key: str = None, openai_api_key: str = None):
        self._check_ffmpeg()
        
        self.api_key = api_key or os.getenv("GMAPS_API_KEY")
        if not self.api_key:
            raise ValueError("Google Maps API key is required")
            
        openai_key = openai_api_key or os.getenv("OPENAI_API_KEY")
        if not openai_key:
            raise ValueError("OpenAI API key is required")
            
        self.openai_client = OpenAI(api_key=openai_key)
        self.temp_dir = "temp_montage"
        os.makedirs(self.temp_dir, exist_ok=True)
        self.DEFAULT_FPS = 30.0

    def _check_ffmpeg(self):
        try:
            conda_ffmpeg = os.path.join(os.environ.get('CONDA_PREFIX', ''), 'bin', 'ffmpeg')
            if os.path.exists(conda_ffmpeg):
                change_settings({"FFMPEG_BINARY": conda_ffmpeg})
                return
            
            result = subprocess.run(['which', 'ffmpeg'], capture_output=True, text=True)
            if result.returncode == 0:
                ffmpeg_path = result.stdout.strip()
                change_settings({"FFMPEG_BINARY": ffmpeg_path})
                return
            
            raise FileNotFoundError("ffmpeg not found")
        except Exception as e:
            raise RuntimeError(
                "ffmpeg not found. Please install it using:\n"
                "conda: conda install ffmpeg\n"
                "ubuntu: sudo apt-get install ffmpeg\n"
                "macos: brew install ffmpeg"
            ) from e

    def _get_street_view_image(self, lat: float, lon: float, heading: float = 0) -> Image.Image:
        base_url = "https://maps.googleapis.com/maps/api/streetview"
        params = {
            "size": "1280x720",
            "location": f"{lat},{lon}",
            "heading": heading,
            "pitch": "0",
            "outside": "true",
            "key": self.api_key
        }
        
        response = requests.get(base_url, params=params)
        if response.status_code == 200:
            return Image.open(io.BytesIO(response.content))
        else:
            raise Exception(f"Failed to fetch Street View image: {response.status_code}")

    def _create_voiceover(self, script: str, output_path: str) -> float:
        response = self.openai_client.audio.speech.create(
            model="tts-1",
            voice="onyx",
            response_format="aac",
            input=script
        )
        
        response.stream_to_file(output_path)
        
        audio = AudioFileClip(output_path)
        duration = float(audio.duration)
        audio.close()
        
        return duration

    def apply_psychedelic_filter(self, image: np.ndarray, intensity: float = 1.0) -> np.ndarray:
        """
        Apply a psychedelic filter to an image.
        
        Args:
            image: Input image as numpy array
            intensity: Filter intensity (0.0 to 1.0)
            
        Returns:
            Filtered image as numpy array
        """
        # Convert to float for processing
        img_float = image.astype(float) / 255.0
        
        # Split into channels
        b, g, r = cv2.split(img_float)
        
        # Apply color shifting
        r_shift = np.roll(r, int(25 * intensity), axis=1)
        b_shift = np.roll(b, int(-25 * intensity), axis=1)
        
        # Edge enhancement
        edges = cv2.Canny(image, 100, 200)
        edges_float = edges.astype(float) / 255.0
        edges_blurred = gaussian_filter(edges_float, sigma=2)
        
        # Create glowing edges
        glow = gaussian_filter(edges_float, sigma=5)
        
        # Combine channels with shifted colors and glowing edges
        result = cv2.merge([
            np.clip(b_shift + glow * 0.3 * intensity, 0, 1),
            np.clip(g + edges_blurred * 0.5 * intensity, 0, 1),
            np.clip(r_shift + glow * 0.3 * intensity, 0, 1)
        ])
        
        # Add slight color boost
        result = np.clip(result * 1.2, 0, 1)
        
        # Convert back to uint8
        return (result * 255).astype(np.uint8)

    # Add this to the StreetMontageCreator class
    def _apply_psychedelic_effects(self, images: List[np.ndarray], fps: float) -> List[np.ndarray]:
        """
        Apply psychedelic effects to a sequence of images.
        
        Args:
            images: List of input images
            fps: Frames per second
            
        Returns:
            List of processed images
        """
        processed_images = []
        frame_count = len(images)
        
        for i, image in enumerate(images):
            # Calculate pulsing intensity based on frame position
            time_position = i / fps
            intensity = 0.5 + 0.3 * np.sin(2 * np.pi * time_position)
            
            # Apply the psychedelic filter
            processed = self.apply_psychedelic_filter(image, intensity)
            processed_images.append(processed)
            
        return processed_images

    def create_montage(self, locations: List[Dict], script: str, output_path: str, fps: float = None) -> None:
        fps = float(fps) if fps is not None else float(self.DEFAULT_FPS)
        print(f"Starting video creation with fps: {fps}")
        
        if not locations:
            raise ValueError("At least one location is required")

        # Create temporary files
        temp_video = os.path.join(self.temp_dir, "temp_video.mp4")
        audio_path = os.path.join(self.temp_dir, "voiceover.aac")
        
        try:
            # Generate voiceover first
            duration = self._create_voiceover(script, audio_path)
            print(f"Generated voiceover with duration: {duration}")

            # Calculate frames needed
            total_frames = int(math.ceil(duration * fps))
            frames_per_location = max(1, total_frames // len(locations))
            print(f"Total frames needed: {total_frames}, frames per location: {frames_per_location}")

            # Generate images
            images = []
            for location in locations:
                lat = None
                lon = None

                if 'lat' in location['coordinates'] and 'lon' in location['coordinates']:
                    lat = location['coordinates']['lat']
                    lon = location['coordinates']['lon']
                
                if 'latitude' in location['coordinates'] and 'longitude' in location['coordinates']:
                    lat = location['coordinates']['latitude']
                    lon = location['coordinates']['longitude']

                if lat is None or lon is None:
                    raise ValueError("Latitude and longitude are required for each location")

                for frame in range(frames_per_location):
                    heading = (360 / frames_per_location) * frame
                    try:
                        image = self._get_street_view_image(lat, lon, heading)
                        images.append(np.array(image))
                    except Exception as e:
                        print(f"Error fetching image for location {location['name']}: {e}")
                        if images:
                            images.append(images[-1].copy())
                        else:
                            images.append(np.zeros((720, 1280, 3), dtype=np.uint8))
                    time.sleep(0.1)

            # Ensure we have enough frames
            while len(images) < total_frames:
                images.append(images[-1].copy())
            images = images[:total_frames]
            
            print(f"Generated {len(images)} images")

            # Apply psychedelic effects
            print("Applying psychedelic effects...")
            images = self._apply_psychedelic_effects(images, fps)

            # Create video without audio first
            print("Creating video clip...")
            video = ImageSequenceClip(images, fps=fps)
            if not hasattr(video, 'fps') or video.fps is None:
                video.fps = fps
            print(f"Video clip created with fps: {video.fps}")

            # Write temporary video file
            print("Writing temporary video file...")
            video.write_videofile(
                temp_video,
                fps=fps,
                codec='libx264',
                audio=False,
                verbose=False
            )

            # Load the video and audio separately
            print("Loading video and audio for final composition...")
            video_clip = VideoFileClip(temp_video)
            audio_clip = AudioFileClip(audio_path)

            # Set the video duration to match the audio
            video_clip = video_clip.set_duration(audio_clip.duration)

            # Combine video and audio
            print("Creating final video with audio...")
            final_clip = video_clip.set_audio(audio_clip)
            
            # Write final video
            print(f"Writing final video to {output_path}...")
            final_clip.write_videofile(
                output_path,
                fps=fps,
                codec='libx264',
                audio_codec='aac',
                temp_audiofile=os.path.join(self.temp_dir, "temp_audio.aac"),
                remove_temp=True,
                verbose=False
            )

            print("Video creation completed successfully!")

        except Exception as e:
            raise Exception(f"Error creating video: {str(e)}")
            
        finally:
            # Cleanup
            for file in [temp_video, audio_path]:
                if os.path.exists(file):
                    try:
                        os.remove(file)
                    except:
                        pass
