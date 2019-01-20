#! /usr/bin/env python3
import requests
import random
import traceback
import operator
import json
import time
import threading
import os

from telegram.ext import CommandHandler
from telegram.ext import Filters
from telegram.ext import Updater
from telegram.ext import CallbackQueryHandler
from telegram import InlineKeyboardMarkup
from telegram import InlineKeyboardButton
from threading import Timer


class Link:
	def __init__(self, tracker, quality, translations, link, size, seeders):
		self.tracker = tracker
		self.quality = quality
		self.translations = translations
		self.link = link
		self.size = size
		self.seeders = seeders

	def __str__(self):
		return "[{0} seeders] {1} {2} {3} {4}".format(self.seeders, self.quality, self.size, str(self.translations), self.tracker)

	def readable_name(self):
		return self.quality


class Movie:
	def __init__(self, title, url):
		self.title = title
		self.url = url

	def __str__(self):
		return self.title


class TorrentOwner:
	def __init__(self, name, chat_id):
		self.name = name
		self.chat_id = chat_id
		self.time = time.time()
		self.half_report = False


class Chats:
	def __init__(self):
		self.chats = {}

	def get_chat_data(self, chat_id):
		if chat_id not in self.chats:
			self.chats.update({chat_id: ChatData()})

		return self.chats[chat_id]


class ChatData:
	def __init__(self):
		self.chosen_links = []
		self.chosen_movies = []
		self.chosen_link = None
		self.chosen_movie = None
		self.language = "ru"
		self.movies = []
		self.links = []

	def format_chosen(self):
		return "\"" + str(self.chosen_movie) + "|" + str(self.chosen_link) + "\""


