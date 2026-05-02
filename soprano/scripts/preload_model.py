"""
The point of this script is to call it during the build phase of the Docker image,
so that the model is downloaded and cached in the image itself. This way, when we
run the container, it doesn't have to download the model again, which can save a
lot of time and bandwidth.
"""

from soprano import SopranoTTS

SopranoTTS()
