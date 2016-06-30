import HTMLParser
import dateutil.relativedelta
import errno
import exceptions
import json
import os.path
import pushbullet
import threading
import time
import sys
from BeautifulSoup import BeautifulSoup
from datetime import datetime
from urllib2 import urlopen
try:
    import pync
    from pync.TerminalNotifier import TerminalNotifier
except:
    pass

debug = False
debug_json_file = 'catalog.json'
logfile = 'evangelus_log.txt'

class Board:
    def __init__(self, board, order='rpm', reverse=True):
        self.board = board
        self.order = order
        self.reverse = reverse

        api_file = self.load_api_file(self.board)
        if api_file:
            api_json = json.loads(api_file)
            threads = []
            for page in api_json:
                for thread in page['threads']:
                    thread = Thread(self.board, thread)
                    threads.append(thread)

            threads.sort(key=lambda t: t.__dict__[self.order],
                                   reverse = self.reverse)

            self.threads = threads
            print 'Board /{0}/ init complete with {1} threads sorted by `{2}`.'\
                .format(self.board, len(self.threads), self.order)
        else:
            print 'Error during board init.'
            self.error = 'file'

#   @timeout(30, os.strerror(errno.ETIMEDOUT))
    def load_api_file(self, board):
        global debug
        global debug_json_file
        if debug:
            try:
                with open(debug_json_file, 'r') as f:
                    api_file = f.read()
                print 'Got JSON from local debug file.'
            except exception.Exception as e:
                print e, '\nError while attempting to get local debug JSON.'
                return None
        else:
            try:
                api_file = urlopen('https://a.4cdn.org/{0}/catalog.json'\
                                   .format(board)).read()
                print 'Got JSON from online 4chan API.'
            except exceptions.Exception as e:
                print e, '\nError while attempting to get 4chan API JSON.'
                return None
        return api_file

    def remove_subjects(self, matches):
        threads = self.threads
        i = 0
        r = 0
        while i < len(threads):
            if hasattr(threads[i], 'sub')\
            and any(match in threads[i].sub.lower() for match in matches):
                del threads[i]
                r = r + 1
            else:
                i = i + 1
        self.threads = threads
        print 'Removed {0} threads matching {1}.'.format(r, str(matches))


    def remove_read(self):
        unread = []
        for t in self.threads:
            if t.is_read() is False:
                unread.append(t)
        self.threads = unread

    def print_debug_list(self):
        print '================\nDEBUG\n==============='
        for thread in self.threads:
            if thread.is_read():
                print '@@@@@@@@@@@@@@@@@@@ read @@@@@@@@@@@@@@@@@@@'
            if hasattr(thread, 'sub'):
                print thread.sub.encode('utf8')
            print '{0}: {1}'.format(thread.rpm,
                                    thread.excerpt.encode('utf8'))
            if thread.is_read():
                print '@@@@@@@@@@@@@@@@@@@ read @@@@@@@@@@@@@@@@@@@'
            print '--------------------'
        print '============\nEnd of top threads:\n============'


class Thread:
    def __init__(self, board, jsondata):
        self.__dict__ = jsondata
        self.board = board
        self.url = 'http://boards.4chan.org/{0}/thread/{1}'\
             .format(board, self.no)
        self.set_excerpt()
        self.set_times()

    def set_excerpt(self):
        self.excerpt = 'No excerpt available'
        if hasattr(self, 'name'):
            self.excerpt = self.name
        if hasattr(self, 'sub'):
            self.excerpt = self.sub
        if hasattr(self, 'com'):
            self.excerpt = self.com[:140]

        s = BeautifulSoup(self.excerpt).getText()
        pars = HTMLParser.HTMLParser()
        s = pars.unescape(s)
        self.excerpt = s

    def set_times(self):
        self.age_seconds = (datetime.now()\
                            - datetime.fromtimestamp(self.time)).seconds

        age = dateutil.relativedelta.relativedelta\
              (datetime.now(), datetime.fromtimestamp(self.time))
        if age.hours:
            if age.minutes > 9:
                self.age_pretty = '{0}:{1}h'.format(age.hours,age.minutes)
            else:
                self.age_pretty = '{0}:0{1}h'.format(age.hours,age.minutes)
        else:
            self.age_pretty = '{0}min'.format(age.minutes)

        self.rpm = float("%.1f" %\
                         (float(self.replies) * 60.0 / float(self.age_seconds)))

    def is_read(self):
        global logfile
        if os.path.isfile(logfile):
            with open(logfile, 'r') as f:
                lines = f.read().splitlines()
            if str(self.no) in lines:
                return True
            else:
                return False
        else:
            print 'No logfile (yet), assuming unnotified:', self.no
            return False

    def mark_read(self):
        with open(logfile, 'a') as f:
            f.write(str(self.no) + '\n')
            print 'Marked as notified:', self.no

    def notify(self):
        if self.is_read():
            print 'Already notified, not notifying again:', self.excerpt
        else:
            if hasattr(self, 'country'):
                s = 'From {0} with {1} posts in {2} = {3}/min'
                s_min = '{0}{1}a{2}/m:{3}'
            else:
                self.country = ''
                s = 'Thread with {1} posts in {2} = {3}/min'
                s_min = '{1}a{2}/m:{3}'
            msg_string = s.format(self.country,
                                  self.replies,
                                  self.age_pretty,
                                  self.rpm)
            msg_string_min = s_min.format(self.country,
                                          self.replies,
                                          self.rpm,
                                          self.excerpt)
            try:
                pync = TerminalNotifier()
                pync.notify(self.excerpt,
                            title=msg_string,
                            open=self.url)
            except:
                pass

            pb=pushbullet.Pushbullet('o.NWYoex8JnjUsNf554Aqp8DoiCm2Z07cJ')
            pb.push_link(msg_string_min,
                         self.url)

            self.mark_read()

class Daemon(threading.Thread):
    def __init__(self,
                 board='pol',
                 remove_subjects_matchlist=['edition',],
                 min_replies=0,
                 min_rpm=2.9,
                 interval=300):
        threading.Thread.__init__(self)
        self.board = board
        self.remove_subjects_matchlist = remove_subjects_matchlist
        self.min_replies = min_replies
        self.min_rpm = min_rpm
        self.interval = interval

    def run(self):
        global debug
        while True:
            print 'Daemon running...'
            b = Board(self.board)
            if hasattr(b, 'error'):
                print 'Error:', b.error
            else:
                b.remove_subjects(self.remove_subjects_matchlist)
                if debug:
                    b.threads = b.threads[:15]
                    b.print_debug_list()
                b.remove_read()
                t = b.threads[0]

                if float(t.replies) > self.min_replies and t.rpm > self.min_rpm:
                    t.notify()
                else:
                    percentage = "%.1f" % (t.rpm * 100 / self.min_rpm)
                    print 'No hot threads, closest @ {0}/min ({1}%): {2}'\
                          .format(t.rpm, percentage, t.excerpt[:60])

            print '... Daemon finished at', time.strftime(\
                  '%Y/%m/%d, %H:%M:%S', time.localtime(time.time()))

            if debug:
                break
            else:
                print 'Waiting {0} seconds...'.format(self.interval)
                time.sleep(self.interval)
                os.system('clear')

d = Daemon(interval=30)
d.start()