class Torrent:
	def __init__(self):
		self.owners = []
		self.bot = None
		self.cookie = ""
		self.timers = {}

		self.get_ssid()

		thread1 = threading.Thread(target=self.state_loop)
		thread1.start()

	def get_ssid(self):
		print("Obtaining SSID")
		resp = requests.post("http://qtor:8080/login", timeout=60, data={"username": "admin", "password": "adminadmin"})

		if resp.status_code != 200 or resp.text != 'Ok.':
			print("Can't obtain cookie: " + resp.text)
			exit(1)

		self.cookie = resp.cookies["SID"]
		print("SID: " + self.cookie)

	def state_loop(self):
		while True:
			try:
				print("Iterating state_loop")
				self.state_loop_imp()
				print("state_loop done")
			except Exception as exp:
				print("Caught exception in state_loop")
				print("Traceback: " + traceback.format_exc())
				print("Exception: " + str(exp))

	def state_loop_imp(self):
		while True:
			if self.bot is not None:
				to_remove = []
				current = self.get_state()
				for item in current:
					for owner in self.owners:
						if owner.name == item["name"].replace("+", " "):
							if item["state"] == "stalledUP":
								self.bot.send_message(
									chat_id=owner.chat_id,
									text=get_string("success_downloading") + "\"" + owner.name + "\". " + get_string("search_here") + item["save_path"].replace("/downloads/", "")
								)
								to_remove.append(owner)
							if owner.time is not None:
								if (time.time() - owner.time) > 5:
									self.bot.send_message(chat_id=owner.chat_id, text=get_string("here_it_is") + self.format_torrent_report(item))
									owner.time = None
							if (owner.half_report is False) and (item["progress"] > 0.5):
								owner.half_report = True
								self.bot.send_message(chat_id=owner.chat_id, text=get_string("half_report") + self.format_torrent_report(item))

				for rm in to_remove:
					self.owners.remove(rm)

			time.sleep(5)

	def get_qtor(self, url):
		cookies = dict(SID=self.cookie)
		resp = requests.get("http://qtor:8080/" + url, cookies=cookies, timeout=60)

		if resp.status_code != 200:
			print("get code: " + str(resp.status_code))
			self.get_ssid()
			return self.get_qtor(url)

		return resp

	def post_qtor(self, url, form_data):
		cookies = dict(SID=self.cookie)
		resp = requests.post("http://qtor:8080/" + url, cookies=cookies, data=form_data, timeout=60)

		if resp.status_code != 200:
			print("post code: " + str(resp.status_code))
			self.get_ssid()
			return self.post_qtor(url, form_data)

		return resp

	def check_bot(self, bot):
		if self.bot is None:
			print("Bot is none. Setting it.")
			self.bot = bot

	def download_magnet(self, bot, update, magnet, name):
		try:
			self.check_bot(bot)
			chat_id = get_chat_id(update)
			chat_data = chats.get_chat_data(chat_id)

			self.post_qtor("command/download", {"urls": magnet, "rename": name, "savepath": "/downloads/" + name})
			print("Starting download")

			self.owners.append(TorrentOwner(name, chat_id))
			bot.send_message(chat_id=chat_id, text=get_string("start_downloading") + chat_data.format_chosen() + ". " + get_string("wait_a_minute"))

		except Exception as exp:
			print("Traceback: " + traceback.format_exc())
			print("Exception: " + str(exp))
			bot.send_message(chat_id=chat_id, text=get_string("call_programmer"))

	def empty(self, bot, update):
		try:
			self.check_bot(bot)
			chat_id = get_chat_id(update)

		except Exception as exp:
			print("Traceback: " + traceback.format_exc())
			print("Exception: " + str(exp))
			bot.send_message(chat_id=chat_id, text=get_string("call_programmer"))

	def qtor_rm_torrent(self, tor_hash):
		self.post_qtor("command/deletePerm", {"hashes": tor_hash})

	def qtor_rm_torrent_no_delete(self, tor_hash):
		self.post_qtor("command/delete", {"hashes": tor_hash})

	def qtor_pause(self, tor_hash):
		self.post_qtor("command/pause", {"hash": tor_hash})

	def qtor_resume(self, tor_hash):
		self.post_qtor("command/resume", {"hash": tor_hash})

	def qtor_throttle(self, tor_hash, limit):
		self.post_qtor("command/setTorrentsDlLimit", {"hashes": tor_hash, "limit": limit})

	def qtor_global_throttle(self, limit):
		self.post_qtor("command/setGlobalDlLimit", {"limit": limit})

	def timeout(self, chat_id, message_id):
		print("Action timeout")
		self.bot.edit_message_text(chat_id=chat_id, message_id=message_id, text=get_string("act_timeout"))

	def add_timer(self, chat_id, message_id, timeout_sec=60):
		timer = Timer(timeout_sec, self.timeout, kwargs={"chat_id": chat_id, "message_id": message_id})

		self.timers.update({chat_id + message_id: timer})
		timer.start()

	def remove_timer(self, chat_id, message_id):
		id = chat_id + message_id

		if id in self.timers:
			timer = self.timers[id]
			timer.cancel()
			del self.timers[id]
			print("Found timer and removing it")

	def torrents(self, bot, update):
		try:
			self.check_bot(bot)
			chat_id = get_chat_id(update)

			keyboard = []
			torrents = self.get_state()

			if len(torrents) > 0:
				for current in torrents:
					keyboard.append([InlineKeyboardButton(current["name"].replace("+", " "), callback_data="torrents:" + current["hash"])])

				msg = bot.send_message(chat_id=chat_id, text=get_string("torrents_choose"), reply_markup=InlineKeyboardMarkup(keyboard))
				self.add_timer(chat_id, msg.message_id)
			else:
				bot.send_message(chat_id=chat_id, text=get_string("status_empty"))

		except Exception as exp:
			print("Traceback: " + traceback.format_exc())
			print("Exception: " + str(exp))
			bot.send_message(chat_id=chat_id, text=get_string("call_programmer"))

	def choose_torrent(self, bot, update, args):
		try:
			self.check_bot(bot)
			chat_id = get_chat_id(update)
			keyboard = []

			tor_hash = args[1]
			keyboard.append([InlineKeyboardButton(get_string("torrent_act_cancel"), callback_data="torrent_act_cancel:" + tor_hash)])
			keyboard.append([InlineKeyboardButton(get_string("torrent_act_pause"), callback_data="torrent_act_pause:" + tor_hash)])
			keyboard.append([InlineKeyboardButton(get_string("torrent_act_resume"), callback_data="torrent_act_resume:" + tor_hash)])
			keyboard.append([InlineKeyboardButton(get_string("torrent_act_throttle"), callback_data="torrent_act_throttle:" + tor_hash)])

			self.remove_timer(chat_id, update.callback_query.message.message_id)
			bot.edit_message_text(chat_id=chat_id, message_id=update.callback_query.message.message_id, text=get_string("torrent_chosen"))
			msg = bot.send_message(chat_id=chat_id, text=get_string("torrent_act_choose"), reply_markup=InlineKeyboardMarkup(keyboard))
			self.add_timer(chat_id, msg.message_id)
		except Exception as exp:
			print("Traceback: " + traceback.format_exc())
			print("Exception: " + str(exp))
			bot.send_message(chat_id=chat_id, text=get_string("call_programmer"))

	def torrent_act_cancel(self, bot, update, args):
		try:
			self.check_bot(bot)
			chat_id = get_chat_id(update)
			self.qtor_rm_torrent(args[1])

			bot.edit_message_text(chat_id=chat_id, message_id=update.callback_query.message.message_id, text=get_string("torrent_act_cancel_chosen"))
			self.remove_timer(chat_id, update.callback_query.message.message_id)

		except Exception as exp:
			print("Traceback: " + traceback.format_exc())
			print("Exception: " + str(exp))
			bot.send_message(chat_id=chat_id, text=get_string("call_programmer"))

	def torrent_act_pause(self, bot, update, args):
		try:
			self.check_bot(bot)
			chat_id = get_chat_id(update)
			self.qtor_pause(args[1])
			bot.edit_message_text(chat_id=chat_id, message_id=update.callback_query.message.message_id, text=get_string("torrent_act_pause_chosen"))
			self.remove_timer(chat_id, update.callback_query.message.message_id)

		except Exception as exp:
			print("Traceback: " + traceback.format_exc())
			print("Exception: " + str(exp))
			bot.send_message(chat_id=chat_id, text=get_string("call_programmer"))

	def torrent_act_resume(self, bot, update, args):
		try:
			self.check_bot(bot)
			chat_id = get_chat_id(update)
			self.qtor_resume(args[1])
			bot.edit_message_text(chat_id=chat_id, message_id=update.callback_query.message.message_id, text=get_string("torrent_act_resume_chosen"))
			self.remove_timer(chat_id, update.callback_query.message.message_id)

		except Exception as exp:
			print("Traceback: " + traceback.format_exc())
			print("Exception: " + str(exp))
			bot.send_message(chat_id=chat_id, text=get_string("call_programmer"))

	def torrent_act_throttle(self, bot, update, args):
		try:
			self.check_bot(bot)
			chat_id = get_chat_id(update)
			keyboard = []

			tor_hash = args[1]
			keyboard.append([InlineKeyboardButton(get_string("throttle_0.5"), callback_data="throttle:" + tor_hash + ":512000")])
			keyboard.append([InlineKeyboardButton(get_string("throttle_1.0"), callback_data="throttle:" + tor_hash + ":1048576")])
			keyboard.append([InlineKeyboardButton(get_string("throttle_2.5"), callback_data="throttle:" + tor_hash + ":2621440")])
			keyboard.append([InlineKeyboardButton(get_string("throttle_5.0"), callback_data="throttle:" + tor_hash + ":5242880")])
			keyboard.append([InlineKeyboardButton(get_string("throttle_7.0"), callback_data="throttle:" + tor_hash + ":7340032")])
			keyboard.append([InlineKeyboardButton(get_string("throttle_10.0"), callback_data="throttle:" + tor_hash + ":10485760")])
			keyboard.append([InlineKeyboardButton(get_string("throttle_15.0"), callback_data="throttle:" + tor_hash + ":15728640")])
			keyboard.append([InlineKeyboardButton(get_string("throttle_0.0"), callback_data="throttle:" + tor_hash + ":0")])

			bot.edit_message_text(chat_id=chat_id, message_id=update.callback_query.message.message_id, text=get_string("torrent_act_throttle_chosen"))
			self.remove_timer(chat_id, update.callback_query.message.message_id)
			msg = bot.send_message(chat_id=chat_id, text=get_string("throttle_choose"), reply_markup=InlineKeyboardMarkup(keyboard))
			self.add_timer(chat_id, msg.message_id)

		except Exception as exp:
			print("Traceback: " + traceback.format_exc())
			print("Exception: " + str(exp))
			bot.send_message(chat_id=chat_id, text=get_string("call_programmer"))

	def torrent_act_throttle_choose(self, bot, update, args):
		try:
			self.check_bot(bot)
			chat_id = get_chat_id(update)

			self.qtor_throttle(args[1], int(args[2]))

			bot.edit_message_text(chat_id=chat_id, message_id=update.callback_query.message.message_id, text=get_string("done"))
			self.remove_timer(chat_id, update.callback_query.message.message_id)
		except Exception as exp:
			print("Traceback: " + traceback.format_exc())
			print("Exception: " + str(exp))
			bot.send_message(chat_id=chat_id, text=get_string("call_programmer"))

	def actions(self, bot, update):
		try:
			self.check_bot(bot)
			chat_id = get_chat_id(update)

			keyboard = []
			keyboard.append([InlineKeyboardButton(get_string("global_act_pause_all"), callback_data="global_act_pause_all")])
			keyboard.append([InlineKeyboardButton(get_string("global_act_resume_all"), callback_data="global_act_resume_all")])
			keyboard.append([InlineKeyboardButton(get_string("global_act_remove_all"), callback_data="global_act_remove_all")])
			keyboard.append([InlineKeyboardButton(get_string("global_act_remove_no_delete_all"), callback_data="global_act_remove_no_delete_all")])
			keyboard.append([InlineKeyboardButton(get_string("global_act_throttle"), callback_data="global_act_throttle")])

			msg = bot.send_message(chat_id=chat_id, text=get_string("global_act_choose"), reply_markup=InlineKeyboardMarkup(keyboard))
			self.add_timer(chat_id, msg.message_id)

		except Exception as exp:
			print("Traceback: " + traceback.format_exc())
			print("Exception: " + str(exp))
			bot.send_message(chat_id=chat_id, text=get_string("call_programmer"))

	def global_act_pause_all(self, bot, update, args):
		try:
			self.check_bot(bot)
			chat_id = get_chat_id(update)

			torrents = self.get_state()
			for current in torrents:
				self.qtor_pause(current["hash"])

			bot.edit_message_text(chat_id=chat_id, message_id=update.callback_query.message.message_id, text=get_string("global_act_pause_all_chosen"))
			self.remove_timer(chat_id, update.callback_query.message.message_id)

		except Exception as exp:
			print("Traceback: " + traceback.format_exc())
			print("Exception: " + str(exp))
			bot.send_message(chat_id=chat_id, text=get_string("call_programmer"))

	def global_act_resume_all(self, bot, update, args):
		try:
			self.check_bot(bot)
			chat_id = get_chat_id(update)

			torrents = self.get_state()
			for current in torrents:
				self.qtor_resume(current["hash"])

			bot.edit_message_text(chat_id=chat_id, message_id=update.callback_query.message.message_id, text=get_string("global_act_resume_all_chosen"))
			self.remove_timer(chat_id, update.callback_query.message.message_id)

		except Exception as exp:
			print("Traceback: " + traceback.format_exc())
			print("Exception: " + str(exp))
			bot.send_message(chat_id=chat_id, text=get_string("call_programmer"))

	def global_act_remove_all(self, bot, update, args):
		try:
			self.check_bot(bot)
			chat_id = get_chat_id(update)

			torrents = self.get_state()
			for current in torrents:
				self.qtor_rm_torrent(current["hash"])

			bot.edit_message_text(chat_id=chat_id, message_id=update.callback_query.message.message_id, text=get_string("global_act_remove_all_chosen"))
			self.remove_timer(chat_id, update.callback_query.message.message_id)

		except Exception as exp:
			print("Traceback: " + traceback.format_exc())
			print("Exception: " + str(exp))
			bot.send_message(chat_id=chat_id, text=get_string("call_programmer"))

	def global_act_remove_no_delete_all(self, bot, update, args):
		try:
			self.check_bot(bot)
			chat_id = get_chat_id(update)

			torrents = self.get_state()
			for current in torrents:
				self.qtor_rm_torrent_no_delete(current["hash"])

			bot.edit_message_text(chat_id=chat_id, message_id=update.callback_query.message.message_id, text=get_string("global_act_remove_no_delete_all"))
			self.remove_timer(chat_id, update.callback_query.message.message_id)

		except Exception as exp:
			print("Traceback: " + traceback.format_exc())
			print("Exception: " + str(exp))
			bot.send_message(chat_id=chat_id, text=get_string("call_programmer"))

	def global_act_throttle(self, bot, update, args):
		try:
			self.check_bot(bot)
			chat_id = get_chat_id(update)

			keyboard = []
			keyboard.append([InlineKeyboardButton(get_string("throttle_0.5"), callback_data="global_throttle:512000")])
			keyboard.append([InlineKeyboardButton(get_string("throttle_1.0"), callback_data="global_throttle:1048576")])
			keyboard.append([InlineKeyboardButton(get_string("throttle_2.5"), callback_data="global_throttle:2621440")])
			keyboard.append([InlineKeyboardButton(get_string("throttle_5.0"), callback_data="global_throttle:5242880")])
			keyboard.append([InlineKeyboardButton(get_string("throttle_7.0"), callback_data="global_throttle:7340032")])
			keyboard.append([InlineKeyboardButton(get_string("throttle_10.0"), callback_data="global_throttle:10485760")])
			keyboard.append([InlineKeyboardButton(get_string("throttle_15.0"), callback_data="global_throttle:15728640")])
			keyboard.append([InlineKeyboardButton(get_string("throttle_0.0"), callback_data="global_throttle:0")])

			bot.edit_message_text(chat_id=chat_id, message_id=update.callback_query.message.message_id, text=get_string("global_act_throttle_chosen"))
			self.remove_timer(chat_id, update.callback_query.message.message_id)
			msg = bot.send_message(chat_id=chat_id, text=get_string("throttle_choose"), reply_markup=InlineKeyboardMarkup(keyboard))
			self.add_timer(chat_id, msg.message_id)

		except Exception as exp:
			print("Traceback: " + traceback.format_exc())
			print("Exception: " + str(exp))
			bot.send_message(chat_id=chat_id, text=get_string("call_programmer"))

	def global_act_throttle_choose(self, bot, update, args):
		try:
			self.check_bot(bot)
			chat_id = get_chat_id(update)

			self.qtor_global_throttle(int(args[1]))

			bot.edit_message_text(chat_id=chat_id, message_id=update.callback_query.message.message_id, text=get_string("done"))
			self.remove_timer(chat_id, update.callback_query.message.message_id)
		except Exception as exp:
			print("Traceback: " + traceback.format_exc())
			print("Exception: " + str(exp))
			bot.send_message(chat_id=chat_id, text=get_string("call_programmer"))

	def get_state(self):
		resp = self.get_qtor("query/torrents")

		return json.loads(resp.text)

	def format_torrent_report(self, current):
		return \
			"[{3:.2f}%] {0} {1} seeders {4:.2f} Mb/s ~{2:.2f} {5}" \
				.format(current["name"].replace("+", " "), current["num_seeds"], current["eta"] / 60.0,
						current["progress"] * 100.0,
						current["dlspeed"] / 1048576.0, get_string("minutes"))

	def status(self, bot, update):
		try:
			self.check_bot(bot)
			chat_id = get_chat_id(update)

			torrent_json = self.get_state()

			report = "\n"
			if len(torrent_json) > 0:
				for current in torrent_json:
					report += "* " + self.format_torrent_report(current) + "\n"
			else:
				report = get_string("status_empty")

			bot.send_message(chat_id=chat_id, text=get_string("status_list") + report)

		except Exception as exp:
			print("Traceback: " + traceback.format_exc())
			print("Exception: " + str(exp))
			bot.send_message(chat_id=chat_id, text=get_string("call_programmer"))


