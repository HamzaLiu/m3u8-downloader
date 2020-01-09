import random
import signal
import time
import os
import threading
import shutil
import requests
import requests.exceptions as exc
from . import configure as conf

LOCK = threading.Lock()


class Download:
    def __init__(self, filename, playlist, path='./', thread_num=8, max_retries=5, print_flag=True):
        self.pause = False
        self.log = open('./download.log', 'a' if os.path.exists('./download.log') else 'w')
        self.filename = filename
        self.playlist = playlist        
        self.th_num = thread_num
        self.max_retries = max_retries
        self.print_flag = print_flag
        self.path = path
        if not os.path.exists(path):
            self.print_and_record('提供的路径不存在！将使用默认路径！')
            self.path = './'

        self.chunk_size = 128
        self.per_interval_chunks = 0
        self.total_length = [0] * self.th_num
        self.playlist_ind = 0
        self.folder_name = os.path.join(self.path, 'download_%.0f/' % time.time())
        self.failed_flag = False
        self.breakpoint_info = []
        self.breakpoint_diff_len = 0
        self.thread_available = [False] * self.th_num

        self.download_info = []
        for ind in range(max(len(self.playlist), self.th_num)):
            self.download_info.append({})
        self.thread_pool = []
        for th in range(self.th_num):
            self.thread_pool.append(threading.Thread())

        self.curr_slice_size = [0] * self.th_num
        self.slice_downloaded_length = [0] * self.th_num
        self.completed_chunk = 0

        if playlist and playlist[0].get('length', ''):
            self.generate_range()

        # new download folder and file
        if not os.path.exists(self.folder_name):
            os.mkdir(self.folder_name)
        for seq in range(self.th_num):
            f = open(self.folder_name + 'tmp%d' % seq, 'wb')
            f.close()

        self.available_flag = -1
        threading.Thread(target=self.check_availability).start()

    def generate_range(self):
        tmp = 0
        for i in range(len(self.playlist)):
            length = int(self.playlist[i]['length'])
            self.playlist[i]['range'] = (tmp, tmp + length - 1)
            tmp += length

    def print_and_record(self, prompt):
        # if the flag is False, the prompt information is not printed
        LOCK.acquire()
        if self.print_flag:
            print('\n%s' % prompt)
        self.log.write(time.strftime('%y-%m-%d %H:%M:%S') + '\n%s\n' % prompt)
        LOCK.release()

    def init_download_info(self, info_dict, ind, seq, pos=-1, file_pos=-1):
        # params 'pos' and 'file_pos' mean a restarted thread
        if pos == -1:
            self.slice_downloaded_length[seq], self.curr_slice_size[seq] = 0, 0
        headers = {'user-agent': random.choice(conf.UA)}
        if info_dict['length']:
            headers['range'] = 'bytes=%d-%d' % (
                info_dict['range'][0] + (pos if pos != -1 else 0), info_dict['range'][1]
            )
        elif pos != -1:
            headers['range'] = 'bytes=%d-' % pos

        size = file_pos if file_pos != -1 else self.total_length[seq]
        self.download_info[ind]['seq'] = seq
        self.download_info[ind]['start'] = size
        self.download_info[ind]['end'] = size + (pos if pos != -1 else 0)

        return headers, size

    def check_retries(self, retries, ind, seq):
        if retries < self.max_retries:
            return 0
        if sum(self.thread_available) < self.th_num - 1:
            self.print_and_record('slice %d 重试次数达到上限！尝试减少线程数。' % ind)
            self.thread_available[seq] = True
        else:
            self.print_and_record('slice %d 重试次数达到上限！下载失败。' % ind)
            self.failed_flag = True
            self.pause = True
        return 1

    def download(self, info_dict, ind, seq, pos=-1, file_pos=-1, retries=0):
        headers, size = self.init_download_info(info_dict, ind, seq, pos, file_pos)
        while not self.pause:
            if self.check_retries(retries, ind, seq):
                break
            try:
                resp = requests.get(info_dict['url'], headers=headers, verify=conf.VERIFY,
                                    stream=True, timeout=conf.TIMEOUT)
                if self.pause:
                    break
                elif resp.status_code >= 500:
                    retries += 1
                    self.print_and_record('slice %d Error: status code - %d %s' %
                                          (ind, resp.status_code, '第 %d 次重试……' % retries))
                    time.sleep(2)
                    continue
                elif resp.status_code >= 400:
                    self.print_and_record('slice %d Error: status code - %d %s' %
                                          (ind, resp.status_code, '源文件获取失败，下载失败！'))
                    self.failed_flag = True
                    break

                if pos == -1 or not self.curr_slice_size[seq]:
                    self.curr_slice_size[seq] = int(resp.headers.get('content-length', '0'))
                with open(self.folder_name + 'tmp%d' % seq, 'ab') as current_file:
                    for chunk in resp.iter_content(self.chunk_size):
                        # when one thread failed, other threads should also terminate
                        if self.failed_flag or self.pause:
                            break
                        current_file.write(chunk)
                        self.per_interval_chunks += 1
                        self.total_length[seq] += len(chunk)
                        self.slice_downloaded_length[seq] += len(chunk)
                        self.download_info[ind]['end'] += len(chunk)
                break
            except (exc.ConnectTimeout, exc.ReadTimeout, exc.ConnectionError, exc.ChunkedEncodingError) as e:
                self.print_and_record('slice %d Error:' % ind + str(e) + '第 %d 次重试……' % (retries + 1))
                length = self.download_info[ind]['end'] - size
                self.download(info_dict, ind, seq, length, size, retries+1)
                return

        if not self.pause and (not self.thread_available[seq] or self.slice_downloaded_length[seq]):
            # solving synchronization problems.
            self.slice_downloaded_length[seq], self.curr_slice_size[seq] = 0, 0
            self.completed_chunk += 1
        else:
            self.breakpoint_info.append({
                'dict': info_dict, 'seq': seq, 'ind': ind, 'file_len': size,
                'length': self.download_info[ind]['end'] - size
            })

    def main_thread(self):
        time.sleep(0.75)
        for i in range(self.th_num):
            # the program cannot return directly here, because it
            # needs to wait until all download threads are finished
            if self.pause or (self.failed_flag and any([t.is_alive() for t in self.thread_pool])):
                break
            # downloaded failed
            if self.failed_flag:
                return -1
            if self.thread_available[i]:
                continue
            
            # restart main thread
            # if the resource doesn't support recovery from breakpoint,
            # currently unfinished slices need to be re-downloaded
            if self.breakpoint_info:
                inf = self.breakpoint_info[0]
                if self.available_flag == 0:
                    inf['length'], inf['file_len'] = -1, -1
                self.thread_pool[inf['seq']] = threading.Thread(
                    target=self.download,
                    args=(inf['dict'], inf['ind'], inf['seq'], inf['length'], inf['file_len'])
                )
                self.thread_pool[inf['seq']].start()
                del self.breakpoint_info[0]
                continue

            # the following line of code should be executed after
            # restart program execution is completed
            if self.playlist_ind >= len(self.playlist):
                break
            if not self.thread_pool[i].is_alive():
                self.thread_pool[i] = threading.Thread(
                    target=self.download,
                    args=(self.playlist[self.playlist_ind], self.playlist_ind, i)
                )
                self.playlist_ind += 1
                self.thread_pool[i].start()

        return not any([thread.is_alive() for thread in self.thread_pool])

    def start(self, duration):
        signal.signal(signal.SIGINT, self.handle_interrupt)
        # start downloading
        last_time = time.time()
        print('\n# 视频时长: %s' % duration)
        while True:
            opcode = self.main_thread()
            if (opcode and self.pause) or self.post_processing(opcode):
                break
            if not self.pause:
                print('\r' + self.status(time.time() - last_time), end='')
            last_time = time.time()
        if not self.pause:
            return
        continue_flag = input('成功暂停，是否继续(y/n):')
        self.pause = False
        if continue_flag == 'n':
            self.post_processing(-1)
            return
        elif continue_flag != 'y':
            print('输入不正确，默认继续。')

        # restart downloading
        self.start(duration)

    def status(self, interval):
        length, downloaded_length, th_num = 0, 0, 0

        for i in range(self.th_num):
            if self.slice_downloaded_length[i] and self.curr_slice_size[i]:
                if self.thread_pool[i].is_alive():
                    th_num += 1
                length += self.curr_slice_size[i]
                downloaded_length += self.slice_downloaded_length[i]

        s1 = (sum(self.total_length) - self.breakpoint_diff_len) / 1024
        unit1, s1 = ('MB', s1 / 1024) if s1 > 1024 else ('KB', s1)
        percent1 = self.completed_chunk / len(self.playlist)
        percent2 = th_num / len(self.playlist)
        percent3 = length and percent2 * downloaded_length / length
        p = (percent1 + percent3) * 100
        # print(self.completed_chunk, th_num, length, downloaded_length)

        s2 = self.chunk_size * self.per_interval_chunks / 1024 / interval
        self.per_interval_chunks = 0
        unit2, s2 = ('MB/s', s2 / 1024) if s2 >= 1000 else ('KB/s', s2)

        return '已下载: %.1f %s 下载进度: %.2f %% 下载速度: %.2f %s\t\t' % (s1, unit1, p, s2, unit2)

    def merge_files(self):
        video = open(os.path.join(self.path, self.filename), 'wb')
        for pl_ind in range(len(self.playlist)):
            seq = self.download_info[pl_ind].get('seq', 0)
            start = self.download_info[pl_ind].get('start', 0)
            length = self.download_info[pl_ind].get('end', 0) - start
            f = open(self.folder_name + 'tmp%d' % seq, 'rb')
            f.seek(start)
            video.write(f.read(length))
            f.close()
        video.close()

    def post_processing(self, opcode):
        if self.pause:
            return False

        if opcode == 1:
            self.merge_files()
        if opcode == 1 or opcode == -1:
            try:
                shutil.rmtree(self.folder_name)
                # the current module execution is end, close the log file
                self.log.close()
                return True
            except PermissionError as e:
                # other threads may occupy files to be deleted,
                # when the 'opcode' is equal to -1
                self.print_and_record(str(e))
                for i in range(self.th_num):
                    if os.path.exists(self.folder_name + 'tmp%d' % i):
                        with open(self.folder_name + 'tmp%d' % i):
                            pass
                time.sleep(0.5)
                return self.post_processing(opcode)
        return False

    def check_availability(self):
        # check if the breakpoint is available
        headers = {
            'user-agent': random.choice(conf.UA),
            'range': 'bytes=0-15'
        }
        try:
            resp = requests.head(self.playlist[0]['url'], headers=headers,
                                 verify=conf.VERIFY, timeout=conf.TIMEOUT)
        except (exc.ConnectTimeout, exc.ReadTimeout, exc.ConnectionError):
            return self.check_availability()
        self.available_flag = 1 if resp.status_code == 206 else 0

    def handle_interrupt(self, num, frame):
        if self.available_flag == -1:
            print('\n正在检测是否支持断点续传，请稍后…')
            return
        self.pause = True
        print('\n\n正在暂停，请稍后…')
        if self.available_flag == 0:
            print("Warning! The resource doesn't support recovery from breakpoint!")
            self.breakpoint_diff_len += sum(self.slice_downloaded_length)
