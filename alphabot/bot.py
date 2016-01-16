import json
import logging
import os
import re
import sys
import traceback

from tornado import websocket, gen, httpclient
import requests

log = logging.getLogger(__name__)


SLACK_TOKEN=os.getenv('SLACK_TOKEN')
SLACK_START='https://slack.com/api/rtm.start'
SLACK_REACT='https://slack.com/api/reactions.add'

def get_instance():
    if not Bot.instance:
        log.debug('Creating a new bot instance...')
        Bot.instance = Bot()

    return Bot.instance


class Bot(object):

    instance=None

    def __init__(self):
        self.regex_commands = []
        self.engine = 'slack'

    @gen.coroutine
    def connect(self):
        log.info('Authenticating...')
        response = requests.get(SLACK_START + '?token=' + SLACK_TOKEN).json()
        log.info('Logged in!')

        self.socket_url = response['url']
        self.connection = yield websocket.websocket_connect(self.socket_url)

    @gen.coroutine
    def gather_scripts(self):
        from scripts import pingpong, desk, random

        self.scripts = []
        self.scripts.append(pingpong)
        self.scripts.append(desk)

    @gen.coroutine
    def send(self, text, to):
        payload = json.dumps({
            "id": 1,
            "type": "message",
            "channel": to,
            "text": text
        })
        log.debug(payload)
        yield self.connection.write_message(payload)

    def get_chat(self, message):
        return Chat(bot=self, message=message)

    @gen.coroutine
    def start(self):

        while True:
            message = yield self.connection.read_message()
            log.info('MESSAGE')
            log.info(message)

            if message is None:
                break

            message = json.loads(message)
            if not message.get('text'):
                continue

            chat = self.get_chat(message)

            # Old style of invoking scripts
            for script in self.scripts:
                try:
                    yield script.hear(message.get('text'), chat)
                except:
                    chat.reply('Script %s had an error.' % script.__name__)
                    traceback.print_exc(file=sys.stdout)

            # New style of invoking scripts
            for pair in self.regex_commands:
                regex, function = pair
                match = re.match(regex, message.get('text'))
                if match:
                    chat = self.get_chat(message)
                    chat.regex_groups = match.groups()
                    yield function(chat)


    def add_command(self, regex):

        def decorator(function):
            log.info('New Command: "%s" => %s()' % (regex, function.__name__))
            self.regex_commands.append((regex, function))

        return decorator 


class Chat(object):

    def __init__(self, bot, message):
        self.bot = bot
        self.message = message

    @gen.coroutine
    def reply(self, text):
        """Reply to the original channel of the message."""
        yield self.bot.send(text, to=self.message.get('channel'))

    @gen.coroutine
    def react(self, reaction):
        client = httpclient.AsyncHTTPClient()
        yield client.fetch(
            (SLACK_REACT + 
            '?token=' + SLACK_TOKEN +
            '&name=' + reaction +
            '&timestamp=' + self.message.get('ts') + 
            '&channel=' + self.message.get('channel')))