strings =\
	{
		"ru":
			{
				"welcome": [u"Привет! Я бот, который будет качать тебе торренты "],
				"how_to": [u" У меня есть следующие команды:\n"\
						   "/search - поиск фильма. Просто отправь мне сообщение, например: '/search Индиана Джонс'.\n" \
						   "/torrents - получить список текущих закачек, чтобы сделать с ними что-нибудь\n"\
						   "/actions - получить список глобальных действий. Вроде удаления всего, что было скачано, ограничения скорости для всех скачиваемых торрентов и т.п.\n"\
						   "/status - текущий статус всех закачек\n\n"\
						   "Немного деталей о том, как я работаю:\n"\
						   "* Список торрентов для скачивания я получаю с сайта cinemate.cc. Из списка я отсеиваю трэкеры и беру только: tfile, rutracker, nnmclub, rutor."\
						   " Остальные не поддерживают магнитные ссылки. Я беру всё, что нашлось, сортирую по количеству сидеров (оно на сайте указанно приблизительное)"\
						   " и вывожу на выбор 50 первых вариантов. Хочется отдельно отметить, что данные по торентам я получаю из магнитных ссылок, но некоторые раздачи"\
						   " на трэкерах были созданы до того, как они начала поддерживать магнитные ссылки и следовательно для меня нет возможности их скачать,"\
						   " но при этом в списке для выбора они будут попадать: я их не анализирую заблаговременно. При попытке скачать такой торрент, тебе скажут, что"\
						   " он не очень и предложат выбрать что-нибудь другое.\n"\
						   "* Я работаю через Tor, поэтому некоторые запросы могут выполняться ни одну и ни две секунды. Когда ты выбрал что-то из предложенного мной списка действий,"\
						   " будь любезен, прояви терпение и подожди, не надо затыкивать меня до полу-смерти, это не ускорит процесс.\n"\
						   "* Через минуту, после начала закачки я отпишусь о том как идут дела. Также я сообщу, когда скачаю половину торрента и когда закончу скачивание.\n"\
						   "У каждого торрента в квадратных скобках указывается какой-то набор букв, например: ['ППД', 'О', 'С']. Это наркоманские, но весьма эффективные сокращения с сайта cinemate.cc:\n"\
						   "ППД - Дублях\nАО - Авторский, одноголосный\nЛО - Любительский, одноголосный\nО - оригинальная дорожка\nС - субтитры\n3D - 5.1 и всё такое\n"
						   "ПМЗ - професионнальный многоголосный, закадровый\nTS - дубляж, но из кинотеатра, хрум-хрум"],
				"searching_hard": [u"Ну всё, я пошёл усиленно искать, скоро будут результаты..."],
				"search_success": [u"Чего-то нашлось. Сейчас составлю список."],
				"search_choose": [u"В общем, вот. Выбирай."],
				"links_choose": [u"Выбери что будем качать"],
				"torrents_choose": [u"Выберите торрент для действий:"],
				"torrent_act_choose": [u"Выберите действие:"],
				"link_choose": [u"Шикарный выбор!"],
				"torrent_chosen": [u"Торрент выбран"],
				"global_act_pause_all": [u"Приостановить закачку всего"],
				"global_act_resume_all": [u"Возобновить закачку всего"],
				"global_act_remove_all": [u"Удалить всё скачанное с файлами"],
				"global_act_remove_no_delete_all": [u"Очистить список закачек"],
				"global_act_throttle": [u"Изменить скорость для всех торрентов"],
				"global_act_pause_all_chosen": [u"Вы решили приостановить закачку всех торрентов"],
				"global_act_resume_all_chosen": [u"Вы возобновили закачку всех торрентов"],
				"global_act_remove_all_chosen": [u"Вы удалили все торренты и скачанные файлы"],
				"global_act_remove_no_delete_all_chosen": [u"Вы очистили список торрентов"],
				"global_act_throttle_chosen": [u"Решили ограничить скорость скачивания всех торрентов"],
				"global_act_choose": [u"Выберите глобальное действие:"],
				"act_timeout": [u"Здесь было какой-то выбор, но вы слишком долго думали."],
				"done": [u"Сделано"],
				"checking": [u"Проверка"],
				"down_metadata": [u"Скачиваю метадату"],
				"downloading": [u"Скачивается"],
				"downloaded": [u"скачано"],
				"finished": [u"Завершено"],
				"already_downloading": [u"Я уже тут качаю кое чего.\n/report - чтобы зунать что я качаю\n/stop - чтобы прервать закачку"],
				"seeding": [u"Раздаю"],
				"torrent_act_pause": [u"Остановить скачивание"],
				"torrent_act_resume": [u"Продолжить скачивание"],
				"torrent_act_cancel": [u"Отменить скачивание и удалить файлы"],
				"torrent_act_throttle": [u"Ограничить скорость"],
				"torrent_act_pause_chosen": [u"Выбрано: Остановить скачивание"],
				"torrent_act_resume_chosen": [u"Выбрано: Продолжить скачивание"],
				"torrent_act_cancel_chosen": [u"Выбрано: Отменить скачивание и удалить файлы"],
				"torrent_act_throttle_chosen": [u"Выбрано: Ограничить скорость"],
				"success_downloading": [u"Скачалось "],
				"allocating": [u"Выделяю место"],
				"status_list": [u"Текущий статус: "],
				"minutes": [u"минут"],
				"throttle_choose": [u"Выберите ограничение по скорости:"],
				"throttle_0.0": [u"Снять все ограничения"],
				"throttle_0.5": [u"До 0.5 Mb/сек"],
				"throttle_1.0": [u"До 1.0 Mb/сек"],
				"throttle_2.5": [u"До 2.5 Mb/сек"],
				"throttle_5.0": [u"До 5.0 Mb/сек"],
				"throttle_7.0": [u"До 7.0 Mb/сек"],
				"throttle_10.0": [u"До 10.0 Mb/сек"],
				"throttle_15.0": [u"До 15.0 Mb/сек"],
				"half_report": [u"Половину уже скачал: "],
				"here_it_is": [u"Раскочегарился и качаю: "],
				"search_here": [u"Ищите его тут: "],
				"wait_a_minute": [u"Через минуту напишу как успехи."],
				"status_empty": [u"ничего не качается :("],
				"nothing_to_dwn": [u"Ничего нет в задачах"],
				"no_tracker": [u"Всё очень странно запуталось. У меня на руках то, чего не существует. Что я должен делать? Паника!"],
				"search_nothing": [u"Неа, ничего такого не нашлось."],
				"getting_redirection": [u"Так, нужно нырнуть глубже, чтобы достать сам фильм."],
				"magnet_is_dead": [u"Жаль, но у этого варианта фильма битая ссылка."],
				"selected_movie": [u"Выбор пал на \""],
				"cant_get_metadata": [u"Нет, плохой вариант фильма, давай другое что-нибудь."],
				"download_by_magnet": [u"Схватил, рассматриваю подойдёт ли он нам. Это может занять несколько минут"],
				"stopping_downloading": [u"Останавливаю текущую закачку. Сейчас, секундочку."],
				"start_downloading": [u"Начинаю стягивать "],
				"failed": [u"Я сломался, давай ещё раз?"],
				"get_redirect_failed": [u"Я попробовал нырнуть, но стукнулся лбом о дно. Давай повторим немного позже, когда заживёт?"],
				"getting_rutracker_magnet": [u"Уже вижу его, сейчас начну тянуть!"],
				"get_links_failed": [u"Ой-ой-ой никаких ссылок, откуда мы могли бы скачаться, на этот фильм нету. Беда - печаль."],
				"getting_links": [u"Шарю в поисках всех доступных вариантов фильма"],
				"call_programmer":
					[u"Ой, мне стало плохо, срочно зовите программиста!",
					 u"Смотрю я на себя и понимаю, что без программиста тут не обойтись: я поломался чуть меньше, чем полностью...",
					 u"Батюшки свет, у меня функциональность отвалилась. Позовите на помощь!!!",
					 u"Сегодня я самый больной в мире бот, зовите врачей и программистов - пусть лечат."],
				"search_fail": [u"Сорян, что-то с поиском проблемы", u"Блин, поиск обломился. Попробуй чуть позже, а?", u"Чего-то не ищется ни шиша.", u"Искалка сломалась, занавес, насмотрелись."]
			},
		"en":
			{
				"welcome": ["Hello there!", "Hi!"]
			},
	}
