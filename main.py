import sys
import os
import requests
import time
import logging
import atexit
from bs4 import BeautifulSoup
from sqlalchemy import Column, Integer, String, DateTime, Text, create_engine, update
from sqlalchemy.orm import sessionmaker, declarative_base
from datetime import datetime
from requests.exceptions import RequestException
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager

log_directory = "logs"
if not os.path.exists(log_directory):
    os.makedirs(log_directory)

log_filename = f"logfile_{time.strftime('%Y%m%d%H%M%S')}.log"
log_path = os.path.join(log_directory, log_filename)

logging.basicConfig(
    format='%(asctime)s | %(levelname)s: %(message)s',
    level=logging.NOTSET,
    handlers=[
        logging.FileHandler(log_path, 'w', 'utf-8'),
        logging.StreamHandler()
    ])
logging.getLogger("urllib3").propagate = False

Base = declarative_base()


class CourseNews(Base):
    __tablename__ = 'COURSE_NEWS'

    id = Column(Integer, primary_key=True)
    name = Column(String(255))
    short_name = Column(String(50))
    url = Column(String(255))
    news_date = Column(DateTime)
    news = Column(Text)
    message = Column(Text)


def get_course_info(session, link):
    try:
        response1 = session.get(url=link)
    except RequestException as e:
        logging.error(f"Can't access course. Reason: {e}")
        return None, None, None

    soup = BeautifulSoup(response1.content, 'html.parser')
    try:
        title = soup.find_all('a', class_='w-100 h-100 d-block')[0].get('title')
        link = soup.find_all('a', class_='w-100 h-100 d-block')[0].get('href')
        tmp = soup.find_all('time')[1].get('data-timestamp')
        date = datetime.utcfromtimestamp(float(tmp))
        response2 = session.get(link)
        soup = BeautifulSoup(response2.content, 'html.parser')
        div_element = soup.find('div', class_='post-content-container')
        messages = [p.get_text(strip=True) for p in div_element.find_all('p')]
        message = '\n'.join(messages)

    except Exception as e:
        logging.error(f"Can't access course info. Reason: {e}")
        return None, None, None
    return title, message, date


def check_if_logged_in(session):
    try:
        response = session.get("https://courses.finki.ukim.mk")
        soup = BeautifulSoup(response.content, 'html.parser')
        if soup.find('span', class_="usertext mr-1") is None:
            raise RequestException("Login failed.")
        else:
            os.system('cls' if os.name == 'nt' else 'clear')
            logging.info("Logged in successfully.")
    except RequestException as e:
        logging.error(f"{e}")
        input("Press any key to exit...")
        sys.exit()


def update_course(session, short_name, title, message, date):
    date_object = datetime.strptime(str(date), "%Y-%m-%d %H:%M:%S")
    formatted_date = date_object.strftime("%d %B %Y %H:%M")
    logging.info(f"\n==========\n{short_name}\n{title}\n{message}\n{formatted_date}")

    stmt = update(CourseNews).where(CourseNews.short_name == short_name).values(
        news=title,
        message=message,
        news_date=date
    )

    session.execute(stmt)
    session.commit()


def get_credentials():
    session_file_path = "credentials.txt"
    try:
        with open(session_file_path, "r") as session_file:
            lines = session_file.readline().strip().split(':')
            return lines[0], lines[1]
    except FileNotFoundError:
        logging.error(f"File {session_file_path} not found.")
        return None, None
    except Exception as e:
        print(f"Error: {e}")
        return None, None


def get_cookie():
    options = webdriver.ChromeOptions()
    driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()),
                              options=options)
    driver.get('https://cas.finki.ukim.mk/cas/login?service=https%3A%2F%2Fcourses.finki.ukim.mk%2Flogin%2Findex.php')

    username, password = get_credentials()
    username_input = driver.find_element("id", "username")
    password_input = driver.find_element("id", "password")
    username_input.send_keys(username)
    password_input.send_keys(password)
    login_button = driver.find_element("name", "submit")
    login_button.click()
    driver.implicitly_wait(10)
    session_cookie = driver.get_cookie('MoodleSession').get('value')
    return session_cookie


def main():
    session = requests.Session()
    cookies = {'MoodleSession': f"{get_cookie()}"}
    session.cookies.update(cookies)
    check_if_logged_in(session)
    sleep_time = 30

    engine = create_engine('sqlite:///database.db')
    Base.metadata.create_all(engine)
    Session2 = sessionmaker(bind=engine)
    session2 = Session2()
    all_course_news = session2.query(CourseNews).all()

    try:
        while True:
            for course_news in all_course_news:
                title, message, date = get_course_info(session, course_news.url)
                if title is not None:
                    if title == course_news.news:
                        if date != course_news.news_date:
                            update_course(session2, course_news.short_name, title, message, date)
                    else:
                        update_course(session2, course_news.short_name, title, message, date)
                time.sleep(sleep_time)
    except Exception as e:
        logging.error(f"An error occurred. Reason: {e}")
    finally:
        session.close()


def exit_handler():
    logging.shutdown()


atexit.register(exit_handler)

if __name__ == '__main__':
    main()
