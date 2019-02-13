This is a pretty simple telegram bot which allows you do download torrents which were announced on cinemate.cc
We are using python telegram bot framework, tor and qbitorrent. So you don't need any vpn.

In case you don't have telegram bot please reach @BotFather to get one.
Before you hit "docker-compose up -d", please do next:
* In docker-compose.yml define BOT_TOKEN with HTTP API token of your bot
* Also provide BOT_USERS value with names of users who will be allowed to use this bot. And don't forget to separate them with colon. For example: @user1:@user2 Everyone will have access to bot in case you will not define this variable.
* Also please define 3 folders: CONFIG_FOLDER, TORRENTS_FOLDER and DOWNLOADS_FOLDER. First 2 used for configuration and working of qBitTorrent and last one will contain all downloaded movies.
* In case you running under windows, don't forget to allow docker for mounting (Settings->Shared drivers)

Это простой телеграм бот, который позволяет искать и скачивать торренты, описанные на cinemate.cc
Используется питоновский телеграм-бот фреймворк, Tor и qBitTorrent, поэтому никакой VPN не нужен.
Если у вас нет телеграм бота, то просто стукнитесь к @BotFather, очень быстро создадите.
Прежде чем запустить всё это дело через "docker-compose up -d":
* В docker-compose.yml определите переменную BOT_TOKEN с токеном вашего бота
* Также определите BOT_USERS, где через двоеточие перечислите имена пользователей, которые будут иметь возможность отправлять команды боту. Например: @user1:@user2 Без всяких ковычек. Если ничего указано не будет, доступ будут иметь все кто попало.
* Также вместо CONFIG_FOLDER и TORRENTS_FOLDER определите две папки, куда будет складываться рабочая информация qBitTorrent'а. А DOWNLOADS_FOLDER определит место, куда будут складываться все скачиваемые файлы
* Если вы запускаетесь под виндой, то не забудьте в настройках докера разрешить ему шарить папки по указанному вами диску. (Settings->Shared drivers)