torrent = Torrent()
proxy = {"http": "http://tor:8118"}
language = "ru"
chats = Chats()


def get_string(title):
	found_str = strings.get(language).get(title)

	return found_str[random.randint(0, len(found_str) - 1)]


def start(bot, update):
	help(bot, update)


def help(bot, update):
	torrent.check_bot(bot)
	bot.send_message(chat_id=update.message.chat_id, text=get_string("welcome") + get_string("how_to"))


def search(bot, update):
	torrent.check_bot(bot)
	chat_id = get_chat_id(update)
	chat_data = chats.get_chat_data(chat_id)

	try:
		print("Searching...")
		search_request = update.message.text[update.message.text.index(" ") + 1:]
		bot.send_message(chat_id=chat_id, text=get_string("searching_hard"))

		resp = requests.get("http://cinemate.cc/search/movie/?term=" + search_request, proxies=proxy, timeout=60)

		if resp.status_code != 200:
			bot.send_message(chat_id=chat_id, text=get_string("search_fail"))
			print("Can't search on cinemate: " + resp.text)
			raise BaseException("Can't search on cinemate: " + resp.text)

		text = resp.text

		bot.send_message(chat_id=chat_id, text=get_string("search_success"))
		if text.find("class=\"posterbig\"") > 0:
			links_index = text.find("links/#tabs")
			href_index = text.find("href", links_index - 20)
			chat_data.chosen_movie = Movie(search_request, "http://")
			get_links(bot, update, text[href_index + 6:links_index] + "links")
			return
		else:
			last_poster_index = 0
			chat_data.movies.clear()
			while True:
				last_poster_index = text.find("class=\"poster\"", last_poster_index)

				if last_poster_index <= 0:
					break

				title_index = text.find("title", last_poster_index - 150)
				title_end = text.find("\"", title_index + 7)
				title = text[title_index + 7:title_end]
				last_poster_index = title_end + 15

				url_index = text.find("\"", text.find("<a href=", title_end))
				url_index_end = text.find("\"", url_index + 1)
				url = text[url_index + 1:url_index_end - 1]

				chat_data.movies.append(Movie(title, url))

		if len(chat_data.movies) > 0:
			keyboard = []

			for i in range(len(chat_data.movies)):
				keyboard.append([InlineKeyboardButton("{0}".format(chat_data.movies[i].title), callback_data="movie:" + str(i))])

			msg = update.message.reply_text(text=get_string("search_choose"), reply_markup=InlineKeyboardMarkup(keyboard))
			torrent.add_timer(chat_id, msg.message_id)
		else:
			bot.send_message(chat_id=chat_id, text=get_string("search_nothing"))
	except Exception as exp:
		print("Traceback: " + traceback.format_exc())
		print("Exception: " + str(exp))
		bot.send_message(chat_id=chat_id, text=get_string("call_programmer"))


