#help: docker access to disk E:\
#try:search for something which is not exists
#если не смог достучаться и получить magnet link - надо опять возвращать на выбор
#если маленькая скорость - предложить найти что-то другое
#requirements
#если с нуля, будет ли скачиваться несколько параллельнор
FROM python:3
ENV PYTHONIOENCODING=UTF-8
ADD . /src
WORKDIR /src
RUN pip install python-telegram-bot --upgrade; pip install requests;
ENTRYPOINT ["python3"]
CMD ["-u", "bot.py"]
