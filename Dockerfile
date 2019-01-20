FROM python:3
ENV PYTHONIOENCODING=UTF-8
ADD . /src
WORKDIR /src
ENTRYPOINT ["python3"]
RUN pip install --no-cache-dir -r requirements.txt
CMD ["-u", "bot.py"]