def movie_callback(bot, update, args):
	chat_id = get_chat_id(update)
	chat_data = chats.get_chat_data(chat_id)

	torrent.check_bot(bot)

	index = int(args[1])
	chat_data.chosen_movie = chat_data.movies[index]
	print("Chosen: " + str(chat_data.chosen_movie))
	chat_data.chosen_movies.append(chat_data.chosen_movie)

	bot.edit_message_text(chat_id=chat_id, message_id=update.callback_query.message.message_id, text=get_string("selected_movie") + chat_data.chosen_movie.title + "\"")
	torrent.remove_timer(chat_id, update.callback_query.message.message_id)

	get_links(bot, update, chat_data.chosen_movie.url + "/links")


def link_callback(bot, update, args):
	chat_id = get_chat_id(update)
	chat_data = chats.get_chat_data(chat_id)
	torrent.check_bot(bot)

	index = int(args[1])
	chat_data.chosen_link = chat_data.links[index]
	chat_data.chosen_links.append(chat_data.chosen_link)
	bot.edit_message_text(chat_id=chat_id, message_id=update.callback_query.message.message_id, text=get_string("link_choose"))
	torrent.remove_timer(chat_id, update.callback_query.message.message_id)

	trackers = {
		"rutracker.org": get_rutracker_magnet,
		"rutor.info": get_rutor_magnet,
		"tfile.me": get_tfile_magnet,
		"nnmclub.to": get_nnm_magnet
	}

	if chat_data.chosen_link.tracker in trackers:
		download_magnet(bot, update, trackers[chat_data.chosen_link.tracker](bot, update, get_redirect_url(bot, update, "/go/s/" + chat_data.chosen_link.link)))
	else:
		bot.send_message(chat_id=chat_id, text=get_string("no_tracker"))


