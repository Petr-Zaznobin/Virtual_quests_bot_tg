import os
from dotenv import find_dotenv, load_dotenv

dotenv_path = find_dotenv() #ищем нужный .env файл
load_dotenv(dotenv_path) #загружаем переменные из найженного файла
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
db_name = os.getenv("db_name")
user = os.getenv("user")
password = os.getenv("password")
host = os.getenv("host")
port = os.getenv("port")