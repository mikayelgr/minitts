# since pytorch doesn't support alpine, we can use at most the slim version
# of the image in order to minimize the image size while still being able
# to install the necessary dependencies
FROM python:3.13-slim
ENV PYTHONUNBUFFERED=1
ENV HF_HUB_DISABLE_PROGRESS_BARS=1

WORKDIR /soprano

RUN pip install soprano-tts==0.2.0 granian==2.7.4 uvloop==0.22.1

EXPOSE 8081
# Running soprano using Granian with uvloop for higher throughput
# in order to be able to use the client libraries provided by OpenAI
# without any additional configuration.
CMD [ "make" ]