def find_callback(bot, update, title, args):
	calls = {
		"movie": movie_callback,
		"link": link_callback,
		"torrents": torrent.choose_torrent,
		"torrent_act_cancel": torrent.torrent_act_cancel,
		"torrent_act_pause": torrent.torrent_act_pause,
		"torrent_act_resume": torrent.torrent_act_resume,
		"torrent_act_throttle": torrent.torrent_act_throttle,
		"global_act_pause_all": torrent.global_act_pause_all,
		"global_act_remove_all": torrent.global_act_remove_all,
		"global_act_remove_no_delete_all": torrent.global_act_remove_no_delete_all,
		"global_act_throttle": torrent.global_act_throttle,
		"global_throttle": torrent.global_act_throttle_choose,
		"global_act_resume_all": torrent.global_act_resume_all,
		"throttle": torrent.torrent_act_throttle_choose
	}

	if title in calls:
		calls[title](bot, update, args)
	else:
		bot.send_message(chat_id=update.message.chat_id, text=get_string("failed"))


def callback(bot, update):
	try:
		query = update.callback_query.data.split(":")
		find_callback(bot, update, query[0], query)
	except Exception as exp:
		print("Traceback: " + traceback.format_exc())
		print("Exception: " + str(exp))
		bot.send_message(chat_id=update.callback_query.message.chat_id, text=get_string("call_programmer"))


