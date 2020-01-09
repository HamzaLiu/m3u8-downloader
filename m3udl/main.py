import random
import signal
import requests
import requests.exceptions as exc
from .parse import *
from . import configure as conf


class Preprocess:
    def __init__(self, m3u_url, choice_flag=False):
        self.root_url = m3u_url
        self.abs_url, self.default_name = self.init_abs_url(m3u_url)
        self.choice_flag = choice_flag

        signal.signal(signal.SIGINT, Preprocess.handle_interrupt)

    def init_abs_url(self, m3u_url):
        return re.search(r'(.*/)([^?]*)', m3u_url).group(1, 2)

    def get_target_url(self, m3u_url=''):
        headers = {'user-agent': random.choice(conf.UA)}
        try:
            resp = requests.get(m3u_url or self.root_url, headers=headers,
                                verify=conf.VERIFY, timeout=conf.TIMEOUT)
            if resp.status_code >= 500:
                print('Error: status code - %d ' % resp.status_code)
                return [], 0
            elif resp.status_code >= 400:
                print('Error: status code - %d %s' % (resp.status_code, '源文件获取失败，url 解析失败！'))
                return [], -1
            parser = Parse(self.abs_url, resp.text)
            top_playlist = parser.stream_inf()
            sec_playlist, duration = parser.slice_url()
            if top_playlist:
                selected_url = self.print_to_screen(top_playlist)
                self.abs_url, self.default_name = self.init_abs_url(selected_url)
                return self.get_target_url(selected_url)

            # return sec_playlist, Preprocess.init_duration(duration)
            return sec_playlist, duration or -1
        except (exc.ConnectTimeout, exc.ReadTimeout, exc.ConnectionError):
            return [], 0

    def print_to_screen(self, data):
        data = sorted(data, key=lambda x: int(x['BANDWIDTH']), reverse=True)
        print('\n# 当前链接有如下码率可选\n')

        for ind in range(len(data)):
            print('## --------------------------')
            print('tag %d' % (ind + 1))
            bitrate = int(data[ind]['BANDWIDTH'])/1024
            unit = 'kbps' if bitrate < 1024 else 'Mbps'
            if bitrate >= 1024:
                bitrate = bitrate/1024
            print('\tbitrate\t\t\t %.1f ' % bitrate + unit)
            if data[ind].get('NAME', ''):
                print('\tquality\t\t\t', data[ind]['NAME'])
            if data[ind].get('RESOLUTION', ''):
                print('\tresolution\t\t', data[ind]['RESOLUTION'])
            if data[ind].get('CODECS', ''):
                print('\tcodecs\t\t\t', data[ind]['CODECS'])
            print()

        while True:
            try:
                if self.choice_flag:
                    choice = 1
                    print('已选择最高比特率选项。\n')
                else:
                    choice = int(input('请输入tag序号:'))
                if choice <= len(data):
                    break
            except ValueError:
                pass
            except EOFError:
                print()

        return data[choice - 1]['url']

    @classmethod
    def init_duration(cls, duration):
        s = ''
        if duration >= 3600:
            s = '%dh ' % (duration // 3600)
            duration = duration % 3600
        if duration >= 60:
            s += '%dmin ' % (duration // 60)
            duration = duration % 60
        s += '%ds' % duration

        return s

    @classmethod
    def handle_interrupt(cls, num, frame):
        pass