def get_rutracker_magnet(bot, update, url):
	try:
		chat_id = get_chat_id(update)

		print("Getting rutracker magnet from " + url)
		bot.send_message(chat_id=chat_id, text=get_string("getting_rutracker_magnet"))
		resp = requests.get(url, proxies=proxy, timeout=60)

		if resp.status_code != 200:
			raise BaseException("Can't get magnet: " + resp.text)

		text = resp.text

		magnet_index = text.find("magnet", text.find("<a href=\"magnet"))
		index_end = text.find("\"", magnet_index)
		magnet = text[magnet_index:index_end]

		print(magnet)

		return magnet

	except Exception as exp:
		print("Traceback: " + traceback.format_exc())
		print("Exception: " + str(exp))
		bot.send_message(chat_id=chat_id, text=get_string("call_programmer"))


def get_rutor_magnet(bot, update, url):
	try:
		chat_id = get_chat_id(update)

		print("Getting rutor magnet from " + url)
		bot.send_message(chat_id=chat_id, text=get_string("getting_rutracker_magnet"))
		resp = requests.get(url, proxies=proxy, timeout=60)

		if resp.status_code != 200:
			raise BaseException("Can't get magnet: " + resp.text)

		text = resp.text

		magnet_index = text.find("magnet", text.find("<div id=\"download"))
		index_end = text.find("\"", magnet_index)
		magnet = text[magnet_index:index_end]

		print(magnet)

		return magnet

	except Exception as exp:
		print("Traceback: " + traceback.format_exc())
		print("Exception: " + str(exp))
		bot.send_message(chat_id=chat_id, text=get_string("call_programmer"))


def get_nnm_magnet(bot, update, url):
	try:
		chat_id = get_chat_id(update)

		print("Getting nnmclub magnet from " + url)
		bot.send_message(chat_id=chat_id, text=get_string("getting_rutracker_magnet"))
		resp = requests.get(url, proxies=proxy, timeout=60)

		if resp.status_code != 200:
			raise BaseException("Can't get magnet: " + resp.text)

		text = resp.text

		magnet_index = text.find("magnet:")
		index_end = text.find("\"", magnet_index)
		magnet = text[magnet_index:index_end]

		print(magnet)

		return magnet

	except Exception as exp:
		print("Traceback: " + traceback.format_exc())
		print("Exception: " + str(exp))
		bot.send_message(chat_id=chat_id, text=get_string("call_programmer"))


def get_tfile_magnet(bot, update, url):
	try:
		chat_id = get_chat_id(update)

		print("Getting tfile magnet from " + url)
		bot.send_message(chat_id=chat_id, text=get_string("getting_rutracker_magnet"))
		resp = requests.get(url, proxies=proxy, timeout=60)

		if resp.status_code != 200:
			raise BaseException("Can't get magnet: " + resp.text)

		text = resp.text

		magnet_index = text.find("magnet", text.find("<a href=\"magnet"))
		index_end = text.find("\"", magnet_index)
		magnet = text[magnet_index:index_end]

		print(magnet)

		return magnet

	except Exception as exp:
		print("Traceback: " + traceback.format_exc())
		print("Exception: " + str(exp))
		bot.send_message(chat_id=chat_id, text=get_string("call_programmer"))


def get_redirect_url(bot, update, url):
	try:
		chat_id = get_chat_id(update)

		bot.send_message(chat_id=chat_id, text=get_string("getting_redirection"))
		print("Getting redirect from " + url)
		resp = requests.get("http://cinemate.cc/" + url, proxies=proxy, timeout=60)

		if resp.status_code != 200:
			bot.send_message(chat_id=chat_id, text=get_string("get_redirect_failed"))
			raise BaseException("Can't get redirect page by: " + resp.text)

		text = resp.text

		href_index = text.find("http", text.find(u"нажмите на <a href"))
		index_end = text.find("\"", href_index)
		href = text[href_index:index_end]

		print(href)

		return href

	except Exception as exp:
		print("Traceback: " + traceback.format_exc())
		print("Exception: " + str(exp))
		bot.send_message(chat_id=chat_id, text=get_string("call_programmer"))


def get_chat_id(update):
	if update.callback_query is None:
		return update.message.chat_id
	else:
		return update.callback_query.message.chat_id


def show_links(bot, update):
	chat_id = get_chat_id(update)
	chat_data = chats.get_chat_data(chat_id)

	keyboard = []

	for i in range(len(chat_data.links)):
		keyboard.append([InlineKeyboardButton(str(chat_data.links[i]), callback_data="link:" + str(i))])

	msg = bot.send_message(chat_id=chat_id, text=get_string("links_choose"), reply_markup=InlineKeyboardMarkup(keyboard))
	torrent.add_timer(chat_id, msg.message_id)


def get_links(bot, update, links_url):
	try:
		trackers = {"rutracker.org", "tfile.me", "nnmclub.to", "rutor.info"}
		chat_id = get_chat_id(update)
		chat_data = chats.get_chat_data(chat_id)

		bot.send_message(chat_id=chat_id, text=get_string("getting_links"))
		print("http://cinemate.cc/" + links_url)
		resp = requests.get("http://cinemate.cc/" + links_url, proxies=proxy, timeout=60)
		print("Get links")

		if resp.status_code != 200:
			bot.send_message(chat_id=chat_id, text=get_string("get_links_failed"))
			raise BaseException("Can't suck links in [" + str(resp.status_code) + "]: " + resp.text)

		text = resp.text
		chat_data.links.clear()
		tracker_index = 0

		while True:
			tracker_index = text.find("class=\"trackert\"", tracker_index)

			if tracker_index == -1:
				break

			index_end = text.find("/div", tracker_index)
			tracker = text[tracker_index + 17:index_end - 1].replace("\t", "").replace(" ", "").replace("\n", "")
			tracker_index = tracker_index + 1

			if tracker not in trackers:
				continue

			quality_index = text.find(">", text.find("<div", tracker_index))
			index_end = text.find("/div", quality_index)
			quality = text[quality_index + 1:index_end - 1].replace("\t", "").replace(" ", "").replace("\n", "")

			translation_index = text.find("<div class=\"perevodt\"", quality_index)
			translation_end = text.find("<div style=\"width:20px; float:right\">", translation_index)
			span_index = translation_index
			translations = []
			while True:
				span_index = text.find(">", text.find("<span", span_index))

				if span_index > translation_end or span_index <= 0:
					break

				index_end = text.find("<span>&nbsp;", span_index)
				translation = text[span_index + 1:index_end]
				span_index = index_end + 5
				translations.append(translation)

			link_index = text.find("href=\"/go/s", translation_end)
			index_end = text.find("\"", link_index + 12)
			link = text[link_index + 12:index_end]

			file_size_index = text.find(">", text.find("<div style=\"height:1.2em; overflow: hidden;\"", link_index))
			seeders_index = text.find(">", text.find(u"Число раздающих", index_end))
			if seeders_index < file_size_index and seeders_index > 0:
				index_end = text.find("</div", seeders_index)
				seeders = text[seeders_index + 1:index_end].replace("\t", "").replace(" ", "").replace("\n", "")
			else:
				seeders = 1

			index_end = text.find("/div", file_size_index)
			file_size = text[file_size_index + 1:index_end - 1].replace("\t", "").replace(" ", "").replace("\n", "")

			chat_data.links.append(Link(tracker, quality, translations, link, file_size, int(seeders)))

		if len(chat_data.links) > 0:
			chat_data.links.sort(key=operator.attrgetter("seeders"), reverse=True)
			print("Links: " + str(len(chat_data.links)))
			if len(chat_data.links) > 50:
				del chat_data.links[50 - len(chat_data.links):]
				print("Links: " + str(len(chat_data.links)))

			show_links(bot, update)
		else:
			bot.send_message(chat_id=chat_id, text=get_string("get_links_failed"))
	except Exception as exp:
		print("Traceback: " + traceback.format_exc())
		print("Exception: " + str(exp))
		bot.send_message(chat_id=chat_id, text=get_string("call_programmer"))


def download_magnet(bot, update, url):
	try:
		chat_id = get_chat_id(update)
		chat_data = chats.get_chat_data(chat_id)

		if len(url) <= 1:
			bot.send_message(chat_id=chat_id, text=get_string("magnet_is_dead"))
			chat_data.links.remove(chat_data.chosen_link)
			show_links(bot, update)
			return False

		bot.send_message(chat_id=chat_id, text=get_string("download_by_magnet"))
		print("Starting download process through magnet link")
		print("Magnet: " + url)
		torrent.download_magnet(bot, update, url, str(chat_data.chosen_movie))

	except Exception as exp:
		print("Traceback: " + traceback.format_exc())
		print("Exception: " + str(exp))
		bot.send_message(chat_id=chat_id, text=get_string("call_programmer"))


if os.environ.get("BOT_USERS") is not None:
	allowed_users = os.environ["BOT_USERS"].split(":")
	print("Filtering by users:" + str(allowed_users))

	if len(allowed_users) > 0:
		users_filter = Filters.user(username=allowed_users)
else:
	users_filter = Filters.all

updater = Updater(
	token=os.environ["BOT_TOKEN"],
	request_kwargs=
	{
		"proxy_url":"http://tor:8118",
		"read_timeout": 60
	}
)
dispatcher = updater.dispatcher
dispatcher.add_handler(CommandHandler("start", start, users_filter))
dispatcher.add_handler(CommandHandler("help", help, users_filter))
dispatcher.add_handler(CommandHandler("search", search, users_filter))
dispatcher.add_handler(CommandHandler("status", torrent.status, users_filter))
dispatcher.add_handler(CommandHandler("torrents", torrent.torrents, users_filter))
dispatcher.add_handler(CommandHandler("actions", torrent.actions, users_filter))
dispatcher.add_handler(CallbackQueryHandler(callback))
updater.start_polling()